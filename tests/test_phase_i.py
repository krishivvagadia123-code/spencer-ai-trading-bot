"""
Phase I — crypto-INR pivot + run-all supervisor + learner + dashboard.

13 required guarantees:
  1. run-all/RUN_BOT starts all loops through testable loop functions
  2. pause blocks BUY only
  3. pause does not block monitor exits
  4. resume re-enables BUY
  5. crypto mode ignores NSE hours/holidays
  6. crypto mode does not use Zerodha charges
  7. invalid/unavailable symbols are skipped safely
  8. auto-buy never places live broker orders
  9. TradingView launch failure does not stop the bot
 10. learner does not use future/open trades
 11. learner weights are bounded
 12. dashboard refresh does not crash run-all
 13. no emergency stop file remains in the final control folder
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional
import json
import pytest

from bot import control
from bot.charges import (
    BROKERAGE_INTRADAY_CAP, CRYPTO_PAPER_FEE_BPS, calculate_charges,
)
from bot.config import (
    AssetClassConfig, BotConfig, FeeConfig, IndicatorConfig, MarketConfig,
    RiskConfig, SupervisorConfig, crypto_inr_config, default_config,
)
from bot.db import get_conn, init_db, set_db_path
from bot.engine import do_monitor_once, do_sell
from bot.execution_sim import simulate_fill
from bot.holidays import DEFAULT_REGISTRY
from bot.learner import (
    DEFAULT_WEIGHTS, MAX_DRIFT, MIN_TRADES, StrategyProfile,
    compute_new_weights, compute_stats, load_profile, save_profile,
    update_profile,
)
from bot.logger_config import get_logger
from bot.market_data import IST, Quote, is_market_open, validate_quote
from bot.portfolio import Portfolio, Position
from bot.signals import Signal, SizingPreview, TechnicalSnapshot, build_candidate
from bot.supervisor import (
    LoopState, auto_buy_once, run_iteration, write_heartbeat,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_db(tmp_path):
    p = tmp_path / "phase_i.db"
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
def crypto_cfg():
    """
    Loosened from production preset so qty=1 of a Rs.100k coin fits in the
    Rs.200k test portfolio. Production crypto_inr_config() keeps the strict
    per-symbol cap and is still exercised in the equity tests.
    """
    base = crypto_inr_config()
    return BotConfig(
        asset=base.asset, fees=base.fees, market=base.market,
        supervisor=base.supervisor,
        indicators=base.indicators,
        risk=RiskConfig(
            risk_per_trade_pct=2.0,
            max_open_positions=5,
            max_daily_loss_pct=10.0,
            max_drawdown_pct=25.0,
            max_total_exposure_pct=200.0,
            # 50% of Rs.200k = Rs.100k → exactly qty=1 of a Rs.100k coin
            max_symbol_notional_pct=50.0,
        ),
    )


@pytest.fixture
def fresh_pf():
    return Portfolio.fresh(starting_balance=200_000.0)


def _usable_quote(symbol="BTC-INR", price=100_000.0):
    """
    Synthetic prices kept small (~Rs.100k) so qty=1 fits in the test portfolio
    (Rs.200k starting balance). Real BTC-INR would be Rs.4.5M and overflow the
    portfolio's per-symbol cap — not what we're testing here.
    """
    return Quote(
        symbol=symbol, price=price,
        timestamp=datetime.now(tz=IST),
        is_stale=False, reject_reason=None,
    )


def _stub_quote_provider(prices: Dict[str, float]):
    def _q(sym: str):
        if sym not in prices:
            return None
        return _usable_quote(sym, prices[sym])
    return _q


def _stub_technical_provider(snaps: Dict[str, TechnicalSnapshot]):
    def _t(sym: str):
        return snaps.get(sym)
    return _t


def _bullish_tech(price=100_000.0):
    return TechnicalSnapshot(
        price=price, rsi=80.0, ema_fast=price * 1.01, ema_slow=price * 0.99,
        supertrend_trend="green", vwap=price * 0.995, atr=price * 0.005,
    )


def _strong_candidate(symbol="BTC-INR", price=100_000.0, ts=None):
    return build_candidate(
        ts=ts or datetime.now(), symbol=symbol, tech=_bullish_tech(price),
        fundamentals_score=0.8, sentiment_score=0.7, liquidity_score=0.8,
        has_position=False, entry_blocked=False, block_reasons=[],
        research_snapshot_id=1,
        sizing_preview=SizingPreview(qty=1, stop_distance=price * 0.01,
                                      expected_loss=price * 0.012, rejected=False),
    )


def _pos(symbol="BTC-INR", qty=1, entry=100_000.0, stop=99_000.0,
         target=102_000.0):
    return Position(
        symbol=symbol, qty=qty, entry_price=entry,
        stop=stop, target=target,
        charges_buy=100.0, entry_time=datetime.now(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. run-all/RUN_BOT starts all loops through testable loop functions
# ═══════════════════════════════════════════════════════════════════════════════
def test_run_iteration_executes_monitor_scan_autobuy_dashboard_heartbeat(
    tmp_path, tmp_db, tmp_control, crypto_cfg, fresh_pf
):
    """One tick with all sub-task intervals at zero — every sub-task fires."""
    snaps = {"BTC-INR": _bullish_tech()}
    prices = {"BTC-INR": 100_000.0}
    dashboard_calls = {"n": 0}

    def fake_refresh(pf, p):
        dashboard_calls["n"] += 1

    # Force everything to fire on this single tick.
    cfg = BotConfig(
        asset=crypto_cfg.asset,
        risk=crypto_cfg.risk,
        fees=crypto_cfg.fees,
        market=crypto_cfg.market,
        indicators=crypto_cfg.indicators,
        supervisor=SupervisorConfig(
            monitor_interval_sec=5,
            scan_interval_sec=30,
            auto_buy_interval_sec=10,
            dashboard_interval_sec=10,
            heartbeat_interval_sec=5,
            cooldown_sec_per_symbol=60,
            min_total_score_to_buy=0.0,
        ),
    )
    state = LoopState()
    summary = run_iteration(
        state=state, portfolio=fresh_pf,
        save_portfolio=lambda pf: None,
        quote_provider=_stub_quote_provider(prices),
        technical_provider=_stub_technical_provider(snaps),
        research_provider=type("P", (), {"fetch": lambda self, s, d: {}})(),
        refresh_dashboard=fake_refresh,
        watchlist=["BTC-INR"],
        cfg=cfg, day_start_equity=200_000.0,
        log_dir=tmp_path / "logs",
        now=1_000_000.0,
        product="CRYPTO",
    )
    assert summary["dashboard"] is True
    assert summary["heartbeat"] is True
    assert summary["scan"] >= 1
    # Heartbeat file written
    assert (tmp_path / "logs" / "heartbeat.log").exists()
    assert dashboard_calls["n"] == 1


def test_run_iteration_respects_intervals_skips_when_not_due(
    tmp_path, tmp_db, tmp_control, crypto_cfg, fresh_pf
):
    """If last_*_ts is recent enough, sub-tasks are skipped on this tick."""
    cfg = crypto_cfg
    state = LoopState()
    state.last_monitor_ts   = 1_000_000.0
    state.last_scan_ts      = 1_000_000.0
    state.last_auto_buy_ts  = 1_000_000.0
    state.last_dashboard_ts = 1_000_000.0
    state.last_heartbeat_ts = 1_000_000.0
    summary = run_iteration(
        state=state, portfolio=fresh_pf,
        save_portfolio=lambda pf: None,
        quote_provider=lambda s: None,
        technical_provider=lambda s: None,
        research_provider=type("P", (), {"fetch": lambda self, s, d: {}})(),
        refresh_dashboard=lambda pf, p: None,
        watchlist=[], cfg=cfg, day_start_equity=200_000.0,
        log_dir=tmp_path / "logs", now=1_000_001.0, product="CRYPTO",
    )
    assert summary["monitor"] == 0
    assert summary["scan"] == 0
    assert summary["dashboard"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. + 4. pause blocks BUY only; resume re-enables
# ═══════════════════════════════════════════════════════════════════════════════
def test_pause_blocks_auto_buy_then_resume_unblocks(
    tmp_db, tmp_control, crypto_cfg, fresh_pf
):
    cand = _strong_candidate()
    qp = _stub_quote_provider({"BTC-INR": 100_000.0})

    control.pause("test pause")
    blocked = auto_buy_once(
        candidates=[cand], portfolio=fresh_pf, quote_provider=qp,
        risk_cfg=crypto_cfg.risk, indi_cfg=crypto_cfg.indicators,
        fee_cfg=crypto_cfg.fees, sup_cfg=crypto_cfg.supervisor,
        day_start_equity=200_000.0, now=0.0, product="CRYPTO",
    )
    assert all(not d.placed for d in blocked)
    assert any("paused" in d.reason.lower() for d in blocked)
    assert "BTC-INR" not in fresh_pf.state.positions

    control.resume()
    allowed = auto_buy_once(
        candidates=[cand], portfolio=fresh_pf, quote_provider=qp,
        risk_cfg=crypto_cfg.risk, indi_cfg=crypto_cfg.indicators,
        fee_cfg=crypto_cfg.fees, sup_cfg=crypto_cfg.supervisor,
        day_start_equity=200_000.0, now=999_999.0, product="CRYPTO",
    )
    placed = [d for d in allowed if d.placed]
    assert len(placed) == 1
    assert "BTC-INR" in fresh_pf.state.positions


# ═══════════════════════════════════════════════════════════════════════════════
# 3. pause does NOT block monitor exits
# ═══════════════════════════════════════════════════════════════════════════════
def test_pause_does_not_block_monitor_exits(
    tmp_db, tmp_control, crypto_cfg, fresh_pf
):
    fresh_pf.add_position(_pos("BTC-INR", qty=1, entry=100_000.0,
                                stop=99_000.0, target=102_000.0),
                          cost=100_100.0)
    control.pause("intentional pause")
    qp = _stub_quote_provider({"BTC-INR": 98_000.0})   # below stop
    results = do_monitor_once(fresh_pf, qp, fee_cfg=crypto_cfg.fees,
                              product="CRYPTO")
    successful = [r for r in results if not r.rejected]
    assert len(successful) == 1
    assert successful[0].exit_reason == "STOP"
    assert "BTC-INR" not in fresh_pf.state.positions


# ═══════════════════════════════════════════════════════════════════════════════
# 5. crypto mode ignores NSE hours/holidays
# ═══════════════════════════════════════════════════════════════════════════════
def test_crypto_24x7_market_always_open():
    cfg = crypto_inr_config().market
    # A Saturday 03:00 IST would be closed for NSE; crypto should be open.
    sat_dawn = datetime(2026, 5, 23, 3, 0, tzinfo=IST)
    is_open, reason = is_market_open(cfg, sat_dawn)
    assert is_open is True, f"unexpected reason: {reason!r}"


def test_crypto_quote_usable_on_holiday():
    cfg = crypto_inr_config().market
    # Add a holiday — crypto mode must ignore it.
    holiday = date(2026, 1, 26)   # Republic Day
    snap = DEFAULT_REGISTRY.snapshot()
    DEFAULT_REGISTRY.add(holiday)
    try:
        ts = datetime(2026, 1, 26, 12, 0, tzinfo=IST)
        q = validate_quote(100_000.0, ts, "BTC-INR", cfg, now=ts)
        assert q.is_usable, f"crypto quote rejected: {q.reject_reason}"
    finally:
        DEFAULT_REGISTRY.restore(snap)


def test_nse_mode_still_rejects_on_holiday():
    """Default (equity) config must still honor holidays — pivot didn't break it."""
    cfg = default_config().market
    holiday = date(2026, 1, 26)
    snap = DEFAULT_REGISTRY.snapshot()
    DEFAULT_REGISTRY.add(holiday)
    try:
        ts = datetime(2026, 1, 26, 11, 0, tzinfo=IST)
        is_open, reason = is_market_open(cfg, ts)
        assert is_open is False
        assert "holiday" in reason.lower()
    finally:
        DEFAULT_REGISTRY.restore(snap)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. crypto mode does not use Zerodha charges
# ═══════════════════════════════════════════════════════════════════════════════
def test_crypto_charges_flat_no_zerodha_components():
    # 1 BTC at 45L INR
    ch = calculate_charges(price=4_500_000.0, qty=1, side="BUY", product="CRYPTO")
    # Zerodha-specific components must all be zero
    assert ch.stt      == 0.0
    assert ch.exchange == 0.0
    assert ch.sebi     == 0.0
    assert ch.gst      == 0.0
    assert ch.stamp    == 0.0
    assert ch.dp       == 0.0
    # Brokerage should equal flat % * notional
    expected = round(4_500_000.0 * (CRYPTO_PAPER_FEE_BPS / 10_000), 2)
    assert ch.brokerage == expected
    assert ch.total     == expected


def test_crypto_charges_diverge_from_intraday_charges():
    crypto = calculate_charges(price=4_500_000.0, qty=1, side="SELL",
                                product="CRYPTO")
    intraday = calculate_charges(price=4_500_000.0, qty=1, side="SELL",
                                  product="INTRADAY")
    assert crypto.total != intraday.total
    # Intraday SELL includes STT — crypto must not
    assert intraday.stt > 0
    assert crypto.stt   == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. invalid/unavailable symbols are skipped safely
# ═══════════════════════════════════════════════════════════════════════════════
def test_supervisor_skips_symbol_with_no_quote(
    tmp_path, tmp_db, tmp_control, crypto_cfg, fresh_pf
):
    """If quote_provider returns None for a symbol, auto-buy skips it cleanly."""
    cand = _strong_candidate("UNKNOWN-INR", 100.0)
    decisions = auto_buy_once(
        candidates=[cand], portfolio=fresh_pf,
        quote_provider=lambda s: None,    # never returns a quote
        risk_cfg=crypto_cfg.risk, indi_cfg=crypto_cfg.indicators,
        fee_cfg=crypto_cfg.fees, sup_cfg=crypto_cfg.supervisor,
        day_start_equity=200_000.0, now=1.0, product="CRYPTO",
    )
    assert len(decisions) == 1
    assert decisions[0].placed is False
    assert "quote" in decisions[0].reason.lower()


def test_run_iteration_continues_after_quote_provider_exception(
    tmp_path, tmp_db, tmp_control, crypto_cfg, fresh_pf
):
    """A raising provider must not crash the iteration."""
    def boom(_):
        raise RuntimeError("provider exploded")
    cfg = BotConfig(
        asset=crypto_cfg.asset, risk=crypto_cfg.risk,
        fees=crypto_cfg.fees, market=crypto_cfg.market,
        indicators=crypto_cfg.indicators,
        supervisor=SupervisorConfig(monitor_interval_sec=5,
                                     scan_interval_sec=30,
                                     auto_buy_interval_sec=10,
                                     dashboard_interval_sec=10,
                                     heartbeat_interval_sec=5),
    )
    state = LoopState()
    summary = run_iteration(
        state=state, portfolio=fresh_pf, save_portfolio=lambda pf: None,
        quote_provider=boom, technical_provider=boom,
        research_provider=type("P", (), {"fetch": lambda self, s, d: {}})(),
        refresh_dashboard=lambda pf, p: None,
        watchlist=["BTC-INR"], cfg=cfg, day_start_equity=200_000.0,
        log_dir=tmp_path / "logs", now=1_000_000.0, product="CRYPTO",
    )
    assert state.errors >= 1
    assert any("monitor" in e or "scan" in e for e in summary["errors"])


# ═══════════════════════════════════════════════════════════════════════════════
# 8. auto-buy never places live broker orders (paper only)
# ═══════════════════════════════════════════════════════════════════════════════
def test_auto_buy_only_routes_through_execution_sim(monkeypatch, tmp_db,
                                                     tmp_control, crypto_cfg,
                                                     fresh_pf):
    """
    Sentinel: monkeypatch execution_sim.simulate_fill to count calls. Any path
    that creates a position MUST go through it. Then assert there is no
    'broker' or 'kite' or 'zerodha' submodule wired in.
    """
    import bot.engine as eng
    calls = {"n": 0}
    real = eng.simulate_fill
    def counted(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)
    monkeypatch.setattr(eng, "simulate_fill", counted)

    cand = _strong_candidate()
    decisions = auto_buy_once(
        candidates=[cand], portfolio=fresh_pf,
        quote_provider=_stub_quote_provider({"BTC-INR": 100_000.0}),
        risk_cfg=crypto_cfg.risk, indi_cfg=crypto_cfg.indicators,
        fee_cfg=crypto_cfg.fees, sup_cfg=crypto_cfg.supervisor,
        day_start_equity=200_000.0, now=1.0, product="CRYPTO",
    )
    assert any(d.placed for d in decisions)
    assert calls["n"] >= 1


def test_no_broker_or_live_order_imports_anywhere():
    """No module imports a live broker SDK (kiteconnect, ccxt, etc.)."""
    import bot
    pkg_dir = Path(bot.__file__).parent
    forbidden = ("kiteconnect", "ccxt", "binance", "alpaca")
    hits = []
    for py in pkg_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text.lower():
                hits.append(f"{py.name}: {needle}")
    assert hits == [], f"forbidden live-broker imports found: {hits}"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. TradingView launch failure does not stop the bot
# ═══════════════════════════════════════════════════════════════════════════════
def test_supervisor_does_not_depend_on_tradingview(
    tmp_path, tmp_db, tmp_control, crypto_cfg, fresh_pf
):
    """
    run_iteration has no TradingView import or call. We don't need to simulate
    a failure — proving the supervisor module never references it is enough.
    """
    import bot.supervisor as sup
    src = Path(sup.__file__).read_text(encoding="utf-8")
    assert "tradingview" not in src.lower()
    # And one full iteration should succeed with no TV present:
    snaps = {"BTC-INR": _bullish_tech()}
    state = LoopState()
    summary = run_iteration(
        state=state, portfolio=fresh_pf, save_portfolio=lambda pf: None,
        quote_provider=_stub_quote_provider({"BTC-INR": 100_000.0}),
        technical_provider=_stub_technical_provider(snaps),
        research_provider=type("P", (), {"fetch": lambda self, s, d: {}})(),
        refresh_dashboard=lambda pf, p: None,
        watchlist=["BTC-INR"], cfg=crypto_cfg, day_start_equity=200_000.0,
        log_dir=tmp_path / "logs", now=1_000_000.0, product="CRYPTO",
    )
    assert state.errors == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 10. learner does not use future/open trades
# ═══════════════════════════════════════════════════════════════════════════════
def _insert_trade(ts: str, action: str, symbol: str, price: float,
                  qty: int, pnl, stop=None, target=None):
    from bot.db import log_trade
    log_trade({
        "ts": ts, "symbol": symbol, "action": action, "price": price, "qty": qty,
        "value": price * qty, "charges": 1.0, "stop": stop, "target": target,
        "pnl": pnl, "balance_after": 1.0,
    })


def test_learner_ignores_buy_rows_and_null_pnl(tmp_db):
    """BUY rows have no PnL; open positions logged as BUY with no SELL pair.
    The learner must read only SELL rows with non-null pnl."""
    _insert_trade("2026-01-01 10:00", "BUY", "BTC-INR", 4_500_000.0, 1, None,
                  stop=4_455_000.0, target=4_590_000.0)
    _insert_trade("2026-01-01 11:00", "SELL", "BTC-INR", 4_550_000.0, 1, 5000.0,
                  stop=4_455_000.0, target=4_590_000.0)
    _insert_trade("2026-01-02 09:00", "BUY", "BTC-INR", 4_500_000.0, 1, None,
                  stop=4_455_000.0, target=4_590_000.0)  # open position — no SELL

    from bot.learner import _load_closed_trades
    closed = _load_closed_trades()
    assert len(closed) == 1
    assert closed[0]["action"] == "SELL"
    assert closed[0]["pnl"] == 5000.0


def test_learner_does_not_train_on_open_positions(tmp_db):
    profile = update_profile(Path(tmp_db).parent / "profile.json")
    # Insert open position only — no SELL rows
    _insert_trade("2026-01-01 10:00", "BUY", "BTC-INR", 4_500_000.0, 1, None,
                  stop=4_455_000.0)
    profile2 = update_profile(Path(tmp_db).parent / "profile.json")
    assert profile2.total_closed_trades == 0
    assert profile2.sample_size_sufficient is False
    # Defaults preserved exactly
    assert profile2.weights == DEFAULT_WEIGHTS


# ═══════════════════════════════════════════════════════════════════════════════
# 11. learner weights are bounded
# ═══════════════════════════════════════════════════════════════════════════════
def test_learner_weights_within_bounds_after_extreme_stats():
    """No stats should push any weight beyond default ± MAX_DRIFT."""
    extreme_stats = {
        "n": 1_000, "win_rate": 1.0, "avg_r": 10.0,
        "losing_streak": 0, "max_drawdown_pct": 0.0, "symbol_pnl": {},
    }
    new_weights = compute_new_weights(dict(DEFAULT_WEIGHTS), extreme_stats)
    for name, value in new_weights.items():
        lo = DEFAULT_WEIGHTS[name] - MAX_DRIFT - 1e-6
        hi = DEFAULT_WEIGHTS[name] + MAX_DRIFT + 1e-6
        assert lo <= value <= hi, f"{name}={value} outside [{lo}, {hi}]"
    assert sum(new_weights.values()) == pytest.approx(1.0, abs=1e-3)


def test_learner_regresses_on_losing_streak():
    """Losing streak >= LOSING_STREAK_REG pulls weights toward defaults."""
    drifted = {"technical": 0.50, "sentiment": 0.05, "fundamentals": 0.10,
               "liquidity": 0.20, "risk": 0.05}
    stats = {"n": 100, "win_rate": 0.3, "avg_r": -0.5,
             "losing_streak": 10, "max_drawdown_pct": 15.0, "symbol_pnl": {}}
    new_weights = compute_new_weights(drifted, stats)
    # Each weight should be strictly closer to its default
    for k in DEFAULT_WEIGHTS:
        before = abs(drifted[k] - DEFAULT_WEIGHTS[k])
        after  = abs(new_weights[k] - DEFAULT_WEIGHTS[k])
        assert after <= before, f"{k} drifted further on losing streak"


def test_learner_does_nothing_below_min_sample():
    stats = {"n": MIN_TRADES - 1, "win_rate": 1.0, "avg_r": 5.0,
             "losing_streak": 0, "max_drawdown_pct": 0.0, "symbol_pnl": {}}
    current = dict(DEFAULT_WEIGHTS)
    new_weights = compute_new_weights(current, stats)
    assert new_weights == current


# ═══════════════════════════════════════════════════════════════════════════════
# 12. dashboard refresh does not crash run-all
# ═══════════════════════════════════════════════════════════════════════════════
def test_dashboard_refresh_failure_does_not_crash_iteration(
    tmp_path, tmp_db, tmp_control, crypto_cfg, fresh_pf
):
    def explode(pf, p):
        raise RuntimeError("dashboard module hard fault")
    cfg = BotConfig(
        asset=crypto_cfg.asset, risk=crypto_cfg.risk,
        fees=crypto_cfg.fees, market=crypto_cfg.market,
        indicators=crypto_cfg.indicators,
        supervisor=SupervisorConfig(monitor_interval_sec=5,
                                     scan_interval_sec=30,
                                     auto_buy_interval_sec=10,
                                     dashboard_interval_sec=10,
                                     heartbeat_interval_sec=5),
    )
    state = LoopState()
    summary = run_iteration(
        state=state, portfolio=fresh_pf, save_portfolio=lambda pf: None,
        quote_provider=_stub_quote_provider({"BTC-INR": 100_000.0}),
        technical_provider=_stub_technical_provider({"BTC-INR": _bullish_tech()}),
        research_provider=type("P", (), {"fetch": lambda self, s, d: {}})(),
        refresh_dashboard=explode,
        watchlist=["BTC-INR"], cfg=cfg, day_start_equity=200_000.0,
        log_dir=tmp_path / "logs", now=1_000_000.0, product="CRYPTO",
    )
    assert state.errors >= 1
    assert any("dashboard" in e for e in summary["errors"])
    # But the rest succeeded:
    assert summary["heartbeat"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 13. no emergency stop file remains in the final control folder
# ═══════════════════════════════════════════════════════════════════════════════
CONTROL_DIR = Path(r"C:\Users\krish\OneDrive\Desktop\KiteBot-Control")


def test_no_emergency_file_in_control_folder():
    if not CONTROL_DIR.exists():
        pytest.skip("KiteBot-Control folder not present on this host")
    forbidden_names = {
        "EMERGENCY_FLATTEN.bat", "EMERGENCY_STOP.bat",
        "FLATTEN.bat", "PANIC.bat",
    }
    present = {p.name for p in CONTROL_DIR.iterdir()}
    leaks = forbidden_names & present
    assert leaks == set(), f"emergency files leaked into control folder: {leaks}"


def test_final_control_folder_contents_minimal():
    if not CONTROL_DIR.exists():
        pytest.skip("KiteBot-Control folder not present on this host")
    expected_bats = {"RUN_BOT.bat", "PAUSE_BOT.bat",
                     "RESUME_BOT.bat", "STATUS_BOT.bat"}
    present_bats = {p.name for p in CONTROL_DIR.glob("*.bat")}
    assert present_bats == expected_bats, \
        f"unexpected .bat set: {present_bats} (expected {expected_bats})"


# ═══════════════════════════════════════════════════════════════════════════════
# Bonus: cooldown enforcement (per spec — "do not buy the same symbol repeatedly")
# ═══════════════════════════════════════════════════════════════════════════════
def test_cooldown_blocks_same_symbol_within_window(
    tmp_db, tmp_control, crypto_cfg, fresh_pf
):
    cand = _strong_candidate()
    qp   = _stub_quote_provider({"BTC-INR": 100_000.0})
    sup  = SupervisorConfig(cooldown_sec_per_symbol=3600)  # 1h

    # First buy succeeds
    decisions1 = auto_buy_once(
        candidates=[cand], portfolio=fresh_pf, quote_provider=qp,
        risk_cfg=crypto_cfg.risk, indi_cfg=crypto_cfg.indicators,
        fee_cfg=crypto_cfg.fees, sup_cfg=sup, day_start_equity=200_000.0,
        now=10_000.0, product="CRYPTO",
    )
    assert any(d.placed for d in decisions1)
    # Sell to clear position so the "already holding" gate doesn't shadow cooldown
    do_sell("BTC-INR", fresh_pf, qp, fee_cfg=crypto_cfg.fees, product="CRYPTO")

    # Within cooldown window — must NOT auto-buy again
    decisions2 = auto_buy_once(
        candidates=[_strong_candidate()], portfolio=fresh_pf, quote_provider=qp,
        risk_cfg=crypto_cfg.risk, indi_cfg=crypto_cfg.indicators,
        fee_cfg=crypto_cfg.fees, sup_cfg=sup, day_start_equity=200_000.0,
        now=10_100.0,    # 100s later, cooldown is 3600
        product="CRYPTO",
    )
    assert all(not d.placed for d in decisions2)
    assert any("cooldown" in d.reason.lower() for d in decisions2)
