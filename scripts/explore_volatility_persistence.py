"""Read-only EDA: does RELIANCE intraday volatility cluster?

Measures whether the *premise* behind a day-selection candidate (SPNCR-003)
holds in the collected data: does a high-range session tend to be followed by
another high-range session, and do gap size / expiry sessions associate with
larger ranges?

Research-integrity note: this measures a statistical PROPERTY of the data
(volatility persistence — a documented stylized fact), NOT a trading edge, and
NOT tuned parameters. Any candidate built later must still be pre-registered and
clear the full in-sample / out-of-sample / walk-forward ladder. This is
motivation, not evidence of profitability. Volatility persistence says WHEN
ranges are large, never WHICH DIRECTION — a viable candidate still needs a
separate directional rule.

Read-only: opens the DB in mode=ro and writes nothing.
"""

from __future__ import annotations

import math
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.intraday_backtest import _monthly_expiry_session  # expiry-session helper
from bot.market_data import IST

DB_PATH = ROOT / "kite_bot.db"


def _pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys)
             if x is not None and y is not None
             and math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return None
    xs2 = [p[0] for p in pairs]
    ys2 = [p[1] for p in pairs]
    mx, my = statistics.mean(xs2), statistics.mean(ys2)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs2))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys2))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _sessions(db_path: Path):
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    rows = []
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ts, open, high, low, close FROM intraday_prices "
            "WHERE symbol='RELIANCE' AND interval='15m' ORDER BY ts"
        ).fetchall()
    by_day = defaultdict(list)
    for r in rows:
        ts = datetime.fromisoformat(r["ts"]).astimezone(IST)
        by_day[ts.date()].append(r)
    sessions = []
    for day in sorted(by_day):
        bars = by_day[day]
        o0 = float(bars[0]["open"])
        hi = max(float(b["high"]) for b in bars)
        lo = min(float(b["low"]) for b in bars)
        cl = float(bars[-1]["close"])
        if o0 <= 0:
            continue
        sessions.append({
            "date": day,
            "open": o0,
            "close": cl,
            "range_pct": (hi - lo) / o0 * 100,
            "oc_pct": (cl - o0) / o0 * 100,
            "bars": len(bars),
            "expiry": day == _monthly_expiry_session(day.year, day.month),
        })
    # gap vs previous session close
    for i in range(1, len(sessions)):
        prev_close = sessions[i - 1]["close"]
        sessions[i]["gap_pct"] = (sessions[i]["open"] - prev_close) / prev_close * 100
    return sessions


def main() -> int:
    sessions = _sessions(DB_PATH)
    full = [s for s in sessions if s["bars"] >= 18]  # ~>=70% of a 25-bar session
    print("VOLATILITY PERSISTENCE EDA — RELIANCE 15m (read-only)")
    print(f"Sessions total: {len(sessions)} | with near-full coverage (>=18 bars): {len(full)}")
    if len(full) < 8:
        print("Too few full sessions for a meaningful read — collect more data.")
        return 0

    ranges = [s["range_pct"] for s in full]
    print(f"\nDaily high-low range %: median={statistics.median(ranges):.2f} "
          f"mean={statistics.mean(ranges):.2f} min={min(ranges):.2f} max={max(ranges):.2f}")

    # 1) Persistence: does session N-1 range predict session N range?
    prev = [full[i - 1]["range_pct"] for i in range(1, len(full))]
    cur = [full[i]["range_pct"] for i in range(1, len(full))]
    corr = _pearson(prev, cur)
    print(f"\n[Persistence] lag-1 autocorrelation of daily range: "
          f"{'%.3f' % corr if corr is not None else 'n/a'}")

    med = statistics.median(ranges)
    hi_then_hi = sum(1 for i in range(1, len(full))
                     if full[i - 1]["range_pct"] > med and full[i]["range_pct"] > med)
    hi_prev = sum(1 for i in range(1, len(full)) if full[i - 1]["range_pct"] > med)
    base = sum(1 for s in full if s["range_pct"] > med) / len(full)
    cond = (hi_then_hi / hi_prev) if hi_prev else None
    print(f"[Persistence] P(high-range day) overall = {base*100:.0f}%; "
          f"P(high-range | prev day high-range) = "
          f"{'%.0f%%' % (cond*100) if cond is not None else 'n/a'}")

    # 2) Gap size vs same-day range
    gap_abs = [abs(s.get("gap_pct")) for s in full if s.get("gap_pct") is not None]
    gap_range = [s["range_pct"] for s in full if s.get("gap_pct") is not None]
    gcorr = _pearson(gap_abs, gap_range)
    print(f"\n[Gap] corr(|gap%|, same-day range%): "
          f"{'%.3f' % gcorr if gcorr is not None else 'n/a'}")

    # 3) Expiry sessions vs the rest
    exp = [s["range_pct"] for s in full if s["expiry"]]
    non = [s["range_pct"] for s in full if not s["expiry"]]
    if exp and non:
        print(f"\n[Expiry] mean range on expiry sessions={statistics.mean(exp):.2f}% "
              f"(n={len(exp)}) vs non-expiry={statistics.mean(non):.2f}% (n={len(non)})")
    else:
        print(f"\n[Expiry] not enough expiry sessions in range (expiry n={len(exp)})")

    print("\nInterpretation: persistence/gap/expiry describe WHEN ranges are large, "
          "not direction. A candidate still needs a directional rule and must clear "
          "the full ladder. Small sample — treat as motivation, not evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
