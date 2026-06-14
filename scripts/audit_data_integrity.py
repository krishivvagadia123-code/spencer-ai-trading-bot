"""Read-only integrity audit for Spencer's daily and intraday market data.

The collectors own the storage conventions. This script only verifies those
conventions and reports offending rows; it never repairs or mutates data.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import spencer_quote_server
from bot.holidays import is_nse_holiday
from bot.market_data import IST, is_weekend, now_ist

DB_PATH = spencer_quote_server.DB_PATH
SPNCR3_MIN_15M_SESSIONS = 70
INTERVAL_MINUTES = {"15m": 15, "1m": 1}
SESSION_MINUTES = 375
GAP_THRESHOLD = 0.70
NSE_CLOSE = dtime(15, 30)


def _read_only_connection(db_path: Path) -> sqlite3.Connection:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _check(
    check_id: str,
    name: str,
    status: str,
    description: str,
    offending_rows: list[dict[str, Any]] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "name": name,
        "status": status,
        "description": description,
        "offending_rows": offending_rows or [],
        "details": details or {},
    }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _parse_date(raw: Any) -> date:
    return date.fromisoformat(str(raw))


def _parse_timestamp(raw: Any) -> datetime:
    parsed = datetime.fromisoformat(str(raw))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed


def _stored_calendar_date(raw_timestamp: Any) -> date:
    timestamp = str(raw_timestamp)
    return date.fromisoformat(timestamp[:10])


def _is_non_trading_day(session: date) -> bool:
    session_start = datetime.combine(session, dtime.min, tzinfo=IST)
    return is_weekend(session_start) or is_nse_holiday(session)


def _market_dates(start: date, end: date) -> list[date]:
    sessions: list[date] = []
    current = start
    while current <= end:
        if not _is_non_trading_day(current):
            sessions.append(current)
        current += timedelta(days=1)
    return sessions


def _most_recent_completed_trading_day(reference: datetime) -> date:
    current = reference.astimezone(IST)
    candidate = current.date()
    if current.time() < NSE_CLOSE or _is_non_trading_day(candidate):
        candidate -= timedelta(days=1)
    while _is_non_trading_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def _duplicate_rows(
    conn: sqlite3.Connection,
    table: str,
    key_columns: Sequence[str],
) -> list[dict[str, Any]]:
    keys = ", ".join(key_columns)
    duplicate_keys = conn.execute(
        f"""
        SELECT {keys}
        FROM {table}
        GROUP BY {keys}
        HAVING COUNT(*) > 1
        ORDER BY {keys}
        """
    ).fetchall()
    offending: list[dict[str, Any]] = []
    where = " AND ".join(f"{column}=?" for column in key_columns)
    for key in duplicate_keys:
        values = [key[column] for column in key_columns]
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE {where} ORDER BY id",
            values,
        ).fetchall()
        offending.extend(_row_dict(row) for row in rows)
    return offending


def _duplicate_checks(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    checks = []
    for table, columns, check_id, label in (
        (
            "daily_prices",
            ("symbol", "trade_date"),
            "daily_duplicates",
            "Daily price uniqueness",
        ),
        (
            "intraday_prices",
            ("symbol", "interval", "ts"),
            "intraday_duplicates",
            "Intraday candle uniqueness",
        ),
    ):
        offending = _duplicate_rows(conn, table, columns)
        checks.append(
            _check(
                check_id,
                label,
                "FAIL" if offending else "PASS",
                f"No duplicate ({', '.join(columns)}) rows.",
                offending,
                {"duplicate_rows": len(offending)},
            )
        )
    return checks


def _intraday_grid_check(conn: sqlite3.Connection) -> dict[str, Any]:
    offending = []
    for row in conn.execute("SELECT * FROM intraday_prices ORDER BY id"):
        item = _row_dict(row)
        try:
            interval_minutes = INTERVAL_MINUTES[item["interval"]]
            parsed = _parse_timestamp(item["ts"])
            aligned = (
                parsed.minute % interval_minutes == 0
                and parsed.second == 0
                and parsed.microsecond == 0
            )
            if not aligned:
                item["audit_reason"] = "timestamp is not aligned to its interval grid"
                offending.append(item)
        except (KeyError, TypeError, ValueError) as exc:
            item["audit_reason"] = str(exc)
            offending.append(item)
    return _check(
        "intraday_finality",
        "Intraday candle boundary/finality",
        "FAIL" if offending else "PASS",
        "Every stored candle is boundary-aligned and therefore eligible to be final.",
        offending,
        {"off_grid_rows": len(offending)},
    )


def _fabricated_session_check(conn: sqlite3.Connection) -> dict[str, Any]:
    offending = []
    for row in conn.execute("SELECT * FROM daily_prices ORDER BY id"):
        item = _row_dict(row)
        try:
            session = _parse_date(item["trade_date"])
            if _is_non_trading_day(session):
                item["audit_reason"] = "daily row falls on an NSE weekend/holiday"
                offending.append(item)
        except (TypeError, ValueError) as exc:
            item["audit_reason"] = f"invalid trade_date: {exc}"
            offending.append(item)

    for row in conn.execute("SELECT * FROM intraday_prices ORDER BY id"):
        item = _row_dict(row)
        try:
            session = _parse_timestamp(item["ts"]).astimezone(IST).date()
            if _is_non_trading_day(session):
                item["audit_reason"] = "intraday row falls on an NSE weekend/holiday"
                offending.append(item)
        except (TypeError, ValueError) as exc:
            item["audit_reason"] = f"invalid intraday timestamp: {exc}"
            offending.append(item)

    return _check(
        "fabricated_sessions",
        "NSE session validity",
        "FAIL" if offending else "PASS",
        "No daily or intraday rows occur on NSE weekends or registered holidays.",
        offending,
        {"non_trading_day_rows": len(offending)},
    )


def _eod_finality_check(conn: sqlite3.Connection) -> dict[str, Any]:
    offending = []
    for row in conn.execute("SELECT * FROM daily_prices ORDER BY id"):
        item = _row_dict(row)
        try:
            trade_date = _parse_date(item["trade_date"])
            quote_time = _parse_timestamp(item["quote_timestamp"]).astimezone(IST)
            if quote_time.date() != trade_date:
                item["audit_reason"] = (
                    f"quote IST date {quote_time.date().isoformat()} does not match "
                    f"trade_date {trade_date.isoformat()}"
                )
                offending.append(item)
            elif quote_time.time() < NSE_CLOSE:
                item["audit_reason"] = (
                    f"quote time {quote_time.time().isoformat(timespec='seconds')} "
                    "IST is before 15:30"
                )
                offending.append(item)
        except (TypeError, ValueError) as exc:
            item["audit_reason"] = str(exc)
            offending.append(item)
    return _check(
        "eod_finality",
        "EOD quote finality",
        "FAIL" if offending else "PASS",
        "Every daily close is timestamped at or after 15:30 IST in its session.",
        offending,
        {"non_final_eod_rows": len(offending)},
    )


def _session_date_consistency_check(conn: sqlite3.Connection) -> dict[str, Any]:
    offending = []
    for row in conn.execute("SELECT * FROM intraday_prices ORDER BY id"):
        item = _row_dict(row)
        try:
            stored_date = _stored_calendar_date(item["ts"])
            ist_date = _parse_timestamp(item["ts"]).astimezone(IST).date()
            if stored_date != ist_date:
                item["audit_reason"] = (
                    f"stored calendar date {stored_date.isoformat()} becomes "
                    f"{ist_date.isoformat()} in IST"
                )
                offending.append(item)
        except (TypeError, ValueError) as exc:
            item["audit_reason"] = str(exc)
            offending.append(item)
    return _check(
        "intraday_session_date",
        "Intraday session-date consistency",
        "FAIL" if offending else "PASS",
        "Each stored timestamp's calendar date agrees with its IST session date.",
        offending,
        {"drift_rows": len(offending)},
    )


def _gap_check(conn: sqlite3.Connection) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[date, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    invalid_rows = []
    for row in conn.execute(
        "SELECT id, symbol, interval, ts FROM intraday_prices ORDER BY id"
    ):
        try:
            session = _parse_timestamp(row["ts"]).astimezone(IST).date()
            grouped[(row["symbol"], row["interval"])][session] += 1
        except (TypeError, ValueError) as exc:
            item = _row_dict(row)
            item["audit_reason"] = str(exc)
            invalid_rows.append(item)

    gaps: list[dict[str, Any]] = []
    for (symbol, interval), counts in sorted(grouped.items()):
        interval_minutes = INTERVAL_MINUTES.get(interval)
        if interval_minutes is None or not counts:
            continue
        expected = SESSION_MINUTES // interval_minutes
        minimum = math.ceil(expected * GAP_THRESHOLD)
        for session in _market_dates(min(counts), max(counts)):
            actual = counts.get(session, 0)
            if actual < minimum:
                gaps.append(
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "session": session.isoformat(),
                        "actual_candles": actual,
                        "expected_candles": expected,
                        "minimum_70_percent": minimum,
                    }
                )

    gaps.extend(invalid_rows)
    return _check(
        "intraday_gaps",
        "Intraday coverage gaps",
        "WARN" if gaps else "PASS",
        "Sessions below 70% of expected candles are reported without smoothing.",
        gaps,
        {"gap_sessions": len(gaps), "threshold_percent": 70},
    )


def _future_daily_check(
    conn: sqlite3.Connection,
    reference: datetime,
) -> dict[str, Any]:
    completed_day = _most_recent_completed_trading_day(reference)
    offending = []
    for row in conn.execute("SELECT * FROM daily_prices ORDER BY id"):
        item = _row_dict(row)
        try:
            trade_date = _parse_date(item["trade_date"])
            if trade_date > completed_day:
                item["audit_reason"] = (
                    f"trade_date is after the most recent completed NSE session "
                    f"{completed_day.isoformat()}"
                )
                offending.append(item)
        except (TypeError, ValueError) as exc:
            item["audit_reason"] = str(exc)
            offending.append(item)
    return _check(
        "daily_freshness",
        "Daily-date freshness",
        "FAIL" if offending else "PASS",
        "Daily rows never extend beyond the most recent completed NSE session.",
        offending,
        {"most_recent_completed_trading_day": completed_day.isoformat()},
    )


def _readiness(conn: sqlite3.Connection) -> dict[str, Any]:
    sessions: dict[str, set[date]] = {"15m": set(), "1m": set()}
    for row in conn.execute(
        "SELECT interval, ts FROM intraday_prices WHERE interval IN ('15m', '1m')"
    ):
        try:
            sessions[row["interval"]].add(
                _parse_timestamp(row["ts"]).astimezone(IST).date()
            )
        except (TypeError, ValueError):
            continue

    sessions_15m = len(sessions["15m"])
    sessions_1m = len(sessions["1m"])
    ready = sessions_15m >= SPNCR3_MIN_15M_SESSIONS
    return {
        "status": "READY" if ready else "NOT-READY",
        "distinct_15m_sessions": sessions_15m,
        "distinct_1m_sessions": sessions_1m,
        "minimum_15m_sessions": SPNCR3_MIN_15M_SESSIONS,
        "sessions_remaining": max(0, SPNCR3_MIN_15M_SESSIONS - sessions_15m),
        "note": (
            "Readiness is a data-depth signal only; it does not validate an edge "
            "or unblock deployment."
        ),
    }


def audit_database(
    db_path: Path | str = DB_PATH,
    *,
    reference_time: datetime | None = None,
) -> dict[str, Any]:
    db_file = Path(db_path)
    generated_at = (reference_time or now_ist()).astimezone(IST)
    checks: list[dict[str, Any]] = []

    with _read_only_connection(db_file) as conn:
        missing_tables = [
            table
            for table in ("daily_prices", "intraday_prices")
            if not _table_exists(conn, table)
        ]
        if missing_tables:
            checks.append(
                _check(
                    "required_tables",
                    "Required market-data tables",
                    "FAIL",
                    "The auditor requires both collector-owned market-data tables.",
                    [{"missing_table": table} for table in missing_tables],
                )
            )
            readiness = {
                "status": "NOT-READY",
                "distinct_15m_sessions": 0,
                "distinct_1m_sessions": 0,
                "minimum_15m_sessions": SPNCR3_MIN_15M_SESSIONS,
                "sessions_remaining": SPNCR3_MIN_15M_SESSIONS,
                "note": "Readiness cannot be established while required tables are absent.",
            }
        else:
            checks.extend(_duplicate_checks(conn))
            checks.extend(
                [
                    _intraday_grid_check(conn),
                    _fabricated_session_check(conn),
                    _eod_finality_check(conn),
                    _session_date_consistency_check(conn),
                    _gap_check(conn),
                    _future_daily_check(conn, generated_at),
                ]
            )
            readiness = _readiness(conn)

    failures = sum(check["status"] == "FAIL" for check in checks)
    warnings = sum(check["status"] == "WARN" for check in checks)
    return {
        "database": str(db_file.resolve()),
        "generated_at": generated_at.isoformat(),
        "read_only": True,
        "summary": {
            "status": "FAIL" if failures else "PASS",
            "failed_checks": failures,
            "warning_checks": warnings,
        },
        "checks": checks,
        "research_readiness": readiness,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "DATA INTEGRITY AUDIT",
        f"Database: {report['database']}",
        f"Generated: {report['generated_at']}",
        "Mode: READ-ONLY",
        "",
    ]
    for check in report["checks"]:
        lines.append(f"[{check['status']}] {check['name']}")
        lines.append(f"  {check['description']}")
        for row in check["offending_rows"]:
            lines.append(f"  OFFENDING: {json.dumps(row, sort_keys=True, default=str)}")
        if check["details"]:
            lines.append(
                f"  DETAILS: {json.dumps(check['details'], sort_keys=True, default=str)}"
            )
        lines.append("")

    readiness = report["research_readiness"]
    lines.extend(
        [
            "RESEARCH READINESS",
            f"  15m distinct sessions: {readiness['distinct_15m_sessions']}",
            f"  1m distinct sessions: {readiness['distinct_1m_sessions']}",
            f"  SPNCR3_MIN_15M_SESSIONS: {readiness['minimum_15m_sessions']}",
            f"  Verdict: {readiness['status']}",
            f"  Sessions remaining: {readiness['sessions_remaining']}",
            f"  Note: {readiness['note']}",
            "",
            f"OVERALL: {report['summary']['status']}",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of Spencer daily and intraday market data."
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        type=Path,
        default=DB_PATH,
        help="SQLite database path; defaults to kite_bot.db.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the complete machine-readable report as JSON.",
    )
    args = parser.parse_args(argv)

    try:
        report = audit_database(args.db_path)
    except (OSError, sqlite3.Error) as exc:
        report = {
            "database": str(args.db_path.resolve()),
            "generated_at": now_ist().isoformat(),
            "read_only": True,
            "summary": {
                "status": "FAIL",
                "failed_checks": 1,
                "warning_checks": 0,
            },
            "checks": [
                _check(
                    "database_access",
                    "Database access",
                    "FAIL",
                    "The database could not be opened read-only.",
                    [{"error": str(exc)}],
                )
            ],
            "research_readiness": {
                "status": "NOT-READY",
                "distinct_15m_sessions": 0,
                "distinct_1m_sessions": 0,
                "minimum_15m_sessions": SPNCR3_MIN_15M_SESSIONS,
                "sessions_remaining": SPNCR3_MIN_15M_SESSIONS,
                "note": "Readiness cannot be established without database access.",
            },
        }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(render_text(report))
    return 1 if report["summary"]["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
