---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/research_fii_dii_flows.md"
---
# research fii dii flows

> Managed mirror of `workflow/tasks/research_fii_dii_flows.md`. Edit the source file, not this copy.

# Task: FII/DII flows predictive-power research module

## Objective
Build a READ-ONLY research module that ingests daily FII (foreign) and DII (domestic
institutional) net cash flow figures and measures whether they predict forward INDEX returns,
using Spencer's existing IC / event framework. This is the next data source because block-deal
edge cannot be tested until manual history is supplied. Measure predictive power only - do NOT
build a trading strategy, do NOT deploy, do NOT wire live or trust-into-sizing.

## Context / Source Research Decision
- Module: blockdeal_eval - Decision: NEEDS MANUAL HISTORY (data-access built + tested, but the
  static archive gave 0 Nifty-50 events; real backtest needs operator-supplied CSVs). See
  AUDIT_REPORT.md section V and `workflow/tasks/blockdeals_manual_history.md`.
- Pivot: DATA_SOURCE_RESEARCH_PLAN.md sequences FII/DII flows next (free NSE/SEBI data; the
  archive-ingest + cache plumbing is proven by nse_delivery / nse_block_deals).
- IMPORTANT scope note: FII/DII figures are MARKET-LEVEL (aggregate), not per-stock. So this is
  a market-TIMING / regime study against the index, NOT a stock-selection study.

## Files Affected
- bot/nse_flows.py            (new - FII/DII daily net-flow ingestion + cache, None on failure)
- bot/flows_eval.py           (new - read-only market-timing study vs ^NSEI forward returns)
- tests/test_flows_eval.py    (new - deterministic, offline tests with fixtures)
- workflow/research_automation.py (register "flows_eval" in MODULE_FILES / MODULE_TESTS)
- workflow/tasks/research_fii_dii_flows.md (this file)
- workflow/logs/

## Acceptance Criteria
- bot/nse_flows.py fetches daily FII & DII net cash buy/sell (provisional) from a free NSE/SEBI
  source, with retry + cache, returning a clean DataFrame (date, fii_net, dii_net) or None on
  failure. Reports the data limitation honestly if unavailable; never fabricates flows.
- bot/flows_eval.py tests, against ^NSEI (and optionally ^NSEMDCP/midcap) forward returns
  (e.g. 1-day and 5-day): IC in-sample vs out-of-sample, quintile spread, cost-adjusted edge,
  monthly stability, and walk-forward survival, for features: fii_net, dii_net, combined
  (fii_net - dii_net), and their z-scores. Market-timing framing only - no per-stock claims,
  no entries/exits/sizing.
- Honest verdict: "usable" only with a stable IC sign across IS/OOS AND a cost-clearing edge
  AND walk-forward survival. Report DATA_UNAVAILABLE if flows can't be fetched. No fabrication.
- (Perf) one-pass ingest; cache the flow series once.
- Calls workflow/research_automation finalize hooks so the result is classified
  PASS / FAIL / NEEDS CONFIRMATION / DATA_UNAVAILABLE and logged; deployment gate stays blocking.

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
- python -m py_compile bot/nse_flows.py bot/flows_eval.py
- python -m pytest tests/test_flows_eval.py
- python -m bot.flows_eval --no-workflow
- python -c "from workflow.research_automation import check_deployment_gate; raise SystemExit(0 if check_deployment_gate() != 0 else 1)"

## Expected Output
- A read-only FII/DII market-timing report (observations, IC IS vs OOS, quintile spread,
  cost-adjusted edge, monthly stability, walk-forward survival) printed and logged.
- A research decision (PASS / FAIL / NEEDS CONFIRMATION / DATA_UNAVAILABLE) written to
  workflow/logs/ and the task status sidecar updated.
- workflow/deployment_gate.json remains blocking (no deployment from a research module).
- AUDIT_REPORT.md updated by the orchestrator with the FII/DII result.

## Out of Scope (do NOT do in this task)
- No trading strategy, no position sizing, no entry/exit logic.
- No per-stock selection claims (FII/DII is aggregate/market-level).
- No live trading, no trust-table wiring, no dashboard changes. No paid data; no synthetic flows.
