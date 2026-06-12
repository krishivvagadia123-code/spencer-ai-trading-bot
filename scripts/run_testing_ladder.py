"""Run the RESEARCH_PROTOCOL testing ladder for a supplied candidate file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.intraday_backtest import (
    DB_PATH,
    BacktestResult,
    assert_not_forbidden_by_kill_registry,
    record_kill,
    run_backtest,
    stage_passed,
)
from bot.research_candidates import ResearchCandidate, load_candidate

StageRunner = Callable[[ResearchCandidate, str, dict, Path], BacktestResult]


def _load_splits(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("split config must be a JSON object")
    return data


def _range_for(splits: dict, key: str) -> dict | None:
    value = splits.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{key} split must be an object")
    return value


def _default_stage_runner(candidate: ResearchCandidate, stage: str, date_range: dict, db_path: Path) -> BacktestResult:
    return run_backtest(
        candidate,
        db_path=db_path,
        stage=stage,
        start=date_range.get("start"),
        end=date_range.get("end"),
        persist=True,
    )


def _verdict_line(stage: str, result: BacktestResult) -> str:
    reason = result.summary.get("status_reason")
    suffix = f" ({reason})" if reason else ""
    return f"{stage}: {result.status}{suffix}"


def run_ladder(
    candidate: ResearchCandidate,
    splits: dict,
    *,
    db_path: str | Path = DB_PATH,
    stage_runner: StageRunner = _default_stage_runner,
) -> dict:
    db = Path(db_path)
    assert_not_forbidden_by_kill_registry(db, candidate)

    outcomes: dict[str, BacktestResult] = {}
    lines: list[str] = []

    in_sample = _range_for(splits, "in_sample")
    if not in_sample:
        return {"verdict": "DATA_INSUFFICIENT", "lines": ["IN_SAMPLE: DATA_INSUFFICIENT (missing split)"], "results": outcomes}
    result = stage_runner(candidate, "IN_SAMPLE", in_sample, db)
    outcomes["IN_SAMPLE"] = result
    lines.append(_verdict_line("IN_SAMPLE", result))
    if not stage_passed(result):
        if result.status == "FAIL":
            record_kill(db, candidate, "IN_SAMPLE failed")
        return {"verdict": result.status, "lines": lines, "results": outcomes}

    out_sample = _range_for(splits, "out_of_sample")
    if not out_sample:
        lines.append("OUT_OF_SAMPLE: DATA_INSUFFICIENT (missing split)")
        return {"verdict": "DATA_INSUFFICIENT", "lines": lines, "results": outcomes}
    result = stage_runner(candidate, "OUT_OF_SAMPLE", out_sample, db)
    outcomes["OUT_OF_SAMPLE"] = result
    lines.append(_verdict_line("OUT_OF_SAMPLE", result))
    if not stage_passed(result):
        if result.status == "FAIL":
            record_kill(db, candidate, "OUT_OF_SAMPLE failed")
        return {"verdict": result.status, "lines": lines, "results": outcomes}

    walk = splits.get("walk_forward")
    if not walk:
        lines.append("WALK_FORWARD: DATA_INSUFFICIENT (missing split)")
        return {"verdict": "DATA_INSUFFICIENT", "lines": lines, "results": outcomes}
    windows = walk if isinstance(walk, list) else [walk]
    walk_results = []
    for idx, window in enumerate(windows, start=1):
        if not isinstance(window, dict):
            raise ValueError("walk_forward windows must be objects")
        result = stage_runner(candidate, "WALK_FORWARD", window, db)
        walk_results.append(result)
        lines.append(_verdict_line(f"WALK_FORWARD[{idx}]", result))
        if not stage_passed(result):
            if result.status == "FAIL":
                record_kill(db, candidate, "WALK_FORWARD failed")
            outcomes["WALK_FORWARD"] = result
            return {"verdict": result.status, "lines": lines, "results": outcomes}
    outcomes["WALK_FORWARD"] = walk_results[-1]
    return {"verdict": "PASS", "lines": lines, "results": outcomes}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the in-sample/OOS/walk-forward testing ladder.")
    parser.add_argument("--candidate", required=True, help="Path to a candidate JSON file.")
    parser.add_argument("--splits", required=True, help="Path to a date split JSON file.")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="SQLite DB path; defaults to kite_bot.db.")
    args = parser.parse_args(argv)

    candidate = load_candidate(args.candidate)
    splits = _load_splits(args.splits)
    try:
        outcome = run_ladder(candidate, splits, db_path=args.db)
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 2
    for line in outcome["lines"]:
        print(line)
    print(f"VERDICT: {outcome['verdict']}")
    return 0 if outcome["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
