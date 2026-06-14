from __future__ import annotations

import hashlib
import json
import sqlite3

from scripts import spencer_status


def _create_status_db(path):
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
            CREATE TABLE backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                stage TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                candidate_version TEXT NOT NULL,
                params_hash TEXT NOT NULL,
                result_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                dataset_start TEXT,
                dataset_end TEXT,
                data_rows INTEGER NOT NULL,
                summary_json TEXT NOT NULL,
                trades_json TEXT NOT NULL,
                equity_json TEXT NOT NULL,
                candidate_json TEXT NOT NULL
            );
            CREATE TABLE backtest_kills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                candidate_version TEXT NOT NULL,
                params_hash TEXT NOT NULL,
                hypothesis_hash TEXT NOT NULL,
                reason TEXT NOT NULL
            );
            INSERT INTO intraday_prices (
                symbol, interval, ts, open, high, low, close, volume,
                source, fetched_at, created_at
            )
            VALUES (
                'RELIANCE', '15m', '2026-06-11T09:15:00+05:30',
                1490, 1492, 1489, 1491, 1000, 'test',
                '2026-06-11T16:00:00+05:30',
                '2026-06-11T16:00:00+05:30'
            );
            INSERT INTO backtest_runs (
                created_at, stage, candidate_id, candidate_version, params_hash,
                result_hash, status, dataset_start, dataset_end, data_rows,
                summary_json, trades_json, equity_json, candidate_json
            )
            VALUES (
                '2026-06-12T09:00:00+05:30', 'IN_SAMPLE', 'SPNCR-TEST', '1',
                'params', 'result', 'FAIL', NULL, NULL, 1,
                '{}', '[]', '[]', '{"id":"SPNCR-TEST","version":1}'
            );
            INSERT INTO backtest_kills (
                created_at, candidate_id, candidate_version, params_hash,
                hypothesis_hash, reason
            )
            VALUES (
                '2026-06-12T10:00:00+05:30', 'SPNCR-TEST', '1',
                'params', 'hypothesis', 'IN_SAMPLE failed'
            );
            """
        )


def test_status_report_contains_every_section_and_json_parses(
    tmp_path,
    monkeypatch,
    capsys,
):
    db_path = tmp_path / "status.db"
    scoreboard_path = tmp_path / "scoreboard.json"
    gate_path = tmp_path / "deployment_gate.json"
    _create_status_db(db_path)
    scoreboard_path.write_text(
        json.dumps(
            {
                "functional": 83,
                "profitability": 4,
                "composite": 48,
                "candidatesTested": 2,
                "candidatesKilled": 2,
                "validatedEdges": 0,
            }
        ),
        encoding="utf-8-sig",
    )
    gate_path.write_text(
        json.dumps(
            {
                "decision": "FAIL",
                "paperOnly": True,
                "deploymentBlocked": True,
                "liveTradingAllowed": False,
            }
        ),
        encoding="utf-8",
    )
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    monkeypatch.setattr(spencer_status, "DB_PATH", db_path)
    monkeypatch.setattr(spencer_status, "SCOREBOARD_PATH", scoreboard_path)
    monkeypatch.setattr(spencer_status, "DEPLOYMENT_GATE_PATH", gate_path)

    exit_code = spencer_status.main(["--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert set(payload) == {
        "asof",
        "readOnly",
        "scoreboard",
        "safetyGate",
        "dataHealth",
        "readiness",
        "researchLedger",
        "git",
    }
    assert payload["scoreboard"]["functional"] == 83
    assert payload["safetyGate"]["deploymentBlocked"] is True
    assert payload["dataHealth"]["overall"] == "PASS"
    assert payload["readiness"]["fifteenMinSessions"] == 1
    assert payload["readiness"]["sessionsRemaining"] == 69
    assert payload["researchLedger"] == [
        {
            "candidateId": "SPNCR-TEST",
            "version": "1",
            "verdict": "KILLED",
        }
    ]
    assert set(payload["git"]) == {"commit", "branch"}
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before
