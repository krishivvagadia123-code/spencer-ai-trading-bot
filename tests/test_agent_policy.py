from pathlib import Path

from workflow.agent_policy import (
    agent_handoff_plan_for,
    load_agent_policy,
    safety_check_agent_policy,
)
from workflow.pipeline import load_task


def _task_text(objective: str, safety: str = "- Keep Spencer paper-only.") -> str:
    return f"""# Task: Agent policy test

## Objective
{objective}

## Files Affected
- workflow/agents/agent_policy.json

## Acceptance Criteria
- The automatic agent handoff is present.
- Trading remains paper-only.

## Safety Rules
{safety}

## Test Commands
- python -m py_compile workflow/agent_policy.py

## Expected Output
- Safety checks pass.
"""


def test_agent_policy_has_required_automatic_roles():
    policy = load_agent_policy()

    stages = [(step["stage"], step["agent"]) for step in policy["automaticFlow"]]

    assert ("PLAN", "claude_manager") in stages
    assert ("BUILD", "codex_builder") in stages
    assert ("REVIEW", "gpt_reviewer") in stages
    assert ("APPROVE", "trading_authority") in stages
    assert policy["display"]["agent"] == "antigravity_designer"
    assert policy["paperOnly"] is True


def test_agent_handoff_plan_is_generated_from_task(tmp_path: Path):
    task_path = tmp_path / "task.md"
    task_path.write_text(_task_text("Claude orchestrates research and Codex edits workflow files."), encoding="utf-8")
    task = load_task(task_path)

    handoff = agent_handoff_plan_for(task)

    assert [step["stage"] for step in handoff[:6]] == ["PLAN", "BUILD", "TEST", "REVIEW", "APPROVE", "LOG"]
    assert handoff[-1]["agent"] == "antigravity_designer"
    assert all(step["taskId"] == task.task_id for step in handoff)


def test_agent_policy_blocks_role_boundary_violations(tmp_path: Path):
    task_path = tmp_path / "task.md"
    task_path.write_text(_task_text("Ask Antigravity to invent fake P&L and fake trade state."), encoding="utf-8")
    task = load_task(task_path)

    failures = safety_check_agent_policy(task)

    assert any("Antigravity fake display state" in failure for failure in failures)


def test_agent_policy_allows_negated_safety_rules(tmp_path: Path):
    task_path = tmp_path / "task.md"
    task_path.write_text(
        _task_text(
            "Make the workflow automatic.",
            "- No agent can enable live trading.\n- No agent can bypass risk gates.\n- No fake P&L.",
        ),
        encoding="utf-8",
    )
    task = load_task(task_path)

    assert safety_check_agent_policy(task) == []
