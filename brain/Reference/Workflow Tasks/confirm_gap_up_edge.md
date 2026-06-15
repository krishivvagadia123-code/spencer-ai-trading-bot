---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/confirm_gap_up_edge.md"
---
# confirm gap up edge

> Managed mirror of `workflow/tasks/confirm_gap_up_edge.md`. Edit the source file, not this copy.

# Task: Confirm gap_up edge

## Objective
Confirm or kill the gap_up candidate from event_eval using more history, realistic gap-day slippage, clean holdout validation, and out-of-universe support before any paper-only strategy spec is allowed.

## Files Affected
- bot/event_eval.py
- bot/gapup_confirm.py
- workflow/tasks/confirm_gap_up_edge.md
- workflow/research_automation.py
- workflow/deployment_gate.json
- workflow/logs/

## Acceptance Criteria
- The gap_up result is confirmed or killed with stricter OOS validation.
- The confirmation run writes PASS, FAIL, or NEEDS CONFIRMATION through workflow/research_automation.py.
- Deployment remains blocked unless validation passes.
- If validation passes, the next generated task is still paper-only.

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
- python -m py_compile workflow/research_automation.py bot/event_eval.py bot/gapup_confirm.py
- python -m pytest tests/test_research_automation.py tests/test_event_eval.py tests/test_gapup_confirm.py
- python -m workflow.research_automation --check-deployment-gate

## Expected Output
- A confirmation result for gap_up is written to workflow/logs/.
- workflow/deployment_gate.json blocks deployment until validation passes.
- The old research task status sidecar is marked passed with the research decision recorded.

## Source Research Decision
- Module: event_eval
- Decision: NEEDS CONFIRMATION
- Reason: 1 of 2 tested event types show a cost-adjusted edge that survives walk-forward: gap_up. CAVEAT: testing multiple buckets and finding 1 survivor is weak evidence. This is a CANDIDATE to confirm with more history, realistic gap-day slippage, and a holdout check - NOT to be deployed.
