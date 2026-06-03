"""
Capital governor — disciplined risk scaling.

Reads the current portfolio + learner profile + regime + leaderboard, returns
the EFFECTIVE per-trade risk percentage that auto-buy is allowed to use.

Hard rules — capital governor never exceeds:
  - the configured RiskConfig.risk_per_trade_pct (config is the ceiling)
  - 1.0% before MIN_PROVEN_TRADES are closed (starts small)
  - 0% in TREND_BEAR regime for altcoins (regime filter takes over)
  - 0% if losing streak ≥ HARD_HALT_STREAK
  - 0% if max-drawdown breach is recorded

Tiers (effective fraction of the configured ceiling):
  T0  : 0 closed trades              →  0.5x   (half of config)
  T1  : 1-29 closed trades           →  0.75x
  T2  : 30-99 closed trades, PF > 1  →  1.0x   (full config)
  T3  : 100+ trades, PF > 1.3, DD<10 →  1.0x   (full config; could scale up
                                                in later phases but capped here)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from bot.config import RiskConfig
from bot.learner import StrategyProfile, load_profile
from bot.logger_config import get_logger

log = get_logger("kite-bot.governor")

MIN_PROVEN_TRADES   = 30
HARD_HALT_STREAK    = 6
MAX_GOVERNED_PCT    = 2.0       # absolute ceiling, regardless of config


@dataclass(frozen=True)
class GovernorDecision:
    effective_risk_pct: float
    tier:               str
    reasons:            list
    halted:             bool


def assess(
    *,
    risk_cfg:         RiskConfig,
    profile:          Optional[StrategyProfile] = None,
    regime_risk_mult: float = 1.0,
) -> GovernorDecision:
    """
    Return the effective per-trade risk pct given the configured ceiling,
    the learner's profile, and the regime multiplier (0..1).

    `regime_risk_mult`:
      1.0 = TREND_BULL  → use full governed risk
      0.5 = RANGE       → half risk
      0.0 = TREND_BEAR  → halts altcoin entries
    """
    profile  = profile or load_profile()
    reasons  = []
    halted   = False

    # Hard halts
    if profile.losing_streak >= HARD_HALT_STREAK:
        halted = True
        reasons.append(f"halted: losing streak {profile.losing_streak} "
                       f">= {HARD_HALT_STREAK}")
    if profile.max_drawdown_pct >= 20.0:
        halted = True
        reasons.append(f"halted: drawdown {profile.max_drawdown_pct:.1f}% "
                       f">= 20%")
    if regime_risk_mult == 0.0:
        halted = True
        reasons.append("halted: regime risk multiplier = 0 (TREND_BEAR)")

    if halted:
        return GovernorDecision(
            effective_risk_pct=0.0, tier="HALT", reasons=reasons, halted=True,
        )

    # Tier selection
    n = profile.total_closed_trades
    pf = (profile.avg_r_multiple + 1) if profile.avg_r_multiple else 0  # rough proxy
    if n == 0:
        tier, mult = "T0", 0.5
    elif n < MIN_PROVEN_TRADES:
        tier, mult = "T1", 0.75
    elif n < 100 and pf > 0:
        tier, mult = "T2", 1.0
    elif n >= 100 and pf > 1.3 and profile.max_drawdown_pct < 10.0:
        tier, mult = "T3", 1.0
    else:
        tier, mult = "T2", 1.0

    # Recent-losing-streak soft penalty (in addition to hard halt above)
    if profile.losing_streak >= 3:
        mult *= 0.5
        reasons.append(f"soft penalty: losing streak {profile.losing_streak}")

    base = min(risk_cfg.risk_per_trade_pct, MAX_GOVERNED_PCT)
    effective = round(base * mult * regime_risk_mult, 4)
    reasons.append(f"tier={tier} mult={mult} regime_mult={regime_risk_mult}")
    reasons.append(f"config_ceiling={base}% -> effective={effective}%")

    return GovernorDecision(
        effective_risk_pct=effective, tier=tier, reasons=reasons, halted=False,
    )


def adjusted_risk_cfg(base: RiskConfig, decision: GovernorDecision) -> RiskConfig:
    """Returns a NEW RiskConfig with risk_per_trade_pct overridden by governor."""
    new_pct = max(0.1, decision.effective_risk_pct) if not decision.halted else 0.1
    return base.model_copy(update={"risk_per_trade_pct": new_pct})
