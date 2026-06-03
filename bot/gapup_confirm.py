"""
Confirm-or-kill the gap_up signal — rigorously, and ONLY gap_up.

gap_up event = open >= prior_close * (1 + GAP_THRESH). Enter at the gap-day CLOSE, hold
HORIZON days, exit at close. We measure forward return net of cost and stress it hard:

  1. 5+ years of history (yfinance daily).
  2. Realistic slippage: gap days are volatile, so cost scales with ATR%
     (round-trip = brokerage + 2 * SLIP_ATR_FRAC * atr_pct). Plus a flat slippage sweep.
  3. Nifty-50 validation.
  4. Midcap-100 validation (out-of-universe).
  5. Clean holdout (last HOLDOUT_FRAC of the timeline) + per-year walk-forward.
  6. Earnings-overlap split (is the edge just an earnings effect?).

Pre-registered verdict (decided before seeing numbers). A universe PASSES only if ALL:
  - realistic-cost average net return > 0
  - still > 0 at FLAT_STRESS slippage (0.50% round-trip)
  - in-sample > 0 AND out-of-sample > 0 (same sign)
  - majority of walk-forward years positive
  - clean holdout net > 0
  - the NON-earnings subset net > 0 (edge is not purely an earnings artifact)
gap_up is CONFIRMED only if Nifty-50 PASSES and Midcap-100 is at least OOS-positive
(supporting). Otherwise it is KILLED. Read-only; nothing deployed or wired to live.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bot import indicators as ind
from bot.backtest import NIFTY50, fetch_history
from bot.event_eval import earnings_events
from bot.midcap_eval import MIDCAP100
from workflow.research_automation import (
    add_research_workflow_args,
    finalize_from_args,
    print_research_workflow_summary,
)

GAP_THRESH = 0.03
HORIZON = 5
YEARS = 8                      # 5+ years history
BROKERAGE = 0.001              # ~0.10% round-trip brokerage+taxes baseline
SLIP_ATR_FRAC = 0.10           # per-side slippage = 10% of one ATR on a gap day
FLAT_SWEEP = [0.0025, 0.005, 0.0075, 0.010]   # round-trip cost levels to stress
FLAT_STRESS = 0.005            # the "higher slippage" pass/fail bar
EARNINGS_WINDOW = 3            # +/- days to flag an earnings-overlapping gap
HOLDOUT_FRAC = 0.20
MIN_EVENTS = 50


def _to_date_index(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.index = [pd.to_datetime(x).date() for x in df.index]
    return df


def realistic_cost(rec: dict) -> float:
    """Round-trip cost for one event: flat brokerage + ATR-scaled slippage (both legs)."""
    return BROKERAGE + 2.0 * SLIP_ATR_FRAC * rec["atr_pct"]


def collect(symbols: list[str], years: int = YEARS, with_earnings: bool = True) -> list[dict]:
    records: list[dict] = []
    for sym in symbols:
        px = fetch_history(sym, years)
        if px is None:
            continue
        px = _to_date_index(px)
        atr = ind.atr(px, 14)
        edates = set()
        if with_earnings:
            for d, _ in earnings_events(sym):
                edates.add(d)
        prev_close = px["close"].shift(1)
        gap = px["open"] / prev_close - 1.0
        idxs = np.where(gap.values >= GAP_THRESH)[0]
        closes = px["close"].values
        lows = px["low"].values
        n = len(px)
        for i in idxs:
            if i + HORIZON >= n:
                continue
            entry = float(closes[i])
            if entry <= 0:
                continue
            fwd = float(closes[i + HORIZON]) / entry - 1.0
            window_low = float(np.min(lows[i + 1: i + HORIZON + 1]))
            max_adv = window_low / entry - 1.0
            ap = float(atr.iloc[i]) / entry if np.isfinite(atr.iloc[i]) else 0.025
            d = px.index[i]
            near = any(abs((d - ed).days) <= EARNINGS_WINDOW for ed in edates)
            records.append({"symbol": sym, "date": d, "fwd": fwd, "max_adv": max_adv,
                            "atr_pct": ap, "near_earnings": near})
    return records


def _summ(records: list[dict], costfn) -> dict:
    n = len(records)
    if n == 0:
        return {"events": 0}
    recs = sorted(records, key=lambda r: r["date"])
    nets = np.array([r["fwd"] - costfn(r) for r in recs])
    fwd = np.array([r["fwd"] for r in recs])
    adv = np.array([r["max_adv"] for r in recs])
    eq, peak, mdd = 1.0, 1.0, 0.0
    for x in nets:
        eq *= (1.0 + x)
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    return {
        "events": n,
        "win_rate": round(float((nets > 0).mean()), 4),
        "avg_gross": round(float(fwd.mean()), 5),
        "avg_net": round(float(nets.mean()), 5),
        "avg_max_adverse": round(float(adv.mean()), 5),
        "seq_drawdown": round(float(mdd), 4),
    }


def _avg_net(records, costfn) -> float | None:
    if not records:
        return None
    return float(np.mean([r["fwd"] - costfn(r) for r in records]))


def analyze_universe(name: str, symbols: list[str]) -> dict:
    recs = collect(symbols)
    if len(recs) < MIN_EVENTS:
        return {"universe": name, "events": len(recs), "verdict": "insufficient"}

    recs = sorted(recs, key=lambda r: r["date"])
    dates = [r["date"] for r in recs]
    mid = dates[len(dates) // 2]
    is_r = [r for r in recs if r["date"] <= mid]
    oos_r = [r for r in recs if r["date"] > mid]
    cut = dates[int(len(dates) * (1 - HOLDOUT_FRAC))]
    holdout = [r for r in recs if r["date"] > cut]
    non_earn = [r for r in recs if not r["near_earnings"]]
    near_earn = [r for r in recs if r["near_earnings"]]

    # Walk-forward by year (realistic cost).
    by_year: dict[int, list] = {}
    for r in recs:
        by_year.setdefault(r["date"].year, []).append(r)
    wf_years = {y: round(_avg_net(rs, realistic_cost), 5) for y, rs in sorted(by_year.items())}
    oos_years = [v for y, v in wf_years.items() if y > mid.year]
    wf_pos = sum(1 for v in oos_years if v and v > 0)

    # Flat slippage sweep.
    sweep = {f"{c:.2%}": round(_avg_net(recs, lambda r, c=c: c), 5) for c in FLAT_SWEEP}

    real = _summ(recs, realistic_cost)
    is_net = _avg_net(is_r, realistic_cost)
    oos_net = _avg_net(oos_r, realistic_cost)
    hold_net = _avg_net(holdout, realistic_cost)
    nonearn_net = _avg_net(non_earn, realistic_cost)
    stress_net = _avg_net(recs, lambda r: FLAT_STRESS)

    gates = {
        "realistic_positive": real["avg_net"] > 0,
        "survives_flat_stress": stress_net is not None and stress_net > 0,
        "is_and_oos_positive": (is_net or -1) > 0 and (oos_net or -1) > 0,
        "walkforward_majority": len(oos_years) > 0 and wf_pos > len(oos_years) / 2,
        "holdout_positive": (hold_net or -1) > 0,
        "non_earnings_positive": (nonearn_net or -1) > 0,
    }
    passed = all(gates.values())
    return {
        "universe": name, "events": real["events"], "summary_realistic": real,
        "is_net": round(is_net, 5) if is_net is not None else None,
        "oos_net": round(oos_net, 5) if oos_net is not None else None,
        "holdout_net": round(hold_net, 5) if hold_net is not None else None,
        "non_earnings_net": round(nonearn_net, 5) if nonearn_net is not None else None,
        "near_earnings_net": round(_avg_net(near_earn, realistic_cost) or 0, 5),
        "near_earnings_share": round(len(near_earn) / len(recs), 3),
        "stress_net_at_0.50%": round(stress_net, 5) if stress_net is not None else None,
        "flat_slippage_sweep": sweep,
        "walk_forward_years": wf_years,
        "gates": gates, "passes": passed,
    }


def run() -> dict:
    nifty = analyze_universe("nifty50", NIFTY50)
    mid = analyze_universe("midcap100", MIDCAP100)
    nifty_pass = nifty.get("passes", False)
    mid_oos_pos = (mid.get("oos_net") or -1) > 0
    confirmed = bool(nifty_pass and mid_oos_pos)
    if confirmed:
        verdict = ("CONFIRMED (candidate): gap_up survives realistic slippage, IS/OOS, "
                   "walk-forward, holdout, and the non-earnings subset on Nifty-50, with "
                   "Midcap-100 OOS support. Proceed to a PAPER-ONLY strategy spec.")
    else:
        verdict = ("KILLED: gap_up does NOT clear the confirmation bar. "
                   + ("Nifty-50 failed one or more gates. " if not nifty_pass else "")
                   + ("Midcap-100 OOS not positive. " if not mid_oos_pos else "")
                   + "Do not build a strategy on it.")
    return {"nifty50": nifty, "midcap100": mid, "confirmed": confirmed, "verdict": verdict}


def _p(x) -> str:
    return f"{x:+.2%}" if isinstance(x, (int, float)) else "n/a"


def _print_universe(u: dict) -> None:
    if u.get("verdict") == "insufficient" or u.get("events", 0) < MIN_EVENTS:
        print(f"[{u['universe']}] insufficient events ({u.get('events', 0)})")
        return
    s = u["summary_realistic"]
    print(f"\n[{u['universe'].upper()}]  events={s['events']}  win={s['win_rate']:.0%}  "
          f"avg_gross={_p(s['avg_gross'])}  avg_net(real)={_p(s['avg_net'])}  "
          f"maxAdv={_p(s['avg_max_adverse'])}  seqDD={s['seq_drawdown']:.1%}")
    print(f"  IS={_p(u['is_net'])}  OOS={_p(u['oos_net'])}  holdout={_p(u['holdout_net'])}  "
          f"non-earn={_p(u['non_earnings_net'])}  near-earn={_p(u['near_earnings_net'])} "
          f"(share {u['near_earnings_share']:.0%})  stress@0.5%={_p(u['stress_net_at_0.50%'])}")
    print("  flat slippage sweep: " + ", ".join(f"{k}->{_p(v)}" for k, v in u["flat_slippage_sweep"].items()))
    print("  walk-forward by year: " + ", ".join(f"{y}:{_p(v)}" for y, v in u["walk_forward_years"].items()))
    print("  gates: " + ", ".join(f"{k}={'Y' if v else 'N'}" for k, v in u["gates"].items())
          + f"  => {'PASS' if u['passes'] else 'FAIL'}")


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="bot.gapup_confirm")
    add_research_workflow_args(p)
    args = p.parse_args(argv)
    print(f"Confirm-or-kill gap_up: gap>={GAP_THRESH:.0%}, hold {HORIZON}d, {YEARS}y history, "
          f"realistic ATR-scaled slippage\n")
    r = run()
    _print_universe(r["nifty50"])
    _print_universe(r["midcap100"])
    print(f"\nVERDICT: {r['verdict']}")
    print("\n(Read-only confirmation. No trades taken. Nothing deployed or wired to live.)")
    print_research_workflow_summary(finalize_from_args("gapup_confirm", r, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
