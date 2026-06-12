# CANDIDATE_TEMPLATE.md

## Spencer Candidate Technique Form

**System:** Spencer
**Mode:** Paper-only
**Stock:** RELIANCE only
**Paper Capital Basis:** ₹5,000
**Governing Rulebook:** `RESEARCH_PROTOCOL.md`

---

## Candidate ID

Write the unique candidate identifier before testing begins.
`<candidate_id>`

## Version

Write the candidate version before testing begins.
`<version>`

## Date Written

Write the date this candidate form was completed.
`<YYYY-MM-DD>`

## Written Hypothesis

Write one falsifiable paragraph explaining why this edge should exist in RELIANCE specifically.
`<hypothesis_paragraph>`

## Timeframe/Interval

Write the exact candle timeframe or interval used for this candidate.
`<timeframe_or_interval>`

## Data Source

Write the approved real data source used for testing.
`<approved_real_data_source>`

## Entry Rule (Mechanical)

Write the exact mechanical conditions that trigger entry, with no human interpretation required.
`<entry_rule>`

## Exit Rule (Mechanical)

Write the exact mechanical conditions that close the trade, with no human interpretation required.
`<exit_rule>`

## Stop-Loss Rule (Mechanical)

Write the exact mechanical stop-loss condition.
`<stop_loss_rule>`

## Position Sizing Rule (From ₹5,000)

Write the exact quantity-sizing rule using the fixed ₹5,000 paper capital basis.
`<position_sizing_rule>`

## No-Trade Conditions

Write the exact conditions where Spencer must not trade.
`<no_trade_conditions>`

## Execution Assumption

Use fill at next candle open after signal.
`<fill_at_next_candle_open_after_signal>`

## Slippage Assumption

Reference the approved slippage model only.
`<from approved slippage model>`

## Cost Model Reference

Reference the RELIANCE cost math document only.
`<from docs/RELIANCE_COST_MATH.md>`

## Invalid-Data Rule

Write the exact rule for missing, delayed, inconsistent, or unverifiable data.
`<invalid_data_rule>`

## Parameters Table

List every parameter before testing begins, including value, allowed range, and justification.

| Name               | Value               | Allowed Range     | Justification     |
| ------------------ | ------------------- | ----------------- | ----------------- |
| `<parameter_name>` | `<parameter_value>` | `<allowed_range>` | `<justification>` |

## Pre-Registered Date Splits

Fix all testing ranges before testing begins.

| Test Stage           | Pre-Registered Range / Windows |
| -------------------- | ------------------------------ |
| In-Sample Range      | `<in_sample_range>`            |
| Out-of-Sample Range  | `<out_of_sample_range>`        |
| Walk-Forward Windows | `<walk_forward_windows>`       |

## Kill Acknowledgment

Write and sign the acknowledgment that this candidate dies permanently if it fails any stage.
`<I acknowledge that this candidate dies permanently if it fails the cost bar, in-sample test, out-of-sample holdout, walk-forward test, data-integrity checks, or any rule in RESEARCH_PROTOCOL.md. Author: <author_name>. Date: <YYYY-MM-DD>.>`

---

## Form Rules

* No field may be left vague.
* No parameter may be added after testing begins.
* No parameter may be changed after testing begins.
* No date split may be changed after testing begins.
* No result may be quoted without costs and slippage.
* No invented number may be used anywhere in this form.
* A failed candidate's form is archived, never edited.
