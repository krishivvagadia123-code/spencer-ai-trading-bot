"""Run the live paper-trading engine for an approved candidate.

Dry-run replays a candidate over one collected session's real candles (a
simulation — no pass required). Live mode runs the market-hours forward loop and
is gated by a journaled WALK_FORWARD PASS, so it refuses until a candidate
graduates the testing ladder.

Examples:
  python scripts/run_live_paper.py --candidate candidates/SPNCR-002.json --mode dry-run
  python scripts/run_live_paper.py --candidate candidates/SPNCR-002.json --mode dry-run --date 2026-06-12
  python scripts/run_live_paper.py --candidate candidates/<passed>.json --mode live
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.live_paper_trader import (  # noqa: E402
    DB_PATH,
    CandidateNotApprovedError,
    GateError,
    LivePaperError,
    run_dry_run,
    run_live,
)
from bot.research_candidates import load_candidate  # noqa: E402


def _latest_session(db_path: Path, interval: str) -> str | None:
    if not db_path.exists():
        return None
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        try:
            row = conn.execute(
                "SELECT MAX(date(ts)) FROM intraday_prices WHERE interval = ?",
                (interval,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
    return row[0] if row and row[0] else None


def _live_quote_fn(symbol: str):
    """Build a quote source from the running quote server's code path. Only
    used after the PASS gate clears (so it never runs today)."""
    import spencer_quote_server as sqs
    from bot.market_data import Quote, now_ist

    def quote_fn():
        rows = sqs._quote_rows([symbol])
        if not rows:
            return None
        row = rows[0]
        price = row.get("price")
        if price is None:
            return None
        return Quote(symbol=symbol, price=float(price), timestamp=now_ist(),
                     is_stale=False, reject_reason=None)

    return quote_fn


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the live paper-trading engine.")
    parser.add_argument("--candidate", required=True, help="Path to a candidate JSON file.")
    parser.add_argument("--mode", choices=["dry-run", "live"], default="dry-run")
    parser.add_argument("--date", dest="session_date", help="Session date YYYY-MM-DD (dry-run).")
    parser.add_argument("--db", dest="db_path", type=Path, default=DB_PATH)
    args = parser.parse_args(argv)

    candidate = load_candidate(args.candidate)

    try:
        if args.mode == "dry-run":
            session = args.session_date or _latest_session(Path(args.db_path), candidate.interval)
            if not session:
                print("No intraday sessions available to dry-run against.")
                return 1
            summary = run_dry_run(candidate, db_path=args.db_path, session_date=session)
        else:
            summary = run_live(
                candidate,
                db_path=args.db_path,
                quote_fn=_live_quote_fn(candidate.symbol),
            )
    except CandidateNotApprovedError as exc:
        print(f"REFUSED (candidate not approved for live): {exc}")
        return 2
    except GateError as exc:
        print(f"REFUSED (deployment gate): {exc}")
        return 2
    except LivePaperError as exc:
        print(f"RUN ERROR: {exc}")
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
