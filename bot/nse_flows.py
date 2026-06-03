"""
Read-only FII/DII flow ingestion from NSE.

NSE's public FII/DII endpoint currently returns provisional current-day cash
market rows. This module caches only real endpoint responses and combines cached
history with the latest fetch. Missing, malformed, or too-thin data returns None
or a short real series; no institutional flow is fabricated.
"""

from __future__ import annotations

import json
import time
from datetime import date
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / ".cache" / "nse_flows"
NSE_REPORT_URL = "https://www.nseindia.com/reports/fii-dii"
NSE_FIIDII_API = "https://www.nseindia.com/api/fiidiiTradeReact"

FetchText = Callable[[str, int], str]


def parse_flows_payload(raw: str) -> pd.DataFrame | None:
    if not raw or not raw.strip():
        return None
    rows = _payload_to_rows(raw)
    if not rows:
        return None

    by_date: dict[date, dict] = {}
    for row in rows:
        normalized = _normalize_row(row)
        if normalized is None:
            continue
        day = normalized.pop("date")
        category = normalized.pop("category")
        out = by_date.setdefault(day, {"date": day})
        prefix = "fii" if category == "fii" else "dii"
        out[f"{prefix}_buy"] = normalized["buy"]
        out[f"{prefix}_sell"] = normalized["sell"]
        out[f"{prefix}_net"] = normalized["net"]

    records = []
    for item in by_date.values():
        if item.get("fii_net") is None or item.get("dii_net") is None:
            continue
        records.append(item)
    if not records:
        return None

    out = pd.DataFrame(records)
    for col in ("fii_buy", "fii_sell", "fii_net", "dii_buy", "dii_sell", "dii_net"):
        if col not in out.columns:
            out[col] = pd.NA
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["date", "fii_net", "dii_net"])
    if out.empty:
        return None
    out["date"] = pd.to_datetime(out["date"]).dt.date
    return out.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)


def fetch_current_flows(
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetch_text: FetchText | None = None,
    retries: int = 2,
    timeout: int = 15,
) -> pd.DataFrame | None:
    """Fetch current official NSE FII/DII rows and cache the raw response."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetcher = fetch_text or _fetch_url_text
    last_text: str | None = None
    for attempt in range(max(retries, 0) + 1):
        try:
            last_text = fetcher(NSE_FIIDII_API, timeout)
            parsed = parse_flows_payload(last_text)
            if parsed is not None:
                _cache_payload(cache_dir, parsed, last_text)
                return _with_source(parsed, "nse_fiidiiTradeReact")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            pass
        if attempt < retries:
            time.sleep(0.35 * (attempt + 1))
    if last_text:
        return _with_source(parse_flows_payload(last_text), "nse_fiidiiTradeReact")
    return None


def flow_history(
    *,
    years: int = 2,
    start: date | pd.Timestamp | None = None,
    end: date | pd.Timestamp | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetch_current: Callable[..., pd.DataFrame | None] = fetch_current_flows,
    refresh: bool = True,
) -> pd.DataFrame | None:
    """Return cached official rows plus the latest real NSE fetch, filtered by date."""
    end_ts = pd.Timestamp(end).normalize() if end is not None else pd.Timestamp.today().normalize()
    start_ts = pd.Timestamp(start).normalize() if start is not None else end_ts - pd.DateOffset(years=years)
    frames: list[pd.DataFrame] = []

    cached = load_cached_flows(cache_dir=cache_dir)
    if cached is not None:
        frames.append(cached)
    if refresh:
        latest = fetch_current(cache_dir=cache_dir)
        if latest is not None:
            frames.append(latest)

    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.date
    out = out[
        (pd.to_datetime(out["date"]) >= start_ts)
        & (pd.to_datetime(out["date"]) <= end_ts)
    ].copy()
    if out.empty:
        return None
    out = out.sort_values(["date", "source"]).drop_duplicates(subset=["date"], keep="last")
    out = out.sort_values("date").reset_index(drop=True)
    out.attrs["source_counts"] = {str(k): int(v) for k, v in out["source"].value_counts().items()}
    out.attrs["source"] = "NSE FII/DII provisional cash market endpoint and local cache"
    return out


def load_cached_flows(*, cache_dir: Path = DEFAULT_CACHE_DIR) -> pd.DataFrame | None:
    folder = Path(cache_dir)
    if not folder.exists() or not folder.is_dir():
        return None
    frames: list[pd.DataFrame] = []
    for path in sorted(folder.glob("fiidii_*.json")):
        parsed = parse_flows_payload(path.read_text(encoding="utf-8", errors="ignore"))
        if parsed is not None:
            parsed = _with_source(parsed, "cache")
            parsed["source_file"] = path.name
            frames.append(parsed)
    for path in sorted(folder.glob("fiidii_*.csv")):
        parsed = parse_flows_payload(path.read_text(encoding="utf-8", errors="ignore"))
        if parsed is not None:
            parsed = _with_source(parsed, "cache")
            parsed["source_file"] = path.name
            frames.append(parsed)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def _payload_to_rows(raw: str) -> list[dict] | None:
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        for key in ("data", "records", "items"):
            rows = payload.get(key) if isinstance(payload, dict) else None
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return None

    try:
        from io import StringIO

        df = pd.read_csv(StringIO(raw))
    except Exception:
        return None
    if df.empty:
        return None
    return df.to_dict(orient="records")


def _normalize_row(row: dict) -> dict | None:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    category = _pick(lowered, "category", "investor category", "client type")
    day = _pick(lowered, "date", "trade date", "dt")
    buy = _pick(lowered, "buyvalue", "buy value", "gross purchase", "buy")
    sell = _pick(lowered, "sellvalue", "sell value", "gross sales", "sell")
    net = _pick(lowered, "netvalue", "net value", "net")
    if category is None or day is None:
        return None

    cat = str(category).strip().upper()
    if "FII" in cat or "FPI" in cat:
        category_key = "fii"
    elif "DII" in cat:
        category_key = "dii"
    else:
        return None

    parsed_date = pd.to_datetime(day, errors="coerce", dayfirst=True)
    if pd.isna(parsed_date):
        return None
    buy_value = _to_float(buy)
    sell_value = _to_float(sell)
    net_value = _to_float(net)
    if net_value is None and buy_value is not None and sell_value is not None:
        net_value = buy_value - sell_value
    if net_value is None:
        return None
    return {
        "date": parsed_date.date(),
        "category": category_key,
        "buy": buy_value,
        "sell": sell_value,
        "net": net_value,
    }


def _pick(row: dict, *keys: str):
    for key in keys:
        if key in row:
            return row[key]
    normalized = {key.replace("_", " ").strip(): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(key.replace("_", " ").strip())
        if value is not None:
            return value
    return None


def _to_float(value) -> float | None:
    try:
        text = str(value).replace(",", "").strip()
        if not text or text.lower() in {"nan", "none"} or text == "-":
            return None
        out = float(text)
    except (TypeError, ValueError):
        return None
    return out if pd.notna(out) else None


def _with_source(df: pd.DataFrame | None, source: str) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    out = df.copy()
    out["source"] = source
    if "source_file" not in out.columns:
        out["source_file"] = ""
    return out


def _cache_payload(cache_dir: Path, parsed: pd.DataFrame, raw: str) -> None:
    for day in sorted(pd.to_datetime(parsed["date"]).dt.date.unique()):
        path = cache_dir / f"fiidii_{day:%Y%m%d}.json"
        path.write_text(raw, encoding="utf-8")


def _fetch_url_text(url: str, timeout: int) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SpencerResearch/1.0",
        "Accept": "application/json,text/plain,*/*",
        "Referer": NSE_REPORT_URL,
        "Origin": "https://www.nseindia.com",
        "Connection": "keep-alive",
    }
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    session_req = Request(NSE_REPORT_URL, headers={**headers, "Accept": "text/html,*/*"})
    with opener.open(session_req, timeout=timeout) as resp:
        resp.read()

    req = Request(url, headers=headers)
    with opener.open(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="ignore")
