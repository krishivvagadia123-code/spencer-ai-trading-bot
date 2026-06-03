# Workflow Outbox

Codex, Antigravity, or local workflow scripts write completed result summaries here.

Each result should be safe to review and should not contain:

- `.env` values
- broker credentials
- private account data
- live order payloads
- fake P&L or fake trade states
- raw private market data

The latest result is also mirrored to `workflow/latest_result.md`.
