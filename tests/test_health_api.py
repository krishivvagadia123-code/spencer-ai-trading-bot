from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

import spencer_quote_server


def _create_market_db(path, *, with_rows):
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
        if not with_rows:
            return
        conn.execute(
            """
            INSERT INTO daily_prices (
                symbol, trade_date, close, prev_close, change_pct,
                quote_timestamp, fetched_at, source, market_state, created_at
            )
            VALUES (
                'RELIANCE', '2026-06-11', 1490.25, 1480.00, 0.69,
                '2026-06-11T10:00:00+00:00',
                '2026-06-11T16:00:00+05:30',
                'test', 'CLOSED', '2026-06-11T16:00:00+05:30'
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO intraday_prices (
                symbol, interval, ts, open, high, low, close, volume,
                source, fetched_at, created_at
            )
            VALUES (
                'RELIANCE', ?, ?, 1490, 1492, 1489, 1491, 1000,
                'test', '2026-06-11T16:00:00+05:30',
                '2026-06-11T16:00:00+05:30'
            )
            """,
            [
                ("15m", "2026-06-10T09:15:00+05:30"),
                ("15m", "2026-06-11T09:15:00+05:30"),
                ("1m", "2026-06-11T09:15:00+05:30"),
            ],
        )


def _get_health(db_path, log_path, monkeypatch):
    monkeypatch.setattr(spencer_quote_server, "DB_PATH", db_path)
    monkeypatch.setattr(
        spencer_quote_server,
        "WORKFLOW_DAILY_AUDIT_LOG_PATH",
        log_path,
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), spencer_quote_server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_health_endpoint_reports_real_integrity_and_readiness(tmp_path, monkeypatch):
    db_path = tmp_path / "market.db"
    log_path = tmp_path / "daily_audit.log"
    _create_market_db(db_path, with_rows=True)
    log_path.write_text(
        "2026-06-13T18:00:00+05:30 | OVERALL PASS | older\n"
        "2026-06-14T18:00:00+05:30 | OVERALL PASS | latest\n",
        encoding="utf-8",
    )
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    payload = _get_health(db_path, log_path, monkeypatch)

    assert payload["ok"] is True
    assert payload["integrity"]["overall"] == "PASS"
    assert payload["integrity"]["checks"]
    assert all(
        set(check) == {"id", "name", "status"}
        for check in payload["integrity"]["checks"]
    )
    assert payload["readiness"] == {
        "fifteenMinSessions": 2,
        "oneMinSessions": 1,
        "required": 70,
        "verdict": "NOT-READY",
        "sessionsRemaining": 68,
    }
    assert payload["lastDailyAudit"] == {
        "timestamp": "2026-06-14T18:00:00+05:30",
        "overall": "PASS",
    }
    assert payload["asof"]
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before


def test_health_endpoint_reports_honest_empty_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "empty.db"
    _create_market_db(db_path, with_rows=False)

    payload = _get_health(
        db_path,
        tmp_path / "missing_daily_audit.log",
        monkeypatch,
    )

    assert payload["integrity"]["overall"] == "PASS"
    assert payload["readiness"] == {
        "fifteenMinSessions": 0,
        "oneMinSessions": 0,
        "required": 70,
        "verdict": "NOT-READY",
        "sessionsRemaining": 70,
    }
    assert payload["lastDailyAudit"] is None
