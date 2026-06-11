"""
Automatic paper-only research workflow finalizer for Spencer.

Research modules call finalize_research(...) with their result dict. This module
classifies the result, creates the next task file, marks the originating task
complete, writes audit logs, and updates a deployment gate. It never places
orders, enables live trading, or mutates journals.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS = "PASS"
FAIL = "FAIL"
NEEDS_CONFIRMATION = "NEEDS CONFIRMATION"

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "workflow"
TASKS_DIR = WORKFLOW_DIR / "tasks"
LOGS_DIR = WORKFLOW_DIR / "logs"
STATUS_DIR = TASKS_DIR / ".status"
DEPLOYMENT_GATE_PATH = WORKFLOW_DIR / "deployment_gate.json"

MODULE_FILES = {
    "event_eval": "bot/event_eval.py",
    "feature_eval": "bot/feature_eval.py",
    "intraday_eval": "bot/intraday_eval.py",
    "midcap_eval": "bot/midcap_eval.py",
    "delivery_eval": "bot/delivery_eval.py",
    "blockdeal_eval": "bot/blockdeal_eval.py",
    "flows_eval": "bot/flows_eval.py",
    "news_sentiment_eval": "bot/news_sentiment_eval.py",
    "gapup_confirm": "bot/gapup_confirm.py",
    "walkforward": "bot/walkforward.py",
}

MODULE_TESTS = {
    "event_eval": ["tests/test_event_eval.py"],
    "gapup_confirm": ["tests/test_gapup_confirm.py"],
    "delivery_eval": ["tests/test_delivery_eval.py"],
    "blockdeal_eval": ["tests/test_blockdeal_eval.py"],
    "flows_eval": ["tests/test_flows_eval.py"],
    "news_sentiment_eval": ["tests/test_news_sentiment_eval.py"],
}

CONFIRMATION_MODULES = {
    ("event_eval", "gap_up"): "bot/gapup_confirm.py",
}

SAFETY_RULES = [
    "Keep Spencer paper-only.",
    "Do not enable live trading.",
    "Do not add broker order placement.",
    "Do not invent dashboard data, trades, profits, P&L, or bot status.",
    "Do not delete journals.",
    "Do not bypass risk gates.",
    "Do not allow AI approval of orders.",
    "Antigravity must display only verified backend state.",
]


@dataclass
class ResearchDecision:
    module: str
    decision: str
    reason: str
    candidates: list[str] = field(default_factory=list)
    validation_passed: bool = False
    deployment_blocked: bool = True
    result_summary: dict[str, Any] = field(default_factory=dict)
    created_tasks: list[str] = field(default_factory=list)
    existing_tasks: list[str] = field(default_factory=list)
    old_task_status: str | None = None
    log_json: str | None = None
    log_markdown: str | None = None
    deployment_gate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "decision": self.decision,
            "reason": self.reason,
            "candidates": self.candidates,
            "validationPassed": self.validation_passed,
            "deploymentBlocked": self.deployment_blocked,
            "resultSummary": self.result_summary,
            "createdTasks": self.created_tasks,
            "existingTasks": self.existing_tasks,
            "oldTaskStatus": self.old_task_status,
            "logJson": self.log_json,
            "logMarkdown": self.log_markdown,
            "deploymentGate": self.deployment_gate,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip()).strip("_").lower()
    return out or "research"


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def repo_display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def add_research_workflow_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workflow-task",
        default=os.environ.get("SPENCER_WORKFLOW_TASK"),
        help="Optional originating workflow task to mark complete after research finalizes.",
    )
    parser.add_argument(
        "--no-workflow",
        action="store_true",
        help="Print research only; do not create workflow tasks, logs, or deployment gate state.",
    )


def finalize_from_args(module: str, result: dict[str, Any], args: Any) -> dict[str, Any] | None:
    if getattr(args, "no_workflow", False):
        return None
    return finalize_research(module, result, old_task_path=getattr(args, "workflow_task", None))


def print_research_workflow_summary(outcome: dict[str, Any] | None) -> None:
    if not outcome:
        return
    created = outcome.get("createdTasks") or []
    existing = outcome.get("existingTasks") or []
    task_note = ""
    if created:
        task_note = f" created {', '.join(created)}."
    elif existing:
        task_note = f" next task already exists: {', '.join(existing)}."
    block = "deployment blocked" if outcome.get("deploymentBlocked") else "deployment gate passed"
    print(f"\nWORKFLOW: {outcome['decision']} - {block}.{task_note}")
    print(f"Reason: {outcome['reason']}")


def decide_research_result(module: str, result: dict[str, Any]) -> ResearchDecision:
    normalized_module = slugify(module)
    verdict = str(result.get("verdict") or result.get("reason") or "").strip()
    verdict_l = verdict.lower()
    candidates = _extract_candidates(normalized_module, result)
    caveats = _has_caveats(result, verdict_l)
    summary = _result_summary(normalized_module, result, candidates)

    if normalized_module == "gapup_confirm" and result.get("confirmed") is True:
        reason = verdict or "gap_up confirmation validation passed."
        return ResearchDecision(
            module=normalized_module,
            decision=PASS,
            reason=reason,
            candidates=["gap_up"],
            validation_passed=True,
            deployment_blocked=False,
            result_summary=summary,
        )

    if _explicit_failure(result, verdict_l) and not candidates:
        reason = verdict or "Research produced no validated edge."
        return ResearchDecision(
            module=normalized_module,
            decision=FAIL,
            reason=reason,
            candidates=[],
            validation_passed=False,
            deployment_blocked=True,
            result_summary=summary,
        )

    if _needs_confirmation(result, verdict_l, candidates, caveats):
        reason = verdict or "Research found a candidate that still needs confirmation."
        return ResearchDecision(
            module=normalized_module,
            decision=NEEDS_CONFIRMATION,
            reason=reason,
            candidates=candidates or [f"{normalized_module}_edge"],
            validation_passed=False,
            deployment_blocked=True,
            result_summary=summary,
        )

    if candidates:
        reason = verdict or "Research validation passed."
        return ResearchDecision(
            module=normalized_module,
            decision=PASS,
            reason=reason,
            candidates=candidates,
            validation_passed=True,
            deployment_blocked=False,
            result_summary=summary,
        )

    reason = verdict or "Research found no actionable edge."
    return ResearchDecision(
        module=normalized_module,
        decision=FAIL,
        reason=reason,
        candidates=[],
        validation_passed=False,
        deployment_blocked=True,
        result_summary=summary,
    )


def finalize_research(
    module: str,
    result: dict[str, Any],
    *,
    old_task_path: str | Path | None = None,
    write: bool = True,
) -> dict[str, Any]:
    decision = decide_research_result(module, result)
    if write:
        _ensure_dirs()
        _create_next_tasks(decision)
        _write_logs(decision, result)
        if old_task_path:
            _mark_old_task_complete(decision, old_task_path)
        _write_deployment_gate(decision)
    return decision.to_dict()


def check_deployment_gate() -> int:
    if not DEPLOYMENT_GATE_PATH.exists():
        print("deployment blocked: workflow/deployment_gate.json is missing")
        return 1
    try:
        gate = json.loads(DEPLOYMENT_GATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("deployment blocked: workflow/deployment_gate.json is invalid")
        return 1
    if gate.get("deploymentAllowed") is True and gate.get("paperOnly") is True:
        print("deployment gate passed: validation passed, Spencer remains paper-only")
        return 0
    reason = gate.get("reason") or "validation has not passed"
    print(f"deployment blocked: {reason}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Spencer research workflow utilities.")
    parser.add_argument(
        "--check-deployment-gate",
        action="store_true",
        help="Exit nonzero unless the latest research validation passed.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_deployment_gate:
        return check_deployment_gate()
    print("Use --check-deployment-gate to enforce research validation before deployment.")
    return 0


def _extract_candidates(module: str, result: dict[str, Any]) -> list[str]:
    if module == "event_eval":
        candidates = []
        for name, metrics in (result.get("results") or {}).items():
            if not isinstance(metrics, dict):
                continue
            if metrics.get("walk_forward") == "survives" and (metrics.get("cost_adj") or 0) > 0:
                candidates.append(name)
        return candidates

    if module == "gapup_confirm":
        return ["gap_up"] if result.get("confirmed") is True else []

    for key in ("usable_features", "promising_features", "survivors", "candidates"):
        values = result.get(key)
        if isinstance(values, list) and values:
            return [str(item) for item in values]

    verdict = str(result.get("verdict") or "").lower()
    negative = any(word in verdict for word in ("killed", "failed", "no ", "none", "do not"))
    if not negative and ("survives" in verdict or "confirmed" in verdict):
        return [f"{module}_edge"]
    return []


def _has_caveats(result: dict[str, Any], verdict_l: str) -> bool:
    caveat_words = (
        "caveat", "candidate", "confirm", "confirmation", "holdout",
        "multiple-comparisons", "small", "suggestive", "not proof",
        "inconclusive", "longer history", "too thin",
    )
    if any(word in verdict_l for word in caveat_words):
        return True
    if result.get("not_testable"):
        return True
    stable_only = result.get("sign_stable_but_uneconomic")
    return isinstance(stable_only, list) and bool(stable_only)


def _explicit_failure(result: dict[str, Any], verdict_l: str) -> bool:
    if result.get("confirmed") is False:
        return True
    failure_words = (
        "killed", "failed", "no event type", "no edge", "none are usable",
        "none of the", "do not build", "do not proceed",
    )
    return any(word in verdict_l for word in failure_words)


def _needs_confirmation(
    result: dict[str, Any],
    verdict_l: str,
    candidates: list[str],
    caveats: bool,
) -> bool:
    if candidates and caveats:
        return True
    if "inconclusive" in verdict_l:
        return True
    stable_only = result.get("sign_stable_but_uneconomic")
    return isinstance(stable_only, list) and bool(stable_only)


def _result_summary(module: str, result: dict[str, Any], candidates: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "module": module,
        "verdict": result.get("verdict"),
        "candidates": candidates,
    }
    for key in (
        "symbols_used", "symbols", "observations", "horizon_days", "horizon_bars",
        "split_date", "split_day", "confirmed",
    ):
        if key in result:
            summary[key] = result[key]
    return summary


def _ensure_dirs() -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_DIR.mkdir(parents=True, exist_ok=True)


def _create_next_tasks(decision: ResearchDecision) -> None:
    specs = _next_task_specs(decision)
    for path, content in specs:
        if path.exists():
            decision.existing_tasks.append(repo_display_path(path))
            continue
        path.write_text(content, encoding="utf-8")
        decision.created_tasks.append(repo_display_path(path))


def _next_task_specs(decision: ResearchDecision) -> list[tuple[Path, str]]:
    if decision.decision == FAIL:
        name = f"record_{decision.module}_rejection"
        title = f"Record {decision.module} rejection"
        objective = (
            f"Archive the {decision.module} failed research result, keep deployment blocked, "
            "and choose the next paper-only research hypothesis without enabling trading."
        )
        return [(TASKS_DIR / f"{name}.md", _task_markdown(decision, title, objective, name))]

    specs = []
    for candidate in decision.candidates or [f"{decision.module}_edge"]:
        candidate_slug = slugify(candidate)
        if decision.decision == NEEDS_CONFIRMATION:
            name = f"confirm_{candidate_slug}_edge"
            title = f"Confirm {candidate} edge"
            objective = _confirmation_objective(decision.module, candidate)
        else:
            name = f"paper_{candidate_slug}_strategy_spec"
            title = f"Paper strategy spec for {candidate}"
            objective = (
                f"Convert the validated {candidate} research result into a paper-only "
                "strategy specification with verified backend state and no broker execution."
            )
        specs.append((TASKS_DIR / f"{name}.md", _task_markdown(decision, title, objective, name, candidate)))
    return specs


def _confirmation_objective(module: str, candidate: str) -> str:
    if module == "event_eval" and candidate == "gap_up":
        return (
            "Confirm or kill the gap_up candidate from event_eval using more history, "
            "realistic gap-day slippage, clean holdout validation, and out-of-universe "
            "support before any paper-only strategy spec is allowed."
        )
    return (
        f"Confirm or kill the {candidate} candidate from {module} with stricter "
        "out-of-sample validation before any paper-only strategy spec is allowed."
    )


def _task_markdown(
    decision: ResearchDecision,
    title: str,
    objective: str,
    task_name: str,
    candidate: str | None = None,
) -> str:
    files = _files_for_task(decision.module, task_name, candidate)
    tests = _tests_for_task(decision.module, candidate)
    acceptance = _acceptance_for(decision, candidate)
    expected = _expected_for(decision, candidate)
    return "\n".join([
        f"# Task: {title}",
        "",
        "## Objective",
        objective,
        "",
        "## Files Affected",
        *[f"- {item}" for item in files],
        "",
        "## Acceptance Criteria",
        *[f"- {item}" for item in acceptance],
        "",
        "## Safety Rules",
        *[f"- {item}" for item in SAFETY_RULES],
        "",
        "## Test Commands",
        *[f"- {item}" for item in tests],
        "",
        "## Expected Output",
        *[f"- {item}" for item in expected],
        "",
        "## Source Research Decision",
        f"- Module: {decision.module}",
        f"- Decision: {decision.decision}",
        f"- Reason: {decision.reason}",
        "",
    ])


def _files_for_task(module: str, task_name: str, candidate: str | None) -> list[str]:
    files = [
        MODULE_FILES.get(module, f"bot/{module}.py"),
        f"workflow/tasks/{task_name}.md",
        "workflow/research_automation.py",
        "workflow/deployment_gate.json",
        "workflow/logs/",
    ]
    confirm_file = CONFIRMATION_MODULES.get((module, candidate or ""))
    if confirm_file and confirm_file not in files:
        files.insert(1, confirm_file)
    return files


def _tests_for_task(module: str, candidate: str | None) -> list[str]:
    py_files = ["workflow/research_automation.py"]
    module_file = MODULE_FILES.get(module)
    if module_file:
        py_files.append(module_file)
    confirm_file = CONFIRMATION_MODULES.get((module, candidate or ""))
    if confirm_file:
        py_files.append(confirm_file)

    test_files = ["tests/test_research_automation.py"]
    for item in MODULE_TESTS.get(module, []):
        if item not in test_files:
            test_files.append(item)
    if confirm_file == "bot/gapup_confirm.py":
        test_files.extend(item for item in ["tests/test_gapup_confirm.py"] if item not in test_files)

    return [
        "python -m py_compile " + " ".join(py_files),
        "python -m pytest " + " ".join(test_files),
        "python -m workflow.research_automation --check-deployment-gate",
    ]


def _acceptance_for(decision: ResearchDecision, candidate: str | None) -> list[str]:
    if decision.decision == FAIL:
        return [
            "The failed research result is documented without deleting journals.",
            "workflow/deployment_gate.json remains blocked because validation did not pass.",
            "No dashboard panel shows invented trades, P&L, profits, or bot status.",
            "The next paper-only research hypothesis is explicit and testable.",
        ]
    if decision.decision == NEEDS_CONFIRMATION:
        return [
            f"The {candidate or 'candidate'} result is confirmed or killed with stricter OOS validation.",
            "The confirmation run writes PASS, FAIL, or NEEDS CONFIRMATION through workflow/research_automation.py.",
            "Deployment remains blocked unless validation passes.",
            "If validation passes, the next generated task is still paper-only.",
        ]
    return [
        f"The {candidate or 'candidate'} result is converted only into a paper-only strategy spec.",
        "The strategy spec uses verified backend state and no fake dashboard data.",
        "Broker execution, live trading, and AI order approval remain disabled.",
        "The workflow log explains why validation passed.",
    ]


def _expected_for(decision: ResearchDecision, candidate: str | None) -> list[str]:
    if decision.decision == NEEDS_CONFIRMATION:
        return [
            f"A confirmation result for {candidate or 'the candidate'} is written to workflow/logs/.",
            "workflow/deployment_gate.json blocks deployment until validation passes.",
            "The old research task status sidecar is marked passed with the research decision recorded.",
        ]
    if decision.decision == PASS:
        return [
            "A paper-only follow-up task is available in workflow/tasks/.",
            "workflow/deployment_gate.json allows only validated paper deployment state.",
            "Live trading and broker execution remain false or absent.",
        ]
    return [
        "A rejection note or next research hypothesis is available in workflow/tasks/.",
        "workflow/deployment_gate.json blocks deployment.",
        "No live trading, broker order placement, or fake P&L is introduced.",
    ]


def _mark_old_task_complete(decision: ResearchDecision, old_task_path: str | Path) -> None:
    task_path = resolve_repo_path(old_task_path)
    status_path = STATUS_DIR / f"{task_path.stem}.status.json"
    payload = {
        "taskId": slugify(task_path.stem),
        "taskPath": repo_display_path(task_path),
        "status": "passed",
        "researchDecision": decision.decision,
        "researchModule": decision.module,
        "updatedAt": utc_now(),
        "logJson": decision.log_json,
        "logMarkdown": decision.log_markdown,
        "deploymentBlocked": decision.deployment_blocked,
        "createdTasks": decision.created_tasks,
        "existingTasks": decision.existing_tasks,
        "reason": decision.reason,
    }
    status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    decision.old_task_status = repo_display_path(status_path)


def _write_deployment_gate(decision: ResearchDecision) -> None:
    payload = {
        "paperOnly": True,
        "deploymentAllowed": decision.validation_passed,
        "deploymentBlocked": decision.deployment_blocked,
        "liveTradingAllowed": False,
        "brokerExecutionAllowed": False,
        "aiOrderApprovalAllowed": False,
        "fakeDashboardDataAllowed": False,
        "decision": decision.decision,
        "sourceModule": decision.module,
        "candidates": decision.candidates,
        "reason": decision.reason,
        "createdTasks": decision.created_tasks,
        "existingTasks": decision.existing_tasks,
        "updatedAt": utc_now(),
    }
    DEPLOYMENT_GATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    decision.deployment_gate = repo_display_path(DEPLOYMENT_GATE_PATH)


def _write_logs(decision: ResearchDecision, result: dict[str, Any]) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{decision.module}-{slugify(decision.decision)}"
    json_path = LOGS_DIR / f"{base}.json"
    md_path = LOGS_DIR / f"{base}.md"

    payload = decision.to_dict()
    payload["loggedAt"] = utc_now()
    payload["rawResult"] = result
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    md = [
        f"# Research Workflow Result: {decision.module}",
        "",
        f"- Decision: {decision.decision}",
        f"- Deployment blocked: {decision.deployment_blocked}",
        f"- Validation passed: {decision.validation_passed}",
        f"- Candidates: {', '.join(decision.candidates) if decision.candidates else 'None'}",
        f"- Reason: {decision.reason}",
        "",
        "## Created Tasks",
        *([f"- {item}" for item in decision.created_tasks] or ["- None"]),
        "",
        "## Existing Tasks",
        *([f"- {item}" for item in decision.existing_tasks] or ["- None"]),
        "",
        "## Safety",
        "- Spencer remains paper-only.",
        "- Live trading, broker execution, fake P&L, journal deletion, risk bypass, and AI order approval remain blocked.",
        "",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")

    decision.log_json = repo_display_path(json_path)
    decision.log_markdown = repo_display_path(md_path)
    payload.update(decision.to_dict())
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
