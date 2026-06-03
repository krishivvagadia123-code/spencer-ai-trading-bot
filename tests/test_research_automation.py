"""Tests for Spencer's automatic paper-only research workflow."""

from __future__ import annotations

import json
from pathlib import Path

from workflow import research_automation as RA


def _wire_temp_workflow(tmp_path: Path, monkeypatch):
    workflow = tmp_path / "workflow"
    monkeypatch.setattr(RA, "WORKFLOW_DIR", workflow)
    monkeypatch.setattr(RA, "TASKS_DIR", workflow / "tasks")
    monkeypatch.setattr(RA, "LOGS_DIR", workflow / "logs")
    monkeypatch.setattr(RA, "STATUS_DIR", workflow / "tasks" / ".status")
    monkeypatch.setattr(RA, "DEPLOYMENT_GATE_PATH", workflow / "deployment_gate.json")
    return workflow


def _event_eval_gap_up_candidate() -> dict:
    return {
        "symbols_used": 50,
        "horizon_days": 5,
        "cost": 0.0025,
        "results": {
            "gap_up": {
                "events": 120,
                "win_rate": 0.55,
                "avg_fwd": 0.012,
                "cost_adj": 0.0095,
                "oos_avg": 0.008,
                "walk_forward": "survives",
            },
            "gap_down": {"events": 95, "cost_adj": -0.004, "walk_forward": "fails"},
        },
        "not_testable": {
            "sector_news_impact": "NOT TESTABLE - no historical sector-news feed.",
        },
        "verdict": (
            "1 of 2 tested event types show a cost-adjusted edge that survives "
            "walk-forward: ['gap_up']. CAVEAT: testing multiple buckets and finding "
            "1 survivor is weak evidence. This is a CANDIDATE to confirm with more "
            "history and a holdout check - NOT to be deployed."
        ),
    }


def test_event_eval_gap_up_caveat_creates_confirmation_task(tmp_path, monkeypatch):
    workflow = _wire_temp_workflow(tmp_path, monkeypatch)
    old_task = workflow / "tasks" / "event_eval_task.md"
    old_task.parent.mkdir(parents=True)
    old_task.write_text("# Task: event eval\n", encoding="utf-8")

    outcome = RA.finalize_research("event_eval", _event_eval_gap_up_candidate(), old_task_path=old_task)

    assert outcome["decision"] == RA.NEEDS_CONFIRMATION
    assert outcome["deploymentBlocked"] is True
    task_path = workflow / "tasks" / "confirm_gap_up_edge.md"
    assert task_path.exists()
    text = task_path.read_text(encoding="utf-8")
    assert "bot/gapup_confirm.py" in text
    assert "Do not enable live trading" in text
    assert "Deployment remains blocked unless validation passes" in text

    status = json.loads((workflow / "tasks" / ".status" / "event_eval_task.status.json").read_text(encoding="utf-8"))
    assert status["status"] == "passed"
    assert status["researchDecision"] == RA.NEEDS_CONFIRMATION

    gate = json.loads((workflow / "deployment_gate.json").read_text(encoding="utf-8"))
    assert gate["deploymentAllowed"] is False
    assert gate["liveTradingAllowed"] is False
    assert gate["brokerExecutionAllowed"] is False


def test_failed_research_blocks_deployment_and_creates_rejection_task(tmp_path, monkeypatch):
    workflow = _wire_temp_workflow(tmp_path, monkeypatch)
    result = {
        "results": {"gap_up": {"events": 80, "cost_adj": -0.01, "walk_forward": "fails"}},
        "verdict": "NO event type shows a cost-adjusted edge that survives walk-forward. No edge.",
    }

    outcome = RA.finalize_research("event_eval", result)

    assert outcome["decision"] == RA.FAIL
    assert outcome["deploymentBlocked"] is True
    assert (workflow / "tasks" / "record_event_eval_rejection.md").exists()
    assert RA.check_deployment_gate() == 1


def test_confirmed_gapup_passes_gate_and_creates_paper_spec_task(tmp_path, monkeypatch):
    workflow = _wire_temp_workflow(tmp_path, monkeypatch)
    result = {
        "confirmed": True,
        "verdict": "CONFIRMED: gap_up survives validation with no caveat.",
        "nifty50": {"passes": True},
        "midcap100": {"oos_net": 0.01},
    }

    outcome = RA.finalize_research("gapup_confirm", result)

    assert outcome["decision"] == RA.PASS
    assert outcome["deploymentBlocked"] is False
    assert (workflow / "tasks" / "paper_gap_up_strategy_spec.md").exists()
    gate = json.loads((workflow / "deployment_gate.json").read_text(encoding="utf-8"))
    assert gate["deploymentAllowed"] is True
    assert gate["paperOnly"] is True
    assert gate["brokerExecutionAllowed"] is False
    assert RA.check_deployment_gate() == 0
