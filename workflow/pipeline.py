"""
Spencer repo-native workflow runner.

Usage:
  python workflow/pipeline.py --task workflow/tasks/current_task.md

The runner is intentionally local and deterministic. It does not call external
AI services, place trades, or mutate trading state. Tasks move through:
PLAN -> BUILD -> TEST -> REVIEW -> APPROVE -> LOG.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.agent_policy import agent_handoff_plan_for, safety_check_agent_policy

WORKFLOW_DIR = ROOT / "workflow"
TASKS_DIR = WORKFLOW_DIR / "tasks"
LOGS_DIR = WORKFLOW_DIR / "logs"
STATUS_DIR = TASKS_DIR / ".status"

REQUIRED_FIELDS = (
    "objective",
    "files affected",
    "acceptance criteria",
    "safety rules",
    "test commands",
    "expected output",
)

CODE_AND_CONFIG_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".yml", ".yaml",
    ".env", ".ini", ".bat", ".ps1", ".sh", ".css", ".html",
}

IGNORED_SCAN_PARTS = {
    ".git", ".pytest_cache", ".venv", "__pycache__", "node_modules", "dist",
    "dist-verify-bot-safety", "logs",
}

JOURNAL_NAMES = {
    "kite_bot.db",
    "backtest_journal.db",
    "backtest_baseline.db",
    "backtest_filtered.db",
    "walkforward_range072.db",
}

UNSAFE_CODE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\blive_enabled\s*[:=]\s*true\b", "live trading enablement"),
    (r"\bhas_live_credentials\s*[:=]\s*true\b", "live credential gate enablement"),
    (r"\bALLOW_LIVE_TRADING\s*=\s*true\b", "live trading environment enablement"),
    (r"\bENABLE_BROKER_EXECUTION\s*=\s*true\b", "broker execution enablement"),
    (r"\bplace_order\s*\(", "broker order placement"),
    (r"\bcreate_order\s*\(", "exchange order placement"),
    (r"\bsubmit_order\s*\(", "broker order submission"),
    (r"\bbroker\.(buy|sell|place|submit|create)_?order\b", "broker order placement"),
    (r"\bexchange\.create_order\b", "exchange order placement"),
    (r"\bMath\.random\s*\(\s*\).*pnl\b", "fake P&L generation"),
    (r"\brandom\.(uniform|random|randint)\s*\(.*pnl", "fake P&L generation"),
    (r"\bfake(Pnl|PNL|Profit|Trade|Order|Dashboard|BotStatus)\b", "fake dashboard data"),
    (r"\bAI_APPROVES_ORDERS\s*=\s*true\b", "AI approval of orders"),
    (r"\baiApproval\s*[:=]\s*true\b", "AI approval of orders"),
    (r"\brisk_gate_bypass\s*[:=]\s*true\b", "risk gate bypass"),
    (r"\bBYPASS_RISK_GATE\s*=\s*true\b", "risk gate bypass"),
)

UNSAFE_INTENT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bdelete\s+(the\s+)?(paper\s+|backtest\s+)?journal", "journal deletion intent"),
    (r"\bwipe\s+(the\s+)?(paper\s+|backtest\s+)?journal", "journal deletion intent"),
    (r"\breset\s+(the\s+)?journal\b", "journal reset intent"),
    (r"\benable\s+live\s+trading\b", "live trading intent"),
    (r"\bplace\s+live\s+(broker\s+)?order", "live order intent"),
    (r"\bapprove\s+orders?\s+with\s+ai\b", "AI order approval intent"),
    (r"\bbypass\s+risk\s+gates?\b", "risk gate bypass intent"),
)

UNSAFE_TEST_COMMAND_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\brm\s+(-rf\s+)?(?:.*\s)?(?:kite_bot|backtest_).*\.db\b", "journal deletion command"),
    (r"\bdel\s+(?:.*\s)?(?:kite_bot|backtest_).*\.db\b", "journal deletion command"),
    (r"\bRemove-Item\b.*(?:kite_bot|backtest_).*\.db\b", "journal deletion command"),
    (r"\bgit\s+reset\s+--hard\b", "destructive git reset"),
    (r"\bgit\s+clean\s+-", "destructive git clean"),
)

NEGATION_PREFIXES = (
    "do not ",
    "don't ",
    "never ",
    "must not ",
    "no ",
    "block ",
    "blocks ",
    "blocked ",
    "prevent ",
    "prevents ",
)


@dataclass
class Task:
    path: Path
    task_id: str
    format: str
    fields: dict[str, Any]
    raw: str

    @property
    def objective(self) -> str:
        return as_text(self.fields.get("objective"))

    @property
    def files_affected(self) -> list[str]:
        return as_list(self.fields.get("files affected"))

    @property
    def acceptance_criteria(self) -> list[str]:
        return as_list(self.fields.get("acceptance criteria"))

    @property
    def safety_rules(self) -> list[str]:
        return as_list(self.fields.get("safety rules"))

    @property
    def test_commands(self) -> list[str]:
        return as_list(self.fields.get("test commands"))

    @property
    def expected_output(self) -> str:
        return as_text(self.fields.get("expected output"))


@dataclass
class CommandResult:
    command: str
    return_code: int
    stdout: str = ""
    stderr: str = ""
    skipped: bool = False
    reason: str | None = None


@dataclass
class PipelineResult:
    task_id: str
    task_path: str
    status: str
    dry_run: bool
    started_at: str
    finished_at: str | None = None
    stage_results: list[dict[str, Any]] = field(default_factory=list)
    agent_handoff: list[dict[str, Any]] = field(default_factory=list)
    files_affected: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    safety_failures: list[str] = field(default_factory=list)
    tests_run: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    reviewer_notes: list[str] = field(default_factory=list)
    implementation_steps: list[str] = field(default_factory=list)
    log_json: str | None = None
    log_markdown: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return out or "task"


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    out: list[str] = []
    for line in text.splitlines():
        cleaned = re.sub(r"^\s*[-*]\s+", "", line).strip()
        if cleaned:
            out.append(cleaned)
    return out or [text]


def read_status(task_path: Path) -> dict[str, Any] | None:
    status_path = status_path_for(task_path)
    if not status_path.exists():
        return None
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def status_path_for(task_path: Path) -> Path:
    return STATUS_DIR / f"{task_path.stem}.status.json"


def discover_pending_tasks() -> list[Path]:
    if not TASKS_DIR.exists():
        return []
    tasks: list[Path] = []
    for path in sorted(TASKS_DIR.glob("*")):
        if path.name.startswith(".") or path.is_dir():
            continue
        if path.suffix.lower() not in {".md", ".json"}:
            continue
        status = read_status(path)
        if status and status.get("status") == "passed":
            continue
        tasks.append(path)
    return tasks


def parse_markdown_task(path: Path, raw: str) -> Task:
    fields: dict[str, list[str]] = {}
    current: str | None = None
    title = path.stem

    for raw_line in raw.splitlines():
        line = raw_line.rstrip()
        heading = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
        if heading:
            label = heading.group(2).strip()
            normalized = normalize_field_name(label)
            if heading.group(1) == "#" and title == path.stem:
                title = label.replace("Task:", "").strip() or path.stem
            if normalized in REQUIRED_FIELDS:
                current = normalized
                fields.setdefault(current, [])
            else:
                current = None
            continue
        if current is not None:
            fields.setdefault(current, []).append(line)

    compacted = {key: clean_section(lines) for key, lines in fields.items()}
    return Task(
        path=path,
        task_id=slugify(title or path.stem),
        format="markdown",
        fields=compacted,
        raw=raw,
    )


def parse_json_task(path: Path, raw: str) -> Task:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON task root must be an object")
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        normalized[normalize_field_name(key)] = value
    task_id = slugify(str(data.get("id") or data.get("title") or data.get("objective") or path.stem))
    return Task(path=path, task_id=task_id, format="json", fields=normalized, raw=raw)


def normalize_field_name(value: str) -> str:
    value = value.strip().lower().replace("_", " ")
    value = re.sub(r"[^a-z0-9 ]+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    aliases = {
        "files": "files affected",
        "affected files": "files affected",
        "criteria": "acceptance criteria",
        "tests": "test commands",
        "commands": "test commands",
        "expected": "expected output",
    }
    return aliases.get(value, value)


def clean_section(lines: list[str]) -> str:
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def load_task(path: Path) -> Task:
    path = resolve_repo_path(path)
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return parse_json_task(path, raw)
    return parse_markdown_task(path, raw)


def resolve_repo_path(path: str | Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def validate_task(task: Task) -> list[str]:
    failures: list[str] = []
    for field_name in REQUIRED_FIELDS:
        value = task.fields.get(field_name)
        if not as_text(value):
            failures.append(f"missing required field: {field_name}")
    if not task.files_affected:
        failures.append("files affected must list at least one path")
    if not task.acceptance_criteria:
        failures.append("acceptance criteria must list at least one criterion")
    if not task.safety_rules:
        failures.append("safety rules must list at least one rule")
    if not task.test_commands:
        failures.append("test commands must list at least one command")
    return failures


def implementation_steps_for(task: Task) -> list[str]:
    files = ", ".join(task.files_affected[:5])
    if len(task.files_affected) > 5:
        files += f", and {len(task.files_affected) - 5} more"
    return [
        f"PLAN/Claude: confirm objective and acceptance criteria for {task.task_id}.",
        f"BUILD/Codex: limit changes to declared files where possible: {files}.",
        "TEST/Codex: run each command listed in the task file.",
        "REVIEW/GPT: compare tests, safety gates, and strategy logic against acceptance criteria.",
        "APPROVE/Trading Authority: mark passed only when backend safety and tests both pass.",
        "DISPLAY/Antigravity: show only verified backend workflow state.",
        "LOG/Pipeline: write JSON, Markdown, and task status outputs under workflow/.",
    ]


def should_scan_file(path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    if any(part in IGNORED_SCAN_PARTS for part in relative.parts):
        return False
    if path.name in JOURNAL_NAMES:
        return False
    if path.suffix.lower() not in CODE_AND_CONFIG_SUFFIXES:
        return False
    return path.exists() and path.is_file()


def iter_scan_targets(task: Task) -> list[Path]:
    targets: list[Path] = []
    for item in task.files_affected:
        cleaned = item.strip().strip("`")
        if not cleaned:
            continue
        path = resolve_repo_path(cleaned)
        if path.is_dir():
            for child in path.rglob("*"):
                if should_scan_file(child):
                    targets.append(child)
        elif should_scan_file(path):
            targets.append(path)

    unique: dict[str, Path] = {}
    for path in targets:
        unique[str(path.resolve())] = path
    return list(unique.values())


def has_negation_prefix(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - 24):match_start]
    return any(window.endswith(prefix) for prefix in NEGATION_PREFIXES)


def safety_check_task_intent(task: Task) -> list[str]:
    failures: list[str] = []
    text = "\n".join([
        task.objective,
        "\n".join(task.acceptance_criteria),
        task.expected_output,
    ]).lower()
    for pattern, label in UNSAFE_INTENT_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            if not has_negation_prefix(text, match.start()):
                failures.append(f"unsafe task intent: {label}")
    return failures


def safety_check_commands(commands: list[str]) -> list[str]:
    failures: list[str] = []
    for command in commands:
        for pattern, label in UNSAFE_TEST_COMMAND_PATTERNS:
            if re.search(pattern, command, flags=re.IGNORECASE):
                failures.append(f"unsafe test command blocked ({label}): {command}")
    return failures


def safety_check_files(task: Task) -> list[str]:
    failures: list[str] = []
    for path in iter_scan_targets(task):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            failures.append(f"could not scan {path}: {exc}")
            continue
        for pattern, label in UNSAFE_CODE_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
                rel = path.resolve().relative_to(ROOT)
                failures.append(f"unsafe code/config pattern in {rel}: {label}")
    return failures


def safety_check_journals() -> list[str]:
    failures: list[str] = []
    for name in ("kite_bot.db",):
        if not (ROOT / name).exists():
            failures.append(f"required paper journal missing: {name}")
    return failures


def run_safety_gates(task: Task) -> list[str]:
    failures = []
    failures.extend(safety_check_agent_policy(task))
    failures.extend(safety_check_task_intent(task))
    failures.extend(safety_check_commands(task.test_commands))
    failures.extend(safety_check_files(task))
    failures.extend(safety_check_journals())
    return sorted(set(failures))


def snapshot_files(task: Task) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for item in task.files_affected:
        path = resolve_repo_path(item.strip().strip("`"))
        if path.exists() and path.is_file():
            snapshot[str(path.resolve())] = path.stat().st_mtime
        elif path.exists() and path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    snapshot[str(child.resolve())] = child.stat().st_mtime
    return snapshot


def changed_files(before: dict[str, float], task: Task) -> list[str]:
    after = snapshot_files(task)
    changed: list[str] = []
    for path, mtime in after.items():
        if path not in before or before[path] != mtime:
            try:
                changed.append(str(Path(path).relative_to(ROOT)))
            except ValueError:
                changed.append(path)
    return sorted(changed)


def repo_display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def run_command(command: str, timeout: int) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        shell=True,
        timeout=timeout,
    )
    return CommandResult(
        command=command,
        return_code=completed.returncode,
        stdout=completed.stdout[-12000:],
        stderr=completed.stderr[-12000:],
    )


def command_to_dict(result: CommandResult) -> dict[str, Any]:
    return {
        "command": result.command,
        "returnCode": result.return_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "skipped": result.skipped,
        "reason": result.reason,
    }


def write_status(task: Task, result: PipelineResult) -> Path:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    path = status_path_for(task.path)
    payload = {
        "taskId": result.task_id,
        "taskPath": result.task_path,
        "status": result.status,
        "dryRun": result.dry_run,
        "updatedAt": result.finished_at,
        "logJson": result.log_json,
        "logMarkdown": result.log_markdown,
        "agentHandoff": result.agent_handoff,
        "failures": result.failures,
        "safetyFailures": result.safety_failures,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_logs(result: PipelineResult) -> tuple[Path, Path]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{slugify(result.task_id)}"
    json_path = LOGS_DIR / f"{base}.json"
    md_path = LOGS_DIR / f"{base}.md"

    json_payload = result.__dict__.copy()
    json_path.write_text(json.dumps(json_payload, indent=2, default=str), encoding="utf-8")

    md = [
        f"# Workflow Result: {result.task_id}",
        "",
        f"- Status: {result.status}",
        f"- Dry run: {result.dry_run}",
        f"- Started: {result.started_at}",
        f"- Finished: {result.finished_at}",
        f"- Task: {result.task_path}",
        "",
        "## Files Affected",
        *[f"- {item}" for item in result.files_affected],
        "",
        "## Files Changed",
        *([f"- {item}" for item in result.files_changed] or ["- None detected by workflow runner"]),
        "",
        "## Implementation Steps",
        *[f"- {item}" for item in result.implementation_steps],
        "",
        "## Agent Handoff",
        *[
            f"- {step.get('stage')}: {step.get('agent')} - {step.get('role')}"
            for step in result.agent_handoff
        ],
        "",
        "## Safety Failures",
        *([f"- {item}" for item in result.safety_failures] or ["- None"]),
        "",
        "## Tests Run",
    ]
    if result.tests_run:
        for test in result.tests_run:
            md.extend([
                f"- `{test['command']}`",
                f"  - return code: {test['returnCode']}",
                f"  - skipped: {test['skipped']}",
            ])
    else:
        md.append("- None")
    md.extend([
        "",
        "## Failures",
        *([f"- {item}" for item in result.failures] or ["- None"]),
        "",
        "## Reviewer Notes",
        *([f"- {item}" for item in result.reviewer_notes] or ["- None"]),
        "",
    ])
    md_path.write_text("\n".join(md), encoding="utf-8")
    return json_path, md_path


def run_pipeline(task_path: Path, *, dry_run: bool = False, timeout: int = 300) -> PipelineResult:
    task = load_task(task_path)
    result = PipelineResult(
        task_id=task.task_id,
        task_path=repo_display_path(task.path),
        status="running",
        dry_run=dry_run,
        started_at=utc_now(),
        agent_handoff=agent_handoff_plan_for(task),
        files_affected=task.files_affected,
        implementation_steps=implementation_steps_for(task),
    )

    failures = validate_task(task)
    result.stage_results.append({
        "stage": "PLAN",
        "agent": "claude_manager",
        "ok": not failures,
        "failures": failures,
    })
    result.failures.extend(failures)
    if failures:
        result.status = "failed"
        result.reviewer_notes.append("Task spec is incomplete; Claude Manager must clarify it before BUILD.")
        return finalize(task, result, write=not dry_run)

    before = snapshot_files(task)
    result.stage_results.append({
        "stage": "BUILD",
        "agent": "codex_builder",
        "ok": True,
        "notes": result.implementation_steps,
    })

    safety_failures = run_safety_gates(task)
    result.safety_failures = safety_failures
    result.stage_results.append({
        "stage": "SAFETY",
        "agent": "trading_authority",
        "ok": not safety_failures,
        "failures": safety_failures,
    })
    if safety_failures:
        result.status = "failed"
        result.failures.extend(safety_failures)
        result.reviewer_notes.append("Trading Authority blocked the task before tests because safety gates failed.")
        return finalize(task, result, write=not dry_run)

    command_failures: list[str] = []
    for command in task.test_commands:
        if dry_run:
            command_result = CommandResult(
                command=command,
                return_code=0,
                skipped=True,
                reason="dry-run mode",
            )
        else:
            try:
                command_result = run_command(command, timeout)
            except subprocess.TimeoutExpired:
                command_result = CommandResult(
                    command=command,
                    return_code=124,
                    stderr=f"command timed out after {timeout}s",
                )
        result.tests_run.append(command_to_dict(command_result))
        if command_result.return_code != 0:
            command_failures.append(f"test command failed ({command_result.return_code}): {command}")

    result.stage_results.append({
        "stage": "TEST",
        "agent": "codex_builder",
        "ok": not command_failures,
        "failures": command_failures,
    })
    result.failures.extend(command_failures)
    result.files_changed = changed_files(before, task)

    post_safety_failures = run_safety_gates(task)
    new_safety_failures = [item for item in post_safety_failures if item not in result.safety_failures]
    if new_safety_failures:
        result.safety_failures.extend(new_safety_failures)
        result.failures.extend(new_safety_failures)

    review_ok = not result.failures
    result.stage_results.append({"stage": "REVIEW", "agent": "gpt_reviewer", "ok": review_ok})
    if review_ok:
        result.reviewer_notes.append("GPT Reviewer: tests and safety gates passed; output remains advisory and paper-only.")
        result.stage_results.append({"stage": "APPROVE", "agent": "trading_authority", "ok": True})
        result.status = "passed"
    else:
        result.reviewer_notes.append("GPT Reviewer: one or more checks failed; task remains failed until corrected.")
        result.stage_results.append({"stage": "APPROVE", "agent": "trading_authority", "ok": False})
        result.status = "failed"

    return finalize(task, result, write=not dry_run)


def finalize(task: Task, result: PipelineResult, *, write: bool) -> PipelineResult:
    result.finished_at = utc_now()
    result.stage_results.append({"stage": "LOG", "agent": "pipeline", "ok": write, "dryRun": not write})
    if write:
        json_path, md_path = write_logs(result)
        result.log_json = str(json_path.relative_to(ROOT))
        result.log_markdown = str(md_path.relative_to(ROOT))
        # Rewrite logs with their own paths included.
        json_path.write_text(json.dumps(result.__dict__, indent=2, default=str), encoding="utf-8")
        write_status(task, result)
    return result


def print_summary(result: PipelineResult) -> None:
    print(f"task: {result.task_id}")
    print(f"status: {result.status}")
    print(f"dry_run: {result.dry_run}")
    if result.safety_failures:
        print("safety_failures:")
        for failure in result.safety_failures:
            print(f"  - {failure}")
    if result.failures:
        print("failures:")
        for failure in result.failures:
            print(f"  - {failure}")
    if result.log_json:
        print(f"log_json: {result.log_json}")
    if result.log_markdown:
        print(f"log_markdown: {result.log_markdown}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Spencer repo-native workflow tasks.")
    parser.add_argument("--task", help="Path to one Markdown or JSON task file.")
    parser.add_argument("--all", action="store_true", help="Run all pending tasks in workflow/tasks/.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and plan without running tests or writing logs.")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per test command in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.task and not args.all:
        parser.error("provide --task PATH or --all")

    task_paths = [resolve_repo_path(args.task)] if args.task else discover_pending_tasks()
    if not task_paths:
        print("No pending workflow tasks.")
        return 0

    exit_code = 0
    for path in task_paths:
        result = run_pipeline(path, dry_run=args.dry_run, timeout=args.timeout)
        print_summary(result)
        if result.status != "passed":
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
