# Project Status

Status date: 2026-06-12 (evening)

## Summary

Spencer is a private paper-only AI trading research system, governed by the
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

- **Functional scale: 82/100.** History: 78 → 80 (scheduled task registered +
  mid-session EOD guard) → 81 (first automated 18:00 run verified end-to-end:
  exit 0, real close ₹1,293 stored with a 15:30 IST stamp, +367 final candles,
  zero duplicates on re-run) → 82 (11 visual bugs fixed + immersive white
  redesign, all verified in-browser). Loses points: 1m history still shallow;
  Brain/Trade-Tracker pages unaudited visually.
- **Profitability scale: 4/100.** Zero validated edge. Two candidates tested
  and killed honestly (see Research Ledger). Cost-feasibility groundwork is
  the only credit.
- Composite stays ~48/100. Per protocol, the score rises only on journaled,
  cost-clearing results — never on infrastructure. (A verbal "58" grade was
  checked and rejected: no journaled basis.)

## Safety State

- Paper-only: true. Live trading: disabled. Broker execution: disabled.
- AI order approval: disabled. Deployment blocked: true (`workflow/deployment_gate.json`).
- Fake dashboard data: forbidden and removed at the root (simulator deleted).

## Team / Workflow

- Claude Code: manager/orchestrator — task specs, reviews, audits, git,
  verification, and ALL frontend design/styling.
- Codex: engineer — implements one task spec at a time, commits locally, never pushes.
- ChatGPT: document drafter. Perplexity: web research.
- Antigravity: removed from the team (2026-06-12) after twice editing frontend
  files against instructions; its work is archived under `workflow/design/`.
- Git is the sync point; every reviewed change is committed and pushed to
  https://github.com/krishivvagadia123-code/spencer-ai-trading-bot

## Research Findings So Far

- Delivery-volume signal: tested and killed (no stable OOS power).
- Bulk/block deals, FII/DII flows: untestable on free endpoints (no history).
- GDELT news: DOC API is ~3-month recent-only; GKG scoping task queued.
- RELIANCE cost math (`docs/RELIANCE_COST_MATH.md`): intraday round-trip
  breakeven ≈ 0.106% vs median daily range 1.70% — costs are clearable
  intraday; delivery at 1 share needs 1.48% and is structurally near-unplayable.
- Day-selection evidence memo (`docs/research/day_selection_evidence_2026-06-12.md`):
  volatility persistence is the best-documented basis; expiry days amplify NSE
  volatility; gap-continuation unsupported; ORB after costs cautious/null.

## Research Ledger (confirm-or-kill)

- SPNCR-001 (15m momentum continuation): **KILLED at IN_SAMPLE 2026-06-12** —
  net −₹45.53 after costs on 28 trades; archived in `candidates/SPNCR-001.md`;
  kill journaled in `backtest_kills`. Lesson: at ₹5,000 size the real round trip
  costs ~0.2%+ (slippage-dominated); viable candidates need fewer, larger moves.
- SPNCR-002 (15m breakout day-drift): **KILLED at IN_SAMPLE 2026-06-12** —
  9 trades, gross +₹31.83, costs ₹77.18, net −₹7.88 (edge −0.021% vs +0.619%
  bar); archived in `candidates/SPNCR-002.md`. Lesson: lower frequency moved
  net per trade from −0.16% to −0.02%; captured breakout drift is still ~7×
  too small. Next hypothesis must select high-expected-range DAYS.

## Data Clock (automatic)

- `SpencerDailySnapshot` runs every market day at 18:00 IST: real EOD close +
  final intraday candles, append-only, idempotent. First run verified
  2026-06-12 (exit 0, ₹1,293 close, +367 candles, zero duplicates on re-run).
- Engine context fields available for candidates: prev_session_range_pct,
  prev_session_close, gap_pct, session_minute, is_expiry_session.

## In Flight

- Manager: Candidate SPNCR-003 design (volatility-regime day selection) —
  deliberately held until ~70+ sessions of 15m data (~2-3 weeks) to avoid
  burning a hypothesis on a thin base.

## Next Tasks

- Daily: data clock runs itself; verify on operator check-ins.
- ~2-3 weeks: pre-register and run SPNCR-003 through the testing ladder.
- If a candidate passes: spec the live paper-trading wiring (market hours,
  journaled, MASTERY_LEDGER daily review). Deployment gate stays blocked.
