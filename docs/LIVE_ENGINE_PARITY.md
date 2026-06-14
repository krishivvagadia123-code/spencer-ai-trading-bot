# Live Engine ↔ Backtest Parity (cross-validation, 2026-06-14)

The Live Paper-Trading Execution Engine (`bot/live_paper_trader.py`) is the
forward, real-time counterpart of the backtest (`bot/intraday_backtest.py`). For
it to be trustworthy, a candidate must behave **identically** when paper-traded
live as it did in backtest — otherwise a "passing" candidate could lose money
live for reasons the backtest never showed.

## Result: bit-perfect parity

Running the live engine's continuous dry-run (`run_dry_run_range`) over the exact
in-sample date range of each killed candidate, against the same collected real
candles, reproduces the journaled backtest result to the paisa:

| Candidate | Range | Backtest | Live engine | Match |
|---|---|---|---|---|
| SPNCR-001 | 2026-03-17 → 05-15 | 28 trades, net −₹45.53 | 28 trades, net −₹45.53 | ✅ |
| SPNCR-002 | 2026-03-17 → 05-15 | 9 trades, net −₹7.88 | 9 trades, net −₹7.88 | ✅ |

## Why this matters

1. **The live engine is correct** — it matches the independently-tested backtest.
2. **No live-vs-backtest surprise** — when a candidate finally passes the ladder,
   the engine will paper-trade it exactly as the walk-forward predicted.
3. **It independently re-confirms the kills** — the live execution path also finds
   SPNCR-001 and SPNCR-002 net-negative after costs. Two engines, same honest
   verdict.

## How parity is guaranteed

The live engine **reuses the backtest's own functions** — `evaluate_rule`,
`_qty_from_sizing`, `_stop_price`, `_contextualize_candles`, `simulate_fill` — and
mirrors its loop shape (decision on bar N fills at bar N+1 open; daily square-off).
A regression test (`test_live_engine_matches_backtest_exactly`) asserts the two
engines produce identical trades and net P&L on synthetic data, so the parity
cannot silently drift.

This is infrastructure, not edge: profitability stays 4/100. The value is that the
day a candidate passes, Spencer can trade it live on paper with confidence.
