---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/review_packet.md"
---
# review packet

> Managed mirror of `workflow/review_packet.md`. Edit the source file, not this copy.

# Spencer Review Packet

## Latest Task
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

## Latest Result
# Latest Result: build-repo-native-automation-bridge

- Status: passed
- Dry run: False
- Task: workflow\current_task.md
- Tests passed: 2
- Tests failed: 0
- Finished: 2026-06-03T14:55:53.361097+00:00

## Files Changed
- None detected

## Tests
- `python -m py_compile workflow/run_next.py workflow/review_packet.py`
  - return code: 0
  - skipped: False
- `python -m pytest tests/test_workflow_bridge.py`
  - return code: 0
  - skipped: False

## Safety Failures
- None

## Failures
- None

## Reviewer Notes
- GPT Reviewer: tests and safety gates passed; output remains advisory and paper-only.

## Files Changed
- None detected

## Tests
- Passed: 2
- Failed: 0

## Deployment Gate
- Paper only: True
- Deployment blocked: True
- Deployment allowed: False
- Live trading allowed: False
- Broker execution allowed: False
- AI order approval allowed: False
- Reason: DATA_UNAVAILABLE: only 1 real FII/DII flow row(s) available; 100 required. Do NOT build a strategy.

## Next Recommended Action
Send to GPT Reviewer; deployment remains blocked and Spencer stays paper-only.
