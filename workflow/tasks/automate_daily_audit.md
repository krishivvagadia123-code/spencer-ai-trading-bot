# Task 1: Run the data-integrity audit automatically after each daily snapshot

## Objective
The auditor exists (`scripts/audit_data_integrity.py`) but nothing runs it on a
schedule. Wire it into the existing 18:00 IST daily job so the data clock is
actually watched every day, with results logged. Read-only; no data changes.

## Changes
- Extend `scripts/run_daily_market_data.ps1` so that AFTER the EOD snapshot and
  intraday collection, it runs the auditor via the project venv python.
- Append the auditor's outcome to `workflow/logs/daily_audit.log` with a
  timestamp: OVERALL PASS/FAIL, any FAIL check names, the gap-WARN count, and
  the SPNCR-003 readiness line (sessions / required / verdict).
- If the auditor exits non-zero (a real integrity FAIL), the log line must be
  clearly marked `ALERT` so it is greppable; the daily job should still exit 0
  for the snapshot/collection portion (audit failure is a report, not a crash).
- Do not change the auditor's logic.

## Tests
- A small test (or a dry-run invocation documented in the task) showing the
  audit step runs and writes a log line. Keep the full suite green.

## Safety
- Paper-only; read-only audit; no journal writes; gate stays blocked.

## Out of scope
- No new checks, no schedule-time change (stays 18:00), no UI, no strategy.
