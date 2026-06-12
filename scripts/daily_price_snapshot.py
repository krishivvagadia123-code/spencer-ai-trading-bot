"""Append one real daily RELIANCE price snapshot to kite_bot.db.

This script is intentionally paper-only and read-only with respect to markets:
it calls the existing Spencer quote server code path for prices and never
places broker orders or invents fallback prices.
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

import spencer_quote_server
from bot.config import default_config
from bot.holidays import is_nse_holiday
from bot.market_data import IST, is_weekend, now_ist

DB_PATH = spencer_quote_server.DB_PATH
LOG_PATH = ROOT / "workflow" / "logs" / "price_snapshot.log"
QuoteFunc = Callable[[list[str]], list[dict]]


DAILY_PRICES_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    trade_date      TEXT    NOT NULL,
    close           REAL    NOT NULL,
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


@dataclass
class SnapshotResult:
    exit_code: int
    message: str
    inserted: int = 0
    rows: list[dict] = field(default_factory=list)
    skipped: bool = False


def _log(message: str, log_path: Path = LOG_PATH) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(IST).isoformat()
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {message}\n")


def _ordered_symbols(symbols: Iterable[str]) -> list[str]:
    out: list[str] = []
    for raw in symbols:
        symbol = str(raw or "").strip().upper()
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def configured_symbols() -> list[str]:
    return _ordered_symbols(default_config().universe)


def _coerce_trade_date(value: date | datetime | str | None) -> date:
    if value is None:
        return now_ist().date()
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(IST).date()
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _market_skip_reason(trade_date: date) -> str | None:
    dt = datetime.combine(trade_date, dtime.min, tzinfo=IST)
    if is_weekend(dt):
        return f"weekend ({dt.strftime('%A')})"
    if is_nse_holiday(trade_date):
        return f"NSE holiday ({trade_date.isoformat()})"
    return None


def ensure_daily_prices_table(conn: sqlite3.Connection) -> None:
    conn.execute(DAILY_PRICES_SCHEMA)


def _row_exists(conn: sqlite3.Connection, symbol: str, trade_date: date) -> bool:
    row = conn.execute(
        "SELECT 1 FROM daily_prices WHERE symbol=? AND trade_date=?",
        (symbol, trade_date.isoformat()),
    ).fetchone()
    return row is not None


def _float_or_none(value) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite numeric value: {value}")
    return parsed


def _session_date_from_timestamp(quote_timestamp: str) -> date:
    """IST session date the quote actually belongs to.

    The row must be labelled with the quote's own session, not the run date:
    a run before market close would otherwise file yesterday's close under
    today's date — a mislabelled (i.e. fake-looking) data point.
    """
    parsed = datetime.fromisoformat(str(quote_timestamp))
    if parsed.tzinfo is None:
        raise ValueError(f"quote timestamp missing timezone: {quote_timestamp}")
    return parsed.astimezone(IST).date()


def _build_insert_row(row: dict, trade_date: date) -> dict:
    symbol = str(row.get("symbol") or "").strip().upper()
    price = _float_or_none(row.get("price"))
    if not symbol:
        raise ValueError("quote row missing symbol")
    if price is None or price <= 0:
        raise ValueError(f"{symbol}: no real positive quote price available")

    quote_timestamp = row.get("timestamp") or row.get("fetchedAt")
    fetched_at = row.get("fetchedAt")
    source = row.get("source")
    if not quote_timestamp:
        raise ValueError(f"{symbol}: quote timestamp missing")
    if not fetched_at:
        raise ValueError(f"{symbol}: fetchedAt timestamp missing")
    if not source:
        raise ValueError(f"{symbol}: quote source missing")

    session_date = _session_date_from_timestamp(quote_timestamp)
    if session_date > trade_date:
        raise ValueError(
            f"{symbol}: quote session {session_date.isoformat()} is after "
            f"requested trade date {trade_date.isoformat()}"
        )
    if session_date == trade_date:
        prev = _float_or_none(row.get("previousClose"))
        change = _float_or_none(row.get("changePct"))
    else:
        # The quote belongs to an earlier session (e.g. run before today's
        # close). previousClose/changePct in the live payload are relative to
        # fetch time, not to that session — record the close under its true
        # session date and leave the rest honestly NULL.
        prev = None
        change = None

    market_state = str(row.get("marketState") or row.get("status") or "UNKNOWN").upper()
    return {
        "symbol": symbol,
        "trade_date": session_date.isoformat(),
        "close": round(price, 2),
        "prev_close": prev,
        "change_pct": change,
        "quote_timestamp": str(quote_timestamp),
        "fetched_at": str(fetched_at),
        "source": str(source),
        "market_state": market_state,
        "created_at": datetime.now(IST).isoformat(),
    }


def _insert_daily_price(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO daily_prices
            (symbol, trade_date, close, prev_close, change_pct,
             quote_timestamp, fetched_at, source, market_state, created_at)
        VALUES
            (:symbol, :trade_date, :close, :prev_close, :change_pct,
             :quote_timestamp, :fetched_at, :source, :market_state, :created_at)
        """,
        row,
    )


def snapshot_prices(
    *,
    db_path: Path | str = DB_PATH,
    trade_date: date | datetime | str | None = None,
    symbols: Sequence[str] | None = None,
    quote_func: QuoteFunc = spencer_quote_server._quote_rows,
    log_path: Path = LOG_PATH,
) -> SnapshotResult:
    trade_day = _coerce_trade_date(trade_date)
    requested = _ordered_symbols(symbols if symbols is not None else configured_symbols())
    if not requested:
        message = "price snapshot failed: configured universe is empty"
        _log(message, log_path)
        return SnapshotResult(exit_code=1, message=message)

    skip_reason = _market_skip_reason(trade_day)
    if skip_reason:
        message = f"price snapshot skipped for {trade_day.isoformat()}: {skip_reason}"
        _log(message, log_path)
        return SnapshotResult(exit_code=0, message=message, skipped=True)

    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_file)) as conn:
        ensure_daily_prices_table(conn)
        missing = [symbol for symbol in requested if not _row_exists(conn, symbol, trade_day)]
        conn.commit()

    if not missing:
        message = f"already snapshotted {', '.join(requested)} for {trade_day.isoformat()}"
        _log(message, log_path)
        return SnapshotResult(exit_code=0, message=message)

    try:
        quote_rows = quote_func(missing)
    except Exception as exc:
        message = f"price snapshot failed for {trade_day.isoformat()}: quote fetch failed: {exc}"
        _log(message, log_path)
        return SnapshotResult(exit_code=1, message=message)

    try:
        rows_by_symbol = {
            str(row.get("symbol") or "").strip().upper(): row
            for row in quote_rows
        }
        insert_rows = []
        for symbol in missing:
            row = rows_by_symbol.get(symbol)
            if row is None:
                raise ValueError(f"{symbol}: quote row missing")
            insert_rows.append(_build_insert_row(row, trade_day))
    except Exception as exc:
        message = f"price snapshot failed for {trade_day.isoformat()}: {exc}"
        _log(message, log_path)
        return SnapshotResult(exit_code=1, message=message)

    with sqlite3.connect(str(db_file)) as conn:
        ensure_daily_prices_table(conn)
        inserted_rows = []
        for row in insert_rows:
            if _row_exists(conn, row["symbol"], date.fromisoformat(row["trade_date"])):
                continue
            _insert_daily_price(conn, row)
            inserted_rows.append(row)
        conn.commit()

    if inserted_rows:
        summary = ", ".join(
            f"{row['symbol']} close={row['close']}" for row in inserted_rows
        )
        message = f"price snapshot inserted for {trade_day.isoformat()}: {summary}"
    else:
        message = f"already snapshotted {', '.join(requested)} for {trade_day.isoformat()}"
    _log(message, log_path)
    return SnapshotResult(
        exit_code=0,
        message=message,
        inserted=len(inserted_rows),
        rows=inserted_rows,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append today's real daily price snapshot.")
    parser.add_argument("--date", dest="trade_date", help="Trade date YYYY-MM-DD; defaults to today in IST.")
    parser.add_argument("--db", dest="db_path", type=Path, default=DB_PATH, help="SQLite DB path; defaults to kite_bot.db.")
    args = parser.parse_args(argv)

    result = snapshot_prices(db_path=args.db_path, trade_date=args.trade_date)
    print(result.message)
    for row in result.rows:
        print(
            f"{row['trade_date']} {row['symbol']} close={row['close']} "
            f"prev_close={row['prev_close']} source={row['source']} "
            f"quote_timestamp={row['quote_timestamp']}"
        )
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
