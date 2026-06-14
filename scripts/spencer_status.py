"""Print one read-only snapshot of Spencer's operational state."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import spencer_quote_server
from bot.market_data import now_ist
from scripts import audit_data_integrity as audit

DB_PATH = ROOT / "kite_bot.db"
SCOREBOARD_PATH = ROOT / "workflow" / "scoreboard.json"
DEPLOYMENT_GATE_PATH = ROOT / "workflow" / "deployment_gate.json"
REPO_ROOT = ROOT


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _scoreboard(path: Path) -> dict[str, Any]:
    payload = _load_json_object(path)
    return {
        "available": payload is not None,
        "functional": payload.get("functional") if payload else None,
        "profitability": payload.get("profitability") if payload else None,
        "composite": payload.get("composite") if payload else None,
        "candidatesTested": payload.get("candidatesTested") if payload else None,
        "candidatesKilled": payload.get("candidatesKilled") if payload else None,
        "validatedEdges": payload.get("validatedEdges") if payload else None,
    }


def _safety_gate(path: Path) -> dict[str, Any]:
    payload = _load_json_object(path)
    return {
        "available": payload is not None,
        "decision": payload.get("decision") if payload else None,
        "paperOnly": payload.get("paperOnly") if payload else None,
        "deploymentBlocked": payload.get("deploymentBlocked") if payload else None,
        "liveTradingAllowed": payload.get("liveTradingAllowed") if payload else None,
    }


def _data_status(db_path: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    report = audit.audit_database(db_path)
    failed = [
        check["name"]
        for check in report["checks"]
        if check["status"] == "FAIL"
    ]
    warnings = [
        check["name"]
        for check in report["checks"]
        if check["status"] == "WARN"
    ]
    readiness = report["research_readiness"]
    return (
        {
            "overall": report["summary"]["status"],
            "failedChecks": failed,
            "warningChecks": warnings,
        },
        {
            "fifteenMinSessions": readiness["distinct_15m_sessions"],
            "oneMinSessions": readiness["distinct_1m_sessions"],
            "required": readiness["minimum_15m_sessions"],
            "verdict": readiness["status"],
            "sessionsRemaining": readiness["sessions_remaining"],
        },
        report["generated_at"],
    )


def _research_ledger(db_path: Path) -> list[dict[str, Any]]:
    with audit._read_only_connection(db_path) as conn:
        candidates = spencer_quote_server._research_candidates(conn)
    return [
        {
            "candidateId": candidate.get("candidateId"),
            "version": candidate.get("version"),
            "verdict": candidate.get("status"),
        }
        for candidate in candidates
    ]


def _live_engine(db_path: Path) -> dict[str, Any]:
    """Live paper engine readiness: ARMED if a candidate carries an un-killed
    WALK_FORWARD PASS, else DORMANT. Plus journaled run/trade counts. Read-only."""
    result: dict[str, Any] = {
        "status": "DORMANT", "approvedCandidate": None, "runs": 0, "trades": 0,
    }
    try:
        with audit._read_only_connection(db_path) as conn:
            try:
                passed = conn.execute(
                    """
                    SELECT r.candidate_id, r.candidate_version
                    FROM backtest_runs r
                    WHERE r.stage = 'WALK_FORWARD' AND r.status = 'PASS'
                      AND NOT EXISTS (
                          SELECT 1 FROM backtest_kills k
                          WHERE k.candidate_id = r.candidate_id
                            AND k.candidate_version = r.candidate_version)
                    ORDER BY r.id DESC LIMIT 1
                    """
                ).fetchone()
            except sqlite3.OperationalError:
                passed = None
            if passed:
                result["status"] = "ARMED"
                result["approvedCandidate"] = f"{passed[0]} v{passed[1]}"
            for table, key in (("live_paper_runs", "runs"), ("live_paper_trades", "trades")):
                try:
                    result[key] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.OperationalError:
                    pass
    except (OSError, sqlite3.Error):
        pass
    return result


def _git_value(repo_root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _git_head(repo_root: Path) -> dict[str, str | None]:
    return {
        "commit": _git_value(repo_root, "rev-parse", "--short", "HEAD"),
        "branch": _git_value(repo_root, "branch", "--show-current"),
    }


def build_status(
    *,
    db_path: Path = DB_PATH,
    scoreboard_path: Path = SCOREBOARD_PATH,
    deployment_gate_path: Path = DEPLOYMENT_GATE_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    try:
        data_health, readiness, asof = _data_status(db_path)
    except (OSError, sqlite3.Error) as exc:
        data_health = {
            "overall": "UNAVAILABLE",
            "failedChecks": [],
            "warningChecks": [],
            "error": str(exc),
        }
        readiness = {
            "fifteenMinSessions": None,
            "oneMinSessions": None,
            "required": audit.SPNCR3_MIN_15M_SESSIONS,
            "verdict": "UNAVAILABLE",
            "sessionsRemaining": None,
        }
        asof = now_ist().isoformat()

    try:
        research_ledger = _research_ledger(db_path)
    except (OSError, sqlite3.Error):
        research_ledger = []

    return {
        "asof": asof,
        "readOnly": True,
        "scoreboard": _scoreboard(scoreboard_path),
        "safetyGate": _safety_gate(deployment_gate_path),
        "dataHealth": data_health,
        "readiness": readiness,
        "researchLedger": research_ledger,
        "liveEngine": _live_engine(db_path),
        "git": _git_head(repo_root),
    }


def _display(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def render_text(status: dict[str, Any]) -> str:
    scoreboard = status["scoreboard"]
    gate = status["safetyGate"]
    health = status["dataHealth"]
    readiness = status["readiness"]
    git_head = status["git"]
    lines = [
        "SPENCER STATUS",
        f"As of: {status['asof']}",
        "Mode: READ-ONLY / PAPER-ONLY",
        "",
        "SCOREBOARD",
        (
            f"  Functional {_display(scoreboard['functional'])} | "
            f"Profitability {_display(scoreboard['profitability'])} | "
            f"Composite {_display(scoreboard['composite'])}"
        ),
        (
            f"  Tested {_display(scoreboard['candidatesTested'])} | "
            f"Killed {_display(scoreboard['candidatesKilled'])} | "
            f"Validated edges {_display(scoreboard['validatedEdges'])}"
        ),
        "",
        "SAFETY GATE",
        (
            f"  Decision {_display(gate['decision'])} | "
            f"Paper only {_display(gate['paperOnly'])} | "
            f"Deployment blocked {_display(gate['deploymentBlocked'])} | "
            f"Live trading allowed {_display(gate['liveTradingAllowed'])}"
        ),
        "",
        "DATA HEALTH",
        f"  Integrity: {_display(health['overall'])}",
        (
            f"  SPNCR-003: {_display(readiness['fifteenMinSessions'])}/"
            f"{_display(readiness['required'])} 15m sessions | "
            f"{_display(readiness['verdict'])} | "
            f"{_display(readiness['sessionsRemaining'])} remaining"
        ),
        f"  1m sessions: {_display(readiness['oneMinSessions'])}",
        "",
        "RESEARCH LEDGER",
    ]
    if status["researchLedger"]:
        lines.extend(
            (
                f"  {_display(candidate['candidateId'])} "
                f"v{_display(candidate['version'])}: "
                f"{_display(candidate['verdict'])}"
            )
            for candidate in status["researchLedger"]
        )
    else:
        lines.append("  No research candidates recorded.")
    live = status.get("liveEngine", {})
    lines.extend(
        [
            "",
            "LIVE PAPER ENGINE",
            (
                f"  {_display(live.get('status'))}"
                + (f" - approved: {live.get('approvedCandidate')}" if live.get("approvedCandidate")
                   else " - no candidate has passed the ladder yet")
            ),
            f"  Journaled paper runs: {_display(live.get('runs'))} | trades: {_display(live.get('trades'))}",
        ]
    )
    lines.extend(
        [
            "",
            "GIT HEAD",
            (
                f"  {_display(git_head['commit'])} on "
                f"{_display(git_head['branch'])}"
            ),
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print Spencer's read-only operational status."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the entire status report as one JSON object.",
    )
    args = parser.parse_args(argv)

    try:
        status = build_status(
            db_path=DB_PATH,
            scoreboard_path=SCOREBOARD_PATH,
            deployment_gate_path=DEPLOYMENT_GATE_PATH,
            repo_root=REPO_ROOT,
        )
        if args.json:
            print(json.dumps(status, indent=2, sort_keys=True, default=str))
        else:
            print(render_text(status))
    except Exception as exc:
        fallback = {
            "asof": now_ist().isoformat(),
            "readOnly": True,
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(fallback, indent=2, sort_keys=True))
        else:
            print("SPENCER STATUS")
            print("Mode: READ-ONLY / PAPER-ONLY")
            print(f"Status unavailable: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
