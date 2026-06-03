"""
Charges tests — validates against Zerodha's brokerage calculator.
Tolerance: Rs.0.50 per side. Uses verified NSE rate 0.00307%.
"""
import pytest
from bot.charges import (
    calculate_charges, round_trip_cost,
    BROKERAGE_INTRADAY_CAP, EXCHANGE_TXN_NSE_PCT,
)


def test_nse_rate_is_correct_official_value():
    """Guard against silent constant drift."""
    assert EXCHANGE_TXN_NSE_PCT == 0.0000307


# ── Intraday ──────────────────────────────────────────────────────────────────
def test_intraday_buy_basic():
    """ADANIENT @ Rs.2500, 10 shares, intraday BUY."""
    c = calculate_charges(price=2500, qty=10, side="BUY", product="INTRADAY")
    # turnover = 25,000
    # brokerage = min(25000 * 0.0003, 20) = 7.5
    # exchange  = 25000 * 0.0000307 = 0.7675
    # sebi      = 25000 * 0.0000001 = 0.0025
    # gst       = (7.5 + 0.7675 + 0.0025) * 0.18 ≈ 1.488
    # stamp     = 25000 * 0.00003 = 0.75
    # total ≈ 10.51
    assert c.brokerage == pytest.approx(7.5,  abs=0.5)
    assert c.stt       == 0.0
    assert c.stamp     == pytest.approx(0.75, abs=0.05)
    assert c.dp        == 0.0
    assert c.total     == pytest.approx(10.51, abs=0.5)


def test_intraday_sell_includes_stt():
    c = calculate_charges(price=2500, qty=10, side="SELL", product="INTRADAY")
    assert c.stt   == pytest.approx(6.25, abs=0.05)
    assert c.stamp == 0.0
    assert c.dp    == 0.0


def test_intraday_brokerage_cap():
    c = calculate_charges(price=1000, qty=100, side="BUY", product="INTRADAY")
    assert c.brokerage == BROKERAGE_INTRADAY_CAP


def test_intraday_low_turnover_uses_percentage():
    c = calculate_charges(price=100, qty=10, side="BUY", product="INTRADAY")
    assert c.brokerage == pytest.approx(0.30, abs=0.01)


# ── Delivery ──────────────────────────────────────────────────────────────────
def test_delivery_zero_brokerage():
    c = calculate_charges(price=2500, qty=10, side="BUY", product="DELIVERY")
    assert c.brokerage == 0.0


def test_delivery_stt_both_sides():
    buy  = calculate_charges(price=2500, qty=10, side="BUY",  product="DELIVERY")
    sell = calculate_charges(price=2500, qty=10, side="SELL", product="DELIVERY")
    assert buy.stt  == pytest.approx(25.0, abs=0.1)
    assert sell.stt == pytest.approx(25.0, abs=0.1)


def test_delivery_sell_has_dp_charge():
    sell = calculate_charges(price=2500, qty=10, side="SELL", product="DELIVERY")
    assert sell.dp > 0
    assert sell.dp == pytest.approx(15.93, abs=0.1)


def test_delivery_buy_no_dp_charge():
    buy = calculate_charges(price=2500, qty=10, side="BUY", product="DELIVERY")
    assert buy.dp == 0.0


def test_delivery_stamp_duty_higher_than_intraday():
    intra = calculate_charges(price=2500, qty=10, side="BUY", product="INTRADAY")
    deliv = calculate_charges(price=2500, qty=10, side="BUY", product="DELIVERY")
    assert deliv.stamp == pytest.approx(intra.stamp * 5, abs=0.1)


# ── Round-trip ────────────────────────────────────────────────────────────────
def test_round_trip_intraday():
    rt = round_trip_cost(price=2500, qty=10, product="INTRADAY")
    # ~10.51 (buy) + ~16.88 (sell) ≈ 27.4 with 0.00307% NSE
    assert rt == pytest.approx(27.4, abs=1.0)


def test_round_trip_delivery_higher_than_intraday():
    intra = round_trip_cost(price=2500, qty=10, product="INTRADAY")
    deliv = round_trip_cost(price=2500, qty=10, product="DELIVERY")
    assert deliv > intra


# ── Edge cases ────────────────────────────────────────────────────────────────
def test_zero_qty_raises():
    with pytest.raises(ValueError, match="qty"):
        calculate_charges(price=100, qty=0, side="BUY")


def test_negative_price_raises():
    with pytest.raises(ValueError, match="price"):
        calculate_charges(price=-10, qty=1, side="BUY")


def test_charge_breakdown_sums_to_total():
    c = calculate_charges(price=2500, qty=10, side="SELL", product="INTRADAY")
    expected = c.brokerage + c.stt + c.exchange + c.sebi + c.gst + c.stamp + c.dp
    assert abs(c.total - expected) < 0.1
