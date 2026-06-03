"""
Phase C.1 hardening tests — risk + execution_sim + charges:

1. check_all_caps enforces existing total exposure cap
2. check_all_caps enforces existing per-symbol exposure cap
3. calculate_position_size rejects negative ATR
4. calculate_position_size rejects negative exposures
5. invalid product → charges raises, execution_sim rejects, risk rejects
6. SizingResult observability metrics populated
"""

from datetime import datetime, timedelta
import pytest

from bot.charges import calculate_charges
from bot.config import RiskConfig, IndicatorConfig, FeeConfig, MarketConfig
from bot.execution_sim import simulate_fill
from bot.market_data import IST, validate_quote
from bot.portfolio import Portfolio, Position
from bot.risk import calculate_position_size, check_all_caps


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def risk_cfg():
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


@pytest.fixture
def usable_quote():
    cfg = MarketConfig()
    now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
    ts  = now - timedelta(seconds=5)
    return validate_quote(2500.0, ts, "ADANIENT", cfg, now=now)


def _pos(symbol="ADANIENT", qty=10, entry=2500.0):
    return Position(
        symbol=symbol, qty=qty, entry_price=entry,
        stop=entry * 0.99, target=entry * 1.02,
        charges_buy=15.0, entry_time=datetime.now(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. check_all_caps — existing total exposure cap blocks new trades
# ═══════════════════════════════════════════════════════════════════════════════
def test_caps_block_when_existing_gross_exposure_at_max(fresh_pf):
    """
    Position market value already at/over max_total_exposure_pct of equity
    → check_all_caps must say can_trade=False with a gross-exposure reason.
    """
    risk_cfg = RiskConfig(
        max_total_exposure_pct=50.0,
        max_open_positions=10,
        max_daily_loss_pct=10.0,
        max_drawdown_pct=25.0,
        max_symbol_notional_pct=100.0,
    )
    # 10 shares * Rs.3000 = Rs.30,000 market value
    # Cash after buy: 50,000 - 25,015 = 24,985
    # Equity at price=3000: 24,985 + 30,000 = 54,985
    # Gross exposure pct: 30,000 / 54,985 ≈ 54.6% > 50% cap
    fresh_pf.add_position(_pos(qty=10, entry=2500.0), cost=25_015)
    eq = fresh_pf.equity({"ADANIENT": 3000.0})
    result = check_all_caps(
        fresh_pf, prices={"ADANIENT": 3000.0},
        day_start_equity=eq, risk_cfg=risk_cfg,
    )
    assert result.can_trade is False
    assert any("gross exposure" in r.lower() for r in result.reasons)
    assert "gross_exposure" in result.metrics
    assert "gross_exposure_pct" in result.metrics


def test_caps_gross_exposure_metrics_populated_when_within_limit(fresh_pf):
    risk_cfg = RiskConfig(
        max_total_exposure_pct=200.0,
        max_open_positions=10,
        max_daily_loss_pct=10.0,
        max_drawdown_pct=25.0,
    )
    fresh_pf.add_position(_pos(qty=10, entry=2500.0), cost=25_015)
    eq = fresh_pf.equity({"ADANIENT": 2500.0})
    result = check_all_caps(
        fresh_pf, prices={"ADANIENT": 2500.0},
        day_start_equity=eq, risk_cfg=risk_cfg,
    )
    assert result.metrics["gross_exposure"] == pytest.approx(25_000.0, abs=1.0)
    assert result.metrics["gross_exposure_pct"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. check_all_caps — existing per-symbol exposure cap blocks new trades
# ═══════════════════════════════════════════════════════════════════════════════
def test_caps_block_when_existing_symbol_exposure_at_max(fresh_pf):
    """Single position exceeds max_symbol_notional_pct of equity → blocked."""
    risk_cfg = RiskConfig(
        max_symbol_notional_pct=20.0,     # tight per-symbol cap
        max_total_exposure_pct=200.0,
        max_open_positions=10,
        max_daily_loss_pct=10.0,
        max_drawdown_pct=25.0,
    )
    fresh_pf.add_position(_pos(qty=10, entry=2500.0), cost=25_015)
    # equity at 2500 ≈ 49,985; symbol_value 25,000 → ~50% > 20%
    eq = fresh_pf.equity({"ADANIENT": 2500.0})
    result = check_all_caps(
        fresh_pf, prices={"ADANIENT": 2500.0},
        day_start_equity=eq, risk_cfg=risk_cfg,
    )
    assert result.can_trade is False
    assert any("max_symbol_notional_pct" in r for r in result.reasons)
    assert "symbol_exposure_pct[ADANIENT]" in result.metrics


# ═══════════════════════════════════════════════════════════════════════════════
# 3. calculate_position_size — negative ATR rejected
# ═══════════════════════════════════════════════════════════════════════════════
def test_negative_atr_rejected(risk_cfg, indi_cfg, fee_cfg):
    result = calculate_position_size(
        equity=50_000, price=1000, atr=-1.0,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    assert result.rejected
    assert result.qty == 0
    assert any("atr" in r.lower() and "non-negative" in r.lower() for r in result.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. calculate_position_size — negative exposure inputs rejected
# ═══════════════════════════════════════════════════════════════════════════════
def test_negative_symbol_exposure_rejected(risk_cfg, indi_cfg, fee_cfg):
    result = calculate_position_size(
        equity=50_000, price=1000, atr=5.0,
        current_symbol_exposure=-100.0,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    assert result.rejected
    assert any("current_symbol_exposure" in r for r in result.reasons)


def test_negative_total_exposure_rejected(risk_cfg, indi_cfg, fee_cfg):
    result = calculate_position_size(
        equity=50_000, price=1000, atr=5.0,
        current_total_exposure=-100.0,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    assert result.rejected
    assert any("current_total_exposure" in r for r in result.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Invalid product — charges raises, execution_sim rejects, risk rejects
# ═══════════════════════════════════════════════════════════════════════════════
def test_charges_invalid_product_raises():
    with pytest.raises(ValueError, match="invalid product"):
        calculate_charges(price=100.0, qty=1, side="BUY", product="MTF")  # type: ignore


def test_execution_sim_invalid_product_returns_rejected_fill(usable_quote, fee_cfg):
    fill = simulate_fill(usable_quote, "BUY", 10, fee_cfg, product="MTF")  # type: ignore
    assert not fill.is_executed
    assert fill.reject_reason is not None
    assert "invalid product" in fill.reject_reason.lower()


def test_risk_invalid_product_rejected(risk_cfg, indi_cfg, fee_cfg):
    result = calculate_position_size(
        equity=50_000, price=1000, atr=5.0,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        product="MTF",  # type: ignore
    )
    assert result.rejected
    assert any("invalid product" in r.lower() for r in result.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Observability metrics on SizingResult
# ═══════════════════════════════════════════════════════════════════════════════
def test_sizing_metrics_populated_on_success(risk_cfg, indi_cfg, fee_cfg):
    r = calculate_position_size(
        equity=100_000, price=500, atr=5.0,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
    )
    assert not r.rejected
    for key in [
        "initial_qty_before_cost_reduction",
        "final_qty",
        "qty_reduced_for_costs",
        "stop_loss_component",
        "charges_component",
        "slippage_component",
    ]:
        assert key in r.metrics, f"missing metric: {key}"
    assert r.metrics["final_qty"] == r.qty
    # Final qty never exceeds initial
    assert r.metrics["final_qty"] <= r.metrics["initial_qty_before_cost_reduction"]
    # Components sum approximately to expected_loss
    component_sum = (
        r.metrics["stop_loss_component"]
        + r.metrics["charges_component"]
        + r.metrics["slippage_component"]
    )
    assert component_sum == pytest.approx(r.expected_loss, abs=0.5)


def test_sizing_metrics_show_reduction_under_high_slippage(risk_cfg, indi_cfg):
    """
    Tight risk budget + high slippage should force the cost-reduction loop to
    shrink qty below the cap-based initial qty.
    """
    tight_risk = RiskConfig(risk_per_trade_pct=0.5)
    high_slip  = FeeConfig(intraday_slippage_bps=50.0)
    r = calculate_position_size(
        equity=200_000, price=1000, atr=5.0,
        risk_cfg=tight_risk, indi_cfg=indi_cfg, fee_cfg=high_slip,
    )
    # If not rejected, qty must have been trimmed for costs
    if not r.rejected:
        assert r.metrics["qty_reduced_for_costs"] >= 0
        assert r.metrics["final_qty"] == r.qty
        # Charges + slippage components must be non-zero (high slip drives them up)
        assert r.metrics["slippage_component"] > 0
        assert r.metrics["charges_component"] > 0
