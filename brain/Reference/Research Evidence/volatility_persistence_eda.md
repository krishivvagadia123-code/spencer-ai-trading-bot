---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "docs/research/volatility_persistence_eda.md"
---
# volatility persistence eda

> Managed mirror of `docs/research/volatility_persistence_eda.md`. Edit the source file, not this copy.

# Volatility-persistence EDA — RELIANCE 15m (2026-06-14)

Read-only analysis (`scripts/explore_volatility_persistence.py`, DB hash verified
unchanged) testing the *premise* behind the planned SPNCR-003 day-selection
candidate: does a high-range RELIANCE session tend to be followed by another
high-range session (volatility clustering), and do gap size / expiry associate
with larger ranges?

This measures a statistical property of the data, NOT a trading edge and NOT
tuned parameters. It is motivation for (or against) a hypothesis; any candidate
still pre-registers and clears the full ladder.

## Data
- 58 collected sessions; 57 with near-full coverage (≥18 of ~25 bars).
- Daily high-low range: median 1.72%, mean 1.99%, min 0.88%, max 4.80%.

## Findings (and they are not what the premise hoped)

| Question | Result | Read |
|---|---|---|
| Does yesterday's range predict today's? (lag-1 autocorrelation) | **0.026** | ~zero — no day-to-day persistence |
| P(high-range day \| previous day high-range) | **52%** vs 49% base | +3pp — noise at n=57 |
| Gap size vs same-day range (corr \|gap%\|, range%) | **0.037** | ~zero — gaps don't foretell range |
| Expiry vs non-expiry mean range | 1.83% (n=3) vs 2.00% (n=54) | expiry NOT higher here (tiny n) |

## Implication for SPNCR-003

**The day-selection premise (filter trades to days following a high-range
session) is NOT supported in our collected RELIANCE data.** Daily range shows
essentially no autocorrelation, so "yesterday was volatile" carries almost no
information about today. Building SPNCR-003 around a prev-session-range filter
would likely be a dead candidate — this EDA lets us avoid burning it.

## Honest caveats

- **Small sample (57 sessions).** This is a weak read; more data (the clock is
  collecting) could change it, though a near-zero autocorrelation is unlikely to
  flip to strongly positive.
- The literature memo's "volatility persistence" referred to *intraday* GARCH/
  U-shape effects over long samples — a different, finer measure than day-to-day
  session-range autocorrelation. This EDA does not contradict that; it only says
  the *day-selection* application of it does not hold in our data.
- Persistence (even if it existed) tells us WHEN ranges are large, never WHICH
  DIRECTION — a viable candidate always needs a separate directional rule.

## Recommended next direction (manager note)

Drop prev-session-range day-selection as SPNCR-003's core. Better candidate
directions to consider when the dataset deepens: opening-range behaviour within
the session (first-N-bars structure), VWAP reversion/continuation, or
time-of-day effects (the documented intraday U-shape) — each tested
mechanically, pre-registered, confirm-or-kill. No candidate is built yet.
