"""Append one compact daily data-integrity audit result to the workflow log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


def format_audit_log_line(
    report: dict[str, Any],
    *,
    audit_exit_code: int,
) -> str:
    summary = report.get("summary") or {}
    overall = str(summary.get("status") or "FAIL").upper()
    checks = report.get("checks") or []
    failed_names = [
        str(check.get("name") or check.get("id") or "unnamed check")
        for check in checks
        if str(check.get("status") or "").upper() == "FAIL"
    ]
    gap_check = next(
        (check for check in checks if check.get("id") == "intraday_gaps"),
        {},
    )
    gap_warn_count = int((gap_check.get("details") or {}).get("gap_sessions") or 0)
    readiness = report.get("research_readiness") or {}
    sessions = int(readiness.get("distinct_15m_sessions") or 0)
    required = int(readiness.get("minimum_15m_sessions") or 0)
    verdict = str(readiness.get("status") or "NOT-READY")
    timestamp = str(report.get("generated_at") or "timestamp-unavailable")
    marker = " | ALERT" if audit_exit_code != 0 or overall == "FAIL" else ""
    failures = ", ".join(failed_names) if failed_names else "none"
    return (
        f"{timestamp}{marker} | OVERALL {overall} | FAIL checks: {failures} "
        f"| gap-WARN count: {gap_warn_count} "
        f"| SPNCR-003 readiness: {sessions}/{required} sessions | {verdict}"
    )


def append_audit_log(
    report: dict[str, Any],
    log_path: Path,
    *,
    audit_exit_code: int,
) -> str:
    line = format_audit_log_line(report, audit_exit_code=audit_exit_code)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{line}\n")
    return line


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append a compact data-integrity audit result to a log."
    )
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--audit-exit-code", type=int, required=True)
    args = parser.parse_args(argv)

    try:
        report = json.load(sys.stdin)
        if not isinstance(report, dict):
            raise ValueError("audit report must be a JSON object")
        line = append_audit_log(
            report,
            args.log,
            audit_exit_code=args.audit_exit_code,
        )
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        print(f"Could not append daily audit result: {exc}", file=sys.stderr)
        return 1

    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
