---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/intraday_backtest_harness.md"
---
# intraday backtest harness

> Managed mirror of `workflow/tasks/intraday_backtest_harness.md`. Edit the source file, not this copy.

# Task: Intraday backtest harness — mechanical executor of RESEARCH_PROTOCOL.md

## Objective
Build the engine that tests candidate techniques exactly as `RESEARCH_PROTOCOL.md`
demands: real candles in, mechanical rules applied, all costs and slippage charged,
in-sample / out-of-sample / walk-forward stages, results journaled and reproducible.
NO candidate technique is defined in this task — the harness must be
candidate-agnostic. The manager defines candidates separately.

## Context
- Data: `intraday_prices` (15m ≈ 58 sessions and growing daily; 1m ≈ 7 days) and
  `daily_prices`, both real, append-only, final-candles-only (commit a8fe193).
- Costs: `bot/charges.py` (the same model the paper engine uses). Slippage model:
  reuse the paper engine's existing slippage assumptions — do not invent a new one.
- Capital: fixed ₹5,000 basis; max one open position; RELIANCE only.
- The protocol bans: parameter changes after in-sample, quoting gross-only results,
  invented fills, subjective rules. The harness must make these violations
  impossible, not just discouraged.

## Changes required

### 1. Candidate interface: `bot/research_candidates.py`
- A candidate is a frozen, declarative rule set (dataclass or dict validated by
  schema): id, version, written hypothesis, interval, entry rule, exit rule,
  stop rule, sizing rule, no-trade conditions, execution assumption
  (fills at next candle open after a signal — never the signal candle's close),
  parameter values. Rules are expressed over candle/indicator values only —
  no callbacks that could smuggle in look-ahead or human judgment.
- Validation rejects: missing fields, non-RELIANCE symbols, >1 position,
  capital ≠ 5000, any rule referencing future candles.

### 2. Backtest engine: `bot/intraday_backtest.py`
- Replays stored real candles strictly forward; indicators computed only from
  candles at or before the decision point (enforce: engine feeds the rule
  evaluator a window that physically excludes future rows).
- Fills at next candle open + slippage; every trade charged via
  `calculate_charges` (INTRADAY product); forced square-off at session end
  (no overnight positions for intraday candidates).
- Outputs per run: trade list (each with entry/exit ts+price, qty, gross,
  charges, slippage, net), equity curve points, summary (trades, win count,
  gross P&L, total costs, net P&L, max drawdown, net edge per trade in % of
  notional, cost-bar check = net edge ≥ 3× round-trip cost), dataset range,
  data row count, candidate id+version+params hash.
- Results persisted append-only to a `backtest_runs` table (or JSON under
  `workflow/logs/backtests/`) with stage label IN_SAMPLE / OUT_OF_SAMPLE /
  WALK_FORWARD — reruns with identical inputs must reproduce identical outputs.

### 3. Stage runner: `scripts/run_testing_ladder.py`
- Given a candidate file and a date split config: runs IN_SAMPLE; only if it
  passes (net positive AND cost bar met) unlocks OUT_OF_SAMPLE on the held-out
  range; only then WALK_FORWARD (rolling re-fit windows if the candidate has
  tunable params; params chosen only from past windows).
- Prints an honest verdict per stage: PASS / FAIL / DATA_INSUFFICIENT (e.g.
  1m history too short). A FAIL stops the ladder and records the kill.
- Hard-wired refusals: refuses to rerun a killed candidate id with changed
  params unless the candidate file carries a new version + new hypothesis text.

### 4. Tests
- Synthetic-candle unit tests for the engine mechanics are allowed in tests ONLY
  (clearly named, temp DB) — they verify: no look-ahead (a rule referencing the
  future raises), fills at next open, charges+slippage always applied, session-end
  square-off, reproducibility (same input → same output hash), cost-bar math,
  ladder gating (OOS locked until IS passes), killed-candidate refusal.
- Full suite must stay green.

## Safety Rules (unchanged, mandatory)
- Paper-only; no live trading; no broker order placement; no AI order approval.
- The harness must never write to the live paper account or `trades` journal —
  backtest results live in their own table/files.
- No fabricated candles outside test fixtures; no results quoted without costs.
- Deployment gate stays blocked regardless of backtest outcomes.

## Test Commands
- .venv/Scripts/python.exe -m pytest tests/ -q
- .venv/Scripts/python.exe -m py_compile bot/intraday_backtest.py bot/research_candidates.py scripts/run_testing_ladder.py

## Expected Output
- Candidate interface + engine + ladder runner + tests, all green.
- No candidate defined, no run executed on real data yet (the manager supplies
  candidate 001 after review).
- Commit locally with a clear message; do NOT push (manager reviews first).

## Out of Scope
- No candidate/strategy definitions, no parameter suggestions, no live data
  fetching changes, no UI work, no deployment.
