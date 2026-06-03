# Contributing

Spencer contributions must preserve the paper-only research boundary.

## Agent Workflow

All repo-native tasks should move through:

```text
PLAN -> BUILD -> TEST -> REVIEW -> APPROVE -> LOG
```

Use task files in `workflow/tasks/` as the source of truth. A task should include:

- objective
- files affected
- acceptance criteria
- safety rules
- test commands
- expected output

Run tasks with:

```bash
python workflow/pipeline.py --task workflow/tasks/<task>.md
```

## Agent Roles

- Claude may orchestrate research and turn goals into task files.
- Codex may edit approved repo files and run verification.
- GPT reviews safety, strategy logic, evidence, and tests.
- Antigravity may display only verified backend truth.
- Trading Authority is the final deterministic backend decision layer.

No agent may bypass risk gates, enable live trading, approve orders, or invent data.

## Coding Rules

- Keep changes scoped to the task.
- Prefer existing module patterns over new abstractions.
- Add tests when changing research logic, workflow policy, or safety gates.
- Report DATA_UNAVAILABLE honestly when real data is missing or insufficient.
- Do not convert research output into entries, exits, sizing, broker orders, or deployment.

## Safety Rules

- Keep Spencer paper-only.
- Do not enable live trading.
- Do not add broker order placement.
- Do not commit broker keys or `.env` files.
- Do not invent dashboard data, trades, profits, P&L, market data, or bot status.
- Do not delete journals locally unless a task explicitly says they are being archived or
  excluded from Git.
- Do not bypass risk gates.
- Do not allow AI approval of orders.

## Before Opening a PR

1. Review `git status` for private files.
2. Confirm `.env`, databases, caches, logs, manual data, and journals are not staged.
3. Run the task's declared tests.
4. Update `AUDIT_REPORT.md`, `PROJECT_STATUS.md`, or workflow task files when the
   research state changes.
5. Confirm `workflow/deployment_gate.json` still blocks deployment unless validation
   explicitly passed.
