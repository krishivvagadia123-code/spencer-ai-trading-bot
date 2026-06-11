"""
Risk module — volatility-scaled position sizing + cap enforcement.

Sizing pipeline:
  stop_distance = max(ATR * multiplier, min_stop_pct * price)
  risk_amount   = equity * risk_per_trade_pct / 100
  qty_by_risk   = floor(risk_amount / stop_distance)
  qty_by_symbol = floor(symbol_cap_remaining / price)
  qty_by_total  = floor(total_exposure_cap_remaining / price)
  qty           = min(all caps), then reduced until expected_loss <= risk_amount

Caps pipeline:
  can_trade only if NONE of these tripped:
    - missing market price (fail closed)
    - daily loss >= max_daily_loss_pct
    - drawdown >= max_drawdown_pct
    - open_positions >= max_open_positions
"""

from dataclasses import dataclass, field
from typing import Dict, List

from bot.charges import calculate_charges, round_trip_cost, Product
from bot.config import RiskConfig, IndicatorConfig, FeeConfig
from bot.control import read_state as _read_control_state
from bot.portfolio import Portfolio, MissingPriceError


# ── Result types ──────────────────────────────────────────────────────────────
@dataclass
class SizingResult:
    qty:           float        # 0 if rejected; integer for equity, fractional for crypto
    rejected:      bool
    reasons:       List[str]
    stop_distance: float
    risk_amount:   float
    expected_loss: float        # incl. charges + slippage at the sized qty
    metrics:       Dict[str, float] = field(default_factory=dict)


@dataclass
class CapsCheckResult:
    can_trade: bool
    reasons:   List[str]
    metrics:   Dict[str, float] = field(default_factory=dict)


@dataclass
class EntryGateResult:
    """
    Result of the BUY-entry gate. Combines control flags (kill/pause) with
    portfolio cap checks. NEVER consulted on the exit path — exits always go
    through regardless of caps, kill switch, or pause state.
    """
    can_enter: bool
    reasons:   List[str]
    caps:      "CapsCheckResult"


# ── Sizing ────────────────────────────────────────────────────────────────────
def _round_trip_slippage(price: float, qty: int, slippage_bps: float) -> float:
    """Slippage cost on round-trip = 2 legs × price × bps × qty."""
    per_share = price * (slippage_bps / 10_000)
    return round(2 * per_share * qty, 2)


def calculate_position_size(
    *,
    equity: float,
    price: float,
    atr: float,
    current_symbol_exposure: float = 0.0,
    current_total_exposure:  float = 0.0,
    risk_cfg:  RiskConfig,
    indi_cfg:  IndicatorConfig,
    fee_cfg:   FeeConfig,
    product:   Product = "INTRADAY",
) -> SizingResult:
    """Compute volatility-scaled qty. Rejects if any cap fails or qty<1."""
    reasons: List[str] = []

    if equity <= 0 or price <= 0:
        return SizingResult(qty=0, rejected=True,
                            reasons=[f"non-positive equity ({equity}) or price ({price})"],
                            stop_distance=0.0, risk_amount=0.0, expected_loss=0.0)

    if product not in ("INTRADAY", "DELIVERY", "CRYPTO"):
        return SizingResult(qty=0, rejected=True,
                            reasons=[f"invalid product: {product!r}; must be 'INTRADAY', 'DELIVERY' or 'CRYPTO'"],
                            stop_distance=0.0, risk_amount=0.0, expected_loss=0.0)

    if atr < 0:
        return SizingResult(qty=0, rejected=True,
                            reasons=[f"atr must be non-negative, got {atr}"],
                            stop_distance=0.0, risk_amount=0.0, expected_loss=0.0)

    if current_symbol_exposure < 0:
        return SizingResult(qty=0, rejected=True,
                            reasons=[f"current_symbol_exposure must be non-negative, got {current_symbol_exposure}"],
                            stop_distance=0.0, risk_amount=0.0, expected_loss=0.0)

    if current_total_exposure < 0:
        return SizingResult(qty=0, rejected=True,
                            reasons=[f"current_total_exposure must be non-negative, got {current_total_exposure}"],
                            stop_distance=0.0, risk_amount=0.0, expected_loss=0.0)

    # 1. Stop distance with absolute floor
    stop_distance = max(atr * indi_cfg.atr_multiplier, indi_cfg.min_stop_pct * price)

    # 2. Risk per trade
    risk_amount = equity * risk_cfg.risk_per_trade_pct / 100

    # 3. Per-symbol notional cap
    symbol_cap_total     = equity * risk_cfg.max_symbol_notional_pct / 100
    if getattr(risk_cfg, "max_symbol_notional_inr", None) is not None:
        symbol_cap_total = min(symbol_cap_total, risk_cfg.max_symbol_notional_inr)
    elif product == "CRYPTO":
        symbol_cap_total = min(symbol_cap_total, 5_000.0)
    symbol_cap_remaining = max(0.0, symbol_cap_total - current_symbol_exposure)

    # 4. Total exposure cap
    total_cap_total      = equity * risk_cfg.max_total_exposure_pct / 100
    if getattr(risk_cfg, "max_total_notional_inr", None) is not None:
        total_cap_total = min(total_cap_total, risk_cfg.max_total_notional_inr)
    total_cap_remaining  = max(0.0, total_cap_total - current_total_exposure)

    # Quantize qty differently per product:
    #   INTRADAY / DELIVERY  → integer floor (NSE doesn't trade fractional shares)
    #   CRYPTO               → floor to fee_cfg.crypto_qty_step (e.g. 0.0001 BTC)
    qty_step = getattr(fee_cfg, "crypto_qty_step", 0.0001) if product == "CRYPTO" else 1.0

    def _floor_step(x: float, step: float) -> float:
        if step <= 0:
            return float(int(x))
        return (int(x / step)) * step

    qty_by_risk   = _floor_step(risk_amount / stop_distance, qty_step) if stop_distance > 0 else 0.0
    qty_by_symbol = _floor_step(symbol_cap_remaining / price, qty_step) if price > 0 else 0.0
    qty_by_total  = _floor_step(total_cap_remaining  / price, qty_step) if price > 0 else 0.0

    qty = min(qty_by_risk, qty_by_symbol, qty_by_total)
    qty = max(0.0, qty)
    initial_qty = qty

    # Minimum notional gate (per asset class)
    if product == "CRYPTO":
        min_notional = getattr(fee_cfg, "crypto_min_notional_inr", 500.0)
    else:
        min_notional = getattr(fee_cfg, "equity_min_notional_inr", 1.0)

    metrics = {
        "stop_distance":                   round(stop_distance, 4),
        "risk_amount":                     round(risk_amount,   2),
        "qty_by_risk":                     qty_by_risk,
        "qty_by_symbol":                   qty_by_symbol,
        "qty_by_total":                    qty_by_total,
        "symbol_cap_remaining":            round(symbol_cap_remaining, 2),
        "total_cap_remaining":             round(total_cap_remaining,  2),
        "initial_qty_before_cost_reduction": initial_qty,
        "final_qty":                       0,
        "qty_reduced_for_costs":           0,
        "stop_loss_component":             0.0,
        "charges_component":               0.0,
        "slippage_component":              0.0,
    }

    # Reject if qty is below smallest tradeable unit OR notional < min
    notional = qty * price
    if qty < qty_step or notional < min_notional:
        if qty_by_risk   < qty_step: reasons.append(f"risk cap: qty_by_risk={qty_by_risk}")
        if qty_by_symbol < qty_step: reasons.append(f"symbol notional cap exhausted "
                                                    f"(remaining Rs.{symbol_cap_remaining:.0f})")
        if qty_by_total  < qty_step: reasons.append(f"total exposure cap exhausted "
                                                    f"(remaining Rs.{total_cap_remaining:.0f})")
        if 0 < qty < qty_step:
            reasons.append(f"qty {qty} below min step {qty_step}")
        if 0 < notional < min_notional:
            reasons.append(f"notional Rs.{notional:.2f} below min Rs.{min_notional:.2f}")
        return SizingResult(qty=0.0, rejected=True, reasons=reasons,
                            stop_distance=stop_distance, risk_amount=risk_amount,
                            expected_loss=0.0, metrics=metrics)

    # 5. Validate expected loss including charges + slippage; reduce qty as needed
    if product == "INTRADAY":
        slip_bps = fee_cfg.intraday_slippage_bps
    elif product == "DELIVERY":
        slip_bps = fee_cfg.delivery_slippage_bps
    else:  # CRYPTO
        slip_bps = fee_cfg.crypto_slippage_bps
    while qty >= qty_step:
        rt_charges  = round_trip_cost(price, qty, product)
        rt_slippage = _round_trip_slippage(price, qty, slip_bps)
        expected_loss = qty * stop_distance + rt_charges + rt_slippage
        if expected_loss <= risk_amount:
            break
        qty = round(qty - qty_step, 8)
        if qty * price < min_notional:
            qty = 0.0
            break

    if qty < qty_step:
        # Even the minimum trade size's costs exceed the risk budget — reject
        rt_charges_1  = round_trip_cost(price, qty_step, product)
        rt_slippage_1 = _round_trip_slippage(price, qty_step, slip_bps)
        expected_loss_1 = qty_step * stop_distance + rt_charges_1 + rt_slippage_1
        reasons.append(
            f"expected loss for qty={qty_step} (Rs.{expected_loss_1:.2f}) "
            f"exceeds risk_amount (Rs.{risk_amount:.2f}) after fees/slippage"
        )
        metrics["expected_loss_for_min_qty"] = round(expected_loss_1, 2)
        return SizingResult(qty=0.0, rejected=True, reasons=reasons,
                            stop_distance=stop_distance, risk_amount=risk_amount,
                            expected_loss=expected_loss_1, metrics=metrics)

    metrics["expected_loss"]                 = round(expected_loss, 2)
    metrics["rt_charges_used"]               = round(rt_charges,    2)
    metrics["rt_slippage_used"]              = round(rt_slippage,   2)
    metrics["final_qty"]                     = qty
    metrics["qty_reduced_for_costs"]         = initial_qty - qty
    metrics["stop_loss_component"]           = round(qty * stop_distance, 2)
    metrics["charges_component"]             = round(rt_charges, 2)
    metrics["slippage_component"]            = round(rt_slippage, 2)

    return SizingResult(qty=qty, rejected=False, reasons=[],
                        stop_distance=stop_distance, risk_amount=risk_amount,
                        expected_loss=expected_loss, metrics=metrics)


# ── Cap enforcement ───────────────────────────────────────────────────────────
def check_all_caps(
    portfolio:        Portfolio,
    prices:           Dict[str, float],
    day_start_equity: float,
    risk_cfg:         RiskConfig,
) -> CapsCheckResult:
    """
    Aggregate cap check. Fail-closed if portfolio equity cannot be computed.
    Returns structured result with reasons + metrics.
    """
    reasons: List[str] = []
    metrics: Dict[str, float] = {}

    # Fail closed on missing prices
    try:
        equity = portfolio.equity(prices)
    except MissingPriceError as e:
        return CapsCheckResult(
            can_trade=False,
            reasons=[f"missing market price(s) for {sorted(e.missing)} — fail closed"],
            metrics={},
        )

    metrics["equity"]            = equity
    metrics["open_positions"]    = len(portfolio.state.positions)
    metrics["day_start_equity"]  = day_start_equity

    # Daily loss
    if day_start_equity > 0:
        daily_loss_pct = max(0.0, (day_start_equity - equity) / day_start_equity * 100)
        metrics["daily_loss_pct"] = round(daily_loss_pct, 4)
        if daily_loss_pct >= risk_cfg.max_daily_loss_pct:
            reasons.append(
                f"daily loss {daily_loss_pct:.2f}% >= max {risk_cfg.max_daily_loss_pct}%"
            )

    # Drawdown (uses portfolio peak vs current equity)
    try:
        dd_pct = portfolio.drawdown_pct(prices)
    except MissingPriceError as e:
        return CapsCheckResult(
            can_trade=False,
            reasons=[f"can't compute drawdown — missing prices {sorted(e.missing)}"],
            metrics=metrics,
        )
    metrics["drawdown_pct"] = round(dd_pct, 4)
    if dd_pct >= risk_cfg.max_drawdown_pct:
        reasons.append(f"drawdown {dd_pct:.2f}% >= max {risk_cfg.max_drawdown_pct}%")

    # Max open positions
    open_count = len(portfolio.state.positions)
    if open_count >= risk_cfg.max_open_positions:
        reasons.append(
            f"max_open_positions reached ({open_count}/{risk_cfg.max_open_positions})"
        )

    # Gross exposure cap
    try:
        gross_exposure = portfolio.gross_exposure(prices)
    except MissingPriceError as e:
        return CapsCheckResult(
            can_trade=False,
            reasons=[f"can't compute gross exposure — missing prices {sorted(e.missing)}"],
            metrics=metrics,
        )
    gross_exposure_pct = (gross_exposure / equity * 100) if equity > 0 else 0.0
    metrics["gross_exposure"]     = round(gross_exposure, 2)
    metrics["gross_exposure_pct"] = round(gross_exposure_pct, 4)
    if gross_exposure_pct >= risk_cfg.max_total_exposure_pct:
        reasons.append(
            f"gross exposure {gross_exposure_pct:.2f}% >= max_total_exposure_pct "
            f"{risk_cfg.max_total_exposure_pct}%"
        )
    if getattr(risk_cfg, "max_total_notional_inr", None) is not None:
        metrics["max_total_notional_inr"] = round(risk_cfg.max_total_notional_inr, 2)
        if gross_exposure >= risk_cfg.max_total_notional_inr:
            reasons.append(
                f"gross exposure Rs.{gross_exposure:.2f} >= max_total_notional_inr "
                f"Rs.{risk_cfg.max_total_notional_inr:.2f}"
            )

    # Per-symbol exposure cap
    for sym, pos in portfolio.state.positions.items():
        symbol_value = pos.qty * prices[sym]
        symbol_exposure_pct = (symbol_value / equity * 100) if equity > 0 else 0.0
        metrics[f"symbol_exposure_pct[{sym}]"] = round(symbol_exposure_pct, 4)
        if symbol_exposure_pct >= risk_cfg.max_symbol_notional_pct:
            reasons.append(
                f"{sym} exposure {symbol_exposure_pct:.2f}% >= max_symbol_notional_pct "
                f"{risk_cfg.max_symbol_notional_pct}%"
            )
        if getattr(risk_cfg, "max_symbol_notional_inr", None) is not None:
            metrics[f"symbol_exposure[{sym}]"] = round(symbol_value, 2)
            if symbol_value >= risk_cfg.max_symbol_notional_inr:
                reasons.append(
                    f"{sym} exposure Rs.{symbol_value:.2f} >= max_symbol_notional_inr "
                    f"Rs.{risk_cfg.max_symbol_notional_inr:.2f}"
                )

    return CapsCheckResult(can_trade=len(reasons) == 0, reasons=reasons, metrics=metrics)


# ── Entry gate (BUY only — never consulted on exits) ──────────────────────────
def is_entry_allowed(
    portfolio:        Portfolio,
    prices:           Dict[str, float],
    day_start_equity: float,
    risk_cfg:         RiskConfig,
) -> EntryGateResult:
    """
    Gate for NEW BUY entries. Combines:
      - Operational control flags (kill switch, pause) from bot.control
      - All portfolio caps from check_all_caps()

    MUST NOT be called on the exit path. Exits (SELL, stop-loss, target,
    flatten, kill-switch liquidation) are always allowed so that existing
    risk can be unwound.
    """
    reasons: List[str] = []

    control = _read_control_state()
    if not control.can_enter():
        block = control.block_reason()
        if block:
            reasons.append(block)

    caps = check_all_caps(portfolio, prices, day_start_equity, risk_cfg)
    if not caps.can_trade:
        reasons.extend(caps.reasons)

    return EntryGateResult(
        can_enter=len(reasons) == 0,
        reasons=reasons,
        caps=caps,
    )
