"""
Intraday predictive-power evaluation (Option B, path 1).

Same honest IC framework as bot/feature_eval, moved to INTRADAY 15-minute candles on the
Nifty-50, with intraday-native features the user asked for:
  1. opening_range  — position vs the first-30-min opening range (>1 = above OR high).
  2. vwap_distance  — % distance from the session-anchored VWAP (resets each day).
  3. volume_shock   — within-day volume z-score (conviction behind the bar).
  4. relative_strength — stock's last-hour return minus Nifty's (intraday leadership).

Target: WITHIN-DAY forward return over HORIZON_BARS (never crosses the overnight gap).
All features are causal (computed at the bar close). No trading, no fitting, no deploy.

Hard constraint (stated, not hidden): yfinance serves only ~60 days of intraday history,
so this is ~2.5 months. IS/OOS split is ~29 days each and "stability" is measured by WEEK,
not quarter. A feature that fails here is dead; one that passes is only a candidate that
would still need a longer-history confirmation before any strategy work.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bot.backtest import NIFTY50
from bot.feature_eval import spearman_ic, quintile_spread
from workflow.research_automation import (
    add_research_workflow_args,
    finalize_from_args,
    print_research_workflow_summary,
)

INTERVAL = "15m"
PERIOD = "60d"
HORIZON_BARS = 4      # ~1 hour forward at 15m
OR_BARS = 2           # first 30 minutes = opening range
RS_BARS = 4           # ~1 hour momentum window for relative strength
VOL_WIN = 8           # ~2 hour trailing volume window
COST_HURDLE = 0.0015  # ~0.15% intraday round-trip (brokerage + slippage; no delivery STT)
IC_MIN = 0.03


def _download(ticker: str) -> pd.DataFrame | None:
    import yfinance as yf
    try:
        df = yf.download(ticker, period=PERIOD, interval=INTERVAL,
                         progress=False, threads=False, auto_adjust=False)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    need = ["open", "high", "low", "close", "volume"]
    if any(c not in df.columns for c in need):
        return None
    df = df[need].dropna()
    df["day"] = [t.date() for t in df.index]
    return df


def _bench_returns() -> pd.Series | None:
    df = _download("^NSEI")
    if df is None:
        return None
    g = df.groupby("day")["close"]
    bret = df["close"] / g.transform(lambda s: s.shift(RS_BARS)) - 1.0   # within-day
    bret.index = df.index
    return bret


def per_symbol(df: pd.DataFrame, bench_ret: pd.Series) -> pd.DataFrame:
    g = df.groupby("day")
    high, low, close, vol = df["high"], df["low"], df["close"], df["volume"]

    # 1. Opening range position.
    or_high = g["high"].transform(lambda s: s.iloc[:OR_BARS].max())
    or_low = g["low"].transform(lambda s: s.iloc[:OR_BARS].min())
    or_mid = (or_high + or_low) / 2.0
    or_half = ((or_high - or_low) / 2.0).replace(0, np.nan)
    df["opening_range"] = (close - or_mid) / or_half

    # 2. VWAP distance (session-anchored, resets daily).
    typical = (high + low + close) / 3.0
    tpv = typical * vol
    cum_pv = tpv.groupby(df["day"]).cumsum()
    cum_v = vol.groupby(df["day"]).cumsum().replace(0, np.nan)
    vwap = cum_pv / cum_v
    df["vwap_distance"] = (close - vwap) / vwap

    # 3. Volume shock (within-day trailing z-score).
    vmean = g["volume"].transform(lambda s: s.rolling(VOL_WIN, min_periods=3).mean())
    vstd = g["volume"].transform(lambda s: s.rolling(VOL_WIN, min_periods=3).std()).replace(0, np.nan)
    df["volume_shock"] = (vol - vmean) / vstd

    # 4. Relative strength vs Nifty (within-day, last RS_BARS).
    ret_k = close / g["close"].transform(lambda s: s.shift(RS_BARS)) - 1.0
    bench_aligned = bench_ret.reindex(df.index)
    df["relative_strength"] = ret_k - bench_aligned

    # Target: within-day forward return.
    df["fwd"] = g["close"].transform(lambda s: s.shift(-HORIZON_BARS)) / close - 1.0
    return df


def build_panel(symbols: list[str]) -> pd.DataFrame:
    bench_ret = _bench_returns()
    if bench_ret is None:
        raise RuntimeError("could not fetch Nifty intraday for relative strength")
    rows = []
    for sym in symbols:
        df = _download(f"{sym}.NS")
        if df is None or len(df) < 100:
            continue
        df = per_symbol(df, bench_ret)
        keep = df[["opening_range", "vwap_distance", "volume_shock",
                   "relative_strength", "fwd"]].copy()
        keep["symbol"] = sym
        keep["ts"] = df.index
        keep["day"] = df["day"].values
        rows.append(keep)
    if not rows:
        raise RuntimeError("no intraday data fetched")
    return pd.concat(rows, ignore_index=True)


def _weekly_sign_stability(sub: pd.DataFrame, col: str) -> dict:
    """Fraction of weeks whose IC has the same sign as the overall OOS IC."""
    sub = sub.copy()
    sub["week"] = pd.to_datetime(sub["ts"]).dt.isocalendar().week
    overall = spearman_ic(sub[col], sub["fwd"])
    if overall is None:
        return {"weeks": 0, "same_sign_frac": None}
    sign = np.sign(overall)
    weeks = []
    for _, gdf in sub.groupby("week"):
        ic = spearman_ic(gdf[col], gdf["fwd"])
        if ic is not None:
            weeks.append(np.sign(ic) == sign)
    return {"weeks": len(weeks),
            "same_sign_frac": round(sum(weeks) / len(weeks), 2) if weeks else None}


def evaluate(symbols: list[str]) -> dict:
    panel = build_panel(symbols)
    days = sorted(panel["day"].unique())
    split = days[len(days) // 2]
    is_mask = panel["day"] <= split
    oos_mask = panel["day"] > split

    feats = ["opening_range", "vwap_distance", "volume_shock", "relative_strength"]
    results = {}
    for col in feats:
        ic_is = spearman_ic(panel.loc[is_mask, col], panel.loc[is_mask, "fwd"])
        ic_oos = spearman_ic(panel.loc[oos_mask, col], panel.loc[oos_mask, "fwd"])
        qs = quintile_spread(panel.loc[oos_mask, col], panel.loc[oos_mask, "fwd"])
        stable = (ic_is is not None and ic_oos is not None
                  and np.sign(ic_is) == np.sign(ic_oos) and abs(ic_oos) >= IC_MIN)
        spread = abs(qs["spread"]) if qs else 0.0
        clears = spread > COST_HURDLE
        weekly = _weekly_sign_stability(panel.loc[oos_mask], col)
        results[col] = {
            "ic_in_sample": round(ic_is, 4) if ic_is is not None else None,
            "ic_out_sample": round(ic_oos, 4) if ic_oos is not None else None,
            "oos_quintile_spread": qs,
            "direction": (None if ic_oos is None else
                          ("momentum/continuation" if ic_oos > 0 else "mean-reversion/fade")),
            "weekly_sign_stability": weekly,
            "sign_stable": bool(stable),
            "clears_costs": bool(clears),
            "usable": bool(stable and clears),
        }

    usable = [k for k, v in results.items() if v["usable"]]
    stable_only = [k for k, v in results.items() if v["sign_stable"] and not v["usable"]]
    n_obs = int(panel[["opening_range", "vwap_distance", "volume_shock",
                       "relative_strength", "fwd"]].dropna().shape[0])
    if usable:
        verdict = f"{len(usable)} intraday feature(s) USABLE (stable + beats costs): {usable}."
    elif stable_only:
        verdict = (f"NONE usable. {stable_only} sign-stable but edge < ~0.15% intraday cost. "
                   "Candidate only — would need longer history to confirm.")
    else:
        verdict = (f"NONE of the intraday features show stable OOS predictive power "
                   f"(|IC|>={IC_MIN}). No intraday edge found in this 2.5-month window.")
    return {"interval": INTERVAL, "symbols": len(panel["symbol"].unique()),
            "observations": n_obs, "trading_days": len(days), "split_day": str(split),
            "horizon_bars": HORIZON_BARS, "features": results,
            "usable_features": usable, "verdict": verdict}


def _s(x) -> str:
    return f"{x:+.4f}" if isinstance(x, (int, float)) else "n/a"


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="bot.intraday_eval")
    p.add_argument("--top", type=int, default=50)
    add_research_workflow_args(p)
    args = p.parse_args(argv)
    symbols = NIFTY50[: args.top]
    print(f"Intraday IC eval: {INTERVAL} candles, {len(symbols)} Nifty-50 symbols, "
          f"forward {HORIZON_BARS} bars (~1h)\n")
    r = evaluate(symbols)
    print(f"Observations: {r['observations']:,} | {r['trading_days']} days | "
          f"IS/OOS split {r['split_day']}\n")
    print(f"{'feature':<20}{'IC in':>9}{'IC oos':>9}{'OOS q5-q1':>11}"
          f"{'direction':>22}{'wk-stable':>11}{'usable':>8}")
    print("-" * 90)
    for name, v in r["features"].items():
        qs = v["oos_quintile_spread"]
        spread = f"{qs['spread']:+.4f}" if qs else "n/a"
        wk = v["weekly_sign_stability"]
        wkf = f"{wk['same_sign_frac']:.0%}" if wk.get("same_sign_frac") is not None else "n/a"
        usable = "YES" if v["usable"] else ("stable*" if v["sign_stable"] else "no")
        print(f"{name:<20}{_s(v['ic_in_sample']):>9}{_s(v['ic_out_sample']):>9}"
              f"{spread:>11}{(v['direction'] or '—'):>22}{wkf:>11}{usable:>8}")
    print("\n  * sign-stable across IS/OOS but edge below the ~0.15% intraday cost hurdle.")
    print(f"\nVERDICT: {r['verdict']}")
    print("\n(No trades taken. No fitting. Nothing deployed or wired to live.)")
    print_research_workflow_summary(finalize_from_args("intraday_eval", r, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
