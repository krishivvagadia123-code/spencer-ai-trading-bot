---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "docs/research/day_selection_evidence_2026-06-12.md"
---
# day selection evidence 2026-06-12

> Managed mirror of `docs/research/day_selection_evidence_2026-06-12.md`. Edit the source file, not this copy.

# Day-selection evidence memo (input for SPNCR-003)

Source: Perplexity web research, 2026-06-12, commissioned by the manager.
Status: SECONDARY EVIDENCE — citations not independently verified; nothing here
is a tested Spencer result. Used only to shape the SPNCR-003 written hypothesis,
which must still survive the full RESEARCH_PROTOCOL.md ladder on our own data.

## Summary of findings (as reported)

1. **Overnight gap → rest-of-day drift: weak/contrarian.** No India- or
   RELIANCE-specific study found. A U.S. study (2011–2024) finds the opposite of
   continuation — an overnight-to-intraday *reversal* — whose alpha turns
   negative after costs. Gap-continuation as a hypothesis is unsupported.
2. **Volatility regime persistence: the strongest evidence.** Indian intraday
   studies (NSE index + stocks) find U-shaped intraday volatility with high
   GARCH persistence; Indian literature repeatedly documents volatility
   clustering. Yesterday's range is informative about today's range.
3. **Derivatives expiry effects: real in India.** NSE studies find expiry days
   and expiry weeks significantly raise spot volatility, with a spike in the
   last 30 minutes, larger for stock-futures names (RELIANCE is one).
4. **Opening-range breakout after costs: cautious/null in India.** An NSE ORB
   study calls the approach operationally appealing but unconfirmed once cost
   modeling and significance testing are demanded. Consistent with our own
   SPNCR-002 kill.

## Manager's implications for SPNCR-003 (design notes, not rules yet)

- Drop gap-continuation as the core idea (point 1).
- Build the day-selection filter on **volatility persistence** (point 2):
  qualify a day for trading only when the prior session's realized range is in
  its upper regime — aiming for fewer trades on days whose expected range can
  clear the ~0.62% cost bar that killed 001/002.
- Consider expiry-day/week as a secondary volatility qualifier (point 3), and
  avoid holding into the final 30 minutes on expiry days.
- Do not resurrect plain ORB (point 4 + SPNCR-002's journaled death).

## Engine gap to close before SPNCR-003 can be expressed

The backtest rule language (bot/intraday_backtest.py) has comparisons over
field/lag/rolling values but NO arithmetic (cannot express "high - low" or
"prior session range" or "gap %"). SPNCR-003 will need a small, candidate-
agnostic engine extension: precomputed per-candle context fields such as
prev_session_range_pct, gap_pct, and is_expiry_session, computed strictly from
past data. That is Codex's next build task, to be spec'd by the manager at
candidate design time.
