# Candidate SPNCR-003 — ARCHIVED (KILLED at IN_SAMPLE, 2026-06-24)

Filled per `CANDIDATE_TEMPLATE.md`. Machine definition: `candidates/SPNCR-003.json`.
Archived; never edited.

- **Candidate ID:** SPNCR-003 · **Version:** 1 · **Date written:** 2026-06-24
- **Hypothesis (new short-side, not a 001/002 tweak):** when RELIANCE opens with
  an up-gap of ≥0.3% vs the prior session close, the gap tends to FADE intraday
  rather than continue. The research scan over 64 real sessions found gap-up days
  averaged ≈ −0.40% intraday (t=−1.84, n=30) — directionally a fade. This
  candidate SHORTS near the open on a qualifying up-gap, holds to the 15:25
  square-off, with a wide 1% protective stop above entry. Falsified.
- **Timeframe:** 15m · **Data:** `intraday_prices` (real, final candles,
  2026-03-17..2026-06-23, 64 sessions)
- **Entry:** gap_pct ≥ 0.3 AND session_minute ≤ 15 (open) · **Side:** SHORT ·
  **Exit:** session square-off · **Stop:** fixed 1% above entry · **Sizing:**
  max affordable from ₹5,000 · **Execution:** next candle open + paper-engine
  slippage · **Costs:** bot/charges.py
- **Parameters (fixed, none tunable):** gap_up_threshold_pct=0.3,
  entry_window_minute=15, stop_pct=0.01
- **Pre-registered splits:** `candidates/SPNCR-003.splits.json`, written
  2026-06-24 BEFORE the run. In-sample 2026-03-17..2026-05-15.
- **Kill acknowledgment:** this candidate dies permanently on any stage failure.
  Author: Claude Code (manager). 2026-06-24.

## Verdict — KILLED at IN_SAMPLE

In-sample window 2026-03-17..2026-05-15. Journaled to `backtest_runs` and
`backtest_kills` (kite_bot.db).

| Metric | Value |
|---|---|
| Trades | 11 |
| Wins | 2 |
| Gross P&L | −₹85.62 |
| Total costs | ₹93.04 (charges ₹47.92 + slippage ₹45.12) |
| **Net P&L** | **−₹133.54** |
| Net edge per trade | −0.296% of notional (cost bar: +0.618%) |
| Max drawdown | ₹162.81 |

**Kill reason (protocol §4):** failed the in-sample test — and not merely a
cost failure: it lost money *gross* (−₹85.62) before costs even applied. Testing
stops at stage 1; no out-of-sample or walk-forward was run.

**Lesson (the fade is a mirage at trade level):** the −0.40% average intraday
move on gap-up days (from the read-only scan) does NOT survive as a tradeable
short. The 1% protective stop is hit on the *continuation* days — gaps that keep
running up stop the short out for a full loss — while the days that do fade
rarely fade far enough to clear the ~0.62% required edge. Win rate 2/11. The
session-average statistic and the per-trade, stop-bounded outcome are different
animals; an unconditional aggregate that "clears the cost bar" is not an edge.
Honest result: no validated edge. Profitability score stays at 4. RELIANCE-only,
paper-only, deployment gate stays blocked.
