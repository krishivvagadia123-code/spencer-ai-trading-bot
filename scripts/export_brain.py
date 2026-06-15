"""Export Spencer's knowledge into a large, cross-linked Obsidian vault (brain/).

Two layers:
  - DYNAMIC notes built from REAL data (scoreboard.json, the backtest journal of
    runs + kills, the integrity auditor, today's collected candles).
  - STATIC knowledge notes: real definitions of Spencer's concepts, data sources,
    research findings, components, and the AI team — densely cross-linked with
    [[wikilinks]] so the Obsidian graph is rich.

Everything is factual: definitions describe how Spencer actually works, and all
numbers come from live sources. Read-only over the database; writes only inside
brain/. Re-run any time (idempotent).

Usage:  python scripts/export_brain.py
Obsidian: "Open folder as vault" -> select brain/.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.obsidian_brain import ObsidianBrain

DB_PATH = ROOT / "kite_bot.db"
SCOREBOARD_PATH = ROOT / "workflow" / "scoreboard.json"
BRAIN_DIR = ROOT / "brain"


# ── helpers ──────────────────────────────────────────────────────────────────

def _ro_conn(db_path: Path):
    return sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _candidates(db_path: Path) -> list[dict]:
    if not db_path.exists():
        return []
    runs: dict[tuple, dict] = {}
    with _ro_conn(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT candidate_id, candidate_version, stage, status, summary_json,"
                " candidate_json FROM backtest_runs ORDER BY id").fetchall()
        except sqlite3.OperationalError:
            rows = []
        try:
            kills = conn.execute(
                "SELECT candidate_id, candidate_version, reason, created_at"
                " FROM backtest_kills ORDER BY id").fetchall()
        except sqlite3.OperationalError:
            kills = []
    kill_map = {(k["candidate_id"], k["candidate_version"]): dict(k) for k in kills}
    for r in rows:
        key = (r["candidate_id"], r["candidate_version"])
        entry = runs.setdefault(key, {"id": r["candidate_id"], "version": r["candidate_version"],
                                      "hypothesis": "", "stages": []})
        try:
            cj = json.loads(r["candidate_json"]) if r["candidate_json"] else {}
        except json.JSONDecodeError:
            cj = {}
        if cj.get("hypothesis"):
            entry["hypothesis"] = cj["hypothesis"]
        try:
            summary = json.loads(r["summary_json"]) if r["summary_json"] else {}
        except json.JSONDecodeError:
            summary = {}
        entry["stages"].append({"stage": r["stage"], "status": r["status"],
                                "trades": summary.get("trades"), "net": summary.get("net_pnl")})
    out = []
    for key, entry in runs.items():
        kill = kill_map.get(key)
        entry["kill"] = kill
        entry["verdict"] = "KILLED" if kill else (
            "PASSED" if any(s["stage"] == "WALK_FORWARD" and s["status"] == "PASS"
                            for s in entry["stages"]) else "IN PROGRESS")
        out.append(entry)
    return out


def _readiness(db_path: Path) -> dict:
    try:
        from scripts import audit_data_integrity as audit
        report = audit.audit_database(db_path)
        r = report["research_readiness"]
        return {"integrity": report["summary"]["status"], "have": r["distinct_15m_sessions"],
                "need": r["minimum_15m_sessions"], "remaining": r["sessions_remaining"],
                "verdict": r["status"]}
    except Exception:
        return {"integrity": "unavailable", "have": None, "need": None,
                "remaining": None, "verdict": "unavailable"}


def _today_counts(db_path: Path) -> dict:
    out = {"date": datetime.now().astimezone().date().isoformat(), "c15": 0, "c1": 0, "last": None}
    if not db_path.exists():
        return out
    with _ro_conn(db_path) as conn:
        try:
            for interval, key in (("15m", "c15"), ("1m", "c1")):
                row = conn.execute("SELECT COUNT(*) FROM intraday_prices WHERE interval=? AND date(ts)=?",
                                   (interval, out["date"])).fetchone()
                out[key] = int(row[0]) if row else 0
            row = conn.execute("SELECT MAX(created_at) FROM intraday_prices").fetchone()
            out["last"] = row[0] if row and row[0] else None
        except sqlite3.OperationalError:
            pass
    return out


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def _note(
    brain: Path,
    name: str,
    tags: str,
    body: str,
    stamp: str,
    *,
    source_path: str = "scripts/export_brain.py",
) -> None:
    text = (
        "---\n"
        f"tags: [{tags}]\n"
        f"updated: {stamp}\n"
        "managed: true\n"
        f"source_path: {json.dumps(source_path, ensure_ascii=False)}\n"
        "---\n"
        f"{body.rstrip()}\n"
    )
    _atomic_write(brain / f"{name}.md", text)


# ── STATIC knowledge layer (real definitions, densely linked) ────────────────
# name -> body (with [[wikilinks]]). Each ends with a back-link to its MOC.

CONCEPTS = {
    "One-Stock Doctrine": "Spencer trades only [[RELIANCE]] until it is mastered. No second stock until consistent net profit after costs. See [[Mastery]], [[Paper Capital]], [[Doctrine]].",
    "Paper Capital": "A fixed ₹5,000 paper account ([[Account Epoch]] `one_stock_reliance_v1`). Max one open position. Never inflated or faked. See [[One-Stock Doctrine]], [[Deployment Gate]].",
    "Mastery": "Repeatable net profit after all costs on [[RELIANCE]] — the bar to unlock a second stock. Tracked honestly via the daily ledger. See [[One-Stock Doctrine]], [[Cost Bar]].",
    "Confirm-or-Kill": "Every technique must survive [[In-Sample]] → [[Out-of-Sample]] → [[Walk-Forward]] after [[Round-Trip Cost]], or it is killed and recorded in the [[Kill Registry]]. See [[Backtest Harness]].",
    "Cost Bar": "A candidate's expected edge per trade must beat ~3× the [[Round-Trip Cost]]. Most simple ideas fail here. See [[RELIANCE Cost Math]].",
    "Round-Trip Cost": "Brokerage + taxes + [[Slippage]] for a buy then sell. On [[RELIANCE]] intraday this is ~0.1% of notional. See [[RELIANCE Cost Math]], [[Cost Bar]].",
    "Slippage": "The price moving against you between decision and fill. Modelled on every simulated trade. Part of [[Round-Trip Cost]].",
    "In-Sample": "The first stage of the [[Confirm-or-Kill]] ladder: test the candidate on real candles it was designed on. Failing here stops the ladder. See [[Backtest Harness]].",
    "Out-of-Sample": "Stage two: test on unseen [[RELIANCE]] data with no parameter changes. See [[Confirm-or-Kill]], [[Walk-Forward]].",
    "Walk-Forward": "Stage three: rolling re-fit on past data only, future unseen, costs applied every step. Passing all three unlocks [[Live Paper Engine]]. See [[Confirm-or-Kill]].",
    "Kill Registry": "A permanent record of killed candidates; a killed idea cannot be revived by tweaking parameters. Enforced by the [[Backtest Harness]] and the [[Live Paper Engine]].",
    "Deployment Gate": "A hard block keeping live trading and broker execution OFF until research validation passes. The [[Live Paper Engine]] refuses to run if it is not paper-only.",
    "Account Epoch": "`one_stock_reliance_v1` — the ₹5,000 reset baseline. Prior history is preserved; stats are reported from the epoch onward. See [[Paper Capital]].",
    "RELIANCE": "Reliance Industries (NSE) — the single, highly liquid large-cap Spencer studies. See [[One-Stock Doctrine]], [[NSE Market Hours]].",
    "NSE Market Hours": "09:15–15:30 IST, Monday–Friday. The [[Intraday Collector]] runs through this window. Closed on [[NSE Holidays]].",
    "NSE Holidays": "Exchange-closed weekdays (the full 2026 calendar is loaded). No session is counted on these days. See [[Data Clock]].",
    "Volatility Persistence": "The premise that high-range days cluster (so 'yesterday was volatile' predicts today). Tested and found absent in our data — see [[Volatility Persistence EDA]].",
}

DATA_SOURCES = {
    "Yahoo Finance": "Active free source for [[RELIANCE]] quotes and candles. Powers the [[Quote Server]] and the [[Data Clock]]. ~60-day intraday history limit.",
    "Delivery Volume": "An NSE positioning signal — tested and KILLED (no stable out-of-sample power). See [[Delivery Volume Result]].",
    "Block Deals": "Large negotiated trades — research blocked: no usable free history. See [[Data Sources]].",
    "FII-DII Flows": "Foreign/domestic institutional flows — blocked: the free endpoint serves only the current provisional day.",
    "GDELT News": "Global news tone — blocked: the free DOC API only covers ~3 recent months. See [[News Sentiment Result]].",
    "GDELT GKG (BigQuery)": "A deeper historical-news path (2015+), scoped for a future build if news research resumes.",
}

FINDINGS = {
    "RELIANCE Cost Math": "Intraday round-trip breakeven ≈ 0.106% vs a median daily range of ~1.7% — costs are clearable intraday; delivery at 1 share needs ~1.48% and is near-unplayable. Sets the [[Cost Bar]].",
    "Volatility Persistence EDA": "On ~57 collected sessions, day-to-day range autocorrelation ≈ 0.026 (≈ zero) and gap-vs-range ≈ 0.037. The [[Volatility Persistence]] premise does NOT hold — it redirected the next candidate away from day-selection.",
    "Delivery Volume Result": "[[Delivery Volume]] features showed no stable OOS predictive power after costs — killed.",
    "News Sentiment Result": "[[GDELT News]] DOC API is recent-only (~3 months); insufficient history for a backtest. Found via [[Perplexity]] + internal probes.",
}

COMPONENTS = {
    "Backtest Harness": "Replays real candles through a candidate's mechanical rules, applies costs + [[Slippage]], and runs the [[Confirm-or-Kill]] ladder. Produces [[Research Ledger]] verdicts.",
    "Live Paper Engine": "A forward paper executor that behaves identically to the [[Backtest Harness]]. Gated by a [[Walk-Forward]] pass and the [[Deployment Gate]]; refuses killed candidates; never places a real order. See [[Live Engine]].",
    "Data Clock": "Collects [[RELIANCE]] data every trading day: the [[Intraday Collector]] during the session and an end-of-day snapshot. Feeds [[Data & Readiness]].",
    "Intraday Collector": "Runs every 30 minutes during [[NSE Market Hours]], storing only final, boundary-aligned candles (no partial bars).",
    "Integrity Auditor": "Read-only checks for duplicates, non-final candles, fabricated-session and freshness problems across the [[Data Clock]] output.",
    "Quote Server": "The local Python backend (port 8787) serving real [[Yahoo Finance]] quotes, charts, health and the [[Research Ledger]] to the [[Webapp]].",
    "Webapp": "The React + Tailwind dashboard (the liquid-glass UI) that displays only verified backend state. Shows [[Scoreboard]], [[Data & Readiness]] and the live chart.",
    "Brain Exporter": "This tool — writes the Obsidian vault you are reading from real data. Runs in the daily job so the graph stays current.",
}

TEAM = {
    "Claude Code": "The manager / orchestrator — writes task specs, reviews and verifies all work, owns git, and enforces the [[Doctrine]].",
    "Codex": "The engineer — implements one task spec at a time and commits locally; the manager reviews before anything lands.",
    "ChatGPT": "The document drafter — writes governance docs and explanations (no code, no orders).",
    "Perplexity": "Web research — sourced the news and volatility literature behind [[News Sentiment Result]] and [[Volatility Persistence EDA]].",
}

MOCS = {
    "Concepts": ("spencer, moc", CONCEPTS, "How Spencer thinks — its rules and methodology."),
    "Data Sources": ("spencer, moc", DATA_SOURCES, "Every data source researched, and its verdict."),
    "Research Findings": ("spencer, moc", FINDINGS, "What the experiments and analyses actually found."),
    "Components": ("spencer, moc", COMPONENTS, "The machine: the parts that make Spencer run."),
    "Team": ("spencer, moc", TEAM, "The multi-AI team and who does what."),
}

REFERENCE_FILES = {
    "SPENCER_CONCEPT.md": "Reference/Governance/SPENCER_CONCEPT",
    "RESEARCH_PROTOCOL.md": "Reference/Governance/RESEARCH_PROTOCOL",
    "PROJECT_STATUS.md": "Reference/Operations/PROJECT_STATUS",
    "MASTERY_LEDGER.md": "Reference/Research/MASTERY_LEDGER",
    "MISTAKE_REVIEW.md": "Reference/Research/MISTAKE_REVIEW",
    "DATA_SOURCE_RESEARCH_PLAN.md": "Reference/Research/DATA_SOURCE_RESEARCH_PLAN",
    "AUDIT_REPORT.md": "Reference/Operations/AUDIT_REPORT",
    "docs/OBSIDIAN_BRAIN.md": "Reference/Operations/OBSIDIAN_BRAIN",
    "docs/RELIANCE_COST_MATH.md": "Reference/Research/RELIANCE_COST_MATH",
    "workflow/current_task.md": "Reference/Workflow/Current Task",
    "workflow/latest_result.md": "Reference/Workflow/Latest Result",
    "workflow/review_packet.md": "Reference/Workflow/Review Packet",
}
REFERENCE_GLOBS = {
    "candidates/*.md": "Reference/Candidates",
    "docs/research/*.md": "Reference/Research Evidence",
    "workflow/tasks/*.md": "Reference/Workflow Tasks",
    "workflow/agents/*.md": "Reference/Agents",
}


def _mirror_reference(brain: Path, source: Path, target: str, stamp: str) -> str | None:
    try:
        content = source.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    source_relative = source.relative_to(ROOT).as_posix()
    body = (
        f"# {source.stem.replace('_', ' ')}\n\n"
        f"> Managed mirror of `{source_relative}`. Edit the source file, not this copy.\n\n"
        f"{content.rstrip()}\n"
    )
    _note(
        brain,
        target,
        "spencer, reference",
        body,
        stamp,
        source_path=source_relative,
    )
    return target


def _mirror_references(brain: Path, stamp: str) -> list[str]:
    mirrored: list[str] = []
    for source_name, target in REFERENCE_FILES.items():
        result = _mirror_reference(brain, ROOT / source_name, target, stamp)
        if result:
            mirrored.append(result)
    for pattern, target_dir in REFERENCE_GLOBS.items():
        for source in sorted(ROOT.glob(pattern)):
            result = _mirror_reference(brain, source, f"{target_dir}/{source.stem}", stamp)
            if result:
                mirrored.append(result)
    return mirrored


def _write_system_canvas(brain: Path) -> None:
    nodes = [
        {"id": "home", "type": "file", "file": "Spencer.md", "x": 0, "y": 0, "width": 420, "height": 260},
        {"id": "status", "type": "file", "file": "Scoreboard.md", "x": -560, "y": -260, "width": 360, "height": 220},
        {"id": "research", "type": "file", "file": "Research Ledger.md", "x": -560, "y": 40, "width": 360, "height": 220},
        {"id": "memory", "type": "file", "file": "Memory/Memory Home.md", "x": 560, "y": -260, "width": 360, "height": 220},
        {"id": "reference", "type": "file", "file": "Reference Index.md", "x": 560, "y": 40, "width": 360, "height": 220},
        {"id": "doctrine", "type": "file", "file": "Doctrine.md", "x": 0, "y": 360, "width": 360, "height": 220},
    ]
    edges = [
        {"id": "e1", "fromNode": "home", "fromSide": "left", "toNode": "status", "toSide": "right"},
        {"id": "e2", "fromNode": "home", "fromSide": "left", "toNode": "research", "toSide": "right"},
        {"id": "e3", "fromNode": "home", "fromSide": "right", "toNode": "memory", "toSide": "left"},
        {"id": "e4", "fromNode": "home", "fromSide": "right", "toNode": "reference", "toSide": "left"},
        {"id": "e5", "fromNode": "home", "fromSide": "bottom", "toNode": "doctrine", "toSide": "top"},
    ]
    _atomic_write(
        brain / "Spencer System.canvas",
        json.dumps({"nodes": nodes, "edges": edges}, indent=2, ensure_ascii=False),
    )


def export_brain(*, db_path: Path = DB_PATH, scoreboard_path: Path = SCOREBOARD_PATH,
                 brain_dir: Path = BRAIN_DIR) -> dict:
    brain = Path(brain_dir)
    store = ObsidianBrain(brain)
    layout_created = store.ensure_layout()
    stamp = datetime.now().astimezone().isoformat(timespec="minutes")
    sb = _load_json(scoreboard_path)
    candidates = _candidates(db_path)
    ready = _readiness(db_path)
    today = _today_counts(db_path)

    # ── Home ─────────────────────────────────────────────────────────────────
    _note(brain, "Spencer", "spencer, home", f"""# 🧠 Spencer — Brain

The live, auto-generated knowledge base for the Spencer paper-trading research
bot. Every note is built from real data or factual methodology — nothing here is
estimated.

## Status
- [[Scoreboard]] — where the bot stands
- [[Research Ledger]] — every experiment and its verdict
- [[Data & Readiness]] — data collection + next-experiment progress
- [[Live Engine]] — the paper-trading executor
- [[Daily/{today['date']}]] — today's generated state snapshot

## Knowledge
- [[Concepts]] — the rules and methodology
- [[Data Sources]] — sources researched + verdicts
- [[Research Findings]] — what we actually found
- [[Components]] — the machine's parts
- [[Team]] — the multi-AI team
- [[Primary Brain]] — runtime memory and retrieval contract
- [[Memory/Memory Home]] — operator-reviewed durable memory
- [[Reference Index]] — canonical repo documents mirrored for recall
- [[Open Questions]] — known unknowns and current blockers
- [[Doctrine]] — the constitution · [[README]]

> One stock ([[RELIANCE]]) · ₹5,000 [[Paper Capital]] · zero fake data · paper-only.
> Generated by the [[Brain Exporter]] at {stamp}.""", stamp)

    # ── Scoreboard ─────────────────────────────────────────────────────────────
    _note(brain, "Scoreboard", "spencer, scoreboard", f"""# 📊 Scoreboard

| Scale | Score | Meaning |
|---|---|---|
| Functional | {sb.get('functional', '—')} / 100 | how well the machine is built |
| Profitability | {sb.get('profitability', '—')} / 100 | real edge (money-making ability) |
| Composite | {sb.get('composite', '—')} / 100 | honest overall |

- Experiments tested: **{sb.get('candidatesTested', '—')}** · killed: **{sb.get('candidatesKilled', '—')}** · validated edges: **{sb.get('validatedEdges', '—')}**

Functional measures engineering; profitability only moves when a candidate clears
the [[Confirm-or-Kill]] ladder and earns net profit beyond the [[Cost Bar]].
See [[Research Ledger]] · back to [[Spencer]].""", stamp)

    # ── Research Ledger + candidate notes ──────────────────────────────────────
    rows = "\n".join(f"| [[{c['id']}]] | v{c['version']} | {c['verdict']} |" for c in candidates) \
        or "| _none yet_ | | |"
    _note(brain, "Research Ledger", "spencer, research", f"""# 🔬 Research Ledger

Every candidate technique tested through the [[Backtest Harness]]. Verdicts are
journaled and permanent (see [[Kill Registry]]).

| Candidate | Version | Verdict |
|---|---|---|
{rows}

Concepts: [[Confirm-or-Kill]] · [[Cost Bar]] · [[Walk-Forward]]. Back to [[Spencer]].""", stamp)

    for c in candidates:
        stage_rows = "\n".join(
            f"| {s['stage']} | {s['status']} | {s['trades'] if s['trades'] is not None else '—'} "
            f"| {s['net'] if s['net'] is not None else '—'} |" for s in c["stages"]) \
            or "| — | — | — | — |"
        kill_line = (f"\n**Killed:** {c['kill']['reason']} ({c['kill']['created_at'][:10]})\n"
                     if c.get("kill") else "")
        _note(brain, c["id"], "spencer, candidate", f"""# {c['id']} (v{c['version']}) — {c['verdict']}

**Hypothesis:** {c['hypothesis'] or '—'}
{kill_line}
| Stage | Status | Trades | Net P&L (₹) |
|---|---|---|---|
{stage_rows}

Measured against the [[Cost Bar]] across [[In-Sample]] → [[Out-of-Sample]] → [[Walk-Forward]].
Part of the [[Research Ledger]] · back to [[Spencer]].""", stamp)

    # ── Data & Readiness ───────────────────────────────────────────────────────
    last_txt = today["last"][:16].replace("T", " ") if today["last"] else "—"
    _note(brain, "Data & Readiness", "spencer, data", f"""# 📡 Data & Readiness

**Integrity:** {ready['integrity']} (via the [[Integrity Auditor]])

**Readiness for the next experiment:** {ready['have']} / {ready['need']} 15-minute
sessions — **{ready['verdict']}** ({ready['remaining']} remaining).

The bar rises by one session per completed trading day (~1.4%); never on
[[NSE Holidays]] or weekends. The [[Intraday Collector]] only keeps *today's* data
fresh — it does not add to the count.

**Today ({today['date']}):** {today['c15']} × 15m + {today['c1']} × 1m candles. Last: {last_txt}.

Powered by the [[Data Clock]] + [[Yahoo Finance]]. Back to [[Spencer]].""", stamp)

    # ── Live Engine ────────────────────────────────────────────────────────────
    armed = any(c["verdict"] == "PASSED" for c in candidates)
    _note(brain, "Live Engine", "spencer, engine", f"""# ⚙️ Live Paper Engine

Status: **{'ARMED' if armed else 'DORMANT'}** — {'a candidate has passed' if armed else 'no candidate has passed the ladder yet'}.

See the component note [[Live Paper Engine]]. It activates the day a candidate in
the [[Research Ledger]] clears [[Walk-Forward]], and obeys the [[Deployment Gate]].
Back to [[Spencer]].""", stamp)

    # ── Doctrine ───────────────────────────────────────────────────────────────
    _note(brain, "Doctrine", "spencer, doctrine", """# 📜 Doctrine

- **One stock:** [[RELIANCE]] only, until [[Mastery]] (see [[One-Stock Doctrine]]).
- **₹5,000** fixed [[Paper Capital]]; max one open position.
- **Zero fake data** — every shown number traces to a real trade, quote, or
  documented calculation.
- **Paper-only**; live trading stays behind the [[Deployment Gate]].
- **[[Confirm-or-Kill]]:** survive [[In-Sample]] → [[Out-of-Sample]] →
  [[Walk-Forward]] after the [[Cost Bar]], or be killed.

Full text: `SPENCER_CONCEPT.md` and `RESEARCH_PROTOCOL.md`. Back to [[Spencer]].""", stamp)

    # ── README ─────────────────────────────────────────────────────────────────
    _note(brain, "README", "spencer", """# Spencer Brain (Obsidian vault)

This vault is Spencer's primary knowledge and memory layer. To view:
1. Install Obsidian (https://obsidian.md).
2. "Open folder as vault" → select this `brain/` folder.
3. Open [[Spencer]] and turn on Graph View.

`managed: true` notes are regenerated from verified repo/database sources.
Human-reviewed memory belongs under [[Memory/Memory Home]] and is never
overwritten. Run `python scripts/export_brain.py` to refresh generated truth,
or `python scripts/brain_cli.py search "query"` to query it.

Back to [[Spencer]].""", stamp)

    # ── MOCs + their member notes ──────────────────────────────────────────────
    for moc_name, (tags, members, blurb) in MOCS.items():
        links = "\n".join(f"- [[{n}]]" for n in members)
        _note(brain, moc_name, tags, f"# {moc_name}\n\n{blurb}\n\n{links}\n\nBack to [[Spencer]].", stamp)
        for n, body in members.items():
            _note(brain, n, "spencer, knowledge", f"# {n}\n\n{body}\n\nPart of [[{moc_name}]] · back to [[Spencer]].", stamp)

    _note(brain, "Primary Brain", "spencer, system", """# Primary Brain

Obsidian is Spencer's primary runtime knowledge source.

- Generated truth is refreshed by the [[Brain Exporter]].
- Durable operator memory lives under [[Memory/Memory Home]].
- Canonical project documents are searchable through [[Reference Index]].
- The quote server exposes status, search, context, recall, graph, note-read,
  capture, and reindex APIs on localhost.
- Chat retrieves Obsidian context before using an LLM and returns source
  citations. Without an LLM key, it falls back to local cited recall.

This changes memory and explanation, not trading authority. [[Doctrine]] and the
[[Deployment Gate]] remain binding. Back to [[Spencer]].""", stamp)

    open_questions = [
        f"- Research readiness is **{ready['verdict']}** with {ready['remaining']} sessions remaining.",
        f"- Validated edges: **{sb.get('validatedEdges', 'unavailable')}**.",
        "- Which pre-registered hypothesis should become the next candidate after readiness is met?",
        "- Which manual memories have enough evidence to move from inbox to durable knowledge?",
        "- Which broken or orphaned links in the vault should be resolved?",
    ]
    _note(
        brain,
        "Open Questions",
        "spencer, questions",
        "# Open Questions\n\n" + "\n".join(open_questions) + "\n\nBack to [[Spencer]].",
        stamp,
    )

    _note(brain, "Safety Boundaries", "spencer, governance", """# Safety Boundaries

- Paper trading only.
- RELIANCE only until mastery.
- Fixed ₹5,000 paper capital and maximum one open position.
- No broker execution, real-money orders, or AI order approval.
- No fabricated prices, trades, P&L, research results, or bot status.
- Missing evidence must be reported as unavailable or unknown.
- Obsidian memories cannot override [[Doctrine]], [[Deployment Gate]], or the
  journaled [[Research Ledger]].

Canonical source: [[Reference/Governance/SPENCER_CONCEPT]]. Back to [[Spencer]].""", stamp)

    mirrored = _mirror_references(brain, stamp)
    reference_links = "\n".join(f"- [[{note}]]" for note in mirrored) or "- No reference files were available."
    _note(
        brain,
        "Reference Index",
        "spencer, reference, moc",
        f"# Reference Index\n\nCanonical project documents mirrored into the primary brain.\n\n"
        f"{reference_links}\n\nBack to [[Spencer]].",
        stamp,
    )

    daily_body = f"""# Spencer Daily State — {today['date']}

- Integrity: **{ready['integrity']}**
- Research readiness: **{ready['have']} / {ready['need']}** sessions ({ready['verdict']})
- Sessions remaining: **{ready['remaining']}**
- 15-minute candles observed today: **{today['c15']}**
- 1-minute candles observed today: **{today['c1']}**
- Candidates in journal: **{len(candidates)}**
- Validated edges: **{sb.get('validatedEdges', 'unavailable')}**
- Live trading: **OFF**
- Broker execution: **OFF**

Links: [[Scoreboard]] · [[Research Ledger]] · [[Data & Readiness]] ·
[[Safety Boundaries]] · [[Memory/Memory Home]]
"""
    _note(
        brain,
        f"Daily/{today['date']}",
        "spencer, daily, generated",
        daily_body,
        stamp,
        source_path="kite_bot.db + workflow/scoreboard.json",
    )
    _write_system_canvas(brain)

    index_result = store.write_index()
    notes = sorted(p.relative_to(brain).as_posix() for p in brain.rglob("*.md"))
    return {
        "brain_dir": str(brain),
        "notes": notes,
        "candidates": len(candidates),
        "note_count": len(notes),
        "references": len(mirrored),
        "layout_created": layout_created,
        "index": index_result,
    }


def main() -> int:
    result = export_brain()
    print(f"Brain exported to {result['brain_dir']}")
    print(f"  notes: {result['note_count']} | candidates: {result['candidates']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
