"""
Strategy tournament — walk-forward backtest + leaderboard.

How no-look-ahead is enforced:
  For each bar index i, we call strategy.generate_signal(bars[: i + 1]).
  Strategies receive ONLY the prefix up to and including bar i. They cannot
  read bar i+1. If a BUY fires at bar i, the simulator opens the trade at the
  bar i+1 OPEN (next-bar execution), and exits the next time the stop or
  target is touched (intra-bar check uses bar.high/bar.low only).

Promotion rules:
  - Min sample size       : MIN_TRADES per strategy (else: ineligible)
  - Max drawdown          : strategies above MAX_DD_PCT_CAP are demoted
  - Champion              : highest "score" = profit_factor * win_rate
                            among eligible strategies. Tie: lower drawdown wins.

Persisted to strategy_leaderboard.json next to the project.
"""

from __future__ import annotations
import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from bot.logger_config import get_logger
from bot.strategies import ALL_STRATEGIES
from bot.strategies.base import BacktestBar, Strategy, StrategyAction

log = get_logger("kite-bot.tournament")

DEFAULT_LEADERBOARD_PATH = Path(__file__).parent.parent / "strategy_leaderboard.json"

MIN_TRADES        = 10           # below this → ineligible for champion
MAX_DD_PCT_CAP    = 25.0         # demote if drawdown ≥ this
DEFAULT_FEE_BPS   = 10.0         # per-side, applied to notional
DEFAULT_SLIP_BPS  = 15.0


@dataclass(frozen=True)
class Trade:
    entry_ts:    str
    exit_ts:     str
    entry_price: float
    exit_price:  float
    qty:         float
    pnl:         float
    r_multiple:  float
    exit_reason: str


@dataclass(frozen=True)
class StrategyResult:
    name:           str
    trades:         int
    win_rate:       float
    profit_factor:  float
    expectancy:     float
    max_dd_pct:     float
    total_pnl:      float
    score:          float
    eligible:       bool
    reason:         str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LeaderboardSnapshot:
    asof:        str
    champion:    Optional[str]
    shadow:      List[str]
    results:     List[StrategyResult]
    notes:       str = ""

    def as_dict(self) -> dict:
        return {
            "asof":     self.asof,
            "champion": self.champion,
            "shadow":   self.shadow,
            "results":  [r.as_dict() for r in self.results],
            "notes":    self.notes,
        }


# ── Backtest one strategy (walk-forward, no look-ahead) ──────────────────────
def backtest_one(
    strategy:  Strategy,
    bars:      List[BacktestBar],
    *,
    fee_bps:   float = DEFAULT_FEE_BPS,
    slip_bps:  float = DEFAULT_SLIP_BPS,
    starting_cash: float = 100_000.0,
    min_history:   int   = 200,
    context_provider = None,
) -> StrategyResult:
    """
    Walk forward bar by bar. Strategy sees only bars[: i + 1]. If it fires
    BUY at bar i, simulator opens at bar i+1 OPEN. Position is checked for
    stop/target hits on bar i+2 onwards using high/low. No look-ahead.
    """
    if len(bars) < min_history + 5:
        return StrategyResult(
            name=strategy.name, trades=0, win_rate=0.0, profit_factor=0.0,
            expectancy=0.0, max_dd_pct=0.0, total_pnl=0.0, score=0.0,
            eligible=False, reason=f"need {min_history + 5} bars, have {len(bars)}",
        )

    trades: List[Trade] = []
    open_trade: Optional[dict] = None
    equity = starting_cash
    peak   = starting_cash
    max_dd = 0.0

    for i in range(min_history, len(bars) - 1):
        prefix = bars[: i + 1]
        cur    = bars[i]
        nxt    = bars[i + 1]

        # 1. Manage open trade — check stop/target on the NEXT bar's range
        if open_trade is not None:
            stop, target, qty, entry = (open_trade["stop"], open_trade["target"],
                                         open_trade["qty"], open_trade["entry"])
            exit_price, exit_reason = None, None
            # Pessimistic ordering: stop checked before target (gap-down wins)
            if nxt.low <= stop:
                exit_price  = stop * (1 - slip_bps / 10_000)
                exit_reason = "STOP"
            elif nxt.high >= target:
                exit_price  = target * (1 - slip_bps / 10_000)
                exit_reason = "TARGET"
            if exit_price is not None:
                fee_in  = entry      * qty * fee_bps / 10_000
                fee_out = exit_price * qty * fee_bps / 10_000
                pnl = (exit_price - entry) * qty - fee_in - fee_out
                risk = abs(entry - stop) * qty
                r_mult = pnl / risk if risk > 0 else 0
                trades.append(Trade(
                    entry_ts=open_trade["entry_ts"], exit_ts=nxt.ts,
                    entry_price=entry, exit_price=exit_price, qty=qty,
                    pnl=round(pnl, 4), r_multiple=round(r_mult, 4),
                    exit_reason=exit_reason,
                ))
                equity += pnl
                peak    = max(peak, equity)
                dd      = (peak - equity) / peak * 100 if peak > 0 else 0
                max_dd  = max(max_dd, dd)
                open_trade = None
                continue   # skip new entry on the same bar we exited

        # 2. No open trade → consult strategy on CURRENT prefix
        if open_trade is None:
            context = context_provider(prefix) if context_provider else None
            sig = strategy.generate_signal(prefix, context=context)
            if sig.action == StrategyAction.BUY and sig.stop and sig.target:
                # Open at next bar's OPEN with slippage (entries pay extra)
                entry = nxt.open * (1 + slip_bps / 10_000)
                risk_pct = 0.01   # fixed 1% per trade for fair comparison
                risk_amount = equity * risk_pct
                per_share_risk = abs(entry - sig.stop)
                qty = risk_amount / per_share_risk if per_share_risk > 0 else 0
                if qty > 0:
                    open_trade = {
                        "entry":   entry, "qty": qty,
                        "stop":    sig.stop, "target": sig.target,
                        "entry_ts": nxt.ts,
                    }

    n = len(trades)
    if n == 0:
        return StrategyResult(
            name=strategy.name, trades=0, win_rate=0.0, profit_factor=0.0,
            expectancy=0.0, max_dd_pct=max_dd, total_pnl=0.0, score=0.0,
            eligible=False, reason="no trades generated in window",
        )
    wins        = [t for t in trades if t.pnl > 0]
    losses      = [t for t in trades if t.pnl < 0]
    gross_gain  = sum(t.pnl for t in wins)
    gross_loss  = abs(sum(t.pnl for t in losses)) or 1e-9
    pf          = gross_gain / gross_loss
    win_rate    = len(wins) / n
    expectancy  = sum(t.pnl for t in trades) / n
    total_pnl   = sum(t.pnl for t in trades)
    eligible    = (n >= MIN_TRADES) and (max_dd <= MAX_DD_PCT_CAP)
    reason      = ""
    if n < MIN_TRADES:
        reason = f"too few trades ({n} < {MIN_TRADES})"
    elif max_dd > MAX_DD_PCT_CAP:
        reason = f"drawdown {max_dd:.1f}% > cap {MAX_DD_PCT_CAP}%"
    score = round(pf * win_rate, 4)
    return StrategyResult(
        name=strategy.name, trades=n,
        win_rate=round(win_rate, 4), profit_factor=round(pf, 4),
        expectancy=round(expectancy, 4), max_dd_pct=round(max_dd, 4),
        total_pnl=round(total_pnl, 4), score=score,
        eligible=eligible, reason=reason,
    )


# ── Run all strategies, pick champion, persist ───────────────────────────────
def run_tournament(
    bars_by_symbol: Dict[str, List[BacktestBar]],
    *,
    strategies:    Optional[List[Strategy]] = None,
    leaderboard_path: Path = DEFAULT_LEADERBOARD_PATH,
    benchmark_symbol: str  = "BTC-INR",
    context_provider = None,
) -> LeaderboardSnapshot:
    """
    Backtest every strategy on every symbol; aggregate by averaging metrics
    across symbols (simple equal-weight). Pick a champion. Persist.
    """
    strategies = strategies or list(ALL_STRATEGIES)
    aggregated: List[StrategyResult] = []

    for strat in strategies:
        per_symbol: List[StrategyResult] = []
        for sym, bars in bars_by_symbol.items():
            per_symbol.append(backtest_one(strat, bars,
                                            context_provider=context_provider))
        # Aggregate: sum trades, weighted means
        n_total = sum(r.trades for r in per_symbol)
        if n_total == 0:
            aggregated.append(StrategyResult(
                name=strat.name, trades=0, win_rate=0.0, profit_factor=0.0,
                expectancy=0.0, max_dd_pct=0.0, total_pnl=0.0, score=0.0,
                eligible=False, reason="no trades across any symbol",
            ))
            continue
        # Weight by trade count
        wr  = sum(r.win_rate      * r.trades for r in per_symbol) / n_total
        pf  = sum(r.profit_factor * r.trades for r in per_symbol) / n_total
        exp = sum(r.expectancy    * r.trades for r in per_symbol) / n_total
        dd  = max(r.max_dd_pct for r in per_symbol)
        pnl = sum(r.total_pnl for r in per_symbol)
        eligible = (n_total >= MIN_TRADES) and (dd <= MAX_DD_PCT_CAP)
        reason   = ""
        if n_total < MIN_TRADES:
            reason = f"too few trades ({n_total} < {MIN_TRADES})"
        elif dd > MAX_DD_PCT_CAP:
            reason = f"drawdown {dd:.1f}% > cap {MAX_DD_PCT_CAP}%"
        aggregated.append(StrategyResult(
            name=strat.name, trades=n_total,
            win_rate=round(wr, 4), profit_factor=round(pf, 4),
            expectancy=round(exp, 4), max_dd_pct=round(dd, 4),
            total_pnl=round(pnl, 4), score=round(pf * wr, 4),
            eligible=eligible, reason=reason,
        ))

    eligible_sorted = sorted(
        [r for r in aggregated if r.eligible],
        key=lambda r: (-r.score, r.max_dd_pct),
    )
    champion = eligible_sorted[0].name if eligible_sorted else None
    shadow   = [r.name for r in aggregated if r.name != champion]
    snap = LeaderboardSnapshot(
        asof=datetime.now().isoformat(timespec="seconds"),
        champion=champion, shadow=shadow, results=aggregated,
        notes=f"benchmark={benchmark_symbol}",
    )
    save_leaderboard(snap, leaderboard_path)
    log.info(f"tournament: champion={champion} eligible={len(eligible_sorted)} "
             f"total={len(aggregated)}")
    return snap


# ── Persistence ──────────────────────────────────────────────────────────────
def save_leaderboard(snap: LeaderboardSnapshot,
                     path: Path = DEFAULT_LEADERBOARD_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        except Exception:
            pass
    path.write_text(json.dumps(snap.as_dict(), indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


def load_leaderboard(
    path: Path = DEFAULT_LEADERBOARD_PATH,
) -> Optional[LeaderboardSnapshot]:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    results = [StrategyResult(**r) for r in raw.get("results", [])]
    return LeaderboardSnapshot(
        asof=raw.get("asof", ""), champion=raw.get("champion"),
        shadow=list(raw.get("shadow", [])), results=results,
        notes=raw.get("notes", ""),
    )


def active_champion(path: Path = DEFAULT_LEADERBOARD_PATH) -> Optional[str]:
    snap = load_leaderboard(path)
    return snap.champion if snap else None
