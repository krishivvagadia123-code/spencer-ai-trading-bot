from __future__ import annotations

import sqlite3

from scripts import audit_data_integrity as audit
from scripts.append_daily_audit import append_audit_log


def _create_empty_market_db(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
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
        )


def test_daily_audit_result_is_appended_to_log(tmp_path):
    db_path = tmp_path / "market.db"
    log_path = tmp_path / "daily_audit.log"
    _create_empty_market_db(db_path)

    report = audit.audit_database(db_path)
    line = append_audit_log(report, log_path, audit_exit_code=0)

    assert log_path.read_text(encoding="utf-8") == f"{line}\n"
    assert "OVERALL PASS" in line
    assert "FAIL checks: none" in line
    assert "gap-WARN count: 0" in line
    assert "SPNCR-003 readiness: 0/70 sessions | NOT-READY" in line


def test_daily_audit_failure_is_marked_alert(tmp_path):
    report = {
        "generated_at": "2026-06-14T18:00:00+05:30",
        "summary": {"status": "FAIL"},
        "checks": [
            {
                "id": "daily_duplicates",
                "name": "Daily price uniqueness",
                "status": "FAIL",
            }
        ],
        "research_readiness": {
            "distinct_15m_sessions": 58,
            "minimum_15m_sessions": 70,
            "status": "NOT-READY",
        },
    }

    line = append_audit_log(
        report,
        tmp_path / "daily_audit.log",
        audit_exit_code=1,
    )

    assert "ALERT | OVERALL FAIL" in line
    assert "FAIL checks: Daily price uniqueness" in line
