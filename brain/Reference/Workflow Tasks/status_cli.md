---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/status_cli.md"
---
# status cli

> Managed mirror of `workflow/tasks/status_cli.md`. Edit the source file, not this copy.

# Task 3: One-command project status CLI

## Objective
A single command that prints Spencer's full state, so any operator or future
session gets the whole picture instantly. Read-only; aggregates existing sources.

## Changes
- Add `scripts/spencer_status.py` that prints, from existing files/DB only:
  * Scoreboard: `workflow/scoreboard.json` (functional / profitability /
    composite + tested/killed/edges).
  * Safety gate: `workflow/deployment_gate.json` (decision, paperOnly,
    deploymentBlocked, liveTradingAllowed).
  * Data health + readiness: reuse the auditor functions (integrity overall +
    SPNCR-003 readiness verdict and sessions-remaining).
  * Research ledger: candidate ids + verdicts from `backtest_kills` /
    `backtest_runs`.
  * Git HEAD: current short commit + branch (subprocess `git`, read-only).
- `--json` flag emits the whole thing as one JSON object.
- Exit 0 always (status report, not a gate); read-only everywhere.

## Tests
- Test against a temp DB + temp json files: the report includes each section
  and `--json` parses. Suite green.

## Safety
- Paper-only; read-only; no writes anywhere; no fabricated values.

## Out of scope
- No new computations beyond aggregating existing sources, no UI, no strategy.
