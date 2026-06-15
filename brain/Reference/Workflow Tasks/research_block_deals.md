---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/research_block_deals.md"
---
# research block deals

> Managed mirror of `workflow/tasks/research_block_deals.md`. Edit the source file, not this copy.

# Task: Bulk/block-deals predictive-power research module

## Objective
Build a READ-ONLY research module that ingests NSE bulk-deal and block-deal disclosures and
measures whether they predict forward returns, using Spencer's existing event-study /
information-coefficient framework. This is the next data source after delivery-volume FAILED.
Measure predictive power only - do NOT build a trading strategy, do NOT deploy, do NOT wire
live or trust-into-sizing.

## Context / Source Research Decision
- Module: delivery_eval - Decision: FAIL (great data coverage, but no usable feature: ICs flip
  sign IS/OOS or are <0.03, quintile spreads below the 0.30% cost hurdle, no walk-forward
  survival, on both Nifty-50 and Midcap-100). See AUDIT_REPORT.md section T.
- Pivot: DATA_SOURCE_RESEARCH_PLAN.md sequences bulk/block deals next (free NSE source, the
  plumbing - NSE archive ingest + cache - is proven by nse_delivery).

## Files Affected
- bot/nse_block_deals.py    (new - NSE bulk/block deal ingestion + on-disk cache, None on failure)
- bot/blockdeal_eval.py     (new - read-only event study, mirrors bot/event_eval.py)
- tests/test_blockdeal_eval.py (new - deterministic, offline tests)
- workflow/research_automation.py (register "blockdeal_eval" in MODULE_FILES / MODULE_TESTS)
- workflow/tasks/research_block_deals.md (this file)
- workflow/logs/

## Acceptance Criteria
- bot/nse_block_deals.py fetches NSE bulk-deals and block-deals (buyer/seller, qty, price,
  buy/sell flag) from the public archives, with retry + cache, returning a clean DataFrame
  (date, symbol, side, qty, price, client) or None on failure. Never fabricates a deal.
- If NSE history is not reliably fetchable, the module REPORTS the data limitation honestly
  (like nse_delivery / the news limitation in event_eval) instead of inventing data.
- bot/blockdeal_eval.py runs an event study per bulk/block-deal event: forward 5-day return,
  win rate, cost-adjusted edge (~0.25% hurdle), max adverse move, IS vs OOS, monthly stability,
  and walk-forward survival. Split buy-side vs sell-side events. Nifty-50 first; Midcap-100 if
  data permits. Read-only - no entries/exits/sizing.
- Reuses the proven plumbing: NSE archive fetch + cache pattern from bot/nse_delivery.py, and
  spearman_ic / quintile_spread / event metrics from the existing eval modules.
- Calls workflow/research_automation finalize hooks (add_research_workflow_args /
  finalize_from_args / print_research_workflow_summary) so the result is classified
  PASS / FAIL / NEEDS CONFIRMATION and logged, and the deployment gate is updated.
- Verdict logic is honest: an event type is "usable" only with a stable IC/return sign across
  IS/OOS AND a cost-clearing edge AND walk-forward survival. No survivor on a boundary; flag
  small samples (bulk/block deals are sparse per symbol).
- (Perf) ingest each archive day ONCE and extract all symbols (do not re-parse per symbol-day -
  the lesson from delivery_eval, which timed out re-parsing ~26k times).

## Safety Rules
- Keep Spencer paper-only.
- Do not enable live trading.
- Do not add broker order placement.
- Do not invent dashboard data, trades, profits, P&L, or bot status.
- Do not delete journals.
- Do not bypass risk gates.
- Do not allow AI approval of orders.
- Antigravity must display only verified backend state.

## Test Commands
- python -m py_compile bot/nse_block_deals.py bot/blockdeal_eval.py
- python -m pytest tests/test_blockdeal_eval.py
- python -m bot.blockdeal_eval --top 0 --no-workflow
- python -c "from workflow.research_automation import check_deployment_gate; raise SystemExit(0 if check_deployment_gate() != 0 else 1)"

## Expected Output
- A read-only bulk/block-deal event-study report (events, win rate, avg/forward return,
  cost-adjusted edge, max adverse move, IS vs OOS, monthly stability, walk-forward survival,
  buy vs sell split) printed and logged.
- A research decision (PASS / FAIL / NEEDS CONFIRMATION) written to workflow/logs/ and the
  task status sidecar updated.
- workflow/deployment_gate.json remains blocking (no deployment from a research module).
- AUDIT_REPORT.md updated by the orchestrator with the bulk/block-deal result.

## Out of Scope (do NOT do in this task)
- No trading strategy, no position sizing, no entry/exit logic.
- No live trading, no trust-table wiring, no dashboard changes.
- No paid data integrations (bulk/block deals are free from NSE).
