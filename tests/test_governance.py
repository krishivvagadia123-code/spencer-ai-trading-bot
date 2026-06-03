from pathlib import Path

import pytest

from bot.control import get_control_path, pause, set_control_path
from bot.governance import build_action_capabilities, build_governance_snapshot


@pytest.fixture
def isolated_control(tmp_path: Path):
    previous = get_control_path()
    set_control_path(tmp_path / "control_state.json")
    try:
        yield
    finally:
        set_control_path(previous)


def test_ai_tools_are_not_trade_authorities(isolated_control):
    snapshot = build_governance_snapshot({"running": False})

    assert snapshot["mode"] == "paper-only"
    assert snapshot["capabilities"]["actions"]["placeLiveOrder"]["allowed"] is False
    assert snapshot["capabilities"]["actions"]["manualPaperOrder"]["allowed"] is False
    assert "place orders" in snapshot["roles"]["gpt"]["mustNeverDo"]
    assert "approve or place trades" in snapshot["roles"]["codex"]["mustNeverDo"]


def test_start_paper_bot_blocks_when_control_is_paused(isolated_control):
    pause("operator review")

    capabilities = build_action_capabilities({"running": False})
    start = capabilities["actions"]["startPaperBot"]

    assert start["allowed"] is False
    assert any("paused" in reason for reason in start["reasons"])


def test_running_status_allows_stop_but_not_duplicate_start(isolated_control):
    capabilities = build_action_capabilities({"running": True})

    assert capabilities["actions"]["startPaperBot"]["allowed"] is False
    assert capabilities["actions"]["stopPaperBot"]["allowed"] is True
