# Manual NSE Bulk/Block Deal CSVs

Drop real NSE bulk-deal or block-deal CSV exports in this folder when the
dynamic historical API is unavailable.

Accepted file naming:

- Include `bulk` in the filename for bulk-deal exports.
- Include `block` in the filename for block-deal exports.

Expected NSE columns:

- `Date`
- `Symbol`
- `Security Name`
- `Client Name`
- `Buy/Sell`
- `Quantity Traded`
- `Trade Price / Wght. Avg. Price`

Spencer reads these files before the static NSE archives and before the dynamic
API. Missing files simply mean no manual rows are available. The ingest never
creates placeholder deals, synthetic prices, fake P&L, or trading actions.
