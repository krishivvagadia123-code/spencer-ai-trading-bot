"""
Engine — orchestrates Portfolio + charges + risk + execution_sim + control + monitor.

Pure-ish functions: each accepts a `quote_provider: Callable[[str], Quote]` so
unit tests inject synthetic quotes without touching yfinance.

Invariant (Phase D/E):
  - BUY  → goes through is_entry_allowed() → caps + kill + pause.
  - SELL / STOP / TARGET / FLATTEN → bypass ALL gates.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from bot.charges import Product
from bot.config import (
    BotConfig, FeeConfig, IndicatorConfig, MarketConfig, RiskConfig,
)
from bot.execution_sim import Fill, simulate_fill
from bot.market_data import Quote
from bot.monitor import ExitDecision, ExitReason, check_exits, flatten_all
from bot.portfolio import MissingPriceError, Portfolio, Position, PortfolioState
from bot.risk import calculate_position_size, is_entry_allowed


QuoteProvider = Callable[[str], Optional[Quote]]


# ── Result types ─────────────────────────────────────────────────────────────
@dataclass
class BuyResult:
    rejected:  bool
    reasons:   List[str] = field(default_factory=list)
    fill:      Optional[Fill] = None
    position:  Optional[Position] = None


@dataclass
class SellResult:
    rejected:    bool
    reasons:     List[str]   = field(default_factory=list)
    fill:        Optional[Fill] = None
    exit_reason: str         = "MANUAL"
    net_pnl:     float       = 0.0


# ── State persistence ────────────────────────────────────────────────────────
def serialize_portfolio(pf: Portfolio) -> dict:
    return pf.state.model_dump(mode="json")


def deserialize_portfolio(raw: dict) -> Portfolio:
    return Portfolio(PortfolioState.model_validate(raw))


# ── BUY (gated) ──────────────────────────────────────────────────────────────
def do_buy(
    symbol:           str,
    portfolio:        Portfolio,
    quote_provider:   QuoteProvider,
    *,
    day_start_equity: float,
    risk_cfg:         RiskConfig,
    indi_cfg:         IndicatorConfig,
    fee_cfg:          FeeConfig,
    atr:              float,
    product:          Product = "INTRADAY",
) -> BuyResult:
    """
    Place a paper BUY. Goes through is_entry_allowed (caps + kill + pause).
    NEVER bypasses gates — entries must respect operational state.
    """
    if symbol in portfolio.state.positions:
        return BuyResult(rejected=True, reasons=[f"already holding {symbol}"])

    quote = quote_provider(symbol)
    if quote is None:
        return BuyResult(rejected=True, reasons=[f"no quote available for {symbol}"])
    if not quote.is_usable:
        return BuyResult(rejected=True,
                         reasons=[f"unusable quote: {quote.reject_reason}"])

    # Build the price map for cap checks — current positions + the candidate
    prices: Dict[str, float] = {symbol: quote.price}
    for sym in portfolio.state.positions:
        if sym == symbol:
            continue
        q = quote_provider(sym)
        if q is None or not q.is_usable:
            return BuyResult(rejected=True,
                             reasons=[f"can't price open position {sym} — fail closed"])
        prices[sym] = q.price

    gate = is_entry_allowed(portfolio, prices=prices,
                            day_start_equity=day_start_equity, risk_cfg=risk_cfg)
    if not gate.can_enter:
        return BuyResult(rejected=True, reasons=gate.reasons)

    # Sizing
    try:
        current_total_exposure = portfolio.gross_exposure(prices) \
            if portfolio.state.positions else 0.0
    except MissingPriceError as e:
        return BuyResult(rejected=True,
                         reasons=[f"missing prices: {sorted(e.missing)}"])

    sizing = calculate_position_size(
        equity=portfolio.equity(prices),
        price=quote.price,
        atr=atr,
        current_symbol_exposure=0.0,
        current_total_exposure=current_total_exposure,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        product=product,
    )
    if sizing.rejected:
        return BuyResult(rejected=True, reasons=sizing.reasons)

    # Simulate the fill
    fill = simulate_fill(quote, "BUY", sizing.qty, fee_cfg, product=product)
    if not fill.is_executed:
        return BuyResult(rejected=True,
                         reasons=[f"fill rejected: {fill.reject_reason}"])

    cost = round(fill.fill_price * fill.qty + (fill.charges.total if fill.charges else 0), 2)
    if cost > portfolio.state.cash:
        return BuyResult(rejected=True,
                         reasons=[f"cost Rs.{cost:.2f} exceeds cash Rs.{portfolio.state.cash:.2f}"])

    position = Position(
        symbol=symbol, qty=fill.qty, entry_price=fill.fill_price,
        stop=round(fill.fill_price - sizing.stop_distance, 2),
        target=round(fill.fill_price + sizing.stop_distance * 1.5, 2),  # 1.5R default
        charges_buy=fill.charges.total if fill.charges else 0.0,
        entry_time=datetime.now(),
    )
    portfolio.add_position(position, cost=cost)
    portfolio.update_peak(prices)
    return BuyResult(rejected=False, fill=fill, position=position)


# ── SELL (ungated — always allowed) ──────────────────────────────────────────
def _execute_sell(
    symbol:          str,
    portfolio:       Portfolio,
    quote:           Quote,
    fee_cfg:         FeeConfig,
    product:         Product,
    exit_reason:     str,
) -> SellResult:
    """Shared sell path. NEVER consults caps/kill/pause — exits are sacred."""
    if symbol not in portfolio.state.positions:
        return SellResult(rejected=True, reasons=[f"no position in {symbol}"],
                          exit_reason=exit_reason)
    if not quote.is_usable:
        return SellResult(rejected=True,
                          reasons=[f"unusable quote: {quote.reject_reason}"],
                          exit_reason=exit_reason)

    pos = portfolio.state.positions[symbol]
    fill = simulate_fill(quote, "SELL", pos.qty, fee_cfg, product=product)
    if not fill.is_executed:
        return SellResult(rejected=True,
                          reasons=[f"fill rejected: {fill.reject_reason}"],
                          exit_reason=exit_reason)

    sell_charges = fill.charges.total if fill.charges else 0.0
    net_pnl = portfolio.close_position(symbol, fill.fill_price, sell_charges)
    return SellResult(rejected=False, fill=fill,
                      exit_reason=exit_reason, net_pnl=net_pnl)


def do_sell(
    symbol:         str,
    portfolio:      Portfolio,
    quote_provider: QuoteProvider,
    *,
    fee_cfg:        FeeConfig,
    product:        Product = "INTRADAY",
    exit_reason:    str = "MANUAL",
) -> SellResult:
    """Manual SELL. Bypasses all gates — exits are always allowed."""
    quote = quote_provider(symbol)
    if quote is None:
        return SellResult(rejected=True, reasons=[f"no quote for {symbol}"],
                          exit_reason=exit_reason)
    return _execute_sell(symbol, portfolio, quote, fee_cfg, product, exit_reason)


# ── FLATTEN (ungated emergency liquidation) ──────────────────────────────────
def do_flatten(
    portfolio:      Portfolio,
    quote_provider: QuoteProvider,
    *,
    fee_cfg:        FeeConfig,
    product:        Product = "INTRADAY",
) -> List[SellResult]:
    """
    Close every open position via paper SELL. Bypasses caps/kill/pause.
    Missing-quote symbols are reported as rejected results (still no broker call).
    """
    results: List[SellResult] = []
    # Snapshot symbol list — close_position mutates portfolio.state.positions
    for symbol in list(portfolio.state.positions.keys()):
        quote = quote_provider(symbol)
        if quote is None:
            results.append(SellResult(rejected=True,
                                      reasons=[f"no quote for {symbol}"],
                                      exit_reason="FLATTEN"))
            continue
        results.append(_execute_sell(symbol, portfolio, quote, fee_cfg, product,
                                     exit_reason="FLATTEN"))
    return results


# ── MONITOR-ONCE (scheduler-safe single pass) ────────────────────────────────
def do_monitor_once(
    portfolio:      Portfolio,
    quote_provider: QuoteProvider,
    *,
    fee_cfg:        FeeConfig,
    product:        Product = "INTRADAY",
) -> List[SellResult]:
    """
    One-shot pass: price every open position, detect stop/target hits,
    execute paper SELL for each. Designed for cron / Task Scheduler.

    Paper-only — never places a real broker order. Bypasses caps/kill/pause.
    """
    if not portfolio.state.positions:
        return []

    prices: Dict[str, float] = {}
    quote_cache: Dict[str, Quote] = {}
    missing_results: List[SellResult] = []

    for symbol in portfolio.state.positions:
        q = quote_provider(symbol)
        if q is None or not q.is_usable:
            reason = (q.reject_reason if q is not None else "no quote")
            missing_results.append(SellResult(
                rejected=True,
                reasons=[f"no usable quote for {symbol}: {reason}"],
                exit_reason="MONITOR_MISSING",
            ))
            continue
        prices[symbol]      = q.price
        quote_cache[symbol] = q

    report = check_exits(portfolio, prices)
    results: List[SellResult] = list(missing_results)

    for decision in report.exits:
        quote = quote_cache[decision.symbol]
        results.append(_execute_sell(
            decision.symbol, portfolio, quote, fee_cfg, product,
            exit_reason=decision.reason.value,
        ))
    return results
