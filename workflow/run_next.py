"""
Local file-based automation bridge for Spencer.

This script does not control external chat UIs, scrape browsers, use passwords,
place trades, or commit code. It reads `workflow/current_task.md`, runs Spencer's
existing pipeline safety checks and test commands, then writes local bridge state
for the next agent to review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.pipeline import PipelineResult, load_task, repo_display_path, run_pipeline


WORKFLOW_DIR = ROOT / "workflow"
CURRENT_TASK_PATH = WORKFLOW_DIR / "current_task.md"
LATEST_RESULT_PATH = WORKFLOW_DIR / "latest_result.md"
AGENT_STATE_PATH = WORKFLOW_DIR / "agent_state.json"
OUTBOX_DIR = WORKFLOW_DIR / "outbox"
DEPLOYMENT_GATE_PATH = WORKFLOW_DIR / "deployment_gate.json"

BRIDGE_UNSAFE_COMMAND_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bgit\s+add\s+(\.|-A|--all)\b", "bulk git staging could include private files"),
    (r"\bgit\s+add\b.*(?:\.env|secret|token|credential|\.key|\.pem)", "credential staging command"),
    (r"\bgit\s+commit\b", "bridge tasks must not commit credentials or local artifacts"),
    (r"\bgit\s+push\b", "bridge tasks must not push without separate review"),
    (r"\bRemove-Item\b.*(?:journal|kite_bot|backtest_).*", "journal deletion command"),
    (r"\brm\s+(-rf\s+)?(?:.*)?(?:journal|kite_bot|backtest_).*", "journal deletion command"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return out or "task"


def load_deployment_gate(path: Path = DEPLOYMENT_GATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "paperOnly": True,
            "deploymentAllowed": False,
            "deploymentBlocked": True,
            "reason": "workflow/deployment_gate.json is missing",
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "paperOnly": True,
            "deploymentAllowed": False,
            "deploymentBlocked": True,
            "reason": "workflow/deployment_gate.json is invalid",
        }


def bridge_safety_failures(task_path: Path) -> list[str]:
    task = load_task(task_path)
    failures: list[str] = []
    for command in task.test_commands:
        for pattern, label in BRIDGE_UNSAFE_COMMAND_PATTERNS:
            if re.search(pattern, command, flags=re.IGNORECASE):
                failures.append(f"unsafe bridge command blocked ({label}): {command}")
    return sorted(set(failures))


def result_to_dict(result: PipelineResult) -> dict[str, Any]:
    return asdict(result)


def blocked_result(task_path: Path, failures: list[str], *, dry_run: bool) -> dict[str, Any]:
    task = load_task(task_path)
    now = utc_now()
    return {
        "task_id": task.task_id,
        "task_path": repo_display_path(task.path),
        "status": "failed",
        "dry_run": dry_run,
        "started_at": now,
        "finished_at": now,
        "files_affected": task.files_affected,
        "files_changed": [],
        "tests_run": [],
        "safety_failures": failures,
        "failures": failures,
        "reviewer_notes": ["Bridge blocked the task before tests because unsafe local automation was requested."],
        "log_json": None,
        "log_markdown": None,
    }


def summarize_tests(tests: list[dict[str, Any]]) -> tuple[int, int]:
    passed = 0
    failed = 0
    for test in tests:
        if int(test.get("returnCode", test.get("return_code", 1)) or 0) == 0:
            passed += 1
        else:
            failed += 1
    return passed, failed


def owner_for(summary: dict[str, Any]) -> str:
    if summary.get("safety_failures"):
        return "trading_authority"
    if summary.get("status") == "passed":
        return "gpt_reviewer"
    return "codex_builder"


def write_latest_result(
    summary: dict[str, Any],
    *,
    latest_result_path: Path = LATEST_RESULT_PATH,
    outbox_dir: Path = OUTBOX_DIR,
) -> tuple[Path, Path]:
    outbox_dir.mkdir(parents=True, exist_ok=True)
    task_id = str(summary.get("task_id") or "task")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    md_path = outbox_dir / f"{stamp}-{slugify(task_id)}.md"
    json_path = outbox_dir / f"{stamp}-{slugify(task_id)}.json"
    content = render_result_markdown(summary)
    md_path.write_text(content, encoding="utf-8")
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    latest_result_path.write_text(content, encoding="utf-8")
    return md_path, json_path


def render_result_markdown(summary: dict[str, Any]) -> str:
    tests = summary.get("tests_run") or []
    passed, failed = summarize_tests(tests)
    safety = summary.get("safety_failures") or []
    failures = summary.get("failures") or []
    files_changed = summary.get("files_changed") or []
    lines = [
        f"# Latest Result: {summary.get('task_id', 'task')}",
        "",
        f"- Status: {summary.get('status')}",
        f"- Dry run: {summary.get('dry_run')}",
        f"- Task: {summary.get('task_path')}",
        f"- Tests passed: {passed}",
        f"- Tests failed: {failed}",
        f"- Finished: {summary.get('finished_at')}",
        "",
        "## Files Changed",
        *([f"- {item}" for item in files_changed] or ["- None detected"]),
        "",
        "## Tests",
    ]
    if tests:
        for test in tests:
            lines.extend([
                f"- `{test.get('command')}`",
                f"  - return code: {test.get('returnCode', test.get('return_code'))}",
                f"  - skipped: {test.get('skipped')}",
            ])
    else:
        lines.append("- None run")
    lines.extend([
        "",
        "## Safety Failures",
        *([f"- {item}" for item in safety] or ["- None"]),
        "",
        "## Failures",
        *([f"- {item}" for item in failures] or ["- None"]),
        "",
        "## Reviewer Notes",
        *([f"- {item}" for item in (summary.get("reviewer_notes") or [])] or ["- None"]),
    ])
    return "\n".join(lines) + "\n"


def write_agent_state(
    summary: dict[str, Any],
    *,
    result_path: Path,
    result_json_path: Path,
    state_path: Path = AGENT_STATE_PATH,
    deployment_gate_path: Path = DEPLOYMENT_GATE_PATH,
) -> dict[str, Any]:
    gate = load_deployment_gate(deployment_gate_path)
    state = {
        "currentOwner": owner_for(summary),
        "taskStatus": summary.get("status"),
        "currentTaskPath": summary.get("task_path"),
        "lastResultPath": repo_display_path(result_path),
        "lastResultJson": repo_display_path(result_json_path),
        "deploymentGateStatus": {
            "deploymentAllowed": bool(gate.get("deploymentAllowed", False)),
            "deploymentBlocked": bool(gate.get("deploymentBlocked", True)),
            "decision": gate.get("decision"),
            "sourceModule": gate.get("sourceModule"),
            "reason": gate.get("reason"),
        },
        "paperOnlyStatus": {
            "paperOnly": bool(gate.get("paperOnly", True)),
            "liveTradingAllowed": bool(gate.get("liveTradingAllowed", False)),
            "brokerExecutionAllowed": bool(gate.get("brokerExecutionAllowed", False)),
            "aiOrderApprovalAllowed": bool(gate.get("aiOrderApprovalAllowed", False)),
            "fakeDashboardDataAllowed": bool(gate.get("fakeDashboardDataAllowed", False)),
        },
        "updatedAt": utc_now(),
    }
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def run_next(
    *,
    task_path: Path = CURRENT_TASK_PATH,
    latest_result_path: Path = LATEST_RESULT_PATH,
    state_path: Path = AGENT_STATE_PATH,
    outbox_dir: Path = OUTBOX_DIR,
    dry_run: bool = False,
    timeout: int = 300,
) -> tuple[dict[str, Any], dict[str, Any]]:
    task_path = Path(task_path)
    if not task_path.is_absolute():
        task_path = ROOT / task_path
    if not task_path.exists():
        summary = blocked_result(task_path, [f"current task not found: {repo_display_path(task_path)}"], dry_run=dry_run)
    else:
        failures = bridge_safety_failures(task_path)
        if failures:
            summary = blocked_result(task_path, failures, dry_run=dry_run)
        else:
            result = run_pipeline(task_path, dry_run=dry_run, timeout=timeout)
            summary = result_to_dict(result)

    result_path, result_json_path = write_latest_result(summary, latest_result_path=latest_result_path, outbox_dir=outbox_dir)
    state = write_agent_state(summary, result_path=result_path, result_json_path=result_json_path, state_path=state_path)
    return summary, state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Spencer's local file-based automation bridge.")
    parser.add_argument("--task", default=str(CURRENT_TASK_PATH), help="Task file to run. Defaults to workflow/current_task.md.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without running test commands.")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per test command in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary, state = run_next(task_path=Path(args.task), dry_run=args.dry_run, timeout=args.timeout)
    print(f"task: {summary.get('task_id')}")
    print(f"status: {summary.get('status')}")
    print(f"owner: {state.get('currentOwner')}")
    print(f"latest_result: {state.get('lastResultPath')}")
    print(f"deployment_blocked: {state.get('deploymentGateStatus', {}).get('deploymentBlocked')}")
    return 0 if summary.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
