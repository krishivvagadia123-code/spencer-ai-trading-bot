# Spencer

Spencer is a private, paper-only AI trading research system for Indian-market research.
It is designed to test ideas, review evidence, and log workflow decisions before any
strategy can be considered.

Spencer is not a live trading system. This repository must not contain broker
credentials, live order execution wiring, private account data, or fake performance
claims.

## Current Safety Posture

- Paper-only: yes.
- Live trading: disabled.
- Broker execution: disabled.
- AI order approval: disabled.
- Deployment gate: blocked unless research validation explicitly passes.
- Fake dashboard data, fake P&L, fake trades, and invented bot status are forbidden.

See `workflow/deployment_gate.json` for the current backend gate state.

## What Spencer Does

- Runs read-only research modules against real data sources.
- Stores task specs under `workflow/tasks/`.
- Records workflow and research decisions under `workflow/logs/`.
- Uses `workflow/research_automation.py` to classify results and block deployment when
  validation fails.
- Keeps audit context in `AUDIT_REPORT.md`.
- Keeps the data-source roadmap in `DATA_SOURCE_RESEARCH_PLAN.md`.

## What Spencer Does Not Do

- It does not place broker orders.
- It does not enable live trading.
- It does not approve orders with AI.
- It does not invent trades, profits, P&L, dashboard state, or market data.
- It does not convert research directly into deployment.

## Repo-Native Workflow

Tasks move through:

```text
PLAN -> BUILD -> TEST -> REVIEW -> APPROVE -> LOG
```

Run a task with:

```bash
python workflow/pipeline.py --task workflow/tasks/current_task.md
```

Research modules should call `workflow.research_automation` so failed or
data-unavailable results automatically keep deployment blocked and create the next
paper-only task.

## Important Included Files

- `workflow/tasks/` - task source of truth.
- `.github/ISSUE_TEMPLATE/` - GitHub issue templates.
- `AUDIT_REPORT.md` - current audit and research history.
- `DATA_SOURCE_RESEARCH_PLAN.md` - data-source sequence and research roadmap.
- `PROJECT_STATUS.md` - current high-level status.
- `SECURITY.md` - credential and broker-safety policy.
- `CONTRIBUTING.md` - agent workflow rules.

## Local-Only Artifacts

Runtime databases, caches, logs, `.env` files, broker keys, private CSVs, and journals
must stay local. The `.gitignore` is intentionally defensive; review `git status`
before every commit.
