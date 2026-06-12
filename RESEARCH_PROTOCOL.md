# RESEARCH_PROTOCOL.md

## Spencer Research Protocol

**System:** Spencer
**Mode:** Paper-only
**Stock:** RELIANCE only
**Paper Capital Basis:** ₹5,000
**Live Trading:** Blocked
**Data Rule:** Zero fake data

---

## 1. Candidate Definition

No trading technique may be tested until it is written as a complete mechanical rule set.

A candidate must define, before testing:

* **Market:** RELIANCE only.
* **Timeframe:** `<daily / intraday candle interval>`.
* **Data source:** `<approved real data source>`.
* **Entry rule:** exact conditions that trigger entry.
* **Exit rule:** exact conditions that close the trade.
* **Stop-loss rule:** exact price, percentage, candle, volatility, or invalidation condition.
* **Position sizing rule:** quantity calculated from the ₹5,000 paper capital basis.
* **No-trade conditions:** exact cases where Spencer must stay out.
* **Execution assumption:** exact candle/quote used for simulated entry and exit.
* **Slippage assumption:** `<from approved slippage model>`.
* **Cost model:** `<from docs/RELIANCE_COST_MATH.md>`.
* **Invalid data rule:** what happens if required data is missing, delayed, or inconsistent.

Vague descriptions are not candidates.

Rejected examples of vague language:

* "Buy momentum."
* "Enter when trend looks strong."
* "Trade breakout if volume is good."
* "Exit when weakness appears."
* "Let AI decide."

A valid candidate must be executable by code without human interpretation.

---

## 2. The Cost Bar

A candidate must clear the cost bar before it can be considered useful.

Required rule:

**Expected edge per trade must be at least 3× the RELIANCE round-trip trading cost.**

The round-trip cost value must be read from:

`<from docs/RELIANCE_COST_MATH.md>`

Spencer must not restate, guess, or hardcode the cost value inside this protocol.

A candidate fails the cost bar if:

* Results are positive only before fees.
* Results disappear after brokerage, taxes, charges, and slippage.
* Average expected edge is less than 3× round-trip cost.
* The cost model is missing, stale, or unverifiable.
* Any result is quoted without costs.

No candidate may graduate on gross P&L.

Only net results after all costs and slippage matter.

---

## 3. Testing Ladder

Every candidate must pass the full testing ladder in order.

### Step 1 — In-Sample Backtest

The candidate is tested on real RELIANCE candles using the exact rules defined before testing.

Requirements:

* Use real historical candle data only.
* Apply all fees, charges, and slippage.
* Use the fixed ₹5,000 paper capital basis.
* Record trade count, gross P&L, total costs, net P&L, drawdown, and rule violations.
* Store results with dataset range, data source, timestamp, and candidate version.

If the candidate fails in-sample, testing stops.

### Step 2 — Out-of-Sample Holdout

The same candidate rules must be tested on unseen RELIANCE data.

Requirements:

* No parameter changes after in-sample testing.
* No date-range adjustment after seeing results.
* No removal of losing periods.
* Costs and slippage must remain enabled.
* Results must be stored separately from in-sample results.

If the candidate fails out-of-sample, testing stops.

### Step 3 — Walk-Forward Test

The candidate must survive walk-forward evaluation using real historical RELIANCE data.

Requirements:

* Parameters must be selected only from past data.
* Future data must remain unseen at each step.
* Costs and slippage must be applied in every step.
* Performance must remain stable enough to justify paper testing.
* Any instability must be recorded, not hidden.

If the candidate fails walk-forward, it is dead.

A candidate must survive all three stages before paper trading.

---

## 4. Kill Criteria

A candidate is declared dead if any of the following occur:

* It fails the cost bar.
* It is profitable before costs but not after costs.
* It fails the in-sample test.
* It fails the out-of-sample holdout.
* It fails the walk-forward test.
* It depends on one unusual date range to look profitable.
* It only works after repeated parameter tweaking.
* It requires removing losing trades, losing days, or losing regimes.
* It produces results that cannot be traced to real data.
* It uses invented candles, invented fills, invented prices, or invented trade outcomes.
* It needs subjective human judgment to decide entries or exits.
* It violates the one-stock RELIANCE rule.
* It violates the ₹5,000 paper capital basis.
* It requires more than one open position at a time.
* It cannot be reproduced from the saved candidate definition and saved dataset.

Once killed, a candidate may not be revived by small parameter changes.

A modified version must be treated as a new candidate only if it has a new written hypothesis, new mechanical rules, and a clear reason that is not based on curve-fitting the failed result.

No overfitting by iteration.

---

## 5. Graduation

A surviving candidate does not earn live trading.

A surviving candidate earns only:

**Paper-trading permission on RELIANCE only.**

Graduated paper trading must follow these rules:

* Trade RELIANCE only.
* Use exactly ₹5,000 paper capital basis.
* Allow at most one open position at a time.
* Journal every signal, trade, no-trade decision, quote, fill assumption, fee, charge, and net result.
* Review every market day using `MASTERY_LEDGER.md`.
* Mark missing data as `DATA_UNAVAILABLE`.
* Show `Market Closed` when the market is closed.
* Keep live trading blocked.

A graduated candidate can be demoted if daily review shows rule violations, cost failure, data integrity issues, or repeated uncorrected mistakes.

---

## 6. Forbidden Practices

The following are banned:

* Cherry-picked date ranges.
* Changing date ranges after seeing results.
* Keeping only winning parameter sets.
* Hiding failed parameter tests.
* Quoting results without costs.
* Quoting gross P&L as if it is real performance.
* Ignoring brokerage, taxes, charges, or slippage.
* Inventing fills.
* Inventing prices.
* Inventing trade outcomes.
* Inventing strategy status.
* Inventing market state.
* Using fake "testing" labels when no real test is running.
* Allowing AI to approve live orders.
* Connecting results to broker execution.
* Adding another stock before RELIANCE mastery is proven.
* Treating backtest survival as a profit guarantee.

If a number cannot be traced, it must not be shown.

If a rule is not mechanical, it must not be tested.

If a candidate cannot survive costs, it must not be traded.
