"""Machine-readable agent workflow policy for Spencer."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "workflow" / "agents" / "agent_policy.json"

ROLE_VIOLATION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(claude|codex|gpt|antigravity|agent)\b.*\b(enable|turn on)\s+live\s+trading\b", "agent live trading enablement"),
    (r"\b(claude|codex|gpt|antigravity|agent)\b.*\b(place|submit|create|approve)\s+(a\s+)?(live\s+)?(broker\s+)?orders?\b", "agent order placement or approval"),
    (r"\b(claude|codex|gpt|antigravity|agent)\b.*\bbypass\s+risk\s+gates?\b", "agent risk gate bypass"),
    (r"\bantigravity\b.*\b(invent|fake|simulate)\b.*\b(p&l|pnl|profit|trade|trades|bot\s+status|state)\b", "Antigravity fake display state"),
    (r"\bgpt\b.*\b(approve|authorize)\b.*\border", "GPT order approval"),
    (r"\btrading\s+authority\b.*\bbypass\s+risk\s+gates?\b", "Trading Authority risk gate bypass"),
)


def load_agent_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def agent_handoff_plan_for(task: Any) -> list[dict[str, str]]:
    policy = load_agent_policy()
    handoff = []
    for step in policy.get("automaticFlow", []):
        handoff.append({
            "stage": str(step.get("stage", "")),
            "agent": str(step.get("agent", "")),
            "role": str(step.get("role", "")),
            "taskId": task.task_id,
        })
    display = policy.get("display") or {}
    if display:
        handoff.append({
            "stage": "DISPLAY",
            "agent": str(display.get("agent", "antigravity_designer")),
            "role": str(display.get("role", "Antigravity may only display verified backend truth.")),
            "taskId": task.task_id,
        })
    return handoff


def safety_check_agent_policy(task: Any) -> list[str]:
    text = "\n".join([
        task.objective,
        "\n".join(task.acceptance_criteria),
        "\n".join(task.safety_rules),
        task.expected_output,
    ]).lower()
    failures = []
    for pattern, label in ROLE_VIOLATION_PATTERNS:
        for line in text.splitlines():
            for match in re.finditer(pattern, line, flags=re.IGNORECASE):
                if _has_safe_negation(line, match.start()):
                    continue
                failures.append(f"agent policy violation: {label}")
    return sorted(set(failures))


def _has_safe_negation(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - 48):match_start]
    return any(window.endswith(prefix) for prefix in (
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
        "cannot ",
        "can not ",
    ))
