# Spencer — Data-Source Research Plan (v1)

> Orchestrator: Claude Manager. Status: research planning only.
> **No strategy is built here. Spencer stays paper-only. Nothing deployed, no live wiring.**

## Why this plan exists
Seven independent tests (daily Nifty-50, intraday Nifty-50, Midcap-100, and the gap_up
confirm-or-kill) found **no stable, cost-clearing, walk-forward-robust edge in free NSE
price/event data.** Conclusion: the *signal source* is the bottleneck, not the method. Our
IC / event-study framework is sound and reusable — it just needs **non-price data** to test.

This plan scopes seven candidate data sources on the same honest criteria we apply to every
result: what data, where to get it, free vs paid, how we would test it, expected cost,
realistic edge potential, and which module to build next. The test method is unchanged:
read-only predictive-power measurement (IC / event study, in-sample vs out-of-sample,
quintile spread, cost-adjusted, walk-forward) **before** any strategy is ever discussed.

---

## Summary (prioritised)

| # | Data source | Free? | Granularity | Edge potential | Feasibility | Tier |
|---|-------------|-------|-------------|----------------|-------------|------|
| 2 | **Delivery volume %** (NSE) | ✅ Free | Per-stock, daily | Medium–High (positioning, not price) | Medium (NSE archive ingest) | **1 — build first** |
| 3 | **Bulk / block deals** (NSE) | ✅ Free | Per-stock, event | Medium (institutional footprint) | Medium | 1 |
| 6 | **FII/DII flows** (NSE/SEBI) | ✅ Free | Market-level, daily | Medium (regime/timing only) | Easy | 2 |
| 5 | **Sector rotation** | ✅ Free | Sector-level | Low–Medium (semi price-derived) | Easy | 2 |
| 4 | **Earnings/result reaction** | ◐ Mostly free | Per-stock, event | Medium (we already have surprise%) | Easy | 2 |
| 1 | **Historical news / sentiment** | ◐ Free via GDELT / Paid otherwise | Per-stock/sector, event | High (genuinely new) | Hard (mapping, noise) | 3 |
| 7 | **Unusual volume confirmed by news** | Depends on #1 | Per-stock, event | High (volume + catalyst) | Hard (needs #1) | 3 |

"Tier 1" = free, per-stock, genuinely non-price, and plugs straight into the existing IC
framework → highest value per unit of effort. We recommend building **#2 delivery volume**
first (the Codex task below).

---

## Per-source detail

### 2. Delivery volume %  — ✅ TESTED → ❌ FAIL (no edge)
> **Result (2026-06-03):** Built (`bot/nse_delivery.py` + `bot/delivery_eval.py`) and run on
> real NSE archives. **Data availability excellent** (Nifty-50 22,981 obs / Midcap-100 43,617
> obs). **No feature usable** — ICs flip sign or are <0.03, quintile spreads below the 0.30%
> cost hurdle, no walk-forward survival. Decision: **FAIL** (deployment stays blocked). See
> AUDIT_REPORT.md section T. The data is great; the *signal* has no 5-day predictive edge.

### 2. Delivery volume %  (original scoping, kept for reference)
- **What's needed:** daily deliverable quantity and delivery % per NSE symbol (the share of
  traded volume that resulted in actual delivery vs intraday churn). High/rising delivery %
  signals conviction/positioning that price+volume alone do not capture.
- **Where:** NSE "Security-wise Delivery Position" / full bhavcopy
  (`sec_bhavdata_full_DDMMYYYY.csv`) from NSE archives. Libraries: `jugaad-data`,
  `nsepython` (both flaky; need retry/caching). yfinance does NOT carry this.
- **Free vs paid:** Free (NSE public archives). Cost = ingestion engineering + rate-limit care.
- **How tested:** features = `delivery_pct`, `delivery_pct_zscore` (vs 20d), `delivery_spike`
  (high delivery + above-avg volume). Run the existing IC framework (IS/OOS IC, quintile
  spread, cost-adjusted, monthly stability, walk-forward) vs 5-day forward returns, on
  Nifty-50 then Midcap-100. Pure read-only measurement.
- **Expected cost:** ₹0 data; ~1 build task. **Data risk:** NSE may rate-limit/anti-bot the
  archive; history depth via free libs may be limited → document honestly like we did for news.
- **Edge potential:** Medium–High. Delivery-based positioning is a classic Indian-market
  signal and is *not* derivable from OHLCV, so it's a real new axis.
- **Next module:** `bot/delivery_eval.py` (ingest + IC eval). → Codex task filed.

### 3. Bulk / block deals  — ⏸️ NEEDS MANUAL HISTORY (data access added; edge untestable yet)
> **Status (2026-06-03):** data-access implemented + tested (manual CSV + static archive +
> source precedence; 11 tests pass; safety clean; no synthetic fallback). **Run result:**
> with the static archive only (no manual CSVs yet), Nifty-50 had **0 usable events** — the
> recent-only archive's deals land on small/mid-caps outside Nifty-50. Module reports
> DATA_UNAVAILABLE (0 < 30 events); gate stays FAIL/blocked.
> **Orchestrator decision: NEEDS MANUAL HISTORY** (a data gap, not a signal failure — the
> edge was never testable). To proceed: an operator downloads real NSE bulk/block CSVs for a
> multi-year range into `data/block_deals/` (instructions:
> `workflow/tasks/blockdeals_manual_history.md`), then `blockdeal_eval` is re-run.
> Research continues meanwhile with FII/DII flows. See AUDIT_REPORT.md §U and §V.
- **What:** daily bulk & block deal disclosures (buyer/seller, qty, price) per stock.
- **Where:** NSE dynamic API (bot-blocked) / static archive (recent-only) / manual CSV download.
- **Free vs paid:** Free (data access is the constraint, not cost).
- **How tested:** event study (like gap_up) once history is available; buy-side vs sell-side.
- **Edge potential:** Medium (institutional footprint), but noisy/sparse — and now also data-gated.
- **Next module:** unblock data access first (`blockdeals_data_access.md`), then run the study.

### 6. FII/DII flows  — ⏸️ DATA_UNAVAILABLE / NEEDS HISTORY (built + run 2026-06-03)
> **Status:** module built (`bot/nse_flows.py` + `bot/flows_eval.py`, 6 tests pass; safety clean;
> no fabrication; `MIN_OBSERVATIONS=100`). **Run result: only 1 real FII/DII row** — NSE's
> `fiidiiTradeReact` endpoint returns the current provisional day only (no historical backfill;
> the cache accrues forward, one day per run). Gate stays FAIL/blocked.
> **Decision: DATA_UNAVAILABLE / NEEDS HISTORY** (1 row ⇒ data gap, not a signal failure — the
> edge was never testable). Revisitable later via historical FII/DII CSVs (NSE report / NSDL FPI).
> See AUDIT_REPORT.md §W.
- **What:** daily provisional FII & DII net cash buy/sell (market-level).
- **Where:** NSE `fiidiiTradeReact` (current-day only) / historical via manual CSV / NSDL FPI.
- **How tested:** market-timing IC vs index forward returns (regime/timing only, NOT selection).
- **Edge potential:** Medium for timing; cannot select stocks — and now also history-gated.
- **Next module:** revisit with manual history later; meanwhile pivot to GDELT news (§1).

### 5. Sector rotation
- **What:** relative performance/breadth across NSE sector indices.
- **Where:** sector index data (free). **Caveat:** this is *semi price-derived* — borderline
  against the "stop price-only" rule. Use breadth/relative-strength-of-sectors, not raw price.
- **How tested:** does leading-sector membership predict forward returns out-of-sample? IC.
- **Cost:** ₹0. **Edge potential:** Low–Medium; likely the same mean-reversion noise we saw.
- **Decision:** lower priority; only after Tier 1 since it risks repeating the null result.

### 4. Earnings / result reaction
- **What:** post-result drift conditioned on surprise%, plus reaction magnitude/volume.
- **Where:** we ALREADY pull earnings dates + `Surprise(%)` (yfinance). Extend with reaction
  features (gap on result day, volume, delivery on result day if #2 lands).
- **How tested:** event study already prototyped in `event_eval` (earnings_beat/miss). Earlier
  result: drift was positive in-sample, **failed OOS**. Worth re-testing *conditioned on
  delivery/volume* once #2 exists (interaction effects).
- **Cost:** ₹0. **Edge potential:** Medium, but standalone earnings drift already failed OOS.

### 1. Historical news / sentiment  — high potential, hard
- **What:** timestamped news + sentiment per stock/sector for an event study.
- **Where / free vs paid:**
  - **GDELT** (free): global news tone, has India coverage, historical — the best *free* path,
    but entity→NSE-symbol mapping is noisy.
  - **NewsAPI / Marketaux / Finnhub** (freemium → ~$0–450/mo): limited history on free tiers.
  - **RavenPack / Bloomberg / Refinitiv** (enterprise, $$$$$): clean but far out of scope.
  - **Build-forward** (free): start capturing RSS/news now for future study (no history today).
- **How tested:** event study around sentiment shocks; forward return, cost-adjusted, OOS,
  walk-forward. Must control for overlap with earnings/gaps (confounding).
- **Expected cost:** ₹0 (GDELT, build-forward) to ~$450/mo (freemium) to $$$$$ (enterprise).
- **Edge potential:** High (genuinely new catalyst data) **if** mapping/noise is solved.
- **Decision:** Tier 3 — prototype with **GDELT free** only after Tier 1; treat as R&D.

### 7. Unusual volume confirmed by news
- **What:** volume shocks that coincide with a news catalyst (filters out noise-only spikes).
- **Where:** requires #1 (news) + price volume. 
- **How tested:** event study on volume-shock days *with* a same-day news hit vs without.
  Recall: volume-shock alone showed ~zero edge — the hypothesis is that *news-confirmed*
  shocks differ.
- **Cost:** depends on #1. **Edge potential:** High if #1 is solved; blocked until then.

---

## Recommendation & sequencing
1. ~~Build `bot/delivery_eval.py` first~~ — ✅ done, ❌ **FAIL** (no edge; see §2 / AUDIT §T).
2. **NEXT → `bot/blockdeal_eval.py`** (free NSE bulk/block deals, event study like gap_up).
3. Then `bot/flows_eval.py` (FII/DII market-timing overlay).
4. R&D track: GDELT-based news sentiment (free) — separate spike, treat as exploratory.

**Status of the search:** 1 of 7 sources tested (delivery → FAIL). Data availability was the
good news — NSE archives are fully usable — so the remaining free NSE sources (bulk/block
deals, FII/DII) are worth testing on the same plumbing before concluding.

Each module is **read-only predictive-power measurement only**. A strategy spec is allowed
**only after** a feature survives the same confirm-or-kill bar gap_up just failed
(realistic costs, IS/OOS, holdout, walk-forward, both universes). Deployment stays blocked
by `workflow/deployment_gate.json`.

## What does NOT change
- Spencer is paper-only. No live trading, no broker order placement, no trust-into-sizing.
- No fabricated data/P&L. Data-availability limits are reported honestly (as with news).
- `AUDIT_REPORT.md` is updated each cycle with the honest result.
