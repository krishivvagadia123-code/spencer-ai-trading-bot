"""
Read-only NSE bulk/block-deal ingestion.

The module normalizes only real NSE disclosure rows from public CSV/JSON
responses. If a response is missing, malformed, or does not contain a symbol,
the caller receives None or an empty filtered set; no deal is fabricated.
"""

from __future__ import annotations

import json
import time
from datetime import date
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / ".cache" / "nse_block_deals"
DEFAULT_MANUAL_DIR = ROOT / "data" / "block_deals"
NSE_API_BASE = "https://www.nseindia.com/api/historical/{deal_type}-deals"
NSE_SESSION_URL = "https://www.nseindia.com/report-detail/display-bulk-and-block-deals"
STATIC_ARCHIVE_BASE = "https://archives.nseindia.com/content/equities/{deal_type}.csv"
VALID_DEAL_TYPES = {"bulk", "block"}
SOURCE_PRIORITY = ("manual_csv", "static_archive", "dynamic_api")
SOURCE_RANK = {source: rank for rank, source in enumerate(SOURCE_PRIORITY)}

FetchText = Callable[[str, int], str]


def api_url(deal_type: str, start: date | pd.Timestamp, end: date | pd.Timestamp) -> str:
    deal_type = _normalize_deal_type(deal_type)
    start_date = pd.Timestamp(start).date().strftime("%d-%m-%Y")
    end_date = pd.Timestamp(end).date().strftime("%d-%m-%Y")
    return f"{NSE_API_BASE.format(deal_type=deal_type)}?{urlencode({'from': start_date, 'to': end_date})}"


def static_archive_url(deal_type: str) -> str:
    return STATIC_ARCHIVE_BASE.format(deal_type=_normalize_deal_type(deal_type))


def parse_deals_payload(raw: str, *, deal_type: str) -> pd.DataFrame | None:
    if not raw or not raw.strip():
        return None
    deal_type = _normalize_deal_type(deal_type)
    data = _payload_to_rows(raw)
    if data is None:
        return None
    rows = [_normalize_row(row, deal_type) for row in data]
    rows = [row for row in rows if row is not None]
    if not rows:
        return None
    out = pd.DataFrame(rows)
    out = out.dropna(subset=["date", "symbol", "side", "qty", "price"])
    if out.empty:
        return None
    out["date"] = pd.to_datetime(out["date"]).dt.date
    out["symbol"] = out["symbol"].astype(str).str.strip().str.upper()
    out["side"] = out["side"].astype(str).str.strip().str.upper()
    out = out[out["side"].isin(["BUY", "SELL"])]
    if out.empty:
        return None
    return out.sort_values(["date", "deal_type", "symbol", "side", "client"]).reset_index(drop=True)


def load_manual_deals(
    deal_type: str | None = None,
    *,
    manual_dir: Path = DEFAULT_MANUAL_DIR,
) -> pd.DataFrame | None:
    """Load operator-supplied NSE CSV exports without inventing missing rows."""
    requested_type = _normalize_deal_type(deal_type) if deal_type is not None else None
    folder = Path(manual_dir)
    if not folder.exists() or not folder.is_dir():
        return None

    frames: list[pd.DataFrame] = []
    for path in sorted(folder.glob("*.csv")):
        inferred = _deal_type_from_filename(path)
        if inferred is None:
            continue
        if requested_type is not None and inferred != requested_type:
            continue
        parsed = parse_deals_payload(path.read_text(encoding="utf-8", errors="ignore"), deal_type=inferred)
        if parsed is not None:
            parsed = _with_source(parsed, "manual_csv")
            parsed["source_file"] = path.name
            frames.append(parsed)
    return _concat_frames(frames)


def fetch_static_archive(
    deal_type: str,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetch_text: FetchText | None = None,
    fetch_day: date | pd.Timestamp | None = None,
    retries: int = 2,
    timeout: int = 15,
) -> pd.DataFrame | None:
    """Fetch NSE's rolling static bulk.csv/block.csv archive and cache by day."""
    deal_type = _normalize_deal_type(deal_type)
    day = pd.Timestamp(fetch_day).date() if fetch_day is not None else pd.Timestamp.today().date()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"static_{deal_type}_{day:%Y%m%d}.csv"
    if cache_path.exists():
        parsed = parse_deals_payload(cache_path.read_text(encoding="utf-8", errors="ignore"), deal_type=deal_type)
        return _with_source(parsed, "static_archive")

    url = static_archive_url(deal_type)
    fetcher = fetch_text or _fetch_static_url_text
    last_text: str | None = None
    for attempt in range(max(retries, 0) + 1):
        try:
            last_text = fetcher(url, timeout)
            parsed = parse_deals_payload(last_text, deal_type=deal_type)
            if parsed is not None:
                cache_path.write_text(last_text, encoding="utf-8")
                return _with_source(parsed, "static_archive")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            pass
        if attempt < retries:
            time.sleep(0.35 * (attempt + 1))
    if last_text:
        return _with_source(parse_deals_payload(last_text, deal_type=deal_type), "static_archive")
    return None


def fetch_deals(
    deal_type: str,
    *,
    start: date | pd.Timestamp,
    end: date | pd.Timestamp,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetch_text: FetchText | None = None,
    retries: int = 2,
    timeout: int = 15,
) -> pd.DataFrame | None:
    deal_type = _normalize_deal_type(deal_type)
    start_ts = pd.Timestamp(start).date()
    end_ts = pd.Timestamp(end).date()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{deal_type}_{start_ts:%Y%m%d}_{end_ts:%Y%m%d}.json"
    if cache_path.exists():
        parsed = parse_deals_payload(cache_path.read_text(encoding="utf-8", errors="ignore"), deal_type=deal_type)
        return _with_source(parsed, "dynamic_api")

    url = api_url(deal_type, start_ts, end_ts)
    fetcher = fetch_text or _fetch_url_text
    last_text: str | None = None
    for attempt in range(max(retries, 0) + 1):
        try:
            last_text = fetcher(url, timeout)
            parsed = parse_deals_payload(last_text, deal_type=deal_type)
            if parsed is not None:
                cache_path.write_text(last_text, encoding="utf-8")
                return _with_source(parsed, "dynamic_api")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            pass
        if attempt < retries:
            time.sleep(0.35 * (attempt + 1))
    if last_text:
        return _with_source(parse_deals_payload(last_text, deal_type=deal_type), "dynamic_api")
    return None


def deals_history(
    symbols: Iterable[str],
    *,
    years: int = 2,
    start: date | pd.Timestamp | None = None,
    end: date | pd.Timestamp | None = None,
    deal_types: Iterable[str] = ("bulk", "block"),
    cache_dir: Path = DEFAULT_CACHE_DIR,
    manual_dir: Path = DEFAULT_MANUAL_DIR,
    fetch_manual: Callable[..., pd.DataFrame | None] = load_manual_deals,
    fetch_static: Callable[..., pd.DataFrame | None] = fetch_static_archive,
    fetch_range: Callable[..., pd.DataFrame | None] = fetch_deals,
    allow_dynamic_fallback: bool = True,
) -> pd.DataFrame | None:
    symbol_set = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
    if not symbol_set:
        return None
    end_ts = pd.Timestamp(end).normalize() if end is not None else pd.Timestamp.today().normalize()
    start_ts = pd.Timestamp(start).normalize() if start is not None else end_ts - pd.DateOffset(years=years)
    frames: list[pd.DataFrame] = []

    # Manual CSVs and static archives are real rows and are ingested once per
    # source/type, then filtered across all requested symbols.
    for deal_type in deal_types:
        normalized = _normalize_deal_type(deal_type)
        for source_frame in (
            fetch_manual(normalized, manual_dir=manual_dir),
            fetch_static(normalized, cache_dir=cache_dir),
        ):
            if source_frame is None or source_frame.empty:
                continue
            frames.append(source_frame)

    # The dynamic API is bot-protected in many environments. Treat it only as a
    # best-effort fallback after manual/static sources produce no rows.
    if allow_dynamic_fallback and not frames:
        windows = _date_windows(start_ts.date(), end_ts.date(), max_days=90)
        for deal_type in deal_types:
            normalized = _normalize_deal_type(deal_type)
            for lo, hi in windows:
                df = fetch_range(normalized, start=lo, end=hi, cache_dir=cache_dir)
                if df is None or df.empty:
                    continue
                frames.append(df)

    if not frames:
        return None

    out = _concat_frames(frames)
    if out is None or out.empty:
        return None
    out = out[
        out["symbol"].isin(symbol_set)
        & (pd.to_datetime(out["date"]) >= start_ts)
        & (pd.to_datetime(out["date"]) <= end_ts)
    ].copy()
    if out.empty:
        return None
    out["_source_rank"] = out["source"].map(SOURCE_RANK).fillna(99)
    out = out.sort_values(["_source_rank", "date", "deal_type", "symbol", "side"])
    out = out.drop_duplicates(subset=["date", "symbol", "side", "qty", "price", "client", "deal_type"], keep="first")
    out = out.drop(columns=["_source_rank"])
    source_counts = {str(k): int(v) for k, v in out["source"].value_counts().items()}
    out = out.sort_values(["date", "deal_type", "symbol", "side"]).reset_index(drop=True)
    out.attrs["source_counts"] = source_counts
    out.attrs["source_priority"] = list(SOURCE_PRIORITY)
    return out


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame | None:
    usable = [frame.copy() for frame in frames if frame is not None and not frame.empty]
    if not usable:
        return None
    out = pd.concat(usable, ignore_index=True)
    if "source" not in out.columns:
        out["source"] = "unknown"
    if "source_file" not in out.columns:
        out["source_file"] = ""
    out["source_file"] = out["source_file"].fillna("")
    return out


def _with_source(df: pd.DataFrame | None, source: str) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    out = df.copy()
    out["source"] = source
    if "source_file" not in out.columns:
        out["source_file"] = ""
    return out


def _deal_type_from_filename(path: Path) -> str | None:
    name = path.name.lower()
    if "bulk" in name:
        return "bulk"
    if "block" in name:
        return "block"
    return None


def _payload_to_rows(raw: str) -> list[dict] | None:
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        for key in ("data", "bulkDeals", "blockDeals"):
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


def _normalize_row(row: dict, deal_type: str) -> dict | None:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    date_value = _pick(lowered, "date", "bd_dt_date", "bd_date", "trade_date", "deal_date")
    symbol = _pick(lowered, "symbol", "bd_symbol", "security symbol", "security_symbol")
    side = _pick(lowered, "buy/sell", "bd_buy_sell", "side", "transaction type", "buy_sell")
    qty = _pick(lowered, "quantity traded", "bd_qty_trd", "qty", "quantity", "traded quantity")
    price = _pick(lowered, "trade price / wght. avg. price", "bd_tp_watp", "price", "trade price", "weighted average price")
    client = _pick(lowered, "client name", "bd_client_name", "client", "name of the client")
    if date_value is None or symbol is None or side is None or qty is None or price is None:
        return None

    side_text = str(side).strip().upper()
    if side_text in {"B", "BUY "}:
        side_text = "BUY"
    elif side_text in {"S", "SELL "}:
        side_text = "SELL"
    elif "BUY" in side_text:
        side_text = "BUY"
    elif "SELL" in side_text:
        side_text = "SELL"

    parsed_date = pd.to_datetime(date_value, errors="coerce", dayfirst=True)
    if pd.isna(parsed_date):
        return None
    qty_value = _to_float(qty)
    price_value = _to_float(price)
    if qty_value is None or price_value is None:
        return None
    return {
        "date": parsed_date.date(),
        "symbol": str(symbol).strip().upper(),
        "side": side_text,
        "qty": qty_value,
        "price": price_value,
        "client": str(client).strip() if client is not None else "",
        "deal_type": deal_type,
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
        if not text or text.lower() == "nan" or text == "-":
            return None
        out = float(text)
    except (TypeError, ValueError):
        return None
    return out if pd.notna(out) else None


def _normalize_deal_type(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in VALID_DEAL_TYPES:
        raise ValueError(f"unsupported NSE deal type: {value}")
    return normalized


def _date_windows(start: date, end: date, *, max_days: int) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    lo = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    while lo <= end_ts:
        hi = min(lo + pd.Timedelta(days=max_days - 1), end_ts)
        windows.append((lo.date(), hi.date()))
        lo = hi + pd.Timedelta(days=1)
    return windows


def _fetch_url_text(url: str, timeout: int) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SpencerResearch/1.0",
        "Accept": "application/json,text/csv,text/plain,*/*",
        "Referer": NSE_SESSION_URL,
        "Origin": "https://www.nseindia.com",
        "Connection": "keep-alive",
    }
    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    # NSE commonly requires a browser session cookie before serving JSON APIs.
    session_req = Request(NSE_SESSION_URL, headers={**headers, "Accept": "text/html,*/*"})
    with opener.open(session_req, timeout=timeout) as resp:
        resp.read()

    req = Request(url, headers=headers)
    with opener.open(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="ignore")


def _fetch_static_url_text(url: str, timeout: int) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 SpencerResearch/1.0",
            "Accept": "text/csv,text/plain,*/*",
            "Referer": "https://www.nseindia.com/",
        },
    )
    with build_opener().open(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="ignore")
