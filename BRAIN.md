# BRAIN.md — Spencer System: Single Source of Truth

> Generated 2026-06-25. This file reverse-engineers the whole Spencer system so an
> AI agent or developer can understand, debug, extend, test, deploy, and maintain
> it with minimal extra exploration. **Read this before touching anything.** When
> code and this doc disagree, the code wins — but update this doc in the same PR.

---

## 0. The one thing you must internalize first

Spencer is a **paper-only, single-stock trading-research system** governed by a
hard constitution (`SPENCER_CONCEPT.md`). It is NOT a trading bot that makes money.
It is a disciplined research harness whose entire value is **honesty**: every number
on screen traces to a real journal row, a real timestamped quote, or a documented
"data unavailable" state. The system is deliberately *boring and restricted*.

**Five invariants that must never be violated** (breaking any is a P0 bug):

1. **Paper only, forever** until research validation explicitly unlocks live. No
   broker execution, no live orders, no AI order approval, no auto-trading.
2. **Capital is exactly ₹5,000.** Never inflate, fake, or silently change it.
3. **One stock: RELIANCE.** Max one open position. No second stock until RELIANCE
   is "mastered" (consistent journaled profit after all costs).
4. **Zero fake data.** No fake prices/trades/results/status. Market closed → say
   "Market Closed". Missing data → say "Data unavailable". Never guess.
5. **Deployment gate stays blocked** (`workflow/deployment_gate.json`,
   `decision: "FAIL"`). The live engine refuses to trade until a candidate
   carries a journaled `WALK_FORWARD PASS`.

Current state (2026-06-25): **3 candidates tested, 3 killed, 0 validated edges.**
Profitability score 4/100. The live engine correctly refuses every live run.

---

## 1. Where things live

- **Repo root:** `C:\Users\krish\OneDrive\Desktop\AI TRADE` (Windows, under OneDrive).
- **GitHub:** `krishivvagadia123-code/spencer-ai-trading-bot`, branch `main` (public).
- **Live site:** https://spencer-ai-trading-bot.vercel.app (Vercel, auto-deploys on push to `main`, project root = `webapp`).
- **Backend:** runs on the PC at `127.0.0.1:8787`, exposed publicly via **Tailscale Funnel** at the stable URL `https://msi.tail65193b.ts.net`.
- **External research tools (separate, OUTSIDE the repo):** `C:\Users\krish\research-tools` (OpenBB, TradingAgents+Ollama, Agent-Reach). Research inputs only; never part of the paper bot.

### Top-level map
```
AI TRADE/
├─ SPENCER_CONCEPT.md      # THE constitution (the 5 invariants). Read first.
├─ RESEARCH_PROTOCOL.md    # Candidate definition + Confirm-or-Kill ladder + kill criteria
├─ PROJECT_STATUS.md       # Live status, research findings ledger (prose)
├─ docs/RELIANCE_COST_MATH.md   # The cost wall every technique must clear
├─ spencer_quote_server.py # THE backend (:8787). Quotes, journal API, brain, governance
├─ paper_engine.py         # Legacy multi-stock engine (pre-epoch; not the research path)
├─ kite_bot.db             # SQLite journal — THE source of truth for numbers (GITIGNORED)
├─ bot/                    # Engine library: backtest, charges, live paper, candidates, data
├─ scripts/                # Runnable tools: ladder, pipeline, scans, history, schedulers
├─ workflow/               # Orchestration: gate, scoreboard, tasks, research findings JSON
├─ candidates/             # SPNCR-*.json (machine spec) + .splits.json + .md (archive)
├─ tests/                  # 60 pytest files (full suite ~545 tests)
├─ brain/                  # Obsidian vault (markdown) indexed by backend for chat/search/graph
├─ webapp/                 # Vite + React + Tailwind v4 frontend (the live site)
└─ tmp/, archive/, data/   # scratch / retired / misc
```

---

## 2. Architecture & data flow

```
                 REAL DATA                       PAPER JOURNAL (truth)
        Yahoo Finance (yfinance)            kite_bot.db (SQLite, gitignored)
        RELIANCE.NS quotes/candles      ┌─ trades (legacy + epoch round trips)
                  │                      ├─ backtest_runs / backtest_kills
                  ▼                      ├─ live_paper_runs / _trades / _decisions
        ┌───────────────────┐           ├─ daily_prices (2,829) / intraday_prices (7,669)
        │ spencer_quote_     │◀──reads───┤ bot_state (epoch, budget, heartbeat)
        │ server.py (:8787)  │           ├─ research_snapshots / signal_candidates
        │  stdlib http.server│           └─ (epoch = "one_stock_reliance_v1", id > 15)
        └─────────┬─────────┘
        /api/* JSON │  (GET open; mutating GET/POST need X-Spencer-Confirm token)
                    │
       Tailscale Funnel (service)  →  https://msi.tail65193b.ts.net
                    │
                    ▼
        webapp/ (Vite/React) on Vercel  ── reads apiBase from public/spencer-config.json
        spencer-ai-trading-bot.vercel.app   (runtime, no rebuild needed to re-point)

   RESEARCH PIPELINE (offline, writes to kite_bot.db ledger, NEVER trades):
     research_scan*.py  →  candidates/SPNCR-*.json + .splits.json
        →  scripts/research_pipeline.py  →  bot/intraday_backtest.run_ladder
           (IN_SAMPLE → OUT_OF_SAMPLE → WALK_FORWARD; each must net>0 AND clear cost bar)
        →  PASS unlocks live paper;  FAIL → record_kill (permanent)
```

**Why this shape:** the backend is a persistent stateful Python server, so it can't
live on Vercel (which is serverless). The frontend is static and deploys to Vercel;
it reaches the backend through the Tailscale funnel. The journal DB is the single
source of truth — the backend only *reads* it for display; the research pipeline and
collectors *write* it.

---

## 3. The backend — `spencer_quote_server.py` (:8787)

Plain Python stdlib `ThreadingHTTPServer` (no framework). Key responsibilities:
real Yahoo quotes, serving the paper journal as JSON, the Obsidian "brain"
(chat/search/graph over `brain/*.md`), governance snapshot, and workflow status.

### Endpoints (GET unless noted)
| Path | Purpose |
|---|---|
| `/api/quotes?symbols=RELIANCE` | Real Yahoo quote rows + `lastSnapshotDate` |
| `/api/chart?symbol=RELIANCE&interval=5m` | Candles for the live chart |
| `/api/health` | Data-readiness + integrity checks (auditor) |
| `/api/analysis` | AI research opinion (`workflow/analysis_latest.json`, Ollama) |
| `/api/research`, `/api/research/ledger` | Research row + candidate ledger/scoreboard |
| `/api/bot/state`, `/api/bot/status` | Dashboard state from the real journal (epoch-scoped) |
| `/api/governance` | Capabilities snapshot (all live actions = blocked) |
| `/api/workflow/status`, `/api/handoff` | Workflow/task state |
| `/api/brain/{status,search,context,recall,note,graph}` | Obsidian brain |
| `/api/trades-resets` | **Trades & Resets view**: every paper trade + resets-to-₹5,000 count |
| POST `/api/ai/chat`, `/api/bot/{start,stop,config,reset}`, `/api/brain/{capture,reindex}` | Mutating — require `X-Spencer-Confirm` == write token |

### Epoch logic (critical — get this right or numbers lie)
The account "epoch" isolates the current RELIANCE-only run from legacy multi-stock
history. Stored in `bot_state`: `account_epoch="one_stock_reliance_v1"`,
`account_epoch_basis_inr=5000`, `account_epoch_started_at="2026-06-11 22:45:46"`,
`account_epoch_trade_id_start=15`. Helpers: `_epoch_context()`, `_epoch_filter()`
(returns `id > 15`), `_epoch_trade_rows()`, `_portfolio_from_epoch_trades()`.
**All displayed P&L/holdings/metrics must be epoch-filtered** so the 15 legacy
pre-epoch `trades` rows (NHPC/NESTLEIND/POWERGRID etc.) never leak into RELIANCE
numbers. The 3 `ONE_STOCK_RESET` sell rows (same timestamp, 2026-06-11) are the
epoch-establishing close = "reset to ₹5,000" event (count = 1).

### What breaks if you modify it
- Remove epoch filtering → legacy trades pollute RELIANCE P&L (fake data violation).
- Change a GET to require auth → frontend (no token in prod) breaks silently.
- Add a fabricated fallback value anywhere → doctrine violation #4.

---

## 4. The journal DB — `kite_bot.db` (SQLite, **gitignored**)

It is runtime data, regenerable from collectors/backfills, so it is NOT in git.
Tables (row counts as of 2026-06-25):

| Table | Rows | Meaning |
|---|---|---|
| `trades` | 15 | Legacy + epoch round trips. Epoch rows are `id > 15` (currently none). |
| `backtest_runs` | 4 | Every ladder stage run (status, dataset range, summary, trades JSON). |
| `backtest_kills` | 3 | Permanent kill registry: `(candidate_id, version, params_hash, reason)`. |
| `live_paper_runs` / `_trades` / `_decisions` | 4 / 1 / 4 | Forward paper engine runs (dry-run + would-be live). |
| `daily_prices` | 2,829 | Real RELIANCE.NS daily OHLCV (2015→now), backfilled via yfinance. |
| `intraday_prices` | 7,669 | Real 15m/1m candles (the only data the backtest engine reads). |
| `bot_state` | 15 | Key/value: epoch, budget, heartbeat, selected_strategy, etc. |
| `research_snapshots` | 187 | Periodic research state. |
| `signal_candidates` | 5,442 | Legacy signal scan output. |

**Read-only access pattern used everywhere:** `sqlite3.connect(uri, uri=True)` with
`?mode=ro`. Writes happen only in the research pipeline, collectors, and the (gated)
live engine.

---

## 5. Cost model & the cost bar — `bot/charges.py` + `docs/RELIANCE_COST_MATH.md`

`calculate_charges()` is calibrated to Zerodha's calculator: intraday brokerage
0.03% capped at ₹20/order, STT 0.025% sell-side (intraday) / 0.1% both sides
(delivery), NSE exchange txn, SEBI fee, 18% GST on (brokerage+exchange+SEBI),
stamp duty, DP charge (delivery sell). Returns a `ChargeBreakdown`.

**The cost bar (the wall every technique must clear):**
- Intraday round-trip breakeven ≈ **0.106%** of notional (scales with size).
- Delivery 1-share breakeven ≈ **1.484%** (fixed DP charge dominates at small size).
- A candidate must show **expected edge per trade ≥ 3× round-trip cost** (≈0.32%
  intraday) net of all charges AND slippage. The backtest engine actually charges
  ~0.2% round-trip in practice (charges + slippage), more conservative than 0.106%.
- The research scans use 0.106% (intraday) / 0.25% (daily) as *screening* bars only.

**Implication baked into the doctrine:** intraday 1–3 shares is the only cost-viable
frequent mode at ₹5,000; delivery needs multi-day moves > ~1%.

---

## 6. Candidate definition & the Confirm-or-Kill ladder

### Anatomy of a candidate (`candidates/SPNCR-NNN.*`)
- `SPNCR-NNN.json` — machine spec (validated by `bot/research_candidates.load_candidate`).
- `SPNCR-NNN.splits.json` — **pre-registered** date splits (in_sample / out_of_sample /
  walk_forward). Per protocol these are written BEFORE the run and never changed after.
- `SPNCR-NNN.md` — human archive with the journaled verdict.

### The rule DSL (`bot/research_candidates.py`) — know its limits
- `symbol` must be `RELIANCE`; `interval` ∈ {`1m`,`15m`}; `side` ∈ {`LONG`,`SHORT`}.
- Operands: `{value}` (scalar), `{rolling: max|mean|min, field, window}`,
  `{context: ...}`, `{field: open|high|low|close|volume}`.
- `ALLOWED_CONTEXT_FIELDS` = `prev_session_range_pct`, `prev_session_close`,
  `gap_pct`, `session_minute`, `is_expiry_session`.
- Operators: comparison only (`> >= < <= == !=`). **No arithmetic** (can't express
  `1.5 × mean(volume,20)` or close-location `(close-low)/(high-low)`).
- Forbidden keys block any future/lookahead reference. `params_hash` = SHA-256 of
  the frozen rule set (used by the kill registry to forbid identical retests).

### The ladder (`scripts/run_testing_ladder.py` → `bot/intraday_backtest.run_ladder`)
Stages run in order; each must PASS to proceed: **IN_SAMPLE → OUT_OF_SAMPLE →
WALK_FORWARD**. `stage_passed()` requires `status == "PASS"` AND `net_pnl > 0` AND
`cost_bar_pass` (net edge per trade ≥ required 3× cost). Any FAIL → `record_kill()`
(permanent; a modified version is a *new* candidate only with a new hypothesis, not
curve-fitting). DATA_INSUFFICIENT if a split is missing or too few bars.

### The pipeline wrapper (`scripts/research_pipeline.py`)
Thin orchestrator over `run_ladder`: refuses to re-test a killed
`(id, version, params_hash)`, persists ledger rows, appends one line to
`workflow/pipeline_results.jsonl`. **This is the "research_pipeline" entry point.**
Run: `python scripts/research_pipeline.py --candidate candidates/X.json --splits candidates/X.splits.json`.

### History so far (all journaled in `backtest_kills`)
- **SPNCR-001** (15m long momentum) — KILLED in-sample.
- **SPNCR-002** (15m breakout drift) — KILLED in-sample (profitable gross, not net).
- **SPNCR-003** (gap-up fade SHORT) — KILLED in-sample (net −₹133.54, 2/11 wins).
  Lesson: a session-average move that "clears cost" is NOT a per-trade edge once a
  stop + costs apply.

---

## 7. The backtest engine — `bot/intraday_backtest.py` (and the BIG blocker)

Forward-only replay over real candles. **It is INTRADAY ONLY:**
- It reads from `intraday_prices` **only** (not `daily_prices`).
- It **force-squares-off at the end of every session** (`must_square_off`, ~line 582)
  — so it physically cannot hold a position across days.

**Consequence (the #1 structural blocker):** the daily research lane
(`scripts/daily_history.py` backfilled 2,829 real daily bars;
`research_scan_daily.py` / `research_scan_multiday.py` mine them) found **no
single-day daily edge clears cost** — only `close_to_close_drift` is significant
(t=2.51) but +0.081%/day is ~3× too small. The only remaining hope is **multi-day
holds** (volatility-compression breakout, volume-climax reversal), and those are
**untestable until a multi-day-hold engine exists**. Building that engine + adding
DSL arithmetic is the next real unlock. Until then, daily candidates can't graduate.

Pass criteria detail: `run_backtest` computes `net_edge_per_trade_pct_of_notional`,
`cost_bar_required_pct` (3× round trip), `cost_bar_pass`; `status = "PASS" if
net_pnl > 0 and cost_bar_pass else "FAIL"`.

---

## 8. The live paper engine — `bot/live_paper_trader.py`

Two modes via `scripts/run_live_paper.py`:
- **dry-run** (`run_dry_run`): replays a candidate over one collected session's real
  candles. A simulation; **no PASS gate** (but still paper-only). This is the only
  way trades appear in `live_paper_trades` today (1 row: SPNCR-002 dry-run, −₹8.01).
- **live** (`run_live`): the market-hours forward loop. **Double-gated:**
  1. `workflow/deployment_gate.json` must assert `paperOnly` and all live flags false
     (else `GateError`).
  2. The candidate must be unkilled AND carry a journaled `WALK_FORWARD PASS`
     (else `CandidateNotApprovedError`). **No candidate qualifies today, so live
     mode always REFUSES — that is the correct, expected state.**

The live quote source reuses `spencer_quote_server._quote_rows` (real Yahoo), and
only runs after the PASS gate clears (never today).

---

## 9. The frontend — `webapp/` (Vite + React 18 + Tailwind v4 + motion)

- **Entry/routing:** `src/App.jsx` holds `activePage` state (no router lib) and
  renders one page at a time inside `<main className="content-scroll ...">`.
  `Header` + `NavigationDrawer` are siblings outside `main`.
- **Pages** (`src/pages/`): `Dashboard`, `Orders`/`Holdings`/`Positions` (Orders nav),
  `Funds`/`TradeTracker`/`TradesResets` (Funds nav), `Brain`/`Research` (Brain nav),
  `Bids`, `Governance`, `Profile`, `WhatIsSpencer`.
- **Hooks** (`src/hooks/`): `useBotState`, `useQuotes`, `useHealth`, `useResearch`,
  `useResearchLedger`, `useTradesResets`, `useObsidianBrain`, `useLocalProfile`.
  All read `SPENCER_API_BASE` from `src/utils/constants.js`.
- **Runtime API base:** `src/main.jsx` fetches `/spencer-config.json` (no-store) on
  boot → sets `window.__SPENCER_API_BASE__` → `constants.js` uses it (fallback
  `VITE_SPENCER_API_BASE` then `127.0.0.1:8787`). `public/spencer-config.json`
  `apiBase` = the stable ts.net funnel. **Re-point the live backend by editing that
  file — no rebuild needed.** Dev (`.env`) points at `127.0.0.1:8787`. Dev server
  port is **5180 only** (`npm run dev`, strictPort).
- **Theming (`src/index.css`) — FRAGILE, read this:** there are **two coexisting
  theme systems**: legacy light `--color-*` (in the Tailwind `@theme` block) and the
  current dark `--theme-*` (on `:root`, `--theme-bg #242835`, `--theme-text #f4f1ff`).
  The redesign layered dark rules over the old light ones, leaving **duplicate /
  conflicting rules** (e.g. `.glass-metric`, `.data-health-panel`, `.story-*`). When
  fixing visual bugs, prefer appending an override block (source order wins) or inline
  styles, and force readable colors via `--theme-text` / `--theme-muted`.

### Known frontend gotchas (already bitten us)
- **`position: sticky` + ancestor `overflow`:** an ancestor with `overflow-x: hidden`
  (we had it on `.page-content`) silently makes itself the scroll container and breaks
  sticky pinning for descendants. **Fix is `overflow-x: clip`** (clips without
  becoming a scroll container). The "What is Spencer" scroll-pinned story
  (`ScrollStory.jsx`) depends on this.
- **Scroll-pin heights:** `ScrollStory` measures the real scroll-container height via
  `ResizeObserver` and pins at `top:0` with inline heights — do NOT reintroduce
  magic-number `calc(100dvh - Nrem)` heights (they assume a header size and break).
- **The RELIANCE chart (`RelianceLiveChart.jsx`):** custom SVG line chart computed in
  **real pixel coordinates** (viewBox == measured pixel size, `ResizeObserver`). The
  live dot is an SVG `<circle>` **inside the same `<svg>` as the line** so it sits on
  the last point by construction — never reintroduce a separate HTML-overlay dot
  (different coordinate system → drifts off the line). Hover crosshair + price readout
  are SVG too. (`lightweight-charts` is bundled but currently unused.)
- **OneDrive + Vite HMR:** the repo is under OneDrive, which interferes with Vite's
  file watcher — HMR can serve stale modules. If a change isn't reflecting, **restart
  the dev server** and hard-refresh the browser (Ctrl+Shift+R). Verify what's actually
  served with `curl http://localhost:5180/src/...jsx`.

---

## 10. The "brain" (Obsidian vault) — `brain/` + `scripts/export_brain.py`

`brain/*.md` is an Obsidian knowledge vault. `scripts/export_brain.py` regenerates
the managed notes (`managed: true` frontmatter, `source_path` points at the
generator); the daily pipeline runs it. The backend indexes every `brain/*.md` for
`/api/brain/{search,context,graph,chat}`, so writing a note there feeds the brain.
`brain/Daily/*` snapshots are gitignored (they churn). Research scans write
`brain/Latest Research Scan.md` and `brain/Latest Daily Research Scan.md`.

---

## 11. Scheduled tasks & operational behavior (Windows Task Scheduler)

Registered via `scripts/register_*.ps1` (operator runs once each):
- **SpencerDailySnapshot** → `run_daily_market_data.ps1`: EOD snapshot + `research_scan`
  + brain export, every trading day.
- **SpencerAgentAnalysis** → Ollama market-analyst (in the research-tools venv) writes
  `workflow/analysis_latest.json`, served by `/api/analysis` ("AI Research View").
  Research opinion ONLY; gate stays blocked. Needs Ollama running.
- **SpencerIntradayCollect** → intraday candle collector (feeds `intraday_prices`).
- **SpencerBackend** (`register_backend_autostart.ps1`) — **registrar exists but is
  NOT actually registered on this PC.** The backend has been running as manually
  launched processes, so it has **no reboot/crash auto-recovery**. The Tailscale
  *funnel* is a resilient Windows service (survives reboots), but the Python backend
  on :8787 is not. **To harden: operator runs `register_backend_autostart.ps1` once
  (Admin PowerShell).** Until then, relaunch manually:
  `Start-Process .venv\Scripts\python.exe -ArgumentList '-u','spencer_quote_server.py' -WorkingDirectory "AI TRADE"`.

`scripts/scheduler_healthcheck.py` checks task health. If the live site shows
"Backend unavailable", the PC backend or the funnel is down.

---

## 12. Deployment & the data path

1. **Frontend:** push to `main` → Vercel rebuilds `webapp/` → live in ~1 min. Verify
   via the Vercel deployments list (state `READY`, target `production`). Roll back with
   Vercel "Instant Rollback" (prior deploy is a one-click revert).
2. **Backend data path:** the live site reads `apiBase` (ts.net funnel) → funnel →
   `127.0.0.1:8787`. Live data flows only while **PC + backend (:8787) + Tailscale
   service** are all up. `tailscale funnel status` to check; `tailscale funnel --bg 8787`
   to re-enable.
3. **After a backend code change:** restart the :8787 process (it's not auto-reload)
   and confirm both `127.0.0.1:8787/api/health` and the funnel URL serve the new code.

---

## 13. Security

- Mutating endpoints require header `X-Spencer-Confirm` == `SPENCER_WRITE_TOKEN`
  (constant-time compare via `_valid_write_token`). Token lives in `backend/.env` +
  `webapp/.env` (both gitignored) and is **NOT set on Vercel**, so the public site
  cannot trigger writes / spend the Gemini key. Localhost dev has the token.
- CORS echoes the Vercel origin. Repo is public but verified clean of secrets
  (`scripts/secret_scan.py`, `SECURITY.md`). A valid free Gemini key was once shared
  in chat (in `research-tools/TradingAgents/.env`) and **should be rotated**.

---

## 14. The multi-AI team workflow (how changes get made)

Krishiv runs a multi-AI team; **Claude Code is the manager/orchestrator** and single
point of truth:
- **Claude (manager):** owns all frontend design/styling, owns git (commits + pushes
  every reviewed change to `main`), independently verifies all work (runs tests
  itself), writes task specs. **Never lets Codex push.** Every reply opens with the
  scoreboard (Functional / Profitability / Composite) and includes ready-to-paste
  prompt sections for ChatGPT and Codex.
- **Codex (engineer):** executes one task spec at a time, commits **locally only**.
- **ChatGPT:** document drafter. **Perplexity:** web research. **Antigravity: removed**
  (it edited frontend against instructions and broke the UI).
- **git is the sync point.** Krishiv pastes other AIs' output back for review.
- **Self-verify rule:** after every change, confirm it actually took effect
  (test passes / commit pushed / Vercel deploy READY / backend restarted / endpoint
  responds) before reporting done.

---

## 15. Risks, technical debt & bottlenecks

| Item | Severity | Notes |
|---|---|---|
| Engine is intraday-only | **High** | Blocks all multi-day/daily candidates. Daily data exists (2,829 bars) but can't be tested. Needs a multi-day-hold backtest mode. |
| Backend not auto-restart | **High** | `SpencerBackend` task not registered → live site loses data on reboot/crash. Operator must run the registrar. |
| Dual-theme CSS | Medium | Legacy `--color-*` + dark `--theme-*` with duplicate/conflicting rules → recurring contrast/blending bugs. |
| Rule DSL has no arithmetic | Medium | Can't express `k×rolling` or close-location filters → ChatGPT's better hypotheses aren't directly expressible. |
| Thin intraday history | Medium | ~64 sessions of 15m candles → selective filters yield near-zero trades. Collector grows it daily. |
| OneDrive vs Vite HMR | Low (dev) | File-watcher misses changes; restart dev server to refresh. |
| `kite_bot.db` gitignored | By design | Numbers live only on the PC; regenerable via collectors/backfills. Back it up. |
| Quick-tunnel legacy scripts | Low | `START_LIVE_TUNNEL.bat` / `wire_tunnel.ps1` are retired Cloudflare fallbacks; Tailscale is the live path. |

---

## 16. Conventions

- **Honesty over polish:** never display a number you can't trace. Prefer "Data
  unavailable" / "Market Closed" / "awaiting first real quote" to a guess.
- **Pre-register splits** before any backtest; never change them after seeing results.
- **Kills are permanent;** a tweaked candidate is new only with a new written
  hypothesis (no curve-fitting by iteration).
- **Scores move only on journaled evidence,** never on infrastructure. Profitability
  rises only from a validated, cost-clearing edge.
- **Frontend stays dark-glass + high-contrast text;** the structural background is in
  `index.css` base styles, not a wrapper class.
- **Python:** dedicated read-only SQLite (`?mode=ro`); real data only; no order
  placement in research code; RELIANCE-only; never touch the deployment gate.
- **Commits** end with the `Co-Authored-By: Claude` trailer; reviewed work is pushed
  to `main` by the manager.

---

## 17. Common tasks (runbook)

```bash
# Run a candidate through the ladder (the research pipeline)
python scripts/research_pipeline.py --candidate candidates/SPNCR-00X.json \
                                    --splits   candidates/SPNCR-00X.splits.json

# Read-only research scans (write findings JSON + brain notes)
python scripts/research_scan.py            # intraday EDA over intraday_prices
python scripts/research_scan_daily.py      # daily EDA over daily_prices
python scripts/daily_history.py --start 2015-01-01   # backfill real daily candles

# Dry-run the live engine over one collected session (simulation, no gate)
python scripts/run_live_paper.py --candidate candidates/SPNCR-002.json --mode dry-run

# Tests (verify before pushing)
.venv/Scripts/python.exe -m pytest -q            # full suite (~545)

# Backend: run / verify
python spencer_quote_server.py                   # serves :8787
curl http://127.0.0.1:8787/api/health            # local
curl https://msi.tail65193b.ts.net/api/health    # via funnel (prod path)

# Frontend: dev / build
cd webapp && npm run dev      # http://localhost:5180 (strictPort)
cd webapp && npm run build    # production build (Vercel does this on push)
```

---

## 18. Pointers (read these next, in order)

1. `SPENCER_CONCEPT.md` — the constitution (the 5 invariants).
2. `RESEARCH_PROTOCOL.md` — candidate definition + ladder + kill criteria.
3. `docs/RELIANCE_COST_MATH.md` — the cost wall.
4. `PROJECT_STATUS.md` — current status + research findings ledger.
5. `bot/research_candidates.py` + `bot/intraday_backtest.py` — the engine + DSL.
6. `bot/live_paper_trader.py` — the gated live engine.
7. `spencer_quote_server.py` — the backend + epoch logic.
8. `webapp/src/App.jsx` + `webapp/src/index.css` — the UI shell + theming.

> Maintenance note: when you change the engine, DSL, gate, epoch logic, or theming,
> update the relevant section here and bump the date at the top. This file is only
> useful if it stays true.
