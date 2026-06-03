from pathlib import Path

from workflow.pipeline import (
    load_task,
    run_pipeline,
    safety_check_task_intent,
)


def _task_text(extra_objective: str = "") -> str:
    return f"""# Task: Temporary workflow test

## Objective
Validate the workflow runner. {extra_objective}

## Files Affected
- workflow/pipeline.py

## Acceptance Criteria
- Task parses successfully.
- Dry run does not write logs.

## Safety Rules
- Keep Spencer paper-only.
- Do not enable live trading.

## Test Commands
- python -m py_compile workflow/pipeline.py

## Expected Output
- Dry run passes.
"""


def test_markdown_task_parser_reads_required_fields(tmp_path: Path):
    task_path = tmp_path / "task.md"
    task_path.write_text(_task_text(), encoding="utf-8")

    task = load_task(task_path)

    assert task.objective.startswith("Validate the workflow runner")
    assert task.files_affected == ["workflow/pipeline.py"]
    assert task.test_commands == ["python -m py_compile workflow/pipeline.py"]


def test_pipeline_dry_run_passes_without_logs(tmp_path: Path):
    task_path = tmp_path / "task.md"
    task_path.write_text(_task_text(), encoding="utf-8")

    result = run_pipeline(task_path, dry_run=True)

    assert result.status == "passed"
    assert result.dry_run is True
    assert result.log_json is None
    assert result.tests_run[0]["skipped"] is True


def test_pipeline_blocks_live_trading_intent(tmp_path: Path):
    task_path = tmp_path / "task.md"
    task_path.write_text(_task_text("Enable live trading for broker execution."), encoding="utf-8")

    result = run_pipeline(task_path, dry_run=True)

    assert result.status == "failed"
    assert any("live trading" in failure for failure in result.safety_failures)


def test_pipeline_blocks_agent_policy_violation(tmp_path: Path):
    task_path = tmp_path / "task.md"
    task_path.write_text(_task_text("Ask Antigravity to invent fake P&L and fake trade state."), encoding="utf-8")

    result = run_pipeline(task_path, dry_run=True)

    assert result.status == "failed"
    assert any("agent policy violation" in failure for failure in result.safety_failures)


def test_negated_live_trading_rule_is_not_blocked(tmp_path: Path):
    task_path = tmp_path / "task.md"
    task_path.write_text(_task_text("Do not enable live trading."), encoding="utf-8")
    task = load_task(task_path)

    assert safety_check_task_intent(task) == []
