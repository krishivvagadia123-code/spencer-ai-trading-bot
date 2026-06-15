---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/research_news_sentiment_gdelt.md"
---
# research news sentiment gdelt

> Managed mirror of `workflow/tasks/research_news_sentiment_gdelt.md`. Edit the source file, not this copy.

# Task: GDELT news-sentiment predictive-power research (R&D)

## Objective
Build a READ-ONLY research module that ingests FREE, HISTORICAL news tone from GDELT for
NSE-listed companies and measures whether news-sentiment shocks predict forward returns, using
Spencer's existing event-study / IC framework. This is the next automated source because both
NSE event/flow APIs (block deals, FII/DII) are history-gated. Measure predictive power only —
do NOT build a trading strategy, do NOT deploy, do NOT wire live or trust-into-sizing.

## Context / Source Research Decision
- Module: flows_eval — Decision: DATA_UNAVAILABLE / NEEDS HISTORY (1 real row; NSE endpoint is
  current-day only). Module: blockdeal_eval — NEEDS MANUAL HISTORY. See AUDIT_REPORT.md §V, §W.
- Pivot: free NSE event/flow APIs have no historical backfill; GDELT is the remaining free source
  with real historical depth. DATA_SOURCE_RESEARCH_PLAN.md §1 flagged GDELT as the free path.
- HONEST EXPECTATION: this is R&D. The hard part is entity→NSE-symbol mapping and news noise;
  treat a null result as likely and report it plainly. Do not overclaim.

## Files Affected
- bot/gdelt_news.py           (new — GDELT GKG/tone ingestion + cache, None/empty on failure)
- bot/news_sentiment_eval.py  (new — read-only event study, news-shock vs forward returns)
- tests/test_news_sentiment_eval.py (new — deterministic, offline tests with fixtures)
- workflow/research_automation.py (register "news_sentiment_eval" in MODULE_FILES / MODULE_TESTS)
- workflow/tasks/research_news_sentiment_gdelt.md (this file)
- workflow/logs/

## Acceptance Criteria
- bot/gdelt_news.py fetches GDELT tone/volume for a mapped set of NSE companies over a multi-year
  window (GDELT 2.0 DOC/GKG free endpoints or CSV exports), with retry + cache, returning a clean
  DataFrame (date, symbol, tone, article_count) or None. Never fabricates articles or tone.
- Maintain an explicit, auditable company→symbol map (name/aliases → NSE symbol) for Nifty-50
  first; document mapping limitations honestly. Unmapped/ambiguous entities are skipped, not guessed.
- bot/news_sentiment_eval.py runs an event study on news-sentiment shocks (e.g. daily tone z-score
  beyond a threshold, and tone × article-volume): forward 5-day return, win rate, cost-adjusted
  edge (~0.25% hurdle), max adverse move, IS vs OOS, monthly stability, walk-forward. Control for
  overlap with earnings/gaps (confounding). Read-only — no entries/exits/sizing.
- Honest verdict: "usable" only with a stable sign across IS/OOS AND a cost-clearing edge AND
  walk-forward survival. Report DATA_UNAVAILABLE if mapping/fetch yields too few events. No fabrication.
- (Perf) one-pass ingest; cache the tone series once. Reuse spearman_ic / quintile_spread / event
  metrics from existing modules.
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
- python -m py_compile bot/gdelt_news.py bot/news_sentiment_eval.py
- python -m pytest tests/test_news_sentiment_eval.py
- python -m bot.news_sentiment_eval --no-workflow
- python -c "from workflow.research_automation import check_deployment_gate; raise SystemExit(0 if check_deployment_gate() != 0 else 1)"

## Expected Output
- A read-only news-sentiment event-study report (events, win rate, forward/cost-adjusted return,
  max adverse move, IS vs OOS, monthly stability, walk-forward) printed and logged.
- A research decision (PASS / FAIL / NEEDS CONFIRMATION / DATA_UNAVAILABLE) written to
  workflow/logs/ and the task status sidecar updated.
- workflow/deployment_gate.json remains blocking (no deployment from a research module).
- AUDIT_REPORT.md updated by the orchestrator with the news-sentiment result.

## Out of Scope (do NOT do in this task)
- No trading strategy, no position sizing, no entry/exit logic. No deployment.
- No live trading, no trust-table wiring, no dashboard changes.
- No paid news/sentiment APIs; no synthetic/fabricated articles or tone to fill gaps.
- Do not claim alpha from news unless it survives the full out-of-sample + walk-forward bar.
