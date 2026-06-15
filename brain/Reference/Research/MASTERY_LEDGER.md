---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "MASTERY_LEDGER.md"
---
# MASTERY LEDGER

> Managed mirror of `MASTERY_LEDGER.md`. Edit the source file, not this copy.

# MASTERY_LEDGER.md

## Spencer Daily Mastery Ledger

**System:** Spencer
**Mode:** Paper-only
**Stock:** RELIANCE only
**Paper Capital Basis:** ₹5,000
**Live Trading:** Blocked

---

## 1. Date and Market State

**Date:** `<YYYY-MM-DD>`

**Market State:** `<OPEN / CLOSED / HOLIDAY / DATA_UNAVAILABLE>`

**Review Completed After Market Close:** `<YES / NO>`

**Data Source Used:** `<daily_prices table / broker quote export / NSE official data / other approved source>`

**Data Timestamp:** `<timestamp from source>`

---

## 2. RELIANCE End-of-Day Data

**Symbol:** RELIANCE

**EOD Close:** `<from daily_prices table>`

**Previous Close:** `<from daily_prices table>`

**% Change:** `<calculated from real close and previous close>`

**Data Verified:** `<YES / NO>`

**If Data Unavailable, Reason:** `<reason>`

---

## 3. Trades Taken Today

### Trade Status

`<TRADE TAKEN / NO TRADE>`

### If No Trade

**Reason for No Trade:** `<rule blocked entry / no valid setup / market closed / data unavailable / risk limit / other>`

**Was No-Trade Decision Rule-Based:** `<YES / NO>`

### If Trade Taken

| Field               | Value                                          |
| ------------------- | ---------------------------------------------- |
| Entry Time          | `<journal timestamp>`                          |
| Entry Price         | `<from real quote / trade journal>`            |
| Exit Time           | `<journal timestamp>`                          |
| Exit Price          | `<from real quote / trade journal>`            |
| Quantity            | `<calculated from ₹5,000 paper capital rules>` |
| Gross P&L           | `<journal calculation>`                        |
| Brokerage           | `<charges table / broker fee model>`           |
| STT/CTT             | `<charges table>`                              |
| Exchange Charges    | `<charges table>`                              |
| SEBI Charges        | `<charges table>`                              |
| GST                 | `<charges table>`                              |
| Stamp Duty          | `<charges table>`                              |
| Total Fees/Charges  | `<sum of all charges>`                         |
| Net P&L After Costs | `<gross P&L - total charges>`                  |
| Journal Trace ID    | `<trade_journal id>`                           |

---

## 4. Rule Compliance Checklist

* [ ] Traded RELIANCE only.
* [ ] No other stock was analyzed for execution.
* [ ] Maximum one open position at any time.
* [ ] Paper capital basis remained exactly ₹5,000.
* [ ] No live order was placed.
* [ ] No broker execution was used.
* [ ] No AI order approval was allowed.
* [ ] Every displayed number traces to a journaled trade, timestamped quote, or approved data table.
* [ ] Market-closed state was shown correctly if the market was closed.
* [ ] No fake wins, fake losses, fake prices, fake strategy status, or fake P&L were shown.

**Compliance Result:** `<PASS / FAIL>`

**If Fail, Immediate Action:** `<block trading / fix UI / correct ledger / add rule / investigate>`

---

## 5. Mistake Analysis

**Did Spencer Make a Mistake Today:** `<YES / NO>`

**What Went Wrong:**
`<plain description>`

**Root Cause:**
`<bad rule / missing rule / bad data / UI issue / calculation issue / discipline issue / unknown>`

**Damage:**
`<net P&L impact after costs / no trade impact / data integrity impact>`

**Rule Added So It Cannot Repeat:**
`<new rule>`

**File / System Area to Update:**
`<strategy rules / UI / journal / charges model / data pipeline / validation gate>`

---

## 6. Running Mastery Scoreboard

**Consecutive Disciplined Days:** `<from mastery_scoreboard table>`

**Cumulative Net P&L After Costs:** `<sum from trade_journal after costs>`

**Approx. 1% Loss Tolerance Basis:** `<calculated from ₹5,000 paper capital>`

**Current Drawdown vs Tolerance:** `<calculated from journaled net P&L only>`

**Mastery Status:** `<NOT MASTERED / UNDER REVIEW / VALIDATION CANDIDATE>`

**Reason for Status:**
`<short reason based only on journaled evidence>`

---

## Final Operator Sign-Off

**Reviewed By:** `<operator name>`

**Review Time:** `<timestamp>`

**Ledger Locked:** `<YES / NO>`

**Notes:**
`<short notes only; no guesses, no predictions, no invented performance claims>`
