# Task: Collect & upload NSE bulk/block-deal history (operator action)

## Objective
Unblock block-deal edge research by supplying REAL historical NSE bulk/block-deal CSVs that the
free static archive cannot provide (it carries only recent days, and those deals rarely touch
Nifty-50). This is an OPERATOR data-collection task, not a code change. No fabrication: only real
NSE exports. Spencer stays paper-only; no strategy, no deployment.

## Why this is needed
- `blockdeal_eval` ran with the static archive only and got **0 usable Nifty-50 events** →
  DATA_UNAVAILABLE / NEEDS MANUAL HISTORY (see AUDIT_REPORT.md §V).
- The dynamic NSE historical API is bot-protected (503). The static archive is recent-only.
- A browser session CAN download bulk/block deals for any date range — so an operator can
  supply the history the bot cannot fetch.

## How to collect (operator steps)
1. Open NSE in a browser: https://www.nseindia.com/report-detail/display-bulk-and-block-deals
2. For **Bulk Deals**: pick a date range (do it in ≤1-year chunks if the site limits range),
   then download the CSV. Repeat for **Block Deals**.
3. Aim for at least ~2 years (ideally 5) so per-bucket samples can exceed MIN_EVENTS=30 after
   filtering to a universe. Bulk/block deals are sparse, so more history is better.
4. Save the files into `data/block_deals/` with names that contain "bulk" or "block"
   (the loader keys on the filename), e.g.:
   - `data/block_deals/bulk_2022.csv`, `bulk_2023.csv`, `bulk_2024.csv`, `bulk_2025.csv`
   - `data/block_deals/block_2022.csv`, ... etc.
5. Keep the standard NSE export columns (the loader already handles them):
   `Date, Symbol, Security Name, Client Name, Buy/Sell, Quantity Traded, Trade Price / Wght. Avg. Price`.
   Do NOT edit, synthesize, or hand-enter rows — upload the raw NSE export only.

## Acceptance Criteria (verification, after CSVs are added)
- `python -c "from bot import nse_block_deals as n; df=n.load_manual_deals(); print(None if df is None else (len(df), sorted(df['deal_type'].unique())))"`
  returns a non-trivial row count from real files.
- Re-running `python -m bot.blockdeal_eval --top 50 --include-midcap` yields
  `used_events >= 30` in at least one bucket (so an edge test is possible), OR an honest
  DATA_UNAVAILABLE if coverage is still too thin — never fabricated events.
- Orchestrator then records the real PASS / FAIL / NEEDS CONFIRMATION in AUDIT_REPORT.md.

## Safety Rules
- Keep Spencer paper-only. No live trading. No broker order placement.
- Do not invent dashboard data, trades, profits, P&L, or bot status.
- Do not synthesize or hand-edit deal rows — upload only real NSE exports.
- Do not delete journals. Do not bypass risk gates. No AI order approval.

## Out of Scope
- No trading strategy, no sizing, no entry/exit logic. No deployment. No paid data.
- Do not attempt to defeat NSE bot-protection; manual browser download is the supported path.
