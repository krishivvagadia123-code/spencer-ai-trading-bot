# Candidate SPNCR-001 — ARCHIVED (KILLED at IN_SAMPLE, 2026-06-12)

Filled per `CANDIDATE_TEMPLATE.md`. Machine definition: `candidates/SPNCR-001.json`
(hashes journaled in `backtest_runs`/`backtest_kills`). This form is archived and
must never be edited.

- **Candidate ID:** SPNCR-001 · **Version:** 1 · **Date written:** 2026-06-12
- **Hypothesis:** RELIANCE exhibits short-horizon intraday momentum persistence —
  close above 20-bar mean + two rising closes + above-average volume should
  continue by more than round-trip costs. Falsifiable; falsified (see verdict).
- **Timeframe:** 15m · **Data source:** `intraday_prices` (real Yahoo candles,
  final-candles-only, 2026-03-17..2026-06-11)
- **Entry (mechanical):** close > rolling mean(close, 20) AND close > close[-1]
  AND close[-1] > close[-2] AND volume > rolling mean(volume, 20)
- **Exit (mechanical):** close < rolling mean(close, 20) · **Stop:** fixed 0.5%
  below entry fill · **Sizing:** max affordable from ₹5,000 (≈3 shares)
- **No-trade conditions:** none beyond engine built-ins (one position max,
  session-end square-off, RELIANCE only)
- **Execution:** fill at next candle open · **Slippage:** paper engine model ·
  **Costs:** `bot/charges.py` (see docs/RELIANCE_COST_MATH.md)
- **Parameters (fixed, none tunable):** ma_window=20 (10–40; ≈5 trading hours),
  momentum_bars=2 (1–3), stop_pct=0.005 (0.003–0.01), vol_window=20 (10–40)
- **Pre-registered splits:** IS 2026-03-17→05-15 · OOS 2026-05-18→06-05 ·
  WF [03-17→04-15, 04-16→05-15, 05-18→06-11] (`candidates/SPNCR-001.splits.json`)
- **Kill acknowledgment:** I acknowledge this candidate dies permanently if it
  fails any stage of RESEARCH_PROTOCOL.md. Author: Claude Code (manager). 2026-06-12.

## Verdict — KILLED at IN_SAMPLE

| Metric | Value |
|---|---|
| Trades | 28 |
| Gross P&L | +₹78.03 |
| Total costs (charges+slippage) | ₹239.93 |
| **Net P&L** | **−₹45.53** |
| Net edge per trade | −0.039% of notional |
| Cost bar required | +0.618% |
| Max drawdown | ₹169.57 |

**Kill reason (protocol §4):** profitable before costs, not after costs. The
signal had weak positive gross content but churned 28 small trades whose
~0.21% real round-trip cost (slippage-dominated) consumed it entirely.

**Audit note:** the first ladder run of this candidate produced an invalid
0-trade FAIL caused by a harness defect (rolling operand shadowed by its
"field" key — fixed with regression test the same day). That false kill was
voided; the verdict above is from the corrected engine.

**Lesson for future candidates (not a parameter tweak — a new hypothesis is
required):** at ₹5,000 size, slippage+charges ≈ 0.2%+ per round trip; viable
candidates need fewer trades capturing larger moves (≥0.6% per trade), not
frequent small-momentum entries.
