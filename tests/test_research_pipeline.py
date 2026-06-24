from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import pytest

from bot.intraday_backtest import record_kill
from bot.market_data import IST
from bot.research_candidates import load_candidate
from scripts import research_pipeline


def _ts(day: int, hh: int, mm: int) -> str:
    return datetime(2026, 6, day, hh, mm, tzinfo=IST).isoformat()


def _candidate_dict() -> dict:
    return {
        "id": "PIPE-001",
        "version": "v1",
        "hypothesis": "Synthetic pipeline candidate, not a real technique.",
        "symbol": "RELIANCE",
        "interval": "15m",
        "entry_rule": {"left": {"field": "close"}, "op": ">", "right": {"value": 100}},
        "exit_rule": {"left": {"field": "close"}, "op": "<", "right": {"value": 0}},
        "stop_rule": {"type": "fixed_pct", "pct": 0.25},
        "sizing_rule": {"type": "fixed_qty", "qty": 1},
        "no_trade_conditions": [],
        "execution_assumption": {"entry_fill": "next_candle_open", "exit_fill": "next_candle_open"},
        "parameters": {"threshold": 100},
        "capital": 5000.0,
        "max_open_positions": 1,
        "side": "LONG",
    }


def _write_candidate_and_splits(tmp_path):
    candidate_path = tmp_path / "PIPE-001.json"
    splits_path = tmp_path / "PIPE-001.splits.json"
    candidate_path.write_text(json.dumps(_candidate_dict()), encoding="utf-8")
    splits_path.write_text(
        json.dumps(
            {
                "in_sample": {"start": "2026-06-11", "end": "2026-06-11"},
                "out_of_sample": {"start": "2026-06-11", "end": "2026-06-11"},
                "walk_forward": [{"start": "2026-06-11", "end": "2026-06-11"}],
            }
        ),
        encoding="utf-8",
    )
    return candidate_path, splits_path


def _make_intraday_db(path):
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
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
                created_at TEXT NOT NULL,
                UNIQUE(symbol, interval, ts)
            )
            """
        )
        rows = [
            (_ts(11, 9, 15), 100, 103, 99, 101),
            (_ts(11, 9, 30), 110, 113, 109, 112),
            (_ts(11, 9, 45), 125, 128, 124, 127),
        ]
        for ts, open_, high, low, close in rows:
            conn.execute(
                """
                INSERT INTO intraday_prices
                    (symbol, interval, ts, open, high, low, close,
                     volume, source, fetched_at, created_at)
                VALUES ('RELIANCE', '15m', ?, ?, ?, ?, ?, 1000, 'test', ?, ?)
                """,
                (ts, open_, high, low, close, ts, ts),
            )


def test_research_pipeline_runs_ladder_persists_ledger_and_appends_jsonl(tmp_path):
    db_path = tmp_path / "pipeline.db"
    results_path = tmp_path / "workflow" / "pipeline_results.jsonl"
    candidate_path, splits_path = _write_candidate_and_splits(tmp_path)
    _make_intraday_db(db_path)

    result = research_pipeline.run_pipeline(
        candidate_path,
        splits_path=splits_path,
        db_path=db_path,
        results_path=results_path,
    )

    assert result["verdict"] == "PASS"
    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM backtest_kills").fetchone()[0] == 0
    lines = results_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["candidate_id"] == "PIPE-001"
    assert payload["verdict"] == "PASS"


def test_research_pipeline_refuses_exact_killed_params(tmp_path):
    db_path = tmp_path / "pipeline.db"
    results_path = tmp_path / "workflow" / "pipeline_results.jsonl"
    candidate_path, splits_path = _write_candidate_and_splits(tmp_path)
    candidate = load_candidate(candidate_path)
    record_kill(db_path, candidate, "IN_SAMPLE failed")

    with pytest.raises(ValueError, match="refusing to re-test killed candidate"):
        research_pipeline.run_pipeline(
            candidate_path,
            splits_path=splits_path,
            db_path=db_path,
            results_path=results_path,
        )

    assert not results_path.exists()
