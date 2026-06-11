"""
Fast driver for the delivery-volume evaluation. Reuses Codex's exact logic
(bot.delivery_eval.evaluate_all and bot.nse_delivery.parse_bhavcopy_csv) but reads
each cached NSE bhavcopy ONCE instead of re-parsing it per (symbol, day). Read-only;
no strategy, no orders, no deployment. It just makes the same research run tractable.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Force THIS project's packages ahead of any installed kite_bot egg-link.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from bot import nse_delivery
from bot import delivery_eval as DE
from workflow.research_automation import (
    add_research_workflow_args, finalize_from_args, print_research_workflow_summary,
)

CACHE = nse_delivery.DEFAULT_CACHE_DIR


def load_combined() -> pd.DataFrame:
    frames = []
    for p in sorted(CACHE.glob("sec_bhavdata_full_*.csv")):
        df = nse_delivery.parse_bhavcopy_csv(p.read_text(encoding="utf-8", errors="ignore"))
        if df is not None and not df.empty:
            frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    return combined


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=2)
    add_research_workflow_args(ap)
    args = ap.parse_args()

    t0 = time.time()
    combined = load_combined()
    by_symbol = {s: g for s, g in combined.groupby("symbol")}
    print(f"Parsed {len(list(CACHE.glob('sec_bhavdata_full_*.csv')))} cached bhavcopies "
          f"-> {combined['symbol'].nunique()} symbols, {len(combined):,} rows "
          f"({time.time()-t0:.0f}s)")

    # Patch the per-day fetch loop with a one-pass cache slice (same output schema).
    def fast_delivery_history(symbol, *, years=2, **_):
        g = by_symbol.get(str(symbol).strip().upper())
        if g is None or g.empty:
            return None
        out = g.drop_duplicates(subset=["date", "symbol"]).sort_values("date").copy()
        out.index = pd.to_datetime(out["date"])
        return out[["symbol", "series", "traded_qty", "deliverable_qty", "delivery_pct"]]

    nse_delivery.delivery_history = fast_delivery_history  # used by delivery_eval

    result = DE.evaluate_all(args.years, include_midcap=True, top=50)
    DE._print_report(result)
    print_research_workflow_summary(finalize_from_args("delivery_eval", result, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
