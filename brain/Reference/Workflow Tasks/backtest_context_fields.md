---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/backtest_context_fields.md"
---
# backtest context fields

> Managed mirror of `workflow/tasks/backtest_context_fields.md`. Edit the source file, not this copy.

# Task: Candidate-agnostic context fields for the backtest engine

## Objective
Extend the backtest engine's rule vocabulary with precomputed, strictly
backward-looking per-candle CONTEXT FIELDS so day-selection hypotheses (like the
planned SPNCR-003) become expressible. The rule language has comparisons but no
arithmetic, so derived quantities must be computed by the engine, not by rules.
NO candidate is defined in this task; the fields are generic infrastructure.

## Context
- Evidence memo: `docs/research/day_selection_evidence_2026-06-12.md` —
  volatility persistence is the best-documented day-selection basis; expiry
  days raise NSE spot volatility; gap-continuation is unsupported.
- Engine: `bot/intraday_backtest.py` (`_operand_value`, `Candle`); holidays in
  `bot/holidays.py`. Rolling-operand ordering bug history: see commit 418c146 —
  keep operand resolution order explicit and tested.

## Changes required

### 1. Context computation (engine-side, strictly past-only)
At replay time, for each candle compute (from candles strictly BEFORE the
current session, or earlier in the current session, never future):
- `prev_session_range_pct`: previous session's (high-low)/close * 100.
- `prev_session_close`: previous session's last candle close.
- `gap_pct`: (current session's first candle open - prev_session_close) /
  prev_session_close * 100. Constant for all candles of a session.
- `session_minute`: minutes since 09:15 for the candle's session (0 = first).
- `is_expiry_session`: 1.0 on the NSE monthly F&O expiry session (last Thursday
  of the month, shifted to the prior trading day when it is a holiday — reuse
  `bot/holidays.py`; document the rule), else 0.0.
- First session in a dataset has NaN prev/gap fields; rules referencing NaN
  evaluate False (existing NaN semantics) — no fabricated values.

### 2. Rule operand
- New operand `{"context": "<field>"}` resolving to the current candle's
  context value. Resolution order documented and placed before generic field
  handling; unknown context names raise.
- `research_candidates.py`: allow the `context` key (not forbidden), and add
  the allowed field names to validation so typos fail at load time.

### 3. Tests (synthetic candles, temp DB)
- prev_session_range_pct/gap_pct computed correctly across a session boundary;
  constant within a session; NaN on the first session (rule evaluates False).
- session_minute correct at 09:15 (0) and 15:15 (360) for 15m candles.
- is_expiry_session: a known monthly expiry date returns 1.0, the prior day
  0.0, and a holiday-shifted expiry case documented + tested.
- No look-ahead: context for candle N must be identical whether or not candles
  after N exist in the dataset (regression-style equality test).
- Reproducibility hash unchanged for existing candidates (no context refs).

## Safety Rules (unchanged, mandatory)
- Paper-only; no live trading; no broker execution; no AI order approval.
- Strictly backward-looking computation; NaN over fabrication; deployment gate
  stays blocked; never write to the live trades journal.

## Test Commands
- .venv/Scripts/python.exe -m pytest tests/ -q
- .venv/Scripts/python.exe -m py_compile bot/intraday_backtest.py bot/research_candidates.py

## Expected Output
- Context fields + operand + validation + tests, full suite green.
- No candidate defined, no real-data run. Commit locally; do NOT push.

## Out of Scope
- No strategy/candidate logic, no parameter suggestions, no UI work, no new
  data sources, no changes to stored tables.
