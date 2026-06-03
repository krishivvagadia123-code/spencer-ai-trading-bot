# Task: Build repo-native automation bridge

## Objective
Create a local file-based automation bridge so Spencer agents can coordinate through
repo files instead of manual prompt copy-pasting. The bridge must follow the Safety
Rules below and must not use external UI automation.

## Files Affected
- workflow/inbox/
- workflow/outbox/
- workflow/current_task.md
- workflow/latest_result.md
- workflow/agent_state.json
- workflow/run_next.py
- workflow/review_packet.py
- workflow/prompts/
- tests/test_workflow_bridge.py

## Acceptance Criteria
- Inbox, outbox, prompts, active task, latest result, and agent state files exist.
- `workflow/run_next.py` reads `workflow/current_task.md`, runs safety checks, runs test commands, writes `workflow/latest_result.md`, writes an outbox result, and updates `workflow/agent_state.json`.
- `workflow/review_packet.py` produces a short review packet with latest task, files changed, test results, deployment gate status, and next recommended action.
- The bridge refuses tasks that violate the Safety Rules before test commands run.

## Safety Rules
- Keep Spencer paper-only.
- Do not enable live trading.
- Do not add broker order placement.
- Do not allow AI approval of orders.
- Do not invent dashboard data, market data, trades, profits, P&L, or bot status.
- Do not delete journals.
- Do not commit `.env` files, credentials, broker keys, tokens, or private data.

## Test Commands
- python -m py_compile workflow/run_next.py workflow/review_packet.py
- python -m pytest tests/test_workflow_bridge.py

## Expected Output
- Files created for the bridge.
- `workflow/latest_result.md` summarizes the run.
- `workflow/agent_state.json` reports paper-only status and deployment gate state.
- Safety checks pass and unsafe tasks are blocked.
