"""
Read-only FII/DII market-flow predictive-power research.

Tests whether aggregate institutional cash-market flows predict index forward
returns. This is market-timing research only: no entries, exits, sizing, broker
execution, live trading, or strategy deployment.
"""

from __future__ import annotations

import argparse
from typing import Optional

import numpy as np
import pandas as pd

from bot.feature_eval import quintile_spread, spearman_ic
from bot import nse_flows
from workflow.research_automation import (
    add_research_workflow_args,
    finalize_from_args,
    print_research_workflow_summary,
)


INDEX_TICKER = "^NSEI"
HORIZONS = (1, 5)
ROLLING_WINDOW = 20
IC_MIN = 0.03
COST_HURDLE = 0.0025
MIN_OBSERVATIONS = 100

FEATURE_DEFINITIONS = {
    "fii_net": "FII/FPI net cash market flow in Rs crore; positive means net buying.",
    "dii_net": "DII net cash market flow in Rs crore; positive means net buying.",
    "fii_minus_dii": "FII net flow minus DII net flow; positive means foreign flow leads domestic flow.",
    "fii_plus_dii": "Combined institutional net flow; positive means aggregate institutional buying.",
    "fii_net_z": "20-session z-score of FII/FPI net cash flow.",
    "dii_net_z": "20-session z-score of DII net cash flow.",
    "fii_minus_dii_z": "20-session z-score of FII-minus-DII flow.",
}


def add_flow_features(flows: pd.DataFrame, window: int = ROLLING_WINDOW) -> pd.DataFrame:
    out = flows.copy()
    out["fii_net"] = pd.to_numeric(out["fii_net"], errors="coerce")
    out["dii_net"] = pd.to_numeric(out["dii_net"], errors="coerce")
    out["fii_minus_dii"] = out["fii_net"] - out["dii_net"]
    out["fii_plus_dii"] = out["fii_net"] + out["dii_net"]
    for col in ("fii_net", "dii_net", "fii_minus_dii"):
        mean = out[col].rolling(window, min_periods=max(5, window // 4)).mean()
        std = out[col].rolling(window, min_periods=max(5, window // 4)).std().replace(0, np.nan)
        out[f"{col}_z"] = (out[col] - mean) / std
    return out


def fetch_index_history(years: int = 2, ticker: str = INDEX_TICKER) -> pd.DataFrame | None:
    try:
        import yfinance as yf

        raw = yf.download(ticker, period=f"{years}y", interval="1d", auto_adjust=False, progress=False, threads=False)
    except Exception:
        return None
    if raw is None or raw.empty:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw.rename(columns={c: str(c).lower() for c in raw.columns})
    if "close" not in df.columns:
        return None
    return df[["close"]].dropna()


def build_panel(flows: pd.DataFrame, index_df: pd.DataFrame, horizons: tuple[int, ...] = HORIZONS) -> pd.DataFrame | None:
    if flows is None or flows.empty or index_df is None or index_df.empty:
        return None
    flow_features = add_flow_features(flows)
    flow_features["date"] = pd.to_datetime(flow_features["date"]).dt.date

    px = index_df.copy()
    px.index = [pd.to_datetime(x).date() for x in px.index]
    px = px.rename(columns={c: str(c).lower() for c in px.columns})
    if "close" not in px.columns:
        return None
    dates = list(px.index)
    closes = px["close"].astype(float).tolist()

    rows = []
    for _, row in flow_features.iterrows():
        event_date = row["date"]
        entry_idx = _first_index_after(dates, event_date)
        if entry_idx is None:
            continue
        rec = {col: row.get(col) for col in FEATURE_DEFINITIONS}
        rec["date"] = event_date
        rec["entry_date"] = dates[entry_idx]
        for horizon in horizons:
            if entry_idx + horizon >= len(closes):
                rec[f"fwd_{horizon}d"] = np.nan
                continue
            entry = float(closes[entry_idx])
            rec[f"fwd_{horizon}d"] = (float(closes[entry_idx + horizon]) / entry - 1.0) if entry > 0 else np.nan
        rows.append(rec)

    if not rows:
        return None
    panel = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
    return panel


def evaluate_panel(panel: pd.DataFrame, *, availability: dict, universe: str = "nifty50") -> dict:
    clean = panel.copy().replace([np.inf, -np.inf], np.nan)
    clean["date"] = pd.to_datetime(clean["date"]).dt.date
    dates = sorted(clean["date"].dropna().unique())
    if len(dates) < 2:
        return _unavailable_result(universe, availability, "not enough dated flow/index observations")
    split = dates[len(dates) // 2]
    results = {}

    for horizon in HORIZONS:
        target = f"fwd_{horizon}d"
        for feature in FEATURE_DEFINITIONS:
            key = f"{feature}_{horizon}d"
            sub = clean[["date", feature, target]].dropna().copy()
            observations = int(len(sub))
            if observations == 0:
                results[key] = _empty_feature_result(feature, horizon, observations)
                continue
            is_mask = sub["date"] <= split
            oos_mask = sub["date"] > split
            ic_all = spearman_ic(sub[feature], sub[target])
            ic_is = spearman_ic(sub.loc[is_mask, feature], sub.loc[is_mask, target])
            ic_oos = spearman_ic(sub.loc[oos_mask, feature], sub.loc[oos_mask, target])
            qs = quintile_spread(sub.loc[oos_mask, feature], sub.loc[oos_mask, target])
            monthly = _period_ic(sub, feature, target, "M", min_n=5)
            quarterly = _period_ic(sub, feature, target, "Q", min_n=10)
            raw_spread = qs["spread"] if qs else None
            economic_spread = None
            if raw_spread is not None and ic_oos is not None:
                economic_spread = raw_spread if ic_oos >= 0 else -raw_spread
            cost_adjusted_edge = None if economic_spread is None else round(float(economic_spread - COST_HURDLE), 5)
            clears_costs = bool(cost_adjusted_edge is not None and cost_adjusted_edge > 0)
            sign_stable = bool(
                ic_is is not None and ic_oos is not None
                and np.sign(ic_is) == np.sign(ic_oos)
                and abs(ic_oos) >= IC_MIN
            )
            monthly_sign_frac = _same_sign_fraction(monthly, ic_oos)
            quarterly_sign_frac = _same_sign_fraction(quarterly, ic_oos)
            walk_forward = _walk_forward_survives(quarterly, split, ic_oos, clears_costs)
            usable = bool(observations >= MIN_OBSERVATIONS and sign_stable and clears_costs and walk_forward)
            needs_confirmation = bool(observations >= MIN_OBSERVATIONS and not usable and (sign_stable or clears_costs))
            status = "PASS" if usable else ("NEEDS CONFIRMATION" if needs_confirmation else "FAIL")
            direction = None if ic_oos is None else ("higher_flow_bullish" if ic_oos > 0 else "higher_flow_bearish")
            results[key] = {
                "feature": feature,
                "horizon_days": horizon,
                "observations": observations,
                "ic_all": round(ic_all, 4) if ic_all is not None else None,
                "ic_in_sample": round(ic_is, 4) if ic_is is not None else None,
                "ic_out_sample": round(ic_oos, 4) if ic_oos is not None else None,
                "oos_quintile_spread": qs,
                "direction": direction,
                "cost_adjusted_edge": cost_adjusted_edge,
                "clears_costs": clears_costs,
                "monthly_sign_frac": monthly_sign_frac,
                "quarterly_sign_frac": quarterly_sign_frac,
                "monthly_ic": monthly,
                "quarterly_ic": quarterly,
                "sign_stable": sign_stable,
                "walk_forward_survives": walk_forward,
                "status": status,
                "usable": usable,
            }

    observations = int(max((item.get("observations", 0) for item in results.values()), default=0))
    availability = dict(availability or {})
    availability["overlapping_observations"] = observations
    usable = [name for name, item in results.items() if item.get("usable")]
    candidates = [name for name, item in results.items() if item.get("status") == "NEEDS CONFIRMATION"]
    limitations = _limitations(availability, observations)
    if observations < MIN_OBSERVATIONS:
        verdict = (
            f"DATA_UNAVAILABLE: only {observations} usable FII/DII flow-index observations "
            f"(< {MIN_OBSERVATIONS}). Do NOT build a strategy."
        )
    elif usable:
        verdict = (
            f"PASS: {len(usable)} FII/DII flow feature(s) survive IS/OOS, costs, and walk-forward "
            f"in {universe}: {usable}. Research only, not deployed."
        )
    elif candidates:
        verdict = (
            f"NEEDS CONFIRMATION: {candidates} show partial FII/DII timing evidence but fail one "
            "or more gates. Do NOT build a strategy."
        )
    else:
        verdict = (
            f"FAIL: no FII/DII flow feature in {universe} shows stable OOS predictive power, "
            "cost-adjusted edge, and walk-forward survival. Do NOT build a strategy."
        )
    return {
        "module": "flows_eval",
        "universe": universe,
        "data_availability": availability,
        "feature_definitions": FEATURE_DEFINITIONS,
        "observations": observations,
        "horizons": list(HORIZONS),
        "split_date": str(split),
        "cost_hurdle": COST_HURDLE,
        "ic_min_threshold": IC_MIN,
        "results": results,
        "usable_features": usable,
        "candidates": candidates,
        "limitations": limitations,
        "verdict": verdict,
    }


def evaluate(years: int = 2, *, universe: str = "nifty50") -> dict:
    availability = {
        "source": "NSE FII/DII provisional cash market endpoint",
        "flow_rows": 0,
        "index_rows": 0,
        "overlapping_observations": 0,
    }
    flows = nse_flows.flow_history(years=years)
    if flows is None or flows.empty:
        return _unavailable_result(universe, availability, "NSE FII/DII flow data could not be fetched")
    availability["flow_rows"] = int(len(flows))
    availability["flow_start"] = str(pd.to_datetime(flows["date"]).min().date())
    availability["flow_end"] = str(pd.to_datetime(flows["date"]).max().date())
    availability["source_counts"] = getattr(flows, "attrs", {}).get("source_counts", {})
    if len(flows) < MIN_OBSERVATIONS:
        return _unavailable_result(
            universe,
            availability,
            f"only {len(flows)} real FII/DII flow row(s) available; {MIN_OBSERVATIONS} required",
        )

    index_df = fetch_index_history(years)
    if index_df is None or index_df.empty:
        return _unavailable_result(universe, availability, "index history could not be fetched")
    availability["index_rows"] = int(len(index_df))
    panel = build_panel(flows, index_df)
    if panel is None or panel.empty:
        return _unavailable_result(universe, availability, "no overlapping flow/index forward-return rows")
    return evaluate_panel(panel, availability=availability, universe=universe)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bot.flows_eval")
    parser.add_argument("--years", type=int, default=2)
    add_research_workflow_args(parser)
    args = parser.parse_args(argv)

    result = evaluate(args.years)
    _print_report(result)
    print_research_workflow_summary(finalize_from_args("flows_eval", result, args))
    return 0


def _first_index_after(dates: list, event_date) -> Optional[int]:
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] > event_date:
            hi = mid
        else:
            lo = mid + 1
    return lo if lo < len(dates) else None


def _empty_feature_result(feature: str, horizon: int, observations: int) -> dict:
    return {
        "feature": feature,
        "horizon_days": horizon,
        "observations": observations,
        "ic_all": None,
        "ic_in_sample": None,
        "ic_out_sample": None,
        "oos_quintile_spread": None,
        "direction": None,
        "cost_adjusted_edge": None,
        "clears_costs": False,
        "monthly_sign_frac": None,
        "quarterly_sign_frac": None,
        "monthly_ic": [],
        "quarterly_ic": [],
        "sign_stable": False,
        "walk_forward_survives": False,
        "status": "FAIL",
        "usable": False,
    }


def _period_ic(panel: pd.DataFrame, feature: str, target: str, freq: str, *, min_n: int) -> list[tuple[str, float]]:
    p = panel[[feature, target, "date"]].dropna().copy()
    p["dt"] = pd.to_datetime(p["date"])
    out = []
    for key, group in p.groupby(p["dt"].dt.to_period(freq)):
        ic = _spearman_min(group[feature], group[target], min_n=min_n)
        if ic is not None:
            out.append((str(key), round(ic, 4)))
    return out


def _spearman_min(feature: pd.Series, fwd: pd.Series, *, min_n: int) -> Optional[float]:
    df = pd.DataFrame({"f": feature, "r": fwd}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(df) < min_n or df["f"].nunique() < 3:
        return None
    rf = df["f"].rank()
    rr = df["r"].rank()
    c = np.corrcoef(rf, rr)[0, 1]
    return float(c) if np.isfinite(c) else None


def _same_sign_fraction(periods: list[tuple[str, float]], ic_oos: Optional[float]) -> Optional[float]:
    if ic_oos is None or not periods:
        return None
    sign = np.sign(ic_oos)
    return round(sum(1 for _, value in periods if np.sign(value) == sign) / len(periods), 2)


def _walk_forward_survives(
    quarterly: list[tuple[str, float]],
    split: object,
    ic_oos: Optional[float],
    clears_costs: bool,
) -> bool:
    if ic_oos is None or not quarterly or not clears_costs or abs(ic_oos) < IC_MIN:
        return False
    split_date = pd.Timestamp(split).date()
    forward = [(key, value) for key, value in quarterly if pd.Period(key).start_time.date() > split_date]
    if not forward:
        return False
    sign = np.sign(ic_oos)
    same = sum(1 for _, value in forward if np.sign(value) == sign)
    return bool(same > len(forward) / 2)


def _limitations(availability: dict, observations: int) -> list[str]:
    limitations = [
        "NSE FII/DII values are provisional cash-market aggregate rows and can change after custodial confirmation.",
        "FII/DII is market-level data; this module makes no per-stock selection claim.",
        "Flow data is evaluated only after publication; no intraday or same-close timing is implied.",
        "This module measures predictive power only and does not define entries, exits, sizing, or deployment.",
    ]
    if observations < MIN_OBSERVATIONS:
        limitations.insert(0, "Usable flow/index observation count is below the pre-set research threshold.")
    if availability.get("flow_rows", 0) == 0:
        limitations.insert(0, "No real FII/DII flow rows were available.")
    return limitations


def _unavailable_result(universe: str, availability: dict, reason: str) -> dict:
    availability = dict(availability or {})
    observations = int(availability.get("overlapping_observations") or 0)
    limitations = _limitations(availability, observations)
    limitations.insert(0, reason)
    return {
        "module": "flows_eval",
        "universe": universe,
        "data_availability": availability,
        "feature_definitions": FEATURE_DEFINITIONS,
        "observations": observations,
        "horizons": list(HORIZONS),
        "cost_hurdle": COST_HURDLE,
        "ic_min_threshold": IC_MIN,
        "results": {},
        "usable_features": [],
        "candidates": [],
        "limitations": limitations,
        "verdict": f"DATA_UNAVAILABLE: {reason}. Do NOT build a strategy.",
    }


def _print_report(result: dict) -> None:
    print("FII/DII market-flow predictive-power research")
    print("Read-only: no trades, no strategy, no broker execution, no live trading.\n")
    availability = result.get("data_availability", {})
    print("Data availability")
    print(
        f"  flow_rows={availability.get('flow_rows', 0)} "
        f"index_rows={availability.get('index_rows', 0)} "
        f"observations={result.get('observations', 0)}"
    )
    if availability.get("source_counts"):
        sources = " ".join(f"{k}={v}" for k, v in sorted(availability["source_counts"].items()))
        print(f"  sources: {sources}")
    if availability.get("flow_start") and availability.get("flow_end"):
        print(f"  flow_range={availability.get('flow_start')}..{availability.get('flow_end')}")

    print("\nFlow feature definitions")
    for name, definition in result.get("feature_definitions", {}).items():
        print(f"  - {name}: {definition}")

    results = result.get("results") or {}
    if results:
        print(f"\nTiming metrics | split={result.get('split_date')} cost_hurdle={COST_HURDLE:.2%}")
        print(
            f"  {'feature_horizon':<24}{'obs':>6}{'IC in':>9}{'IC oos':>9}"
            f"{'Q spread':>10}{'costAdj':>10}{'mo':>7}{'qtr':>7}{'wf':>5}{'status':>20}"
        )
        for name, values in results.items():
            qs = values.get("oos_quintile_spread")
            spread = qs.get("spread") if qs else None
            print(
                f"  {name:<24}{values.get('observations', 0):>6}"
                f"{_fmt(values.get('ic_in_sample')):>9}"
                f"{_fmt(values.get('ic_out_sample')):>9}"
                f"{_fmt(spread):>10}"
                f"{_fmt(values.get('cost_adjusted_edge')):>10}"
                f"{_pct(values.get('monthly_sign_frac')):>7}"
                f"{_pct(values.get('quarterly_sign_frac')):>7}"
                f"{('yes' if values.get('walk_forward_survives') else 'no'):>5}"
                f"{values.get('status', 'FAIL'):>20}"
            )
    else:
        print("\nTiming metrics unavailable: not enough real flow/index observations.")

    print("\nLimitations:")
    for item in result.get("limitations", []):
        print(f"  - {item}")
    print(f"\nVERDICT: {result['verdict']}")


def _fmt(value) -> str:
    return f"{value:+.4f}" if isinstance(value, (int, float)) else "n/a"


def _pct(value) -> str:
    return f"{value:.0%}" if isinstance(value, (int, float)) else "n/a"


if __name__ == "__main__":
    raise SystemExit(main())
