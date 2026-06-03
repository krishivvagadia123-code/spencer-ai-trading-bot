"""
Zerodha equity charges — INTRADAY and DELIVERY computed separately.

All values are from Zerodha's official public charges page (zerodha.com/charges).
Verify these BEFORE going live — rates change. Sources noted inline.

Tested against Zerodha's brokerage calculator (zerodha.com/brokerage-calculator)
in tests/test_charges.py — values within Rs.0.50 tolerance.
"""

from typing import Literal
from dataclasses import dataclass

# ── Source: https://zerodha.com/charges ───────────────────────────────────────
# Equity intraday brokerage: 0.03% or Rs.20 whichever is lower per executed order
BROKERAGE_INTRADAY_PCT      = 0.0003       # 0.03%
BROKERAGE_INTRADAY_CAP      = 20.0          # Rs.20 cap
BROKERAGE_DELIVERY_PCT      = 0.0           # Zero brokerage on delivery

# STT (Securities Transaction Tax) — Govt of India
STT_INTRADAY_SELL_PCT       = 0.00025       # 0.025% on sell side only
STT_DELIVERY_BOTH_SIDES_PCT = 0.001         # 0.1% on both buy and sell

# NSE Exchange Transaction Charge — official Zerodha rate
# Source: https://zerodha.com/charges (NSE equity cash row)
# Verified: 2026-05-24 — current public rate is 0.00307%
EXCHANGE_TXN_NSE_PCT        = 0.0000307     # 0.00307%

# SEBI Turnover Fee — Rs.10 per crore = 0.0001% / 100 = 0.0000001
SEBI_CHARGE_PCT             = 0.0000001

# GST — applied on (brokerage + exchange + SEBI)
GST_PCT                     = 0.18          # 18%

# Stamp Duty — Govt of India (buy-side only)
STAMP_DUTY_INTRADAY_PCT     = 0.00003       # 0.003% on buy side intraday
STAMP_DUTY_DELIVERY_PCT     = 0.00015       # 0.015% on buy side delivery

# DP Charges (delivery sell only — modelling actual demat delivery)
DP_CHARGE_PER_SCRIP         = 13.5          # Rs.13.5 + GST per scrip per day on sell
# ─────────────────────────────────────────────────────────────────────────────


Side    = Literal["BUY", "SELL"]
Product = Literal["INTRADAY", "DELIVERY", "CRYPTO"]

# Crypto-paper flat fee (one side). Set generously — exchanges vary 0.05-0.20%.
CRYPTO_PAPER_FEE_BPS = 10.0   # 0.10% per side


@dataclass(frozen=True)
class ChargeBreakdown:
    brokerage: float
    stt:       float
    exchange:  float
    sebi:      float
    gst:       float
    stamp:     float
    dp:        float
    total:     float

    def as_dict(self) -> dict:
        return {
            "brokerage": self.brokerage, "stt": self.stt,
            "exchange":  self.exchange,  "sebi": self.sebi,
            "gst":       self.gst,       "stamp": self.stamp,
            "dp":        self.dp,        "total": self.total,
        }


def _round(x: float) -> float:
    return round(x, 2)


def calculate_charges(
    price:   float,
    qty:     float,
    side:    Side,
    product: Product = "INTRADAY",
) -> ChargeBreakdown:
    """Compute Zerodha charges for a single leg of an equity trade, or a flat
    crypto-paper fee when product='CRYPTO' (NO Zerodha/STT/GST/stamp applied)."""
    if qty <= 0:
        raise ValueError(f"qty must be positive, got {qty}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    if product not in ("INTRADAY", "DELIVERY", "CRYPTO"):
        raise ValueError(f"invalid product: {product!r}; must be 'INTRADAY', 'DELIVERY' or 'CRYPTO'")
    if side not in ("BUY", "SELL"):
        raise ValueError(f"invalid side: {side!r}; must be 'BUY' or 'SELL'")

    turnover = price * qty

    # Crypto: flat-bps fee only. No STT, exchange charge, SEBI fee, GST,
    # stamp duty, or DP charges — those are Indian-equity-specific.
    if product == "CRYPTO":
        brokerage = turnover * (CRYPTO_PAPER_FEE_BPS / 10_000)
        return ChargeBreakdown(
            brokerage=_round(brokerage), stt=0.0, exchange=0.0, sebi=0.0,
            gst=0.0, stamp=0.0, dp=0.0, total=_round(brokerage),
        )

    if product == "INTRADAY":
        brokerage = min(turnover * BROKERAGE_INTRADAY_PCT, BROKERAGE_INTRADAY_CAP)
    else:
        brokerage = turnover * BROKERAGE_DELIVERY_PCT

    if product == "INTRADAY":
        stt = turnover * STT_INTRADAY_SELL_PCT if side == "SELL" else 0.0
    else:
        stt = turnover * STT_DELIVERY_BOTH_SIDES_PCT

    exchange = turnover * EXCHANGE_TXN_NSE_PCT
    sebi     = turnover * SEBI_CHARGE_PCT
    gst      = (brokerage + exchange + sebi) * GST_PCT

    if side == "BUY":
        stamp = turnover * (STAMP_DUTY_INTRADAY_PCT if product == "INTRADAY"
                            else STAMP_DUTY_DELIVERY_PCT)
    else:
        stamp = 0.0

    dp = DP_CHARGE_PER_SCRIP * (1 + GST_PCT) if (product == "DELIVERY" and side == "SELL") else 0.0

    total = brokerage + stt + exchange + sebi + gst + stamp + dp

    return ChargeBreakdown(
        brokerage=_round(brokerage), stt=_round(stt),
        exchange=_round(exchange),  sebi=_round(sebi),
        gst=_round(gst),            stamp=_round(stamp),
        dp=_round(dp),              total=_round(total),
    )


def round_trip_cost(price: float, qty: float, product: Product = "INTRADAY") -> float:
    """Total charges for buy + sell at same price (cost-only estimate)."""
    buy  = calculate_charges(price, qty, "BUY",  product)
    sell = calculate_charges(price, qty, "SELL", product)
    return _round(buy.total + sell.total)
