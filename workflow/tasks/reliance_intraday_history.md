# Task: RELIANCE intraday history collector — real candles, append-only, forward-growing

## Objective
Build the data foundation for the RELIANCE mastery research. The cost analysis
(`docs/RELIANCE_COST_MATH.md`) showed intraday is the only cost-viable mode on
₹5,000 (breakeven ≈0.106% vs median daily range 1.70%), so technique research
needs real intraday candles. Collect what Yahoo legitimately provides and grow
the archive forward every day. Paper-only; no strategy logic in this task.

## Context
- Yahoo chart API provides ~60 days of 15-minute candles and ~7 days of 1-minute
  candles for RELIANCE.NS. That is the honest free ceiling — take it, label it,
  and extend it forward daily so depth accumulates over time.
- `daily_prices` (EOD) already exists with its scheduled 18:00 snapshot; this
  task adds intraday and must reuse the same conventions (append-only, session
  dates from candle timestamps in IST, honest failure states).

## Changes required

### 1. Collector: `scripts/intraday_history.py`
- New table `intraday_prices` in `kite_bot.db`: symbol, interval ("15m"/"1m"),
  ts (candle start, ISO IST), open, high, low, close, volume, source,
  fetched_at, created_at. UNIQUE(symbol, interval, ts).
- Backfill mode: fetch the full available window (60d×15m, 7d×1m) for the
  configured universe (currently ["RELIANCE"]); insert only missing candles.
- Idempotent: re-runs insert nothing new unless new candles exist.
- Candles with null OHLC are skipped, not filled. API failure → honest log to
  `workflow/logs/intraday_history.log`, exit non-zero, zero rows written.
- Session date always derived from the candle timestamp in IST — never the run
  date (same rule as the daily snapshot fix in commit 8648b62).

### 2. Scheduling
- Extend `scripts/register_daily_snapshot.ps1` (or add a sibling script) so the
  18:00 IST scheduled run executes BOTH the EOD snapshot and the intraday
  collector. Manual registration only.

### 3. Coverage report
- `scripts/intraday_history.py --report` prints honest coverage: per interval,
  first/last candle, number of sessions, gaps (sessions with <70% of expected
  candles listed explicitly). No smoothing over gaps.

### 4. Tests
- Backfill inserts candles; re-run inserts zero (temp DB, mocked fetch).
- Null-OHLC candles are skipped.
- API failure: no rows, non-zero exit, log line written.
- Candle timestamps map to correct IST session dates.
- Non-universe symbols are never collected.

## Safety Rules (unchanged, mandatory)
- Paper-only; no live trading; no broker order placement; no AI order approval.
- No fabricated or interpolated candles; gaps stay visible.
- Append-only; never delete or rewrite price rows.
- Deployment gate stays blocked; no strategy/signal code in this task.

## Test Commands
- .venv/Scripts/python.exe -m pytest tests/ -q
- .venv/Scripts/python.exe -m py_compile scripts/intraday_history.py

## Expected Output
- Real backfill executed once: show the coverage report for RELIANCE.
- All tests green (full suite, no regressions).
- Commit locally with a clear message; do NOT push (manager reviews first).

## Out of Scope
- No strategy, signals, indicators, or backtest logic (next task, after data).
- No paid data sources; no symbols beyond the configured universe.
