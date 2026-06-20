"""Read-only scanner for secrets and never-commit files.

The scanner only reads git-tracked files from ``git ls-files``. It never writes,
never fixes, never calls the network, and never contacts broker APIs.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
SEVERITY_ORDER = (HIGH, MEDIUM, LOW)


@dataclass(frozen=True)
class Finding:
    severity: str
    path: str
    line: int | None
    rule: str
    message: str


SECRET_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        HIGH,
        "google_api_key",
        re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    ),
    (
        HIGH,
        "openai_api_key",
        re.compile(r"\bsk-[0-9A-Za-z_-]{20,}\b"),
    ),
    (
        HIGH,
        "aq_prefixed_token",
        re.compile(r"\bAQ\.[0-9A-Za-z_-]{16,}\b"),
    ),
    (
        HIGH,
        "bearer_token",
        re.compile(r"(?i)\bbearer\s+[0-9A-Za-z._~+/\-=]{20,}"),
    ),
    (
        HIGH,
        "private_key",
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    ),
    (
        HIGH,
        "hardcoded_password",
        re.compile(
            r"""(?ix)
            ["']?\b(password|passwd|pwd)\b["']?
            \s*[:=]\s*
            (?P<quote>["'])
            (?!(?:changeme|change-me|example|fake|placeholder|redacted|test|todo)\b)
            [^"'\s]{6,}
            (?P=quote)
            """
        ),
    ),
)


NEVER_COMMIT_GLOBS = (
    "*.db",
    "*.log",
    ".env",
    ".env.*",
    "*.pem",
    "*cookie*",
    "*credential*",
    "*token*",
)


def tracked_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        repo_root / line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def is_never_commit_path(path_text: str) -> bool:
    normalized = path_text.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(normalized, pattern)
        for pattern in NEVER_COMMIT_GLOBS
    )


def _read_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def scan_content(path_text: str, content: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = content.splitlines() or [""]
    for line_no, line in enumerate(lines, start=1):
        for severity, rule, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(
                        severity=severity,
                        path=path_text,
                        line=line_no,
                        rule=rule,
                        message="credential-like value detected",
                    )
                )
    return findings


def scan_paths(paths: list[Path], repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        path_text = _display_path(path, repo_root)
        if is_never_commit_path(path_text):
            findings.append(
                Finding(
                    severity=HIGH,
                    path=path_text,
                    line=None,
                    rule="never_commit_file",
                    message="tracked file matches a never-commit pattern",
                )
            )

        content = _read_text(path)
        if content is None:
            continue
        findings.extend(scan_content(path_text, content))
    return findings


def grouped_findings(findings: list[Finding]) -> dict[str, list[Finding]]:
    return {
        severity: [finding for finding in findings if finding.severity == severity]
        for severity in SEVERITY_ORDER
    }


def print_report(findings: list[Finding]) -> None:
    if not findings:
        print("Secret scan: no findings.")
        return

    print("Secret scan findings:")
    grouped = grouped_findings(findings)
    for severity in SEVERITY_ORDER:
        items = grouped[severity]
        if not items:
            continue
        print(f"\n{severity}:")
        for finding in items:
            location = finding.path
            if finding.line is not None:
                location = f"{location}:{finding.line}"
            print(f"  - {location} [{finding.rule}] {finding.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only scan for tracked secrets.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to scan. Defaults to current directory.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    try:
        paths = tracked_files(repo_root)
    except subprocess.CalledProcessError as exc:
        print(f"Secret scan unavailable: git ls-files failed ({exc.returncode})", file=sys.stderr)
        return 2

    findings = scan_paths(paths, repo_root)
    print_report(findings)
    return 1 if any(finding.severity == HIGH for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
