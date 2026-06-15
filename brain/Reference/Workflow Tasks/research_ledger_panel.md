---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/research_ledger_panel.md"
---
# research ledger panel

> Managed mirror of `workflow/tasks/research_ledger_panel.md`. Edit the source file, not this copy.

# Task: Research Ledger on the website — honest research history, kills included

## Objective
Surface Spencer's research truth on the dashboard: every candidate tested, its
verdict (including kills), and the journaled numbers behind it. The dashboard
currently shows only the paper account; it must also show what Spencer has
*learned* — exactly as recorded, never prettified.

## Context
- Source of truth: `backtest_runs` and `backtest_kills` tables in `kite_bot.db`,
  plus archived forms in `candidates/*.md`. Two candidates exist (SPNCR-001,
  SPNCR-002), both KILLED at IN_SAMPLE — they must be displayed as kills with
  their real negative net P&L. Voided/defect runs are NOT in the tables.
- Server: `spencer_quote_server.py` (:8787). Frontend: `frontend/src/App.jsx`.
- Scoreboard source: PROJECT_STATUS.md grades (functional 80 / profitability 4 /
  composite ~48) — serve these as static config read from a small JSON the
  manager maintains (`workflow/scoreboard.json`; create it with those values),
  never computed or invented by the frontend.

## Changes required

### 1. API: `GET /api/research/ledger` on the quote server
Returns, from the DB only:
- `candidates`: one entry per candidate_id+version with: hypothesis (from the
  stored candidate_json), status (KILLED / IN_PROGRESS / PASSED), kill reason +
  date if killed, and per-stage summaries (stage, status, trades, gross_pnl,
  total_costs, net_pnl, net_edge_pct, cost_bar_required_pct, dataset range).
- `scoreboard`: contents of `workflow/scoreboard.json` plus `updatedAt`.
- `dataCoverage`: per interval, first/last candle ts and session count from
  `intraday_prices`, and last `daily_prices` trade_date.
- No field may be synthesized; if a table is empty, return empty lists.

### 2. Frontend: "Research" panel
- New dashboard section listing candidates: ID, one-line hypothesis (truncate
  with expand), verdict badge (KILLED in red with date — kills are shown
  proudly, not hidden), and the stage table with the real numbers (gross, costs,
  net, edge vs bar). Show the scoreboard (functional/profitability/composite)
  and data coverage ("15m: N sessions, growing daily").
- Every number rendered must come from the API response; placeholder/sample
  data is forbidden. Empty state: "No candidates tested yet."
- Keep markup hooks/class names stable and semantic (Antigravity will restyle).

### 3. Tests
- API test against a temp DB with a seeded killed run: response carries the
  exact journaled numbers; empty-DB case returns empty lists; scoreboard comes
  from the JSON file.
- Frontend builds (`npm run build`).

## Safety Rules (unchanged, mandatory)
- Paper-only; no live trading; no broker execution; no AI order approval.
- Zero fake data: no sample/placeholder numbers anywhere, including loading
  states. Kills displayed exactly as journaled.
- Read-only over research tables; never write from the API path.
- Deployment gate stays blocked.

## Test Commands
- .venv/Scripts/python.exe -m pytest tests/ -q
- npm --prefix frontend run build

## Expected Output
- Working /api/research/ledger + Research panel showing SPNCR-001 and
  SPNCR-002 as kills with their real numbers; scoreboard and coverage visible.
- Full suite green; frontend builds. Commit locally; do NOT push.

## Out of Scope
- No visual redesign (Antigravity owns styling), no new research, no candidate
  changes, no score computation logic.
