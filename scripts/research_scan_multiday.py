"""Search RELIANCE daily history for multi-day swing hypotheses.

Read-only over kite_bot.db. This is an idea miner for the new 1d backtest mode:
it reports cost-aware hypotheses over 2/3/5/10-session holds and never trades,
never writes live journals, and never claims validation.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.charges import round_trip_cost
from bot.config import default_config
from bot.research_candidates import CAPITAL_BASIS_INR
from scripts.research_scan_daily import DailyRow, load_daily_rows, pct

DB = ROOT / "kite_bot.db"
OUT = ROOT / "workflow" / "research_findings_multiday.json"
BRAIN_NOTE = ROOT / "brain" / "Latest Multi-Day Research Scan.md"
HORIZONS = (2, 3, 5, 10)
SYMBOL = "RELIANCE"


@dataclass(frozen=True)
class Sample:
    idx: int
    value: float
    entry_price: float


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _t_stat(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    std = statistics.pstdev(values)
    if std <= 0:
        return 0.0
    return mean / (std / math.sqrt(len(values)))


def _affordable_qty(price: float) -> int:
    return max(1, min(3, int(CAPITAL_BASIS_INR // price)))


def _round_trip_cost_pct(price: float) -> float:
    qty = _affordable_qty(price)
    notional = price * qty
    charges_pct = round_trip_cost(price, qty, "DELIVERY") / notional
    slippage_pct = 2 * default_config().fees.delivery_slippage_bps / 10_000
    return charges_pct + slippage_pct


def _forward_return(rows: Sequence[DailyRow], idx: int, horizon: int) -> float | None:
    end = idx + horizon
    if idx < 0 or end >= len(rows):
        return None
    entry = rows[idx].close
    if entry <= 0:
        return None
    return rows[end].close / entry - 1.0


def _rolling_mean(values: Sequence[float], end_exclusive: int, window: int) -> float | None:
    start = end_exclusive - window
    if start < 0:
        return None
    return statistics.fmean(values[start:end_exclusive])


Condition = Callable[[Sequence[DailyRow], int], bool]


def _close_location(row: DailyRow) -> float:
    width = row.high - row.low
    if width <= 0:
        return float("nan")
    return (row.close - row.low) / width


def _pattern_samples(
    rows: Sequence[DailyRow],
    *,
    horizon: int,
    condition: Condition,
    side: str = "LONG",
) -> list[Sample]:
    samples: list[Sample] = []
    for idx in range(len(rows) - horizon):
        if not condition(rows, idx):
            continue
        forward = _forward_return(rows, idx, horizon)
        if forward is None:
            continue
        value = forward if side == "LONG" else -forward
        samples.append(Sample(idx=idx, value=value, entry_price=rows[idx].close))
    return samples


def _finding(name: str, hypothesis: str, horizon: int, side: str, samples: Sequence[Sample]) -> dict:
    values = [sample.value for sample in samples]
    mean = _mean(values)
    t_stat = _t_stat(values)
    avg_cost = _mean([_round_trip_cost_pct(sample.entry_price) for sample in samples])
    if mean is None or avg_cost is None:
        return {
            "name": name,
            "hypothesis": hypothesis,
            "horizon_sessions": horizon,
            "side": side,
            "n": len(samples),
            "mean": None,
            "t_stat": None,
            "avg_delivery_cost": avg_cost,
            "net_after_cost": None,
            "clears_cost_bar": False,
            "clears_3x_cost_bar": False,
            "significant": False,
            "status": "DATA_INSUFFICIENT",
        }
    net = abs(mean) - avg_cost
    return {
        "name": name,
        "hypothesis": hypothesis,
        "horizon_sessions": horizon,
        "side": side,
        "n": len(samples),
        "mean": round(mean, 8),
        "t_stat": None if t_stat is None else round(t_stat, 2),
        "avg_delivery_cost": round(avg_cost, 6),
        "net_after_cost": round(net, 6),
        "clears_cost_bar": net > 0,
        "clears_3x_cost_bar": abs(mean) >= 3 * avg_cost,
        "significant": bool(t_stat is not None and abs(t_stat) >= 2.0),
    }


def scan_multiday(rows: Sequence[DailyRow]) -> dict:
    closes = [row.close for row in rows]
    volumes = [row.volume or 0.0 for row in rows]
    findings: list[dict] = []

    def prior_3_drop(rows_: Sequence[DailyRow], idx: int) -> bool:
        if idx < 3:
            return False
        return rows_[idx].close / rows_[idx - 3].close - 1.0 <= -0.02

    def prior_3_rip(rows_: Sequence[DailyRow], idx: int) -> bool:
        if idx < 3:
            return False
        return rows_[idx].close / rows_[idx - 3].close - 1.0 >= 0.02

    def close_bottom_quartile(rows_: Sequence[DailyRow], idx: int) -> bool:
        return _close_location(rows_[idx]) <= 0.25

    def close_top_quartile(rows_: Sequence[DailyRow], idx: int) -> bool:
        return _close_location(rows_[idx]) >= 0.75

    def volume_washout(rows_: Sequence[DailyRow], idx: int) -> bool:
        avg = _rolling_mean(volumes, idx, 20)
        return avg is not None and volumes[idx] > 1.5 * avg and _close_location(rows_[idx]) <= 0.35

    def breakout_20(rows_: Sequence[DailyRow], idx: int) -> bool:
        if idx < 20:
            return False
        return rows_[idx].close > max(closes[idx - 20:idx])

    def breakdown_20(rows_: Sequence[DailyRow], idx: int) -> bool:
        if idx < 20:
            return False
        return rows_[idx].close < min(closes[idx - 20:idx])

    pattern_defs = [
        ("drop_revert", "After a 3-session drop >=2%, RELIANCE mean-reverts over the hold window.", "LONG", prior_3_drop),
        ("rip_fade", "After a 3-session rally >=2%, RELIANCE fades over the hold window.", "SHORT", prior_3_rip),
        ("bottom_close_revert", "A close in the bottom quartile of the daily range mean-reverts.", "LONG", close_bottom_quartile),
        ("top_close_fade", "A close in the top quartile of the daily range fades.", "SHORT", close_top_quartile),
        ("volume_washout_revert", "High-volume weak close mean-reverts over multiple days.", "LONG", volume_washout),
        ("breakout_followthrough", "20-day closing breakout continues.", "LONG", breakout_20),
        ("breakdown_followthrough", "20-day closing breakdown continues downward.", "SHORT", breakdown_20),
    ]
    for horizon in HORIZONS:
        for name, hypothesis, side, condition in pattern_defs:
            samples = _pattern_samples(rows, horizon=horizon, condition=condition, side=side)
            findings.append(_finding(f"{name}_{horizon}d", hypothesis, horizon, side, samples))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": SYMBOL,
        "timeframe": "1d",
        "sessions_analyzed": len(rows),
        "date_range": [rows[0].trade_date, rows[-1].trade_date] if rows else [],
        "horizons": list(HORIZONS),
        "capital_basis_inr": CAPITAL_BASIS_INR,
        "max_qty_model": "min(3, floor(5000 / entry_close))",
        "cost_model": "bot.charges.round_trip_cost(..., product='DELIVERY') + configured delivery slippage both sides",
        "findings": sorted(
            findings,
            key=lambda item: (
                -int(item["clears_3x_cost_bar"]),
                -int(item["clears_cost_bar"]),
                -abs(item["mean"] or 0.0),
            ),
        ),
        "note": "Hypotheses only. Formal candidates must still pass the Confirm-or-Kill ladder.",
    }


def write_outputs(report: dict, *, out_path: Path = OUT, brain_note: Path = BRAIN_NOTE) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "---",
        "tags: [spencer, research, generated, multiday]",
        f"updated: {report['generated_at']}",
        "managed: false",
        'source_path: "scripts/research_scan_multiday.py"',
        "---",
        "# Latest Multi-Day Research Scan",
        "",
        f"> Read-only scan over {report['sessions_analyzed']} real RELIANCE daily sessions. "
        "These are hypotheses only; they are not deployable edges.",
        "",
        "| pattern | side | hold | n | mean | avg cost | clears 3x? | t |",
        "|---|---|---:|---:|---:|---:|---|---:|",
    ]
    for finding in report["findings"][:20]:
        lines.append(
            f"| {finding['name']} | {finding['side']} | {finding['horizon_sessions']} | "
            f"{finding['n']} | {pct(finding['mean'])} | {pct(finding['avg_delivery_cost'])} | "
            f"{'yes' if finding['clears_3x_cost_bar'] else 'no'} | {finding['t_stat']} |"
        )
    lines += ["", "Back to [[Research Findings]] · [[Backtest Harness]] · [[Spencer]]."]
    brain_note.parent.mkdir(parents=True, exist_ok=True)
    brain_note.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_scan(
    *,
    db_path: Path | str = DB,
    out_path: Path = OUT,
    brain_note: Path = BRAIN_NOTE,
) -> dict:
    report = scan_multiday(load_daily_rows(db_path))
    write_outputs(report, out_path=out_path, brain_note=brain_note)
    return report


def main() -> int:
    report = run_scan()
    date_range = report["date_range"] or ["n/a", "n/a"]
    print(f"=== Spencer multi-day research scan: {report['sessions_analyzed']} sessions ({date_range[0]}..{date_range[-1]}) ===")
    for finding in report["findings"][:12]:
        print(
            f"{finding['name']:32} {finding['side']:5} h={finding['horizon_sessions']:>2} "
            f"n={finding['n']:>4} mean={pct(finding['mean']):>10} "
            f"cost={pct(finding['avg_delivery_cost']):>9} 3x={finding['clears_3x_cost_bar']}"
        )
    print(f"WROTE {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
