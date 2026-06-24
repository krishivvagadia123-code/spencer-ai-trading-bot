"""Run a candidate through Spencer's Confirm-or-Kill ladder and log the verdict.

This is an orchestrator only: it reuses scripts.run_testing_ladder.run_ladder
for the actual backtest stages and therefore preserves the research ledger
tables in kite_bot.db. It never trades and never writes to live journals.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.intraday_backtest import DB_PATH, ensure_backtest_tables
from bot.research_candidates import ResearchCandidate, load_candidate
from scripts.run_testing_ladder import StageRunner, _load_splits, run_ladder

RESULTS_PATH = ROOT / "workflow" / "pipeline_results.jsonl"


def _default_splits_path(candidate_path: Path) -> Path:
    if candidate_path.name.endswith(".json"):
        return candidate_path.with_name(candidate_path.name[:-5] + ".splits.json")
    return candidate_path.with_suffix(candidate_path.suffix + ".splits.json")


def _refuse_exact_killed_params(db_path: Path | str, candidate: ResearchCandidate) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        ensure_backtest_tables(conn)
        row = conn.execute(
            """
            SELECT reason
            FROM backtest_kills
            WHERE candidate_id=? AND candidate_version=? AND params_hash=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (candidate.id, candidate.version, candidate.params_hash),
        ).fetchone()
    if row:
        raise ValueError(
            f"refusing to re-test killed candidate {candidate.id} {candidate.version} "
            f"with identical params ({row[0]})"
        )


def _append_result(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def run_pipeline(
    candidate_path: Path | str,
    *,
    splits_path: Path | str | None = None,
    db_path: Path | str = DB_PATH,
    results_path: Path = RESULTS_PATH,
    stage_runner: StageRunner | None = None,
) -> dict:
    candidate_file = Path(candidate_path)
    split_file = Path(splits_path) if splits_path is not None else _default_splits_path(candidate_file)
    candidate = load_candidate(candidate_file)
    _refuse_exact_killed_params(db_path, candidate)
    splits = _load_splits(split_file)
    kwargs = {"db_path": db_path}
    if stage_runner is not None:
        kwargs["stage_runner"] = stage_runner
    outcome = run_ladder(candidate, splits, **kwargs)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_id": candidate.id,
        "candidate_version": candidate.version,
        "params_hash": candidate.params_hash,
        "candidate_path": str(candidate_file),
        "splits_path": str(split_file),
        "verdict": outcome["verdict"],
        "lines": outcome["lines"],
    }
    _append_result(results_path, result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a candidate through Confirm-or-Kill.")
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--splits", type=Path)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--results", type=Path, default=RESULTS_PATH)
    args = parser.parse_args(argv)
    try:
        result = run_pipeline(
            args.candidate,
            splits_path=args.splits,
            db_path=args.db,
            results_path=args.results,
        )
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 2
    for line in result["lines"]:
        print(line)
    print(f"VERDICT: {result['verdict']}")
    print(f"WROTE {args.results}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
