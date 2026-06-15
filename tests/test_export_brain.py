"""Tests for the Obsidian brain exporter (scripts/export_brain.py).

Confirms it builds the cross-linked vault from real journal data, reflects real
verdicts/numbers, writes only inside the brain folder, and never mutates the DB.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from scripts import export_brain


def _seed_db(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, stage TEXT,
                candidate_id TEXT, candidate_version TEXT, params_hash TEXT,
                result_hash TEXT, status TEXT, dataset_start TEXT, dataset_end TEXT,
                data_rows INTEGER, summary_json TEXT, trades_json TEXT,
                equity_json TEXT, candidate_json TEXT
            );
            CREATE TABLE backtest_kills (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT,
                candidate_id TEXT, candidate_version TEXT, params_hash TEXT,
                hypothesis_hash TEXT, reason TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO backtest_runs (created_at, stage, candidate_id, candidate_version,"
            " params_hash, result_hash, status, data_rows, summary_json, trades_json,"
            " equity_json, candidate_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-06-12T09:00:00+05:30", "IN_SAMPLE", "SPNCR-T", "1", "p", "r", "FAIL",
             0, json.dumps({"trades": 14, "net_pnl": -23.45}), "[]", "[]",
             json.dumps({"id": "SPNCR-T", "version": "1", "hypothesis": "test hypothesis text"})),
        )
        conn.execute(
            "INSERT INTO backtest_kills (created_at, candidate_id, candidate_version,"
            " params_hash, hypothesis_hash, reason) VALUES (?,?,?,?,?,?)",
            ("2026-06-12T10:00:00+05:30", "SPNCR-T", "1", "p", "h", "IN_SAMPLE failed"),
        )
        conn.commit()


def test_export_brain_builds_linked_vault_from_real_data(tmp_path):
    db = tmp_path / "brain.db"
    _seed_db(db)
    scoreboard = tmp_path / "scoreboard.json"
    scoreboard.write_text(json.dumps({
        "functional": 84, "profitability": 4, "composite": 48,
        "candidatesTested": 1, "candidatesKilled": 1, "validatedEdges": 0,
    }), encoding="utf-8")
    brain = tmp_path / "brain"

    before = hashlib.sha256(db.read_bytes()).hexdigest()
    result = export_brain.export_brain(db_path=db, scoreboard_path=scoreboard, brain_dir=brain)

    # Core notes exist
    for note in ("Spencer.md", "Scoreboard.md", "Research Ledger.md",
                 "Data & Readiness.md", "Live Engine.md", "Doctrine.md", "SPNCR-T.md"):
        assert (brain / note).exists(), f"missing {note}"

    # Real scoreboard number rendered, and wikilinks present (graph works)
    sb = (brain / "Scoreboard.md").read_text(encoding="utf-8")
    assert "84" in sb and "[[Research Ledger]]" in sb

    # Candidate note reflects the real verdict + journaled numbers
    cand = (brain / "SPNCR-T.md").read_text(encoding="utf-8")
    assert "KILLED" in cand
    assert "test hypothesis text" in cand
    assert "14" in cand and "-23.45" in cand

    # The ledger links to the candidate note
    assert "[[SPNCR-T]]" in (brain / "Research Ledger.md").read_text(encoding="utf-8")

    # Read-only over the DB
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before

    # Writes ONLY inside the brain folder
    assert result["candidates"] == 1
    assert all((brain / n).resolve().is_relative_to(brain.resolve())
               for n in result["notes"])


def test_export_brain_handles_empty_journal(tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()  # no tables
    brain = tmp_path / "brain"
    export_brain.export_brain(db_path=db, scoreboard_path=tmp_path / "none.json",
                              brain_dir=brain)
    # Still produces the home + ledger, honestly noting no candidates
    assert (brain / "Spencer.md").exists()
    assert "none yet" in (brain / "Research Ledger.md").read_text(encoding="utf-8")
