# Security Policy

Spencer is a private, paper-only research repository. Treat every credential,
database, journal, and private market-data file as sensitive.

## Never Commit

- `.env` files.
- Broker API keys, broker secrets, access tokens, or request tokens.
- Live account identifiers.
- SQLite databases or local trading journals.
- Runtime logs with account, order, or local machine details.
- Private CSVs or manually downloaded market-data files.
- Any file containing live broker credentials or order-execution state.

## Broker Safety

This repository must remain paper-only.

- Do not enable live trading.
- Do not add broker order placement.
- Do not wire research output into broker execution.
- Do not allow AI approval of orders.
- Do not bypass risk gates.

If broker SDK packages are present as dependencies, they must not be used to place live
orders in Spencer. Any broker integration must remain disabled unless a future task
explicitly changes the project scope and receives a separate safety review.

## Secret Handling

Use local environment variables for private values. Keep `.env` files out of Git.

If a secret is accidentally committed:

1. Revoke or rotate it immediately.
2. Remove it from the repository history before pushing.
3. Re-run a safety review before using the repo again.

## Reporting Issues

For this private project, report security issues directly to the repository owner.
Do not open public issues containing credentials, account identifiers, private data,
logs, journals, or broker state.
