"""
Deterministic AI-tool governance and trading-authority contract.

This module is deliberately static and backend-owned. It tells the UI which
tool owns which kind of work, and which operator actions are currently allowed.
No AI model is allowed to promote advice into an order decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.control import read_state as read_control_state


PAPER_ONLY_MODE = "paper-only"


TOOL_ROLES: dict[str, dict[str, Any]] = {
    "dashboard": {
        "displayName": "Dashboard (manager-owned)",
        "corePurpose": "Render verified backend state in the trading dashboard.",
        "owns": [
            "UI rendering",
            "data presentation",
            "visual feedback",
            "component state derived from backend state",
        ],
        "mayDecide": [
            "How verified backend state is displayed",
            "Whether a control should be visually disabled from backend capability flags",
            "Local form validation such as required fields and numeric formatting",
        ],
        "mustDefer": [
            "Trading eligibility",
            "order state",
            "strategy rules",
            "risk decisions",
            "source-of-truth data freshness",
        ],
        "mustNeverDo": [
            "Invent market, order, or PnL data",
            "override backend blocks",
            "infer a trade decision from chart visuals",
            "place or approve orders",
        ],
    },
    "claude": {
        "displayName": "Claude",
        "corePurpose": "Coordinate architecture, specs, sequencing, and boundary validation.",
        "owns": [
            "architecture decisions",
            "feature specifications",
            "acceptance criteria",
            "handoff sequencing",
            "boundary reviews",
        ],
        "mayDecide": [
            "whether a specification is complete",
            "which tool should act next",
            "whether output violates a tool boundary",
        ],
        "mustDefer": [
            "production implementation to Codex",
            "UI rendering to the dashboard layer",
            "analysis drafts to GPT",
            "trade authorization to deterministic backend risk and order systems",
        ],
        "mustNeverDo": [
            "write production code",
            "place orders",
            "bypass risk or audit rules",
        ],
    },
    "codex": {
        "displayName": "Codex",
        "corePurpose": "Implement production code from complete, approved specifications.",
        "owns": [
            "code generation",
            "API route implementation",
            "database queries",
            "tests",
            "backend logic execution",
        ],
        "mayDecide": [
            "implementation details inside an approved spec",
            "repo-local code structure",
            "test coverage needed for the implementation risk",
        ],
        "mustDefer": [
            "architecture ambiguity to Claude",
            "trading decisions to deterministic backend authority",
            "visual interaction choices to the dashboard layer",
        ],
        "mustNeverDo": [
            "invent missing strategy rules",
            "define architecture alone",
            "ship vague behavior",
            "approve or place trades",
        ],
    },
    "gpt": {
        "displayName": "GPT",
        "corePurpose": "Analyze, explain, and report without direct system control.",
        "owns": [
            "analysis",
            "explanations",
            "reports",
            "educational output",
            "non-authoritative strategy interpretation",
        ],
        "mayDecide": [
            "how to explain a result",
            "what caveats belong in a report",
            "which observations are useful for a human review",
        ],
        "mustDefer": [
            "system-impacting recommendations to Claude",
            "production code to Codex",
            "UI behavior to the dashboard layer",
            "trade authorization to deterministic backend authority",
        ],
        "mustNeverDo": [
            "mutate production systems",
            "place orders",
            "approve order placement",
            "write deployable code directly",
        ],
    },
    "tradingAuthority": {
        "displayName": "Trading Authority Layer",
        "corePurpose": "Own deterministic paper-trading state, risk gates, order eligibility, and audit truth.",
        "owns": [
            "strategy engine signals",
            "risk gates",
            "paper order journal",
            "broker/live-trading blocks",
            "audit source of truth",
        ],
        "mayDecide": [
            "whether a paper entry is allowed",
            "whether live trading is blocked",
            "whether UI actions are currently available",
            "which source of truth is authoritative",
        ],
        "mustDefer": [
            "rendering to the dashboard layer",
            "architecture changes to Claude",
            "implementation changes to Codex",
            "explanatory reports to GPT",
        ],
        "mustNeverDo": [
            "use an AI explanation as order approval",
            "enable live trading without an audited broker adapter and explicit double gate",
        ],
    },
}


WORKFLOW: list[dict[str, str]] = [
    {
        "step": "spec",
        "owner": "claude",
        "output": "complete implementation contract with boundaries and acceptance criteria",
    },
    {
        "step": "analysis",
        "owner": "gpt",
        "output": "non-authoritative analysis or explanation for Claude validation",
    },
    {
        "step": "build",
        "owner": "codex",
        "output": "production code, tests, and backend contracts matching the approved spec",
    },
    {
        "step": "display",
        "owner": "dashboard",
        "output": "reactive UI bound only to verified backend state and capabilities",
    },
    {
        "step": "authority",
        "owner": "tradingAuthority",
        "output": "deterministic action permission, risk status, order state, and audit truth",
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decision(
    *,
    action: str,
    label: str,
    owner: str,
    allowed: bool,
    reasons: list[str] | None = None,
    source_of_truth: str = "deterministic backend",
) -> dict[str, Any]:
    return {
        "action": action,
        "label": label,
        "owner": owner,
        "allowed": bool(allowed),
        "reasons": reasons or [],
        "sourceOfTruth": source_of_truth,
    }


def _control_reasons() -> list[str]:
    control = read_control_state()
    reasons: list[str] = []
    if control.killed:
        reasons.append(control.block_reason() or "kill switch is active")
    if control.paused:
        reasons.append(control.block_reason() or "paper entries are paused")
    return reasons


def build_action_capabilities(
    bot_status: dict[str, Any] | None = None,
    *,
    journal_present: bool = True,
) -> dict[str, Any]:
    """
    Build UI capabilities from backend state.

    The dashboard should use these booleans to enable/disable controls instead of
    inferring permissions from labels, charts, or model text.
    """
    bot_status = bot_status or {}
    running = bool(bot_status.get("running"))
    control_reasons = _control_reasons()

    start_reasons: list[str] = []
    if running:
        start_reasons.append("paper bot loop is already running")
    if control_reasons:
        start_reasons.extend(control_reasons)

    stop_reasons = [] if running else ["paper bot loop is not running"]

    actions = {
        "viewDashboard": _decision(
            action="viewDashboard",
            label="View verified dashboard state",
            owner="dashboard",
            allowed=True,
        ),
        "requestAnalysis": _decision(
            action="requestAnalysis",
            label="Ask GPT/Gemini for explanation",
            owner="gpt",
            allowed=True,
            reasons=["analysis is advisory only and cannot approve orders"],
        ),
        "setBudget": _decision(
            action="setBudget",
            label="Set paper budget",
            owner="tradingAuthority",
            allowed=True,
            reasons=["budget updates persist to the paper engine state store"],
        ),
        "startPaperBot": _decision(
            action="startPaperBot",
            label="Start paper research loop",
            owner="tradingAuthority",
            allowed=not running and not control_reasons,
            reasons=start_reasons,
        ),
        "stopPaperBot": _decision(
            action="stopPaperBot",
            label="Stop paper research loop",
            owner="tradingAuthority",
            allowed=running,
            reasons=stop_reasons,
        ),
        "manualPaperOrder": _decision(
            action="manualPaperOrder",
            label="Submit manual paper order from UI",
            owner="tradingAuthority",
            allowed=False,
            reasons=["no audited manual-order endpoint exists"],
        ),
        "placeLiveOrder": _decision(
            action="placeLiveOrder",
            label="Place live broker order",
            owner="tradingAuthority",
            allowed=False,
            reasons=["Spencer is paper-only; live broker execution is not implemented"],
        ),
        "resetJournal": _decision(
            action="resetJournal",
            label="Reset paper journal",
            owner="tradingAuthority",
            allowed=False,
            reasons=["journal is the audit record and is preserved by reset"],
        ),
    }

    if not journal_present:
        actions["viewDashboard"]["reasons"] = [
            "journal not found yet; dashboard may show honest empty state"
        ]

    return {
        "mode": PAPER_ONLY_MODE,
        "generatedAt": _now_iso(),
        "sourceOfTruth": "kite_bot.db, control_state.json, paper_engine.py",
        "actions": actions,
    }


def build_governance_snapshot(
    bot_status: dict[str, Any] | None = None,
    *,
    journal_present: bool = True,
) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": PAPER_ONLY_MODE,
        "principle": "Claude governs, designs, and verifies; Codex builds; the dashboard displays; GPT explains; the backend decides.",
        "generatedAt": _now_iso(),
        "roles": TOOL_ROLES,
        "workflow": WORKFLOW,
        "capabilities": build_action_capabilities(
            bot_status,
            journal_present=journal_present,
        ),
        "hardRules": [
            "No AI tool may make or approve trading decisions.",
            "The dashboard displays backend state and backend action permissions only.",
            "GPT analysis is advisory and cannot mutate trading state.",
            "Codex implements only complete, approved specifications.",
            "Claude validates boundaries but does not write production code.",
            "Live order placement is blocked until an audited broker adapter and explicit double gate exist.",
        ],
    }
