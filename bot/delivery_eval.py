"""
Read-only delivery-volume predictive-power research.

Measures whether NSE deliverable quantity / delivery percent predicts 5-day
forward returns. It is research only: no strategy, no orders, no live trading,
no broker execution, and no fake NSE data.
"""

from __future__ import annotations

import argparse
from typing import Optional

import numpy as np
import pandas as pd

from bot.backtest import NIFTY50, fetch_history
from bot.feature_eval import quintile_spread, spearman_ic
from bot.midcap_eval import MIDCAP100
from bot import nse_delivery
from workflow.research_automation import (
    add_research_workflow_args,
    finalize_from_args,
    print_research_workflow_summary,
)


HORIZON = 5
ROLLING_WINDOW = 20
IC_MIN = 0.03
COST_HURDLE = 0.003
MIN_OBSERVATIONS = 100

FEATURES = {
    "delivery_pct": "delivery_pct",
    "delivery_pct_zscore": "delivery_pct_zscore",
    "delivery_spike": "delivery_spike",
}


def add_delivery_features(df: pd.DataFrame, window: int = ROLLING_WINDOW) -> pd.DataFrame:
    out = df.copy()
    pct = out["delivery_pct"].astype(float)
    traded = out["traded_qty"].astype(float)
    pct_mean = pct.rolling(window).mean()
    pct_std = pct.rolling(window).std().replace(0, np.nan)
    vol_mean = traded.rolling(window).mean()
    out["delivery_pct_zscore"] = (pct - pct_mean) / pct_std
    high_delivery = pct >= (pct_mean + pct_std)
    above_avg_volume = traded > vol_mean
    out["delivery_spike"] = (high_delivery & above_avg_volume).astype(float)
    return out


def build_symbol_panel(symbol: str, price: pd.DataFrame, delivery: pd.DataFrame) -> pd.DataFrame | None:
    if price is None or delivery is None or price.empty or delivery.empty:
        return None
    px = price.copy()
    px.index = pd.to_datetime(px.index).normalize()
    px = px.rename(columns={c: str(c).lower() for c in px.columns})
    if "close" not in px.columns:
        return None

    dlv = delivery.copy()
    dlv.index = pd.to_datetime(dlv.index).normalize()
    need = ["traded_qty", "deliverable_qty", "delivery_pct"]
    if any(col not in dlv.columns for col in need):
        return None

    joined = px[["close"]].join(dlv[need], how="inner")
    if joined.empty:
        return None
    joined = add_delivery_features(joined)
    joined["fwd"] = joined["close"].shift(-HORIZON) / joined["close"] - 1.0
    joined["symbol"] = symbol
    joined["date"] = joined.index.date
    keep = ["symbol", "date", "delivery_pct", "delivery_pct_zscore",
            "delivery_spike", "traded_qty", "deliverable_qty", "fwd"]
    return joined[keep].replace([np.inf, -np.inf], np.nan).dropna(subset=["fwd"])


def build_panel(symbols: list[str], years: int = 2) -> tuple[pd.DataFrame | None, dict]:
    rows: list[pd.DataFrame] = []
    availability = {
        "symbols_requested": len(symbols),
        "price_symbols": 0,
        "delivery_symbols": 0,
        "symbols_used": 0,
        "unavailable_symbols": [],
        "observations": 0,
        "source": "NSE sec_bhavdata_full archives",
    }
    for symbol in symbols:
        price = fetch_history(symbol, years)
        if price is None:
            availability["unavailable_symbols"].append({"symbol": symbol, "reason": "price history unavailable"})
            continue
        availability["price_symbols"] += 1
        delivery = nse_delivery.delivery_history(symbol, years=years)
        if delivery is None:
            availability["unavailable_symbols"].append({"symbol": symbol, "reason": "NSE delivery archive unavailable"})
            continue
        availability["delivery_symbols"] += 1
        panel = build_symbol_panel(symbol, price, delivery)
        if panel is None or panel.empty:
            availability["unavailable_symbols"].append({"symbol": symbol, "reason": "no overlapping price/delivery rows"})
            continue
        rows.append(panel)

    if not rows:
        return None, availability
    panel = pd.concat(rows, ignore_index=True)
    availability["symbols_used"] = int(panel["symbol"].nunique())
    availability["observations"] = int(panel[["delivery_pct", "delivery_pct_zscore", "delivery_spike", "fwd"]].dropna().shape[0])
    return panel, availability


def evaluate_panel(panel: pd.DataFrame, *, universe: str, availability: dict) -> dict:
    clean = panel.copy().replace([np.inf, -np.inf], np.nan)
    clean["date"] = pd.to_datetime(clean["date"]).dt.date
    dates = sorted(clean["date"].dropna().unique())
    if len(dates) < 2:
        return _unavailable_result(universe, availability, "not enough dated observations")
    split = dates[len(dates) // 2]
    is_mask = clean["date"] <= split
    oos_mask = clean["date"] > split

    results = {}
    for name, col in FEATURES.items():
        ic_all = spearman_ic(clean[col], clean["fwd"])
        ic_is = spearman_ic(clean.loc[is_mask, col], clean.loc[is_mask, "fwd"])
        ic_oos = spearman_ic(clean.loc[oos_mask, col], clean.loc[oos_mask, "fwd"])
        qs = quintile_spread(clean.loc[oos_mask, col], clean.loc[oos_mask, "fwd"])
        monthly = _period_ic(clean, col, "M")
        quarterly = _period_ic(clean, col, "Q")
        direction = None if ic_oos is None else ("higher_delivery_bullish" if ic_oos > 0 else "higher_delivery_bearish")
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
        walk_forward_survives = _walk_forward_survives(quarterly, split, ic_oos, clears_costs)
        usable = bool(sign_stable and clears_costs and walk_forward_survives)
        results[name] = {
            "ic_all": round(ic_all, 4) if ic_all is not None else None,
            "ic_in_sample": round(ic_is, 4) if ic_is is not None else None,
            "ic_out_sample": round(ic_oos, 4) if ic_oos is not None else None,
            "oos_quintile_spread": qs,
            "direction": direction,
            "cost_adjusted_edge": cost_adjusted_edge,
            "clears_costs": clears_costs,
            "monthly_sign_frac": monthly_sign_frac,
            "monthly_ic": monthly,
            "quarterly_ic": quarterly,
            "sign_stable": sign_stable,
            "walk_forward_survives": walk_forward_survives,
            "usable": usable,
        }

    usable = [k for k, v in results.items() if v["usable"]]
    stable_only = [k for k, v in results.items() if v["sign_stable"] and not v["usable"]]
    observations = int(clean[list(FEATURES.values()) + ["fwd"]].dropna().shape[0])
    limitations = _limitations(availability, observations)
    if observations < MIN_OBSERVATIONS:
        verdict = (
            f"DATA UNAVAILABLE: {universe} delivery-volume panel has only {observations} "
            f"usable observations (< {MIN_OBSERVATIONS}). Do NOT build a strategy."
        )
    elif usable:
        verdict = (
            f"{len(usable)} delivery-volume feature(s) are USABLE in {universe}: {usable}. "
            "This is research only and still not a trading strategy."
        )
    elif stable_only:
        verdict = (
            f"NONE are usable in {universe}. {stable_only} has stable IC sign but does not "
            "clear costs and walk-forward together. Do NOT build a strategy."
        )
    else:
        verdict = (
            f"NO delivery-volume feature in {universe} shows stable OOS predictive power, "
            "cost-adjusted edge, and walk-forward survival. Do NOT build a strategy."
        )
    return {
        "universe": universe,
        "data_availability": availability,
        "observations": observations,
        "horizon_days": HORIZON,
        "split_date": str(split),
        "cost_hurdle": COST_HURDLE,
        "features": results,
        "usable_features": usable,
        "sign_stable_but_uneconomic": stable_only,
        "limitations": limitations,
        "verdict": verdict,
    }


def evaluate(symbols: list[str], years: int = 2, *, universe: str = "nifty50") -> dict:
    panel, availability = build_panel(symbols, years)
    if panel is None or panel.empty:
        return _unavailable_result(universe, availability, "NSE delivery archive was not fetchable for any symbol")
    return evaluate_panel(panel, universe=universe, availability=availability)


def evaluate_all(years: int = 2, *, include_midcap: bool = False, top: int = 50) -> dict:
    universes = {"nifty50": evaluate(NIFTY50[:top], years, universe="nifty50")}
    if include_midcap:
        universes["midcap100"] = evaluate(MIDCAP100, years, universe="midcap100")
    primary = universes["nifty50"]
    usable = []
    for name, result in universes.items():
        usable.extend([f"{name}:{feature}" for feature in result.get("usable_features", [])])
    verdict = primary["verdict"] if not usable else f"Delivery-volume usable candidates found: {usable}. Research only, not deployed."
    return {
        "module": "delivery_eval",
        "universes": universes,
        "data_availability": primary.get("data_availability", {}),
        "features": primary.get("features", {}),
        "usable_features": usable,
        "observations": primary.get("observations", 0),
        "horizon_days": HORIZON,
        "limitations": primary.get("limitations", []),
        "verdict": verdict,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bot.delivery_eval")
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--include-midcap", action="store_true")
    add_research_workflow_args(parser)
    args = parser.parse_args(argv)

    result = evaluate_all(args.years, include_midcap=args.include_midcap, top=args.top)
    _print_report(result)
    print_research_workflow_summary(finalize_from_args("delivery_eval", result, args))
    return 0


def _period_ic(panel: pd.DataFrame, col: str, freq: str) -> list[tuple[str, float]]:
    p = panel[[col, "fwd", "date"]].dropna().copy()
    p["dt"] = pd.to_datetime(p["date"])
    out = []
    for key, group in p.groupby(p["dt"].dt.to_period(freq)):
        ic = spearman_ic(group[col], group["fwd"])
        if ic is not None:
            out.append((str(key), round(ic, 4)))
    return out


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
    missing = availability.get("unavailable_symbols") or []
    limitations = [
        "NSE archive availability can vary by date; holidays and failed archive fetches are skipped.",
        "Delivery data is end-of-day and used only after the close; this is not intraday evidence.",
        "This module measures predictive power only and does not define entries, exits, sizing, or deployment.",
    ]
    if missing:
        limitations.append(f"{len(missing)} requested symbol(s) lacked usable delivery rows or price overlap.")
    if observations < MIN_OBSERVATIONS:
        limitations.append("Usable observation count is below the pre-set research threshold.")
    return limitations


def _unavailable_result(universe: str, availability: dict, reason: str) -> dict:
    availability = dict(availability or {})
    availability.setdefault("source", "NSE sec_bhavdata_full archives")
    limitations = _limitations(availability, 0)
    limitations.insert(0, reason)
    return {
        "universe": universe,
        "data_availability": availability,
        "observations": 0,
        "horizon_days": HORIZON,
        "features": {},
        "usable_features": [],
        "sign_stable_but_uneconomic": [],
        "limitations": limitations,
        "verdict": f"DATA UNAVAILABLE: {reason}. Do NOT build a strategy.",
    }


def _print_report(result: dict) -> None:
    print("Delivery-volume predictive-power research")
    print("Read-only: no trades, no strategy, no broker execution, no live trading.\n")
    for universe, data in result["universes"].items():
        availability = data.get("data_availability", {})
        print(f"[{universe}] data availability")
        print(
            f"  requested={availability.get('symbols_requested', 0)} "
            f"delivery_symbols={availability.get('delivery_symbols', 0)} "
            f"used={availability.get('symbols_used', 0)} "
            f"observations={data.get('observations', 0)}"
        )
        if not data.get("features"):
            print(f"  VERDICT: {data.get('verdict')}\n")
            continue
        print(f"  split={data.get('split_date')} horizon={data.get('horizon_days')}d cost_hurdle={COST_HURDLE:.2%}")
        print(f"  {'feature':<22}{'IC in':>9}{'IC oos':>9}{'Q spread':>10}{'costAdj':>10}{'mo-stab':>9}{'wf':>5}{'usable':>8}")
        for name, values in data["features"].items():
            qs = values.get("oos_quintile_spread")
            spread = qs.get("spread") if qs else None
            mo = values.get("monthly_sign_frac")
            print(
                f"  {name:<22}{_fmt(values.get('ic_in_sample')):>9}"
                f"{_fmt(values.get('ic_out_sample')):>9}{_fmt(spread):>10}"
                f"{_fmt(values.get('cost_adjusted_edge')):>10}"
                f"{(_pct(mo) if mo is not None else 'n/a'):>9}"
                f"{('yes' if values.get('walk_forward_survives') else 'no'):>5}"
                f"{('YES' if values.get('usable') else 'no'):>8}"
            )
        print(f"  VERDICT: {data.get('verdict')}\n")
    print("Limitations:")
    for item in result.get("limitations", []):
        print(f"  - {item}")
    print(f"\nVERDICT: {result['verdict']}")


def _fmt(value) -> str:
    return f"{value:+.4f}" if isinstance(value, (int, float)) else "n/a"


def _pct(value) -> str:
    return f"{value:.0%}" if isinstance(value, (int, float)) else "n/a"


if __name__ == "__main__":
    raise SystemExit(main())
