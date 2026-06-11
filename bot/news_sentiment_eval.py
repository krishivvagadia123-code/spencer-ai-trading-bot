"""
Read-only GDELT news-sentiment predictive-power research.

This module tests whether GDELT news tone shocks for mapped NSE companies have
predictive value for forward returns. It is research only: no strategy, no
entries/exits, no sizing, no broker execution, no live trading, and no fake data.
"""

from __future__ import annotations

import argparse
from typing import Optional

import numpy as np
import pandas as pd

from bot.backtest import NIFTY50, fetch_history
from bot.feature_eval import quintile_spread, spearman_ic
from bot import gdelt_news
from workflow.research_automation import (
    add_research_workflow_args,
    finalize_from_args,
    print_research_workflow_summary,
)


HORIZON = 5
ROLLING_WINDOW = 20
SHOCK_Z = 1.5
MIN_ARTICLES_PER_DAY = 2
MIN_OBSERVATIONS = 100
MIN_EVENTS = 30
IC_MIN = 0.03
COST_HURDLE = 0.0025
GAP_CONFOUND_PCT = 0.03

FEATURE_DEFINITIONS = {
    "tone_z": "20-session z-score of GDELT average tone for an explicitly mapped company query.",
    "shock_score": "Signed tone shock used for the event study; higher is more positive news tone.",
    "tone_volume_z": "Tone z-score multiplied by log1p(article_count), capturing high-coverage tone shocks.",
}


def add_sentiment_features(news: pd.DataFrame, window: int = ROLLING_WINDOW) -> pd.DataFrame:
    out = news.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.date
    out["tone"] = pd.to_numeric(out["tone"], errors="coerce")
    out["article_count"] = pd.to_numeric(out["article_count"], errors="coerce")
    out = out.sort_values(["symbol", "date"])
    grouped = out.groupby("symbol", group_keys=False)
    mean = grouped["tone"].transform(lambda s: s.rolling(window, min_periods=max(5, window // 4)).mean())
    std = grouped["tone"].transform(lambda s: s.rolling(window, min_periods=max(5, window // 4)).std())
    out["tone_z"] = (out["tone"] - mean) / std.replace(0, np.nan)
    out["tone_volume_z"] = out["tone_z"] * np.log1p(out["article_count"].clip(lower=0))
    out["shock_score"] = out["tone_z"]
    out["is_sentiment_shock"] = (out["tone_z"].abs() >= SHOCK_Z).astype(float)
    return out.replace([np.inf, -np.inf], np.nan)


def build_symbol_panel(symbol: str, price: pd.DataFrame, news: pd.DataFrame, *, horizon: int = HORIZON) -> pd.DataFrame | None:
    if price is None or price.empty or news is None or news.empty:
        return None
    px = price.copy()
    px.index = [pd.to_datetime(x).date() for x in px.index]
    px = px.rename(columns={c: str(c).lower() for c in px.columns})
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(set(px.columns)):
        return None
    dates = list(px.index)
    rows = []
    for _, item in news[news["symbol"] == symbol].iterrows():
        event_date = pd.to_datetime(item["date"]).date()
        entry_idx = _first_index_after(dates, event_date)
        if entry_idx is None or entry_idx + horizon >= len(dates):
            continue
        entry = float(px["close"].iloc[entry_idx])
        if entry <= 0:
            continue
        fwd = float(px["close"].iloc[entry_idx + horizon]) / entry - 1.0
        lows = px["low"].iloc[entry_idx + 1: entry_idx + horizon + 1]
        highs = px["high"].iloc[entry_idx + 1: entry_idx + horizon + 1]
        tone_z = float(item.get("tone_z")) if pd.notna(item.get("tone_z")) else np.nan
        sign = np.sign(tone_z) if np.isfinite(tone_z) and tone_z != 0 else 0.0
        if sign >= 0:
            max_adverse = float(lows.min()) / entry - 1.0 if len(lows) else 0.0
        else:
            max_adverse = 1.0 - (float(highs.max()) / entry) if len(highs) else 0.0
        gap_pct = None
        if entry_idx > 0:
            prev_close = float(px["close"].iloc[entry_idx - 1])
            entry_open = float(px["open"].iloc[entry_idx])
            if prev_close > 0:
                gap_pct = entry_open / prev_close - 1.0
        rows.append({
            "symbol": symbol,
            "date": event_date,
            "entry_date": dates[entry_idx],
            "tone": item.get("tone"),
            "article_count": item.get("article_count"),
            "tone_z": item.get("tone_z"),
            "shock_score": item.get("shock_score"),
            "tone_volume_z": item.get("tone_volume_z"),
            "is_sentiment_shock": item.get("is_sentiment_shock"),
            "fwd": fwd,
            "directional_return": fwd * sign if sign != 0 else np.nan,
            "max_adverse": max_adverse,
            "gap_pct": gap_pct,
            "gap_confounded": bool(gap_pct is not None and abs(gap_pct) >= GAP_CONFOUND_PCT),
        })
    if not rows:
        return None
    return pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)


def build_panel(symbols: list[str], news: pd.DataFrame, years: int = 2) -> tuple[pd.DataFrame | None, dict]:
    availability = {
        "symbols_requested": len(symbols),
        "symbols_mapped": 0,
        "symbols_with_news": 0,
        "price_symbols": 0,
        "symbols_used": 0,
        "news_rows": 0,
        "observations": 0,
        "events": 0,
        "gap_confounded_rows": 0,
        "unmapped_symbols": gdelt_news.unmapped_symbols(symbols),
        "unavailable_symbols": [],
        "source": "GDELT DOC API TimelineTone and TimelineVolRaw plus yfinance NSE daily bars",
    }
    if news is None or news.empty:
        return None, availability
    availability["news_rows"] = int(len(news))
    availability["symbols_with_news"] = int(news["symbol"].nunique())
    mappings = gdelt_news.mapped_companies(symbols, top=None)
    mapped_symbols = [row["symbol"] for row in mappings]
    availability["symbols_mapped"] = len(mapped_symbols)

    featured = add_sentiment_features(news)
    frames = []
    for symbol in mapped_symbols:
        symbol_news = featured[featured["symbol"] == symbol]
        if symbol_news.empty:
            availability["unavailable_symbols"].append({"symbol": symbol, "reason": "no GDELT coverage rows"})
            continue
        price = fetch_history(symbol, years)
        if price is None:
            availability["unavailable_symbols"].append({"symbol": symbol, "reason": "price history unavailable"})
            continue
        availability["price_symbols"] += 1
        panel = build_symbol_panel(symbol, price, symbol_news)
        if panel is None or panel.empty:
            availability["unavailable_symbols"].append({"symbol": symbol, "reason": "no overlapping news/price rows"})
            continue
        frames.append(panel)

    if not frames:
        return None, availability
    panel = pd.concat(frames, ignore_index=True)
    availability["symbols_used"] = int(panel["symbol"].nunique())
    availability["observations"] = int(panel[["tone_z", "shock_score", "tone_volume_z", "fwd"]].dropna().shape[0])
    availability["events"] = int(((panel["is_sentiment_shock"] == 1.0) & (panel["article_count"] >= MIN_ARTICLES_PER_DAY)).sum())
    availability["gap_confounded_rows"] = int(panel["gap_confounded"].sum())
    return panel, availability


def evaluate_panel(panel: pd.DataFrame, *, availability: dict, universe: str = "nifty50") -> dict:
    clean = panel.copy().replace([np.inf, -np.inf], np.nan)
    clean["date"] = pd.to_datetime(clean["date"]).dt.date
    clean["article_count"] = pd.to_numeric(clean["article_count"], errors="coerce")
    clean = clean[clean["article_count"] >= MIN_ARTICLES_PER_DAY]
    clean = clean[clean["gap_confounded"] != True].copy()  # noqa: E712
    dates = sorted(clean["date"].dropna().unique())
    if len(dates) < 2:
        return _unavailable_result(universe, availability, "not enough dated, non-confounded GDELT/news-price observations")
    split = dates[len(dates) // 2]
    is_mask = clean["date"] <= split
    oos_mask = clean["date"] > split

    feature_results = {}
    for name in FEATURE_DEFINITIONS:
        sub = clean[["date", name, "fwd"]].dropna().copy()
        if sub.empty:
            feature_results[name] = _empty_feature(name)
            continue
        is_sub = sub["date"] <= split
        oos_sub = sub["date"] > split
        ic_all = spearman_ic(sub[name], sub["fwd"])
        ic_is = spearman_ic(sub.loc[is_sub, name], sub.loc[is_sub, "fwd"])
        ic_oos = spearman_ic(sub.loc[oos_sub, name], sub.loc[oos_sub, "fwd"])
        qs = quintile_spread(sub.loc[oos_sub, name], sub.loc[oos_sub, "fwd"])
        raw_spread = qs["spread"] if qs else None
        economic_spread = None
        if raw_spread is not None and ic_oos is not None:
            economic_spread = raw_spread if ic_oos >= 0 else -raw_spread
        feature_results[name] = {
            "observations": int(len(sub)),
            "ic_all": round(ic_all, 4) if ic_all is not None else None,
            "ic_in_sample": round(ic_is, 4) if ic_is is not None else None,
            "ic_out_sample": round(ic_oos, 4) if ic_oos is not None else None,
            "oos_quintile_spread": qs,
            "cost_adjusted_spread": None if economic_spread is None else round(float(economic_spread - COST_HURDLE), 5),
            "sign_stable": bool(ic_is is not None and ic_oos is not None and np.sign(ic_is) == np.sign(ic_oos) and abs(ic_oos) >= IC_MIN),
        }

    events = clean[
        (clean["is_sentiment_shock"] == 1.0)
        & clean["directional_return"].notna()
        & clean["fwd"].notna()
    ].copy()
    observations = int(clean[["tone_z", "shock_score", "tone_volume_z", "fwd"]].dropna().shape[0])
    event_metrics = _event_metrics(events, split)
    availability = dict(availability or {})
    availability["observations"] = observations
    availability["events"] = int(len(events))
    availability["gap_confounded_rows_removed"] = int((panel.get("gap_confounded") == True).sum()) if "gap_confounded" in panel else 0  # noqa: E712

    best_feature = max(feature_results.values(), key=lambda item: abs(item.get("ic_out_sample") or 0), default={})
    sign_stable = bool(best_feature.get("sign_stable"))
    clears_costs = bool((event_metrics.get("cost_adjusted_return") or -1) > 0)
    walk_forward = bool(event_metrics.get("walk_forward_survives"))
    enough = observations >= MIN_OBSERVATIONS and len(events) >= MIN_EVENTS
    usable = bool(enough and sign_stable and clears_costs and walk_forward)
    needs_confirmation = bool(enough and not usable and (sign_stable or clears_costs or walk_forward))

    limitations = _limitations(availability, observations, len(events))
    if observations < MIN_OBSERVATIONS:
        verdict = (
            f"DATA_UNAVAILABLE: only {observations} usable GDELT/news-price observations "
            f"(< {MIN_OBSERVATIONS}). Do NOT build a strategy."
        )
    elif len(events) < MIN_EVENTS:
        verdict = (
            f"DATA_UNAVAILABLE: only {len(events)} non-confounded sentiment-shock events "
            f"(< {MIN_EVENTS}). Do NOT build a strategy."
        )
    elif usable:
        verdict = (
            "PASS: GDELT sentiment shocks survive out-of-sample IC, cost-adjusted event returns, "
            "and walk-forward checks. Research only; no deployment."
        )
    elif needs_confirmation:
        verdict = (
            "NEEDS CONFIRMATION: GDELT sentiment shows partial evidence but fails at least one "
            "OOS/cost/walk-forward gate. Do NOT build a strategy."
        )
    else:
        verdict = (
            "FAIL: GDELT sentiment does not show stable OOS predictive power, cost-adjusted edge, "
            "and walk-forward survival. Do NOT build a strategy."
        )

    return {
        "module": "news_sentiment_eval",
        "universe": universe,
        "data_availability": availability,
        "coverage_decision": availability.get("coverage_decision"),
        "feature_definitions": FEATURE_DEFINITIONS,
        "observations": observations,
        "events": int(len(events)),
        "horizon_days": HORIZON,
        "split_date": str(split),
        "shock_z_threshold": SHOCK_Z,
        "min_articles_per_day": MIN_ARTICLES_PER_DAY,
        "cost_hurdle": COST_HURDLE,
        "ic_min_threshold": IC_MIN,
        "features": feature_results,
        "event_study": event_metrics,
        "usable_features": ["gdelt_sentiment_shock"] if usable else [],
        "candidates": ["gdelt_sentiment_shock"] if needs_confirmation else [],
        "limitations": limitations,
        "verdict": verdict,
    }


def evaluate(years: int = 2, *, top: int = 5, refresh: bool = True, universe: str = "nifty50") -> dict:
    symbols = NIFTY50[: max(top, 0)]
    mappings = gdelt_news.mapped_companies(symbols, top=None)
    availability = {
        "symbols_requested": len(symbols),
        "symbols_mapped": len(mappings),
        "unmapped_symbols": gdelt_news.unmapped_symbols(symbols),
        "news_rows": 0,
        "observations": 0,
        "events": 0,
        "source": "GDELT DOC API TimelineTone and TimelineVolRaw",
    }
    if not mappings:
        availability["coverage_decision"] = "DATA_UNAVAILABLE_MAPPING_TOO_THIN"
        return _unavailable_result(universe, availability, "DATA_UNAVAILABLE_MAPPING_TOO_THIN: no auditable company-to-NSE mapping rows selected")

    preferred_probe = ["RELIANCE", "TCS", "INFY"]
    selected = {row["symbol"] for row in mappings}
    probe_symbols = [symbol for symbol in preferred_probe if symbol in selected] or [row["symbol"] for row in mappings[:3]]
    coverage = gdelt_news.coverage_probe(symbols=probe_symbols, refresh=refresh)
    availability["coverage_probe"] = coverage
    availability["coverage_decision"] = coverage.get("decision")
    if coverage.get("decision") != "DATA_AVAILABLE_FOR_RESEARCH":
        return _unavailable_result(universe, availability, _coverage_reason(coverage))

    news = gdelt_news.news_history(symbols=symbols, top=None, years=years, refresh=refresh)
    if news is None or news.empty:
        return _unavailable_result(universe, availability, "DATA_UNAVAILABLE_INSUFFICIENT_HISTORY: GDELT news/tone coverage could not be fetched from real data or cache")
    availability["news_rows"] = int(len(news))
    availability["symbols_with_news"] = int(news["symbol"].nunique())
    availability["cache_dir"] = news.attrs.get("cache_dir")
    availability["rate_limited_requests"] = int(news.attrs.get("rate_limited_requests", 0) or 0)
    if availability["rate_limited_requests"] > 0:
        availability["coverage_decision"] = "DATA_UNAVAILABLE_RATE_LIMITED"
        return _unavailable_result(universe, availability, "DATA_UNAVAILABLE_RATE_LIMITED: GDELT returned HTTP 429/503 during news ingestion")
    if len(news) < MIN_OBSERVATIONS:
        return _unavailable_result(
            universe,
            availability,
            f"DATA_UNAVAILABLE_INSUFFICIENT_HISTORY: only {len(news)} real GDELT tone rows available; {MIN_OBSERVATIONS} required",
        )

    panel, panel_availability = build_panel(symbols, news, years=years)
    availability.update(panel_availability)
    if panel is None or panel.empty:
        return _unavailable_result(universe, availability, "DATA_UNAVAILABLE_INSUFFICIENT_HISTORY: no overlapping GDELT/news and NSE price rows")
    return evaluate_panel(panel, availability=availability, universe=universe)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bot.news_sentiment_eval")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--refresh", action="store_true", help="Fetch live public GDELT data before falling back to cache.")
    parser.add_argument("--no-refresh", action="store_true", help="Use cached raw GDELT responses only. This is the default.")
    add_research_workflow_args(parser)
    args = parser.parse_args(argv)

    result = evaluate(args.years, top=args.top, refresh=bool(args.refresh and not args.no_refresh))
    _print_report(result)
    print_research_workflow_summary(finalize_from_args("news_sentiment_eval", result, args))
    return 0


def _event_metrics(events: pd.DataFrame, split) -> dict:
    if events.empty:
        return {
            "event_count": 0,
            "win_rate": None,
            "average_return": None,
            "average_directional_return": None,
            "cost_adjusted_return": None,
            "average_max_adverse": None,
            "is_average_directional": None,
            "oos_average_directional": None,
            "monthly_stability": None,
            "quarterly_stability": None,
            "walk_forward_survives": False,
        }
    ordered = events.sort_values("date")
    is_events = ordered[ordered["date"] <= split]
    oos_events = ordered[ordered["date"] > split]
    directional = ordered["directional_return"].astype(float)
    monthly = _period_means(ordered, "M")
    quarterly_oos = _period_means(oos_events, "Q")
    is_avg = _avg(is_events["directional_return"])
    oos_avg = _avg(oos_events["directional_return"])
    walk_forward = False
    if is_avg is not None and oos_avg is not None and quarterly_oos:
        q_cost_clear = sum(1 for _, value in quarterly_oos if value - COST_HURDLE > 0)
        walk_forward = bool(
            is_avg - COST_HURDLE > 0
            and oos_avg - COST_HURDLE > 0
            and q_cost_clear > len(quarterly_oos) / 2
        )
    return {
        "event_count": int(len(ordered)),
        "win_rate": round(float((directional > 0).mean()), 4),
        "average_return": round(float(ordered["fwd"].mean()), 5),
        "average_directional_return": round(float(directional.mean()), 5),
        "cost_adjusted_return": round(float((_avg(oos_events["directional_return"]) or 0.0) - COST_HURDLE), 5),
        "average_max_adverse": round(float(ordered["max_adverse"].mean()), 5),
        "is_average_directional": round(is_avg, 5) if is_avg is not None else None,
        "oos_average_directional": round(oos_avg, 5) if oos_avg is not None else None,
        "monthly_stability": _positive_fraction(monthly),
        "quarterly_stability": _positive_fraction(quarterly_oos),
        "monthly_directional_return": monthly,
        "oos_quarterly_directional_return": quarterly_oos,
        "walk_forward_survives": walk_forward,
    }


def _period_means(records: pd.DataFrame, freq: str) -> list[tuple[str, float]]:
    if records.empty:
        return []
    tmp = records.copy()
    tmp["period"] = pd.to_datetime(tmp["date"]).dt.to_period(freq)
    grouped = tmp.groupby("period")["directional_return"].mean()
    return [(str(key), round(float(value), 5)) for key, value in grouped.items()]


def _positive_fraction(periods: list[tuple[str, float]]) -> Optional[float]:
    if not periods:
        return None
    return round(sum(1 for _, value in periods if value > 0) / len(periods), 2)


def _avg(series: pd.Series) -> Optional[float]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return float(clean.mean())


def _first_index_after(dates: list, event_date) -> Optional[int]:
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] > event_date:
            hi = mid
        else:
            lo = mid + 1
    return lo if lo < len(dates) else None


def _empty_feature(name: str) -> dict:
    return {
        "observations": 0,
        "ic_all": None,
        "ic_in_sample": None,
        "ic_out_sample": None,
        "oos_quintile_spread": None,
        "cost_adjusted_spread": None,
        "sign_stable": False,
    }


def _limitations(availability: dict, observations: int, events: int) -> list[str]:
    limitations = [
        "GDELT tone is machine-coded news tone, not a company-specific analyst sentiment feed.",
        "Company-name queries can pick up group, subsidiary, sector, or unrelated mentions despite explicit mapping.",
        "GDELT DOC timeline coverage and historical backfill can vary; cached raw responses are the audit trail.",
        "Gap-confounded rows are removed from the primary event study; earnings-calendar overlap is listed as unresolved because no verified calendar is available in-repo.",
        "This module measures predictive power only and does not define entries, exits, sizing, or deployment.",
    ]
    if availability.get("unmapped_symbols"):
        limitations.insert(0, f"{len(availability['unmapped_symbols'])} requested symbol(s) lacked auditable mapping.")
    if observations < MIN_OBSERVATIONS:
        limitations.insert(0, "Usable GDELT/news-price observation count is below the pre-set research threshold.")
    if events < MIN_EVENTS:
        limitations.insert(0, "Sentiment-shock event count is below the pre-set research threshold.")
    if availability.get("gap_confounded_rows_removed"):
        limitations.append(f"{availability['gap_confounded_rows_removed']} gap-confounded row(s) removed from the primary study.")
    return limitations


def _unavailable_result(universe: str, availability: dict, reason: str) -> dict:
    availability = dict(availability or {})
    coverage_decision = availability.get("coverage_decision")
    reason = str(reason).rstrip(".")
    limitations = _limitations(availability, int(availability.get("observations", 0) or 0), int(availability.get("events", 0) or 0))
    limitations.insert(0, reason)
    return {
        "module": "news_sentiment_eval",
        "universe": universe,
        "data_availability": availability,
        "coverage_decision": coverage_decision,
        "feature_definitions": FEATURE_DEFINITIONS,
        "observations": int(availability.get("observations", 0) or 0),
        "events": int(availability.get("events", 0) or 0),
        "horizon_days": HORIZON,
        "shock_z_threshold": SHOCK_Z,
        "cost_hurdle": COST_HURDLE,
        "features": {},
        "event_study": {},
        "usable_features": [],
        "candidates": [],
        "limitations": limitations,
        "verdict": f"DATA_UNAVAILABLE: {reason}. Do NOT build a strategy.",
    }


def _coverage_reason(coverage: dict) -> str:
    decision = coverage.get("decision") or "DATA_UNAVAILABLE_INSUFFICIENT_HISTORY"
    windows = coverage.get("windows") or []
    available = sum(1 for item in windows if item.get("merged_points", 0) > 0)
    total = len(windows)
    unprobed = sum(1 for item in windows if item.get("status") == "NOT_PROBED_CACHE_MISS")
    if decision == "DATA_UNAVAILABLE_RATE_LIMITED":
        limited = coverage.get("request_summary", {}).get("rate_limited_requests", 0)
        return f"{decision}: GDELT returned HTTP 429/503 in {limited} request(s); rerun later or rely on cache."
    if decision == "DATA_UNAVAILABLE_MAPPING_TOO_THIN":
        unmapped = coverage.get("unmapped_symbols") or []
        return f"{decision}: auditable company-to-symbol mapping missing for {unmapped}."
    if decision == "NEEDS_PAID_OR_BULK_DATA":
        return f"{decision}: recent DOC data exists but older 30-day windows are missing ({available}/{total} windows with real rows)."
    if decision == "DATA_UNAVAILABLE_INSUFFICIENT_HISTORY":
        if unprobed:
            return f"{decision}: coverage probe found real rows in {available}/{total} checks; {unprobed} cache-only checks were not probed live."
        return f"{decision}: coverage probe found real rows in {available}/{total} symbol-window checks."
    return f"{decision}: historical GDELT coverage probe passed."


def _print_report(result: dict) -> None:
    print("GDELT news-sentiment predictive-power research")
    print("Read-only: no trades, no strategy, no broker execution, no live trading.\n")
    availability = result.get("data_availability", {})
    print("Data availability")
    print(
        f"  mapped={availability.get('symbols_mapped', 0)} "
        f"news_symbols={availability.get('symbols_with_news', 0)} "
        f"news_rows={availability.get('news_rows', 0)} "
        f"observations={result.get('observations', 0)} "
        f"events={result.get('events', 0)}"
    )
    if availability.get("cache_dir"):
        print(f"  raw_cache={availability.get('cache_dir')}")
    coverage = availability.get("coverage_probe") or {}
    if coverage:
        print(f"  coverage_decision={coverage.get('decision')}")
        summary = coverage.get("request_summary") or {}
        print(
            f"  probe_cache_hits={summary.get('cache_hits', 0)} "
            f"probe_network_fetches={summary.get('network_fetches', 0)} "
            f"probe_rate_limited={summary.get('rate_limited_requests', 0)}"
        )
        for row in coverage.get("windows", [])[:12]:
            print(
                f"  probe {row.get('symbol')} {row.get('window')} "
                f"{row.get('start')}..{row.get('end')} "
                f"merged_points={row.get('merged_points', 0)} status={row.get('status')}"
            )

    print("\nNews feature definitions")
    for name, definition in result.get("feature_definitions", {}).items():
        print(f"  - {name}: {definition}")

    features = result.get("features") or {}
    if features:
        print(f"\nIC metrics | split={result.get('split_date')} horizon={HORIZON}d cost_hurdle={COST_HURDLE:.2%}")
        print(f"  {'feature':<18}{'obs':>6}{'IC in':>9}{'IC oos':>9}{'Q spread':>10}{'costAdj':>10}{'stable':>8}")
        for name, values in features.items():
            qs = values.get("oos_quintile_spread")
            spread = qs.get("spread") if qs else None
            print(
                f"  {name:<18}{values.get('observations', 0):>6}"
                f"{_fmt(values.get('ic_in_sample')):>9}"
                f"{_fmt(values.get('ic_out_sample')):>9}"
                f"{_fmt(spread):>10}"
                f"{_fmt(values.get('cost_adjusted_spread')):>10}"
                f"{str(values.get('sign_stable')):>8}"
            )
    else:
        print("\nIC metrics unavailable: not enough real GDELT/news-price observations.")

    event = result.get("event_study") or {}
    if event:
        print("\nSentiment-shock event study")
        print(
            f"  events={event.get('event_count', 0)} "
            f"win_rate={_pct(event.get('win_rate'))} "
            f"avg_return={_fmt(event.get('average_return'))} "
            f"cost_adj_oos={_fmt(event.get('cost_adjusted_return'))} "
            f"walk_forward={'yes' if event.get('walk_forward_survives') else 'no'}"
        )

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
