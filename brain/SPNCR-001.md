---
tags: [spencer, candidate]
verdict: KILLED
updated: 2026-06-15T15:20+05:30
---
# SPNCR-001 (v1) — KILLED

**Hypothesis:** RELIANCE, as India's most liquid large-cap, exhibits short-horizon intraday momentum persistence: when price closes above its 20-bar (about five trading hours of 15-minute candles) rolling mean, with two consecutive rising closes and volume above its own 20-bar mean, buying pressure tends to continue over the following bars by more than the round-trip cost (about 0.106% plus slippage, per docs/RELIANCE_COST_MATH.md). If this continuation does not exceed costs after a fixed protective stop, the hypothesis is false and the candidate dies.

**Killed:** IN_SAMPLE failed (2026-06-12)

| Stage | Status | Trades | Net P&L (₹) |
|---|---|---|---|
| IN_SAMPLE | FAIL | 28 | -45.53 |

Part of the [[Research Ledger]] · back to [[Spencer]].
