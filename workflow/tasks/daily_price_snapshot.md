# Task: Daily automatic price snapshot — RELIANCE EOD, scheduled, append-only

## Objective
Keep stock prices updated daily and automatically: every market day after NSE close,
fetch the real RELIANCE end-of-day quote and append it to a local price history table,
with zero manual steps. This builds the honest local price history Spencer needs for
RELIANCE mastery analysis. Paper-only; no broker; no fabrication.

## Context
- Real quote path already exists in `spencer_quote_server.py` (`_quote_rows`,
  Yahoo intraday/last-close with timestamps + market-state labels).
- Account epoch `one_stock_reliance_v1` is live (basis ₹5,000, RELIANCE-only).
- Host is Windows 11; scheduling must use Windows Task Scheduler (`schtasks`).

## Changes required

### 1. Snapshot script: `scripts/daily_price_snapshot.py`
- Fetches the RELIANCE quote via the existing quote-server code path (import the
  module; do NOT duplicate fetch logic).
- Appends one row per (symbol, trade_date) into a new `daily_prices` table in
  `kite_bot.db`: symbol, trade_date, close, prev_close, change_pct, quote_timestamp,
  fetched_at, source, market_state. UNIQUE(symbol, trade_date).
- Idempotent: re-running on the same day updates nothing and exits 0 with a clear
  "already snapshotted" message. Never overwrites an existing row.
- If no real quote is available (API down), log the failure honestly to
  `workflow/logs/price_snapshot.log` and exit non-zero. NEVER write a guessed price.
- Skips NSE holidays/weekends gracefully (no row, honest log line).
- Symbols come from the configured universe (currently ["RELIANCE"]) — do not hardcode
  a wider list.

### 2. Scheduling
- Add `scripts/register_daily_snapshot.ps1` that registers a Windows scheduled task
  "SpencerDailySnapshot" running the script via the project venv python daily at
  18:00 IST (after NSE close + Yahoo EOD settle). Print clear confirmation.
- Registering the task is an operator action: the script must only be run manually;
  do not auto-register during tests or imports.

### 3. Dashboard surfacing (small)
- `/api/...` price payloads may include `lastSnapshotDate` so the UI can show
  "EOD history up to YYYY-MM-DD". Optional; keep minimal.

### 4. Tests
- Snapshot writes exactly one row per symbol/date (temp DB).
- Re-run same day = no duplicate, exit 0.
- API-failure path writes no row and exits non-zero (mock the quote function).
- No symbol outside the configured universe is snapshotted.

## Safety Rules (unchanged, mandatory)
- Paper-only; no live trading; no broker order placement; no AI order approval.
- No fabricated prices — failure states stay failures.
- Append-only history; never delete or rewrite journal/price rows.
- Deployment gate stays blocked.

## Test Commands
- .venv/Scripts/python.exe -m pytest tests/ -q
- .venv/Scripts/python.exe -m py_compile scripts/daily_price_snapshot.py

## Expected Output
- Script + scheduler registration + tests, all green.
- One real snapshot row written for today (run the script once manually, with a real
  quote, and show the row).
- Commit locally with a clear message; do NOT push (manager reviews first).

## Out of Scope
- No strategy logic, no signals, no backtests, no new data providers, no UI redesign.
