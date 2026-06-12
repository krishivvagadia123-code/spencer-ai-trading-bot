import json
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

from bot.intraday_backtest import ensure_backtest_tables
import spencer_quote_server
from spencer_quote_server import _research_ledger


def _seed_research_tables(db_path):
    with sqlite3.connect(db_path) as conn:
        ensure_backtest_tables(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS intraday_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                ts TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL,
                source TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(symbol, interval, ts)
            );
            CREATE TABLE IF NOT EXISTS daily_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL NOT NULL,
                source TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(symbol, trade_date)
            );
            """
        )
        summary = {
            "trades": 4,
            "gross_pnl": 12.5,
            "total_costs": 19.75,
            "net_pnl": -7.25,
            "net_edge_per_trade_pct_of_notional": -0.0185,
            "cost_bar_required_pct": 0.61,
        }
        candidate = {
            "id": "SPNCR-001",
            "version": 1,
            "hypothesis": "Opening range confirmation should capture larger RELIANCE expansion days.",
        }
        conn.execute(
            """
            INSERT INTO backtest_runs (
                created_at, stage, candidate_id, candidate_version, params_hash,
                result_hash, status, dataset_start, dataset_end, data_rows,
                summary_json, trades_json, equity_json, candidate_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-12T09:00:00+05:30",
                "IN_SAMPLE",
                "SPNCR-001",
                "1",
                "params-a",
                "result-a",
                "FAIL",
                "2026-03-17T09:15:00+05:30",
                "2026-05-15T15:15:00+05:30",
                956,
                json.dumps(summary),
                "[]",
                "[]",
                json.dumps(candidate),
            ),
        )
        conn.execute(
            """
            INSERT INTO backtest_kills (
                created_at, candidate_id, candidate_version, params_hash,
                hypothesis_hash, reason
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-12T11:20:53+05:30",
                "SPNCR-001",
                "1",
                "params-a",
                "hypothesis-a",
                "IN_SAMPLE failed",
            ),
        )
        conn.executemany(
            """
            INSERT INTO intraday_prices (
                symbol, interval, ts, open, high, low, close, volume, source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("RELIANCE", "15m", "2026-06-10T09:15:00+05:30", 1, 1, 1, 1, 10, "test", "now"),
                ("RELIANCE", "15m", "2026-06-11T09:15:00+05:30", 1, 1, 1, 1, 10, "test", "now"),
                ("RELIANCE", "1m", "2026-06-11T09:15:00+05:30", 1, 1, 1, 1, 10, "test", "now"),
            ],
        )
        conn.execute(
            """
            INSERT INTO daily_prices (symbol, trade_date, close, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("RELIANCE", "2026-06-11", 1490.25, "test", "now"),
        )


def test_research_ledger_reports_exact_journaled_kill_and_coverage(tmp_path):
    db_path = tmp_path / "ledger.db"
    scoreboard_path = tmp_path / "scoreboard.json"
    scoreboard_path.write_text(
        json.dumps({
            "functional": 80,
            "profitability": 4,
            "composite": 48,
            "candidatesTested": 2,
            "candidatesKilled": 2,
            "validatedEdges": 0,
        }),
        encoding="utf-8",
    )
    _seed_research_tables(db_path)

    payload = _research_ledger(db_path=db_path, scoreboard_path=scoreboard_path)

    assert payload["ok"] is True
    assert payload["scoreboard"]["functional"] == 80
    assert payload["scoreboard"]["profitability"] == 4
    assert payload["scoreboard"]["composite"] == 48
    assert payload["scoreboard"]["updatedAt"]

    assert len(payload["candidates"]) == 1
    candidate = payload["candidates"][0]
    assert candidate["candidateId"] == "SPNCR-001"
    assert candidate["version"] == "1"
    assert candidate["hypothesis"] == "Opening range confirmation should capture larger RELIANCE expansion days."
    assert candidate["status"] == "KILLED"
    assert candidate["kill"]["reason"] == "IN_SAMPLE failed"
    assert candidate["kill"]["date"] == "2026-06-12T11:20:53+05:30"

    stage = candidate["stages"][0]
    assert stage["stage"] == "IN_SAMPLE"
    assert stage["status"] == "FAIL"
    assert stage["trades"] == 4
    assert stage["gross_pnl"] == 12.5
    assert stage["total_costs"] == 19.75
    assert stage["net_pnl"] == -7.25
    assert stage["net_edge_pct"] == -0.0185
    assert stage["cost_bar_required_pct"] == 0.61
    assert stage["dataset"]["start"] == "2026-03-17T09:15:00+05:30"
    assert stage["dataset"]["end"] == "2026-05-15T15:15:00+05:30"
    assert stage["dataset"]["rows"] == 956

    intraday = {row["interval"]: row for row in payload["dataCoverage"]["intraday"]}
    assert intraday["15m"]["firstTs"] == "2026-06-10T09:15:00+05:30"
    assert intraday["15m"]["lastTs"] == "2026-06-11T09:15:00+05:30"
    assert intraday["15m"]["sessions"] == 2
    assert intraday["1m"]["sessions"] == 1
    assert payload["dataCoverage"]["daily"]["lastTradeDate"] == "2026-06-11"


def test_research_ledger_empty_db_returns_empty_lists_and_json_scoreboard(tmp_path):
    db_path = tmp_path / "empty.db"
    scoreboard_path = tmp_path / "scoreboard.json"
    scoreboard_path.write_text(json.dumps({"functional": 80}), encoding="utf-8")
    sqlite3.connect(db_path).close()

    payload = _research_ledger(db_path=db_path, scoreboard_path=scoreboard_path)

    assert payload["ok"] is True
    assert payload["candidates"] == []
    assert payload["dataCoverage"]["intraday"] == []
    assert payload["dataCoverage"]["daily"]["lastTradeDate"] is None
    assert payload["scoreboard"]["functional"] == 80
    assert payload["scoreboard"]["updatedAt"]


def test_research_ledger_get_endpoint_reads_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "ledger.db"
    scoreboard_path = tmp_path / "scoreboard.json"
    scoreboard_path.write_text(json.dumps({"functional": 80}), encoding="utf-8")
    _seed_research_tables(db_path)
    monkeypatch.setattr(spencer_quote_server, "DB_PATH", db_path)
    monkeypatch.setattr(spencer_quote_server, "WORKFLOW_SCOREBOARD_PATH", scoreboard_path)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), spencer_quote_server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/api/research/ledger", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    assert payload["ok"] is True
    assert payload["candidates"][0]["candidateId"] == "SPNCR-001"
    assert payload["candidates"][0]["status"] == "KILLED"
    assert payload["candidates"][0]["stages"][0]["net_pnl"] == -7.25
    assert payload["scoreboard"]["functional"] == 80
