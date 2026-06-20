from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts import export_brain


class FrozenDateTime(datetime):
    current = datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls.current.astimezone(tz)
        return cls.current


def _wire_temp_export(tmp_path: Path, monkeypatch):
    root = tmp_path / "repo"
    tasks = root / "workflow" / "tasks"
    tasks.mkdir(parents=True)
    source = tasks / "current_task.md"
    source.write_text("# Current Task\n\nBuild the thing.\n", encoding="utf-8")

    scoreboard = root / "workflow" / "scoreboard.json"
    scoreboard.write_text(
        json.dumps(
            {
                "functional": 84,
                "profitability": 4,
                "composite": 48,
                "candidatesTested": 0,
                "candidatesKilled": 0,
                "validatedEdges": 0,
            }
        ),
        encoding="utf-8",
    )

    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    brain = tmp_path / "brain"

    monkeypatch.setattr(export_brain, "ROOT", root)
    monkeypatch.setattr(export_brain, "REFERENCE_FILES", {})
    monkeypatch.setattr(
        export_brain,
        "REFERENCE_GLOBS",
        {"workflow/tasks/*.md": "Reference/Workflow Tasks"},
    )
    monkeypatch.setattr(
        export_brain,
        "_readiness",
        lambda db_path: {
            "integrity": "PASS",
            "have": 70,
            "need": 70,
            "remaining": 0,
            "verdict": "READY",
        },
    )
    monkeypatch.setattr(
        export_brain,
        "_today_counts",
        lambda db_path: {
            "date": "2026-06-20",
            "c15": 0,
            "c1": 0,
            "last": "2026-06-20T15:30:00+05:30",
        },
    )
    monkeypatch.setattr(export_brain, "datetime", FrozenDateTime)

    return db, scoreboard, brain, source


def _export(db: Path, scoreboard: Path, brain: Path):
    return export_brain.export_brain(
        db_path=db,
        scoreboard_path=scoreboard,
        brain_dir=brain,
    )


def _markdown_mtimes(brain: Path) -> dict[str, int]:
    return {
        path.relative_to(brain).as_posix(): path.stat().st_mtime_ns
        for path in sorted(brain.rglob("*.md"))
    }


def test_second_export_without_source_changes_rewrites_zero_notes(tmp_path, monkeypatch):
    db, scoreboard, brain, _source = _wire_temp_export(tmp_path, monkeypatch)

    FrozenDateTime.current = datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc)
    _export(db, scoreboard, brain)
    before = _markdown_mtimes(brain)

    FrozenDateTime.current = datetime(2026, 6, 20, 10, 7, tzinfo=timezone.utc)
    _export(db, scoreboard, brain)
    after = _markdown_mtimes(brain)

    assert after == before


def test_changing_one_source_file_rewrites_only_that_mirror(tmp_path, monkeypatch):
    db, scoreboard, brain, source = _wire_temp_export(tmp_path, monkeypatch)

    FrozenDateTime.current = datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc)
    _export(db, scoreboard, brain)
    before = _markdown_mtimes(brain)

    time.sleep(0.02)
    source.write_text("# Current Task\n\nBuild the changed thing.\n", encoding="utf-8")
    FrozenDateTime.current = datetime(2026, 6, 20, 10, 9, tzinfo=timezone.utc)
    _export(db, scoreboard, brain)
    after = _markdown_mtimes(brain)

    changed = {
        path
        for path, mtime in after.items()
        if before.get(path) != mtime
    }
    assert changed == {"Reference/Workflow Tasks/current_task.md"}
