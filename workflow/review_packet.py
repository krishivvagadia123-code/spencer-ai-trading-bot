"""
Create a short repo-native review packet for Spencer agents.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.run_next import (
    AGENT_STATE_PATH,
    CURRENT_TASK_PATH,
    DEPLOYMENT_GATE_PATH,
    LATEST_RESULT_PATH,
    load_deployment_gate,
    summarize_tests,
)


DEFAULT_PACKET_PATH = ROOT / "workflow" / "review_packet.md"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_latest_result_json(state: dict[str, Any]) -> dict[str, Any]:
    raw_path = state.get("lastResultJson")
    if not raw_path:
        return {}
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    return load_json(path)


def excerpt(text: str, max_chars: int = 1800) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated]"


def next_action(summary: dict[str, Any], gate: dict[str, Any]) -> str:
    if summary.get("safety_failures"):
        return "Trading Authority blocked the task. Fix safety failures before any build or review."
    if summary.get("status") != "passed":
        return "Return to Codex Builder to fix failed tests or task issues, then rerun workflow/run_next.py."
    if gate.get("deploymentBlocked", True):
        return "Send to GPT Reviewer; deployment remains blocked and Spencer stays paper-only."
    return "Send to Trading Authority for final paper-only review before any further action."


def create_review_packet(
    *,
    task_path: Path = CURRENT_TASK_PATH,
    latest_result_path: Path = LATEST_RESULT_PATH,
    state_path: Path = AGENT_STATE_PATH,
    deployment_gate_path: Path = DEPLOYMENT_GATE_PATH,
) -> str:
    task_text = task_path.read_text(encoding="utf-8") if task_path.exists() else "Task file missing."
    latest_text = latest_result_path.read_text(encoding="utf-8") if latest_result_path.exists() else "Latest result missing."
    state = load_json(state_path)
    gate = load_deployment_gate(deployment_gate_path)
    summary = load_latest_result_json(state)
    tests = summary.get("tests_run") or []
    passed, failed = summarize_tests(tests)
    files_changed = summary.get("files_changed") or []
    lines = [
        "# Spencer Review Packet",
        "",
        "## Latest Task",
        excerpt(task_text),
        "",
        "## Latest Result",
        excerpt(latest_text),
        "",
        "## Files Changed",
        *([f"- {item}" for item in files_changed] or ["- None detected"]),
        "",
        "## Tests",
        f"- Passed: {passed}",
        f"- Failed: {failed}",
        "",
        "## Deployment Gate",
        f"- Paper only: {gate.get('paperOnly', True)}",
        f"- Deployment blocked: {gate.get('deploymentBlocked', True)}",
        f"- Deployment allowed: {gate.get('deploymentAllowed', False)}",
        f"- Live trading allowed: {gate.get('liveTradingAllowed', False)}",
        f"- Broker execution allowed: {gate.get('brokerExecutionAllowed', False)}",
        f"- AI order approval allowed: {gate.get('aiOrderApprovalAllowed', False)}",
        f"- Reason: {gate.get('reason', 'n/a')}",
        "",
        "## Next Recommended Action",
        next_action(summary, gate),
        "",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a Spencer workflow review packet.")
    parser.add_argument("--output", default=str(DEFAULT_PACKET_PATH), help="Where to write the packet. Use '-' for stdout only.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    packet = create_review_packet()
    if args.output == "-":
        print(packet)
    else:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
        output.write_text(packet, encoding="utf-8")
        print(f"review_packet: {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
