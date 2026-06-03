"""
Walk-forward test of ONE fixed hypothesis: the "RANGE regime + strict BUY cutoff
(score >= 0.72)" pocket that was the only positive bucket in the quality experiment.

Why this design (and what it is NOT):
  - The rule has NO free parameters to fit here. RANGE-only and cutoff=0.72 are FIXED
    (the hypothesis). We do not re-tune the cutoff per fold — that would be the exact
    "optimize after seeing the data" trap. We only ask: does the fixed rule keep working
    on later, out-of-sample periods?
  - Same universe (Nifty-50), same costs/slippage (bot.charges via the engine), same risk
    rules (bot.risk sizing), same engine (bot.backtest._simulate). Only the date window
    changes between in-sample and out-of-sample.
  - Honest caveat: with ~2 years of data and a hypothesis drawn from the full sample, this
    is a temporal-stability / robustness check, not a pristine hold-out. A pocket that
    FAILS this is luck. A pocket that passes is *suggestive*, not proof — and still must
    not be deployed.

Walk-forward layout (anchored, expanding train; no look-ahead):
  - Calendar = sorted union of all trading days.
  - In-sample reference  = first TRAIN_DAYS (~year 1).
  - Out-of-sample        = everything after, tiled into TEST_DAYS quarters (each trade
                           counted once). A trade is assigned by its ENTRY date (the
                           moment the decision was made) — never by exit.

Verdict rule (decided BEFORE looking at numbers):
  Survives only if OOS has >= MIN_OOS_TRADES, OOS net P&L > 0, OOS win rate >= BREAKEVEN_WR,
  AND a majority of OOS quarters are net-positive. Otherwise: FAILED or INCONCLUSIVE.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

from bot.backtest import _prepare, _simulate, _index_regime_series, NIFTY50
from bot.config import default_config
from bot.entry_policy import EntryConfig
from workflow.research_automation import (
    add_research_workflow_args,
    finalize_from_args,
    print_research_workflow_summary,
)

TRAIN_DAYS = 252        # ~1 trading year in-sample reference
TEST_DAYS = 63          # ~1 trading quarter per OOS block
MIN_OOS_TRADES = 20     # below this we cannot conclude an edge
BREAKEVEN_WR = 0.35     # ~33% gross at 2R, lifted for charges on small trades
START_EQUITY = 50_000.0


def _metrics(trades: List[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "win_rate": 0.0, "net_pnl": 0.0, "charges": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0, "max_drawdown_pct": 0.0}
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    # Realized-equity drawdown, trades ordered by exit date.
    eq = START_EQUITY
    peak = eq
    mdd = 0.0
    for t in sorted(trades, key=lambda x: (x["exit_date"], x["entry_date"])):
        eq += t["pnl"]
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, (peak - eq) / peak * 100)
    return {
        "trades": n,
        "win_rate": round(len(wins) / n, 4),
        "net_pnl": round(sum(pnls), 2),
        "charges": round(sum(t["charges"] for t in trades), 2),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "max_drawdown_pct": round(mdd, 2),
    }


def _load(journal: str) -> List[dict]:
    conn = sqlite3.connect(journal)
    conn.row_factory = sqlite3.Row
    try:
        rid = conn.execute("SELECT MAX(run_id) FROM backtest_trades").fetchone()[0]
        rows = conn.execute(
            "SELECT symbol, regime, entry_date, exit_date, charges, pnl "
            "FROM backtest_trades WHERE run_id=?", (rid,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def run(symbols: List[str], years: int = 2,
        journal: str = "walkforward_range072.db") -> dict:
    cfg = default_config()
    index_regimes = _index_regime_series(years)
    print("Preparing data once…")
    prepared, rowmap = _prepare(symbols, years, cfg)

    # The FIXED hypothesis. No tuning. RANGE-only + score >= 0.72.
    pocket = EntryConfig(name="range072", min_score=0.72, only_regime="RANGE")
    _simulate(prepared, rowmap, symbols, cfg, entry_cfg=pocket, filter_cfg=None,
              trust_table={}, index_regimes=index_regimes, journal_path=journal)
    trades = _load(journal)
    for t in trades:
        t["_entry"] = datetime.fromisoformat(t["entry_date"]).date()

    # Master calendar + date->position.
    all_dates = sorted({d for rm in rowmap.values() for d in rm})
    pos = {d: i for i, d in enumerate(all_dates)}

    def window_trades(lo: int, hi: int) -> List[dict]:
        return [t for t in trades if lo <= pos.get(t["_entry"], -1) < hi]

    in_sample = window_trades(0, TRAIN_DAYS)
    oos_all = window_trades(TRAIN_DAYS, len(all_dates))

    # Per-quarter OOS folds (non-overlapping; each trade counted once).
    folds = []
    start = TRAIN_DAYS
    q = 1
    while start < len(all_dates):
        ft = window_trades(start, start + TEST_DAYS)
        d0 = all_dates[start]
        d1 = all_dates[min(start + TEST_DAYS, len(all_dates)) - 1]
        folds.append({"quarter": q, "from": str(d0), "to": str(d1), **_metrics(ft)})
        start += TEST_DAYS
        q += 1

    is_m = _metrics(in_sample)
    oos_m = _metrics(oos_all)

    # Verdict (criteria fixed in the docstring, applied without cherry-picking).
    oos_quarters = [f for f in folds if f["trades"] > 0]
    pos_quarters = sum(1 for f in oos_quarters if f["net_pnl"] > 0)
    majority_positive = len(oos_quarters) > 0 and pos_quarters > len(oos_quarters) / 2

    if oos_m["trades"] < MIN_OOS_TRADES:
        verdict = "INCONCLUSIVE"
        reason = (f"only {oos_m['trades']} out-of-sample trades (< {MIN_OOS_TRADES}). "
                  "Too thin to confirm an edge — treat as NOT real until proven.")
    elif oos_m["net_pnl"] > 0 and oos_m["win_rate"] >= BREAKEVEN_WR and majority_positive:
        verdict = "SURVIVES (suggestive, not proof)"
        reason = (f"OOS net ₹{oos_m['net_pnl']:,.0f}, win {oos_m['win_rate']:.1%} ≥ "
                  f"{BREAKEVEN_WR:.0%}, {pos_quarters}/{len(oos_quarters)} quarters positive.")
    else:
        verdict = "FAILED"
        reason = (f"OOS net ₹{oos_m['net_pnl']:,.0f}, win {oos_m['win_rate']:.1%} "
                  f"(breakeven ~{BREAKEVEN_WR:.0%}), {pos_quarters}/{len(oos_quarters)} "
                  "quarters positive — the in-sample pocket did not hold up.")

    return {"in_sample": is_m, "oos": oos_m, "folds": folds,
            "verdict": verdict, "reason": reason,
            "params": {"train_days": TRAIN_DAYS, "test_days": TEST_DAYS,
                       "min_score": 0.72, "regime": "RANGE", "symbols": len(prepared)}}


def _fmt(m: dict) -> str:
    return (f"trades={m['trades']:>4}  win={m['win_rate']:.1%}  net=Rs.{m['net_pnl']:>9,.0f}  "
            f"charges=Rs.{m['charges']:>8,.0f}  avgW={m['avg_win']:>6,.0f}  "
            f"avgL={m['avg_loss']:>7,.0f}  maxDD={m['max_drawdown_pct']:>5}%")


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="bot.walkforward")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--years", type=int, default=2)
    add_research_workflow_args(p)
    args = p.parse_args(argv)
    symbols = NIFTY50[: args.top]
    print(f"Walk-forward: RANGE + score>=0.72, {len(symbols)} symbols, {args.years}y\n")
    r = run(symbols, args.years)
    print("\n=== RANGE + strict-cutoff (>=0.72) walk-forward ===")
    print(f"IN-SAMPLE  (yr1): {_fmt(r['in_sample'])}")
    print(f"OUT-SAMPLE (yr2): {_fmt(r['oos'])}")
    print("\nPer-quarter OUT-OF-SAMPLE:")
    print(f"  {'quarter':<9}{'window':<26}{'trades':>7}{'win':>7}{'net':>10}{'avgW':>8}{'avgL':>9}")
    for f in r["folds"]:
        print(f"  Q{f['quarter']:<8}{f['from']+'..'+f['to']:<26}{f['trades']:>7}"
              f"{f['win_rate']:>7.0%}{f['net_pnl']:>10,.0f}{f['avg_win']:>8,.0f}{f['avg_loss']:>9,.0f}")
    print(f"\nVERDICT: {r['verdict']}")
    print(f"  {r['reason']}")
    print("\n(Not deployed. Not wired into live. No new AI learning added.)")
    print_research_workflow_summary(finalize_from_args("walkforward", r, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
