"""
Predictive-power evaluation for the Option B features — BEFORE any trading.

Method (honest, no fitting, no look-ahead in the features):
  - For every symbol/day, compute each feature at the close (causal) and the forward
    `HORIZON`-day return (the target).
  - Information Coefficient (IC) = Spearman rank correlation between the feature and the
    forward return, pooled across the Nifty-50 panel. IC measures monotonic predictive
    power. |IC| ~ 0.00-0.02 = noise; >= 0.03 with a stable sign is a faint but real edge.
  - We split the timeline IN-SAMPLE (first half) vs OUT-OF-SAMPLE (second half) and report
    IC in BOTH. A feature only "passes" if its IC keeps the SAME SIGN and stays >= IC_MIN
    out-of-sample. This is the anti-luck filter from the walk-forward, applied to raw edge.
  - Quintile spread: average forward return of the top feature-quintile minus the bottom
    (OOS). A real feature shows a positive, monotonic spread.

No trade is taken. No parameter is tuned to maximise anything. Nothing is deployed.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from bot import features as F
from bot.backtest import fetch_history, NIFTY50
from workflow.research_automation import (
    add_research_workflow_args,
    finalize_from_args,
    print_research_workflow_summary,
)

HORIZON = 5         # forward return horizon (trading days)
RS_PERIOD = 20
IC_MIN = 0.03       # minimum |IC| out-of-sample to call a feature "promising"
COST_HURDLE = 0.003  # OOS quintile spread must EXCEED this (~0.25% round-trip cost + margin)

# Coarse sector map for Nifty-50 (for sector_strength peer averaging).
SECTORS: Dict[str, str] = {}
for _sec, _syms in {
    "IT": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
    "BANK": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK"],
    "FIN": ["BAJFINANCE", "BAJAJFINSV", "SHRIRAMFIN", "HDFCLIFE", "SBILIFE"],
    "AUTO": ["MARUTI", "TATAMOTORS", "M&M", "EICHERMOT", "HEROMOTOCO", "BAJAJ-AUTO"],
    "ENERGY": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA", "BPCL"],
    "METAL": ["TATASTEEL", "JSWSTEEL", "HINDALCO"],
    "PHARMA": ["SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "APOLLOHOSP"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "TATACONSUM"],
    "MATERIALS": ["ULTRACEMCO", "GRASIM", "ASIANPAINT"],
    "OTHER": ["BHARTIARTL", "LT", "TITAN", "ADANIENT", "ADANIPORTS", "TRENT"],
}.items():
    for _s in _syms:
        SECTORS[_s] = _sec


def spearman_ic(feature: pd.Series, fwd: pd.Series) -> Optional[float]:
    """Spearman IC = Pearson correlation of ranks. Returns None if too few points."""
    df = pd.DataFrame({"f": feature, "r": fwd}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(df) < 50 or df["f"].nunique() < 5:
        return None
    rf = df["f"].rank()
    rr = df["r"].rank()
    c = np.corrcoef(rf, rr)[0, 1]
    return float(c) if np.isfinite(c) else None


def _fetch_index(years: int):
    from bot.regime_learner import fetch_index
    idx = _fetch_or_none(lambda: fetch_index(years))
    return idx


def _fetch_or_none(fn):
    try:
        return fn()
    except Exception:
        return None


def build_panel(symbols: List[str], years: int) -> pd.DataFrame:
    """Long panel: one row per (date, symbol) with features + forward return."""
    bench = _fetch_index(years)
    if bench is None:
        raise RuntimeError("could not fetch Nifty index for relative strength")
    bench_close = bench["close"]
    bench_close.index = [pd.to_datetime(x).date() for x in bench_close.index]

    rows = []
    rs_by_symbol: Dict[str, pd.Series] = {}
    frames: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = fetch_history(sym, years)
        if df is None:
            continue
        df = df.copy()
        df.index = [pd.to_datetime(x).date() for x in df.index]
        b = bench_close.reindex(df.index).ffill()
        rs = F.relative_strength(df["close"], b, RS_PERIOD)
        rs_by_symbol[sym] = rs
        df["rs"] = rs
        df["bq"] = F.breakout_quality(df)
        df["vq"] = F.volume_expansion_quality(df)
        df["fwd"] = F.forward_return(df["close"], HORIZON)
        frames[sym] = df

    # Sector strength: per date, mean RS of sector peers (excluding self).
    rs_wide = pd.DataFrame(rs_by_symbol)
    sector_of = {s: SECTORS.get(s, "OTHER") for s in rs_wide.columns}
    sector_mean: Dict[str, pd.Series] = {}
    for sec in set(sector_of.values()):
        cols = [s for s in rs_wide.columns if sector_of[s] == sec]
        if not cols:
            continue
        sub = rs_wide[cols]
        for s in cols:
            peers = [c for c in cols if c != s]
            sector_mean[s] = sub[peers].mean(axis=1) if peers else pd.Series(index=sub.index, dtype=float)

    for sym, df in frames.items():
        ss = sector_mean.get(sym)
        df["ss"] = ss.reindex(df.index) if ss is not None else np.nan
        tmp = df[["rs", "bq", "vq", "ss", "fwd"]].copy()
        tmp["symbol"] = sym
        tmp["date"] = df.index
        rows.append(tmp)

    panel = pd.concat(rows, ignore_index=True)
    return panel


def quintile_spread(feature: pd.Series, fwd: pd.Series) -> Optional[dict]:
    df = pd.DataFrame({"f": feature, "r": fwd}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(df) < 100:
        return None
    try:
        df["q"] = pd.qcut(df["f"], 5, labels=False, duplicates="drop")
    except ValueError:
        return None
    g = df.groupby("q")["r"].mean()
    if g.empty:
        return None
    top, bot = g.index.max(), g.index.min()
    return {"top_q_ret": round(float(g.loc[top]), 5),
            "bottom_q_ret": round(float(g.loc[bot]), 5),
            "spread": round(float(g.loc[top] - g.loc[bot]), 5)}


def evaluate(symbols: List[str], years: int = 2) -> dict:
    panel = build_panel(symbols, years)
    dates = sorted(panel["date"].unique())
    split = dates[len(dates) // 2]
    is_mask = panel["date"] <= split
    oos_mask = panel["date"] > split

    feats = {"relative_strength": "rs", "breakout_quality": "bq",
             "volume_expansion_quality": "vq", "sector_strength": "ss"}
    results = {}
    for name, col in feats.items():
        ic_all = spearman_ic(panel[col], panel["fwd"])
        ic_is = spearman_ic(panel.loc[is_mask, col], panel.loc[is_mask, "fwd"])
        ic_oos = spearman_ic(panel.loc[oos_mask, col], panel.loc[oos_mask, "fwd"])
        qs = quintile_spread(panel.loc[oos_mask, col], panel.loc[oos_mask, "fwd"])
        stable = (ic_is is not None and ic_oos is not None
                  and np.sign(ic_is) == np.sign(ic_oos) and abs(ic_oos) >= IC_MIN)
        direction = None
        if ic_oos is not None:
            direction = "momentum/continuation" if ic_oos > 0 else "mean-reversion/fade"
        # Economic caveat: |spread| must EXCEED the cost hurdle (with margin) to be tradeable.
        spread = abs(qs["spread"]) if qs else 0.0
        clears_costs = spread > COST_HURDLE
        results[name] = {
            "ic_all": round(ic_all, 4) if ic_all is not None else None,
            "ic_in_sample": round(ic_is, 4) if ic_is is not None else None,
            "ic_out_sample": round(ic_oos, 4) if ic_oos is not None else None,
            "oos_quintile_spread": qs,
            "sign_stable": bool(stable),
            "direction": direction,
            "clears_costs": bool(clears_costs),
            # "Usable" requires BOTH a stable sign AND an edge big enough to beat costs.
            "promising": bool(stable and clears_costs),
        }

    n_obs = int(panel[["rs", "bq", "vq", "ss", "fwd"]].dropna().shape[0])
    promising = [k for k, v in results.items() if v["promising"]]
    stable_only = [k for k, v in results.items() if v["sign_stable"] and not v["promising"]]
    if promising:
        verdict = (f"{len(promising)} feature(s) are USABLE (stable sign + spread beats "
                   f"~0.25% costs): {promising}.")
    elif stable_only:
        verdict = (f"NONE are usable. {stable_only} has a stable OOS sign but the edge is too "
                   "small to beat costs (and may point the 'wrong' way, i.e. mean-reversion). "
                   "Do NOT build a long entry on it; at most, test a controlled mean-reversion "
                   "variant — expect it to be marginal.")
    else:
        verdict = (f"NONE of the features show stable OOS predictive power (|IC|>={IC_MIN}). "
                   "No edge to build on yet — do NOT proceed to entries.")
    return {
        "symbols": len(panel["symbol"].unique()),
        "observations": n_obs,
        "horizon_days": HORIZON,
        "ic_min_threshold": IC_MIN,
        "split_date": str(split),
        "features": results,
        "promising_features": promising,
        "sign_stable_but_uneconomic": stable_only,
        "verdict": verdict,
    }


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="bot.feature_eval")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--years", type=int, default=2)
    add_research_workflow_args(p)
    args = p.parse_args(argv)
    symbols = NIFTY50[: args.top]
    print(f"Feature predictive-power eval: {len(symbols)} symbols, {args.years}y, "
          f"forward horizon {HORIZON}d\n")
    r = evaluate(symbols, args.years)
    print(f"Observations: {r['observations']:,} | IS/OOS split at {r['split_date']}\n")
    print(f"{'feature':<26}{'IC in':>9}{'IC oos':>9}{'OOS q5-q1':>11}{'direction':>22}{'usable':>8}")
    print("-" * 84)
    for name, v in r["features"].items():
        qs = v["oos_quintile_spread"]
        spread = f"{qs['spread']:+.4f}" if qs else "n/a"
        direction = v.get("direction") or "—"
        usable = "YES" if v["promising"] else ("stable*" if v["sign_stable"] else "no")
        print(f"{name:<26}{_s(v['ic_in_sample']):>9}{_s(v['ic_out_sample']):>9}"
              f"{spread:>11}{direction:>22}{usable:>8}")
    print("\n  * stable sign across IS/OOS but edge too small to beat ~0.25% round-trip costs.")
    print(f"\nVERDICT: {r['verdict']}")
    print("\n(No trades taken. No fitting. Nothing deployed or wired to live.)")
    print_research_workflow_summary(finalize_from_args("feature_eval", r, args))
    return 0


def _s(x) -> str:
    return f"{x:+.4f}" if isinstance(x, (int, float)) else "n/a"


if __name__ == "__main__":
    raise SystemExit(main())
