from __future__ import annotations

import json
from pathlib import Path

import pytest

from bot.obsidian_brain import ObsidianBrain


def test_search_context_graph_and_status(tmp_path: Path):
    brain = ObsidianBrain(tmp_path / "brain")
    brain.ensure_layout()
    (brain.root / "Doctrine.md").write_text(
        """---
tags: [spencer, doctrine]
managed: true
source_path: SPENCER_CONCEPT.md
---
# Doctrine

Spencer is paper-only and studies [[RELIANCE]].
""",
        encoding="utf-8",
    )
    (brain.root / "RELIANCE.md").write_text(
        "# RELIANCE\n\nThe one stock under study. Back to [[Doctrine]].\n",
        encoding="utf-8",
    )

    results = brain.search("paper only")
    assert results[0]["title"] == "Doctrine"
    assert results[0]["wikilink"] == "[[Doctrine]]"

    context = brain.context("What is Spencer allowed to do?")
    assert "Source: [[Doctrine]]" in context["context"]
    assert context["citations"][0]["path"] == "Doctrine.md"

    status = brain.status()
    assert status["primary"] is True
    assert status["generatedCount"] == 1
    assert status["paperOnly"] is True

    graph = brain.graph()
    assert {"source": "Doctrine", "target": "RELIANCE"} in graph["edges"]
    assert {"source": "RELIANCE", "target": "Doctrine"} in graph["edges"]


def test_capture_is_safe_persistent_and_indexed(tmp_path: Path):
    brain = ObsidianBrain(tmp_path / "brain")
    result = brain.capture(
        title="Keep paper-only boundary",
        content="The operator confirmed that broker execution remains disabled.",
        kind="decision",
        tags=["governance"],
        source="test",
        confidence="verified",
    )

    note = brain.root / result["created"]
    assert note.exists()
    text = note.read_text(encoding="utf-8")
    assert "managed: false" in text
    assert "broker execution remains disabled" in text
    assert (brain.root / ".spencer-brain-index.json").exists()
    decisions_index = (brain.root / "Memory" / "Decisions.md").read_text(encoding="utf-8")
    assert result["wikilink"] in decisions_index

    payload = json.loads((brain.root / ".spencer-brain-index.json").read_text(encoding="utf-8"))
    assert any(row["path"] == result["created"] for row in payload["notes"])


def test_capture_rejects_traversal_kind_and_oversized_content(tmp_path: Path):
    brain = ObsidianBrain(tmp_path / "brain")
    with pytest.raises(ValueError):
        brain.capture(title="Unsafe", content="body", kind="../../outside")
    with pytest.raises(ValueError):
        brain.capture(title="Large", content="x" * 40_001)


def test_manual_seed_notes_are_never_overwritten(tmp_path: Path):
    brain = ObsidianBrain(tmp_path / "brain")
    brain.ensure_layout()
    memory_home = brain.root / "Memory" / "Memory Home.md"
    memory_home.write_text("# Custom memory home\n", encoding="utf-8")

    brain.ensure_layout()

    assert memory_home.read_text(encoding="utf-8") == "# Custom memory home\n"
