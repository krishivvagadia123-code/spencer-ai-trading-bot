---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "docs/RELIANCE_COST_MATH.md"
---
# RELIANCE COST MATH

> Managed mirror of `docs/RELIANCE_COST_MATH.md`. Edit the source file, not this copy.

# RELIANCE Cost Math — what a trade must clear on a ₹5,000 account

Manager analysis, 2026-06-12. Every number below is computed, not invented:
charges come from the repo's own fee model (`bot/charges.py`); price/volatility
stats come from real Yahoo Finance daily data for RELIANCE.NS. No performance
is claimed — this is the *cost wall* a future technique must clear.

## Inputs (real, sourced)

- RELIANCE last close: **₹1,263.00** (2026-06-11, Yahoo, matches our quote server).
- Affordable quantity on ₹5,000: **1–3 shares** (₹1,263 / ₹2,526 / ₹3,789 notional).
- Volatility sample: 124 trading days (≈6 months) of RELIANCE.NS daily candles.

## Round-trip charges (buy + sell, repo fee model)

| Qty | Notional | Intraday round-trip | Intraday breakeven | Delivery round-trip | Delivery breakeven |
|----:|---------:|--------------------:|-------------------:|--------------------:|-------------------:|
| 1 | ₹1,263 | ₹1.34 | **0.106%** | ₹18.74 | **1.484%** |
| 2 | ₹2,526 | ₹2.68 | **0.106%** | ₹21.55 | **0.853%** |
| 3 | ₹3,789 | ₹4.02 | **0.106%** | ₹24.36 | **0.643%** |

Delivery is dominated by the fixed DP charge on the sell side, which is why its
breakeven explodes as quantity shrinks. Intraday charges scale with notional, so
its breakeven stays ~0.106% at any affordable size.

## What RELIANCE actually moves (124 real trading days)

| Metric | Median | Mean | p25 | p75 |
|---|---:|---:|---:|---:|
| Daily high–low range | 1.70% | 1.93% | 1.32% | 2.40% |
| Open-to-close abs move | 0.70% | 1.03% | 0.32% | 1.27% |
| Close-to-close abs move | 0.82% | 1.09% | 0.33% | 1.62% |

- Days with intraday range ≥ 0.5%: **120 / 124**
- Days with intraday range ≥ 1.5%: **74 / 124**

## Conclusions (cost structure only — NOT a strategy claim)

1. **Intraday is the only cost-viable mode for frequent trading at ₹5,000.**
   Breakeven 0.106% vs a median daily range of 1.70% — the room exists nearly
   every single day. The challenge is *direction and timing*, not costs.
2. **Delivery at 1 share is structurally near-unplayable:** it needs a 1.48% move
   just to break even, which exceeds the median close-to-close move (0.82%).
   Delivery becomes plausible only at 3 shares (0.64% breakeven) held for
   multi-day swings larger than ~1%.
3. **Slippage is not included above** and at 1–3 shares it is small but nonzero;
   the paper engine already models it and must keep doing so.
4. Therefore the mastery research should evaluate techniques in this order:
   (a) intraday RELIANCE with 1–3 shares, (b) multi-day swing with 3 shares,
   and must reject anything whose expected edge per trade is below ~3× its
   round-trip cost.

## What this document is not

It is not evidence of an edge. It defines the bar. A technique only graduates
when journaled paper trades clear these costs consistently (see
`SPENCER_CONCEPT.md`, Definition of Mastery).
