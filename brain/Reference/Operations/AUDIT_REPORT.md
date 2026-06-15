---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "AUDIT_REPORT.md"
---
# AUDIT REPORT

> Managed mirror of `AUDIT_REPORT.md`. Edit the source file, not this copy.

# Spencer — Codebase Audit (2026-06-02)

Audit of the existing project at `AI TRADE/`. Scope: locate fabricated data, and
verify four safety properties. Evidence cited as `file:line`. **No code was changed
by this audit** except adding a read-only backtest harness (`bot/backtest.py`).

## TL;DR

The **real engine** (`bot/` + `paper_engine.py`) is honest and safe: paper-only, real
risk vetoes, journaled. The **dashboard** is wired to a **separate simulated Node
engine** that runs on synthetic prices — that is where every fabricated number lives.

| Check | Verdict |
|-------|---------|
| Fake dashboard data | ❌ FOUND — Node engine runs on a synthetic price simulator |
| Fake strategy statuses | ❌ FOUND (Node) / ✅ clean (Python defaults) |
| Fake win/loss numbers | ❌ FOUND (Node sim) / ✅ none in real engine |
| PaperBroker is default | ✅ PASS (engine is hard paper-only) |
| Live trading double-gated off | ⚠️ PARTIAL — off by *absence*, no explicit guard flag |
| Risk gate can veto trades | ✅ PASS |
| All trade decisions journaled | ✅ MOSTLY — `signal_log` table is empty (0 rows) |

---

## A. Fake data findings

### A1. The dashboard's "bot" is a price simulation, not the real engine
- `backend/engine/priceSimulator.js` — generates synthetic OHLC bars via a
  regime-driven random walk (`driftFor`, `generateNextBar`, `normal(rand, drift, sigma)`).
- `backend/engine/botEngine.js` — consumes those synthetic bars; all orders, holdings,
  P&L, and win-rate come from the simulation. `Math.random()` used at `:264`.
- `backend/server.js:21,415` — serves this simulation on port **8787** at `/api/bot/*`.
- `frontend/src/App.jsx` — the bot panel calls `http://127.0.0.1:8787/api/bot/state`
  (`:2205`), `/status` (`:234`), `/start` (`:223`) → it is showing **simulated** activity.
- **Impact:** every "live bot" number on the dashboard is synthetic. The real Python
  paper engine (`paper_engine.py`) is a *different* process the dashboard does not read.

### A2. Hardcoded "AI confidence" numbers
- `frontend/src/utils/constants.js:95-97` — `defaultCopyStyles` hardcode
  `confidence: 70 / 75 / 80`. These are fabricated confidence scores.

### A3. Unverifiable performance claims in strategy `edge` text
- `frontend/src/utils/constants.js:71-91` — e.g. *"Minervini averaged 220%…"*,
  *"68–72%"*, *"cuts false signals by ~40%"*, *"80% of the time"*. Marketing claims, not
  measured stats. Acceptable only if clearly labelled as descriptions, not live metrics.

### A4. Synthetic seed prices
- `frontend/src/utils/constants.js:4-19` — `STOCK_BASES` hardcoded price seeds used to
  bootstrap the simulator. Fine for a demo, but must never be presented as live quotes.

### B. Fake strategy statuses
- `backend/engine/botEngine.js:85` — `status = (id === activeStrategyId) ? "Testing" : "Queued"`.
  Status reflects *which strategy is selected*, not any real test outcome.
- ✅ **Already cleaned:** `defaultStrategies` in `constants.js` now ship
  `status:"Not Tested", wins:0, losses:0` (migration in `frontend/patch_strats.js`).

### C. Fake win/loss numbers
- `backend/engine/botEngine.js:349,596,620` — `winRate` computed from **simulated** trades.
- ✅ The real engine has **no** fabricated win/loss. The live `kite_bot.db` holds only
  **6 closed trades**, and all are forced exits (`FLATTEN`, `EQUITY_ONLY_MIGRATION`) —
  not strategy outcomes. There is not yet enough real history to report performance.

---

## D. Safety property verification (real Python engine)

### D1. PaperBroker is default — ✅ PASS
- `paper_engine.py:22` header: *"Paper-only. No live broker order placement anywhere."*
- Grep for `place_order` / `KiteConnect.*order` / `transaction_type` across `bot/` →
  **no matches**. No live order path exists.

### D2. Live trading double-gated off — ⚠️ PARTIAL (recommend hardening)
- Live is effectively off because **no order-placement code exists at all**.
- **Gap:** there is no explicit, auditable gate. `bot/config.py` has `use_zerodha: bool`
  and `broker: "zerodha"` (used for *quotes*), but no `live_enabled` / credentials guard.
- **Recommendation:** add an explicit double-gate (`live_enabled=False` **and**
  `has_live_credentials=False`) that any future live adapter must check, so "off" is
  enforced by a guard rather than by absence.

### D3. Risk gate can veto trades — ✅ PASS
- `bot/risk.py`:
  - `check_all_caps` (`:228`) fails **closed** on missing prices (`:245`), and vetoes on
    daily-loss (`:259`), drawdown (`:274`), max-open-positions (`:279`), gross/per-symbol
    exposure (`:296,:314`).
  - `calculate_position_size` rejects when stop is undefined or when expected loss incl.
    charges+slippage exceeds the risk budget (`:199-211`).
  - `is_entry_allowed` (`:331`) combines kill-switch/pause control with caps; exits are
    explicitly **never** gated (correct — risk can always be unwound).

### D4. All trade decisions journaled — ✅ MOSTLY (one gap)
- `bot/db.py`: `trades` table + `log_trade` (`:164`); `signal_candidates` is richly
  journaled (scores, block reasons, `entry_blocked`) — **5,442 rows present**.
- **Gap:** the `signal_log` table exists (`:94`) but currently has **0 rows** — per-scan
  signals are not being written on the active path. Either wire it up or standardize on
  `signal_candidates` (which is populated) as the canonical decision log.

---

## E. Existing learning layer (do NOT rebuild)
- `bot/learner.py` already implements a sound **anti-overfit** learner: bounded weights
  (±0.10), 30-trade minimum, deterministic (seeded), trains only on **closed** trades,
  no look-ahead, regress-to-mean on losing streaks/drawdown, `.bak` backups.
- Phase 3 should **extend** this with *per-regime* attribution, not replace it.

---

## F. Real backtest results (generated by this audit)
- New harness `bot/backtest.py` replays the **real** `bot.signals` + `bot.risk` logic
  over real yfinance daily data; writes to a **separate** `backtest_journal.db`
  (live DB untouched). Research scores held neutral (0.5) → technical-only replay.
- **Nifty-50, 2 years, 49 symbols, 595 trades:** win rate **31.9%**, gross **−₹2,401**,
  charges **₹21,579**, **net −₹23,980**.
- **Key finding:** the strategy is ~breakeven *gross* but loses entirely to **transaction
  costs** — it overtrades. Charges are 9× the gross P&L.
- **Second finding:** 100% of trades tagged `TREND_UP` because the regime label is
  *collinear* with the entry filter. Per-regime attribution needs an **independent**
  regime signal (e.g. the Nifty index regime at entry) — this is what Phase 3 adds.

---

## G. Remediation log (applied this session)

1. **Dashboard wired to the REAL engine.** Added real `/api/bot/state`, `/api/bot/config`,
   `/api/bot/stop`, `/api/bot/reset` to `spencer_quote_server.py`, reading the actual
   paper journal (`kite_bot.db`) via stdlib `sqlite3`. The dashboard now shows real
   positions, real closed-trade metrics, and real P&L (`simulated: false`). A parser bug
   that briefly produced a misleading +80% P&L was caught and fixed (positions use
   `entry_price`). The legacy Node simulation (`backend/server.js`) now prints a loud
   startup warning and must not be served on 8787.
2. **Explicit live double-gate added.** `bot/config.py` now has `LiveTradingGate`
   (`live_enabled` + `has_live_credentials`, both default False), `live_trading_allowed()`,
   and `assert_paper_only()` for any future execution path. "Off" is now enforced, not
   merely absent.

## H. Phase 3 delivered
- `bot/regime_learner.py` — per-regime trust over the real backtest journal, attributed
  to the **independent** Nifty-index regime. Down-only trust `[0.25, 1.0]`, ≥20-trade
  min-sample, deterministic, closed-trades-only, `.bak` backups. 6 passing tests.
- Result on real data: TREND_UP trust 0.25, TREND_DOWN 0.25, RANGE 0.64 → `regime_trust.json`.

## I. Anti-overtrading filter (delivered)
- `bot/trade_filter.py` — 6-rule pre-trade quality gate (min trust, min R:R, min edge
  after charges, max trades/day, post-loss cooldown, charges-vs-target cap). Pure,
  deterministic, explainable; can only make the engine MORE selective. 9 passing tests.
- `bot/backtest.py` upgraded to a portfolio-level event loop (needed for per-day caps +
  cooldown) with a `--compare` mode. Baseline vs filtered on Nifty-50 / 2y:

  | metric | baseline | filtered | change |
  |---|---|---|---|
  | trades taken | 586 | 375 | −36% |
  | win rate | 30.9% | 30.4% | ~flat |
  | net P&L | −₹24,891 | −₹16,940 | +32% (loss cut ~₹7.9k) |
  | charges | ₹18,193 | ₹12,196 | −33% |
  | max drawdown | 56.2% | 39.3% | −30% |
  | rejected trades | 0 | 3,246 | min_trust 2,620 · daily-cap 590 · cooldown 36 |

- **Honest read:** the filter did its job — a third fewer trades, a third less cost, and
  a much smaller drawdown. But it is still net-negative because the underlying technical
  config has **no real edge** (≈30% win rate vs ~33% breakeven at 2R). A filter reduces
  damage; it cannot manufacture edge. Next step is improving the signal itself, not the
  filter. (Note: rejection counts attribute each reject to its FIRST failing rule, so
  `min_trust` masks later-rule rejections for trades it already blocks.)

## J. Entry-signal experiments (controlled, one group at a time)
- `bot/entry_policy.py` — three toggleable upgrades; `bot/backtest.py --experiment` runs
  baseline + each upgrade + combined on ONE shared data fetch (20 passing unit tests total).
- **Full Nifty-50 / 2y (the honest sample — a 3-symbol sample misleadingly favoured v2):**

  | metric | baseline | v1 volume | v2 regime | v3 targets | v_all |
  |---|---|---|---|---|---|
  | trades | 586 | 475 | 1043 | 674 | 524 |
  | win rate | 30.9% | 29.5% | 25.8% | 24.9% | 27.5% |
  | avg win | 490 | 503 | 309 | 564 | 539 |
  | avg loss | −281 | −283 | −139 | −250 | −239 |
  | net P&L | −24,891 | −24,228 | −24,409 | −31,992 | **−13,044** |
  | charges | 18,193 | 14,882 | 33,719 | 21,358 | 20,695 |
  | max DD % | 57.1 | 53.3 | 59.6 | 70.0 | **42.8** |

- **Honest conclusion: no single upgrade created edge.** Win rate stayed ~25–31% across
  all variants — still below the ~33% break-even at 2R. Specifically:
  - *Volume confirmation (v1):* cut trades/charges ~18% but win rate slightly DOWN; net flat.
  - *Regime-specific (v2):* as implemented it OVERTRADES — the "pullback within 0.5 ATR of
    EMA" condition fires constantly in up-trends (797 TREND_UP trades) and LOWERS win rate.
    This is a bug-shaped finding, not a win: the entry condition is too loose.
  - *Wider 3R target + 1.5-ATR stop (v3):* worse win rate AND worse drawdown (70%).
- **v_all** has the best net (−13k vs −25k) and lowest drawdown (42.8%), but that comes from
  trading *less* in bad regimes + the charge guard — **damage reduction, not edge.** At 27.5%
  win it is still unprofitable.
- **Takeaway:** the bottleneck is real and not yet solved — daily technical signals on
  large-caps show no exploitable edge after costs in this window. Next steps that follow the
  evidence: (a) tighten the TREND_UP pullback condition + require confluence; (b) walk-forward
  validate v_all before trusting it; (c) question whether the timeframe/universe can have edge
  at all, rather than adding parameters. Do NOT ship any variant as "improved" — none is.

## K. Mistake Review Engine (delivered)
- `bot/mistake_review.py` — read-only post-mortem over the journals (9 passing tests).
  Detects all 8 loss causes per losing trade (bad_regime, weak_entry, overtrading,
  high_charges, bad_risk_reward, stop_too_tight, bad_symbol, bad_setup), and writes:
  - `MISTAKE_REVIEW.md` — top loss reasons, worst symbols/regimes/strategies, repeated
    mistakes, what-should-have-been-rejected, and the next rule to TEST (not applied).
  - `mistake_trust.json` — DOWN-ONLY trust [0.25,1.0] for symbol / regime / strategy / setup.
- **Findings (baseline portfolio, 586 trades):** loss is **SYSTEMIC** — net-negative in
  every regime (RANGE 0.25, TREND_UP 0.25, TREND_DOWN 0.42) and every setup band
  (marginal/moderate ≈0.25, strong 1.0 but only 14 trades). 29/49 symbols down-weighted.
  Strategy trust: v_all 0.49 / v2 0.52 least-bad; baseline/v1/v3/filtered floored at 0.25.
- A **router trust-gate simulation** (skip when combined trust < 0.5) skips all 586 trades —
  the honest verdict that this strategy should not be traded as-is.
- Guarantees honored: read-only, no live change, down-only (never increases risk), no
  fabricated improvement. The engine explicitly flags the bottleneck as the entry SIGNAL.
- Router API: `lookup_trust(table, symbol=, regime=, strategy=, setup=)` → most-conservative
  multiplier ≤ 1.0 for the scanner to scale size down / skip (wiring into live scanner is
  left as a deliberate, separate step — not done here).

## L. "Fewer, higher-quality entries" experiment (delivered)
- `bot/entry_policy.py` quality gates: stricter BUY cutoff (`min_score`), momentum+volume
  confluence (`require_confluence`), and no-long-in-TREND_DOWN (`avoid_trend_down`).
  `bot/backtest.py --quality` runs old vs new + each lever isolated (14 entry tests pass).
- **Full Nifty-50 / 2y (stop/target held at 2R so win-rate change = entry quality only):**

  | metric | baseline (old) | q1 cutoff≥0.72 | q2 confluence | q3 no-downtrend | q_highquality (new) |
  |---|---|---|---|---|---|
  | trades | 586 | 202 | 445 | 529 | 117 |
  | **win rate** | 30.9% | 31.2% | 28.5% | 30.8% | 29.9% |
  | avg win | 490 | 611 | 491 | 457 | 636 |
  | avg loss | −281 | −353 | −274 | −268 | −384 |
  | net P&L | −24,891 | −10,553 | −24,792 | −23,602 | −9,232 |
  | max DD % | 57.1 | 33.4 | 52.6 | 54.7 | 25.4 |

- **Verdict (honest): the goal was NOT met.** Win rate did not improve — 30.9% → 29.9%
  (−1.0 pt) for the combined "new" signal, despite an 80% cut in trades. The big drops in
  net loss (−25k → −9k) and drawdown (57% → 25%) come purely from **trading less / smaller
  exposure**, NOT from picking better trades. Stricter filtering of a non-predictive score
  yields fewer non-predictive trades; the ~30% win-rate ceiling is unmoved.
- **One faint lead (do not overclaim):** RANGE with the stricter cutoff was the only pocket
  to turn positive (q1 RANGE 38% win, +₹1,055 over 73 trades). Small sample — worth a
  focused, walk-forward test, not a deployment.
- **Conclusion:** confirms the mistake-review SYSTEMIC diagnosis from a second angle. Raising
  win rate requires a genuinely *predictive* feature/timeframe, not more selectivity on the
  same technical score. No variant is shipped as "improved."

## M. Walk-forward of the RANGE + strict-cutoff pocket — FAILED
- `bot/walkforward.py` — out-of-sample test of the ONLY positive pocket (RANGE-only,
  score ≥ 0.72). Fixed hypothesis, no per-fold re-tuning, verdict criteria pre-registered
  in the docstring. Same universe/costs/risk/engine; only the date window changes.

  | | trades | win rate | net P&L | max DD |
  |---|---|---|---|---|
  | In-sample (yr 1) | 30 | 43.3% | +₹2,261 | 6.9% |
  | Out-of-sample (yr 2) | 95 | **31.6%** | **−₹3,726** | 17.1% |

- **Verdict: FAILED.** The in-sample 43% win rate collapsed to 31.6% OOS (below ~35%
  breakeven); only 2/4 OOS quarters positive; aggregate negative. The pocket was a
  selection illusion, not a real edge. Not deployed, not wired to live.
- **Consequence:** per the plan, this triggers Option B — prototype genuinely *predictive*
  features (relative strength vs Nifty, breakout quality, volume-expansion quality, sector
  strength) and MEASURE their predictive power before building any entry around them.

## N. Option B — predictive-feature prototypes (measured, not deployed)
- `bot/features.py` (4 causal features) + `bot/feature_eval.py` (information-coefficient
  evaluation: Spearman IC of each feature vs 5-day forward return, split IS vs OOS, plus
  quintile spread and a ~0.25% cost hurdle). 6 passing tests. No trading, no fitting.
- **Nifty-50 / 2y, 23,120 observations, IS/OOS split 2025-06-03:**

  | feature | IC in-sample | IC out-sample | OOS q5−q1 | direction | usable |
  |---|---|---|---|---|---|
  | relative_strength | +0.005 | −0.035 | −0.29% | mean-reversion | no (sign flips) |
  | breakout_quality | −0.012 | −0.034 | −0.25% | mean-reversion | stable but uneconomic |
  | volume_expansion_quality | +0.011 | −0.034 | −0.29% | mean-reversion | no (sign flips) |
  | sector_strength | +0.020 | −0.047 | −0.43% | mean-reversion | no (sign flips) |

- **Verdict: NONE are usable.** Three features flip IC sign between IS and OOS (= noise).
  `breakout_quality` is the only sign-stable one, but it points the "wrong" way (breakouts
  *fade*, not continue) and its ~0.25% 5-day spread does not clear ~0.25% round-trip costs.
- **Honest meaning:** on Nifty-50 daily data, these classic technical features carry no
  reliable long-momentum edge; the only stable tendency is faint MEAN-REVERSION (breakouts
  fade), too small to trade after costs. This is consistent with every prior result.
- **Recommended next (your call):** either (a) a controlled mean-reversion prototype using
  breakout-fade / RS-fade, walk-forward tested and expected to be marginal; or (b) step
  outside daily large-cap technicals (different timeframe, universe, or non-price data),
  since the evidence says daily NSE large-cap price features alone don't carry tradeable edge.

## O. Option B path 1 — INTRADAY predictive-power test (no edge found)
- `bot/intraday_eval.py` — same IC framework on 15-minute Nifty-50 candles with intraday
  features: opening-range position, VWAP distance, volume shock, relative strength.
  Within-day forward returns (no overnight leak). 2 tests; intraday data WAS available
  (~58 trading days, the yfinance 60-day cap), so the midcap fallback was not triggered.
- **15m, 50 symbols, 47,481 observations, IS/OOS split 2026-04-21:**

  | feature | IC in-sample | IC out-sample | OOS q5−q1 | weekly sign-stable | usable |
  |---|---|---|---|---|---|
  | opening_range | +0.010 | −0.020 | −0.02% | 86% | no (sign flips IS→OOS) |
  | vwap_distance | +0.025 | −0.006 | −0.01% | 43% | no (sign flips) |
  | volume_shock | +0.005 | −0.001 | ~0% | 57% | no (sign flips) |
  | relative_strength | +0.009 | −0.013 | −0.02% | 57% | no (sign flips) |

- **Verdict: NO intraday edge found.** All four features flip IC sign from in-sample
  (faint positive) to out-of-sample (negative) — the classic noise/overfit signature — and
  the OOS quintile spreads are ~0.0–0.02% over 1 hour, far below the ~0.15% intraday cost
  hurdle. Same conclusion as daily, on a different timeframe.
- **Caveat:** only ~2.5 months of intraday history is available from this free source, so
  this is a screen, not a verdict for all time. But nothing here is even a candidate.
- **Next probe (your call):** Nifty Midcap 100 daily with the same IC framework — the one
  remaining cheap place edge is more likely (larger inefficiencies than large-caps).

## P. Option B path 2 — Nifty Midcap 100 daily IC test (no survivable edge)
- `bot/midcap_eval.py` — same IC framework on ~99 mid-caps, 5 features (incl. new
  `mean_reversion_after_failure`), plus monthly stability and walk-forward survival.
  Benchmark fell back to ^NSEI (midcap index tickers 404'd). 46,221 observations.
  A unit test caught and fixed a real bug in the failed-breakout feature (the spike was
  being absorbed into its own resistance level; fixed by shifting the level by `recent`).

  | feature | IC in | IC oos | OOS q5−q1 | dir | monthly-stable | walk-fwd | usable |
  |---|---|---|---|---|---|---|---|
  | relative_strength | −0.017 | −0.026 | −0.28% | mean-rev | 70% | no | no |
  | breakout_quality | −0.027 | −0.014 | −0.27% | mean-rev | 83% | no | no |
  | volume_expansion | +0.021 | +0.001 | +0.01% | momentum | 74% | no | no |
  | mean_reversion_after_failure | −0.010 | −0.026 | ~0% | mean-rev | 65% | no | no |
  | sector_strength | +0.011 | −0.073 | −0.66% | mean-rev | 70% | **yes** | no |

- **Verdict: NO midcap feature is usable.** Four features lean mean-reversion (consistent
  with every prior result). `sector_strength` is the only one to "survive" the within-OOS
  walk-forward AND clear costs — but its IC **flips sign** from in-sample (+0.011) to
  out-of-sample (−0.073), i.e. it's regime-dependent, not a stable edge, so it fails the
  usability bar. Midcap ICs are somewhat *larger* in magnitude than Nifty-50 (more
  cross-sectional dispersion) but they are not stable or tradeable.
- **Answer to "do midcaps have more exploitable edge than Nifty-50?": No.** Same null
  result, different universe. The mean-reversion tilt is slightly stronger but sign-unstable.

## Conclusion of the edge search (six independent tests)
Daily large-cap, intraday large-cap, and daily mid-cap technical features all show **no
stable, cost-clearing, walk-forward-robust edge.** The only recurring (but unstable/uneconomic)
signal is mild mean-reversion. Recommendation for capital protection: do NOT build a directional
technical strategy on these signals; if pursuing further, leave price-only technicals
(event/earnings windows, fundamentals, or a different asset class) — measured the same honest way.

## Q. Option B path 3 — EVENT-ALPHA research (read-only)
- `bot/event_eval.py` — event study measuring forward return / win rate / cost-adjusted
  return / max adverse move / IS-vs-OOS / walk-forward around events. 6 tests.
- **Data reality (honest):** earnings dates+surprise and corporate actions ARE available
  historically (yfinance); gaps/volume-shocks are price-derived. **News-based types are NOT
  testable** — yfinance news is recent-only, so `sector_news_impact` and
  `stock_sentiment_shock` are reported as NOT TESTABLE rather than faked.
- **Nifty-50, 2y, 49 symbols, forward 5d, cost 0.25%:**

  | event type | events | win% | avg fwd | cost-adj | max adverse | IS | OOS | walk-fwd |
  |---|---|---|---|---|---|---|---|---|
  | earnings_all | 441 | 61% | +0.71% | +0.46% | −6.4% | +0.92% | −0.10% | fails |
  | earnings_beat | 214 | 63% | +0.77% | +0.52% | −6.7% | +0.76% | +0.17% | fails |
  | earnings_miss | 206 | 64% | +1.03% | +0.78% | −5.9% | +1.64% | −0.12% | fails |
  | volume_shock | 457 | 52% | +0.24% | −0.01% | −2.5% | +0.03% | −0.04% | fails |
  | **gap_up** | 176 | 69% | +1.67% | **+1.42%** | −2.4% | +1.33% | +1.51% | **survives** |
  | gap_down | 165 | 60% | +1.93% | +1.68% | −2.6% | +3.50% | −0.17% | fails |
  | corp_action_dividend | 1622 | 67% | +1.31% | +1.06% | −8.5% | +1.19% | −0.23% | fails |
  | corp_action_split | 103 | 67% | +1.42% | +1.17% | −8.1% | +1.33% | −0.49% | fails |

- **First non-null result of the whole search:** `gap_up` is the only event type whose
  cost-adjusted edge (+1.42% / 5d, 69% win, IS +1.33% ≈ OOS +1.51%) survives walk-forward.
  Every other type is positive in-sample but flat/negative out-of-sample (the usual overfit
  signature) — notably earnings drift and dividend/split "edges" vanish OOS.
- **Hard caveats (do not over-read):** (1) multiple comparisons — 8 buckets tested, 1
  survivor is weak evidence; (2) small sample (~176 events, ~88 OOS); (3) gap-day slippage
  likely exceeds the flat 0.25% cost assumed; (4) gap-ups overlap with earnings/news, so the
  effect may be confounded. It is a CANDIDATE, not a confirmed edge. Not deployed.
- **Recommended confirmation (if pursued):** gap-up over 5+ years, realistic gap-day
  slippage, midcap out-of-universe replication, and a true holdout split.

## R. gap_up confirm-or-kill — **KILLED**
- `bot/gapup_confirm.py` — rigorous, gap_up-only test: 8 years history, ATR-scaled realistic
  slippage + flat sweep, both universes, holdout + per-year walk-forward, earnings-overlap
  split. Verdict gates pre-registered. 4 tests.
- **Nifty-50 (739 events, 8y) — FAILS:** win 49%, gross +0.91%, **realistic net −0.20%**,
  IS −0.50% / OOS +0.10%, non-earnings −0.18%; walk-forward NEGATIVE in 7 of 9 years and
  positive only in 2025–2026. 4 of 6 gates fail.
- **Midcap-100 (2,405 events) — passes the gates** (realistic net +0.47%, IS +0.52% / OOS
  +0.42%) BUT is year-inconsistent (2018/2019/2022/2024 negative) and, like Nifty-50, is
  driven by the recent 2025–2026 window; avg adverse move −5.4%.
- **Verdict: KILLED.** The original 2-year gap_up "edge" was a **recent-bull-market
  artifact** — gap_up lost money in most pre-2025 years on the cleaner Nifty-50 universe and
  only worked in exactly the window the 2-year test had sampled. It does not survive long
  history + realistic slippage on the primary universe. No strategy was built. Not deployed.
- (Note: the sequential-drawdown figure is a proxy that compounds thousands of overlapping
  5-day bets and hits ~100% — not a real portfolio DD; the meaningful risk stat is the
  ~−5% average adverse move.)

## Final conclusion of the edge search (seven tests)
Daily large-cap, intraday large-cap, daily mid-cap technicals, and event studies (earnings,
gaps, corporate actions, volume shocks) **all fail to show a stable, cost-clearing,
walk-forward-robust edge.** The only positive-looking results were recent-period artifacts
that died under longer history or realistic costs. News/sentiment event types remain
untestable without a historical news feed.
**Honest position:** Spencer has no demonstrated alpha source in free daily/intraday NSE
price+event data. Its real, delivered value is the disciplined, fully-tested **paper-trading
+ risk-gate + mistake-review + honest-research** framework. Recommend pausing the alpha hunt
unless a genuinely new data source (historical news/fundamentals/alternative data) is added.

## S. Orchestration pivot — capital-protection + research assistant
- Decision recorded: **price-only mining is paused** (seven null tests). Spencer's role is now
  (a) a disciplined paper-trading / risk / mistake-review framework, and (b) a research
  assistant that screens NEW, non-price data sources with the same honest IC/event method.
- **`DATA_SOURCE_RESEARCH_PLAN.md`** scopes seven data sources (delivery volume, bulk/block
  deals, FII/DII flows, sector rotation, earnings reaction, news/sentiment, news-confirmed
  volume) on: data needed, source, free vs paid, test method, cost, edge potential, feasibility.
- **First module chosen:** delivery volume % (free, per-stock, genuinely non-price, plugs into
  the IC framework). **Codex task filed:** `workflow/tasks/research_delivery_volume.md`
  (read-only research only; paper-only; no strategy; deployment stays blocked).
- Manager scope respected: created the plan + task + this audit update only. Did NOT modify the
  workflow engine (`pipeline.py` / `research_automation.py`) — that is Codex's in-flight work.

## T. Delivery-volume predictive-power test — **FAIL** (first non-price data source)
- Codex built `bot/nse_delivery.py` (NSE archive ingest, EQ-only, cache, None on failure)
  + `bot/delivery_eval.py` (read-only IC research, 5 tests pass). Reviewed: sound, causal,
  honest. One perf issue flagged below. Orchestrator ran the real evaluation via an efficient
  driver (`scripts/run_delivery_eval_fast.py`) that reuses Codex's exact logic but parses each
  cached bhavcopy once (the shipped per-(symbol,day) re-parse was >10 min / timed out).
- **1. Data availability — EXCELLENT (the pleasant surprise):** NSE `sec_bhavdata_full`
  archives fully reachable; 512 daily files → 2,781 symbols, 1.09M rows. Nifty-50: 49/50
  symbols, **22,981** obs. Midcap-100: 99/99 symbols, **46,426** obs. Far above the 100-obs bar.
  (Result reproduced 2026-06-03; verdict identical across runs.)

  | universe | feature | IC in | IC oos | quintile spread | cost-adj | monthly-stable | walk-fwd | usable |
  |---|---|---|---|---|---|---|---|---|
  | Nifty-50 | delivery_pct | +0.003 | −0.000 | −0.08% | −0.22% | 50% | no | no |
  | Nifty-50 | delivery_pct_zscore | −0.016 | +0.006 | −0.08% | −0.38% | 57% | no | no |
  | Nifty-50 | delivery_spike | n/a | n/a | ~0% | n/a | n/a | no | no |
  | Midcap-100 | delivery_pct | +0.012 | −0.006 | −0.29% | −0.01% | 46% | no | no |
  | Midcap-100 | delivery_pct_zscore | +0.012 | +0.005 | +0.01% | −0.29% | 48% | no | no |
  | Midcap-100 | delivery_spike | n/a | n/a | ~0% | n/a | n/a | no | no |

- **Decision: FAIL.** Every feature either flips IC sign IS→OOS or sits far below |IC|≥0.03;
  quintile spreads ~0 (below the 0.30% cost hurdle); monthly stability ~coin-flip (46–57%);
  no walk-forward survival. None usable in either universe. `research_automation` recorded
  FAIL, kept deployment blocked, and created `workflow/tasks/record_delivery_eval_rejection.md`.
- **8. Limitations:** delivery data is end-of-day (used only after close; not intraday); NSE
  archive coverage varies by date (holidays/failures skipped); 1 Nifty + 6 midcap symbols
  lacked usable rows/overlap. None of this affects the conclusion — coverage was ample.
- **Honest read:** delivery volume is a genuinely *non-price* positioning signal with great
  data, yet shows **no edge** for 5-day forward returns. Consistent with every prior result.
- **Codex follow-up (perf, not correctness):** `nse_delivery.delivery_history` re-parses the
  full daily bhavcopy per (symbol, day) → ~26k parses for 50 symbols × 2y. Should fetch each
  day once and extract all symbols (one-pass), or expose a multi-symbol panel builder.

## U. Bulk/block-deals module — built, but **DATA-LIMITED** (not edge-tested)
- Codex built `bot/nse_block_deals.py` (session-cookie warmup, retries, cache, robust
  multi-format normalization, BUY/SELL filter, `None` on failure) + `bot/blockdeal_eval.py`
  (read-only buy/sell event study). 6 tests pass. Code quality: good.
- **Data-availability finding (probed 2026-06-03):**
  - Codex's source = NSE dynamic API `/api/historical/{bulk,block}-deals` → **bot-protected,
    returns None / 503**. Not reliable for historical auto-fetch.
  - **Static archive `archives.nseindia.com/content/equities/{bulk,block}.csv` WORKS** (HTTP 200,
    real deals; header matches Codex's normalizer exactly) — but carries only a **rolling
    recent window** (current sessions), NOT 2 years. Good for forward collection, not a backtest.
- **Decision (among the 4 options): primarily (2) add manual-CSV upload + (1) static-archive
  ingestion; NOT (4) blocked.** Rationale: data IS obtainable — an operator can download real
  NSE bulk/block CSVs for any historical range from the browser, and the static archive covers
  recent/forward days. So block deals are *data-limited pending operator-supplied history*, not
  permanently blocked. No fabrication; the module ingests only real NSE rows.
- **No edge test was possible** (no 2-year history yet) → no PASS/FAIL/NEEDS-CONFIRMATION on the
  signal. Deployment gate stays blocked (still FAIL from delivery_eval). Once historical CSVs
  are supplied, the same event-study bar (IS/OOS, cost-adjusted, walk-forward) applies.
- **Next task filed:** `workflow/tasks/blockdeals_data_access.md` — Codex to add (a) a
  manual-CSV folder ingestion path and (b) the working static-archive CSV fetch to
  `nse_block_deals.py`, with an honest DATA-UNAVAILABLE report when neither yields ≥ the
  minimum events.

## V. Block-deals data-access (Codex) — reviewed + run → **NEEDS MANUAL HISTORY**
- **Implementation review:** Codex delivered `nse_block_deals.py` with manual-CSV ingestion
  (`data/block_deals/`), static-archive fetch (`bulk.csv`/`block.csv`), source precedence
  `manual_csv > static_archive > dynamic_api`, source-rank dedup, `source_counts` via
  `df.attrs`, and **no synthetic fallback**. `blockdeal_eval.py` buckets bulk/block × buy/sell
  (directional return = +fwd for BUY, −fwd for SELL), with cost-adjusted edge, IS/OOS, monthly
  stability, walk-forward, and a `MIN_EVENTS=30` DATA_UNAVAILABLE guard. **11 tests pass.**
  Code quality: good; correct; no issues beyond the data gap below.
- **Safety review (verified):** paper-only ✓; no live trading ✓; no broker execution / no
  `place_order` / no broker SDK ✓; no AI order approval ✓; no fabricated data, P&L, or bot
  status ✓ (grep clean — only the module's own "no live trading" *declarations* match); no
  strategy deployment ✓. Deployment gate remains `deploymentBlocked: true`, `paperOnly: true`,
  `liveTradingAllowed: false`.
- **Research result (run through automation, static archive only — no manual CSVs yet):**
  Nifty-50 `requested=50, deal_symbols=0, raw_events=0, used_events=0` → all six buckets empty.
  **Data source used:** static archive only (recent rolling window; no manual history present).
  The static archive's current-day deals fell on small/mid-caps, so **zero** overlapped the
  Nifty-50 universe.
- **Decision: NEEDS MANUAL HISTORY** (per the orchestrator rule: too-small data ⇒ not FAIL).
  The module's literal string is "FAIL: DATA_UNAVAILABLE (0 < 30 events)" and the gate is FAIL
  (correctly non-deployable), but the *research* status is a **data gap, not a signal failure** —
  the edge was never testable. Reason: bulk/block deals are sparse and concentrate outside the
  Nifty-50 universe; the static archive carries only recent days, so a real test needs
  operator-supplied historical CSVs in `data/block_deals/`.
- **Spencer Score Impact: no change (stays ~48/100).** No alpha was found or could be tested,
  and no strategy/capability shipped. The only gain is *research-infrastructure robustness*
  (a new honest, no-fabrication data-ingestion path with a clean DATA_UNAVAILABLE guard) — a
  process improvement, not an edge. We do NOT raise the score on infrastructure alone.

## W. FII/DII flows (Codex) — reviewed + run → **DATA_UNAVAILABLE / NEEDS HISTORY**
- **Implementation review:** Codex delivered `nse_flows.py` (parses NSE `fiidiiTradeReact`
  JSON/CSV, categorizes FII/FPI vs DII, computes net, caches raw payloads per day, `None` on
  failure, no fabrication) + `flows_eval.py` (market-timing IC study vs index forward returns
  with features `fii_net`, `dii_net`, `fii_minus_dii`, `fii_plus_dii` and z-scores; IS/OOS,
  quintile spread, cost-adjusted, monthly stability, walk-forward; `MIN_OBSERVATIONS=100`
  DATA_UNAVAILABLE guard; market-level framing, no per-stock claim). **6 tests pass.** Correct.
- **Safety review (verified):** paper-only ✓; no live trading ✓; no broker execution /
  `place_order` / broker SDK ✓; no AI order approval ✓; no fabricated data or P&L ✓ (grep clean
  — only the module's own "no live trading" *declarations* match); no strategy deployment ✓.
  Gate: `deploymentBlocked: true`, `paperOnly: true`, `liveTradingAllowed: false`.
- **Research result (run through automation):** **only 1 real FII/DII row** available
  (the NSE endpoint returns the current provisional day only) vs 100 required → all timing
  metrics unavailable.
- **Decision: DATA_UNAVAILABLE / NEEDS HISTORY** (per the 1-row rule: not FAIL). The gate string
  is FAIL (correctly non-deployable) but the *research* status is a **data-availability failure,
  NOT a signal failure** — the edge was never testable. The `fiidiiTradeReact` endpoint has no
  historical backfill; cache only accumulates forward, one day per run.
- **Signal vs data failure:** purely a DATA failure. We have made no observation about whether
  FII/DII predicts index returns — 1 row proves nothing either way.
- **Spencer Score Impact: no change (stays ~48/100).** No alpha found or testable; no
  strategy/capability shipped. Only a process gain: another honest, no-fabrication ingest path
  with a clean DATA_UNAVAILABLE guard. Infrastructure robustness ≠ edge; score unchanged.

## Pattern note (two consecutive data walls)
Both NSE *event/flow* endpoints (block deals, FII/DII) are current-day-only or bot-protected →
no free historical backfill. Free NSE *price/positioning archives* (delivery, bhavcopy) have
full history; free NSE *event/flow APIs* do not. The remaining free + **historically deep**
source is **GDELT news tone** — chosen as the next automated research source so the pipeline
keeps moving without waiting on manual data collection.

## X. GDELT news sentiment (Codex) — reviewed + run → **DATA_UNAVAILABLE (API rate-limit)**
- **Implementation review:** Codex delivered `gdelt_news.py` — an auditable Nifty-50
  company→name map (aliases + notes per symbol), well-formed GDELT DOC queries
  (`sourcecountry:india sourcelang:english`, quoted OR aliases), tone+volume timelines merged,
  query-hash cache, `None` on insufficiency, **no fabrication** — and `news_sentiment_eval.py`
  (sentiment-shock event study, earnings/gap confounder control, `MIN_OBSERVATIONS=100`,
  `MIN_EVENTS=30`, DATA_UNAVAILABLE guard). **7 tests pass.** Code quality: high; correct.
- **Safety review (verified):** paper-only ✓; no live trading ✓; no broker execution/SDK ✓;
  no AI order approval ✓; no fabricated data/P&L ✓ (grep clean — only the module's own
  "no live trading" declarations match); no strategy deployment ✓. Gate: blocked, paper-only.
- **Research result:** DATA_UNAVAILABLE (recorded via automation; `record_news_sentiment_eval_rejection.md`).
- **Root cause (diagnosed by orchestrator, direct probes):** **GDELT API rate-limiting — HTTP
  429 Too Many Requests.** The eval fires ~100 requests in a burst (50 symbols × tone+volume)
  with `retries=1` and **no inter-request pacing/backoff**, so GDELT throttles and most
  companies return `None`. A direct 2-year query for RELIANCE (heavily covered) returned empty,
  and paced single requests still hit 429 — so it is **NOT** bad mapping, **NOT** weak coverage,
  **NOT** a cache or symbol-mismatch issue, **NOT** a date-range bug. It is an API query/rate
  limit. *Secondary, unconfirmed:* the GDELT DOC 2.0 API may also be ~3-month coverage-limited
  (could not measure while throttled).
- **Signal vs data:** purely a DATA-ACCESS failure (zero observations). No statement made about
  whether news predicts returns.
- **Spencer Score Impact: no change (stays ~48/100).** No alpha tested; only a process gain
  (a clean, auditable news-ingest path + company map). Infrastructure ≠ edge.

## Pattern note (data walls, continued)
Free NSE *price/positioning archives* have full history (delivery, bhavcopy). Free NSE
*event/flow APIs* (block deals, FII/DII) are current-day/bot-protected. GDELT *can* be free +
historical but its DOC API throttles aggressively and may be coverage-limited. The fix is an
access-engineering task (throttle/backoff/cache + a coverage probe + possible GKG/BigQuery
backfill), not a new source — GDELT is not yet proven unsuitable, only un-tuned.

## Y. GDELT rate-limit + coverage fix (Codex) — reviewed → **NEEDS_GKG_BIGQUERY_OR_BULK_DATA**
- **Implementation review:** Codex added real rate-limit safety to `gdelt_news.py` — 5s min
  inter-request delay, exponential backoff on `{429, 503}`, honors `Retry-After`, cache-first
  reads + duplicate-query prevention — plus a `coverage_probe()` over four 30-day windows
  (now / −6mo / −1y / −2y) and a nuanced `_coverage_decision()` that separates rate-limited,
  recent-only, and complete-coverage cases. Quality: high; honest; no fabrication.
- **Test note (important):** `15 tests pass` — BUT only after I freed disk space. The host was
  **100% full (0 bytes)**, which made 6 cache-writing tests ERROR with "No space left on device."
  I cleared the re-fetchable `.cache/nse_delivery` (165M; not a journal) → 15/15 pass. The 6
  errors were environmental, not code defects. **Operational flag: the disk is effectively full.**
- **Safety review (verified):** paper-only ✓; no live trading ✓; no broker execution/SDK ✓; no
  AI order approval ✓; no fabricated news/P&L ✓ (grep clean — only the modules' own declarations
  match); no strategy deployment ✓. Gate: `decision: FAIL`, `sourceModule: news_sentiment_eval`,
  blocked, paper-only.
- **Coverage-probe result (cached, no API hammering):** decision
  `DATA_UNAVAILABLE_INSUFFICIENT_HISTORY`; per-window merged-data: **current 1/3, −6mo 1/3,
  −1y 0/3, −2y 0/3** (8 windows `NOT_PROBED_CACHE_MISS`). The resolved windows show **recent
  data exists, historical (≥1y) does not**.
- **Root cause:** the **GDELT DOC 2.0 API is a recent-only window (~3 months)** — confirmed by
  the probe (recent windows return tone; 1y/2y return none across all 3 probe symbols). The
  throttling fix worked (no longer rate-limited); the wall is now *historical depth*, not access.
- **Decision (orchestrator): NEEDS_GKG_BIGQUERY_OR_BULK_DATA.** A historical news backtest needs
  GDELT **GKG** (BigQuery or bulk CSV, 2015+), not the DOC API. The DOC API + a slow scheduled
  collector is useful **forward-only** (NEEDS_SLOW_SCHEDULED_COLLECTOR) — viable for future data
  but cannot supply history now. NOT structurally unsuitable (GKG is suitable); the DOC path is.
  Per the rule: **do not keep hammering the DOC API for history.**
- **Spencer Score Impact: no change (stays ~48/100).** Still no alpha tested (no historical
  observations). Process gain only: a rate-limit-safe, auditable news-ingest path + an honest
  coverage probe. Infrastructure ≠ edge.

## Still open (owned by Codex / next cycles / operator)
- Codex: scope GDELT **GKG/BigQuery/bulk-CSV** historical news ingestion
  (`workflow/tasks/scope_gdelt_gkg_history.md`) — feasibility, access, cost, and a small
  proof-of-coverage before any full build. Stop using the DOC API for history.
- Operator: free up disk space on the host (currently ~100% full) so research caches/tests run.
- Operator (optional, revisitable): historical NSE bulk/block + FII/DII CSVs to re-test those.
- Strategy specs remain forbidden until a feature clears the same confirm-or-kill bar gap_up failed.
- Wire `regime_trust.json` into the live scanner's sizing (down-weight by current regime).
- Populate `signal_log` or standardize on `signal_candidates` as the decision log.
- Pre-existing test debt: 9 failures unrelated to this work (e.g. `coach.py` contains the
  string `binance` in a TradingView mapping, tripping the SDK-import guard).
