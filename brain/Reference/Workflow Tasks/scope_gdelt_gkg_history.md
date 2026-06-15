---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/scope_gdelt_gkg_history.md"
---
# scope gdelt gkg history

> Managed mirror of `workflow/tasks/scope_gdelt_gkg_history.md`. Edit the source file, not this copy.

# Task: Scope GDELT GKG historical news ingestion (BigQuery / bulk CSV)

## Objective
SCOPE (feasibility-first, then a small proof) how to obtain MULTI-YEAR historical news tone for
NSE companies, because the GDELT DOC 2.0 API is recent-only (~3 months) and cannot support a
backtest. Evaluate GDELT GKG via (a) BigQuery and (b) free bulk GKG CSV files. Do NOT build the
full pipeline yet, do NOT build a strategy, do NOT deploy, keep Spencer paper-only, no fabrication.

## Context / Source Research Decision
- Module: news_sentiment_eval / gdelt_news — Decision: NEEDS_GKG_BIGQUERY_OR_BULK_DATA. The
  rate-limit fix works (5s delay, backoff, Retry-After, cache-first; 15 tests pass), but the
  coverage probe shows DOC returns recent windows only (current/−6mo have data; −1y/−2y do not).
  Do NOT keep hammering the DOC API for history. See AUDIT_REPORT.md §X, §Y;
  DATA_SOURCE_RESEARCH_PLAN.md §1.

## Deliverable: a scoping note (not a full build)
Produce `docs/gdelt_gkg_scope.md` comparing the two GKG paths on:
- **Access:** what credentials/setup each needs (BigQuery = GCP project + auth; bulk CSV = plain
  HTTP download of GDELT GKG master file list, no auth).
- **History depth:** earliest available date for India/English GKG tone (GKG 2.0 ≈ 2015+).
- **Cost:** BigQuery query/storage cost vs bulk-CSV download volume (GKG is very large — estimate
  GB/day and total for a 2-3y NSE-filtered slice). Free vs paid clearly stated.
- **Entity mapping:** how GKG `V2Organizations` / themes map to the existing auditable
  `NSE_COMPANY_MAP`; expected noise.
- **Recommendation:** which path Spencer should use first, with a concrete next build task.

## Acceptance Criteria
- `docs/gdelt_gkg_scope.md` written with the comparison above and a clear recommendation.
- A SMALL real proof-of-coverage (read-only, no fabrication): fetch GKG tone for 1-2 symbols
  (e.g. RELIANCE) for a single historical month (e.g. a month ~1-2 years ago) via whichever path
  is free/zero-auth (bulk CSV is preferred for the proof), and show it returns real dated rows
  that the DOC API could not. If neither path is reachable in this environment, report that
  honestly with the exact blocker (auth/cost/volume) — do NOT synthesize data.
- No full ingestion pipeline, no strategy, no deployment. Mind disk space (host is near-full) —
  do not download the entire GKG corpus; sample a tiny slice only.

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
- python -m py_compile bot/gdelt_news.py
- python -m pytest tests/test_gdelt_news.py
- python -c "from workflow.research_automation import check_deployment_gate; raise SystemExit(0 if check_deployment_gate() != 0 else 1)"

## Expected Output
- `docs/gdelt_gkg_scope.md` with the access/depth/cost/mapping comparison + recommendation.
- A tiny real proof-of-coverage (or an honest blocker report), logged.
- workflow/deployment_gate.json remains blocking (no deployment from a scoping task).
- AUDIT_REPORT.md updated by the orchestrator with the scoping outcome + chosen next build.

## Out of Scope (do NOT do in this task)
- No full GKG ingestion pipeline, no strategy, no sizing, no deployment.
- No downloading the entire GKG corpus (disk is near-full; sample a tiny slice).
- No paid commitments without surfacing the cost in the scope note first.
- No synthetic/fabricated tone or articles to stand in for missing history.
