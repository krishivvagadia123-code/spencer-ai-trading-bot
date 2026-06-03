"""
Read-only bulk/block-deals event study.

Measures whether NSE bulk/block-deal disclosures predict 5-day forward returns.
This is research only: no strategy, no entries/exits, no sizing, no broker
execution, no live trading, and no fake NSE data.
"""

from __future__ import annotations

import argparse
from typing import Iterable

import numpy as np
import pandas as pd

from bot.backtest import NIFTY50, fetch_history
from bot.midcap_eval import MIDCAP100
from bot import nse_block_deals
from workflow.research_automation import (
    add_research_workflow_args,
    finalize_from_args,
    print_research_workflow_summary,
)


HORIZON = 5
COST = 0.0025
MIN_EVENTS = 30


def forward_record(price: pd.DataFrame, event_date, side: str) -> dict | None:
    px = price.copy()
    px.index = [pd.to_datetime(x).date() for x in px.index]
    px = px.rename(columns={c: str(c).lower() for c in px.columns})
    if "close" not in px.columns or "low" not in px.columns:
        return None
    dates = list(px.index)
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] > event_date:
            hi = mid
        else:
            lo = mid + 1
    entry_idx = lo
    if entry_idx >= len(dates) or entry_idx + HORIZON >= len(dates):
        return None
    entry = float(px["close"].iloc[entry_idx])
    if entry <= 0:
        return None
    fwd = float(px["close"].iloc[entry_idx + HORIZON]) / entry - 1.0
    lows = px["low"].iloc[entry_idx + 1: entry_idx + HORIZON + 1]
    max_adv = float(lows.min()) / entry - 1.0 if len(lows) else 0.0
    side_norm = side.upper()
    directional = fwd if side_norm == "BUY" else -fwd
    return {
        "date": dates[entry_idx],
        "fwd": fwd,
        "directional_return": directional,
        "max_adv": max_adv,
        "side": side_norm,
    }


def build_events(symbols: list[str], years: int = 2) -> tuple[dict[str, list[dict]], dict]:
    availability = {
        "symbols_requested": len(symbols),
        "price_symbols": 0,
        "deal_symbols": 0,
        "events_raw": 0,
        "events_used": 0,
        "source_priority": list(nse_block_deals.SOURCE_PRIORITY),
        "source_counts": {},
        "sources_used": [],
        "source": "NSE bulk/block-deal archives",
        "unavailable_symbols": [],
    }
    deals = nse_block_deals.deals_history(symbols, years=years)
    buckets: dict[str, list[dict]] = {
        "bulk_buy": [],
        "bulk_sell": [],
        "block_buy": [],
        "block_sell": [],
        "all_buy": [],
        "all_sell": [],
    }
    if deals is None or deals.empty:
        return buckets, availability

    availability["events_raw"] = int(len(deals))
    availability["deal_symbols"] = int(deals["symbol"].nunique())
    source_counts = getattr(deals, "attrs", {}).get("source_counts", {})
    availability["source_counts"] = {str(k): int(v) for k, v in source_counts.items()}
    availability["sources_used"] = [source for source in nse_block_deals.SOURCE_PRIORITY if source_counts.get(source, 0) > 0]
    price_by_symbol: dict[str, pd.DataFrame] = {}
    for symbol in sorted(deals["symbol"].unique()):
        price = fetch_history(symbol, years)
        if price is None:
            availability["unavailable_symbols"].append({"symbol": symbol, "reason": "price history unavailable"})
            continue
        price_by_symbol[symbol] = price
        availability["price_symbols"] += 1

    for _, deal in deals.iterrows():
        symbol = str(deal["symbol"]).upper()
        price = price_by_symbol.get(symbol)
        if price is None:
            continue
        rec = forward_record(price, pd.to_datetime(deal["date"]).date(), str(deal["side"]))
        if rec is None:
            continue
        rec.update({
            "symbol": symbol,
            "deal_type": str(deal["deal_type"]).lower(),
            "qty": float(deal["qty"]),
            "price": float(deal["price"]),
            "client": str(deal.get("client", "")),
        })
        side = rec["side"].lower()
        deal_type = rec["deal_type"]
        bucket = f"{deal_type}_{side}"
        if bucket in buckets:
            buckets[bucket].append(rec)
        all_bucket = f"all_{side}"
        if all_bucket in buckets:
            buckets[all_bucket].append(rec)

    availability["events_used"] = int(sum(len(v) for k, v in buckets.items() if k.startswith(("bulk_", "block_"))))
    return buckets, availability


def summarize_bucket(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {
            "events": 0,
            "status": "FAIL",
            "win_rate": None,
            "avg_return": None,
            "avg_directional_return": None,
            "cost_adj": None,
            "avg_max_adverse": None,
            "is_avg": None,
            "oos_avg": None,
            "monthly_sign_frac": None,
            "walk_forward": "insufficient",
        }
    directional = np.array([r["directional_return"] for r in records], dtype=float)
    fwd = np.array([r["fwd"] for r in records], dtype=float)
    adv = np.array([r["max_adv"] for r in records], dtype=float)
    split = _split_and_walkforward(records)
    cost_adj = float(directional.mean() - COST)
    status = _status_for(n, cost_adj, split)
    return {
        "events": n,
        "status": status,
        "win_rate": round(float((directional > 0).mean()), 4),
        "avg_return": round(float(fwd.mean()), 5),
        "avg_directional_return": round(float(directional.mean()), 5),
        "cost_adj": round(cost_adj, 5),
        "avg_max_adverse": round(float(adv.mean()), 5),
        **split,
    }


def evaluate(symbols: list[str], years: int = 2, *, universe: str = "nifty50") -> dict:
    buckets, availability = build_events(symbols, years)
    results = {name: summarize_bucket(records) for name, records in buckets.items()}
    tested = [name for name, data in results.items() if data.get("events", 0) >= MIN_EVENTS]
    survivors = [
        name for name, data in results.items()
        if data.get("status") == "PASS" and data.get("walk_forward") == "survives"
    ]
    caveat_survivors = [
        name for name, data in results.items()
        if data.get("status") == "NEEDS CONFIRMATION"
    ]
    limitations = _limitations(availability, results)
    if survivors:
        verdict = (
            f"PASS: {len(survivors)} bulk/block deal bucket(s) clear costs, IS/OOS, "
            f"and walk-forward in {universe}: {survivors}. CAVEAT: sparse disclosures "
            "still require confirmation before any paper-only strategy spec."
        )
    elif caveat_survivors:
        verdict = (
            f"NEEDS CONFIRMATION: {caveat_survivors} show positive cost-adjusted evidence "
            "but sample size or walk-forward support is not strong enough. Do NOT build a strategy."
        )
    elif availability["events_used"] < MIN_EVENTS:
        verdict = (
            f"FAIL: DATA_UNAVAILABLE - only {availability['events_used']} usable NSE bulk/block "
            f"deal event rows; minimum required is {MIN_EVENTS}. "
            "Do NOT build a strategy."
        )
    else:
        verdict = (
            f"FAIL: no bulk/block deal bucket in {universe} shows a cost-adjusted edge "
            "that survives IS/OOS and walk-forward. Do NOT build a strategy."
        )
    return {
        "module": "blockdeal_eval",
        "universe": universe,
        "data_availability": availability,
        "events": availability["events_used"],
        "horizon_days": HORIZON,
        "cost": COST,
        "tested_buckets": tested,
        "results": results,
        "usable_features": survivors,
        "candidates": caveat_survivors,
        "limitations": limitations,
        "verdict": verdict,
    }


def evaluate_all(years: int = 2, *, include_midcap: bool = False, top: int = 50) -> dict:
    universes = {"nifty50": evaluate(NIFTY50[:top], years, universe="nifty50")}
    if include_midcap:
        universes["midcap100"] = evaluate(MIDCAP100, years, universe="midcap100")
    primary = universes["nifty50"]
    usable: list[str] = []
    candidates: list[str] = []
    for universe, result in universes.items():
        usable.extend([f"{universe}:{item}" for item in result.get("usable_features", [])])
        candidates.extend([f"{universe}:{item}" for item in result.get("candidates", [])])
    verdict = primary["verdict"]
    if usable:
        verdict = f"PASS: bulk/block-deal usable buckets found: {usable}. Research only, not deployed."
    elif candidates:
        verdict = f"NEEDS CONFIRMATION: bulk/block-deal candidate buckets found: {candidates}. Do NOT build a strategy."
    return {
        "module": "blockdeal_eval",
        "universes": universes,
        "data_availability": primary.get("data_availability", {}),
        "events": primary.get("events", 0),
        "horizon_days": HORIZON,
        "cost": COST,
        "results": primary.get("results", {}),
        "usable_features": usable,
        "candidates": candidates,
        "limitations": primary.get("limitations", []),
        "verdict": verdict,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bot.blockdeal_eval")
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--include-midcap", action="store_true")
    add_research_workflow_args(parser)
    args = parser.parse_args(argv)

    result = evaluate_all(args.years, include_midcap=args.include_midcap, top=args.top)
    _print_report(result)
    print_research_workflow_summary(finalize_from_args("blockdeal_eval", result, args))
    return 0


def _split_and_walkforward(records: list[dict]) -> dict:
    if len(records) < MIN_EVENTS:
        return {
            "is_avg": None,
            "oos_avg": None,
            "monthly_sign_frac": None,
            "walk_forward": "insufficient",
        }
    recs = sorted(records, key=lambda r: r["date"])
    mid = recs[len(recs) // 2]["date"]
    is_r = [r for r in recs if r["date"] <= mid]
    oos_r = [r for r in recs if r["date"] > mid]
    is_avg = _avg_directional(is_r)
    oos_avg = _avg_directional(oos_r)
    monthly = _period_means(recs, "M")
    quarterly_oos = _period_means(oos_r, "Q")
    monthly_sign_frac = _same_sign_fraction(monthly, oos_avg)
    survive = False
    if quarterly_oos and is_avg is not None and oos_avg is not None:
        q_pos = sum(1 for _, value in quarterly_oos if value - COST > 0)
        survive = bool(
            oos_avg - COST > 0
            and q_pos > len(quarterly_oos) / 2
            and np.sign(is_avg) == np.sign(oos_avg)
        )
    return {
        "is_avg": round(is_avg - COST, 5) if is_avg is not None else None,
        "oos_avg": round(oos_avg - COST, 5) if oos_avg is not None else None,
        "monthly_sign_frac": monthly_sign_frac,
        "walk_forward": "survives" if survive else "fails",
    }


def _avg_directional(records: list[dict]) -> float | None:
    if not records:
        return None
    return float(np.mean([r["directional_return"] for r in records]))


def _period_means(records: list[dict], freq: str) -> list[tuple[str, float]]:
    if not records:
        return []
    df = pd.DataFrame(records)
    df["period"] = pd.to_datetime(df["date"]).dt.to_period(freq)
    grouped = df.groupby("period")["directional_return"].mean()
    return [(str(key), round(float(value), 5)) for key, value in grouped.items()]


def _same_sign_fraction(periods: list[tuple[str, float]], oos_avg: float | None) -> float | None:
    if oos_avg is None or not periods:
        return None
    sign = np.sign(oos_avg)
    return round(sum(1 for _, value in periods if np.sign(value) == sign) / len(periods), 2)


def _status_for(events: int, cost_adj: float, split: dict) -> str:
    if events < MIN_EVENTS:
        return "FAIL"
    if cost_adj <= 0:
        return "FAIL"
    if split.get("walk_forward") == "survives" and (split.get("is_avg") or -1) > 0 and (split.get("oos_avg") or -1) > 0:
        return "PASS"
    return "NEEDS CONFIRMATION"


def _limitations(availability: dict, results: dict) -> list[str]:
    limitations = [
        "NSE bulk/block deal archive availability can vary by date and API response shape.",
        "Deals are public disclosures and are evaluated only after the event date; no intraday execution is implied.",
        "Bulk/block deals are sparse per symbol, so small samples are treated as failed or requiring confirmation.",
        "This module measures predictive power only and does not define entries, exits, sizing, or deployment.",
    ]
    if availability.get("events_used", 0) == 0:
        limitations.insert(0, "No usable overlapping deal/price event rows were available.")
    elif availability.get("events_used", 0) < MIN_EVENTS:
        limitations.insert(
            0,
            f"Only {availability.get('events_used', 0)} usable event rows were available; "
            f"{MIN_EVENTS} are required before testing an edge.",
        )
    sparse = [name for name, data in results.items() if 0 < data.get("events", 0) < MIN_EVENTS]
    if sparse:
        limitations.append(f"Sparse buckets below {MIN_EVENTS} events: {sparse}.")
    return limitations


def _print_report(result: dict) -> None:
    print("Bulk/block-deals event-study research")
    print("Read-only: no trades, no strategy, no broker execution, no live trading.\n")
    for universe, data in result["universes"].items():
        availability = data.get("data_availability", {})
        print(f"[{universe}] data availability")
        print(
            f"  requested={availability.get('symbols_requested', 0)} "
            f"deal_symbols={availability.get('deal_symbols', 0)} "
            f"raw_events={availability.get('events_raw', 0)} "
            f"used_events={availability.get('events_used', 0)}"
        )
        if availability.get("source_counts"):
            sources = " ".join(
                f"{source}={availability['source_counts'].get(source, 0)}"
                for source in availability.get("source_priority", [])
            )
            print(f"  sources: {sources}")
        print(
            f"  {'bucket':<14} {'events':>7} {'win%':>7} {'avgRet':>9} "
            f"{'costAdj':>9} {'IS':>9} {'OOS':>9} {'walk-fwd':>13} {'status':>18}"
        )
        for name, values in data.get("results", {}).items():
            print(
                f"  {name:<14} {values.get('events', 0):>7} "
                f"{_pct(values.get('win_rate')):>7} "
                f"{_pct(values.get('avg_directional_return')):>9} "
                f"{_pct(values.get('cost_adj')):>9} "
                f"{_pct(values.get('is_avg')):>9} "
                f"{_pct(values.get('oos_avg')):>9} "
                f"{values.get('walk_forward', 'n/a'):>13} "
                f"{values.get('status', 'FAIL'):>18}"
            )
        print(f"  VERDICT: {data.get('verdict')}\n")
    print("Limitations:")
    for item in result.get("limitations", []):
        print(f"  - {item}")
    print(f"\nVERDICT: {result['verdict']}")


def _pct(value) -> str:
    return f"{value:+.2%}" if isinstance(value, (int, float)) else "n/a"


if __name__ == "__main__":
    raise SystemExit(main())
