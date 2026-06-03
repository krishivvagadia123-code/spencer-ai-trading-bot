"""
Phase H.1 — cached research + signal engine + scanner tests.

Required guarantees (per spec):
  1. Cached research refreshes once per day per (symbol, asof).
  2. Signal engine is deterministic.
  3. No LLM/API call in intraday scan path.
  4. Signal logs include all required fields.
  5. Paused/killed state marks candidate as blocked.
  6. No BUY is executed in Phase H.1.
"""

from datetime import date, datetime
from pathlib import Path
import json
import pytest

from bot import control
from bot.config import RiskConfig, IndicatorConfig, FeeConfig
from bot.db import init_db, set_db_path, get_conn
from bot.portfolio import Portfolio, Position
from bot.research import (
    NeutralResearchProvider, ResearchSnapshot, get_or_fetch,
    list_snapshots_for_date, score_source_data,
)
from bot.scanner import list_recent_candidates, scan_once
from bot.signals import (
    BUY_THRESHOLD, SELL_THRESHOLD, Signal, SignalCandidate,
    SizingPreview, TechnicalSnapshot,
    build_candidate, classify_signal, compute_risk_score,
    compute_technical_score, compute_total_score,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_db(tmp_path):
    p = tmp_path / "h1.db"
    set_db_path(p)
    init_db()
    yield p
    set_db_path(Path(__file__).parent.parent / "kite_bot.db")


@pytest.fixture
def tmp_control(tmp_path):
    p = tmp_path / "ctrl.json"
    control.set_control_path(p)
    yield p
    control.set_control_path(control.DEFAULT_CONTROL_PATH)


@pytest.fixture
def risk_cfg():
    return RiskConfig(
        risk_per_trade_pct=1.0,
        max_open_positions=5,
        max_daily_loss_pct=10.0,
        max_drawdown_pct=25.0,
        max_total_exposure_pct=200.0,
        max_symbol_notional_pct=30.0,
    )


@pytest.fixture
def indi_cfg():
    return IndicatorConfig()


@pytest.fixture
def fee_cfg():
    return FeeConfig()


@pytest.fixture
def fresh_pf():
    return Portfolio.fresh(starting_balance=200_000.0)


class _CountingProvider:
    """Counts fetch() calls — proves cache prevents repeat external work."""
    def __init__(self, source: dict | None = None):
        self.calls = 0
        self.source = source or {"provider": "counting", "placeholder": True}
    def fetch(self, symbol: str, asof: date) -> dict:
        self.calls += 1
        return {**self.source, "symbol": symbol, "asof": asof.isoformat()}


class _ExplodingProvider:
    """Raises if fetch is ever called — proves cache hits never invoke provider."""
    def fetch(self, symbol: str, asof: date) -> dict:
        raise AssertionError(
            f"provider.fetch called for {symbol} on {asof} — "
            "cache layer must short-circuit external research calls"
        )


def _bullish_tech(price=2500.0) -> TechnicalSnapshot:
    return TechnicalSnapshot(
        price=price, rsi=80.0, ema_fast=2510.0, ema_slow=2480.0,
        supertrend_trend="green", vwap=price - 5, atr=12.0,
    )


def _bearish_tech(price=2500.0) -> TechnicalSnapshot:
    return TechnicalSnapshot(
        price=price, rsi=15.0, ema_fast=2480.0, ema_slow=2510.0,
        supertrend_trend="red", vwap=price + 5, atr=12.0,
    )


def _provider_for(snapshots: dict) -> "TechnicalProvider":
    def _p(symbol: str):
        return snapshots.get(symbol)
    return _p


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Cached research refreshes once per (symbol, asof)
# ═══════════════════════════════════════════════════════════════════════════════
def test_research_provider_called_once_per_symbol_per_day(tmp_db):
    p = _CountingProvider()
    asof = date(2026, 5, 25)
    s1 = get_or_fetch("ADANIENT", asof, p)
    s2 = get_or_fetch("ADANIENT", asof, p)
    s3 = get_or_fetch("ADANIENT", asof, p)
    assert p.calls == 1
    assert s1.id == s2.id == s3.id


def test_research_provider_called_again_on_next_day(tmp_db):
    p = _CountingProvider()
    get_or_fetch("ADANIENT", date(2026, 5, 25), p)
    get_or_fetch("ADANIENT", date(2026, 5, 26), p)
    assert p.calls == 2


def test_research_provider_called_per_symbol(tmp_db):
    p = _CountingProvider()
    get_or_fetch("ADANIENT",   date(2026, 5, 25), p)
    get_or_fetch("TATAMOTORS", date(2026, 5, 25), p)
    assert p.calls == 2


def test_research_snapshot_persisted(tmp_db):
    p = _CountingProvider({"provider": "x", "fundamentals_raw": 0.8,
                            "sentiment_raw": 0.6, "liquidity_raw": 0.7})
    snap = get_or_fetch("ADANIENT", date(2026, 5, 25), p)
    assert snap.fundamentals_score == pytest.approx(0.8)
    assert snap.sentiment_score    == pytest.approx(0.6)
    assert snap.liquidity_score    == pytest.approx(0.7)
    # Persisted in DB
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM research_snapshots "
            "WHERE symbol='ADANIENT' AND asof='2026-05-25'"
        ).fetchone()
    assert row["n"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Signal engine is deterministic + pure
# ═══════════════════════════════════════════════════════════════════════════════
def test_technical_score_deterministic():
    s = _bullish_tech()
    assert compute_technical_score(s) == compute_technical_score(s)
    assert compute_technical_score(s) == compute_technical_score(s)


def test_technical_score_neutral_when_no_signals():
    s = TechnicalSnapshot(price=100.0)
    assert compute_technical_score(s) == 0.5


def test_technical_score_bullish_higher_than_bearish():
    assert compute_technical_score(_bullish_tech()) \
         > compute_technical_score(_bearish_tech())


def test_risk_score_lower_with_higher_atr():
    high_vol = compute_risk_score(price=100, atr=4.0)   # 4%
    low_vol  = compute_risk_score(price=100, atr=0.5)   # 0.5%
    assert low_vol > high_vol


def test_risk_score_clipped_to_unit_interval():
    assert 0.0 <= compute_risk_score(100, 100.0) <= 1.0
    assert 0.0 <= compute_risk_score(100, 0.0)   <= 1.0
    assert compute_risk_score(100, None) == 0.5


def test_total_score_weights_sum_correctly():
    t = compute_total_score(technical=1.0, sentiment=1.0,
                            fundamentals=1.0, liquidity=1.0, risk=1.0)
    assert t == 1.0
    t0 = compute_total_score(technical=0.0, sentiment=0.0,
                             fundamentals=0.0, liquidity=0.0, risk=0.0)
    assert t0 == 0.0


def test_classify_signal_no_position_bullish_yields_buy_candidate():
    assert classify_signal(total_score=BUY_THRESHOLD,
                           has_position=False, entry_blocked=False) \
        == Signal.BUY_CANDIDATE


def test_classify_signal_no_position_weak_yields_hold():
    assert classify_signal(total_score=BUY_THRESHOLD - 0.01,
                           has_position=False, entry_blocked=False) \
        == Signal.HOLD


def test_classify_signal_entry_blocked_yields_rejected():
    assert classify_signal(total_score=0.9,
                           has_position=False, entry_blocked=True) \
        == Signal.REJECTED


def test_classify_signal_holder_with_weak_yields_sell_candidate():
    assert classify_signal(total_score=SELL_THRESHOLD,
                           has_position=True, entry_blocked=False) \
        == Signal.SELL_CANDIDATE


def test_classify_signal_holder_with_strong_yields_hold():
    assert classify_signal(total_score=0.9,
                           has_position=True, entry_blocked=False) \
        == Signal.HOLD


# ═══════════════════════════════════════════════════════════════════════════════
# 3. No LLM/API call in intraday scan path (cache short-circuits provider)
# ═══════════════════════════════════════════════════════════════════════════════
def test_scan_does_not_call_provider_on_warm_cache(
    tmp_db, tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg
):
    """
    Warm the cache for today using a permissive provider, then run scan_once
    with an ExplodingProvider — if the scanner tries to fetch, the test fails.
    """
    today = date.today()
    # Warm
    for sym in ("ADANIENT", "TATAMOTORS"):
        get_or_fetch(sym, today, _CountingProvider())
    # Scan with exploding provider — must NOT call .fetch
    snaps = {"ADANIENT": _bullish_tech(), "TATAMOTORS": _bearish_tech(2500.0)}
    candidates = scan_once(
        portfolio=fresh_pf, watchlist=list(snaps.keys()),
        technical_provider=_provider_for(snaps),
        research_provider=_ExplodingProvider(),
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        day_start_equity=200_000.0, asof=today,
    )
    assert len(candidates) == 2


def test_scan_counts_one_fetch_per_symbol_then_warms(
    tmp_db, tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg
):
    """First scan fetches; second scan same day must NOT re-fetch."""
    today = date.today()
    snaps = {"ADANIENT": _bullish_tech()}
    counting = _CountingProvider()
    scan_once(
        portfolio=fresh_pf, watchlist=["ADANIENT"],
        technical_provider=_provider_for(snaps),
        research_provider=counting,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        day_start_equity=200_000.0, asof=today,
    )
    assert counting.calls == 1
    scan_once(
        portfolio=fresh_pf, watchlist=["ADANIENT"],
        technical_provider=_provider_for(snaps),
        research_provider=counting,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        day_start_equity=200_000.0, asof=today,
    )
    assert counting.calls == 1   # still 1 — cache hit, no re-fetch


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Signal logs include all required fields
# ═══════════════════════════════════════════════════════════════════════════════
REQUIRED_LOG_COLUMNS = {
    "ts", "symbol", "signal", "total_score",
    "technical_score", "sentiment_score", "fundamentals_score",
    "liquidity_score", "risk_score",
    "indicators", "research_snapshot_id",
    "entry_blocked", "block_reasons", "sizing_preview", "rejection_reason",
}


def test_signal_log_row_contains_all_required_fields(
    tmp_db, tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg
):
    snaps = {"ADANIENT": _bullish_tech()}
    scan_once(
        portfolio=fresh_pf, watchlist=["ADANIENT"],
        technical_provider=_provider_for(snaps),
        research_provider=_CountingProvider(),
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        day_start_equity=200_000.0,
    )
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM signal_candidates ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    cols = set(dict(row).keys())
    missing = REQUIRED_LOG_COLUMNS - cols
    assert not missing, f"missing log columns: {missing}"
    # Indicator + sizing preview JSON parseable
    indicators = json.loads(row["indicators"])
    assert "price" in indicators
    sizing = json.loads(row["sizing_preview"])
    assert "qty" in sizing and "stop_distance" in sizing


def test_candidate_in_memory_carries_research_snapshot_id(
    tmp_db, tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg
):
    snaps = {"ADANIENT": _bullish_tech()}
    cands = scan_once(
        portfolio=fresh_pf, watchlist=["ADANIENT"],
        technical_provider=_provider_for(snaps),
        research_provider=_CountingProvider(),
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        day_start_equity=200_000.0,
    )
    assert len(cands) == 1
    assert cands[0].research_snapshot_id is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Paused/killed state marks candidate as blocked
# ═══════════════════════════════════════════════════════════════════════════════
def test_paused_state_marks_candidate_blocked_and_rejected(
    tmp_db, tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg
):
    control.pause("test pause")
    snaps = {"ADANIENT": _bullish_tech()}
    cands = scan_once(
        portfolio=fresh_pf, watchlist=["ADANIENT"],
        technical_provider=_provider_for(snaps),
        research_provider=_CountingProvider(),
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        day_start_equity=200_000.0,
    )
    c = cands[0]
    assert c.entry_blocked is True
    assert any("paused" in r.lower() for r in c.block_reasons)
    # Strong bullish score that would normally yield BUY_CANDIDATE
    # must downgrade to REJECTED because entry is blocked.
    assert c.signal == Signal.REJECTED
    assert c.rejection_reason == "entry_blocked"


def test_killed_state_marks_candidate_blocked_and_rejected(
    tmp_db, tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg
):
    control.kill("test kill")
    snaps = {"ADANIENT": _bullish_tech()}
    cands = scan_once(
        portfolio=fresh_pf, watchlist=["ADANIENT"],
        technical_provider=_provider_for(snaps),
        research_provider=_CountingProvider(),
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        day_start_equity=200_000.0,
    )
    c = cands[0]
    assert c.entry_blocked is True
    assert any("killed" in r.lower() for r in c.block_reasons)
    assert c.signal == Signal.REJECTED


# ═══════════════════════════════════════════════════════════════════════════════
# 6. No BUY is executed in Phase H.1
# ═══════════════════════════════════════════════════════════════════════════════
def test_scan_never_mutates_portfolio_positions(
    tmp_db, tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg
):
    cash_before = fresh_pf.state.cash
    positions_before = dict(fresh_pf.state.positions)
    snaps = {"ADANIENT": _bullish_tech(), "TATAMOTORS": _bullish_tech(price=800.0)}
    cands = scan_once(
        portfolio=fresh_pf, watchlist=list(snaps.keys()),
        technical_provider=_provider_for(snaps),
        research_provider=_CountingProvider(),
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        day_start_equity=200_000.0,
    )
    # At least one BUY_CANDIDATE generated...
    assert any(c.signal == Signal.BUY_CANDIDATE for c in cands)
    # ...but portfolio is unchanged.
    assert fresh_pf.state.cash == cash_before
    assert fresh_pf.state.positions == positions_before
    assert fresh_pf.state.total_trades == 0


def test_scan_never_writes_to_trades_table(
    tmp_db, tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg
):
    snaps = {"ADANIENT": _bullish_tech()}
    scan_once(
        portfolio=fresh_pf, watchlist=["ADANIENT"],
        technical_provider=_provider_for(snaps),
        research_provider=_CountingProvider(),
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        day_start_equity=200_000.0,
    )
    with get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"]
    assert n == 0


# ═══════════════════════════════════════════════════════════════════════════════
# scoring of source_data is pure
# ═══════════════════════════════════════════════════════════════════════════════
def test_score_source_data_handles_missing_keys():
    f, s, l = score_source_data({})
    assert f == s == l == 0.5


def test_score_source_data_clips_out_of_range():
    f, s, l = score_source_data({
        "fundamentals_raw": 1.5,
        "sentiment_raw":   -0.5,
        "liquidity_raw":    0.3,
    })
    assert f == 1.0
    assert s == 0.0
    assert l == 0.3


def test_score_source_data_accepts_dict_with_score_key():
    f, _, _ = score_source_data({"fundamentals_raw": {"score": 0.42, "notes": "ok"}})
    assert f == 0.42


# ═══════════════════════════════════════════════════════════════════════════════
# list_recent_candidates feeds the dashboard
# ═══════════════════════════════════════════════════════════════════════════════
def test_list_recent_candidates_returns_logged_rows(
    tmp_db, tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg
):
    snaps = {"ADANIENT": _bullish_tech()}
    scan_once(
        portfolio=fresh_pf, watchlist=["ADANIENT"],
        technical_provider=_provider_for(snaps),
        research_provider=_CountingProvider(),
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        day_start_equity=200_000.0,
    )
    rows = list_recent_candidates(limit=10)
    assert len(rows) >= 1
    assert rows[0]["symbol"] == "ADANIENT"
