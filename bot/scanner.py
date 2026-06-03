"""
Intraday scanner — orchestrates research cache + technicals + risk preview
into a list of SignalCandidate rows.

GUARANTEE: this module never executes a BUY or SELL. It is signal-only.
GUARANTEE: this module never calls an LLM. Research caching ensures the
external research provider runs at most once per (symbol, asof) per day.

Inputs are explicit and injectable (so tests can substitute stubs):
  - watchlist            : iterable[str]
  - technical_provider   : Callable[[str], TechnicalSnapshot]
  - research_provider    : ResearchProvider protocol
  - portfolio, risk_cfg, indi_cfg, fee_cfg, day_start_equity

For each symbol the scanner:
  1. Loads (or fetches once) today's research snapshot.
  2. Pulls a TechnicalSnapshot from technical_provider.
  3. Runs is_entry_allowed() with prices it can gather → entry_blocked + reasons.
  4. Computes a SizingPreview via calculate_position_size (no order placed).
  5. Builds a SignalCandidate and persists it to signal_candidates.

Returns the list of candidates so the engine layer can render the dashboard.
"""

from __future__ import annotations
import json
from datetime import date, datetime
from typing import Callable, Dict, Iterable, List, Optional

from bot.charges import Product
from bot.config import FeeConfig, IndicatorConfig, RiskConfig
from bot.db import get_conn
from bot.logger_config import get_logger
from bot.portfolio import Portfolio
from bot.research import (
    NeutralResearchProvider, ResearchProvider, get_or_fetch,
)
from bot.risk import calculate_position_size, is_entry_allowed
from bot.signals import (
    SignalCandidate, SizingPreview, TechnicalSnapshot, build_candidate,
)

log = get_logger("kite-bot.scanner")

TechnicalProvider = Callable[[str], Optional[TechnicalSnapshot]]


# ── DB write ─────────────────────────────────────────────────────────────────
def _persist(candidate: SignalCandidate) -> None:
    row = candidate.as_log_row()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO signal_candidates "
            "(ts, symbol, signal, total_score, technical_score, sentiment_score, "
            " fundamentals_score, liquidity_score, risk_score, indicators, "
            " research_snapshot_id, entry_blocked, block_reasons, sizing_preview, "
            " rejection_reason) "
            "VALUES (:ts, :symbol, :signal, :total_score, :technical_score, "
            ":sentiment_score, :fundamentals_score, :liquidity_score, :risk_score, "
            ":indicators, :research_snapshot_id, :entry_blocked, :block_reasons, "
            ":sizing_preview, :rejection_reason)",
            row,
        )


def list_recent_candidates(limit: int = 100) -> List[dict]:
    """Read-only: latest candidates for dashboard rendering."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT ts, symbol, signal, total_score, technical_score, "
            "       sentiment_score, fundamentals_score, liquidity_score, "
            "       risk_score, entry_blocked, block_reasons, rejection_reason "
            "FROM signal_candidates ORDER BY id DESC LIMIT ?", (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Helpers ──────────────────────────────────────────────────────────────────
def _sizing_preview(
    *, equity: float, tech: TechnicalSnapshot,
    current_symbol_exposure: float, current_total_exposure: float,
    risk_cfg: RiskConfig, indi_cfg: IndicatorConfig, fee_cfg: FeeConfig,
    product: Product = "INTRADAY",
) -> SizingPreview:
    atr = tech.atr if tech.atr is not None else 0.0
    s = calculate_position_size(
        equity=equity, price=tech.price, atr=atr,
        current_symbol_exposure=current_symbol_exposure,
        current_total_exposure=current_total_exposure,
        risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
        product=product,
    )
    return SizingPreview(
        qty=s.qty, stop_distance=s.stop_distance,
        expected_loss=s.expected_loss, rejected=s.rejected,
        reasons=list(s.reasons),
    )


def _gather_prices_for_open_positions(
    portfolio: Portfolio, technical_provider: TechnicalProvider,
    fallback_price_for: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Best-effort price gathering for the entry-gate's cap checks.
    Falls back to entry_price for any open position whose technical is
    missing — risk caps work in degraded mode but we never silently skip
    a price (entry-gate also enforces its own missing-price fail-closed).
    """
    prices: Dict[str, float] = {}
    fallback = fallback_price_for or {}
    for sym in portfolio.state.positions:
        if sym in fallback:
            prices[sym] = fallback[sym]
            continue
        snap = technical_provider(sym)
        if snap is not None:
            prices[sym] = snap.price
        else:
            prices[sym] = portfolio.state.positions[sym].entry_price
    return prices


# ── Main entry point ─────────────────────────────────────────────────────────
def scan_once(
    *,
    portfolio:          Portfolio,
    watchlist:          Iterable[str],
    technical_provider: TechnicalProvider,
    research_provider:  ResearchProvider = None,
    risk_cfg:           RiskConfig,
    indi_cfg:           IndicatorConfig,
    fee_cfg:            FeeConfig,
    day_start_equity:   float,
    asof:               Optional[date] = None,
    product:            Product = "INTRADAY",
) -> List[SignalCandidate]:
    """
    One scan pass. Returns SignalCandidate per watched symbol.
    Persists each candidate to signal_candidates table.

    No order placement. No LLM calls. No buys.
    """
    research_provider = research_provider or NeutralResearchProvider()
    asof = asof or date.today()
    candidates: List[SignalCandidate] = []
    now = datetime.now()

    for symbol in watchlist:
        tech = technical_provider(symbol)
        if tech is None:
            log.warning(f"scan {symbol}: no technical snapshot — skipping")
            continue

        # 1. Cached daily research (fetched at most once per symbol/day)
        snapshot = get_or_fetch(symbol, asof, research_provider)

        # 2. Entry-gate evaluation (BUY-only; never modifies portfolio)
        prices = _gather_prices_for_open_positions(
            portfolio, technical_provider,
            fallback_price_for={symbol: tech.price},
        )
        prices[symbol] = tech.price
        gate = is_entry_allowed(
            portfolio, prices=prices,
            day_start_equity=day_start_equity, risk_cfg=risk_cfg,
        )
        entry_blocked = not gate.can_enter
        block_reasons = list(gate.reasons)

        # 3. Risk sizing preview (no order placed)
        try:
            equity = portfolio.equity(prices) if portfolio.state.positions \
                     else portfolio.state.cash
        except Exception:
            equity = portfolio.state.cash
        current_symbol_exp = 0.0
        if symbol in portfolio.state.positions:
            pos = portfolio.state.positions[symbol]
            current_symbol_exp = pos.qty * tech.price
        current_total_exp = sum(
            pos.qty * prices.get(s, pos.entry_price)
            for s, pos in portfolio.state.positions.items()
        )
        sizing = _sizing_preview(
            equity=equity, tech=tech,
            current_symbol_exposure=current_symbol_exp,
            current_total_exposure=current_total_exp,
            risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
            product=product,
        )

        # 4. Build + persist candidate
        candidate = build_candidate(
            ts=now, symbol=symbol, tech=tech,
            fundamentals_score=snapshot.fundamentals_score,
            sentiment_score=snapshot.sentiment_score,
            liquidity_score=snapshot.liquidity_score,
            has_position=symbol in portfolio.state.positions,
            entry_blocked=entry_blocked,
            block_reasons=block_reasons,
            research_snapshot_id=snapshot.id,
            sizing_preview=sizing,
            rejection_reason=(
                "; ".join(block_reasons) if entry_blocked and block_reasons
                else ("entry_blocked" if entry_blocked else None)
            ),
        )
        _persist(candidate)
        candidates.append(candidate)

    return candidates
