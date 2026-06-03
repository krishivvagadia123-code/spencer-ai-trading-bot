"""
Phase E — engine integration tests.

End-to-end coverage of the invariant from Phase D, now at the engine layer:
  BUY is gated by caps + kill + pause.
  SELL / FLATTEN / MONITOR-driven STOP/TARGET exits are NEVER gated.

Tests inject a synthetic quote_provider so no yfinance / market-hours dependency.
"""

from datetime import datetime, timedelta
from typing import Callable, Dict, Optional
import pytest

from bot import control
from bot.config import RiskConfig, IndicatorConfig, FeeConfig
from bot.engine import (
    BuyResult, SellResult,
    do_buy, do_sell, do_flatten, do_monitor_once,
    serialize_portfolio, deserialize_portfolio,
)
from bot.market_data import IST, Quote
from bot.portfolio import Portfolio, Position


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_control(tmp_path):
    p = tmp_path / "control.json"
    control.set_control_path(p)
    yield p
    control.set_control_path(control.DEFAULT_CONTROL_PATH)


@pytest.fixture
def risk_cfg():
    # Loose caps so BUY can succeed when nothing else is blocking
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


def make_quote_provider(prices: Dict[str, float]) -> Callable[[str], Optional[Quote]]:
    """Synthetic provider: returns a fresh, usable Quote at the given price."""
    def _provider(symbol: str) -> Optional[Quote]:
        if symbol not in prices:
            return None
        return Quote(
            symbol=symbol, price=prices[symbol],
            timestamp=datetime.now(tz=IST),
            is_stale=False, reject_reason=None,
        )
    return _provider


def _pos(symbol="ADANIENT", qty=10, entry=2500.0, stop=2475.0, target=2550.0):
    return Position(
        symbol=symbol, qty=qty, entry_price=entry,
        stop=stop, target=target,
        charges_buy=15.0, entry_time=datetime.now(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BUY path — gated by control + caps
# ═══════════════════════════════════════════════════════════════════════════════
def test_buy_succeeds_when_unblocked(tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg):
    qp = make_quote_provider({"ADANIENT": 2500.0})
    r = do_buy(
        "ADANIENT", fresh_pf, qp,
        day_start_equity=200_000.0,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        atr=15.0,
    )
    assert not r.rejected, r.reasons
    assert r.fill is not None and r.fill.is_executed
    assert "ADANIENT" in fresh_pf.state.positions
    assert fresh_pf.state.cash < 200_000.0


def test_buy_blocked_by_kill(tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg):
    control.kill("manual safety stop")
    qp = make_quote_provider({"ADANIENT": 2500.0})
    r = do_buy(
        "ADANIENT", fresh_pf, qp,
        day_start_equity=200_000.0,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        atr=15.0,
    )
    assert r.rejected
    assert any("killed" in reason.lower() for reason in r.reasons)
    assert "ADANIENT" not in fresh_pf.state.positions
    # Nothing was filled
    assert r.fill is None


def test_buy_blocked_by_pause(tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg):
    control.pause("eod")
    qp = make_quote_provider({"ADANIENT": 2500.0})
    r = do_buy(
        "ADANIENT", fresh_pf, qp,
        day_start_equity=200_000.0,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        atr=15.0,
    )
    assert r.rejected
    assert any("paused" in reason.lower() for reason in r.reasons)
    assert "ADANIENT" not in fresh_pf.state.positions


def test_buy_blocked_by_caps(tmp_control, fresh_pf, indi_cfg, fee_cfg):
    """Tight max_open_positions: existing pos → new BUY rejected."""
    tight = RiskConfig(max_open_positions=1, max_daily_loss_pct=10.0,
                       max_drawdown_pct=25.0)
    fresh_pf.add_position(_pos("VEDL", qty=5, entry=400.0,
                                stop=395.0, target=410.0), cost=2_015)
    qp = make_quote_provider({"ADANIENT": 2500.0, "VEDL": 400.0})
    r = do_buy(
        "ADANIENT", fresh_pf, qp,
        day_start_equity=fresh_pf.equity({"VEDL": 400.0}),
        risk_cfg=tight, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        atr=15.0,
    )
    assert r.rejected
    assert any("max_open_positions" in reason for reason in r.reasons)


def test_buy_rejects_already_held(tmp_control, fresh_pf, risk_cfg, indi_cfg, fee_cfg):
    fresh_pf.add_position(_pos("ADANIENT"), cost=25_015)
    qp = make_quote_provider({"ADANIENT": 2500.0})
    r = do_buy("ADANIENT", fresh_pf, qp,
               day_start_equity=200_000.0,
               risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg, atr=15.0)
    assert r.rejected
    assert any("already holding" in reason.lower() for reason in r.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# SELL path — NEVER gated. Kill, pause, caps all irrelevant.
# ═══════════════════════════════════════════════════════════════════════════════
def test_sell_succeeds_when_killed(tmp_control, fresh_pf, fee_cfg):
    fresh_pf.add_position(_pos("ADANIENT", qty=10, entry=2500.0), cost=25_015)
    control.kill("circuit breaker")
    qp = make_quote_provider({"ADANIENT": 2550.0})
    r = do_sell("ADANIENT", fresh_pf, qp, fee_cfg=fee_cfg, exit_reason="MANUAL")
    assert not r.rejected, r.reasons
    assert "ADANIENT" not in fresh_pf.state.positions
    assert r.exit_reason == "MANUAL"


def test_sell_succeeds_when_paused(tmp_control, fresh_pf, fee_cfg):
    fresh_pf.add_position(_pos("ADANIENT"), cost=25_015)
    control.pause("manual halt")
    qp = make_quote_provider({"ADANIENT": 2550.0})
    r = do_sell("ADANIENT", fresh_pf, qp, fee_cfg=fee_cfg)
    assert not r.rejected
    assert "ADANIENT" not in fresh_pf.state.positions


def test_sell_succeeds_when_caps_would_block_entry(tmp_control, fresh_pf, fee_cfg):
    """Even with hypothetical impossible caps, exits must clear."""
    fresh_pf.add_position(_pos("ADANIENT"), cost=25_015)
    # No mention of caps in do_sell signature — proves the path doesn't consult them
    qp = make_quote_provider({"ADANIENT": 2400.0})  # a loss
    r = do_sell("ADANIENT", fresh_pf, qp, fee_cfg=fee_cfg)
    assert not r.rejected


def test_sell_with_no_position_rejects(tmp_control, fresh_pf, fee_cfg):
    qp = make_quote_provider({"ADANIENT": 2500.0})
    r = do_sell("ADANIENT", fresh_pf, qp, fee_cfg=fee_cfg)
    assert r.rejected
    assert any("no position" in reason.lower() for reason in r.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# FLATTEN — emergency liquidation, ungated
# ═══════════════════════════════════════════════════════════════════════════════
def test_flatten_clears_everything_when_killed(tmp_control, fresh_pf, fee_cfg):
    fresh_pf.add_position(_pos("ADANIENT", qty=5, entry=2500.0,
                                stop=2475.0, target=2550.0), cost=12_515)
    fresh_pf.state.positions["TATAMOTORS"] = _pos(
        "TATAMOTORS", qty=10, entry=800.0, stop=790.0, target=820.0,
    )
    control.kill("flash crash")
    qp = make_quote_provider({"ADANIENT": 2490.0, "TATAMOTORS": 805.0})
    results = do_flatten(fresh_pf, qp, fee_cfg=fee_cfg)
    assert len(results) == 2
    assert all(not r.rejected for r in results), [r.reasons for r in results]
    assert all(r.exit_reason == "FLATTEN" for r in results)
    assert fresh_pf.state.positions == {}


def test_flatten_handles_missing_quote_per_symbol(tmp_control, fresh_pf, fee_cfg):
    fresh_pf.add_position(_pos("ADANIENT", qty=5, entry=2500.0), cost=12_515)
    fresh_pf.state.positions["TATAMOTORS"] = _pos(
        "TATAMOTORS", qty=10, entry=800.0, stop=790.0, target=820.0,
    )
    # Quote only for one symbol
    qp = make_quote_provider({"ADANIENT": 2490.0})
    results = do_flatten(fresh_pf, qp, fee_cfg=fee_cfg)
    by_symbol = {(r.fill.symbol if r.fill else "?"): r for r in results}
    # ADANIENT cleared, TATAMOTORS still open and reported rejected
    assert "ADANIENT" not in fresh_pf.state.positions
    assert "TATAMOTORS" in fresh_pf.state.positions
    rejected = [r for r in results if r.rejected]
    assert len(rejected) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# MONITOR-ONCE — scheduler-safe automatic stop/target exits
# ═══════════════════════════════════════════════════════════════════════════════
def test_monitor_once_no_positions_returns_empty(tmp_control, fresh_pf, fee_cfg):
    qp = make_quote_provider({})
    assert do_monitor_once(fresh_pf, qp, fee_cfg=fee_cfg) == []


def test_monitor_once_inside_band_no_exits(tmp_control, fresh_pf, fee_cfg):
    fresh_pf.add_position(_pos("ADANIENT", stop=2475.0, target=2550.0), cost=25_015)
    qp = make_quote_provider({"ADANIENT": 2510.0})
    results = do_monitor_once(fresh_pf, qp, fee_cfg=fee_cfg)
    assert results == []
    assert "ADANIENT" in fresh_pf.state.positions


def test_monitor_once_executes_stop_exit(tmp_control, fresh_pf, fee_cfg):
    fresh_pf.add_position(_pos("ADANIENT", qty=10, entry=2500.0,
                                stop=2475.0, target=2550.0), cost=25_015)
    qp = make_quote_provider({"ADANIENT": 2400.0})   # below stop
    results = do_monitor_once(fresh_pf, qp, fee_cfg=fee_cfg)
    assert len(results) == 1
    r = results[0]
    assert not r.rejected, r.reasons
    assert r.exit_reason == "STOP"
    assert "ADANIENT" not in fresh_pf.state.positions
    # Net P&L recorded (will be negative — stop hit)
    assert r.net_pnl <= 0


def test_monitor_once_executes_target_exit(tmp_control, fresh_pf, fee_cfg):
    fresh_pf.add_position(_pos("ADANIENT", qty=10, entry=2500.0,
                                stop=2475.0, target=2550.0), cost=25_015)
    qp = make_quote_provider({"ADANIENT": 2600.0})   # above target
    results = do_monitor_once(fresh_pf, qp, fee_cfg=fee_cfg)
    assert len(results) == 1
    r = results[0]
    assert not r.rejected
    assert r.exit_reason == "TARGET"
    assert "ADANIENT" not in fresh_pf.state.positions


def test_monitor_once_fires_even_when_killed(tmp_control, fresh_pf, fee_cfg):
    """Kill switch never suppresses automatic stop exits."""
    fresh_pf.add_position(_pos("ADANIENT", qty=10, entry=2500.0,
                                stop=2475.0, target=2550.0), cost=25_015)
    control.kill("emergency")
    qp = make_quote_provider({"ADANIENT": 2400.0})
    results = do_monitor_once(fresh_pf, qp, fee_cfg=fee_cfg)
    successful = [r for r in results if not r.rejected]
    assert len(successful) == 1
    assert successful[0].exit_reason == "STOP"
    assert "ADANIENT" not in fresh_pf.state.positions


def test_monitor_once_reports_missing_quotes(tmp_control, fresh_pf, fee_cfg):
    fresh_pf.add_position(_pos("ADANIENT"), cost=25_015)
    qp = make_quote_provider({})    # no quote available
    results = do_monitor_once(fresh_pf, qp, fee_cfg=fee_cfg)
    assert len(results) == 1
    assert results[0].rejected
    assert results[0].exit_reason == "MONITOR_MISSING"
    # Position NOT closed — fail loud, never silent
    assert "ADANIENT" in fresh_pf.state.positions


def test_monitor_once_handles_multiple_positions(tmp_control, fresh_pf, fee_cfg):
    fresh_pf.add_position(_pos("ADANIENT", qty=5, entry=2500.0,
                                stop=2475.0, target=2550.0), cost=12_515)
    fresh_pf.state.positions["TATAMOTORS"] = _pos(
        "TATAMOTORS", qty=10, entry=800.0, stop=790.0, target=820.0,
    )
    # ADANIENT inside band; TATAMOTORS above target
    qp = make_quote_provider({"ADANIENT": 2510.0, "TATAMOTORS": 825.0})
    results = do_monitor_once(fresh_pf, qp, fee_cfg=fee_cfg)
    assert len(results) == 1
    assert results[0].exit_reason == "TARGET"
    assert "ADANIENT" in fresh_pf.state.positions
    assert "TATAMOTORS" not in fresh_pf.state.positions


# ═══════════════════════════════════════════════════════════════════════════════
# State persistence round-trip
# ═══════════════════════════════════════════════════════════════════════════════
def test_portfolio_serializes_round_trip(fresh_pf):
    fresh_pf.add_position(_pos("ADANIENT"), cost=25_015)
    raw = serialize_portfolio(fresh_pf)
    restored = deserialize_portfolio(raw)
    assert "ADANIENT" in restored.state.positions
    assert restored.state.cash == fresh_pf.state.cash
    assert restored.state.positions["ADANIENT"].qty == 10
