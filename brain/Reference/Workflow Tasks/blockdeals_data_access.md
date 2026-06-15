---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/blockdeals_data_access.md"
---
# blockdeals data access

> Managed mirror of `workflow/tasks/blockdeals_data_access.md`. Edit the source file, not this copy.

# Task: Unblock bulk/block-deals data access (manual CSV + static archive)

## Objective
Make `bot/nse_block_deals.py` able to obtain REAL bulk/block-deal data despite NSE's dynamic
historical API being bot-protected (503). Add two reliable, free, honest ingestion paths:
(1) operator-supplied manual CSV files for any historical date range, and (2) the working NSE
static archive CSVs for recent/forward collection. Then `bot/blockdeal_eval.py` can run the
read-only event study when enough real events exist. Still READ-ONLY: no strategy, no orders,
no deployment, no live, no trust wiring.

## Context / Source Research Decision
- Module: blockdeal_eval - Decision: DATA-LIMITED (not edge-tested). NSE dynamic API
  `/api/historical/{bulk,block}-deals` returns None/503 (bot-protected); the static archive
  `archives.nseindia.com/content/equities/{bulk,block}.csv` returns real deals but only a
  rolling recent window. See AUDIT_REPORT.md section U and DATA_SOURCE_RESEARCH_PLAN.md section 3.
- Orchestrator decision: add manual-CSV upload (primary) + static-archive ingestion
  (forward/recent), NOT mark as permanently blocked. No fabrication - ingest only real rows.

## Files Affected
- bot/nse_block_deals.py        (add manual-CSV folder ingest + static-archive CSV fetch)
- bot/blockdeal_eval.py         (consume the combined source; honest DATA-UNAVAILABLE report)
- tests/test_nse_block_deals.py (new - offline tests for CSV parsing + source precedence)
- tests/test_blockdeal_eval.py  (extend - data-unavailable path)
- data/block_deals/README.md    (new - where the operator drops downloaded NSE CSVs)
- workflow/tasks/blockdeals_data_access.md (this file)
- workflow/logs/

## Acceptance Criteria
- Manual CSV ingestion: `nse_block_deals` reads any real NSE bulk/block CSV files placed in
  `data/block_deals/` (the standard NSE export format - columns: Date, Symbol, Security Name,
  Client Name, Buy/Sell, Quantity Traded, Trade Price / Wght. Avg. Price). It reuses the
  existing `_normalize_row` / `parse_deals_payload` logic. Missing folder -> no rows (no error).
- Static-archive ingestion: add a fetch of
  `https://archives.nseindia.com/content/equities/bulk.csv` and `.../block.csv` (these are NOT
  bot-protected and return real recent deals; verified 2026-06-03). Cache per fetch day.
- Source precedence and honesty: prefer manual CSV (deepest history) > static archive (recent)
  > dynamic API (best-effort). If the combined real data has fewer than the minimum events,
  `blockdeal_eval` REPORTS "DATA UNAVAILABLE" with the real counts - it must NOT fabricate deals
  or fall back to synthetic data.
- `blockdeal_eval` runs the buy/sell event study (forward 5-day return, win rate, cost-adjusted
  edge, max adverse move, IS vs OOS, monthly stability, walk-forward) ONLY when enough real
  events exist; otherwise it returns DATA UNAVAILABLE through research_automation.
- (Perf) ingest each archive/CSV once and filter all symbols together (the delivery_eval lesson).
- All existing block-deal tests still pass; new tests cover CSV parsing and the data-unavailable
  path with deterministic fixtures (no network).

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
- python -m pytest tests/test_nse_block_deals.py tests/test_blockdeal_eval.py
- python -m bot.blockdeal_eval --top 0 --no-workflow
- python -c "from workflow.research_automation import check_deployment_gate; raise SystemExit(0 if check_deployment_gate() != 0 else 1)"

## Expected Output
- `nse_block_deals` returns real deals from manual CSVs and/or the static archive; the dynamic
  API remains best-effort only.
- `blockdeal_eval` either runs the event study on real data or reports DATA UNAVAILABLE with
  honest counts; the result is classified and logged via research_automation.
- workflow/deployment_gate.json remains blocking (no deployment from a research module).
- AUDIT_REPORT.md updated by the orchestrator once real block-deal history is available.

## Out of Scope (do NOT do in this task)
- No trading strategy, no position sizing, no entry/exit logic.
- No live trading, no trust-table wiring, no dashboard changes.
- No paid data integrations; no synthetic/fabricated deals to fill missing history.
- Do not attempt to defeat NSE bot-protection beyond the existing best-effort session warmup.
