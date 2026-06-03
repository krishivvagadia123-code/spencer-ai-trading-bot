"""
Nifty Midcap 100 daily predictive-power test (Option B, path 2).

Same honest IC framework as bot/feature_eval, on a MID-CAP universe (less efficient than
large-caps, so more plausible edge), with five features and TWO extra robustness layers the
user asked for: monthly stability and walk-forward survival.

Features:
  1. relative_strength            — return minus the broad index over a lookback.
  2. breakout_quality             — (close - prior-N high) / ATR.
  3. volume_expansion_quality     — volume z-score vs recent average.
  4. mean_reversion_after_failure — failed-breakout magnitude (expects reversion).
  5. sector_strength              — mean relative strength of sector peers.

For each feature we report: IC in-sample, IC out-of-sample, OOS quintile spread, whether the
cost-adjusted edge clears ~0.25% round-trip, monthly sign-stability, a per-quarter IC table,
and a walk-forward survival verdict (sign must persist on a majority of forward quarters AND
keep |IC| >= IC_MIN). No trading, no fitting, nothing deployed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bot import features as F
from bot.backtest import fetch_history
from bot.feature_eval import spearman_ic, quintile_spread
from workflow.research_automation import (
    add_research_workflow_args,
    finalize_from_args,
    print_research_workflow_summary,
)

HORIZON = 5
RS_PERIOD = 20
IC_MIN = 0.03
COST_HURDLE = 0.003   # OOS quintile spread must exceed ~0.25% round-trip + margin

# Approximate Nifty Midcap 100 universe (liquid mid-caps). yfinance 404s are skipped, so a
# few misses don't matter — the point is a mid-cap-tilted panel, not exact index membership.
MIDCAP100 = [
    "AUBANK", "ASHOKLEY", "AUROPHARMA", "BALKRISIND", "BANDHANBNK", "BHARATFORG", "BHEL",
    "BIOCON", "COFORGE", "CONCOR", "CUMMINSIND", "DALBHARAT", "DIXON", "ESCORTS", "EXIDEIND",
    "FEDERALBNK", "GODREJPROP", "GUJGASLTD", "HINDPETRO", "IDFCFIRSTB", "INDHOTEL",
    "INDUSTOWER", "IPCALAB", "JUBLFOOD", "LICHSGFIN", "LUPIN", "MFSL", "MPHASIS", "MRF",
    "MUTHOOTFIN", "NMDC", "OBEROIRLTY", "OFSS", "PAGEIND", "PERSISTENT", "PETRONET", "PIIND",
    "POLYCAB", "PFC", "RECLTD", "SAIL", "SRF", "SUNTV", "SUPREMEIND", "TATACOMM", "TATAPOWER",
    "TIINDIA", "TORNTPHARM", "TVSMOTOR", "UBL", "UNIONBANK", "VOLTAS", "ZYDUSLIFE", "ABCAPITAL",
    "ALKEM", "APLAPOLLO", "ASTRAL", "BANKINDIA", "BSE", "CGPOWER", "CHOLAFIN", "COLPAL",
    "CROMPTON", "DELHIVERY", "DEEPAKNTR", "GODREJIND", "HDFCAMC", "HINDZINC", "HUDCO",
    "ICICIGI", "ICICIPRULI", "IDEA", "IGL", "INDIANB", "IRFC", "JINDALSTEL", "JSWENERGY",
    "KPITTECH", "LTF", "MAHABANK", "MANKIND", "MARICO", "MAXHEALTH", "MOTHERSON", "NHPC",
    "NYKAA", "OIL", "PAYTM", "PHOENIXLTD", "PRESTIGE", "SJVN", "SOLARINDS", "SONACOMS",
    "SUZLON", "TATAELXSI", "TATATECH", "UPL", "VBL", "YESBANK",
]

# Coarse sector map (best-effort; unmapped -> OTHER). Used only for sector_strength peers.
_SEC = {
    "BANK": ["AUBANK", "BANDHANBNK", "FEDERALBNK", "IDFCFIRSTB", "UNIONBANK", "BANKINDIA",
             "INDIANB", "MAHABANK", "YESBANK"],
    "FIN": ["ABCAPITAL", "CHOLAFIN", "HDFCAMC", "ICICIGI", "ICICIPRULI", "LICHSGFIN",
            "MUTHOOTFIN", "MFSL", "PFC", "RECLTD", "IRFC", "LTF", "PAYTM"],
    "PHARMA": ["AUROPHARMA", "BIOCON", "IPCALAB", "LUPIN", "TORNTPHARM", "ZYDUSLIFE",
               "ALKEM", "MANKIND", "MAXHEALTH"],
    "IT": ["COFORGE", "MPHASIS", "OFSS", "PERSISTENT", "KPITTECH", "TATAELXSI", "TATATECH"],
    "AUTO": ["ASHOKLEY", "BALKRISIND", "BHARATFORG", "ESCORTS", "EXIDEIND", "MRF", "TVSMOTOR",
             "TIINDIA", "MOTHERSON", "SONACOMS"],
    "ENERGY": ["HINDPETRO", "PETRONET", "TATAPOWER", "PFC", "NHPC", "JSWENERGY", "OIL",
               "SJVN", "SUZLON", "IGL", "GUJGASLTD"],
    "METAL": ["NMDC", "SAIL", "JINDALSTEL", "HINDZINC", "APLAPOLLO"],
    "CONSUMER": ["DIXON", "JUBLFOOD", "PAGEIND", "UBL", "VOLTAS", "COLPAL", "CROMPTON",
                 "MARICO", "NYKAA", "VBL", "SUNTV", "INDHOTEL"],
    "INDUSTRIAL": ["BHEL", "CONCOR", "CUMMINSIND", "POLYCAB", "SUPREMEIND", "CGPOWER",
                   "ASTRAL", "SOLARINDS", "DELHIVERY", "SRF", "PIIND", "DEEPAKNTR", "UPL"],
    "REALTY": ["GODREJPROP", "OBEROIRLTY", "PHOENIXLTD", "PRESTIGE", "HUDCO"],
    "MATERIALS": ["DALBHARAT"],
    "TELECOM": ["INDUSTOWER", "IDEA", "TATACOMM"],
}
SECTORS = {s: sec for sec, syms in _SEC.items() for s in syms}


def _fetch_bench(years: int) -> pd.Series | None:
    """Broad-market reference for relative strength. Try a midcap index, else Nifty 50."""
    import yfinance as yf
    for ticker in ("^CNXMIDCAP", "^NSEMDCP100", "^NSEI"):
        try:
            raw = yf.download(ticker, period=f"{years}y", interval="1d",
                              auto_adjust=False, progress=False, threads=False)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.rename(columns={c: str(c).lower() for c in raw.columns})
        s = raw["close"].dropna()
        s.index = [pd.to_datetime(x).date() for x in s.index]
        s.name = ticker
        return s
    return None


def build_panel(symbols: list[str], years: int) -> tuple[pd.DataFrame, str]:
    bench = _fetch_bench(years)
    if bench is None:
        raise RuntimeError("could not fetch a benchmark index")
    rs_by_symbol: dict[str, pd.Series] = {}
    frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = fetch_history(sym, years)
        if df is None:
            continue
        df = df.copy()
        df.index = [pd.to_datetime(x).date() for x in df.index]
        b = bench.reindex(df.index).ffill()
        rs = F.relative_strength(df["close"], b, RS_PERIOD)
        rs_by_symbol[sym] = rs
        df["rs"] = rs
        df["bq"] = F.breakout_quality(df)
        df["vq"] = F.volume_expansion_quality(df)
        df["mr"] = F.mean_reversion_after_failure(df)
        df["fwd"] = F.forward_return(df["close"], HORIZON)
        frames[sym] = df

    rs_wide = pd.DataFrame(rs_by_symbol)
    sector_of = {s: SECTORS.get(s, "OTHER") for s in rs_wide.columns}
    sector_mean: dict[str, pd.Series] = {}
    for sec in set(sector_of.values()):
        cols = [s for s in rs_wide.columns if sector_of[s] == sec]
        for s in cols:
            peers = [c for c in cols if c != s]
            sector_mean[s] = rs_wide[peers].mean(axis=1) if peers else pd.Series(dtype=float)

    rows = []
    for sym, df in frames.items():
        ss = sector_mean.get(sym)
        df["ss"] = ss.reindex(df.index) if ss is not None and len(ss) else np.nan
        tmp = df[["rs", "bq", "vq", "mr", "ss", "fwd"]].copy()
        tmp["symbol"] = sym
        tmp["date"] = df.index
        rows.append(tmp)
    return pd.concat(rows, ignore_index=True), bench.name


def _period_ic(panel: pd.DataFrame, col: str, freq: str) -> list[tuple[str, float]]:
    """IC per calendar period (freq='M' month or 'Q' quarter)."""
    p = panel[[col, "fwd", "date"]].copy()
    p["dt"] = pd.to_datetime(p["date"])
    out = []
    for key, g in p.groupby(p["dt"].dt.to_period(freq)):
        ic = spearman_ic(g[col], g["fwd"])
        if ic is not None:
            out.append((str(key), round(ic, 4)))
    return out


def evaluate(symbols: list[str], years: int = 2) -> dict:
    panel, bench_name = build_panel(symbols, years)
    dates = sorted(panel["date"].unique())
    split = dates[len(dates) // 2]
    is_mask = panel["date"] <= split
    oos_mask = panel["date"] > split

    feats = {
        "relative_strength": "rs", "breakout_quality": "bq",
        "volume_expansion_quality": "vq", "mean_reversion_after_failure": "mr",
        "sector_strength": "ss",
    }
    results = {}
    for name, col in feats.items():
        ic_is = spearman_ic(panel.loc[is_mask, col], panel.loc[is_mask, "fwd"])
        ic_oos = spearman_ic(panel.loc[oos_mask, col], panel.loc[oos_mask, "fwd"])
        qs = quintile_spread(panel.loc[oos_mask, col], panel.loc[oos_mask, "fwd"])
        monthly = _period_ic(panel, col, "M")
        quarterly = _period_ic(panel, col, "Q")

        sign_stable = (ic_is is not None and ic_oos is not None
                       and np.sign(ic_is) == np.sign(ic_oos) and abs(ic_oos) >= IC_MIN)
        spread = abs(qs["spread"]) if qs else 0.0
        clears = spread > COST_HURDLE
        # Monthly stability: fraction of months sharing the OOS IC sign.
        msf = None
        if ic_oos is not None and monthly:
            sign = np.sign(ic_oos)
            msf = round(sum(1 for _, v in monthly if np.sign(v) == sign) / len(monthly), 2)
        # Walk-forward survival: forward quarters (after split) majority same sign + |IC|>=MIN.
        fwd_q = [(k, v) for k, v in quarterly
                 if pd.Period(k).start_time.date() > split]
        wf_survive = False
        if ic_oos is not None and fwd_q:
            sign = np.sign(ic_oos)
            same = sum(1 for _, v in fwd_q if np.sign(v) == sign)
            wf_survive = bool(same > len(fwd_q) / 2 and abs(ic_oos) >= IC_MIN and clears)

        results[name] = {
            "ic_in_sample": round(ic_is, 4) if ic_is is not None else None,
            "ic_out_sample": round(ic_oos, 4) if ic_oos is not None else None,
            "oos_quintile_spread": qs,
            "direction": (None if ic_oos is None else
                          ("momentum" if ic_oos > 0 else "mean-reversion")),
            "monthly_sign_frac": msf, "n_months": len(monthly),
            "quarterly_ic": quarterly,
            "sign_stable": bool(sign_stable), "clears_costs": bool(clears),
            "walk_forward_survives": wf_survive,
            "usable": bool(sign_stable and clears and wf_survive),
        }

    usable = [k for k, v in results.items() if v["usable"]]
    n_obs = int(panel[list(feats.values()) + ["fwd"]].dropna().shape[0])
    if usable:
        verdict = (f"{len(usable)} midcap feature(s) SURVIVE walk-forward AND beat costs: "
                   f"{usable}. Candidate(s) worth a controlled, out-of-sample strategy test "
                   "(still not deployed).")
    else:
        verdict = ("NO midcap feature survives walk-forward with a cost-clearing edge. "
                   "Midcaps show the same lack of exploitable daily technical edge as "
                   "Nifty-50 — do NOT build a strategy on these features.")
    return {"benchmark": bench_name, "symbols": len(panel["symbol"].unique()),
            "observations": n_obs, "split_date": str(split), "horizon_days": HORIZON,
            "features": results, "usable_features": usable, "verdict": verdict}


def _s(x) -> str:
    return f"{x:+.4f}" if isinstance(x, (int, float)) else "n/a"


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="bot.midcap_eval")
    p.add_argument("--years", type=int, default=2)
    add_research_workflow_args(p)
    args = p.parse_args(argv)
    print(f"Nifty Midcap 100 daily IC eval: {len(MIDCAP100)} symbols, {args.years}y, "
          f"forward {HORIZON}d\n")
    r = evaluate(MIDCAP100, args.years)
    print(f"Benchmark: {r['benchmark']} | symbols used: {r['symbols']} | "
          f"obs: {r['observations']:,} | IS/OOS split {r['split_date']}\n")
    print(f"{'feature':<28}{'IC in':>9}{'IC oos':>9}{'OOS q5-q1':>11}{'dir':>14}"
          f"{'mo-stable':>10}{'wf-surv':>9}{'usable':>8}")
    print("-" * 97)
    for name, v in r["features"].items():
        qs = v["oos_quintile_spread"]
        spread = f"{qs['spread']:+.4f}" if qs else "n/a"
        mo = f"{v['monthly_sign_frac']:.0%}" if v["monthly_sign_frac"] is not None else "n/a"
        wf = "yes" if v["walk_forward_survives"] else "no"
        usable = "YES" if v["usable"] else ("stable*" if v["sign_stable"] else "no")
        print(f"{name:<28}{_s(v['ic_in_sample']):>9}{_s(v['ic_out_sample']):>9}{spread:>11}"
              f"{(v['direction'] or '—'):>14}{mo:>10}{wf:>9}{usable:>8}")
    print("\n  * sign-stable IS/OOS but fails the cost hurdle and/or walk-forward.")
    print(f"\nVERDICT: {r['verdict']}")
    print("\n(No trades taken. No fitting. Nothing deployed or wired to live.)")
    print_research_workflow_summary(finalize_from_args("midcap_eval", r, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
