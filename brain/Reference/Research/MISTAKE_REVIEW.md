---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "MISTAKE_REVIEW.md"
---
# MISTAKE REVIEW

> Managed mirror of `MISTAKE_REVIEW.md`. Edit the source file, not this copy.

# Spencer — Mistake Review

Closed trades analysed: **586** (losers: 405, avg P&L/trade: ₹-42.48).

**Diagnosis: SYSTEMIC** — net-negative in every regime AND setup; the trust table down-weights across the board (≈ stop trading this strategy). The fix is the entry SIGNAL, not bucket selection.

> Read-only post-mortem. Trust is **down-only** — it can shrink or skip trades, never increase risk. No live rules were changed.

## Top loss reasons
| reason | losing trades | loss (₹) |
|---|---:|---:|
| bad_regime | 405 | -113,648 |
| bad_setup | 395 | -110,883 |
| overtrading | 379 | -106,560 |
| bad_symbol | 282 | -79,564 |
| weak_entry | 121 | -33,241 |
| high_charges | 26 | -1,225 |

## Worst symbols (lowest avg P&L)
| symbol | trades | win rate | net ₹ | trust |
|---|---:|---:|---:|---:|
| ULTRACEMCO | 1 | 0% | -459 | 1.0 |
| ITC | 8 | 0% | -1,972 | 0.25 |
| INFY | 12 | 8% | -2,721 | 0.25 |
| TCS | 10 | 10% | -1,976 | 0.25 |
| DRREDDY | 10 | 10% | -1,730 | 0.25 |
| GRASIM | 15 | 13% | -2,507 | 0.25 |
| ICICIBANK | 15 | 20% | -2,469 | 0.25 |
| ADANIENT | 13 | 23% | -2,114 | 0.25 |

## Worst regimes
| regime | trades | win rate | net ₹ | trust |
|---|---:|---:|---:|---:|
| RANGE | 260 | 31% | -12,188 | 0.25 |
| TREND_UP | 210 | 30% | -8,915 | 0.2504 |
| TREND_DOWN | 116 | 31% | -3,789 | 0.4233 |

## Worst strategies (across backtest variants)
| strategy | trades | win rate | net ₹ | trust |
|---|---:|---:|---:|---:|
| v1_volume | 475 | 29% | -24,228 | 0.25 |
| v3_targets | 674 | 25% | -31,992 | 0.25 |
| filtered | 375 | 30% | -16,940 | 0.25 |
| baseline | 595 | 32% | -23,980 | 0.25 |
| v_all | 524 | 27% | -13,044 | 0.4887 |
| v2_regime | 1043 | 26% | -24,409 | 0.5193 |

## Setup band breakdown
| setup | trades | win rate | net ₹ | trust |
|---|---:|---:|---:|---:|
| strong | 14 | 29% | -981 | 1.0 |
| marginal | 173 | 30% | -7,322 | 0.2527 |
| moderate | 399 | 31% | -16,589 | 0.2659 |

## Repeated mistakes (symbols that lost ≥3 times)
| symbol | losses | net ₹ | dominant reason |
|---|---:|---:|---|
| INFY | 11 | -2,721 | bad_regime |
| GRASIM | 13 | -2,507 | bad_regime |
| ICICIBANK | 12 | -2,469 | bad_regime |
| ADANIENT | 10 | -2,114 | bad_regime |
| TCS | 9 | -1,976 | bad_regime |
| ITC | 8 | -1,972 | bad_regime |
| KOTAKBANK | 12 | -1,910 | bad_regime |
| CIPLA | 9 | -1,755 | bad_regime |
| DRREDDY | 9 | -1,730 | bad_regime |
| APOLLOHOSP | 13 | -1,721 | bad_regime |

## What should have been rejected
- Rule: reject any trade flagged with a pre-trade-knowable reason (['bad_regime', 'bad_risk_reward', 'bad_setup', 'bad_symbol', 'high_charges', 'weak_entry'])
- Would reject **586** trades (405 losers, 181 winners).
- Loss avoided: **₹-113,648**; profit foregone: ₹88,757; **net removed: ₹-24,891**.
- (Honest caveat: this also removes some winners — the net is what matters.)

## Router trust-gate simulation (how the router would use the table)
- Skip a trade when combined down-only trust < 0.50 (min of symbol/regime/setup trust).
- Would **skip 586** trades (net ₹-24,891) and **keep 0** (net ₹0).
- The router only *reduces* trading here — it never adds risk.

## Rule change to test next (NOT applied)
> SYSTEMIC loss: the strategy is net-negative in EVERY regime and EVERY setup band. The trust table therefore down-weights across the board — effectively 'do not trade this strategy'. The bottleneck is the entry SIGNAL's lack of edge, not bucket selection, so do NOT simply disable regimes. Least-bad regime = TREND_DOWN. Test next: fix/replace the entry signal (features or timeframe), or out-of-sample / walk-forward validate v_all before any deployment.

## Paper journal context
- 6 closed paper trades. all closed paper trades are forced exits (FLATTEN/migration) — excluded from mistake stats as they are not strategy decisions.
