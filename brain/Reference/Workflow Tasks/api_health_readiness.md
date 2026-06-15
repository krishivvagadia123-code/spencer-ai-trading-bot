---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/api_health_readiness.md"
---
# api health readiness

> Managed mirror of `workflow/tasks/api_health_readiness.md`. Edit the source file, not this copy.

# Task 2: Expose data-health + SPNCR-003 readiness on the backend API

## Objective
Surface the data clock's health and research-readiness through the existing
quote server so the dashboard can show them. Backend only — the manager renders
the frontend. Read-only over the DB.

## Changes
- Add `GET /api/health` to `spencer_quote_server.py` returning, computed live
  from the real tables (reuse `scripts/audit_data_integrity.py` functions; do
  NOT duplicate logic):
  * `integrity`: overall PASS/FAIL + per-check status list (no row dumps).
  * `readiness`: { fifteenMinSessions, oneMinSessions, required, verdict,
    sessionsRemaining } against the documented SPNCR3_MIN_15M_SESSIONS.
  * `lastDailyAudit`: the most recent line parsed from
    `workflow/logs/daily_audit.log` if present (timestamp + OVERALL), else null.
  * `asof` timestamp. Never fabricate — if a table is empty, say so honestly.
- The endpoint must open the DB read-only (mode=ro) and never write.

## Tests
- API test against a temp DB: response carries real integrity + readiness;
  empty-DB case returns honest empties, not fabricated numbers. Suite green.

## Safety
- Paper-only; read-only; no journal writes; no fake data; gate stays blocked.

## Out of scope
- No frontend changes (manager owns rendering), no new checks beyond the
  auditor's, no strategy.
