"""
Entry-signal policy — the three CONTROLLED upgrades to the entry decision.

This is deliberately a *toggle box*: each upgrade is an independent flag so we can
change ONE group at a time and measure its effect honestly. It contains no
predictions and no fabricated numbers — only deterministic conditions on real bars.

Upgrade groups
  1. volume_confirmation  — require volume expansion vs its 20-bar average; this is how
                            we "avoid weak breakouts" (no conviction → no entry).
  2. regime_specific      — pick the entry archetype from the INDEPENDENT index regime:
                              RANGE      → mean-reversion only (oversold + lower band)
                              TREND_UP   → continuation only (pullback to EMA OR breakout)
                              TREND_DOWN → avoid long-only entries (stand aside)
  3. improved_targets     — wider target (target_r), explicit ATR stop (atr_stop_mult,
                            applied via position sizing so risk stays consistent), and a
                            charge guard (skip when charges eat too much of the target).

decide_entry returns one of:
  ("take",   proposal)   — enter this trade
  ("reject", reason)     — a setup existed but an added quality rule blocked it (counted)
  ("skip",   None)       — no setup on this bar (not a "rejection", just no trade)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class EntryConfig:
    name: str = "baseline"
    # group 1
    volume_confirmation: bool = False
    vol_expansion_mult: float = 1.2
    # group 2
    regime_specific: bool = False
    rsi_oversold: float = 35.0
    pullback_atr: float = 0.5        # "near EMA" = within this many ATRs of ema_fast
    # group 3
    target_r: float = 2.0            # target = entry + target_r * stop_distance
    atr_stop_mult: Optional[float] = None   # None → use the engine's default ATR stop
    max_charge_ratio: Optional[float] = None  # None → no charge guard
    # group 4 — "fewer, higher-quality entries"
    min_score: Optional[float] = None       # raise the BUY cutoff above 0.65 (None = base)
    require_confluence: bool = False         # require momentum agreement (EMA + ST + RSI)
    confluence_rsi_lo: float = 50.0          # RSI healthy-momentum band
    confluence_rsi_hi: float = 70.0
    avoid_trend_down: bool = False           # no long entries when index regime = TREND_DOWN
    only_regime: Optional[str] = None        # if set, ONLY enter when index regime == this


@dataclass(frozen=True)
class EntryProposal:
    archetype: str
    target_r: float


def decide_entry(
    *,
    regime: str,
    base_is_buy: bool,
    price: float,
    atr: float,
    rsi: Optional[float],
    ema_fast: float,
    boll_lower: float,
    prior_high: float,
    volume: float,
    vol_sma: float,
    stop_distance: float,
    qty: float,
    charges: float,
    cfg: EntryConfig,
    entry_score: Optional[float] = None,
    ema_slow: Optional[float] = None,
    st_trend: Optional[str] = None,
) -> Tuple[str, object]:
    # ── 1. Is there a setup on this bar? ──────────────────────────────────────
    if cfg.regime_specific:
        if regime == "TREND_DOWN":
            # Long-only system: avoid longs into a down-trending market.
            return ("reject", "trend_down_avoid") if base_is_buy else ("skip", None)
        if regime == "RANGE":
            oversold = rsi is not None and rsi <= cfg.rsi_oversold
            at_band = boll_lower == boll_lower and price <= boll_lower  # NaN-safe
            if not (oversold and at_band):
                return ("skip", None)
            archetype = "mean_reversion"
        else:  # TREND_UP
            pullback = abs(price - ema_fast) <= cfg.pullback_atr * atr
            breakout = prior_high == prior_high and price > prior_high   # NaN-safe
            if not (pullback or breakout):
                return ("skip", None)
            archetype = "continuation"
    else:
        # Restrict to a single index regime (used by the walk-forward pocket test).
        if cfg.only_regime is not None and regime != cfg.only_regime:
            return ("skip", None)
        # Upgrade 4 — avoid long entries when the index regime is TREND_DOWN.
        if cfg.avoid_trend_down and regime == "TREND_DOWN":
            return ("reject", "trend_down_avoid") if base_is_buy else ("skip", None)
        # Upgrades 1/2/5 — stricter BUY cutoff (reject marginal scores).
        if cfg.min_score is not None:
            if entry_score is None or entry_score < cfg.min_score:
                return ("reject", "below_min_score") if base_is_buy else ("skip", None)
        elif not base_is_buy:
            return ("skip", None)
        # Upgrade 3 — momentum confluence (EMA stack + Supertrend + RSI band).
        if cfg.require_confluence:
            momentum_ok = (
                ema_slow is not None and ema_fast > ema_slow
                and st_trend == "green"
                and rsi is not None and cfg.confluence_rsi_lo <= rsi <= cfg.confluence_rsi_hi
            )
            if not momentum_ok:
                return ("reject", "no_confluence")
        archetype = ("high_quality"
                     if (cfg.min_score or cfg.require_confluence or cfg.avoid_trend_down)
                     else "baseline")

    # ── 2. Volume confirmation (group 1) ──────────────────────────────────────
    if cfg.volume_confirmation:
        if not (vol_sma == vol_sma and vol_sma > 0 and volume > cfg.vol_expansion_mult * vol_sma):
            return ("reject", "weak_volume")

    # ── 3. Charge guard (group 3) ─────────────────────────────────────────────
    target = price + cfg.target_r * stop_distance
    reward_gross = (target - price) * qty
    if cfg.max_charge_ratio is not None and reward_gross > 0:
        if charges / reward_gross > cfg.max_charge_ratio:
            return ("reject", "charge_ratio")

    return ("take", EntryProposal(archetype=archetype, target_r=cfg.target_r))


# ── Experiment presets: change ONE group at a time, then combine ─────────────
def variants() -> list[EntryConfig]:
    return [
        EntryConfig(name="baseline"),
        EntryConfig(name="v1_volume", volume_confirmation=True),
        EntryConfig(name="v2_regime", regime_specific=True),
        EntryConfig(name="v3_targets", target_r=3.0, atr_stop_mult=1.5, max_charge_ratio=0.25),
        EntryConfig(name="v_all", volume_confirmation=True, regime_specific=True,
                    target_r=3.0, atr_stop_mult=1.5, max_charge_ratio=0.25),
    ]


def quality_variants() -> list[EntryConfig]:
    """
    'Fewer, higher-quality entries' experiment. Each lever isolated, then combined.
    Stop/target held at the baseline 2R so any win-rate change is attributable to the
    ENTRY quality, not the exit math. 'baseline' here is the OLD signal (score >= 0.65).
    """
    return [
        EntryConfig(name="baseline"),                              # OLD: score >= 0.65
        EntryConfig(name="q1_cutoff72", min_score=0.72),           # raise BUY cutoff
        EntryConfig(name="q2_confluence", require_confluence=True, volume_confirmation=True),
        EntryConfig(name="q3_no_downtrend", avoid_trend_down=True),
        EntryConfig(name="q_highquality",                          # NEW: all combined
                    min_score=0.72, require_confluence=True,
                    volume_confirmation=True, avoid_trend_down=True),
    ]
