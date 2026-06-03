"""
Paper-only execution simulator.

Given a usable Quote + side + qty, produce a Fill with:
  - fill_price = quote.price * (1 +/- slippage_bps/10000)
  - charges    = Zerodha charges computed on the FILL price (not quote price)
  - slippage   = absolute per-share slippage amount

Unusable quotes are rejected outright with reject_reason propagated.
This module never places real orders. No broker integration.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal

from bot.charges import calculate_charges, ChargeBreakdown, Product
from bot.config import FeeConfig
from bot.market_data import Quote


Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class Fill:
    symbol:        str
    side:          Side
    qty:           float                     # float for fractional crypto support
    quote_price:   float
    fill_price:    float
    slippage:      float                     # absolute Rs. per unit
    charges:       Optional[ChargeBreakdown]
    timestamp:     datetime
    reject_reason: Optional[str] = None

    @property
    def is_executed(self) -> bool:
        return self.reject_reason is None

    @property
    def total_slippage(self) -> float:
        """Total slippage cost across all shares filled."""
        return round(self.slippage * self.qty, 2) if self.is_executed else 0.0


def _rejected_fill(quote: Quote, side: Side, qty: float, reason: str) -> Fill:
    return Fill(
        symbol=quote.symbol, side=side, qty=qty,
        quote_price=quote.price, fill_price=0.0,
        slippage=0.0, charges=None,
        timestamp=quote.timestamp, reject_reason=reason,
    )


def simulate_fill(
    quote:   Quote,
    side:    Side,
    qty:     float,
    fee_cfg: FeeConfig,
    product: Product = "INTRADAY",
) -> Fill:
    """
    Simulate a market-order fill at quote.price adjusted by slippage.
    Returns a Fill — check fill.is_executed before treating as real.
    """
    # 1. Reject unusable quotes — never trade on stale/closed/naked data
    if not quote.is_usable:
        return _rejected_fill(quote, side, qty,
                              f"unusable quote: {quote.reject_reason}")

    # 2. Validate qty + side + product. Crypto-fractional minimum here is
    #    intentionally tiny (1e-8 ~ satoshi); the risk module enforces the
    #    real qty_step + min_notional gate upstream.
    if qty <= 0:
        return _rejected_fill(quote, side, qty, f"qty must be > 0, got {qty}")
    if side not in ("BUY", "SELL"):
        return _rejected_fill(quote, side, qty, f"invalid side: {side!r}")
    if product not in ("INTRADAY", "DELIVERY", "CRYPTO"):
        return _rejected_fill(quote, side, qty,
                              f"invalid product: {product!r}; must be 'INTRADAY', 'DELIVERY' or 'CRYPTO'")

    # 3. Apply slippage in the unfavourable direction
    if product == "INTRADAY":
        slippage_bps = fee_cfg.intraday_slippage_bps
    elif product == "DELIVERY":
        slippage_bps = fee_cfg.delivery_slippage_bps
    else:  # CRYPTO
        slippage_bps = fee_cfg.crypto_slippage_bps
    factor       = (1 + slippage_bps / 10_000) if side == "BUY" \
                   else (1 - slippage_bps / 10_000)
    fill_price   = round(quote.price * factor, 2)

    # Sanity: SELL slippage could not push price below 0
    if fill_price <= 0:
        return _rejected_fill(quote, side, qty,
                              f"slippage produced non-positive fill_price {fill_price}")

    slippage_per_share = round(abs(fill_price - quote.price), 4)

    # 4. Compute Zerodha charges on the FILL price (not the quote price)
    charges = calculate_charges(price=fill_price, qty=qty, side=side, product=product)

    return Fill(
        symbol=quote.symbol, side=side, qty=qty,
        quote_price=quote.price, fill_price=fill_price,
        slippage=slippage_per_share, charges=charges,
        timestamp=quote.timestamp,
    )
