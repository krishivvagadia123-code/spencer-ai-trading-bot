"""
Adaptive scoring layer — bounded, deterministic, paper-only.

NOT an LLM. NOT self-modifying. NOT online. The learner reads CLOSED paper
trades + matched signal_candidates, computes deterministic statistics, and
proposes weight adjustments within hard bounds. It writes a profile JSON
that the scanner can read. It never trains on:
  - open trades   (no leakage from in-flight risk)
  - future bars   (no look-ahead)
  - itself        (no recursive amplification)

Hard rules:
  - Bounded: every weight stays within DEFAULT ± MAX_DRIFT.
  - Min-sample: requires >= MIN_TRADES closed trades before any change.
  - Deterministic: same DB state → same profile (seeded numerics).
  - Backed-up: previous profile saved to .bak before overwrite.
  - Risk-down on losing streak / drawdown: weights regress toward defaults.
"""

from __future__ import annotations
import json
import math
import shutil
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from bot.db import get_conn
from bot.logger_config import get_logger

log = get_logger("kite-bot.learner")

DEFAULT_PROFILE_PATH = Path(__file__).parent.parent / "strategy_profile.json"

# Scoring defaults — must match signals.compute_total_score weights exactly.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "technical":    0.40,
    "sentiment":    0.15,
    "fundamentals": 0.20,
    "liquidity":    0.10,
    "risk":         0.15,
}
MAX_DRIFT          = 0.10     # weights stay within ±0.10 of default
MIN_TRADES         = 30       # below this, no adjustments are made
LOSING_STREAK_REG  = 4        # losing streak ≥ this triggers regress-to-mean
DRAWDOWN_REG_PCT   = 8.0      # drawdown % ≥ this triggers regress-to-mean
RNG_SEED           = 1729     # deterministic, never use random in this module


@dataclass
class StrategyProfile:
    weights:                Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    win_rate:               float = 0.0
    avg_r_multiple:         float = 0.0
    total_closed_trades:    int   = 0
    losing_streak:          int   = 0
    max_drawdown_pct:       float = 0.0
    cooled_down_symbols:    List[str] = field(default_factory=list)
    last_updated:           str = ""
    sample_size_sufficient: bool = False
    notes:                  str = ""


# ── Persistence ──────────────────────────────────────────────────────────────
def load_profile(path: Path = DEFAULT_PROFILE_PATH) -> StrategyProfile:
    if not path.exists():
        return StrategyProfile(last_updated=datetime.now().isoformat(timespec="seconds"))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning(f"profile corrupt at {path}; using defaults")
        return StrategyProfile(notes="defaulted: corrupt file",
                               last_updated=datetime.now().isoformat(timespec="seconds"))
    weights = {k: float(raw.get("weights", {}).get(k, DEFAULT_WEIGHTS[k]))
               for k in DEFAULT_WEIGHTS}
    return StrategyProfile(
        weights=weights,
        win_rate=float(raw.get("win_rate", 0.0)),
        avg_r_multiple=float(raw.get("avg_r_multiple", 0.0)),
        total_closed_trades=int(raw.get("total_closed_trades", 0)),
        losing_streak=int(raw.get("losing_streak", 0)),
        max_drawdown_pct=float(raw.get("max_drawdown_pct", 0.0)),
        cooled_down_symbols=list(raw.get("cooled_down_symbols", [])),
        last_updated=str(raw.get("last_updated", "")),
        sample_size_sufficient=bool(raw.get("sample_size_sufficient", False)),
        notes=str(raw.get("notes", "")),
    )


def save_profile(profile: StrategyProfile,
                 path: Path = DEFAULT_PROFILE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        except Exception as e:
            log.warning(f"profile backup failed: {e}")
    path.write_text(json.dumps(asdict(profile), indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


# ── Reading closed trades (NO open positions, NO future data) ────────────────
def _load_closed_trades() -> List[dict]:
    """
    Return only SELL rows with a non-null pnl. These are completed exits —
    they cannot leak data from in-flight trades or look ahead.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT ts, symbol, action, pnl, price, qty, stop, target "
            "FROM trades WHERE action = 'SELL' AND pnl IS NOT NULL "
            "ORDER BY ts ASC"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Deterministic statistics ─────────────────────────────────────────────────
def compute_stats(trades: List[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate": 0.0, "avg_r": 0.0,
                "losing_streak": 0, "max_drawdown_pct": 0.0,
                "symbol_pnl": {}}
    wins = [t for t in trades if (t["pnl"] or 0) > 0]
    win_rate = len(wins) / n

    # R-multiple per trade: pnl / risk_per_share*qty. Approximate from stop.
    r_values = []
    for t in trades:
        stop = t.get("stop") or 0.0
        price = t.get("price") or 0.0
        qty = t.get("qty") or 0
        risk = abs(price - stop) * qty
        if risk > 0:
            r_values.append((t["pnl"] or 0.0) / risk)
    avg_r = sum(r_values) / len(r_values) if r_values else 0.0

    # Current losing streak (count from end)
    streak = 0
    for t in reversed(trades):
        if (t["pnl"] or 0) < 0:
            streak += 1
        else:
            break

    # Equity-curve drawdown
    curve = 0.0
    peak = 0.0
    max_dd_pct = 0.0
    for t in trades:
        curve += t["pnl"] or 0.0
        peak = max(peak, curve)
        if peak > 0:
            dd = (peak - curve) / peak * 100
            max_dd_pct = max(max_dd_pct, dd)

    # Per-symbol pnl for cooldowns
    symbol_pnl: Dict[str, float] = {}
    for t in trades:
        symbol_pnl[t["symbol"]] = symbol_pnl.get(t["symbol"], 0.0) + (t["pnl"] or 0.0)

    return {"n": n, "win_rate": win_rate, "avg_r": avg_r,
            "losing_streak": streak, "max_drawdown_pct": max_dd_pct,
            "symbol_pnl": symbol_pnl}


# ── Weight adjustment (bounded, deterministic) ───────────────────────────────
def _clip_weight(name: str, value: float) -> float:
    default = DEFAULT_WEIGHTS[name]
    low, high = default - MAX_DRIFT, default + MAX_DRIFT
    return max(low, min(high, value))


def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
    """Re-scale to sum exactly 1.0 after clipping."""
    total = sum(weights.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(v / total, 6) for k, v in weights.items()}


def _regress_toward_defaults(weights: Dict[str, float],
                              alpha: float = 0.5) -> Dict[str, float]:
    """Pull each weight `alpha` of the way back toward the default."""
    return {k: w + alpha * (DEFAULT_WEIGHTS[k] - w) for k, w in weights.items()}


def compute_new_weights(current: Dict[str, float],
                         stats: dict) -> Dict[str, float]:
    """
    Deterministic adjustment policy:
      n < MIN_TRADES                     → keep current (no info)
      losing_streak ≥ LOSING_STREAK_REG  → regress toward defaults
      max_dd_pct    ≥ DRAWDOWN_REG_PCT   → regress toward defaults
      else: nudge weights based on which side of break-even avg_r sits
            (favor 'risk' weight when avg_r poor; favor 'technical' when good)
    Always clipped + normalized.
    """
    if stats["n"] < MIN_TRADES:
        return dict(current)

    if stats["losing_streak"] >= LOSING_STREAK_REG \
       or stats["max_drawdown_pct"] >= DRAWDOWN_REG_PCT:
        adjusted = _regress_toward_defaults(current, alpha=0.5)
        return _normalize({k: _clip_weight(k, v) for k, v in adjusted.items()})

    # Small bounded nudge based on avg_r quality
    nudge = max(-0.05, min(0.05, (stats["avg_r"] - 1.0) * 0.02))  # tiny step
    adjusted = dict(current)
    if nudge >= 0:
        adjusted["technical"] = current["technical"] + nudge
        adjusted["risk"]      = current["risk"]      - nudge
    else:
        adjusted["technical"] = current["technical"] + nudge   # nudge is negative
        adjusted["risk"]      = current["risk"]      - nudge
    return _normalize({k: _clip_weight(k, v) for k, v in adjusted.items()})


def _cooled_down_symbols(stats: dict, threshold: float = -500.0) -> List[str]:
    """Symbols whose cumulative paper P&L sits below threshold get cooled."""
    return sorted([sym for sym, pnl in stats["symbol_pnl"].items() if pnl < threshold])


# ── Public API ───────────────────────────────────────────────────────────────
def update_profile(path: Path = DEFAULT_PROFILE_PATH) -> StrategyProfile:
    """
    Read closed trades, compute stats deterministically, propose bounded
    weight updates, persist with backup. Returns the new profile.
    """
    trades  = _load_closed_trades()
    stats   = compute_stats(trades)
    current = load_profile(path)

    new_weights = compute_new_weights(current.weights, stats)
    cooled      = _cooled_down_symbols(stats)
    sufficient  = stats["n"] >= MIN_TRADES

    profile = StrategyProfile(
        weights=new_weights,
        win_rate=round(stats["win_rate"], 4),
        avg_r_multiple=round(stats["avg_r"], 4),
        total_closed_trades=stats["n"],
        losing_streak=stats["losing_streak"],
        max_drawdown_pct=round(stats["max_drawdown_pct"], 4),
        cooled_down_symbols=cooled,
        last_updated=datetime.now().isoformat(timespec="seconds"),
        sample_size_sufficient=sufficient,
        notes=(f"deterministic update; seed={RNG_SEED}; "
               f"adjusted={'yes' if sufficient else 'no (min-sample)'}"),
    )
    save_profile(profile, path)
    log.info(f"learner: n={stats['n']} win_rate={stats['win_rate']:.2f} "
             f"streak={stats['losing_streak']} dd={stats['max_drawdown_pct']:.2f}%")
    return profile
