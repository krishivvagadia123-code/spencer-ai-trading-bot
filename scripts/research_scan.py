"""Spencer research scan: mine the real RELIANCE intraday DB for candidate edges.

Read-only over kite_bot.db. Surfaces statistical patterns and compares each to
the cost bar. It does NOT trade and does NOT validate anything - every pattern it
finds is a HYPOTHESIS that must still pass Spencer's backtest + cost bar. Small
samples are flagged honestly; nothing here is a signal.

Writes a compact findings JSON (workflow/research_findings.json) for the brain.

Usage:  python scripts/research_scan.py
"""
from __future__ import annotations

import json
import math
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "kite_bot.db"
OUT = ROOT / "workflow" / "research_findings.json"

# Cost bar (docs/RELIANCE_COST_MATH.md): intraday round-trip breakeven ~0.106%.
# A real edge must clear ~3x that to survive slippage/variance.
ROUND_TRIP_COST = 0.00106
EDGE_TARGET = 3 * ROUND_TRIP_COST  # ~0.32%


def load_sessions(interval: str = "15m"):
    """Return {date: [(ts,o,h,l,c,v), ...]} sorted, from real candles only."""
    uri = f"{DB.resolve().as_uri()}?mode=ro"
    rows = []
    with sqlite3.connect(uri, uri=True) as conn:
        rows = conn.execute(
            "SELECT ts, open, high, low, close, volume FROM intraday_prices "
            "WHERE symbol='RELIANCE' AND interval=? ORDER BY ts", (interval,)
        ).fetchall()
    sessions: dict[str, list] = {}
    for ts, o, h, l, c, v in rows:
        day = ts[:10]
        sessions.setdefault(day, []).append((ts, o, h, l, c, v))
    return {d: bars for d, bars in sessions.items() if len(bars) >= 10}


def _stats(xs):
    n = len(xs)
    if n < 2:
        return {"n": n, "mean": None, "std": None, "t": None}
    mean = statistics.fmean(xs)
    std = statistics.pstdev(xs)
    t = (mean / (std / math.sqrt(n))) if std > 0 else 0.0
    return {"n": n, "mean": mean, "std": std, "t": t}


def pct(x):
    return "n/a" if x is None else f"{x*100:+.3f}%"


def main() -> int:
    sessions = load_sessions("15m")
    days = sorted(sessions)
    findings = []

    # Per-session derived series.
    intraday, overnight, or_up_then_close, or_down_then_close = [], [], [], []
    gap_up_next, gap_down_next = [], []
    prev_close = None
    for d in days:
        bars = sessions[d]
        o = bars[0][1]
        c = bars[-1][4]
        first_c = bars[0][4]
        intraday.append(c / o - 1.0)
        if prev_close:
            gap = o / prev_close - 1.0
            overnight.append(gap)
            (gap_up_next if gap > 0 else gap_down_next).append(c / o - 1.0)
        # Opening-bar momentum: sign of first 15m bar -> rest-of-day move from first close to close.
        rod = c / first_c - 1.0
        (or_up_then_close if bars[0][4] >= bars[0][1] else or_down_then_close).append(rod)
        prev_close = c

    def add(name, hypothesis, xs, directional=True):
        s = _stats(xs)
        if s["mean"] is None:
            return
        edge = abs(s["mean"]) if directional else s["mean"]
        clears = edge - ROUND_TRIP_COST  # net after one round-trip cost
        findings.append({
            "name": name, "hypothesis": hypothesis,
            "n": s["n"], "mean": s["mean"], "t_stat": round(s["t"], 2),
            "net_after_cost": round(clears, 5),
            "clears_cost_bar": clears > 0,
            "significant": abs(s["t"]) >= 2.0,
        })

    add("intraday_drift", "Buy at open, sell at close (long bias).", intraday)
    add("overnight_gap", "Magnitude of open vs prior close (gap size).", overnight)
    add("openbar_up_momentum", "First 15m bar UP -> rest of day continues up.", or_up_then_close)
    add("openbar_down_momentum", "First 15m bar DOWN -> rest of day continues down.", or_down_then_close)
    add("gap_up_continuation", "Gap up -> intraday continues up.", gap_up_next)
    add("gap_down_continuation", "Gap down -> intraday continues down.", gap_down_next)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sessions_analyzed": len(days),
        "date_range": [days[0], days[-1]] if days else [],
        "cost_bar_round_trip": ROUND_TRIP_COST,
        "edge_target_3x": EDGE_TARGET,
        "findings": sorted(findings, key=lambda f: -abs(f["mean"])),
        "note": "Hypotheses only. None is validated until it passes Spencer's backtest + cost bar. Small sample = low confidence.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"=== Spencer research scan: {len(days)} sessions ({days[0]}..{days[-1]}) ===")
    print(f"Cost bar (round-trip): {pct(ROUND_TRIP_COST)} | edge target ~3x: {pct(EDGE_TARGET)}\n")
    print(f"{'pattern':28} {'n':>4} {'mean':>10} {'t':>6} {'net/cost':>10} {'clears?':>8} {'signif?':>8}")
    for f in report["findings"]:
        print(f"{f['name']:28} {f['n']:>4} {pct(f['mean']):>10} {f['t_stat']:>6} "
              f"{pct(f['net_after_cost']):>10} {str(f['clears_cost_bar']):>8} {str(f['significant']):>8}")
    any_real = [f for f in report["findings"] if f["clears_cost_bar"] and f["significant"]]
    print()
    if any_real:
        print("CANDIDATE EDGES (clear cost + statistically notable):")
        for f in any_real:
            print(f"  - {f['name']}: {f['hypothesis']} (mean {pct(f['mean'])}, t={f['t_stat']}, n={f['n']})")
    else:
        print("No pattern both clears the cost bar AND is statistically notable (t>=2). "
              "Honest result: no tradeable edge in this sample yet.")
    print(f"\nWROTE {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
