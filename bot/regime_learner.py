"""
Phase 3 — anti-overfit per-REGIME trust layer.

Extends bot.learner (which adapts global scoring weights) with a second, orthogonal
question: *in which market regimes does our playbook actually make money?*

Why a new regime axis: in the backtest, every entry is tagged TREND_UP because the
entry filter (EMA stack + green Supertrend) is collinear with a per-stock trend label.
So we measure regime INDEPENDENTLY of the entry — using the Nifty-50 index regime on
the trade's entry date. That answers "does this strategy work when the broad market is
trending up vs down vs ranging?" — which the per-stock label cannot.

Anti-overfit guardrails (mirroring learner.py's discipline):
  - Closed trades only. No open positions, no look-ahead (index regime is as-of the
    entry date, computed from causal indicators).
  - Min-sample per regime: below MIN_TRADES_PER_REGIME → trust = 1.0 (neutral). Thin
    data never penalizes and never rewards.
  - DOWN-ONLY trust in [TRUST_FLOOR, 1.0]. We can shrink size in regimes that lose, but
    we never amplify above 1.0 — no leverage from curve-fitting a good-looking bucket.
  - Deterministic: same journal + same index data → same output.
  - Backed-up: previous regime_trust.json copied to .bak before overwrite.

Output: regime_trust.json — a small, auditable table the scanner/router can read to
scale position size (or gate entries) by the CURRENT index regime.

Usage:
    python -m bot.regime_learner --journal backtest_journal.db
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

DEFAULT_TRUST_PATH = Path(__file__).parent.parent / "regime_trust.json"

MIN_TRADES_PER_REGIME = 20      # below this, trust stays neutral (1.0)
TRUST_FLOOR           = 0.25    # never shrink a regime below 25% size
INDEX_TICKER          = "^NSEI"  # Nifty 50
EMA_FAST, EMA_SLOW    = 20, 50
SLOPE_LOOKBACK        = 5

REGIMES = ("TREND_UP", "TREND_DOWN", "RANGE")


@dataclass
class RegimeStat:
    regime:        str
    trades:        int = 0
    wins:          int = 0
    win_rate:      float = 0.0
    net_pnl:       float = 0.0
    avg_pnl:       float = 0.0        # expectancy per trade (₹)
    trust:         float = 1.0        # bounded down-only multiplier
    sufficient:    bool = False
    note:          str = ""


@dataclass
class RegimeTrustProfile:
    regimes:      Dict[str, dict] = field(default_factory=dict)
    total_trades: int = 0
    last_updated: str = ""
    notes:        str = ""


# ── Independent index regime (pure, causal) ──────────────────────────────────
def classify_index_regimes(index_df: pd.DataFrame) -> pd.Series:
    """
    Map each index date -> {TREND_UP, TREND_DOWN, RANGE} using a causal 20/50 EMA
    stack + fast-EMA slope. No future data is used at any row.
    Returns a Series indexed by date (datetime.date) for easy joining.
    """
    close = index_df["close"]
    ema_f = close.ewm(span=EMA_FAST, adjust=False).mean()
    ema_s = close.ewm(span=EMA_SLOW, adjust=False).mean()
    slope_up = ema_f > ema_f.shift(SLOPE_LOOKBACK)

    out = []
    for i in range(len(close)):
        c, ef, es = close.iloc[i], ema_f.iloc[i], ema_s.iloc[i]
        if i < EMA_SLOW:
            out.append("RANGE")          # warmup -> neutral bucket
        elif c > ef > es and bool(slope_up.iloc[i]):
            out.append("TREND_UP")
        elif c < ef < es and not bool(slope_up.iloc[i]):
            out.append("TREND_DOWN")
        else:
            out.append("RANGE")
    s = pd.Series(out, index=[d.date() if hasattr(d, "date") else d for d in index_df.index])
    return s


def fetch_index(years: int = 2) -> Optional[pd.DataFrame]:
    import yfinance as yf
    try:
        raw = yf.download(INDEX_TICKER, period=f"{years}y", interval="1d",
                          auto_adjust=False, progress=False, threads=False)
    except Exception:
        return None
    if raw is None or raw.empty:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(columns={c: str(c).lower() for c in raw.columns})
    return raw[["open", "high", "low", "close"]].dropna()


# ── Load closed trades from a backtest (or live) journal ─────────────────────
def load_closed_trades(journal_path: str | Path) -> List[dict]:
    conn = sqlite3.connect(str(journal_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT symbol, entry_date, pnl FROM backtest_trades "
            "WHERE pnl IS NOT NULL ORDER BY entry_date ASC"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Trust policy (deterministic, bounded, down-only) ─────────────────────────
def _trust_from_expectancy(avg_pnl: float, overall_avg: float) -> float:
    """
    Down-only multiplier:
      - avg_pnl >= 0           → 1.0 (full size; we never reward above 1.0)
      - avg_pnl <  0           → scale down toward TRUST_FLOOR by how negative it is
                                  relative to the worst-case anchor.
    Deterministic and bounded; no tuning to maximize past P&L.
    """
    if avg_pnl >= 0:
        return 1.0
    # Anchor the shrink on the overall average magnitude so it is scale-aware.
    anchor = abs(overall_avg) if overall_avg < 0 else max(1.0, abs(overall_avg))
    severity = min(1.0, abs(avg_pnl) / (anchor + 1e-9))   # 0..1
    trust = 1.0 - severity * (1.0 - TRUST_FLOOR)
    return round(max(TRUST_FLOOR, min(1.0, trust)), 4)


def compute_regime_trust(
    trades: List[dict], index_regimes: pd.Series
) -> RegimeTrustProfile:
    # Attribute each trade to the index regime on its entry date.
    buckets: Dict[str, List[float]] = {r: [] for r in REGIMES}
    unmatched = 0
    for t in trades:
        d = pd.to_datetime(t["entry_date"]).date()
        regime = index_regimes.get(d)
        if regime is None:
            # nearest prior trading day (markets closed on entry_date is unusual here)
            prior = index_regimes[index_regimes.index <= d]
            if len(prior) == 0:
                unmatched += 1
                continue
            regime = prior.iloc[-1]
        buckets.setdefault(regime, []).append(float(t["pnl"]))

    all_pnls = [p for v in buckets.values() for p in v]
    overall_avg = (sum(all_pnls) / len(all_pnls)) if all_pnls else 0.0

    regimes_out: Dict[str, dict] = {}
    for regime in REGIMES:
        pnls = buckets.get(regime, [])
        n = len(pnls)
        if n == 0:
            regimes_out[regime] = asdict(RegimeStat(regime=regime, note="no trades"))
            continue
        wins = sum(1 for p in pnls if p > 0)
        net = sum(pnls)
        avg = net / n
        sufficient = n >= MIN_TRADES_PER_REGIME
        if sufficient:
            trust = _trust_from_expectancy(avg, overall_avg)
            note = "trust set from expectancy"
        else:
            trust = 1.0
            note = f"insufficient sample (<{MIN_TRADES_PER_REGIME}); trust neutral"
        regimes_out[regime] = asdict(RegimeStat(
            regime=regime, trades=n, wins=wins,
            win_rate=round(wins / n, 4), net_pnl=round(net, 2),
            avg_pnl=round(avg, 2), trust=trust, sufficient=sufficient, note=note,
        ))

    return RegimeTrustProfile(
        regimes=regimes_out,
        total_trades=len(all_pnls),
        last_updated=datetime.now().isoformat(timespec="seconds"),
        notes=(f"per-regime trust from index ({INDEX_TICKER}); "
               f"down-only [{TRUST_FLOOR},1.0]; min_sample={MIN_TRADES_PER_REGIME}; "
               f"unmatched_trades={unmatched}"),
    )


def save_profile(profile: RegimeTrustProfile, path: Path = DEFAULT_TRUST_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        except Exception:
            pass
    path.write_text(json.dumps(asdict(profile), indent=2, sort_keys=True), encoding="utf-8")
    return path


def update_regime_trust(
    journal_path: str | Path = "backtest_journal.db",
    index_df: Optional[pd.DataFrame] = None,
    out_path: Path = DEFAULT_TRUST_PATH,
    years: int = 2,
) -> RegimeTrustProfile:
    trades = load_closed_trades(journal_path)
    if index_df is None:
        index_df = fetch_index(years)
        if index_df is None:
            raise RuntimeError("Could not fetch index data; pass index_df explicitly.")
    regimes = classify_index_regimes(index_df)
    profile = compute_regime_trust(trades, regimes)
    save_profile(profile, out_path)
    return profile


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="bot.regime_learner")
    p.add_argument("--journal", default="backtest_journal.db")
    p.add_argument("--years", type=int, default=2)
    p.add_argument("--out", default=str(DEFAULT_TRUST_PATH))
    args = p.parse_args(argv)
    profile = update_regime_trust(args.journal, out_path=Path(args.out), years=args.years)
    print(json.dumps(asdict(profile), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
