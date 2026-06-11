# Task: One-stock mastery reset — RELIANCE only, ₹5,000 capital, zero fake data paths

## Objective
Reset Spencer to its true concept: ONE stock (RELIANCE), ONE open position max,
₹5,000 total paper capital, and physically remove every code path that can produce
synthetic/fake market data. Paper-only stays enforced; deployment gate stays blocked.

## Context
- The journal (`kite_bot.db`) holds 3 stale open paper positions from 2026-05-27
  (POWERGRID, NESTLEIND, NHPC) opened under an old multi-position config.
- The dashboard mixes stats bases: total portfolio ~₹49,254 vs a ₹5,000 "budget",
  and shows P&L% computed against ₹5,000 while displaying the ₹49k portfolio.
- `backend/` contains a legacy Node simulation engine (synthetic prices) that must go.
- The real data path is `spencer_quote_server.py` (Yahoo/NSE real quotes) on :8787.

## Changes required

### 1. Delete the fake-data engine (hard removal, not deprecation)
- Delete `backend/engine/priceSimulator.js`, `backend/engine/botEngine.js`, and all
  imports/routes in `backend/server.js` that serve simulated bot state.
- If `backend/server.js` then serves nothing real, delete the whole Node backend and
  note it in the commit message. The frontend must talk ONLY to the Python quote server.
- Grep the frontend for any fallback to simulated/hardcoded values
  (`STOCK_BASES` seeds, hardcoded `confidence: 70/75/80` in
  `frontend/src/utils/constants.js`) — remove or replace with backend-fed values.
  Strategy "edge" marketing text must be labeled as descriptions, never as metrics.

### 2. One-stock mode
- `bot/config.py`: default config → `max_open_positions = 1`,
  `starting_balance = 5000.0`, universe/watchlist = `["RELIANCE"]` only.
- The scanner/paper engine must refuse symbols outside the configured universe.
- The crypto preset (`crypto_inr_config`) is unused for this concept — delete it or
  clearly mark it inactive so its `max_open_positions=3` can never leak in.

### 3. Honest journal reset (no deletion of history)
- Do NOT delete or rewrite journal rows. Close the 3 stale open positions with proper
  journaled SELL rows, exit_reason = `ONE_STOCK_RESET`, at the latest real quote
  available from the quote server (or last close). P&L recorded honestly.
- Then start a fresh paper account state: balance = ₹5,000.00. Keep prior rows as
  history; add a `bot_state` marker (e.g. `account_epoch = one_stock_reliance_v1`)
  so the dashboard reports stats from the reset onward.

### 4. One consistent stats basis
- Dashboard/API portfolio value, invested, free cash, P&L ₹ and P&L % must ALL derive
  from the ₹5,000 epoch and from journal rows only. No second basis anywhere.
- Every displayed price carries its timestamp and market state
  (`OPEN` / `CLOSED — as of HH:MM IST`). No bare "N/A" walls: show
  "awaiting first real quote" states explicitly.

### 5. Tests (must pass)
- Test: config default is RELIANCE-only, max 1 position, ₹5,000.
- Test: paper engine rejects a second concurrent position.
- Test: paper engine rejects any non-RELIANCE symbol.
- Test: no file in the repo imports or references `priceSimulator` (grep test).
- Test: portfolio stats derive from journal rows of the current epoch and basis
  equals 5000.0.
- Existing tests must not regress (known pre-existing debt documented in
  AUDIT_REPORT.md is exempt).

## Safety Rules (unchanged, mandatory)
- Paper-only. No live trading, no broker order placement, no broker SDK order calls.
- No AI order approval. Deployment gate stays blocked (`workflow/deployment_gate.json`).
- No fabricated prices, trades, P&L, holdings, or bot status — if real data is
  unavailable, display/return "unavailable", never a synthetic number.
- Do not delete journals or rewrite journal history.

## Test Commands
- python -m pytest tests/ -q
- python -m py_compile bot/config.py paper_engine.py spencer_quote_server.py
- grep -ri "priceSimulator\|generateNextBar" --include="*.js" --include="*.py" . (must be empty)

## Expected Output
- Legacy simulator gone; frontend wired only to real backend.
- Config: RELIANCE-only, 1 position, ₹5,000.
- Stale positions closed honestly; fresh ₹5,000 epoch started.
- Consistent stats + timestamped, market-state-labeled prices.
- All new tests passing. Commit the work with a clear message (no push without the
  operator's review).

## Out of Scope
- No strategy building, no signal changes, no deployment, no new data sources.
- No UI redesign (Antigravity owns visual design separately; keep markup hooks stable).
