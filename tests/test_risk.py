"""
Risk module tests — volatility sizing, expected-loss validation, cap enforcement.
"""

from datetime import datetime
import pytest

from bot.config import RiskConfig, IndicatorConfig, FeeConfig
from bot.portfolio import Portfolio, Position
from bot.risk import (
    calculate_position_size, check_all_caps,
    SizingResult, CapsCheckResult,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def risk_cfg():
    # 1% per trade, default caps (1 position, 30% per symbol, 100% total)
    return RiskConfig()


@pytest.fixture
def indi_cfg():
    return IndicatorConfig()


@pytest.fixture
def fee_cfg():
    return FeeConfig()


@pytest.fixture
def fresh_pf():
    return Portfolio.fresh(starting_balance=50_000.0)


def _make_position(symbol="ADANIENT", qty=10, entry=2500.0):
    return Position(
        symbol=symbol, qty=qty, entry_price=entry,
        stop=entry * 0.99, target=entry * 1.02,
        charges_buy=15.0, entry_time=datetime.now(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Sizing — volatility scaled
# ═══════════════════════════════════════════════════════════════════════════════
def test_higher_atr_reduces_qty(risk_cfg, indi_cfg, fee_cfg):
    """Higher volatility → wider stop → smaller qty."""
    low_atr  = calculate_position_size(
        equity=50_000, price=1000, atr=5.0,        # ATR 0.5%
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    high_atr = calculate_position_size(
        equity=50_000, price=1000, atr=50.0,       # ATR 5%
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    assert low_atr.qty > high_atr.qty
    assert low_atr.stop_distance < high_atr.stop_distance


def test_min_stop_floor_applies_when_atr_tiny(risk_cfg, indi_cfg, fee_cfg):
    """Tiny ATR should not produce tiny stop_distance — min_stop_pct floor kicks in."""
    result = calculate_position_size(
        equity=50_000, price=1000, atr=0.01,       # 0.001% ATR — ridiculous
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    # min_stop_pct = 0.005 (0.5%) of 1000 = 5.0
    assert result.stop_distance == pytest.approx(5.0, abs=0.01)
    # ATR * 2.0 = 0.02 is ignored in favour of the floor


def test_higher_risk_pct_increases_qty(indi_cfg, fee_cfg):
    """Higher risk_per_trade_pct allows larger qty (subject to caps)."""
    risk_1pct = RiskConfig(risk_per_trade_pct=1.0)
    risk_3pct = RiskConfig(risk_per_trade_pct=3.0)
    r1 = calculate_position_size(equity=200_000, price=100, atr=2.0,
                                 risk_cfg=risk_1pct, indi_cfg=indi_cfg, fee_cfg=fee_cfg)
    r3 = calculate_position_size(equity=200_000, price=100, atr=2.0,
                                 risk_cfg=risk_3pct, indi_cfg=indi_cfg, fee_cfg=fee_cfg)
    assert r3.qty > r1.qty


# ═══════════════════════════════════════════════════════════════════════════════
# Sizing — symbol cap
# ═══════════════════════════════════════════════════════════════════════════════
def test_symbol_cap_limits_qty(risk_cfg, indi_cfg, fee_cfg):
    """
    With 30% symbol cap and Rs.50k equity → Rs.15k per symbol.
    @ price 1000 → max 15 shares — even if risk_amount would allow more.
    """
    result = calculate_position_size(
        equity=50_000, price=1000, atr=2.0,        # very tight stop → high qty_by_risk
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    assert result.qty <= 15
    assert result.metrics["qty_by_symbol"] == 15


def test_symbol_cap_exhausted_rejects(risk_cfg, indi_cfg, fee_cfg):
    """If existing exposure already at symbol cap, sizing rejects."""
    result = calculate_position_size(
        equity=50_000, price=1000, atr=5.0,
        current_symbol_exposure=15_000,            # already at 30% cap
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    assert result.rejected
    assert any("symbol" in r.lower() for r in result.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# Sizing — total exposure cap
# ═══════════════════════════════════════════════════════════════════════════════
def test_total_exposure_cap_limits_qty(indi_cfg, fee_cfg):
    """
    With max_total_exposure_pct=20 (custom) and equity 50k → 10k total cap.
    @ price 1000 → max 10 shares regardless of symbol cap.
    """
    risk_cfg = RiskConfig(max_total_exposure_pct=20.0, max_symbol_notional_pct=100.0)
    result = calculate_position_size(
        equity=50_000, price=1000, atr=2.0,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    assert result.qty <= 10
    assert result.metrics["qty_by_total"] == 10


def test_total_exposure_cap_exhausted_rejects(indi_cfg, fee_cfg):
    risk_cfg = RiskConfig(max_total_exposure_pct=20.0, max_symbol_notional_pct=100.0)
    result = calculate_position_size(
        equity=50_000, price=1000, atr=2.0,
        current_total_exposure=10_000,             # already at cap
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    assert result.rejected
    assert any("total" in r.lower() for r in result.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# Sizing — expected-loss validation incl. fees + slippage
# ═══════════════════════════════════════════════════════════════════════════════
def test_expected_loss_includes_charges_and_slippage(risk_cfg, indi_cfg, fee_cfg):
    """Reported expected_loss must exceed pure stop-distance loss (qty * stop)."""
    r = calculate_position_size(
        equity=100_000, price=500, atr=5.0,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    pure_stop_loss = r.qty * r.stop_distance
    assert r.expected_loss > pure_stop_loss
    assert r.expected_loss <= r.risk_amount    # never exceed budget


def test_high_slippage_reduces_qty(risk_cfg, indi_cfg):
    """Increasing slippage_bps should reduce final qty."""
    low_slip  = FeeConfig(intraday_slippage_bps=0.0)
    high_slip = FeeConfig(intraday_slippage_bps=50.0)   # 0.5% per side
    r_low  = calculate_position_size(equity=50_000, price=2500, atr=15.0,
                                     risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=low_slip)
    r_high = calculate_position_size(equity=50_000, price=2500, atr=15.0,
                                     risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=high_slip)
    assert r_high.qty <= r_low.qty


def test_costs_exceeding_risk_amount_rejects(indi_cfg):
    """
    Sized qty's expected loss (stop + charges + slippage) exceeds risk_amount
    even at qty=1 → reject with 'expected loss' reason.

    Setup tuned so qty_by_risk == 1 initially, but high slippage pushes
    expected_loss above risk_amount.
        risk_amount    = 30000 * 0.1% = 30
        stop_distance  = max(14 * 2.0, 0.005 * 1000) = 28
        qty_by_risk    = floor(30/28) = 1
        rt_slippage(1) = 2 * 1000 * 0.01 * 1 = 20
        rt_charges(1)  ≈ 1.0
        expected_loss  ≈ 49  >> risk_amount 30  → reject
    """
    tight_risk = RiskConfig(risk_per_trade_pct=0.1)
    high_slip  = FeeConfig(intraday_slippage_bps=100.0)   # 1% per side
    result = calculate_position_size(
        equity=30_000, price=1000, atr=14.0,
        risk_cfg=tight_risk, indi_cfg=indi_cfg, fee_cfg=high_slip,
    )
    assert result.rejected
    assert any("expected loss" in r.lower() for r in result.reasons), \
        f"Expected 'expected loss' rejection, got reasons: {result.reasons}"


# ═══════════════════════════════════════════════════════════════════════════════
# check_all_caps — fail-closed + structured results
# ═══════════════════════════════════════════════════════════════════════════════
def test_check_all_caps_fresh_portfolio_can_trade(fresh_pf, risk_cfg):
    """Empty portfolio, no positions, no losses → can_trade."""
    result = check_all_caps(fresh_pf, prices={}, day_start_equity=50_000, risk_cfg=risk_cfg)
    assert isinstance(result, CapsCheckResult)
    assert result.can_trade is True
    assert result.reasons == []
    assert "equity" in result.metrics


def test_check_all_caps_fails_closed_on_missing_price(fresh_pf, risk_cfg):
    """If a position exists but no price is supplied → fail closed, no exception."""
    fresh_pf.add_position(_make_position(), cost=25_015)
    result = check_all_caps(fresh_pf, prices={}, day_start_equity=50_000, risk_cfg=risk_cfg)
    assert result.can_trade is False
    assert any("missing market price" in r.lower() for r in result.reasons)


def test_check_all_caps_daily_loss_blocks(fresh_pf):
    """Equity has dropped > max_daily_loss_pct since day-start → blocked."""
    risk_cfg = RiskConfig(max_daily_loss_pct=3.0, max_open_positions=10)
    # Simulate: equity computed from positions+prices is much lower than day start
    # Easiest path: portfolio cash already reduced, no positions, day_start_equity higher
    fresh_pf.state.cash = 48_000   # 4% drop
    result = check_all_caps(fresh_pf, prices={}, day_start_equity=50_000, risk_cfg=risk_cfg)
    assert result.can_trade is False
    assert any("daily loss" in r.lower() for r in result.reasons)
    assert result.metrics["daily_loss_pct"] >= 3.0


def test_check_all_caps_drawdown_blocks(fresh_pf):
    """Drawdown from peak > max_drawdown_pct → blocked."""
    # max_daily_loss_pct must be <=10 per validator; use loose loss cap
    risk_cfg = RiskConfig(max_drawdown_pct=5.0, max_open_positions=10,
                          max_daily_loss_pct=10.0)
    fresh_pf.state.peak_equity = 60_000
    fresh_pf.state.cash        = 50_000     # ~16.7% drawdown
    # day_start_equity = current equity → no daily loss, only drawdown triggers
    result = check_all_caps(fresh_pf, prices={}, day_start_equity=50_000, risk_cfg=risk_cfg)
    assert result.can_trade is False
    assert any("drawdown" in r.lower() for r in result.reasons)


def test_check_all_caps_max_open_positions_blocks(fresh_pf):
    """At max_open_positions, no new entries."""
    risk_cfg = RiskConfig(max_open_positions=1, max_daily_loss_pct=10.0,
                          max_drawdown_pct=25.0)
    fresh_pf.add_position(_make_position(), cost=25_015)
    # day_start = current equity to avoid daily-loss trigger
    eq_at_2500 = fresh_pf.equity({"ADANIENT": 2500.0})
    result = check_all_caps(fresh_pf, prices={"ADANIENT": 2500.0},
                            day_start_equity=eq_at_2500, risk_cfg=risk_cfg)
    assert result.can_trade is False
    assert any("max_open_positions" in r for r in result.reasons)


def test_check_all_caps_multiple_reasons_aggregated(fresh_pf):
    """Multiple failures stack in the same result."""
    risk_cfg = RiskConfig(
        max_open_positions=1, max_daily_loss_pct=1.0, max_drawdown_pct=5.0,
    )
    fresh_pf.add_position(_make_position(), cost=25_015)
    # Force big drop
    fresh_pf.state.cash = 1_000
    fresh_pf.state.peak_equity = 60_000
    result = check_all_caps(fresh_pf, prices={"ADANIENT": 2500.0},
                            day_start_equity=50_000, risk_cfg=risk_cfg)
    assert result.can_trade is False
    # At least daily-loss + max_positions + drawdown should be present
    assert len(result.reasons) >= 2


def test_check_all_caps_metrics_populated(fresh_pf, risk_cfg):
    result = check_all_caps(fresh_pf, prices={},
                            day_start_equity=50_000, risk_cfg=risk_cfg)
    for k in ["equity", "open_positions", "day_start_equity",
              "daily_loss_pct", "drawdown_pct"]:
        assert k in result.metrics
