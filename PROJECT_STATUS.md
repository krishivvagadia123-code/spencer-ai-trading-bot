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

## Current Score (two scales, graded 2026-06-12 by the manager)

- **Functional scale: 78/100.** Real data pipeline (EOD + intraday, final-candle
  integrity), honest UI sync, full safety posture, research protocol, and a
  working backtest harness (rolling-operand defect found and fixed with a
  regression test). Loses points: scheduled task not yet registered by the
  operator; 1m history still shallow; Antigravity UI redesign pending.
- **Profitability scale: 4/100.** Zero validated edge. Candidate SPNCR-001
  (intraday momentum) was tested and KILLED at in-sample: 28 trades, gross
  +₹78.03, costs ₹239.93, net −₹45.53 — profitable before costs, not after.
  Cost feasibility groundwork is the only credit.
- Composite stays ~48/100. Per protocol, the score rises only on journaled,
  cost-clearing results — never on infrastructure. (A verbal "58" grade was
  checked and rejected: no journaled basis.)

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

## Research Ledger (confirm-or-kill)

- SPNCR-001 (15m momentum continuation): **KILLED at IN_SAMPLE 2026-06-12** —
  net −₹45.53 after costs on 28 trades; archived in `candidates/SPNCR-001.md`;
  kill journaled in `backtest_kills`. Lesson: at ₹5,000 size the real round trip
  costs ~0.2%+ (slippage-dominated); viable candidates need fewer, larger moves.

## In Flight

- Operator: register the 18:00 IST scheduled task (one manual command).
- Manager: Candidate SPNCR-002 (new hypothesis required — not a parameter tweak).

## Next Tasks

- Review + land the daily snapshot; register the scheduled task with the operator.
- Begin RELIANCE mastery research: candidate intraday techniques evaluated against
  the cost bar (edge per trade ≥ ~3× round-trip cost), walk-forward, journaled.
- Keep deployment blocked until validation passes; keep `AUDIT_REPORT.md` current.
