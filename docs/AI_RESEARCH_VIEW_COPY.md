# AI Research View — Dashboard Panel Copy

Approved copy for the "AI Research View" panel on the Spencer dashboard. The
panel shows the local AI analyst's latest opinion on RELIANCE. It is research
only and never represents a trade or an instruction.

## Panel title
> AI Research View

## Disclaimer banner (always visible, top of panel)
> AI research opinion — not a trade, not a signal. Spencer's deployment gate stays blocked until a strategy is proven.

## Rating label
> Research rating: **{RATING}** · as of {ANALYSIS_DATE}

Example: `Research rating: Underweight · as of 2026-06-19`

- **Stale** (analysis older than the latest trading day) — append:
  `· last analysis {ANALYSIS_DATE} (not current)`
- **No analysis yet:**
  `No analysis yet — the AI runs after market close.`

## "How to read this" tooltip (2 sentences)
> This is one local AI model's view of RELIANCE from recent price and indicator data — it is often wrong and is not financial advice. Nothing here is acted on automatically; every idea must pass Spencer's own backtest and cost bar before it counts.
