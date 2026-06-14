# Task: Live Paper-Trading Execution Engine (candidate-agnostic, gate-protected)

## Objective
Build the engine that runs an APPROVED candidate forward — on paper — during NSE
market hours, plus a dry-run mode that replays it against collected real candles.
This is the bridge from "Spencer can backtest" to "Spencer can trade RELIANCE on
paper, honestly journaled." Paper-only forever; never places a broker order.

## Design (matches the backtest exactly for parity)
- Module `bot/live_paper_trader.py`, a forward `LivePaperTrader` state machine.
- Reuses the backtest's own functions so live behaviour == backtest behaviour:
  `evaluate_rule`, `_qty_from_sizing`, `_stop_price`, `_contextualize_candles`,
  `load_candles`, `Candle`, `_same_session`, `simulate_fill`, `calculate_charges`.
- Pending-order model: a decision on bar N executes at bar N+1's OPEN (same as the
  backtest's "fill at next candle open"); stop detected on a bar's low, exit next
  open; forced square-off at the session's final bar / 15:25 IST at that bar close.
- One position max, ₹5,000 basis, RELIANCE only, INTRADAY product (no overnight).
- Context fields (gap_pct, prev_session_range_pct, is_expiry_session, …) computed
  live via the same contextualizer — candidates using `{"context": …}` work live.

## Safety gates (hard, non-negotiable)
- `assert_paper_only(db_path)`: reads `workflow/deployment_gate.json`; refuses to
  run unless paperOnly=true AND liveTradingAllowed=false AND brokerExecutionAllowed=false.
- `assert_candidate_passed(db_path, candidate)` (LIVE mode only): the candidate must
  have a journaled WALK_FORWARD `PASS` in `backtest_runs` AND must NOT appear in
  `backtest_kills`; otherwise refuse. (Correctly refuses today — no candidate has
  passed; both SPNCR-001/002 are KILLED.)
- No broker SDK import anywhere; only `simulate_fill` (paper). A grep test enforces it.
- Dry-run mode is a SIMULATION (no PASS gate) but is paper-only and clearly marked.

## Journaling (append-only, isolated)
- New tables only: `live_paper_runs`, `live_paper_trades`, `live_paper_decisions`.
- NEVER writes to the epoch `trades` table or any backtest table.
- Every decision journaled: entry signal, no-trade reason, exit signal, stop,
  session-end, and each simulated fill (price, qty, charges, slippage, net).

## Drivers + CLI
- `run_dry_run(candidate, db_path, session_date)`: seeds prior-session history for
  context, replays that session's candles, journals mode=DRY_RUN, returns summary.
- `run_live(...)`: market-hours loop — polls the quote server, aggregates 15m bars,
  feeds completed bars, squares off at 15:25. Gated by the PASS check.
- `scripts/run_live_paper.py --candidate <file> --mode dry-run|live [--date YYYY-MM-DD]`.

## Tests (`tests/test_live_paper_trader.py`)
- LIVE refuses a killed candidate and a never-passed candidate.
- Refuses if the deployment gate has liveTradingAllowed/brokerExecutionAllowed true.
- No broker/exchange SDK imported (grep test).
- State machine: entry fills at next bar open; stop exit; rule exit; forced
  session-end square-off; max one position; charges+slippage applied; deterministic.
- Dry-run journals to live_paper_* only and leaves the epoch `trades` table untouched.
- A candidate using a `{"context": …}` rule evaluates live.

## Out of scope
- No real broker, no live money, no schedule registration (operator decides),
  no UI (manager wires the dashboard separately), no new research candidate.
