# Project Status

Status date: 2026-06-12

## Summary

Spencer is a private paper-only AI trading research system, now governed by the
One-Stock Mastery Doctrine (`SPENCER_CONCEPT.md`): one stock (RELIANCE), one open
position max, exactly ₹5,000 paper capital, zero fake data, mastery before expansion.

## Current Epoch

- Account epoch: `one_stock_reliance_v1` (started 2026-06-11).
- Basis: ₹5,000.00 — cash ₹5,000, invested ₹0, 0 holdings, 0 orders, 0 closed trades.
- Prior multi-stock history is preserved in the journal (trades ≤ id 15); the three
  stale May-27 positions were closed honestly via journaled `ONE_STOCK_RESET` sells.
- The legacy Node simulation backend has been deleted; the frontend talks only to
  the real Python quote server (`spencer_quote_server.py`, port 8787).

## Current Score

Approximate Spencer score: 48/100. Infrastructure and honesty are strong; no
validated, cost-clearing edge exists yet. The score moves only when journaled
paper results clear costs consistently.

## Safety State

- Paper-only: true. Live trading: disabled. Broker execution: disabled.
- AI order approval: disabled. Deployment blocked: true (`workflow/deployment_gate.json`).
- Fake dashboard data: forbidden and removed at the root (simulator deleted).

## Team / Workflow

- Claude Code: manager/orchestrator — task specs, reviews, audits, git, verification.
- Codex: engineer — implements one task spec at a time, commits locally, never pushes.
- ChatGPT: document drafter. Antigravity: frontend design. Perplexity: web research.
- Git is the sync point; every reviewed change is committed and pushed to
  https://github.com/krishivvagadia123-code/spencer-ai-trading-bot

## Research Findings So Far

- Delivery-volume signal: tested and killed (no stable OOS power).
- Bulk/block deals, FII/DII flows: untestable on free endpoints (no history).
- GDELT news: DOC API is ~3-month recent-only; GKG scoping task queued.
- RELIANCE cost math (2026-06-12, `docs/RELIANCE_COST_MATH.md`): intraday
  round-trip breakeven ≈ 0.106% vs median daily range 1.70% — costs are clearable
  intraday; delivery at 1 share needs 1.48% and is structurally near-unplayable.

## In Flight

- Codex: `workflow/tasks/daily_price_snapshot.md` — daily automatic RELIANCE EOD
  price snapshot via Windows Task Scheduler (append-only, honest failure states).
- ChatGPT: `MASTERY_LEDGER.md` daily review template.

## Next Tasks

- Review + land the daily snapshot; register the scheduled task with the operator.
- Begin RELIANCE mastery research: candidate intraday techniques evaluated against
  the cost bar (edge per trade ≥ ~3× round-trip cost), walk-forward, journaled.
- Keep deployment blocked until validation passes; keep `AUDIT_REPORT.md` current.
