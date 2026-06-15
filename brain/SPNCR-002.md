---
tags: [spencer, candidate]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "scripts/export_brain.py"
---
# SPNCR-002 (v1) — KILLED

**Hypothesis:** On days when RELIANCE sets a new full-session (25-bar) closing high accompanied by the heaviest volume of the last three hours (12 bars), institutional participation tends to produce a directional drift day; entering on that breakout and riding the rest of the session with a wide 1% stop and a 10-bar trailing mean exit captures a large fraction of the 1.70% median daily range in fewer, larger trades whose size exceeds the ~0.2% real round-trip cost. This is a NEW hypothesis (range-breakout day-drift), not a parameter tweak of the killed SPNCR-001 (short-horizon momentum churn): it trades at most about once per day, holds toward session end, and uses breakout-of-extremes rather than mean-relative momentum. If breakout days do not drift enough to clear costs, the hypothesis is false and the candidate dies.

**Killed:** IN_SAMPLE failed (2026-06-12)

| Stage | Status | Trades | Net P&L (₹) |
|---|---|---|---|
| IN_SAMPLE | FAIL | 9 | -7.88 |

Measured against the [[Cost Bar]] across [[In-Sample]] → [[Out-of-Sample]] → [[Walk-Forward]].
Part of the [[Research Ledger]] · back to [[Spencer]].
