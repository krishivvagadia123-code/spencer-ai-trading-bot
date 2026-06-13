# Project Status

Status date: 2026-06-12

## Summary

Spencer is a private paper-only AI trading research system, now governed by the
One-Stock Mastery Doctrine (`SPENCER_CONCEPT.md`): one stock (RELIANCE), one open
position max, exactly â‚¹5,000 paper capital, zero fake data, mastery before expansion.

## Current Epoch

- Account epoch: `one_stock_reliance_v1` (started 2026-06-11).
- Basis: â‚¹5,000.00 â€” cash â‚¹5,000, invested â‚¹0, 0 holdings, 0 orders, 0 closed trades.
- Prior multi-stock history is preserved in the journal (trades â‰¤ id 15); the three
  stale May-27 positions were closed honestly via journaled `ONE_STOCK_RESET` sells.
- The legacy Node simulation backend has been deleted; the frontend talks only to
  the real Python quote server (`spencer_quote_server.py`, port 8787).

## Current Score (two scales, graded 2026-06-12 by the manager)

- **Functional scale: 82/100** (was 80; +1 on 2026-06-12 evening: first automated
  18:00 run verified end-to-end â€” exit 0, real close â‚¹1,293 stored for
  2026-06-12 with a 15:30 IST quote stamp, +367 final intraday candles, and a
  19:51 re-run inserted zero duplicates). Real data pipeline (EOD + intraday,
  final-candle integrity), honest UI sync with live Research Ledger, full
  safety posture, research protocol, battle-tested backtest harness, white
  theme made structural. Loses points: 1m history still shallow; visual polish
  ongoing (Antigravity removed from the team; manager owns styling).
- **Profitability scale: 4/100.** Zero validated edge. Candidate SPNCR-001
  (intraday momentum) was tested and KILLED at in-sample: 28 trades, gross
  +â‚¹78.03, costs â‚¹239.93, net âˆ’â‚¹45.53 â€” profitable before costs, not after.
  Cost feasibility groundwork is the only credit.
- Composite stays ~48/100. Per protocol, the score rises only on journaled,
  cost-clearing results â€” never on infrastructure. (A verbal "58" grade was
  checked and rejected: no journaled basis.)

## Safety State

- Paper-only: true. Live trading: disabled. Broker execution: disabled.
- AI order approval: disabled. Deployment blocked: true (`workflow/deployment_gate.json`).
- Fake dashboard data: forbidden and removed at the root (simulator deleted).

## Team / Workflow

- Claude Code: manager/orchestrator â€” task specs, reviews, audits, git, verification.
- Codex: engineer â€” implements one task spec at a time, commits locally, never pushes.
- ChatGPT: document drafter. Antigravity: frontend design. Perplexity: web research.
- Git is the sync point; every reviewed change is committed and pushed to
  https://github.com/krishivvagadia123-code/spencer-ai-trading-bot

## Research Findings So Far

- Delivery-volume signal: tested and killed (no stable OOS power).
- Bulk/block deals, FII/DII flows: untestable on free endpoints (no history).
- GDELT news: DOC API is ~3-month recent-only; GKG scoping task queued.
- RELIANCE cost math (2026-06-12, `docs/RELIANCE_COST_MATH.md`): intraday
  round-trip breakeven â‰ˆ 0.106% vs median daily range 1.70% â€” costs are clearable
  intraday; delivery at 1 share needs 1.48% and is structurally near-unplayable.

## Research Ledger (confirm-or-kill)

- SPNCR-001 (15m momentum continuation): **KILLED at IN_SAMPLE 2026-06-12** â€”
  net âˆ’â‚¹45.53 after costs on 28 trades; archived in `candidates/SPNCR-001.md`;
  kill journaled in `backtest_kills`. Lesson: at â‚¹5,000 size the real round trip
  costs ~0.2%+ (slippage-dominated); viable candidates need fewer, larger moves.
- SPNCR-002 (15m breakout day-drift): **KILLED at IN_SAMPLE 2026-06-12** â€”
  9 trades, gross +â‚¹31.83, costs â‚¹77.18, net âˆ’â‚¹7.88 (edge âˆ’0.021% vs +0.619%
  bar); archived in `candidates/SPNCR-002.md`. Lesson: lower frequency moved
  net per trade from âˆ’0.16% to âˆ’0.02%; captured breakout drift is still ~7Ã—
  too small. Next hypothesis must select high-expected-range DAYS (gap or
  volatility context), and a deeper dataset materially helps.

## In Flight

- Operator: register the 18:00 IST scheduled task (one manual command).
- Manager: Candidate SPNCR-003 design (day-selection hypothesis) â€” may wait for
  more collected sessions before testing, to avoid burning hypotheses on a
  thin 58-session base.

## Next Tasks

- Review + land the daily snapshot; register the scheduled task with the operator.
- Begin RELIANCE mastery research: candidate intraday techniques evaluated against
  the cost bar (edge per trade â‰¥ ~3Ã— round-trip cost), walk-forward, journaled.
- Keep deployment blocked until validation passes; keep `AUDIT_REPORT.md` current.
