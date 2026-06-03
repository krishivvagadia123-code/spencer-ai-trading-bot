# Task: Record flows_eval rejection

## Objective
Archive the flows_eval failed research result, keep deployment blocked, and choose the next paper-only research hypothesis without enabling trading.

## Files Affected
- bot/flows_eval.py
- workflow/tasks/record_flows_eval_rejection.md
- workflow/research_automation.py
- workflow/deployment_gate.json
- workflow/logs/

## Acceptance Criteria
- The failed research result is documented without deleting journals.
- workflow/deployment_gate.json remains blocked because validation did not pass.
- No dashboard panel shows invented trades, P&L, profits, or bot status.
- The next paper-only research hypothesis is explicit and testable.

## Safety Rules
- Keep Spencer paper-only.
- Do not enable live trading.
- Do not add broker order placement.
- Do not invent dashboard data, trades, profits, P&L, or bot status.
- Do not delete journals.
- Do not bypass risk gates.
- Do not allow AI approval of orders.
- Antigravity must display only verified backend state.

## Test Commands
- python -m py_compile workflow/research_automation.py bot/flows_eval.py
- python -m pytest tests/test_research_automation.py tests/test_flows_eval.py
- python -m workflow.research_automation --check-deployment-gate

## Expected Output
- A rejection note or next research hypothesis is available in workflow/tasks/.
- workflow/deployment_gate.json blocks deployment.
- No live trading, broker order placement, or fake P&L is introduced.

## Source Research Decision
- Module: flows_eval
- Decision: FAIL
- Reason: DATA_UNAVAILABLE: only 1 real FII/DII flow row(s) available; 100 required. Do NOT build a strategy.
