# Project Status

Status date: 2026-06-03

## Summary

Spencer is a private paper-only AI trading research system. It is currently a
research and workflow platform, not a deployable live trading system.

## Current Score

Approximate Spencer score: 48/100.

Reason: multiple research cycles improved infrastructure and safety, but no feature has
yet produced a validated, cost-clearing, walk-forward-surviving edge. Infrastructure
robustness does not raise the score by itself.

## Safety State

- Paper-only: true.
- Deployment allowed: false.
- Deployment blocked: true.
- Live trading allowed: false.
- Broker execution allowed: false.
- AI order approval allowed: false.
- Fake dashboard data allowed: false.

Current gate source: `workflow/deployment_gate.json`.

## Current Research Findings

- Delivery-volume research: failed as a signal. Data coverage was good, but ICs did not
  show stable OOS predictive power and cost-clearing walk-forward survival.
- Bulk/block-deal research: data-access path exists, but the edge remains untestable
  without enough historical manual NSE CSVs.
- FII/DII flows: official NSE endpoint produced only the current provisional day, so the
  result is DATA_UNAVAILABLE until enough real historical rows are accumulated or supplied.
- Gap-up/event work: no strategy spec is allowed until confirmation gates pass.

## Known Limitations

- No validated alpha source yet.
- Some free NSE event/flow endpoints are current-day-only or bot-protected.
- Manual historical CSVs may be required for block-deal or FII/DII retests.
- Research modules are read-only and must not create strategy deployment code.
- Pre-existing test debt is documented in `AUDIT_REPORT.md`.

## Next Tasks

- Keep deployment blocked until a research module passes validation.
- Record and triage `workflow/tasks/record_flows_eval_rejection.md`.
- Optionally supply historical NSE bulk/block CSVs under `data/block_deals/` for retesting.
- Continue the next historically deep data-source research track from
  `DATA_SOURCE_RESEARCH_PLAN.md`.
- Keep `AUDIT_REPORT.md` updated after every research cycle.

## Files That Should Remain Included

- `workflow/tasks/`
- `AUDIT_REPORT.md`
- `DATA_SOURCE_RESEARCH_PLAN.md`
- `.github/ISSUE_TEMPLATE/`
- `workflow/research_automation.py`
- `workflow/pipeline.py`
- `workflow/agents/`
