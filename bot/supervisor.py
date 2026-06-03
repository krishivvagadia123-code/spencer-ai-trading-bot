"""
Supervisor — the run-all loop. Crash-resistant, paper-only.

Each iteration is a pure function of (now, last_*_ts, config). The interactive
forever-loop is a thin wrapper around `run_iteration()` so tests can drive a
single tick without sleeping or threading.

What it does on each tick:
  1. monitor_once  — auto-exit stops/targets (NEVER gated)
  2. scan_once     — generate signal candidates
  3. auto_buy_once — for top BUY_CANDIDATEs, place a PAPER buy with cooldown
  4. refresh_dashboard
  5. heartbeat to logs

What it MUST NOT do:
  - place real broker orders (paper only — uses engine.do_buy → execution_sim)
  - call an LLM in the loop
  - silently swallow errors without logging
  - crash the process on a single iteration error
"""

from __future__ import annotations
import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from bot import control
from bot.charges import Product
from bot.config import (
    BotConfig, FeeConfig, IndicatorConfig, RiskConfig, SupervisorConfig,
)
from bot.db import save_state, load_state, log_trade as db_log_trade
from bot.engine import BuyResult, do_buy, do_monitor_once
from bot.logger_config import get_logger
from bot.market_data import Quote
from bot.portfolio import Portfolio
from bot.research import NeutralResearchProvider, ResearchProvider
from bot.scanner import scan_once
from bot.signals import Signal, SignalCandidate, TechnicalSnapshot

log = get_logger("kite-bot.supervisor")

# Type aliases
QuoteProvider     = Callable[[str], Optional[Quote]]
TechnicalProvider = Callable[[str], Optional[TechnicalSnapshot]]


# ── State carried between ticks ──────────────────────────────────────────────
@dataclass
class LoopState:
    last_monitor_ts:    float = 0.0
    last_scan_ts:       float = 0.0
    last_auto_buy_ts:   float = 0.0
    last_dashboard_ts:  float = 0.0
    last_heartbeat_ts:  float = 0.0
    last_candidates:    List[SignalCandidate] = field(default_factory=list)
    iterations:         int = 0
    errors:             int = 0


# ── Auto-buy gates (paper only) ──────────────────────────────────────────────
@dataclass
class AutoBuyDecision:
    symbol:    str
    placed:    bool
    reason:    str
    result:    Optional[BuyResult] = None


def _log_supervisor_trade(row: dict) -> None:
    try:
        db_log_trade(row)
    except Exception as e:
        log.warning(f"supervisor trade audit log failed: {e}")


def _log_auto_buy(candidate: SignalCandidate, result: BuyResult,
                  portfolio: Portfolio) -> None:
    if result.fill is None or result.position is None:
        return
    fill = result.fill
    pos = result.position
    strategy = load_state("selected_strategy", "equity_vwap_breakout")
    snapshot = candidate.as_log_row()
    snapshot["active_strategy"] = strategy
    _log_supervisor_trade({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": candidate.symbol,
        "action": "BUY",
        "price": fill.fill_price,
        "qty": fill.qty,
        "value": round(fill.fill_price * fill.qty, 2),
        "charges": fill.charges.total if fill.charges else 0.0,
        "stop": pos.stop,
        "target": pos.target,
        "pnl": None,
        "balance_after": portfolio.state.cash,
        "entry_reason": f"AUTO strategy={strategy} score={candidate.scores.total:.3f}",
        "exit_reason": None,
        "signal_snapshot": json.dumps(snapshot, default=str),
        "slippage": fill.total_slippage,
        "equity_after": None,
    })


def _log_auto_sell(result, portfolio: Portfolio, stop=None, target=None) -> None:
    if result.rejected or result.fill is None:
        return
    fill = result.fill
    _log_supervisor_trade({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": fill.symbol,
        "action": "SELL",
        "price": fill.fill_price,
        "qty": fill.qty,
        "value": round(fill.fill_price * fill.qty, 2),
        "charges": fill.charges.total if fill.charges else 0.0,
        "stop": stop,
        "target": target,
        "pnl": result.net_pnl,
        "balance_after": portfolio.state.cash,
        "entry_reason": None,
        "exit_reason": result.exit_reason,
        "signal_snapshot": None,
        "slippage": fill.total_slippage,
        "equity_after": None,
    })


def _load_cooldowns() -> Dict[str, float]:
    raw = load_state("auto_buy_cooldowns") or {}
    return {k: float(v) for k, v in raw.items()}


def _save_cooldowns(c: Dict[str, float]) -> None:
    save_state("auto_buy_cooldowns", c)


def _is_in_cooldown(symbol: str, cooldowns: Dict[str, float],
                    now: float, cooldown_sec: int) -> bool:
    """Symbols not in the cooldown map are NOT in cooldown."""
    if symbol not in cooldowns:
        return False
    return (now - cooldowns[symbol]) < cooldown_sec


def _sizing_preview_is_usable(candidate: SignalCandidate, fee_cfg: FeeConfig,
                              product: Product) -> tuple[bool, str]:
    """
    Product-aware final sanity check for scanner sizing.

    Equities still require whole-share qty >= 1. Legacy fractional products
    must clear the configured minimum notional.
    """
    sizing = candidate.sizing_preview
    if sizing is None:
        return False, "no sizing"
    if sizing.rejected:
        return False, "; ".join(sizing.reasons) or "sizing rejected"

    qty = float(sizing.qty)
    price = float(candidate.indicators.get("price") or 0.0)
    if qty <= 0:
        return False, f"qty {qty:g} <= 0"
    if product == "CRYPTO":
        notional = qty * price
        min_notional = getattr(fee_cfg, "crypto_min_notional_inr", 500.0)
        if notional < min_notional:
            return False, (
                f"notional Rs.{notional:.2f} below min Rs.{min_notional:.2f}"
            )
        return True, ""

    if qty < 1:
        return False, f"qty {qty:g} < 1"
    return True, ""


def auto_buy_once(
    *,
    candidates:       List[SignalCandidate],
    portfolio:        Portfolio,
    quote_provider:   QuoteProvider,
    risk_cfg:         RiskConfig,
    indi_cfg:         IndicatorConfig,
    fee_cfg:          FeeConfig,
    sup_cfg:          SupervisorConfig,
    day_start_equity: float,
    now:              Optional[float] = None,
    product:          Product = "INTRADAY",
) -> List[AutoBuyDecision]:
    """
    Try to auto-buy the highest-scoring BUY_CANDIDATEs.
    Every BUY goes through engine.do_buy (which routes through
    is_entry_allowed → caps + kill + pause). Paper only.

    Gates applied here, before do_buy:
      - signal must be BUY_CANDIDATE
      - total_score >= sup_cfg.min_total_score_to_buy
      - candidate freshness (max_signal_age_sec)
      - per-symbol cooldown
      - never average down (already holding rejects)
      - control state (paused/killed) — let do_buy enforce, but log here too
    """
    now = now if now is not None else time.time()
    decisions: List[AutoBuyDecision] = []
    cooldowns = _load_cooldowns()

    # Rank by total_score descending — try strongest first
    ranked = sorted(
        [c for c in candidates if c.signal == Signal.BUY_CANDIDATE],
        key=lambda c: c.scores.total, reverse=True,
    )
    if not ranked:
        return decisions

    state = control.read_state()
    if state.killed or state.paused:
        # Don't even try — but log every candidate as rejected for audit
        reason = state.block_reason() or "control flag set"
        for c in ranked:
            decisions.append(AutoBuyDecision(c.symbol, False, f"control: {reason}"))
        return decisions

    for c in ranked:
        if c.symbol in portfolio.state.positions:
            decisions.append(AutoBuyDecision(c.symbol, False,
                                              "already holding (no averaging down)"))
            continue
        if c.scores.total < sup_cfg.min_total_score_to_buy:
            decisions.append(AutoBuyDecision(c.symbol, False,
                                              f"score {c.scores.total:.2f} < threshold {sup_cfg.min_total_score_to_buy}"))
            continue
        age = (datetime.now() - c.ts).total_seconds()
        if age > sup_cfg.max_signal_age_sec:
            decisions.append(AutoBuyDecision(c.symbol, False,
                                              f"stale signal: {age:.0f}s > {sup_cfg.max_signal_age_sec}s"))
            continue
        if _is_in_cooldown(c.symbol, cooldowns, now, sup_cfg.cooldown_sec_per_symbol):
            wait = sup_cfg.cooldown_sec_per_symbol - (now - cooldowns[c.symbol])
            decisions.append(AutoBuyDecision(c.symbol, False,
                                              f"cooldown: {wait:.0f}s remaining"))
            continue
        sizing_ok, sizing_reason = _sizing_preview_is_usable(c, fee_cfg, product)
        if not sizing_ok:
            decisions.append(AutoBuyDecision(
                c.symbol, False, f"risk sizing rejected: {sizing_reason}",
            ))
            continue

        # Fresh quote check
        quote = quote_provider(c.symbol)
        if quote is None or not quote.is_usable:
            decisions.append(AutoBuyDecision(c.symbol, False,
                                              f"quote not fresh/usable: "
                                              f"{quote.reject_reason if quote else 'none'}"))
            continue

        # Delegate to engine.do_buy — this is the ONLY path to a position.
        # do_buy itself runs is_entry_allowed → caps + kill + pause.
        atr = c.indicators.get("atr") or 0.0
        result = do_buy(
            c.symbol, portfolio, quote_provider,
            day_start_equity=day_start_equity,
            risk_cfg=risk_cfg, indi_cfg=indi_cfg, fee_cfg=fee_cfg,
            atr=atr, product=product,
        )
        if result.rejected:
            decisions.append(AutoBuyDecision(
                c.symbol, False, f"do_buy rejected: {'; '.join(result.reasons)}",
                result=result,
            ))
            continue

        cooldowns[c.symbol] = now
        _save_cooldowns(cooldowns)
        _log_auto_buy(c, result, portfolio)
        decisions.append(AutoBuyDecision(c.symbol, True, "executed (paper)", result=result))
        log.info(f"AUTO-BUY (paper) {c.symbol} qty={result.fill.qty} "
                 f"@ Rs.{result.fill.fill_price}")

    return decisions


# ── Heartbeat / log helper ───────────────────────────────────────────────────
def write_heartbeat(log_dir: Path, state: LoopState, portfolio: Portfolio,
                    extra: Optional[dict] = None) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    hb_path = log_dir / "heartbeat.log"
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "iterations": state.iterations,
        "errors": state.errors,
        "cash": round(portfolio.state.cash, 2),
        "open_positions": len(portfolio.state.positions),
        "control": {
            "killed": control.is_killed(),
            "paused": control.is_paused(),
        },
    }
    if extra:
        payload.update(extra)
    save_state("last_heartbeat", payload)
    with open(hb_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
    return hb_path


# ── Single iteration (the testable unit) ─────────────────────────────────────
def run_iteration(
    *,
    state:              LoopState,
    portfolio:          Portfolio,
    save_portfolio:     Callable[[Portfolio], None],
    quote_provider:     QuoteProvider,
    technical_provider: TechnicalProvider,
    research_provider:  ResearchProvider,
    refresh_dashboard:  Callable[[Portfolio, Optional[Dict[str, float]]], None],
    watchlist:          List[str],
    cfg:                BotConfig,
    day_start_equity:   float,
    log_dir:            Path,
    now:                Optional[float] = None,
    product:            Product = "INTRADAY",
) -> dict:
    """
    Execute one tick. Returns a summary dict for tests/heartbeat.
    Errors in any sub-step are caught, logged, counted, and the tick continues.
    """
    now = now if now is not None else time.time()
    state.iterations += 1
    summary = {"monitor": 0, "scan": 0, "auto_buy": 0,
               "dashboard": False, "heartbeat": False, "errors": []}

    # 1. monitor exits (NEVER gated)
    if (now - state.last_monitor_ts) >= cfg.supervisor.monitor_interval_sec:
        try:
            exit_targets = {
                sym: (pos.stop, pos.target)
                for sym, pos in portfolio.state.positions.items()
            }
            results = do_monitor_once(portfolio, quote_provider, fee_cfg=cfg.fees,
                                       product=product)
            for r in results:
                sym = r.fill.symbol if (not r.rejected and r.fill) else None
                stop, target = exit_targets.get(sym, (None, None)) if sym else (None, None)
                _log_auto_sell(r, portfolio, stop=stop, target=target)
            save_portfolio(portfolio)
            summary["monitor"] = sum(1 for r in results if not r.rejected)
            state.last_monitor_ts = now
        except Exception as e:
            state.errors += 1
            summary["errors"].append(f"monitor: {e}")
            log.exception("monitor iteration failed; continuing")

    # 2. scan (signal-only)
    if (now - state.last_scan_ts) >= cfg.supervisor.scan_interval_sec:
        try:
            state.last_candidates = scan_once(
                portfolio=portfolio, watchlist=watchlist,
                technical_provider=technical_provider,
                research_provider=research_provider,
                risk_cfg=cfg.risk, indi_cfg=cfg.indicators, fee_cfg=cfg.fees,
                day_start_equity=day_start_equity, product=product,
            )
            summary["scan"] = len(state.last_candidates)
            state.last_scan_ts = now
        except Exception as e:
            state.errors += 1
            summary["errors"].append(f"scan: {e}")
            log.exception("scan iteration failed; continuing")

    # 3. auto-buy (delegates to engine.do_buy → paper only)
    if (now - state.last_auto_buy_ts) >= cfg.supervisor.auto_buy_interval_sec \
       and state.last_candidates:
        try:
            decisions = auto_buy_once(
                candidates=state.last_candidates,
                portfolio=portfolio, quote_provider=quote_provider,
                risk_cfg=cfg.risk, indi_cfg=cfg.indicators, fee_cfg=cfg.fees,
                sup_cfg=cfg.supervisor, day_start_equity=day_start_equity,
                now=now, product=product,
            )
            save_portfolio(portfolio)
            summary["auto_buy"] = sum(1 for d in decisions if d.placed)
            state.last_auto_buy_ts = now
        except Exception as e:
            state.errors += 1
            summary["errors"].append(f"auto_buy: {e}")
            log.exception("auto_buy iteration failed; continuing")

    # 4. dashboard (must NEVER crash the loop)
    if (now - state.last_dashboard_ts) >= cfg.supervisor.dashboard_interval_sec:
        try:
            refresh_dashboard(portfolio, None)
            summary["dashboard"] = True
            state.last_dashboard_ts = now
        except Exception as e:
            state.errors += 1
            summary["errors"].append(f"dashboard: {e}")
            log.exception("dashboard refresh failed; continuing")

    # 5. heartbeat
    if (now - state.last_heartbeat_ts) >= cfg.supervisor.heartbeat_interval_sec:
        try:
            write_heartbeat(log_dir, state, portfolio, extra={"summary": summary})
            summary["heartbeat"] = True
            state.last_heartbeat_ts = now
        except Exception as e:
            state.errors += 1
            summary["errors"].append(f"heartbeat: {e}")
            log.exception("heartbeat write failed; continuing")

    return summary


# ── Forever loop ─────────────────────────────────────────────────────────────
def run_forever(
    *,
    portfolio_loader:   Callable[[], Portfolio],
    save_portfolio:     Callable[[Portfolio], None],
    quote_provider:     QuoteProvider,
    technical_provider: TechnicalProvider,
    research_provider:  ResearchProvider,
    refresh_dashboard:  Callable[[Portfolio, Optional[Dict[str, float]]], None],
    watchlist_loader:   Callable[[], List[str]],
    cfg:                BotConfig,
    day_start_equity_loader: Callable[[Portfolio], float],
    log_dir:            Path,
    tick_seconds:       float = 5.0,
    product:            Product = "INTRADAY",
    max_loops:          Optional[int] = None,
) -> LoopState:
    """
    Run until Ctrl+C, or until `max_loops` iterations if provided.
    Each tick is delegated to run_iteration(). Never raises — every per-tick
    error is logged and the loop continues. Returns the final LoopState so
    tests / verification can assert iteration counts.
    """
    state = LoopState()
    log.info(f"supervisor starting (tick={tick_seconds}s, product={product}, "
             f"max_loops={max_loops})")
    try:
        while True:
            if max_loops is not None and state.iterations >= max_loops:
                log.info(f"max_loops={max_loops} reached, exiting cleanly")
                break
            try:
                pf = portfolio_loader()
                day_start = day_start_equity_loader(pf)
                summary = run_iteration(
                    state=state, portfolio=pf, save_portfolio=save_portfolio,
                    quote_provider=quote_provider,
                    technical_provider=technical_provider,
                    research_provider=research_provider,
                    refresh_dashboard=refresh_dashboard,
                    watchlist=watchlist_loader(),
                    cfg=cfg, day_start_equity=day_start,
                    log_dir=log_dir, product=product,
                )
                if any([summary["monitor"], summary["auto_buy"], summary["scan"]]):
                    log.info(f"tick #{state.iterations}: {summary}")
            except Exception as e:
                state.errors += 1
                log.exception(f"unexpected iteration error: {e}")
            time.sleep(tick_seconds)
    except KeyboardInterrupt:
        log.info("supervisor stopped by Ctrl+C (graceful)")
    return state
