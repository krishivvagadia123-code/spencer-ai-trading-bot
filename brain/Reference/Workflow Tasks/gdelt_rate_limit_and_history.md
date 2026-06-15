---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/gdelt_rate_limit_and_history.md"
---
# gdelt rate limit and history

> Managed mirror of `workflow/tasks/gdelt_rate_limit_and_history.md`. Edit the source file, not this copy.

# Task: Make GDELT ingestion rate-limit-safe + confirm historical coverage

## Objective
Fix the GDELT news ingestion so it stops hitting HTTP 429 (Too Many Requests) and can actually
collect real tone/volume history. Then determine whether the GDELT DOC API has enough historical
depth for an event study, or whether a GKG/BigQuery backfill is required. READ-ONLY research
plumbing only: no strategy, no orders, no deployment, no live, no trust wiring, no fabrication.

## Context / Source Research Decision
- Module: news_sentiment_eval — Decision: DATA_UNAVAILABLE. Root cause diagnosed by the
  orchestrator: **GDELT DOC API rate-limiting (HTTP 429)**. The eval bursts ~100 requests
  (50 symbols × tone+volume) with `retries=1` and no inter-request pacing/backoff, so it gets
  throttled and most companies return None. A direct 2-year RELIANCE query (heavily covered)
  returned empty under throttle. NOT mapping, NOT coverage, NOT cache, NOT date-range, NOT
  symbol mismatch. Secondary unconfirmed: DOC 2.0 may be ~3-month coverage-limited. See
  AUDIT_REPORT.md §X and DATA_SOURCE_RESEARCH_PLAN.md §1.

## Files Affected
- bot/gdelt_news.py            (add rate-limit handling; coverage probe helper)
- bot/news_sentiment_eval.py   (consume throttled fetch; honest DATA_UNAVAILABLE with reason)
- tests/test_gdelt_news.py     (new — offline tests: backoff logic, 429 handling, parsing)
- tests/test_news_sentiment_eval.py (extend — rate-limited / partial-coverage paths)
- workflow/tasks/gdelt_rate_limit_and_history.md (this file)
- workflow/logs/

## Acceptance Criteria
- Rate-limit safety: GDELT fetches use (a) a minimum inter-request delay (e.g. ≥5s, configurable),
  (b) exponential backoff with retries on HTTP 429/503 (honor `Retry-After` if present), and
  (c) a persistent cache so a re-run does NOT re-fetch already-cached (symbol, mode, window). The
  module must never burst the API. A run over Nifty-50 must complete without being fully throttled.
- Coverage probe: add a helper that, for 2-3 well-covered symbols (e.g. RELIANCE, TCS, INFY),
  reports how far back the DOC API actually returns dated tone points (e.g. test 30-day windows
  at now, −6mo, −1y, −2y). Print/log the real historical depth — no guessing.
- Honest classification: if, after throttling is fixed, usable observations are still
  < MIN_OBSERVATIONS because the DOC API is coverage-limited, `news_sentiment_eval` reports
  DATA_UNAVAILABLE **with the measured coverage depth**, and the orchestrator decides whether to
  (i) add a GKG/BigQuery historical backfill, or (ii) mark GDELT structurally unsuitable and pivot.
- No fabrication: only real GDELT rows; never synthesize tone/articles to reach thresholds.
- (Perf) one fetch per (symbol, mode, window), cached; reuse spearman_ic / event metrics.
- Calls workflow/research_automation finalize hooks; deployment gate stays blocking.

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
- python -m pytest tests/test_gdelt_news.py tests/test_news_sentiment_eval.py
- python -m bot.news_sentiment_eval --no-workflow
- python -c "from workflow.research_automation import check_deployment_gate; raise SystemExit(0 if check_deployment_gate() != 0 else 1)"

## Expected Output
- A GDELT run that completes without being throttled out, plus a printed/logged coverage-depth
  report for the probe symbols.
- A research decision (PASS / FAIL / NEEDS CONFIRMATION / DATA_UNAVAILABLE) — with the REAL
  reason (rate-limit fixed → measured coverage) — written to workflow/logs/ and the task status sidecar.
- workflow/deployment_gate.json remains blocking (no deployment from a research module).
- AUDIT_REPORT.md updated by the orchestrator with the rate-limit-fixed GDELT result.

## Out of Scope (do NOT do in this task)
- No trading strategy, no sizing, no entry/exit logic. No deployment.
- No live trading, no trust-table wiring, no dashboard changes.
- No paid news APIs; no synthetic/fabricated tone or articles.
- Do not aggressively hammer GDELT to defeat throttling — pace requests politely.
