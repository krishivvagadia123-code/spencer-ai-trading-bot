"""Export Spencer's live state into a self-contained Obsidian vault (brain/).

Generates cross-linked markdown notes from REAL sources only — scoreboard.json,
the backtest journal (runs + kills), the data-integrity auditor, and today's
collected candles. Re-run any time (idempotent); Obsidian auto-reloads the files.

Read-only over the database. Writes only inside the brain/ folder. Zero fabricated
content — if a source is empty, the note says so.

Usage:  python scripts/export_brain.py
Then in Obsidian: "Open folder as vault" -> select the brain/ folder.
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

DB_PATH = ROOT / "kite_bot.db"
SCOREBOARD_PATH = ROOT / "workflow" / "scoreboard.json"
BRAIN_DIR = ROOT / "brain"


def _ro_conn(db_path: Path):
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _candidates(db_path: Path) -> list[dict]:
    """One entry per candidate id+version with stages, kill, hypothesis."""
    if not db_path.exists():
        return []
    runs: dict[tuple, dict] = {}
    with _ro_conn(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT candidate_id, candidate_version, stage, status, summary_json, "
                "candidate_json, created_at FROM backtest_runs ORDER BY id"
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        try:
            kills = conn.execute(
                "SELECT candidate_id, candidate_version, reason, created_at "
                "FROM backtest_kills ORDER BY id"
            ).fetchall()
        except sqlite3.OperationalError:
            kills = []
    kill_map = {(k["candidate_id"], k["candidate_version"]): dict(k) for k in kills}
    for r in rows:
        key = (r["candidate_id"], r["candidate_version"])
        entry = runs.setdefault(key, {
            "id": r["candidate_id"], "version": r["candidate_version"],
            "hypothesis": "", "stages": [],
        })
        cj = {}
        try:
            cj = json.loads(r["candidate_json"]) if r["candidate_json"] else {}
        except json.JSONDecodeError:
            cj = {}
        if cj.get("hypothesis"):
            entry["hypothesis"] = cj["hypothesis"]
        summary = {}
        try:
            summary = json.loads(r["summary_json"]) if r["summary_json"] else {}
        except json.JSONDecodeError:
            summary = {}
        entry["stages"].append({
            "stage": r["stage"], "status": r["status"],
            "trades": summary.get("trades"), "net": summary.get("net_pnl"),
        })
    out = []
    for key, entry in runs.items():
        kill = kill_map.get(key)
        entry["verdict"] = "KILLED" if kill else (
            "PASSED" if any(s["stage"] == "WALK_FORWARD" and s["status"] == "PASS"
                            for s in entry["stages"]) else "IN PROGRESS")
        entry["kill"] = kill
        out.append(entry)
    return out


def _readiness_and_integrity(db_path: Path) -> dict:
    try:
        from scripts import audit_data_integrity as audit
        report = audit.audit_database(db_path)
        r = report["research_readiness"]
        return {
            "integrity": report["summary"]["status"],
            "have": r["distinct_15m_sessions"],
            "need": r["minimum_15m_sessions"],
            "remaining": r["sessions_remaining"],
            "verdict": r["status"],
        }
    except Exception:
        return {"integrity": "unavailable", "have": None, "need": None,
                "remaining": None, "verdict": "unavailable"}


def _today_counts(db_path: Path) -> dict:
    out = {"date": datetime.now().astimezone().date().isoformat(),
           "c15": 0, "c1": 0, "last": None}
    if not db_path.exists():
        return out
    today = out["date"]
    with _ro_conn(db_path) as conn:
        try:
            for interval, key in (("15m", "c15"), ("1m", "c1")):
                row = conn.execute(
                    "SELECT COUNT(*) FROM intraday_prices WHERE interval=? AND date(ts)=?",
                    (interval, today)).fetchone()
                out[key] = int(row[0]) if row else 0
            row = conn.execute("SELECT MAX(created_at) FROM intraday_prices").fetchone()
            out["last"] = row[0] if row and row[0] else None
        except sqlite3.OperationalError:
            pass
    return out


def _write(brain: Path, name: str, body: str) -> None:
    (brain / name).write_text(body.rstrip() + "\n", encoding="utf-8")


def export_brain(*, db_path: Path = DB_PATH, scoreboard_path: Path = SCOREBOARD_PATH,
                 brain_dir: Path = BRAIN_DIR) -> dict:
    brain = Path(brain_dir)
    brain.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="minutes")
    sb = _load_json(scoreboard_path)
    candidates = _candidates(db_path)
    ready = _readiness_and_integrity(db_path)
    today = _today_counts(db_path)

    # ── Home (Map of Content) ────────────────────────────────────────────────
    _write(brain, "Spencer.md", f"""---
tags: [spencer, home]
updated: {stamp}
---
# 🧠 Spencer — Brain

The live, auto-generated knowledge base for the Spencer paper-trading research
bot. Every note here is built from real data; nothing is estimated.

## Map
- [[Scoreboard]] — where the bot stands
- [[Research Ledger]] — every experiment and its verdict
- [[Data & Readiness]] — data collection + next-experiment progress
- [[Live Engine]] — the paper-trading executor (dormant until a candidate passes)
- [[Doctrine]] — the rules Spencer must obey

> One stock (RELIANCE) · ₹5,000 paper capital · zero fake data · paper-only.
> Generated by `scripts/export_brain.py` at {stamp}.
""")

    # ── Scoreboard ───────────────────────────────────────────────────────────
    _write(brain, "Scoreboard.md", f"""---
tags: [spencer, scoreboard]
updated: {stamp}
---
# 📊 Scoreboard

| Scale | Score | Meaning |
|---|---|---|
| Functional | {sb.get('functional', '—')} / 100 | how well the machine is built |
| Profitability | {sb.get('profitability', '—')} / 100 | real money-making ability (edge) |
| Composite | {sb.get('composite', '—')} / 100 | honest overall |

- Experiments tested: **{sb.get('candidatesTested', '—')}**
- Killed: **{sb.get('candidatesKilled', '—')}**
- Validated edges: **{sb.get('validatedEdges', '—')}**

Functional measures engineering; profitability only moves when a candidate
clears the ladder and earns net profit after costs. See [[Research Ledger]].

Back to [[Spencer]].
""")

    # ── Research Ledger + per-candidate notes ────────────────────────────────
    if candidates:
        rows = "\n".join(
            f"| [[{c['id']}]] | v{c['version']} | {c['verdict']} |"
            for c in candidates
        )
    else:
        rows = "| _none yet_ | | |"
    _write(brain, "Research Ledger.md", f"""---
tags: [spencer, research]
updated: {stamp}
---
# 🔬 Research Ledger

Every candidate technique Spencer has tested. Verdicts are journaled and
permanent — a killed candidate cannot be revived by tweaking.

| Candidate | Version | Verdict |
|---|---|---|
{rows}

Back to [[Spencer]].
""")

    for c in candidates:
        stage_rows = "\n".join(
            f"| {s['stage']} | {s['status']} | {s['trades'] if s['trades'] is not None else '—'} "
            f"| {s['net'] if s['net'] is not None else '—'} |"
            for s in c["stages"]
        ) or "| — | — | — | — |"
        kill_line = (
            f"\n**Killed:** {c['kill']['reason']} ({c['kill']['created_at'][:10]})\n"
            if c.get("kill") else "")
        _write(brain, f"{c['id']}.md", f"""---
tags: [spencer, candidate]
verdict: {c['verdict']}
updated: {stamp}
---
# {c['id']} (v{c['version']}) — {c['verdict']}

**Hypothesis:** {c['hypothesis'] or '—'}
{kill_line}
| Stage | Status | Trades | Net P&L (₹) |
|---|---|---|---|
{stage_rows}

Part of the [[Research Ledger]] · back to [[Spencer]].
""")

    # ── Data & Readiness ─────────────────────────────────────────────────────
    last_txt = today["last"][:16].replace("T", " ") if today["last"] else "—"
    _write(brain, "Data & Readiness.md", f"""---
tags: [spencer, data]
updated: {stamp}
---
# 📡 Data & Readiness

**Integrity:** {ready['integrity']}

**Readiness for the next experiment (SPNCR-003):**
{ready['have']} / {ready['need']} 15-minute sessions — **{ready['verdict']}**
({ready['remaining']} sessions remaining).

The bar rises by **one session per completed trading day** (~1.4%). It does not
rise on weekends/holidays, and the 30-minute intraday collector only keeps
*today's* data fresh — it does not add to the count.

**Today ({today['date']}):** collected {today['c15']} × 15m + {today['c1']} × 1m
candles. Last collection: {last_txt}.

Back to [[Spencer]].
""")

    # ── Live Engine ──────────────────────────────────────────────────────────
    armed = any(c["verdict"] == "PASSED" for c in candidates)
    _write(brain, "Live Engine.md", f"""---
tags: [spencer, engine]
updated: {stamp}
---
# ⚙️ Live Paper-Trading Engine

Status: **{'ARMED' if armed else 'DORMANT'}** — {'a candidate has passed' if armed else 'no candidate has passed the ladder yet'}.

The engine paper-trades an approved candidate forward, identically to how it
backtested. It refuses to run a killed or unproven candidate and never places a
real order. It activates the day a candidate in the [[Research Ledger]] passes.

Back to [[Spencer]].
""")

    # ── Doctrine ─────────────────────────────────────────────────────────────
    _write(brain, "Doctrine.md", f"""---
tags: [spencer, doctrine]
updated: {stamp}
---
# 📜 Doctrine

- **One stock:** RELIANCE only, until mastered.
- **₹5,000** fixed paper capital. Max one open position.
- **Zero fake data** — every shown number traces to a real trade, quote, or
  documented calculation.
- **Paper-only**; live trading and broker execution stay blocked until research
  validation passes.
- **Confirm-or-kill:** a technique must survive in-sample → out-of-sample →
  walk-forward, after costs, before it may paper-trade.

Full text lives in the repo: `SPENCER_CONCEPT.md` and `RESEARCH_PROTOCOL.md`.

Back to [[Spencer]].
""")

    # ── README (how to open) ─────────────────────────────────────────────────
    _write(brain, "README.md", """# Spencer Brain (Obsidian vault)

Auto-generated by `scripts/export_brain.py` from real data. To view:

1. Install Obsidian (https://obsidian.md).
2. "Open folder as vault" -> select this `brain/` folder.
3. Open **Spencer.md** and turn on Graph View.

Re-run `python scripts/export_brain.py` to refresh; Obsidian reloads on save.
Do not hand-edit these files — they are regenerated.
""")

    notes = sorted(p.name for p in brain.glob("*.md"))
    return {"brain_dir": str(brain), "notes": notes, "candidates": len(candidates)}


def main() -> int:
    result = export_brain()
    print(f"Brain exported to {result['brain_dir']}")
    print(f"  notes: {len(result['notes'])} | candidates: {result['candidates']}")
    for n in result["notes"]:
        print(f"   - {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
