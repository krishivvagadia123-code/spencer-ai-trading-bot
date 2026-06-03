# Trading Authority

## Purpose
Trading Authority is the deterministic backend layer that owns paper-trading state, risk gates, action permissions, and audit truth.

## Owns
- Paper strategy signals.
- Risk gates.
- Paper journal integrity.
- Backend action capability flags.
- Live-trading blocks.
- Audit logs and source-of-truth state.

## Must Defer
- UI presentation to Antigravity Designer.
- Architecture changes to Claude Manager.
- Code implementation to Codex Builder.
- Explanatory review to GPT Reviewer.

## Must Never Do
- Enable live trading without an audited broker adapter and explicit double gate.
- Use AI analysis as order approval.
- Delete journals to make results look cleaner.
- Bypass risk gates.

## Spencer Rule
Spencer remains paper-only. Broker execution and live order placement are blocked by default and must stay blocked in this workflow.

## Automatic Workflow Rule
Trading Authority is the final backend decision layer for paper state, risk gates, journal integrity, and deployment gating. No agent can bypass this layer, and Trading Authority cannot use AI analysis as order approval.
