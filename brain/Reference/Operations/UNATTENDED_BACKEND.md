---
tags: [spencer, reference]
updated: 2026-06-20T15:25+05:30
managed: true
source_path: "docs/UNATTENDED_BACKEND.md"
---
# UNATTENDED BACKEND

> Managed mirror of `docs/UNATTENDED_BACKEND.md`. Edit the source file, not this copy.

# Unattended Backend Runbook

Spencer collects its own market data and exercises its engine on a schedule via
Windows Task Scheduler, with no operator present. This runbook lists the
scheduled tasks, when they fire, how to confirm they ran, and how to fix the
most common failure.

All tasks run the project virtual environment (`.venv\Scripts\python.exe`) with
the repo root as the working directory, are registered once by PowerShell
scripts in `scripts/`, and survive reboots. Everything here is collect/replay
only — no task places a live order.

## Tasks

### SpencerIntradayCollect
- **What it does:** appends real RELIANCE intraday candles (15m + 1m) to
  `kite_bot.db` via `scripts/intraday_history.py`. Idempotent; stores only
  final, boundary-aligned candles.
- **When it fires:** every 30 minutes, 09:30–15:30 IST, Mon–Fri.
- **Verify it ran:**
  - `python scripts/intraday_history.py --report` — coverage and gaps.
  - Tail `workflow/logs/intraday_history.log` for the latest "complete" line.
  - `Get-ScheduledTaskInfo -TaskName SpencerIntradayCollect` (LastRunTime / LastTaskResult).
- **Registrar:** `scripts/register_intraday_collector.ps1`

### SpencerDailySnapshot
- **What it does:** records the end-of-day price snapshot via
  `scripts/daily_price_snapshot.py`.
- **When it fires:** daily at 18:00 (after the close).
- **Verify it ran:** `Get-ScheduledTaskInfo -TaskName SpencerDailySnapshot`
  (LastTaskResult `0` = success); check the day's snapshot row in `kite_bot.db`.
- **Registrar:** `scripts/register_daily_snapshot.ps1`

### SpencerDryRun
- **What it does:** replays the active candidate through the live paper engine
  (`scripts/run_live_paper.py --mode dry-run`) over the latest collected
  session, journaling to the `live_paper_*` tables. Paper-only; requires no
  walk-forward pass.
- **When it fires:** 16:00, Mon–Fri (after the close).
- **Verify it ran:** `Get-ScheduledTaskInfo -TaskName SpencerDryRun`; check the
  newest row in `live_paper_runs`.
- **Registrar:** `scripts/register_dry_run.ps1`
- **Note:** if `Get-ScheduledTask` does not list `SpencerDryRun`, it has not
  been registered yet — run the registrar once.

## Verify all tasks at once
- `Get-ScheduledTask | Where-Object { $_.TaskName -like 'Spencer*' }`
- `python scripts/scheduler_healthcheck.py` — read-only; flags any task whose
  last result was non-zero or whose data is stale, and exits non-zero on a flag.

## Troubleshooting: task shows error 0x800710E0
`0x800710E0` ("The operator or administrator has refused the request") means
Windows refused to start the task. Historically this happened because the
default Task Scheduler power settings refuse to run on battery
(`DisallowStartIfOnBatteries`) and do not retry a missed run — so collection was
silently skipped while the laptop was unplugged.

**Fix (already baked into the registrar scripts):** the tasks are now registered
with battery-resilient settings — `AllowStartIfOnBatteries`,
`DontStopIfGoingOnBatteries`, `StartWhenAvailable` (catch up a missed run), and
`WakeToRun`. If you see `0x800710E0`, re-run that task's registrar script in
`scripts/`, then confirm with `(Get-ScheduledTask -TaskName <name>).Settings`.
