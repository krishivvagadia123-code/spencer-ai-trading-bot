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

## What Counts as Sensitive

Beyond broker credentials, treat these as secrets in this project:

- **LLM API keys** — Gemini/OpenAI/Google keys in `backend/.env` and the
  research tools' `.env`.
- **`SPENCER_API_TOKEN`** — the shared token gating the mutating backend
  endpoints (`backend/.env`; mirrored to `webapp/.env` for local dev only).
- **The Cloudflare tunnel URL** — exposes the local backend to the internet.
  The backend behind it must stay read-only for the public; mutating endpoints
  require the token. Do not paste the live tunnel URL into public places.
- **Social login cookies** — captured by Agent-Reach under `~/.agent-reach/`;
  local-only, never committed.
- **The local SQLite DBs and journals** — `kite_bot.db`, `backtest_*.db`,
  `trades.csv` — contain the real paper-trading record.

## Secret Handling

Use local environment variables / `.env` files for private values, and keep
them out of Git. Confirm coverage with `git check-ignore <file>` and run
`python scripts/secret_scan.py` (read-only) before pushing.

### Key-rotation policy

Rotate a key immediately if it is exposed — including being **pasted into a chat
or shared with a tool**, not only when committed to Git:

1. Revoke/regenerate the key at its provider (e.g. Google AI Studio for Gemini).
2. Update the local `.env` file(s) with the new value; never print it back.
3. If it ever reached Git, remove it from history before the next push.
4. Re-run `python scripts/secret_scan.py` and a quick safety review.

## Incident Checklist

When a secret may be exposed:

1. **Contain** — revoke/rotate the affected key now.
2. **Assess** — was it ever committed? `git log -S '<fragment>' --all`. Was the
   repo public at the time?
3. **Clean** — purge from working tree and history if present; re-run `secret_scan.py`.
4. **Replace** — issue a new secret, update `.env`, restart the backend.
5. **Record** — note what leaked, when, and the fix in this project's notes.

## Reporting Issues

For this private project, report security issues directly to the repository owner.
Do not open public issues containing credentials, account identifiers, private data,
logs, journals, or broker state.
