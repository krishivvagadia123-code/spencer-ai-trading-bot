# Task: Event eval gap_up scan

## Objective
Run the event_eval research scan and let Spencer automatically decide whether event edges pass, fail, or need confirmation.

## Files Affected
- bot/event_eval.py
- bot/gapup_confirm.py
- workflow/research_automation.py
- workflow/tasks/event_eval_gap_up_scan.md
- workflow/tasks/confirm_gap_up_edge.md
- workflow/deployment_gate.json
- workflow/logs/

## Acceptance Criteria
- event_eval results are read by workflow/research_automation.py.
- Spencer records PASS, FAIL, or NEEDS CONFIRMATION.
- If gap_up survives OOS with caveats, workflow/tasks/confirm_gap_up_edge.md is created automatically.
- This source task is marked passed after the research result is logged.
- Deployment remains blocked unless validation passes.
- Spencer remains paper-only.

## Safety Rules
- Keep Spencer paper-only.
- Do not enable live trading.
- Do not add broker order placement.
- Do not invent dashboard data, trades, profits, P&L, or bot status.
- Do not delete journals.
- Do not bypass risk gates.
- Do not allow AI approval of orders.
- Antigravity displays only verified backend state.

## Test Commands
- python -m py_compile workflow/research_automation.py bot/event_eval.py bot/gapup_confirm.py
- python -m pytest tests/test_research_automation.py tests/test_event_eval.py tests/test_gapup_confirm.py

## Expected Output
- The workflow finalizer creates a next task when confirmation is needed.
- workflow/deployment_gate.json blocks deployment until validation passes.
- workflow/logs/ contains the research decision and reason.
