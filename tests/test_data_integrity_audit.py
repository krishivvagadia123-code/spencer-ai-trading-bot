from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime, time, timedelta

import pytest

from bot.holidays import DEFAULT_REGISTRY
from bot.market_data import IST
from scripts import audit_data_integrity as audit


DAILY_SCHEMA = """
CREATE TABLE daily_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    close REAL NOT NULL,
    prev_close REAL,
    change_pct REAL,
    quote_timestamp TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    source TEXT NOT NULL,
    market_state TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

INTRADAY_SCHEMA = """
CREATE TABLE intraday_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    ts TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

REFERENCE_TIME = datetime(2026, 6, 12, 18, 0, tzinfo=IST)


def _create_db(tmp_path):
    db_path = tmp_path / "audit.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(DAILY_SCHEMA + INTRADAY_SCHEMA)
    return db_path


def _insert_daily(
    db_path,
    *,
    trade_date="2026-06-11",
    quote_timestamp="2026-06-11T10:00:00+00:00",
    symbol="RELIANCE",
):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO daily_prices
                (symbol, trade_date, close, prev_close, change_pct,
                 quote_timestamp, fetched_at, source, market_state, created_at)
            VALUES (?, ?, 2500, 2490, 0.4, ?, ?, 'test', 'CLOSED', ?)
            """,
            (
                symbol,
                trade_date,
                quote_timestamp,
                quote_timestamp,
                quote_timestamp,
            ),
        )


def _insert_candle(
    db_path,
    *,
    ts,
    interval="15m",
    symbol="RELIANCE",
):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO intraday_prices
                (symbol, interval, ts, open, high, low, close, volume,
                 source, fetched_at, created_at)
            VALUES (?, ?, ?, 2499, 2502, 2498, 2500, 1000, 'test', ?, ?)
            """,
            (
                symbol,
                interval,
                ts,
                "2026-06-12T18:00:00+05:30",
                "2026-06-12T18:00:00+05:30",
            ),
        )


def _insert_complete_session(db_path, session=date(2026, 6, 11)):
    start = datetime.combine(session, time(9, 15), tzinfo=IST)
    for interval, count, minutes in (("15m", 25, 15), ("1m", 375, 1)):
        for index in range(count):
            _insert_candle(
                db_path,
                interval=interval,
                ts=(start + timedelta(minutes=index * minutes)).isoformat(),
            )


def _check(report, check_id):
    return next(item for item in report["checks"] if item["id"] == check_id)


def _trading_days(start, count):
    days = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def test_clean_dataset_passes_exit_zero_and_audit_is_read_only(tmp_path, capsys):
    db_path = _create_db(tmp_path)
    _insert_daily(db_path)
    _insert_complete_session(db_path)
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    report = audit.audit_database(db_path, reference_time=REFERENCE_TIME)
    exit_code = audit.main(["--db", str(db_path)])
    capsys.readouterr()

    after = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert exit_code == 0
    assert report["summary"]["status"] == "PASS"
    assert report["summary"]["failed_checks"] == 0
    assert all(check["status"] == "PASS" for check in report["checks"])
    assert before == after


@pytest.mark.parametrize(
    ("table", "check_id"),
    (
        ("daily", "daily_duplicates"),
        ("intraday", "intraday_duplicates"),
    ),
)
def test_duplicate_failure_classes_are_detected(
    tmp_path,
    capsys,
    table,
    check_id,
):
    db_path = _create_db(tmp_path)
    if table == "daily":
        _insert_daily(db_path)
        _insert_daily(db_path)
    else:
        _insert_candle(db_path, ts="2026-06-11T09:15:00+05:30")
        _insert_candle(db_path, ts="2026-06-11T09:15:00+05:30")

    report = audit.audit_database(db_path, reference_time=REFERENCE_TIME)
    exit_code = audit.main(["--db", str(db_path)])
    capsys.readouterr()

    check = _check(report, check_id)
    assert exit_code == 1
    assert report["summary"]["status"] == "FAIL"
    assert check["status"] == "FAIL"
    assert len(check["offending_rows"]) == 2


def test_off_grid_candle_is_detected(tmp_path):
    db_path = _create_db(tmp_path)
    _insert_candle(db_path, ts="2026-06-11T09:17:30+05:30")

    report = audit.audit_database(db_path, reference_time=REFERENCE_TIME)

    check = _check(report, "intraday_finality")
    assert check["status"] == "FAIL"
    assert check["offending_rows"][0]["ts"] == "2026-06-11T09:17:30+05:30"


@pytest.mark.parametrize("table", ("daily", "intraday"))
def test_weekend_rows_are_detected(tmp_path, table):
    db_path = _create_db(tmp_path)
    if table == "daily":
        _insert_daily(
            db_path,
            trade_date="2026-06-13",
            quote_timestamp="2026-06-13T10:00:00+00:00",
        )
    else:
        _insert_candle(db_path, ts="2026-06-13T09:15:00+05:30")

    report = audit.audit_database(db_path, reference_time=REFERENCE_TIME)

    check = _check(report, "fabricated_sessions")
    assert check["status"] == "FAIL"
    assert len(check["offending_rows"]) == 1


def test_registered_nse_holiday_row_is_detected(tmp_path):
    db_path = _create_db(tmp_path)
    holiday = date(2026, 6, 11)
    DEFAULT_REGISTRY.add(holiday)
    try:
        _insert_daily(db_path)
        report = audit.audit_database(db_path, reference_time=REFERENCE_TIME)
    finally:
        DEFAULT_REGISTRY.remove(holiday)

    assert _check(report, "fabricated_sessions")["status"] == "FAIL"


def test_pre_close_eod_row_is_detected(tmp_path):
    db_path = _create_db(tmp_path)
    _insert_daily(
        db_path,
        quote_timestamp="2026-06-11T09:59:00+00:00",  # 15:29 IST
    )

    report = audit.audit_database(db_path, reference_time=REFERENCE_TIME)

    check = _check(report, "eod_finality")
    assert check["status"] == "FAIL"
    assert "before 15:30" in check["offending_rows"][0]["audit_reason"]


def test_intraday_utc_session_date_drift_is_detected(tmp_path):
    db_path = _create_db(tmp_path)
    _insert_candle(db_path, ts="2026-06-11T20:00:00+00:00")

    report = audit.audit_database(db_path, reference_time=REFERENCE_TIME)

    check = _check(report, "intraday_session_date")
    assert check["status"] == "FAIL"
    assert "becomes 2026-06-12 in IST" in check["offending_rows"][0]["audit_reason"]


def test_future_dated_daily_row_is_detected(tmp_path):
    db_path = _create_db(tmp_path)
    _insert_daily(
        db_path,
        trade_date="2026-06-15",
        quote_timestamp="2026-06-15T10:00:00+00:00",
    )

    report = audit.audit_database(db_path, reference_time=REFERENCE_TIME)

    check = _check(report, "daily_freshness")
    assert check["status"] == "FAIL"
    assert check["details"]["most_recent_completed_trading_day"] == "2026-06-12"


def test_gap_warning_does_not_flip_exit_code(tmp_path, capsys):
    db_path = _create_db(tmp_path)
    _insert_daily(db_path)
    _insert_candle(db_path, ts="2026-06-11T09:15:00+05:30")

    exit_code = audit.main(["--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[WARN] Intraday coverage gaps" in output
    assert "OVERALL: PASS" in output


@pytest.mark.parametrize(
    ("session_count", "expected_status", "expected_remaining"),
    (
        (audit.SPNCR3_MIN_15M_SESSIONS - 1, "NOT-READY", 1),
        (audit.SPNCR3_MIN_15M_SESSIONS, "READY", 0),
    ),
)
def test_readiness_flips_at_documented_threshold(
    tmp_path,
    session_count,
    expected_status,
    expected_remaining,
):
    db_path = _create_db(tmp_path)
    for session in _trading_days(date(2026, 1, 2), session_count):
        _insert_candle(
            db_path,
            ts=datetime.combine(session, time(9, 15), tzinfo=IST).isoformat(),
        )

    report = audit.audit_database(
        db_path,
        reference_time=datetime(2026, 6, 30, 18, 0, tzinfo=IST),
    )
    readiness = report["research_readiness"]

    assert report["summary"]["status"] == "PASS"
    assert readiness["status"] == expected_status
    assert readiness["sessions_remaining"] == expected_remaining
    assert readiness["minimum_15m_sessions"] == audit.SPNCR3_MIN_15M_SESSIONS


def test_json_flag_emits_full_report(tmp_path, capsys):
    db_path = _create_db(tmp_path)
    _insert_daily(db_path)
    _insert_complete_session(db_path)

    exit_code = audit.main(["--db", str(db_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["read_only"] is True
    assert payload["summary"]["status"] == "PASS"
    assert payload["research_readiness"]["minimum_15m_sessions"] == 70
