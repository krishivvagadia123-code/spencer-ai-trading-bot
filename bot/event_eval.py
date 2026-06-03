"""
Read-only EVENT-ALPHA research (Option B, path 3). Does Spencer find edge around events?

For each event we measure the FORWARD return over a fixed horizon, the win rate, the
cost-adjusted return, the worst adverse move during the hold, and whether the result holds
in-sample vs out-of-sample and across walk-forward quarters. No trading, no fitting, no
deployment, no AI learning.

DATA REALITY (stated honestly, not worked around):
  - Earnings dates + surprise%  : available historically (yfinance). TESTABLE.
  - Corporate actions (div/split): available historically (yfinance). TESTABLE.
  - Gap up / gap down           : derived from price. TESTABLE.
  - Volume shock                : derived from price. TESTABLE (as a proxy; we CANNOT
                                  confirm "with news" without a historical news feed).
  - Sector news impact          : NOT TESTABLE — no historical news feed.
  - Stock-specific sentiment shock: NOT TESTABLE — no historical sentiment feed.
We report the two untestable types explicitly rather than fabricate a result.

Entry timing (tradeable, causal):
  - Earnings: enter at the close of the FIRST session AFTER the announcement (post-event
    drift; avoids using an after-hours announcement's same-day close).
  - Gap / volume / corporate action: enter at that day's close (the event is observed
    during the session).
Forward return = close[entry+H]/close[entry] - 1. Max adverse move = worst low in the hold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bot.backtest import NIFTY50, fetch_history
from workflow.research_automation import (
    add_research_workflow_args,
    finalize_from_args,
    print_research_workflow_summary,
)

HORIZON = 5
GAP_THRESH = 0.03        # +/-3% open vs prior close = a gap
VSHOCK_Z = 3.0           # volume z-score (20d) above this = a volume shock
COST = 0.0025            # ~0.25% round-trip (entry + exit) for a directional bet
MIN_EVENTS = 30          # below this, no conclusion


# ── Event builders ───────────────────────────────────────────────────────────
def _to_date_index(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.index = [pd.to_datetime(x).date() for x in df.index]
    return df


def gap_events(price: pd.DataFrame):
    prev_close = price["close"].shift(1)
    gap = price["open"] / prev_close - 1.0
    up = price.index[gap >= GAP_THRESH]
    down = price.index[gap <= -GAP_THRESH]
    return list(up), list(down)


def volume_shock_events(price: pd.DataFrame):
    v = price["volume"]
    z = (v - v.rolling(20).mean()) / v.rolling(20).std().replace(0, np.nan)
    return list(price.index[z >= VSHOCK_Z])


def earnings_events(symbol: str):
    """(date, surprise%) list from yfinance. Empty on any failure."""
    import yfinance as yf
    try:
        ed = yf.Ticker(f"{symbol}.NS").get_earnings_dates(limit=24)
    except Exception:
        return []
    if ed is None or len(ed) == 0:
        return []
    out = []
    for ts, row in ed.iterrows():
        d = pd.to_datetime(ts).date()
        surprise = row.get("Surprise(%)")
        out.append((d, float(surprise) if pd.notna(surprise) else None))
    return out


def corporate_action_events(symbol: str):
    """(div_dates, split_dates) from yfinance actions. Empty on failure."""
    import yfinance as yf
    try:
        a = yf.Ticker(f"{symbol}.NS").actions
    except Exception:
        return [], []
    if a is None or len(a) == 0:
        return [], []
    divs = [pd.to_datetime(d).date() for d in a.index[a.get("Dividends", 0) > 0]]
    splits = [pd.to_datetime(d).date() for d in a.index[a.get("Stock Splits", 0) > 0]]
    return divs, splits


# ── Forward window ───────────────────────────────────────────────────────────
def forward_record(price: pd.DataFrame, event_date, strictly_after: bool):
    dates = list(price.index)
    # First entry index at/after the event.
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        cond = dates[mid] > event_date if strictly_after else dates[mid] >= event_date
        if cond:
            hi = mid
        else:
            lo = mid + 1
    entry_idx = lo
    if entry_idx >= len(dates) or entry_idx + HORIZON >= len(dates):
        return None
    entry = float(price["close"].iloc[entry_idx])
    if entry <= 0:
        return None
    fwd = float(price["close"].iloc[entry_idx + HORIZON]) / entry - 1.0
    lows = price["low"].iloc[entry_idx + 1: entry_idx + HORIZON + 1]
    max_adv = float(lows.min()) / entry - 1.0 if len(lows) else 0.0
    return {"date": dates[entry_idx], "fwd": fwd, "max_adv": max_adv}


# ── Metrics + walk-forward ───────────────────────────────────────────────────
def _metrics(records: list) -> dict:
    n = len(records)
    if n == 0:
        return {"events": 0}
    fwd = np.array([r["fwd"] for r in records])
    adv = np.array([r["max_adv"] for r in records])
    return {
        "events": n,
        "win_rate": round(float((fwd > 0).mean()), 4),
        "avg_fwd": round(float(fwd.mean()), 5),
        "cost_adj": round(float(fwd.mean() - COST), 5),
        "avg_max_adverse": round(float(adv.mean()), 5),
    }


def _split_and_walkforward(records: list) -> dict:
    if len(records) < MIN_EVENTS:
        return {"is_avg": None, "oos_avg": None, "walk_forward": "insufficient"}
    recs = sorted(records, key=lambda r: r["date"])
    mid = recs[len(recs) // 2]["date"]
    is_r = [r for r in recs if r["date"] <= mid]
    oos_r = [r for r in recs if r["date"] > mid]
    is_avg = float(np.mean([r["fwd"] for r in is_r])) - COST if is_r else None
    oos_avg = float(np.mean([r["fwd"] for r in oos_r])) - COST if oos_r else None

    # Walk-forward: cost-adjusted average per quarter; survive if OOS avg > 0 AND a
    # majority of OOS quarters are positive AND the IS sign agrees with OOS.
    dfq = pd.DataFrame(oos_r)
    survive = False
    if len(dfq) >= 10:
        dfq["q"] = pd.to_datetime(dfq["date"]).dt.to_period("Q")
        qmeans = dfq.groupby("q")["fwd"].mean() - COST
        pos = int((qmeans > 0).sum())
        survive = bool(oos_avg is not None and oos_avg > 0 and pos > len(qmeans) / 2
                       and is_avg is not None and np.sign(is_avg) == np.sign(oos_avg))
    return {
        "is_avg": round(is_avg, 5) if is_avg is not None else None,
        "oos_avg": round(oos_avg, 5) if oos_avg is not None else None,
        "walk_forward": "survives" if survive else "fails",
    }


# ── Orchestration ────────────────────────────────────────────────────────────
def evaluate(symbols: list[str], years: int = 2) -> dict:
    buckets: dict[str, list] = {
        "earnings_all": [], "earnings_beat": [], "earnings_miss": [],
        "volume_shock": [], "gap_up": [], "gap_down": [],
        "corp_action_dividend": [], "corp_action_split": [],
    }
    used = 0
    for sym in symbols:
        price = fetch_history(sym, years)
        if price is None:
            continue
        price = _to_date_index(price)
        used += 1

        for d, surprise in earnings_events(sym):
            rec = forward_record(price, d, strictly_after=True)
            if rec is None:
                continue
            buckets["earnings_all"].append(rec)
            if surprise is not None:
                (buckets["earnings_beat"] if surprise >= 0 else buckets["earnings_miss"]).append(rec)

        up, down = gap_events(price)
        for d in up:
            r = forward_record(price, d, strictly_after=False)
            if r: buckets["gap_up"].append(r)
        for d in down:
            r = forward_record(price, d, strictly_after=False)
            if r: buckets["gap_down"].append(r)

        for d in volume_shock_events(price):
            r = forward_record(price, d, strictly_after=False)
            if r: buckets["volume_shock"].append(r)

        divs, splits = corporate_action_events(sym)
        for d in divs:
            r = forward_record(price, d, strictly_after=False)
            if r: buckets["corp_action_dividend"].append(r)
        for d in splits:
            r = forward_record(price, d, strictly_after=False)
            if r: buckets["corp_action_split"].append(r)

    results = {}
    for name, recs in buckets.items():
        m = _metrics(recs)
        m.update(_split_and_walkforward(recs))
        results[name] = m

    # Honestly mark the event types we cannot test without a historical news/sentiment feed.
    not_testable = {
        "sector_news_impact": "NOT TESTABLE — no historical sector-news feed.",
        "stock_sentiment_shock": "NOT TESTABLE — no historical sentiment feed.",
    }

    tested = [k for k, v in results.items() if v.get("events", 0) >= MIN_EVENTS]
    survivors = [k for k, v in results.items()
                 if v.get("walk_forward") == "survives" and (v.get("cost_adj") or -1) > 0]
    if survivors:
        verdict = (
            f"{len(survivors)} of {len(tested)} tested event types show a cost-adjusted edge "
            f"that survives walk-forward: {survivors}. CAVEAT: testing {len(tested)} buckets "
            "and finding 1 survivor is weak evidence (multiple-comparisons risk) and samples "
            "are small (~hundreds of events). This is a CANDIDATE to confirm with more history, "
            "realistic gap-day slippage, and an out-of-universe / holdout check — NOT a "
            "confirmed edge and NOT to be deployed.")
    else:
        verdict = ("NO event type shows a cost-adjusted edge that survives walk-forward. "
                   "On this data, events do not predict forward returns after costs.")
    return {"symbols_used": used, "horizon_days": HORIZON, "cost": COST,
            "results": results, "not_testable": not_testable, "verdict": verdict}


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="bot.event_eval")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--years", type=int, default=2)
    add_research_workflow_args(p)
    args = p.parse_args(argv)
    symbols = NIFTY50[: args.top]
    print(f"Event-alpha research: {len(symbols)} Nifty-50 symbols, {args.years}y, "
          f"forward {HORIZON}d, cost {COST:.2%}\n")
    r = evaluate(symbols, args.years)
    print(f"Symbols used: {r['symbols_used']}\n")
    print(f"{'event type':<24}{'events':>7}{'win%':>7}{'avgFwd':>9}{'costAdj':>9}"
          f"{'maxAdv':>9}{'IS':>9}{'OOS':>9}{'walk-fwd':>11}")
    print("-" * 103)
    for name, v in r["results"].items():
        if v.get("events", 0) == 0:
            print(f"{name:<24}{0:>7}{'—':>7}{'—':>9}{'—':>9}{'—':>9}{'—':>9}{'—':>9}{'—':>11}")
            continue
        def pct(x): return f"{x:+.2%}" if isinstance(x, (int, float)) else "n/a"
        print(f"{name:<24}{v['events']:>7}{v['win_rate']:>7.0%}{pct(v['avg_fwd']):>9}"
              f"{pct(v['cost_adj']):>9}{pct(v['avg_max_adverse']):>9}{pct(v['is_avg']):>9}"
              f"{pct(v['oos_avg']):>9}{v['walk_forward']:>11}")
    print("\nNot testable without a historical news/sentiment data source:")
    for k, why in r["not_testable"].items():
        print(f"  - {k}: {why}")
    print(f"\nVERDICT: {r['verdict']}")
    print("\n(Read-only research. No trades taken. Nothing deployed or wired to live.)")
    print_research_workflow_summary(finalize_from_args("event_eval", r, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
