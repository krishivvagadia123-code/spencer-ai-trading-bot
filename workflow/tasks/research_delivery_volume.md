# Task: Delivery-volume predictive-power research module

## Objective
Build a READ-ONLY research module that ingests NSE daily delivery-volume data (deliverable
quantity and delivery %) and measures whether it predicts forward returns, using Spencer's
existing information-coefficient / event-study framework. This is the first non-price data
source after seven price/event tests found no edge. Measure predictive power only — do NOT
build a trading strategy, do NOT deploy, do NOT wire live or trust-into-sizing.

## Context / Source Research Decision
- Module: gapup_confirm — Decision: KILLED (gap_up was a recent-bull-market artifact; failed
  Nifty-50 over 8y with realistic slippage). See AUDIT_REPORT.md sections N–R.
- Pivot: DATA_SOURCE_RESEARCH_PLAN.md selects delivery volume % as the first new data source
  (free, per-stock, genuinely non-price, plugs into the IC framework).

## Files Affected
- bot/nse_delivery.py        (new — robust NSE delivery-data ingestion + local cache)
- bot/delivery_eval.py       (new — read-only IC research, mirrors bot/feature_eval.py)
- tests/test_delivery_eval.py (new — deterministic, offline tests)
- workflow/research_automation.py (register "delivery_eval" in MODULE_FILES / MODULE_TESTS)
- workflow/tasks/research_delivery_volume.md (this file)
- workflow/logs/

## Acceptance Criteria
- bot/nse_delivery.py fetches per-symbol daily `deliverable_qty` and `delivery_pct` from NSE
  public archives (e.g. sec_bhavdata_full), with retry + on-disk cache, and returns a clean
  DataFrame indexed by date. On failure it returns None and the caller skips the symbol
  (never fabricates values).
- If NSE history is not reliably fetchable, the module REPORTS the data limitation honestly
  (like the news limitation in event_eval) instead of inventing data.
- bot/delivery_eval.py computes causal features: `delivery_pct`, `delivery_pct_zscore` (20d),
  `delivery_spike` (high delivery % AND above-average volume), and runs the SAME framework:
  IC in-sample vs out-of-sample, quintile spread, cost-adjusted edge (~0.25% hurdle), monthly
  stability, and walk-forward survival, vs 5-day forward returns. Nifty-50 first; Midcap-100
  if data permits.
- The module calls workflow/research_automation finalize hooks (add_research_workflow_args /
  finalize_from_args / print_research_workflow_summary) like the existing eval modules, so the
  result is classified PASS / FAIL / NEEDS CONFIRMATION and logged.
- Verdict logic is honest: "usable" requires stable IC sign across IS/OOS AND a cost-clearing
  quintile spread AND walk-forward survival. No feature is called promising on a boundary.

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
- python -m py_compile bot/nse_delivery.py bot/delivery_eval.py
- python -m pytest tests/test_delivery_eval.py
- python -c "from workflow.research_automation import check_deployment_gate; raise SystemExit(0 if check_deployment_gate() != 0 else 1)"

## Expected Output
- A read-only delivery-volume IC report (events/observations, IC IS vs OOS, quintile spread,
  cost-adjusted edge, monthly stability, walk-forward survival) printed and logged.
- A research decision (PASS / FAIL / NEEDS CONFIRMATION) written to workflow/logs/ and the
  task status sidecar updated.
- workflow/deployment_gate.json remains blocking (no deployment from a research module).
- AUDIT_REPORT.md updated by the orchestrator with the delivery-volume result.

## Out of Scope (do NOT do in this task)
- No trading strategy, no position sizing, no entry/exit logic.
- No live trading, no trust-table wiring, no dashboard changes.
- No paid data integrations (delivery data is free from NSE).
