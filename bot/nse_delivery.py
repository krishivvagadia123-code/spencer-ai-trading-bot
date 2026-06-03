"""
Read-only NSE delivery-volume ingestion.

This module fetches NSE `sec_bhavdata_full_DDMMYYYY.csv` archive rows and
returns only real archive values. Missing network responses, holidays, missing
symbols, or malformed files return None; no delivery quantity or percentage is
fabricated.
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / ".cache" / "nse_delivery"
NSE_ARCHIVE_URL = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{stamp}.csv"

FetchText = Callable[[str, int], str]


def archive_url(day: date | pd.Timestamp) -> str:
    ts = pd.Timestamp(day).date()
    return NSE_ARCHIVE_URL.format(stamp=ts.strftime("%d%m%Y"))


def parse_bhavcopy_csv(raw: str) -> pd.DataFrame | None:
    if not raw or not raw.strip():
        return None
    try:
        from io import StringIO

        df = pd.read_csv(StringIO(raw))
    except Exception:
        return None
    if df.empty:
        return None

    df.columns = [str(c).strip().upper() for c in df.columns]
    required = {"SYMBOL", "SERIES", "DATE1", "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER"}
    if not required.issubset(set(df.columns)):
        return None

    out = pd.DataFrame({
        "date": pd.to_datetime(df["DATE1"], errors="coerce").dt.date,
        "symbol": df["SYMBOL"].astype(str).str.strip().str.upper(),
        "series": df["SERIES"].astype(str).str.strip().str.upper(),
        "traded_qty": _to_number(df["TTL_TRD_QNTY"]),
        "deliverable_qty": _to_number(df["DELIV_QTY"]),
        "delivery_pct": _to_number(df["DELIV_PER"]),
    })
    out = out.replace([float("inf"), float("-inf")], pd.NA).dropna(
        subset=["date", "symbol", "traded_qty", "deliverable_qty", "delivery_pct"]
    )
    if out.empty:
        return None
    out = out[out["series"] == "EQ"].copy()
    if out.empty:
        return None
    return out.sort_values(["symbol", "date"]).reset_index(drop=True)


def fetch_bhavcopy(
    day: date | pd.Timestamp,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetch_text: FetchText | None = None,
    retries: int = 2,
    timeout: int = 15,
) -> pd.DataFrame | None:
    ts = pd.Timestamp(day).date()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"sec_bhavdata_full_{ts.strftime('%d%m%Y')}.csv"
    if cache_path.exists():
        return parse_bhavcopy_csv(cache_path.read_text(encoding="utf-8", errors="ignore"))

    url = archive_url(ts)
    fetcher = fetch_text or _fetch_url_text
    last_text: str | None = None
    for attempt in range(max(retries, 0) + 1):
        try:
            last_text = fetcher(url, timeout)
            if last_text and "DELIV_QTY" in last_text:
                cache_path.write_text(last_text, encoding="utf-8")
                return parse_bhavcopy_csv(last_text)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            pass
        if attempt < retries:
            time.sleep(0.35 * (attempt + 1))
    if last_text:
        return parse_bhavcopy_csv(last_text)
    return None


def delivery_history(
    symbol: str,
    *,
    years: int = 2,
    start: date | pd.Timestamp | None = None,
    end: date | pd.Timestamp | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetch_day: Callable[..., pd.DataFrame | None] = fetch_bhavcopy,
) -> pd.DataFrame | None:
    symbol = symbol.strip().upper()
    end_ts = pd.Timestamp(end).normalize() if end is not None else pd.Timestamp.today().normalize()
    start_ts = pd.Timestamp(start).normalize() if start is not None else end_ts - pd.DateOffset(years=years)
    frames: list[pd.DataFrame] = []

    for day in pd.date_range(start_ts, end_ts, freq="B"):
        daily = fetch_day(day.date(), cache_dir=cache_dir)
        if daily is None or daily.empty:
            continue
        sub = daily[daily["symbol"] == symbol].copy()
        if not sub.empty:
            frames.append(sub)

    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["date", "symbol"]).sort_values("date")
    out.index = pd.to_datetime(out["date"])
    return out[["symbol", "series", "traded_qty", "deliverable_qty", "delivery_pct"]]


def _to_number(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(",", "", regex=False).str.strip()
    cleaned = cleaned.replace({"-": pd.NA, "": pd.NA, "nan": pd.NA})
    return pd.to_numeric(cleaned, errors="coerce")


def _fetch_url_text(url: str, timeout: int) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 SpencerResearch/1.0",
            "Accept": "text/csv,text/plain,*/*",
            "Referer": "https://www.nseindia.com/",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="ignore")
