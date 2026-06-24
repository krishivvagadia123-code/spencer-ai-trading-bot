"""Append years of real RELIANCE daily OHLCV history to kite_bot.db.

Paper-only data plumbing. This script fetches RELIANCE.NS daily bars from
yfinance/OpenBB-compatible Yahoo data, writes only real fetched rows, and is
append-only/idempotent on (symbol, trade_date). It never places orders and
never fabricates fallback prices.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.holidays import is_nse_holiday
from bot.market_data import IST

DB_PATH = ROOT / "kite_bot.db"
SYMBOL = "RELIANCE"
YF_SYMBOL = "RELIANCE.NS"
SOURCE = "yfinance:RELIANCE.NS"


@dataclass(frozen=True)
class DailyBar:
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    adj_close: float | None = None


@dataclass
class DailyHistoryResult:
    inserted: int
    skipped_existing: int
    rows: list[dict] = field(default_factory=list)


FetchFunc = Callable[..., Iterable[DailyBar]]


DAILY_PRICES_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    trade_date      TEXT    NOT NULL,
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL    NOT NULL,
    adj_close       REAL,
    volume          REAL,
    prev_close      REAL,
    change_pct      REAL,
    quote_timestamp TEXT    NOT NULL,
    fetched_at      TEXT    NOT NULL,
    source          TEXT    NOT NULL,
    market_state    TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    UNIQUE(symbol, trade_date)
);
"""

MISSING_COLUMNS = {
    "open": "REAL",
    "high": "REAL",
    "low": "REAL",
    "adj_close": "REAL",
    "volume": "REAL",
    "prev_close": "REAL",
    "change_pct": "REAL",
}


def _finite_float(value, name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{name} is not finite: {value!r}")
    return parsed


def _normalize_bar(bar) -> DailyBar:
    if isinstance(bar, DailyBar):
        return bar
    if isinstance(bar, dict):
        raw_date = bar.get("trade_date") or bar.get("date") or bar.get("Date")
        if isinstance(raw_date, datetime):
            trade_date = raw_date.date()
        elif isinstance(raw_date, date):
            trade_date = raw_date
        else:
            trade_date = datetime.fromisoformat(str(raw_date)[:10]).date()
        return DailyBar(
            trade_date=trade_date,
            open=_finite_float(bar.get("open", bar.get("Open")), "open"),
            high=_finite_float(bar.get("high", bar.get("High")), "high"),
            low=_finite_float(bar.get("low", bar.get("Low")), "low"),
            close=_finite_float(bar.get("close", bar.get("Close")), "close"),
            volume=_finite_float(bar.get("volume", bar.get("Volume")), "volume"),
            adj_close=(
                None
                if bar.get("adj_close", bar.get("Adj Close")) is None
                else _finite_float(bar.get("adj_close", bar.get("Adj Close")), "adj_close")
            ),
        )
    raise TypeError(f"unsupported daily bar type: {type(bar).__name__}")


def _is_trading_day(trade_date: date) -> bool:
    return trade_date.weekday() < 5 and not is_nse_holiday(trade_date)


def ensure_daily_prices_table(conn: sqlite3.Connection) -> None:
    conn.execute(DAILY_PRICES_SCHEMA)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(daily_prices)").fetchall()}
    for column, decl in MISSING_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE daily_prices ADD COLUMN {column} {decl}")


def fetch_yfinance_daily(
    *,
    yf_symbol: str = YF_SYMBOL,
    start: str | date = "2010-01-01",
    end: str | date | None = None,
) -> list[DailyBar]:
    """Fetch daily bars using yfinance.

    Kept behind a small function so tests can inject synthetic fetched data and
    so a future OpenBB adapter can produce the same DailyBar sequence.
    """
    import yfinance as yf

    frame = yf.download(
        yf_symbol,
        start=str(start),
        end=None if end is None else str(end),
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if frame is None or frame.empty:
        return []
    if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
        frame.columns = [col[0] for col in frame.columns]

    bars: list[DailyBar] = []
    for idx, row in frame.iterrows():
        trade_date = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        bars.append(
            DailyBar(
                trade_date=trade_date,
                open=_finite_float(row["Open"], "open"),
                high=_finite_float(row["High"], "high"),
                low=_finite_float(row["Low"], "low"),
                close=_finite_float(row["Close"], "close"),
                adj_close=_finite_float(row["Adj Close"], "adj_close") if "Adj Close" in row else None,
                volume=_finite_float(row["Volume"], "volume"),
            )
        )
    return bars


def _existing_dates(conn: sqlite3.Connection, symbol: str) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT trade_date FROM daily_prices WHERE symbol=?", (symbol,))
    }


def append_daily_history(
    *,
    db_path: Path | str = DB_PATH,
    symbol: str = SYMBOL,
    start: str | date = "2010-01-01",
    end: str | date | None = None,
    fetch_func: FetchFunc = fetch_yfinance_daily,
) -> DailyHistoryResult:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(IST).isoformat()
    created_at = fetched_at
    bars = [_normalize_bar(bar) for bar in fetch_func(start=start, end=end)]

    with sqlite3.connect(str(db)) as conn:
        ensure_daily_prices_table(conn)
        existing = _existing_dates(conn, symbol)
        inserted_rows: list[dict] = []
        skipped_existing = 0
        prev_close: float | None = None
        for bar in sorted(bars, key=lambda item: item.trade_date):
            if not _is_trading_day(bar.trade_date):
                continue
            key = bar.trade_date.isoformat()
            if key in existing:
                skipped_existing += 1
                prev_close = bar.close
                continue
            if min(bar.open, bar.high, bar.low, bar.close) <= 0:
                raise ValueError(f"{key}: OHLC must be positive")
            if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
                raise ValueError(f"{key}: inconsistent OHLC range")
            change_pct = None if not prev_close else round((bar.close / prev_close - 1.0) * 100.0, 6)
            quote_ts = datetime.combine(bar.trade_date, dtime(15, 30), tzinfo=IST).isoformat()
            row = {
                "symbol": symbol,
                "trade_date": key,
                "open": round(bar.open, 2),
                "high": round(bar.high, 2),
                "low": round(bar.low, 2),
                "close": round(bar.close, 2),
                "adj_close": None if bar.adj_close is None else round(bar.adj_close, 2),
                "volume": round(bar.volume, 2),
                "prev_close": None if prev_close is None else round(prev_close, 2),
                "change_pct": change_pct,
                "quote_timestamp": quote_ts,
                "fetched_at": fetched_at,
                "source": SOURCE,
                "market_state": "CLOSED",
                "created_at": created_at,
            }
            conn.execute(
                """
                INSERT INTO daily_prices
                    (symbol, trade_date, open, high, low, close, adj_close,
                     volume, prev_close, change_pct, quote_timestamp,
                     fetched_at, source, market_state, created_at)
                VALUES
                    (:symbol, :trade_date, :open, :high, :low, :close,
                     :adj_close, :volume, :prev_close, :change_pct,
                     :quote_timestamp, :fetched_at, :source, :market_state,
                     :created_at)
                """,
                row,
            )
            inserted_rows.append(row)
            existing.add(key)
            prev_close = bar.close
        conn.commit()

    return DailyHistoryResult(
        inserted=len(inserted_rows),
        skipped_existing=skipped_existing,
        rows=inserted_rows,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append real RELIANCE.NS daily OHLCV history.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end")
    args = parser.parse_args(argv)
    result = append_daily_history(db_path=args.db, start=args.start, end=args.end)
    print(
        f"daily history inserted={result.inserted} "
        f"skipped_existing={result.skipped_existing} db={args.db}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
