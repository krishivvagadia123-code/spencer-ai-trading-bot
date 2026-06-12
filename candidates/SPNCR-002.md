# Candidate SPNCR-002 — ARCHIVED (KILLED at IN_SAMPLE, 2026-06-12)

Filled per `CANDIDATE_TEMPLATE.md`. Machine definition: `candidates/SPNCR-002.json`.
Archived; never edited.

- **Candidate ID:** SPNCR-002 · **Version:** 1 · **Date written:** 2026-06-12
- **Hypothesis (new, not a 001 tweak):** a new 25-bar closing high on the
  heaviest volume of the last 12 bars marks institutional breakout days whose
  remaining-session drift exceeds costs in fewer, larger trades. Falsified.
- **Timeframe:** 15m · **Data:** `intraday_prices` (real, final candles,
  2026-03-17..2026-06-11)
- **Entry:** close ≥ rolling max(close, 25) AND volume ≥ rolling max(volume, 12)
  AND volume > 0 · **Exit:** close < rolling mean(close, 10) · **Stop:** fixed
  1% · **Sizing:** max affordable from ₹5,000 · **Execution:** next candle open
  + paper-engine slippage · **Costs:** bot/charges.py
- **Parameters (fixed, none tunable):** breakout_window=25, vol_max_window=12,
  trail_window=10, stop_pct=0.01
- **Pre-registered splits:** identical calendars to SPNCR-001 (comparability);
  see `candidates/SPNCR-002.splits.json`
- **Kill acknowledgment:** this candidate dies permanently on any stage failure.
  Author: Claude Code (manager). 2026-06-12.

## Verdict — KILLED at IN_SAMPLE

| Metric | Value |
|---|---|
| Trades | 9 (≈1 per 4–5 sessions — frequency target achieved) |
| Wins | 4 |
| Gross P&L | +₹31.83 |
| Total costs | ₹77.18 |
| **Net P&L** | **−₹7.88** |
| Net edge per trade | −0.021% of notional (cost bar: +0.619%) |
| Max drawdown | ₹60.03 |

**Kill reason (protocol §4):** profitable before costs, not after costs.

**Comparative lesson (001 → 002):** cutting trade count 28→9 improved net per
trade from −0.16% to −0.02% of notional — the cost-frequency logic is right,
but average breakout-day drift captured (+0.09% gross/trade) is still ~7×
too small for the 3× cost bar. Two structural readings, recorded honestly:
(1) RELIANCE 15m breakouts in this 40-session window simply did not drift;
(2) 58 sessions of free Yahoo history is a thin base — every week the
collector runs strengthens future verdicts. The next hypothesis must select
*days* with abnormally large expected ranges (e.g. gap/volatility context),
not just intra-session breakout moments.
