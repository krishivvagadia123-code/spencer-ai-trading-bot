# Task: Build repo-native workflow system

## Objective
Create a local workflow system for Spencer so tasks are stored, executed, reviewed, and logged inside the project without manual prompt copying between AI tools.

## Files Affected
- workflow/pipeline.py
- workflow/agents/claude_manager.md
- workflow/agents/codex_builder.md
- workflow/agents/gpt_reviewer.md
- workflow/agents/antigravity_designer.md
- workflow/agents/trading_authority.md
- workflow/logs/
- .github/ISSUE_TEMPLATE/feature_request.md
- .github/ISSUE_TEMPLATE/research_task.md
- .github/ISSUE_TEMPLATE/safety_review.md
- .github/ISSUE_TEMPLATE/backtest_report.md

## Acceptance Criteria
- Tasks can be stored as Markdown or JSON.
- Each task includes objective, files affected, acceptance criteria, safety rules, test commands, and expected output.
- The pipeline reads pending tasks or a specific task path.
- The pipeline follows PLAN -> BUILD -> TEST -> REVIEW -> APPROVE -> LOG.
- The pipeline runs listed test commands.
- The pipeline writes JSON and Markdown logs under workflow/logs/.
- The pipeline writes a task status sidecar file.
- The pipeline blocks unsafe changes.
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
- python -m py_compile workflow/pipeline.py
- python workflow/pipeline.py --task workflow/tasks/current_task.md --dry-run
- python -m pytest tests/test_workflow_pipeline.py

## Expected Output
- Pipeline validates this task.
- Safety gates pass.
- Tests pass.
- Logs describe task result, files changed, tests run, failures, and reviewer notes.
