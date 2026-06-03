"""
Execution simulator tests — slippage direction, charges on fill price,
unusable quote rejection, qty/side validation.
"""

from datetime import datetime, timedelta
import pytest

from bot.config import FeeConfig, MarketConfig
from bot.market_data import Quote, IST, validate_quote
from bot.execution_sim import simulate_fill, Fill
from bot.charges import calculate_charges


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def fee_cfg():
    return FeeConfig()                    # 5 bps intraday default


@pytest.fixture
def mkt_cfg():
    return MarketConfig()


@pytest.fixture
def usable_quote(mkt_cfg):
    """A live, in-session, fresh quote."""
    now      = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
    quote_ts = now - timedelta(seconds=5)
    return validate_quote(2500.0, quote_ts, "ADANIENT", mkt_cfg, now=now)


@pytest.fixture
def stale_quote(mkt_cfg):
    now      = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
    quote_ts = now - timedelta(seconds=120)
    return validate_quote(2500.0, quote_ts, "ADANIENT", mkt_cfg, now=now)


# ═══════════════════════════════════════════════════════════════════════════════
# Slippage direction
# ═══════════════════════════════════════════════════════════════════════════════
def test_buy_fill_price_higher_than_quote(usable_quote, fee_cfg):
    fill = simulate_fill(usable_quote, "BUY", 10, fee_cfg)
    assert fill.is_executed
    assert fill.fill_price > usable_quote.price
    # 5 bps slippage on 2500 = Rs.1.25 → fill 2501.25
    assert fill.fill_price == pytest.approx(2501.25, abs=0.05)


def test_sell_fill_price_lower_than_quote(usable_quote, fee_cfg):
    fill = simulate_fill(usable_quote, "SELL", 10, fee_cfg)
    assert fill.is_executed
    assert fill.fill_price < usable_quote.price
    assert fill.fill_price == pytest.approx(2498.75, abs=0.05)


def test_slippage_per_share_is_absolute_value(usable_quote, fee_cfg):
    buy  = simulate_fill(usable_quote, "BUY",  10, fee_cfg)
    sell = simulate_fill(usable_quote, "SELL", 10, fee_cfg)
    assert buy.slippage  > 0
    assert sell.slippage > 0
    assert buy.slippage == pytest.approx(sell.slippage, abs=0.01)


def test_zero_slippage_means_fill_equals_quote(usable_quote):
    zero_fee = FeeConfig(intraday_slippage_bps=0.0)
    buy = simulate_fill(usable_quote, "BUY", 10, zero_fee)
    assert buy.fill_price == usable_quote.price
    assert buy.slippage == 0


def test_higher_slippage_bps_widens_fill(usable_quote):
    low  = FeeConfig(intraday_slippage_bps=5.0)
    high = FeeConfig(intraday_slippage_bps=50.0)
    buy_low  = simulate_fill(usable_quote, "BUY", 1, low)
    buy_high = simulate_fill(usable_quote, "BUY", 1, high)
    assert buy_high.fill_price > buy_low.fill_price


# ═══════════════════════════════════════════════════════════════════════════════
# Unusable quotes are rejected outright
# ═══════════════════════════════════════════════════════════════════════════════
def test_stale_quote_rejected(stale_quote, fee_cfg):
    fill = simulate_fill(stale_quote, "BUY", 10, fee_cfg)
    assert fill.is_executed is False
    assert "stale" in fill.reject_reason.lower() or "old" in fill.reject_reason.lower()
    assert fill.charges is None
    assert fill.fill_price == 0.0


def test_market_closed_quote_rejected(fee_cfg, mkt_cfg):
    sunday = datetime(2026, 5, 31, 10, 0, tzinfo=IST)
    quote  = validate_quote(2500.0, sunday, "ADANIENT", mkt_cfg, now=sunday)
    fill   = simulate_fill(quote, "BUY", 10, fee_cfg)
    assert fill.is_executed is False
    assert "market closed" in fill.reject_reason.lower() \
        or "weekend" in fill.reject_reason.lower()


def test_invalid_qty_rejected(usable_quote, fee_cfg):
    fill = simulate_fill(usable_quote, "BUY", 0, fee_cfg)
    assert fill.is_executed is False
    assert "qty" in fill.reject_reason.lower()


def test_negative_qty_rejected(usable_quote, fee_cfg):
    fill = simulate_fill(usable_quote, "BUY", -5, fee_cfg)
    assert fill.is_executed is False


def test_invalid_side_rejected(usable_quote, fee_cfg):
    fill = simulate_fill(usable_quote, "HOLD", 1, fee_cfg)   # type: ignore[arg-type]
    assert fill.is_executed is False
    assert "side" in fill.reject_reason.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Charges computed from FILL price, not quote price
# ═══════════════════════════════════════════════════════════════════════════════
def test_charges_use_fill_price_not_quote(usable_quote, fee_cfg):
    fill = simulate_fill(usable_quote, "BUY", 10, fee_cfg)
    # Charges computed from fill_price=2501.25 (NOT quote.price=2500)
    expected = calculate_charges(price=fill.fill_price, qty=10, side="BUY", product="INTRADAY")
    assert fill.charges.total == expected.total
    assert fill.charges.brokerage == expected.brokerage


def test_charges_differ_from_quote_based_calculation(usable_quote):
    """With non-trivial slippage and qty, fill-based charges must differ from
    quote-based charges. Uses 50 bps + qty=100 so differences clear rounding."""
    big_slip = FeeConfig(intraday_slippage_bps=50.0)
    fill = simulate_fill(usable_quote, "BUY", 100, big_slip)
    quote_based = calculate_charges(price=usable_quote.price, qty=100, side="BUY",
                                    product="INTRADAY")
    # Total differs by more than rounding noise
    assert fill.charges.total != quote_based.total
    assert fill.charges.total > quote_based.total   # BUY slippage → higher turnover


def test_sell_charges_include_stt(usable_quote, fee_cfg):
    sell = simulate_fill(usable_quote, "SELL", 10, fee_cfg)
    assert sell.charges.stt > 0


def test_buy_charges_include_stamp_duty(usable_quote, fee_cfg):
    buy = simulate_fill(usable_quote, "BUY", 10, fee_cfg)
    assert buy.charges.stamp > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Fill object integrity
# ═══════════════════════════════════════════════════════════════════════════════
def test_executed_fill_has_all_fields(usable_quote, fee_cfg):
    fill = simulate_fill(usable_quote, "BUY", 10, fee_cfg)
    assert isinstance(fill, Fill)
    assert fill.symbol == "ADANIENT"
    assert fill.side == "BUY"
    assert fill.qty == 10
    assert fill.quote_price == 2500.0
    assert fill.fill_price > 0
    assert fill.slippage >= 0
    assert fill.charges is not None
    assert fill.timestamp == usable_quote.timestamp
    assert fill.reject_reason is None


def test_total_slippage_property(usable_quote, fee_cfg):
    fill = simulate_fill(usable_quote, "BUY", 10, fee_cfg)
    assert fill.total_slippage == pytest.approx(fill.slippage * fill.qty, abs=0.05)


def test_total_slippage_zero_on_rejected_fill(stale_quote, fee_cfg):
    fill = simulate_fill(stale_quote, "BUY", 10, fee_cfg)
    assert fill.total_slippage == 0.0


def test_delivery_product_uses_delivery_slippage(usable_quote):
    """Delivery slippage bps differs from intraday — fill price should reflect."""
    fee_cfg = FeeConfig(intraday_slippage_bps=5.0, delivery_slippage_bps=20.0)
    intraday = simulate_fill(usable_quote, "BUY", 10, fee_cfg, product="INTRADAY")
    delivery = simulate_fill(usable_quote, "BUY", 10, fee_cfg, product="DELIVERY")
    assert delivery.fill_price > intraday.fill_price
