"""Mine real RELIANCE daily OHLCV history for cost-aware hypotheses.

Read-only over kite_bot.db. This is daily-timeframe EDA, not a trading signal:
patterns are hypotheses only until they pass Spencer's Confirm-or-Kill ladder.
Writes workflow/research_findings_daily.json and a brain note.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = ROOT / "kite_bot.db"
OUT = ROOT / "workflow" / "research_findings_daily.json"
BRAIN_NOTE = ROOT / "brain" / "Latest Daily Research Scan.md"
SYMBOL = "RELIANCE"

# Daily delivery round-trip costs are roughly larger than intraday and still
# need a wide margin before an idea deserves formal testing.
ROUND_TRIP_COST = 0.0025
EDGE_TARGET = 3 * ROUND_TRIP_COST


@dataclass(frozen=True)
class DailyRow:
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None


def _stats(xs: Sequence[float]) -> dict:
    n = len(xs)
    if n < 2:
        return {"n": n, "mean": None, "std": None, "t": None}
    mean = statistics.fmean(xs)
    std = statistics.pstdev(xs)
    t_stat = (mean / (std / math.sqrt(n))) if std > 0 else 0.0
    return {"n": n, "mean": mean, "std": std, "t": t_stat}


def pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:+.3f}%"


def load_daily_rows(db_path: Path | str = DB) -> list[DailyRow]:
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(daily_prices)").fetchall()}
        required = {"trade_date", "open", "high", "low", "close"}
        if not required.issubset(columns):
            return []
        volume_expr = "volume" if "volume" in columns else "NULL"
        rows = conn.execute(
            f"""
            SELECT trade_date, open, high, low, close, {volume_expr}
            FROM daily_prices
            WHERE symbol=? AND open IS NOT NULL AND high IS NOT NULL
              AND low IS NOT NULL AND close IS NOT NULL
            ORDER BY trade_date
            """,
            (SYMBOL,),
        ).fetchall()
    out = []
    for trade_date, open_, high, low, close, volume in rows:
        out.append(
            DailyRow(
                trade_date=str(trade_date),
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=None if volume is None else float(volume),
            )
        )
    return out


def _add_findings(findings: list[dict], name: str, hypothesis: str, values: Sequence[float]) -> None:
    stats = _stats(values)
    if stats["mean"] is None:
        findings.append(
            {
                "name": name,
                "hypothesis": hypothesis,
                "n": stats["n"],
                "mean": None,
                "t_stat": None,
                "net_after_cost": None,
                "clears_cost_bar": False,
                "clears_3x_edge_target": False,
                "significant": False,
                "status": "DATA_INSUFFICIENT",
            }
        )
        return
    edge = abs(stats["mean"])
    net_after_cost = edge - ROUND_TRIP_COST
    findings.append(
        {
            "name": name,
            "hypothesis": hypothesis,
            "n": stats["n"],
            "mean": round(stats["mean"], 8),
            "t_stat": round(stats["t"], 2),
            "net_after_cost": round(net_after_cost, 6),
            "clears_cost_bar": net_after_cost > 0,
            "clears_3x_edge_target": edge >= EDGE_TARGET,
            "significant": abs(stats["t"]) >= 2.0,
        }
    )


def scan_daily(rows: Sequence[DailyRow]) -> dict:
    findings: list[dict] = []
    close_to_close: list[float] = []
    momentum_up_next: list[float] = []
    momentum_down_next: list[float] = []
    mean_revert_up_next: list[float] = []
    mean_revert_down_next: list[float] = []
    gap_up: list[float] = []
    gap_down: list[float] = []
    dow: dict[int, list[float]] = {idx: [] for idx in range(5)}
    vol_breakout_next: list[float] = []

    closes: list[float] = []
    ranges: list[float] = []
    for idx, row in enumerate(rows):
        intraday = row.close / row.open - 1.0
        day_idx = datetime.fromisoformat(row.trade_date).weekday()
        if day_idx in dow:
            dow[day_idx].append(intraday)
        if idx > 0:
            prev = rows[idx - 1]
            cc = row.close / prev.close - 1.0
            close_to_close.append(cc)
            gap = row.open / prev.close - 1.0
            (gap_up if gap > 0 else gap_down).append(intraday)
        if idx > 0 and idx + 1 < len(rows):
            prev_cc = row.close / rows[idx - 1].close - 1.0
            next_cc = rows[idx + 1].close / row.close - 1.0
            (momentum_up_next if prev_cc > 0 else momentum_down_next).append(next_cc)
            (mean_revert_up_next if prev_cc > 0 else mean_revert_down_next).append(-next_cc)
        if len(ranges) >= 20 and idx + 1 < len(rows):
            today_range = (row.high - row.low) / row.close
            avg_range = statistics.fmean(ranges[-20:])
            if today_range > 1.5 * avg_range:
                vol_breakout_next.append(rows[idx + 1].close / row.close - 1.0)
        closes.append(row.close)
        ranges.append((row.high - row.low) / row.close)

    _add_findings(findings, "close_to_close_drift", "Hold one daily close to next daily close.", close_to_close)
    _add_findings(findings, "one_day_momentum_up", "Up close-to-close day continues next day.", momentum_up_next)
    _add_findings(findings, "one_day_momentum_down", "Down close-to-close day continues next day.", momentum_down_next)
    _add_findings(findings, "one_day_mean_revert_after_up", "Fade the next day after an up day.", mean_revert_up_next)
    _add_findings(findings, "one_day_mean_revert_after_down", "Fade the next day after a down day.", mean_revert_down_next)
    _add_findings(findings, "gap_up_intraday", "Gap-up daily open continues/fades into same-day close.", gap_up)
    _add_findings(findings, "gap_down_intraday", "Gap-down daily open continues/fades into same-day close.", gap_down)
    _add_findings(findings, "volatility_breakout_followthrough", "Large daily range is followed by next-day movement.", vol_breakout_next)
    names = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    for idx, values in dow.items():
        _add_findings(findings, f"day_of_week_{names[idx]}", f"{names[idx].title()} intraday drift.", values)

    date_range = [rows[0].trade_date, rows[-1].trade_date] if rows else []
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": "1d",
        "symbol": SYMBOL,
        "sessions_analyzed": len(rows),
        "date_range": date_range,
        "cost_bar_round_trip": ROUND_TRIP_COST,
        "edge_target_3x": EDGE_TARGET,
        "findings": sorted(findings, key=lambda item: (-item["clears_3x_edge_target"], -abs(item["mean"] or 0.0))),
        "note": "Hypotheses only. Real daily OHLCV, no fake data, no deployment without Confirm-or-Kill.",
    }


def write_outputs(report: dict, *, out_path: Path = OUT, brain_note: Path = BRAIN_NOTE) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "---",
        "tags: [spencer, research, generated, daily]",
        f"updated: {report['generated_at']}",
        "managed: false",
        'source_path: "scripts/research_scan_daily.py"',
        "---",
        "# Latest Daily Research Scan",
        "",
        f"> Read-only EDA over {report['sessions_analyzed']} real RELIANCE daily sessions. "
        "Hypotheses only; nothing here is validated until it clears the [[Confirm-or-Kill]] ladder.",
        "",
        "| pattern | n | mean | t | clears cost? | clears 3x? |",
        "|---|---|---|---|---|---|",
    ]
    for finding in report["findings"]:
        lines.append(
            f"| {finding['name']} | {finding['n']} | {pct(finding['mean'])} | "
            f"{finding['t_stat']} | {'yes' if finding['clears_cost_bar'] else 'no'} | "
            f"{'yes' if finding['clears_3x_edge_target'] else 'no'} |"
        )
    strong = [
        finding
        for finding in report["findings"]
        if finding["clears_cost_bar"] and finding["significant"]
    ]
    lines.append("")
    if strong:
        lines.append("## Formalization candidates")
        for finding in strong:
            lines.append(f"- **{finding['name']}** - {finding['hypothesis']} (mean {pct(finding['mean'])}, t={finding['t_stat']})")
    else:
        lines.append("No daily pattern both clears cost and reaches statistical notability yet.")
    lines += ["", "Back to [[Research Findings]] · [[Research Ledger]] · [[Spencer]]."]
    brain_note.parent.mkdir(parents=True, exist_ok=True)
    brain_note.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_scan(
    *,
    db_path: Path | str = DB,
    out_path: Path = OUT,
    brain_note: Path = BRAIN_NOTE,
) -> dict:
    report = scan_daily(load_daily_rows(db_path))
    write_outputs(report, out_path=out_path, brain_note=brain_note)
    return report


def main() -> int:
    report = run_scan()
    date_range = report["date_range"] or ["n/a", "n/a"]
    print(f"=== Spencer daily research scan: {report['sessions_analyzed']} sessions ({date_range[0]}..{date_range[-1]}) ===")
    print(f"Cost bar: {pct(report['cost_bar_round_trip'])} | edge target ~3x: {pct(report['edge_target_3x'])}")
    for finding in report["findings"]:
        print(
            f"{finding['name']:34} n={finding['n']:>4} mean={pct(finding['mean']):>10} "
            f"t={str(finding['t_stat']):>5} clears_cost={finding['clears_cost_bar']}"
        )
    print(f"WROTE {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
