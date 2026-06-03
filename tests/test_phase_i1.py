"""
Phase I.1 — fractional crypto qty + min_notional gate.

Guarantees:
  1. Rs.50k portfolio can paper-buy a fractional BTC/ETH (qty < 1).
  2. Sizing floors to crypto_qty_step (no qty=0.00012345 surprises).
  3. Min-notional gate rejects trades below crypto_min_notional_inr.
  4. Equity mode (INTRADAY/DELIVERY) still produces integer qty.
  5. Position model accepts fractional qty (Pydantic float field).
  6. simulate_fill executes with fractional qty.
  7. round_trip_cost works with fractional qty.
  8. DB persists fractional qty exactly (REAL not INTEGER).
"""

from datetime import datetime
from pathlib import Path
import pytest

from bot.charges import calculate_charges, round_trip_cost
from bot.config import (
    BotConfig, FeeConfig, IndicatorConfig, RiskConfig, crypto_inr_config,
)
from bot.db import get_all_trades, init_db, log_trade, set_db_path
from bot.engine import do_buy
from bot.execution_sim import simulate_fill
from bot.market_data import IST, Quote
from bot.portfolio import Portfolio, Position
from bot.risk import calculate_position_size
from bot.signals import Signal, SignalCandidate, ScoreBundle, SizingPreview
from bot.supervisor import _sizing_preview_is_usable


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_db(tmp_path):
    p = tmp_path / "i1.db"
    set_db_path(p)
    init_db()
    yield p
    set_db_path(Path(__file__).parent.parent / "kite_bot.db")


@pytest.fixture
def crypto_cfg():
    base = crypto_inr_config()
    return BotConfig(
        asset=base.asset, fees=base.fees, market=base.market,
        supervisor=base.supervisor, indicators=base.indicators,
        risk=RiskConfig(
            risk_per_trade_pct=1.0,
            max_open_positions=5, max_daily_loss_pct=10.0,
            max_drawdown_pct=25.0, max_total_exposure_pct=200.0,
            max_symbol_notional_pct=30.0,
        ),
    )


@pytest.fixture
def fresh_pf_50k():
    return Portfolio.fresh(starting_balance=50_000.0)


def _usable_quote(symbol="BTC-INR", price=4_500_000.0):
    return Quote(symbol=symbol, price=price,
                 timestamp=datetime.now(tz=IST),
                 is_stale=False, reject_reason=None)


# ═══════════════════════════════════════════════════════════════════════════════
# 1 + 2 — Rs.50k can size a fractional BTC; qty is floored to qty_step
# ═══════════════════════════════════════════════════════════════════════════════
def test_rs50k_can_size_fractional_btc(crypto_cfg):
    """Real BTC-INR at Rs.4.5M. Rs.50k portfolio. Default qty_step=0.0001."""
    sizing = calculate_position_size(
        equity=50_000.0, price=4_500_000.0,
        atr=4_500_000.0 * 0.01,           # 1% ATR
        risk_cfg=crypto_cfg.risk,
        indi_cfg=crypto_cfg.indicators,
        fee_cfg=crypto_cfg.fees,
        product="CRYPTO",
    )
    assert not sizing.rejected, sizing.reasons
    # qty must be fractional (< 1) and a multiple of step (0.0001)
    assert 0 < sizing.qty < 1
    step = crypto_cfg.fees.crypto_qty_step
    # Floor-quantize: qty should be very close to a multiple of step
    multiples = sizing.qty / step
    assert abs(multiples - round(multiples)) < 1e-6, \
        f"qty {sizing.qty} not aligned to step {step}"
    # Notional must be within the crypto symbol cap (10% of 50k = 5k)
    notional = sizing.qty * 4_500_000.0
    assert notional <= 5_000.0 + 1.0


def test_rs50k_eth_fractional(crypto_cfg):
    """Rs.50k vs ETH at Rs.300k → should size ~0.05 ETH = Rs.15k."""
    sizing = calculate_position_size(
        equity=50_000.0, price=300_000.0,
        atr=300_000.0 * 0.01,
        risk_cfg=crypto_cfg.risk, indi_cfg=crypto_cfg.indicators,
        fee_cfg=crypto_cfg.fees, product="CRYPTO",
    )
    assert not sizing.rejected, sizing.reasons
    assert sizing.qty > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3 — Min-notional gate rejects tiny trades
# ═══════════════════════════════════════════════════════════════════════════════
def test_min_notional_rejects_tiny_trade(crypto_cfg):
    """High min_notional + tiny risk_amount → reject."""
    fees = crypto_cfg.fees.model_copy(update={"crypto_min_notional_inr": 100_000.0})
    sizing = calculate_position_size(
        equity=50_000.0, price=4_500_000.0,
        atr=4_500_000.0 * 0.01,
        risk_cfg=crypto_cfg.risk, indi_cfg=crypto_cfg.indicators,
        fee_cfg=fees, product="CRYPTO",
    )
    assert sizing.rejected
    assert any("notional" in r.lower() and "below min" in r.lower()
               for r in sizing.reasons), sizing.reasons


# ═══════════════════════════════════════════════════════════════════════════════
# 4 — Equity mode still produces integer qty
# ═══════════════════════════════════════════════════════════════════════════════
def test_equity_mode_qty_is_whole_number(crypto_cfg):
    """INTRADAY product → qty floored to int. Step=1.0 by construction."""
    sizing = calculate_position_size(
        equity=200_000.0, price=2_500.0, atr=15.0,
        risk_cfg=RiskConfig(),     # default equity caps
        indi_cfg=IndicatorConfig(), fee_cfg=FeeConfig(),
        product="INTRADAY",
    )
    if not sizing.rejected:
        # Must be an integer value
        assert sizing.qty == int(sizing.qty), f"equity qty {sizing.qty} not int"


# ═══════════════════════════════════════════════════════════════════════════════
# 5 — Position model accepts fractional qty
# ═══════════════════════════════════════════════════════════════════════════════
def test_position_model_accepts_fractional_qty():
    pos = Position(
        symbol="BTC-INR", qty=0.0025, entry_price=4_500_000.0,
        stop=4_455_000.0, target=4_590_000.0, charges_buy=10.0,
        entry_time=datetime.now(),
    )
    assert pos.qty == pytest.approx(0.0025)


def test_position_model_rejects_zero_qty():
    with pytest.raises(Exception):
        Position(
            symbol="BTC-INR", qty=0.0, entry_price=100.0,
            stop=99.0, target=101.0, charges_buy=1.0,
            entry_time=datetime.now(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 6 — simulate_fill executes with fractional qty
# ═══════════════════════════════════════════════════════════════════════════════
def test_simulate_fill_fractional_qty(crypto_cfg):
    q = _usable_quote("BTC-INR", 4_500_000.0)
    fill = simulate_fill(q, "BUY", 0.0025, crypto_cfg.fees, product="CRYPTO")
    assert fill.is_executed
    assert fill.qty == pytest.approx(0.0025)
    assert fill.fill_price > q.price   # slippage applied
    assert fill.charges.total > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 7 — round_trip_cost works with fractional qty
# ═══════════════════════════════════════════════════════════════════════════════
def test_round_trip_cost_fractional():
    rt = round_trip_cost(price=4_500_000.0, qty=0.001, product="CRYPTO")
    # 0.001 BTC at Rs.4.5M = Rs.4500 notional. 10 bps/side = Rs.4.5 per side.
    # Round trip ≈ Rs.9
    assert 5.0 <= rt <= 15.0, f"rt={rt}"


def test_charges_fractional_no_floor_to_zero():
    ch = calculate_charges(price=4_500_000.0, qty=0.001, side="BUY", product="CRYPTO")
    assert ch.brokerage > 0
    assert ch.total > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 8 — DB persists fractional qty exactly
# ═══════════════════════════════════════════════════════════════════════════════
def test_db_persists_fractional_qty(tmp_db):
    log_trade({
        "ts": "2026-05-25 10:00:00", "symbol": "BTC-INR", "action": "BUY",
        "price": 4_500_000.0, "qty": 0.0025, "value": 11_250.0, "charges": 12.0,
        "stop": 4_455_000.0, "target": 4_590_000.0, "pnl": None,
        "balance_after": 38_750.0,
    })
    rows = get_all_trades()
    assert len(rows) == 1
    assert rows[0]["qty"] == pytest.approx(0.0025)
    # Crucial: SQLite must NOT have floored to 0
    assert rows[0]["qty"] != 0


# ═══════════════════════════════════════════════════════════════════════════════
# 9 — End-to-end: do_buy places a fractional BTC paper trade from Rs.50k
# ═══════════════════════════════════════════════════════════════════════════════
def test_do_buy_fractional_btc_end_to_end(tmp_db, crypto_cfg, fresh_pf_50k):
    """The headline ask: a Rs.50k portfolio paper-buys real-priced BTC-INR."""
    def qp(symbol):
        if symbol != "BTC-INR":
            return None
        return _usable_quote("BTC-INR", 4_500_000.0)
    result = do_buy(
        "BTC-INR", fresh_pf_50k, qp,
        day_start_equity=50_000.0,
        risk_cfg=crypto_cfg.risk,
        indi_cfg=crypto_cfg.indicators,
        fee_cfg=crypto_cfg.fees,
        atr=4_500_000.0 * 0.01,
        product="CRYPTO",
    )
    assert not result.rejected, result.reasons
    assert result.fill is not None
    assert 0 < result.fill.qty < 1, "expected fractional BTC fill"
    # Cash must remain positive — the trade fit within 50k
    assert fresh_pf_50k.state.cash > 0
    # Position was opened
    assert "BTC-INR" in fresh_pf_50k.state.positions
    held = fresh_pf_50k.state.positions["BTC-INR"]
    assert held.qty == result.fill.qty


def test_supervisor_final_gate_allows_fractional_crypto_qty(crypto_cfg):
    """Regression: supervisor auto-buy must not use the old qty < 1 stock gate."""
    candidate = SignalCandidate(
        ts=datetime.now(), symbol="BTC-INR", signal=Signal.BUY_CANDIDATE,
        scores=ScoreBundle(technical=0.9, sentiment=0.5, fundamentals=0.5,
                           liquidity=0.5, risk=0.8, total=0.72),
        indicators={"price": 4_500_000.0},
        research_snapshot_id=1,
        entry_blocked=False,
        block_reasons=[],
        sizing_preview=SizingPreview(
            qty=0.002, stop_distance=90_000.0,
            expected_loss=180.0, rejected=False, reasons=[],
        ),
        rejection_reason=None,
    )
    ok, reason = _sizing_preview_is_usable(
        candidate, crypto_cfg.fees, product="CRYPTO",
    )
    assert ok is True
    assert reason == ""
