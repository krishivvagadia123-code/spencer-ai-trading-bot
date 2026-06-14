# Task: Daily data-integrity auditor + SPNCR-003 readiness report

## Objective
The data clock (`SpencerDailySnapshot`, 18:00 IST) now runs UNSUPERVISED every
market day. Build a read-only auditor that verifies its output is honest and
intact, and that reports when the dataset is deep enough for the next research
candidate. No strategy logic, no candidate, no writes to journals.

## Context
- Tables in `kite_bot.db`: `daily_prices` (EOD), `intraday_prices` (15m/1m,
  final-candles-only), plus `backtest_runs` / `backtest_kills`.
- Conventions already enforced by the collectors (don't re-implement, VERIFY):
  session date derived from quote timestamp in IST; no candle stored unless
  boundary-aligned AND its window elapsed; weekends/holidays skipped honestly;
  EOD refused before 15:30 IST. Holidays: `bot/holidays.py`.
- The auditor must be paper-only and read-only; it never repairs data, it reports.

## Changes required

### 1. Auditor: `scripts/audit_data_integrity.py`
Read-only checks, each PASS/FAIL/WARN with the offending rows listed:
- **No duplicates:** unique (symbol, trade_date) in daily_prices; unique
  (symbol, interval, ts) in intraday_prices.
- **All candles final:** every intraday ts is on the interval grid (minute %
  interval == 0, seconds == 0). Report any off-grid rows.
- **No fabricated sessions:** no daily_prices or intraday rows fall on an NSE
  weekend/holiday.
- **EOD finality:** every daily_prices row's quote_timestamp is at/after 15:30
  IST for its session.
- **Session-date consistency:** each intraday ts's IST date matches the session
  it is grouped under; flag any UTC/round-trip drift.
- **Gap report (WARN only, never FAIL):** trading sessions in the covered range
  with < 70% of expected candles, listed explicitly (no smoothing).
- **Monotonic freshness:** max(daily_prices.trade_date) is the most recent
  completed trading day or older (never a future date).

### 2. Readiness signal
- Print a `RESEARCH READINESS` block: distinct 15m sessions, distinct 1m
  sessions, and a READY / NOT-READY verdict against a threshold constant
  `SPNCR3_MIN_15M_SESSIONS = 70` (documented, single source). NOT-READY shows
  how many sessions remain.
- `--json` flag emits the full report as JSON for the manager / dashboard.

### 3. Exit code
- Exit non-zero if ANY integrity check FAILs (duplicates, off-grid candles,
  fabricated sessions, EOD-finality, session-date drift, future dates).
  Gap WARNs and NOT-READY do NOT fail the run.

### 4. Tests (synthetic temp DB)
- Clean dataset passes, exit 0.
- Each failure class is detected: a seeded duplicate, an off-grid candle, a
  weekend row, a pre-15:30 EOD row, a future-dated daily row.
- Gap WARN does not flip exit code.
- Readiness flips READY at the threshold and reports the remaining count below it.

## Safety Rules (unchanged, mandatory)
- Paper-only; no live trading; no broker execution; no AI order approval.
- READ-ONLY over all tables — the auditor must never INSERT/UPDATE/DELETE.
- No fabricated data; report problems, never repair them.
- Deployment gate stays blocked.

## Test Commands
- .venv/Scripts/python.exe -m pytest tests/ -q
- .venv/Scripts/python.exe -m py_compile scripts/audit_data_integrity.py
- .venv/Scripts/python.exe scripts/audit_data_integrity.py   (run on the real DB; paste output)

## Expected Output
- Auditor + tests, full suite green, plus the real-DB report pasted back.
- Commit locally with a clear message; do NOT push — the manager reviews first.

## Out of Scope
- No data repair/backfill, no candidate or strategy logic, no schedule changes,
  no UI work, no new data sources.
