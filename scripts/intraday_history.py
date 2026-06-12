"""Append real RELIANCE intraday Yahoo chart candles to kite_bot.db.

No strategy logic lives here. The script only collects real chart candles,
keeps them append-only, and reports gaps honestly.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import spencer_quote_server
from bot.config import default_config
from bot.holidays import is_nse_holiday
from bot.market_data import IST, is_weekend

DB_PATH = spencer_quote_server.DB_PATH
LOG_PATH = ROOT / "workflow" / "logs" / "intraday_history.log"
INTERVAL_WINDOWS = {"15m": "60d", "1m": "7d"}
INTERVAL_MINUTES = {"15m": 15, "1m": 1}
SESSION_MINUTES = 375
ChartFunc = Callable[[str, str, str], dict]


INTRADAY_PRICES_SCHEMA = """
CREATE TABLE IF NOT EXISTS intraday_prices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT    NOT NULL,
    interval   TEXT    NOT NULL,
    ts         TEXT    NOT NULL,
    open       REAL    NOT NULL,
    high       REAL    NOT NULL,
    low        REAL    NOT NULL,
    close      REAL    NOT NULL,
    volume     REAL    NOT NULL,
    source     TEXT    NOT NULL,
    fetched_at TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    UNIQUE(symbol, interval, ts)
);
"""


@dataclass
class HistoryResult:
    exit_code: int
    message: str
    inserted: int = 0
    skipped_null_ohlc: int = 0
    skipped_incomplete: int = 0
    rows: list[dict] = field(default_factory=list)


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


def requested_symbols(symbols: Sequence[str] | None = None) -> list[str]:
    universe = configured_symbols()
    allowed = set(universe)
    raw = universe if symbols is None else _ordered_symbols(symbols)
    return [symbol for symbol in raw if symbol in allowed]


def _parse_intervals(intervals: Sequence[str] | None = None) -> list[str]:
    raw = list(INTERVAL_WINDOWS) if intervals is None else list(intervals)
    out: list[str] = []
    for interval in raw:
        clean = str(interval).strip()
        if clean not in INTERVAL_WINDOWS:
            raise ValueError(f"unsupported interval: {interval}")
        if clean not in out:
            out.append(clean)
    return out


def ensure_intraday_prices_table(conn: sqlite3.Connection) -> None:
    conn.execute(INTRADAY_PRICES_SCHEMA)


def fetch_chart(symbol: str, interval: str, range_name: str) -> dict:
    return spencer_quote_server._chart(
        symbol,
        interval=interval,
        range_name=range_name,
        max_candles=None,
    )


def _finite_float(value, field_name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite {field_name}: {value}")
    return parsed


def _candle_ts_ist(raw_ts) -> str:
    parsed = datetime.fromisoformat(str(raw_ts))
    if parsed.tzinfo is None:
        raise ValueError(f"candle timestamp missing timezone: {raw_ts}")
    return parsed.astimezone(IST).isoformat()


def _is_final_candle(ts_iso: str, interval: str, fetched_at_iso: str) -> bool:
    """Only completed, boundary-aligned candles may be stored.

    Yahoo's chart payload appends the live in-progress bar stamped at the
    current second (e.g. 09:48:38, O=H=L=C, volume 0) and, during market
    hours, the latest boundary bar is still forming. Storing either would
    freeze a partial value behind the UNIQUE constraint — a quietly wrong
    candle forever. A candle is final only if its timestamp sits on the
    interval grid AND its window has fully elapsed at fetch time.
    """
    parsed = datetime.fromisoformat(str(ts_iso))
    minutes = INTERVAL_MINUTES[interval]
    if parsed.second != 0 or parsed.microsecond != 0 or parsed.minute % minutes != 0:
        return False
    fetched = datetime.fromisoformat(str(fetched_at_iso))
    return parsed + timedelta(minutes=minutes) <= fetched


def _normalize_candle(
    *,
    symbol: str,
    interval: str,
    candle: dict,
    source: str,
    fetched_at: str,
    created_at: str,
) -> tuple[dict | None, bool]:
    if any(candle.get(name) is None for name in ("open", "high", "low", "close")):
        return None, True
    row = {
        "symbol": symbol,
        "interval": interval,
        "ts": _candle_ts_ist(candle.get("time")),
        "open": round(_finite_float(candle.get("open"), "open"), 2),
        "high": round(_finite_float(candle.get("high"), "high"), 2),
        "low": round(_finite_float(candle.get("low"), "low"), 2),
        "close": round(_finite_float(candle.get("close"), "close"), 2),
        "volume": round(_finite_float(candle.get("volume") or 0, "volume"), 2),
        "source": source,
        "fetched_at": fetched_at,
        "created_at": created_at,
    }
    if min(row["open"], row["high"], row["low"], row["close"]) <= 0:
        raise ValueError(f"{symbol} {interval} {row['ts']}: non-positive OHLC")
    return row, False


def _collect_rows(
    *,
    symbols: Sequence[str],
    intervals: Sequence[str],
    chart_func: ChartFunc,
) -> tuple[list[dict], int, int]:
    rows: list[dict] = []
    skipped_null_ohlc = 0
    skipped_incomplete = 0
    fetched_at = datetime.now(IST).isoformat()
    created_at = fetched_at
    for symbol in symbols:
        for interval in intervals:
            range_name = INTERVAL_WINDOWS[interval]
            chart = chart_func(symbol, interval, range_name)
            candles = chart.get("candles") or []
            if not candles:
                raise ValueError(f"{symbol} {interval}: no real candles returned")
            source = str(chart.get("source") or "Yahoo Finance chart")
            valid_for_window = 0
            for candle in candles:
                row, skipped = _normalize_candle(
                    symbol=symbol,
                    interval=interval,
                    candle=candle,
                    source=source,
                    fetched_at=fetched_at,
                    created_at=created_at,
                )
                if skipped:
                    skipped_null_ohlc += 1
                    continue
                if not _is_final_candle(row["ts"], interval, fetched_at):
                    skipped_incomplete += 1
                    continue
                rows.append(row)
                valid_for_window += 1
            if valid_for_window == 0:
                raise ValueError(f"{symbol} {interval}: no valid OHLC candles returned")
    return rows, skipped_null_ohlc, skipped_incomplete


def _insert_rows(db_path: Path, rows: Sequence[dict]) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    inserted = 0
    with sqlite3.connect(str(db_path)) as conn:
        ensure_intraday_prices_table(conn)
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO intraday_prices
                    (symbol, interval, ts, open, high, low, close,
                     volume, source, fetched_at, created_at)
                VALUES
                    (:symbol, :interval, :ts, :open, :high, :low, :close,
                     :volume, :source, :fetched_at, :created_at)
                """,
                row,
            )
            inserted += cursor.rowcount
        conn.commit()
    return inserted


def backfill_intraday_history(
    *,
    db_path: Path | str = DB_PATH,
    symbols: Sequence[str] | None = None,
    intervals: Sequence[str] | None = None,
    chart_func: ChartFunc = fetch_chart,
    log_path: Path = LOG_PATH,
) -> HistoryResult:
    try:
        selected_intervals = _parse_intervals(intervals)
    except ValueError as exc:
        message = f"intraday history failed: {exc}"
        _log(message, log_path)
        return HistoryResult(exit_code=1, message=message)

    selected_symbols = requested_symbols(symbols)
    if not selected_symbols:
        message = "intraday history failed: configured universe is empty"
        _log(message, log_path)
        return HistoryResult(exit_code=1, message=message)

    try:
        rows, skipped_null_ohlc, skipped_incomplete = _collect_rows(
            symbols=selected_symbols,
            intervals=selected_intervals,
            chart_func=chart_func,
        )
    except Exception as exc:
        message = f"intraday history failed: {exc}"
        _log(message, log_path)
        return HistoryResult(exit_code=1, message=message)

    inserted = _insert_rows(Path(db_path), rows)
    message = (
        f"intraday history complete: inserted={inserted}, "
        f"valid_candles={len(rows)}, skipped_null_ohlc={skipped_null_ohlc}, "
        f"skipped_incomplete={skipped_incomplete}"
    )
    _log(message, log_path)
    return HistoryResult(
        exit_code=0,
        message=message,
        inserted=inserted,
        skipped_null_ohlc=skipped_null_ohlc,
        skipped_incomplete=skipped_incomplete,
        rows=rows,
    )


def _expected_per_session(interval: str) -> int:
    return SESSION_MINUTES // INTERVAL_MINUTES[interval]


def _ts_date(ts: str) -> date:
    parsed = datetime.fromisoformat(str(ts))
    if parsed.tzinfo is None:
        raise ValueError(f"stored candle timestamp missing timezone: {ts}")
    return parsed.astimezone(IST).date()


def _market_dates(start: date, end: date) -> list[date]:
    days = []
    cur = start
    while cur <= end:
        dt = datetime.combine(cur, datetime.min.time(), tzinfo=IST)
        if not is_weekend(dt) and not is_nse_holiday(cur):
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _coverage_lines(db_path: Path, symbols: Sequence[str], intervals: Sequence[str]) -> list[str]:
    if not db_path.exists():
        return [f"intraday coverage: no database at {db_path}"]

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT symbol, interval, ts
                FROM intraday_prices
                WHERE symbol IN ({symbols}) AND interval IN ({intervals})
                ORDER BY symbol, interval, ts
                """.format(
                    symbols=",".join("?" for _ in symbols),
                    intervals=",".join("?" for _ in intervals),
                ),
                [*symbols, *intervals],
            ).fetchall()
        except sqlite3.OperationalError:
            return ["intraday coverage: intraday_prices table is absent"]

    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        grouped[(row["symbol"], row["interval"])].append(row["ts"])

    lines = ["intraday coverage report"]
    for symbol in symbols:
        for interval in intervals:
            key = (symbol, interval)
            timestamps = grouped.get(key, [])
            expected = _expected_per_session(interval)
            threshold = math.ceil(expected * 0.70)
            if not timestamps:
                lines.append(
                    f"{symbol} {interval}: candles=0 first=None last=None "
                    f"sessions=0 expected_per_session={expected}"
                )
                lines.append(f"{symbol} {interval}: gaps (<70% expected): no candles")
                continue

            counts: dict[date, int] = defaultdict(int)
            parsed_dates = []
            for ts in timestamps:
                session = _ts_date(ts)
                counts[session] += 1
                parsed_dates.append(session)

            all_sessions = _market_dates(min(parsed_dates), max(parsed_dates))
            gaps = [
                (session, counts.get(session, 0))
                for session in all_sessions
                if counts.get(session, 0) < threshold
            ]
            lines.append(
                f"{symbol} {interval}: candles={len(timestamps)} "
                f"first={timestamps[0]} last={timestamps[-1]} "
                f"sessions={len(counts)} expected_per_session={expected}"
            )
            if gaps:
                gap_text = ", ".join(
                    f"{session.isoformat()} ({count}/{expected})"
                    for session, count in gaps
                )
                lines.append(f"{symbol} {interval}: gaps (<70% expected): {gap_text}")
            else:
                lines.append(f"{symbol} {interval}: gaps (<70% expected): none")
    return lines


def coverage_report(
    *,
    db_path: Path | str = DB_PATH,
    symbols: Sequence[str] | None = None,
    intervals: Sequence[str] | None = None,
) -> str:
    selected_symbols = requested_symbols(symbols)
    selected_intervals = _parse_intervals(intervals)
    if not selected_symbols:
        return "intraday coverage: configured universe is empty"
    return "\n".join(_coverage_lines(Path(db_path), selected_symbols, selected_intervals))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect real RELIANCE intraday candles.")
    parser.add_argument("--db", dest="db_path", type=Path, default=DB_PATH, help="SQLite DB path; defaults to kite_bot.db.")
    parser.add_argument("--report", action="store_true", help="Print intraday coverage without fetching.")
    args = parser.parse_args(argv)

    if args.report:
        print(coverage_report(db_path=args.db_path))
        return 0

    result = backfill_intraday_history(db_path=args.db_path)
    print(result.message)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
