"""
Read-only GDELT news/tone ingestion for Spencer research.

This module fetches only public GDELT DOC timeline data, caches raw responses,
and returns None when mapping, network access, or coverage is insufficient. It
does not fabricate articles, tone, trades, prices, or bot state.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import date
from email.utils import parsedate_to_datetime
from io import StringIO
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from bot.backtest import NIFTY50


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / ".cache" / "gdelt_news"
GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_MIN_REQUEST_DELAY = 5.0
DEFAULT_BACKOFF_BASE = 2.0
THROTTLE_STATUS_CODES = {429, 503}
PROBE_SYMBOLS = ("RELIANCE", "TCS", "INFY")
PROBE_WINDOW_DAYS = 30

FetchText = Callable[[str, int], str]
SleepFunc = Callable[[float], None]
NowFunc = Callable[[], float]


@dataclass
class RateLimitState:
    last_request_at: float | None = None
    request_cache: dict[str, str] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)


# Auditable manual mapping for Nifty-50 names. The mapping deliberately stores
# aliases and notes beside each NSE symbol; ambiguous entities are skipped by
# callers rather than guessed.
NSE_COMPANY_MAP: dict[str, dict] = {
    "RELIANCE": {"company_name": "Reliance Industries Limited", "aliases": ["Reliance Industries", "Reliance Jio"], "source": "manual Nifty-50 company-name mapping", "notes": "Reliance may match group or telecom coverage."},
    "TCS": {"company_name": "Tata Consultancy Services Limited", "aliases": ["Tata Consultancy Services", "TCS"], "source": "manual Nifty-50 company-name mapping", "notes": "TCS is a short alias; query includes full company phrase."},
    "HDFCBANK": {"company_name": "HDFC Bank Limited", "aliases": ["HDFC Bank"], "source": "manual Nifty-50 company-name mapping", "notes": "Distinct from HDFC Life."},
    "ICICIBANK": {"company_name": "ICICI Bank Limited", "aliases": ["ICICI Bank"], "source": "manual Nifty-50 company-name mapping", "notes": "Bank-specific phrase."},
    "INFY": {"company_name": "Infosys Limited", "aliases": ["Infosys"], "source": "manual Nifty-50 company-name mapping", "notes": "Common company name."},
    "SBIN": {"company_name": "State Bank of India", "aliases": ["SBI", "State Bank of India"], "source": "manual Nifty-50 company-name mapping", "notes": "SBI abbreviation can be noisy; full phrase retained."},
    "BHARTIARTL": {"company_name": "Bharti Airtel Limited", "aliases": ["Bharti Airtel", "Airtel"], "source": "manual Nifty-50 company-name mapping", "notes": "Airtel may include non-listed subsidiaries."},
    "ITC": {"company_name": "ITC Limited", "aliases": ["ITC Limited", "ITC India"], "source": "manual Nifty-50 company-name mapping", "notes": "ITC acronym is noisy; full phrase preferred."},
    "LT": {"company_name": "Larsen and Toubro Limited", "aliases": ["Larsen and Toubro", "L&T"], "source": "manual Nifty-50 company-name mapping", "notes": "Ampersand alias may vary by outlet."},
    "AXISBANK": {"company_name": "Axis Bank Limited", "aliases": ["Axis Bank"], "source": "manual Nifty-50 company-name mapping", "notes": "Bank-specific phrase."},
    "KOTAKBANK": {"company_name": "Kotak Mahindra Bank Limited", "aliases": ["Kotak Mahindra Bank", "Kotak Bank"], "source": "manual Nifty-50 company-name mapping", "notes": "Bank-specific phrase."},
    "HINDUNILVR": {"company_name": "Hindustan Unilever Limited", "aliases": ["Hindustan Unilever", "HUL"], "source": "manual Nifty-50 company-name mapping", "notes": "HUL abbreviation can be noisy."},
    "BAJFINANCE": {"company_name": "Bajaj Finance Limited", "aliases": ["Bajaj Finance"], "source": "manual Nifty-50 company-name mapping", "notes": "Distinct from Bajaj Finserv."},
    "ASIANPAINT": {"company_name": "Asian Paints Limited", "aliases": ["Asian Paints"], "source": "manual Nifty-50 company-name mapping", "notes": "Company phrase."},
    "MARUTI": {"company_name": "Maruti Suzuki India Limited", "aliases": ["Maruti Suzuki", "Maruti Suzuki India"], "source": "manual Nifty-50 company-name mapping", "notes": "Auto maker phrase."},
    "SUNPHARMA": {"company_name": "Sun Pharmaceutical Industries Limited", "aliases": ["Sun Pharma", "Sun Pharmaceutical"], "source": "manual Nifty-50 company-name mapping", "notes": "Pharma phrase."},
    "TITAN": {"company_name": "Titan Company Limited", "aliases": ["Titan Company"], "source": "manual Nifty-50 company-name mapping", "notes": "Titan alone is ambiguous; full phrase preferred."},
    "WIPRO": {"company_name": "Wipro Limited", "aliases": ["Wipro"], "source": "manual Nifty-50 company-name mapping", "notes": "Company name."},
    "TATAMOTORS": {"company_name": "Tata Motors Limited", "aliases": ["Tata Motors"], "source": "manual Nifty-50 company-name mapping", "notes": "Auto maker phrase."},
    "ADANIENT": {"company_name": "Adani Enterprises Limited", "aliases": ["Adani Enterprises"], "source": "manual Nifty-50 company-name mapping", "notes": "Adani group coverage can be confounded."},
    "HCLTECH": {"company_name": "HCL Technologies Limited", "aliases": ["HCL Technologies", "HCLTech"], "source": "manual Nifty-50 company-name mapping", "notes": "IT phrase."},
    "TECHM": {"company_name": "Tech Mahindra Limited", "aliases": ["Tech Mahindra"], "source": "manual Nifty-50 company-name mapping", "notes": "IT phrase."},
    "ULTRACEMCO": {"company_name": "UltraTech Cement Limited", "aliases": ["UltraTech Cement"], "source": "manual Nifty-50 company-name mapping", "notes": "Cement phrase."},
    "NESTLEIND": {"company_name": "Nestle India Limited", "aliases": ["Nestle India"], "source": "manual Nifty-50 company-name mapping", "notes": "India unit phrase."},
    "POWERGRID": {"company_name": "Power Grid Corporation of India Limited", "aliases": ["Power Grid Corporation", "Power Grid India"], "source": "manual Nifty-50 company-name mapping", "notes": "Power Grid phrase can match grid-sector news."},
    "ONGC": {"company_name": "Oil and Natural Gas Corporation Limited", "aliases": ["ONGC", "Oil and Natural Gas Corporation"], "source": "manual Nifty-50 company-name mapping", "notes": "ONGC abbreviation is common company usage."},
    "NTPC": {"company_name": "NTPC Limited", "aliases": ["NTPC Limited", "NTPC India"], "source": "manual Nifty-50 company-name mapping", "notes": "NTPC acronym is company usage."},
    "COALINDIA": {"company_name": "Coal India Limited", "aliases": ["Coal India"], "source": "manual Nifty-50 company-name mapping", "notes": "Company phrase."},
    "JSWSTEEL": {"company_name": "JSW Steel Limited", "aliases": ["JSW Steel"], "source": "manual Nifty-50 company-name mapping", "notes": "Steel phrase."},
    "TATASTEEL": {"company_name": "Tata Steel Limited", "aliases": ["Tata Steel"], "source": "manual Nifty-50 company-name mapping", "notes": "Steel phrase."},
    "CIPLA": {"company_name": "Cipla Limited", "aliases": ["Cipla"], "source": "manual Nifty-50 company-name mapping", "notes": "Company name."},
    "DRREDDY": {"company_name": "Dr Reddy's Laboratories Limited", "aliases": ["Dr Reddy's Laboratories", "Dr Reddy's Labs"], "source": "manual Nifty-50 company-name mapping", "notes": "Apostrophe variants may differ."},
    "DIVISLAB": {"company_name": "Divi's Laboratories Limited", "aliases": ["Divi's Laboratories", "Divis Laboratories"], "source": "manual Nifty-50 company-name mapping", "notes": "Apostrophe variants included."},
    "EICHERMOT": {"company_name": "Eicher Motors Limited", "aliases": ["Eicher Motors"], "source": "manual Nifty-50 company-name mapping", "notes": "Auto phrase."},
    "HEROMOTOCO": {"company_name": "Hero MotoCorp Limited", "aliases": ["Hero MotoCorp"], "source": "manual Nifty-50 company-name mapping", "notes": "Auto phrase."},
    "BAJAJFINSV": {"company_name": "Bajaj Finserv Limited", "aliases": ["Bajaj Finserv"], "source": "manual Nifty-50 company-name mapping", "notes": "Distinct from Bajaj Finance."},
    "M&M": {"company_name": "Mahindra and Mahindra Limited", "aliases": ["Mahindra and Mahindra", "M&M"], "source": "manual Nifty-50 company-name mapping", "notes": "Ampersand alias can be noisy; full phrase retained."},
    "GRASIM": {"company_name": "Grasim Industries Limited", "aliases": ["Grasim Industries"], "source": "manual Nifty-50 company-name mapping", "notes": "Company phrase."},
    "HDFCLIFE": {"company_name": "HDFC Life Insurance Company Limited", "aliases": ["HDFC Life", "HDFC Life Insurance"], "source": "manual Nifty-50 company-name mapping", "notes": "Distinct from HDFC Bank."},
    "SBILIFE": {"company_name": "SBI Life Insurance Company Limited", "aliases": ["SBI Life", "SBI Life Insurance"], "source": "manual Nifty-50 company-name mapping", "notes": "Distinct from State Bank of India."},
    "APOLLOHOSP": {"company_name": "Apollo Hospitals Enterprise Limited", "aliases": ["Apollo Hospitals", "Apollo Hospitals Enterprise"], "source": "manual Nifty-50 company-name mapping", "notes": "Hospital phrase."},
    "BRITANNIA": {"company_name": "Britannia Industries Limited", "aliases": ["Britannia Industries"], "source": "manual Nifty-50 company-name mapping", "notes": "Company phrase."},
    "ADANIPORTS": {"company_name": "Adani Ports and Special Economic Zone Limited", "aliases": ["Adani Ports", "Adani Ports SEZ"], "source": "manual Nifty-50 company-name mapping", "notes": "Adani group coverage can be confounded."},
    "BPCL": {"company_name": "Bharat Petroleum Corporation Limited", "aliases": ["Bharat Petroleum", "BPCL"], "source": "manual Nifty-50 company-name mapping", "notes": "Oil marketing phrase."},
    "HINDALCO": {"company_name": "Hindalco Industries Limited", "aliases": ["Hindalco Industries", "Hindalco"], "source": "manual Nifty-50 company-name mapping", "notes": "Company phrase."},
    "INDUSINDBK": {"company_name": "IndusInd Bank Limited", "aliases": ["IndusInd Bank"], "source": "manual Nifty-50 company-name mapping", "notes": "Bank-specific phrase."},
    "TATACONSUM": {"company_name": "Tata Consumer Products Limited", "aliases": ["Tata Consumer Products", "Tata Consumer"], "source": "manual Nifty-50 company-name mapping", "notes": "Consumer phrase."},
    "SHRIRAMFIN": {"company_name": "Shriram Finance Limited", "aliases": ["Shriram Finance"], "source": "manual Nifty-50 company-name mapping", "notes": "Finance phrase."},
    "BAJAJ-AUTO": {"company_name": "Bajaj Auto Limited", "aliases": ["Bajaj Auto"], "source": "manual Nifty-50 company-name mapping", "notes": "Auto phrase."},
    "TRENT": {"company_name": "Trent Limited", "aliases": ["Trent Limited", "Trent retail"], "source": "manual Nifty-50 company-name mapping", "notes": "Trent alone can be a person/place; full phrase preferred."},
}


def mapped_companies(symbols: Iterable[str] | None = None, *, top: int | None = None) -> list[dict]:
    ordered = list(symbols) if symbols is not None else list(NIFTY50)
    if top is not None:
        ordered = ordered[: max(top, 0)]
    rows = []
    seen: set[str] = set()
    for symbol in ordered:
        symbol_key = str(symbol).upper()
        if symbol_key in seen:
            continue
        seen.add(symbol_key)
        rec = NSE_COMPANY_MAP.get(symbol_key)
        if not rec:
            continue
        row = dict(rec)
        row["symbol"] = symbol_key
        rows.append(row)
    return rows


def unmapped_symbols(symbols: Iterable[str]) -> list[str]:
    return [str(symbol).upper() for symbol in symbols if str(symbol).upper() not in NSE_COMPANY_MAP]


def build_company_query(mapping: dict, *, source_country: str = "india", source_lang: str = "english") -> str:
    terms = [mapping["company_name"], *(mapping.get("aliases") or [])]
    seen = []
    for term in terms:
        clean = str(term).strip()
        if clean and clean.lower() not in {item.lower() for item in seen}:
            seen.append(clean)
    quoted = " OR ".join(f'"{term}"' for term in seen)
    return f"({quoted}) sourcecountry:{source_country} sourcelang:{source_lang}"


def news_history(
    *,
    symbols: Iterable[str] | None = None,
    top: int = 5,
    years: int = 2,
    start: date | pd.Timestamp | None = None,
    end: date | pd.Timestamp | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetch_text: FetchText | None = None,
    refresh: bool = True,
    timeout: int = 20,
    retries: int = 2,
    min_request_delay: float = DEFAULT_MIN_REQUEST_DELAY,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    sleep_func: SleepFunc = time.sleep,
    now_func: NowFunc = time.monotonic,
    rate_state: RateLimitState | None = None,
) -> pd.DataFrame | None:
    end_ts = pd.Timestamp(end).normalize() if end is not None else pd.Timestamp.today().normalize()
    start_ts = pd.Timestamp(start).normalize() if start is not None else end_ts - pd.DateOffset(years=years)
    mappings = mapped_companies(symbols, top=top)
    if not mappings:
        return None

    frames = []
    failures = []
    state = rate_state or RateLimitState()
    for mapping in mappings:
        frame = fetch_company_timeline(
            mapping,
            start=start_ts,
            end=end_ts,
            cache_dir=cache_dir,
            fetch_text=fetch_text,
            refresh=refresh,
            timeout=timeout,
            retries=retries,
            min_request_delay=min_request_delay,
            backoff_base=backoff_base,
            sleep_func=sleep_func,
            now_func=now_func,
            rate_state=state,
        )
        if frame is None or frame.empty:
            failures.append(mapping["symbol"])
            continue
        frames.append(frame)

    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True).replace([float("inf"), float("-inf")], pd.NA)
    out["date"] = pd.to_datetime(out["date"]).dt.date
    out = out.dropna(subset=["date", "symbol", "tone", "article_count"])
    out["article_count"] = pd.to_numeric(out["article_count"], errors="coerce")
    out["tone"] = pd.to_numeric(out["tone"], errors="coerce")
    out = out.dropna(subset=["tone", "article_count"])
    out = out[out["article_count"] > 0].sort_values(["symbol", "date"]).reset_index(drop=True)
    if out.empty:
        return None
    out.attrs["mapping_count"] = len(mappings)
    out.attrs["symbols_with_news"] = int(out["symbol"].nunique())
    out.attrs["symbols_without_news"] = failures
    out.attrs["cache_dir"] = str(cache_dir)
    out.attrs["source"] = "GDELT DOC API TimelineTone and TimelineVolRaw"
    out.attrs["request_events"] = list(state.events)
    out.attrs["rate_limited_requests"] = sum(1 for item in state.events if item.get("event") == "rate_limited")
    return out


def fetch_company_timeline(
    mapping: dict,
    *,
    start: date | pd.Timestamp,
    end: date | pd.Timestamp,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetch_text: FetchText | None = None,
    refresh: bool = True,
    timeout: int = 20,
    retries: int = 2,
    min_request_delay: float = DEFAULT_MIN_REQUEST_DELAY,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    sleep_func: SleepFunc = time.sleep,
    now_func: NowFunc = time.monotonic,
    rate_state: RateLimitState | None = None,
) -> pd.DataFrame | None:
    query = build_company_query(mapping)
    state = rate_state or RateLimitState()
    tone_raw = _load_or_fetch_raw(
        cache_dir=cache_dir,
        symbol=mapping["symbol"],
        query=query,
        mode="timelinetone",
        start=start,
        end=end,
        fetch_text=fetch_text,
        refresh=refresh,
        timeout=timeout,
        retries=retries,
        min_request_delay=min_request_delay,
        backoff_base=backoff_base,
        sleep_func=sleep_func,
        now_func=now_func,
        rate_state=state,
    )
    volume_raw = _load_or_fetch_raw(
        cache_dir=cache_dir,
        symbol=mapping["symbol"],
        query=query,
        mode="timelinevolraw",
        start=start,
        end=end,
        fetch_text=fetch_text,
        refresh=refresh,
        timeout=timeout,
        retries=retries,
        min_request_delay=min_request_delay,
        backoff_base=backoff_base,
        sleep_func=sleep_func,
        now_func=now_func,
        rate_state=state,
    )
    if tone_raw is None or volume_raw is None:
        return None

    tone = parse_timeline_payload(tone_raw, value_name="tone")
    volume = parse_timeline_payload(volume_raw, value_name="article_count")
    if tone is None or tone.empty or volume is None or volume.empty:
        return None

    merged = tone.merge(volume, on="date", how="inner")
    if merged.empty:
        return None
    merged["symbol"] = mapping["symbol"]
    merged["company_name"] = mapping["company_name"]
    merged["query"] = query
    merged["mapping_source"] = mapping.get("source", "")
    merged["mapping_notes"] = mapping.get("notes", "")
    return merged[["date", "symbol", "company_name", "tone", "article_count", "query", "mapping_source", "mapping_notes"]]


def parse_timeline_payload(raw: str, *, value_name: str) -> pd.DataFrame | None:
    if not raw or not raw.strip():
        return None
    stripped = raw.lstrip("\ufeff").strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        records = _json_timeline_records(payload)
        rows = [_normalize_record(record, value_name) for record in records]
    else:
        try:
            df = pd.read_csv(StringIO(stripped))
        except Exception:
            return None
        rows = [_normalize_record(row, value_name) for row in df.to_dict(orient="records")]

    rows = [row for row in rows if row is not None]
    if not rows:
        return None
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"]).dt.date
    out[value_name] = pd.to_numeric(out[value_name], errors="coerce")
    out = out.dropna(subset=["date", value_name]).sort_values("date")
    if out.empty:
        return None
    return out.groupby("date", as_index=False)[value_name].mean()


def _load_or_fetch_raw(
    *,
    cache_dir: Path,
    symbol: str,
    query: str,
    mode: str,
    start: date | pd.Timestamp,
    end: date | pd.Timestamp,
    fetch_text: FetchText | None,
    refresh: bool,
    timeout: int,
    retries: int,
    min_request_delay: float = DEFAULT_MIN_REQUEST_DELAY,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    sleep_func: SleepFunc = time.sleep,
    now_func: NowFunc = time.monotonic,
    rate_state: RateLimitState | None = None,
) -> str | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    url = _doc_url(query=query, mode=mode, start=start, end=end)
    path = _cache_path(cache_dir, symbol, mode, start, end, query)
    cache_key = str(path.resolve())
    state = rate_state or RateLimitState()
    if cache_key in state.request_cache:
        state.events.append({"event": "memory_cache_hit", "symbol": symbol, "mode": mode, "path": path.name})
        return state.request_cache[cache_key]
    if path.exists():
        raw = path.read_text(encoding="utf-8", errors="ignore")
        state.request_cache[cache_key] = raw
        state.events.append({"event": "disk_cache_hit", "symbol": symbol, "mode": mode, "path": path.name})
        return raw
    if not refresh:
        state.events.append({"event": "cache_miss_no_refresh", "symbol": symbol, "mode": mode, "path": path.name})
        return None

    fetcher = fetch_text or _fetch_url_text
    last_error = None
    for attempt in range(max(retries, 0) + 1):
        _respect_min_delay(state, min_request_delay, sleep_func=sleep_func, now_func=now_func)
        try:
            raw = fetcher(url, timeout)
            state.last_request_at = now_func()
            if raw and raw.strip():
                path.write_text(raw, encoding="utf-8")
                state.request_cache[cache_key] = raw
                state.events.append({"event": "fetched", "symbol": symbol, "mode": mode, "attempt": attempt, "path": path.name})
                return raw
            state.events.append({"event": "empty_response", "symbol": symbol, "mode": mode, "attempt": attempt})
        except HTTPError as exc:
            state.last_request_at = now_func()
            last_error = exc
            if exc.code in THROTTLE_STATUS_CODES:
                delay = _retry_delay(exc, attempt, backoff_base)
                state.events.append({
                    "event": "rate_limited",
                    "symbol": symbol,
                    "mode": mode,
                    "attempt": attempt,
                    "status": exc.code,
                    "sleep_seconds": delay,
                })
                if attempt < retries:
                    sleep_func(delay)
                    continue
            state.events.append({"event": "http_error", "symbol": symbol, "mode": mode, "attempt": attempt, "status": exc.code})
            break
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            state.last_request_at = now_func()
            last_error = exc
            state.events.append({"event": "fetch_error", "symbol": symbol, "mode": mode, "attempt": attempt, "error": type(exc).__name__})
            if attempt < retries:
                sleep_func(backoff_base * (2 ** attempt))
                continue
            break

    _ = last_error
    return None


def coverage_probe(
    *,
    symbols: Iterable[str] = PROBE_SYMBOLS,
    as_of: date | pd.Timestamp | None = None,
    window_days: int = PROBE_WINDOW_DAYS,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetch_text: FetchText | None = None,
    refresh: bool = False,
    timeout: int = 20,
    retries: int = 2,
    min_request_delay: float = DEFAULT_MIN_REQUEST_DELAY,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    sleep_func: SleepFunc = time.sleep,
    now_func: NowFunc = time.monotonic,
) -> dict:
    """Probe four 30-day windows for real GDELT DOC tone/volume coverage."""
    as_of_ts = pd.Timestamp(as_of).normalize() if as_of is not None else pd.Timestamp.today().normalize()
    offsets = [
        ("current", pd.DateOffset(days=0)),
        ("six_months_ago", pd.DateOffset(months=6)),
        ("one_year_ago", pd.DateOffset(years=1)),
        ("two_years_ago", pd.DateOffset(years=2)),
    ]
    mappings = mapped_companies(symbols, top=None)
    requested = [str(symbol).upper() for symbol in symbols]
    unmapped = unmapped_symbols(requested)
    state = RateLimitState()
    windows: list[dict] = []

    for mapping in mappings:
        query = build_company_query(mapping)
        for label, offset in offsets:
            end = as_of_ts - offset
            start = end - pd.DateOffset(days=max(window_days - 1, 0))
            before = len(state.events)
            tone_raw = _load_or_fetch_raw(
                cache_dir=cache_dir,
                symbol=mapping["symbol"],
                query=query,
                mode="timelinetone",
                start=start,
                end=end,
                fetch_text=fetch_text,
                refresh=refresh,
                timeout=timeout,
                retries=retries,
                min_request_delay=min_request_delay,
                backoff_base=backoff_base,
                sleep_func=sleep_func,
                now_func=now_func,
                rate_state=state,
            )
            volume_raw = _load_or_fetch_raw(
                cache_dir=cache_dir,
                symbol=mapping["symbol"],
                query=query,
                mode="timelinevolraw",
                start=start,
                end=end,
                fetch_text=fetch_text,
                refresh=refresh,
                timeout=timeout,
                retries=retries,
                min_request_delay=min_request_delay,
                backoff_base=backoff_base,
                sleep_func=sleep_func,
                now_func=now_func,
                rate_state=state,
            )
            events = state.events[before:]
            tone = parse_timeline_payload(tone_raw, value_name="tone") if tone_raw else None
            volume = parse_timeline_payload(volume_raw, value_name="article_count") if volume_raw else None
            merged = 0
            if tone is not None and volume is not None and not tone.empty and not volume.empty:
                merged = int(tone.merge(volume, on="date", how="inner").shape[0])
            rate_limited = any(item.get("event") == "rate_limited" for item in events)
            cache_miss = any(item.get("event") == "cache_miss_no_refresh" for item in events)
            if merged > 0:
                status = "DATA_AVAILABLE"
            elif rate_limited:
                status = "RATE_LIMITED"
            elif cache_miss:
                status = "NOT_PROBED_CACHE_MISS"
            else:
                status = "NO_REAL_DATA"
            windows.append({
                "symbol": mapping["symbol"],
                "company_name": mapping["company_name"],
                "window": label,
                "start": str(pd.Timestamp(start).date()),
                "end": str(pd.Timestamp(end).date()),
                "tone_points": int(0 if tone is None else len(tone)),
                "volume_points": int(0 if volume is None else len(volume)),
                "merged_points": merged,
                "cache_hits": sum(1 for item in events if item.get("event") in {"disk_cache_hit", "memory_cache_hit"}),
                "network_fetches": sum(1 for item in events if item.get("event") == "fetched"),
                "rate_limited": rate_limited,
                "cache_miss": cache_miss,
                "status": status,
            })

    decision = _coverage_decision(requested, unmapped, windows)
    return {
        "decision": decision,
        "symbols_requested": requested,
        "symbols_mapped": len(mappings),
        "unmapped_symbols": unmapped,
        "window_days": int(window_days),
        "windows": windows,
        "request_summary": {
            "cache_hits": sum(1 for item in state.events if item.get("event") in {"disk_cache_hit", "memory_cache_hit"}),
            "network_fetches": sum(1 for item in state.events if item.get("event") == "fetched"),
            "rate_limited_requests": sum(1 for item in state.events if item.get("event") == "rate_limited"),
            "cache_misses_without_refresh": sum(1 for item in state.events if item.get("event") == "cache_miss_no_refresh"),
        },
        "source": "GDELT DOC API coverage probe using cached or fetched real tone/volume rows only",
    }


def _doc_url(*, query: str, mode: str, start: date | pd.Timestamp, end: date | pd.Timestamp) -> str:
    params = {
        "query": query,
        "mode": mode,
        "format": "json",
        "startdatetime": pd.Timestamp(start).strftime("%Y%m%d000000"),
        "enddatetime": pd.Timestamp(end).strftime("%Y%m%d235959"),
        "timelinesmooth": "0",
    }
    return f"{GDELT_DOC_API}?{urlencode(params)}"


def _cache_path(cache_dir: Path, symbol: str, mode: str, start, end, query: str) -> Path:
    digest = hashlib.sha1(f"{symbol}|{mode}|{pd.Timestamp(start).date()}|{pd.Timestamp(end).date()}|{query}".encode("utf-8")).hexdigest()[:16]
    return Path(cache_dir) / f"{symbol.lower()}_{mode}_{digest}.json"


def _fetch_url_text(url: str, timeout: int) -> str:
    req = Request(url, headers={"User-Agent": "SpencerResearch/1.0 (paper-only)"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _respect_min_delay(
    state: RateLimitState,
    min_request_delay: float,
    *,
    sleep_func: SleepFunc,
    now_func: NowFunc,
) -> None:
    if min_request_delay <= 0 or state.last_request_at is None:
        return
    elapsed = max(0.0, now_func() - state.last_request_at)
    remaining = min_request_delay - elapsed
    if remaining > 0:
        state.events.append({"event": "min_delay_sleep", "sleep_seconds": remaining})
        sleep_func(remaining)


def _retry_delay(exc: HTTPError, attempt: int, backoff_base: float) -> float:
    retry_after = None
    headers = getattr(exc, "headers", None)
    if headers is not None:
        try:
            retry_after = headers.get("Retry-After")
        except AttributeError:
            retry_after = None
    parsed = _parse_retry_after(retry_after)
    if parsed is not None:
        return parsed
    return float(backoff_base * (2 ** attempt))


def _parse_retry_after(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if dt is None:
        return None
    delay = (pd.Timestamp(dt).tz_convert("UTC") - pd.Timestamp.utcnow()).total_seconds()
    return max(0.0, float(delay))


def _coverage_decision(requested: list[str], unmapped: list[str], windows: list[dict]) -> str:
    if not requested or len(unmapped) == len(requested):
        return "DATA_UNAVAILABLE_MAPPING_TOO_THIN"
    if any(item.get("rate_limited") for item in windows):
        return "DATA_UNAVAILABLE_RATE_LIMITED"
    if not windows or not any(item.get("merged_points", 0) > 0 for item in windows):
        return "DATA_UNAVAILABLE_INSUFFICIENT_HISTORY"

    by_symbol: dict[str, list[dict]] = {}
    for item in windows:
        by_symbol.setdefault(str(item["symbol"]), []).append(item)
    complete_symbols = [
        symbol
        for symbol, items in by_symbol.items()
        if len(items) >= 4 and all(item.get("merged_points", 0) > 0 for item in items)
    ]
    if complete_symbols:
        return "DATA_AVAILABLE_FOR_RESEARCH"

    current_data = any(
        item.get("window") == "current" and item.get("merged_points", 0) > 0
        for item in windows
    )
    older_missing = any(
        item.get("window") != "current" and item.get("merged_points", 0) == 0
        for item in windows
    )
    unknown_windows = any(item.get("status") == "NOT_PROBED_CACHE_MISS" for item in windows)
    if current_data and older_missing and not unknown_windows:
        return "NEEDS_PAID_OR_BULK_DATA"
    return "DATA_UNAVAILABLE_INSUFFICIENT_HISTORY"


def _json_timeline_records(payload) -> list[dict]:
    out: list[dict] = []
    if isinstance(payload, list):
        for item in payload:
            out.extend(_json_timeline_records(item))
        return out
    if not isinstance(payload, dict):
        return out
    if _has_date_and_value(payload):
        out.append(payload)
    for key in ("timeline", "data", "results", "rows", "series"):
        value = payload.get(key)
        if isinstance(value, (list, dict)):
            out.extend(_json_timeline_records(value))
    return out


def _has_date_and_value(record: dict) -> bool:
    keys = {str(k).lower() for k in record}
    has_date = bool(keys & {"date", "datetime", "time", "timestamp"})
    has_value = bool(keys & {"value", "tone", "avgtone", "average_tone", "averagetone", "count", "article_count", "articles"})
    return has_date and has_value


def _normalize_record(record: dict, value_name: str) -> dict | None:
    lowered = {str(key).strip().lower().replace(" ", "_"): value for key, value in record.items()}
    day = _pick(lowered, "date", "datetime", "time", "timestamp")
    if day is None:
        return None
    parsed_day = pd.to_datetime(day, errors="coerce")
    if pd.isna(parsed_day):
        return None
    if value_name == "tone":
        value = _pick(lowered, "tone", "avgtone", "average_tone", "averagetone", "value")
    else:
        value = _pick(lowered, "article_count", "articles", "count", "value")
    numeric = _to_float(value)
    if numeric is None:
        return None
    return {"date": parsed_day.date(), value_name: numeric}


def _pick(row: dict, *keys: str):
    for key in keys:
        if key in row:
            return row[key]
    return None


def _to_float(value) -> float | None:
    try:
        text = str(value).replace(",", "").strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return None
        out = float(text)
    except (TypeError, ValueError):
        return None
    return out if pd.notna(out) else None
