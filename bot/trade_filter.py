"""
Anti-overtrading filter — a pre-trade QUALITY gate.

Goal: reject low-quality trades *before* they are taken, so the engine stops
bleeding edge into transaction costs. This is deterministic and explainable —
every rejection carries a human-readable reason. It contains NO predictions and
NO fabricated numbers; it only does arithmetic on the proposed trade.

Six rules (all must pass to accept):
  1. Minimum regime trust   — from regime_trust.json (current index regime).
  2. Minimum risk-reward     — (target-entry)/(entry-stop) >= min_rr.
  3. Minimum expected edge   — net reward AFTER charges, expressed in R, >= min_edge_r.
  4. Maximum trades per day  — portfolio-wide cap on new entries per session.
  5. Cooldown after a loss   — no re-entry in a symbol within N sessions of a loss.
  6. Charges-vs-target cap   — round-trip charges <= max_charge_ratio of target profit.

The filter is advisory on quality; it can only make the engine MORE selective. It
never enables a trade the risk gate blocked, and it never overrides risk limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TradeFilterConfig:
    min_trust:          float = 0.50   # require regime trust >= this
    min_rr:             float = 1.50   # reward:risk floor
    min_edge_r:         float = 1.00   # net-of-charges reward must be >= this many R
    max_trades_per_day: int   = 3      # portfolio-wide new entries per session
    loss_cooldown_days: int   = 3      # sessions to wait after a loss in a symbol
    max_charge_ratio:   float = 0.25   # charges <= 25% of gross target profit


@dataclass
class FilterDecision:
    accepted: bool
    reasons:  List[str] = field(default_factory=list)   # why rejected (empty if accepted)
    checks:   Dict[str, bool] = field(default_factory=dict)
    metrics:  Dict[str, float] = field(default_factory=dict)

    def primary_reason(self) -> str:
        return self.reasons[0] if self.reasons else "accepted"


def evaluate_trade(
    *,
    trust:               float,
    entry:               float,
    stop:                float,
    target:              float,
    qty:                 float,
    charges:             float,
    trades_today:        int,
    sessions_since_loss: Optional[int],   # None if no prior loss in this symbol
    cfg:                 TradeFilterConfig,
) -> FilterDecision:
    reasons: List[str] = []
    checks:  Dict[str, bool] = {}

    risk_value   = (entry - stop) * qty          # 1R in rupees
    reward_gross = (target - entry) * qty        # gross profit at target
    rr           = (target - entry) / (entry - stop) if entry > stop else 0.0
    net_reward   = reward_gross - charges
    edge_r       = (net_reward / risk_value) if risk_value > 0 else 0.0
    charge_ratio = (charges / reward_gross) if reward_gross > 0 else 1.0

    # 1. Minimum regime trust
    ok = trust >= cfg.min_trust
    checks["min_trust"] = ok
    if not ok:
        reasons.append(f"regime trust {trust:.2f} < min {cfg.min_trust:.2f}")

    # 2. Minimum risk-reward
    ok = rr >= cfg.min_rr
    checks["min_rr"] = ok
    if not ok:
        reasons.append(f"R:R {rr:.2f} < min {cfg.min_rr:.2f}")

    # 3. Minimum expected edge after charges (in R)
    ok = edge_r >= cfg.min_edge_r
    checks["min_edge_r"] = ok
    if not ok:
        reasons.append(f"net edge {edge_r:.2f}R < min {cfg.min_edge_r:.2f}R after charges")

    # 4. Maximum trades per day
    ok = trades_today < cfg.max_trades_per_day
    checks["max_trades_per_day"] = ok
    if not ok:
        reasons.append(f"daily trade cap reached ({trades_today}/{cfg.max_trades_per_day})")

    # 5. Cooldown after a loss
    if sessions_since_loss is None:
        checks["loss_cooldown"] = True
    else:
        ok = sessions_since_loss >= cfg.loss_cooldown_days
        checks["loss_cooldown"] = ok
        if not ok:
            reasons.append(
                f"post-loss cooldown ({sessions_since_loss} < {cfg.loss_cooldown_days} sessions)"
            )

    # 6. Charges vs target profit
    ok = charge_ratio <= cfg.max_charge_ratio
    checks["charge_ratio"] = ok
    if not ok:
        reasons.append(
            f"charges are {charge_ratio:.0%} of target profit > max {cfg.max_charge_ratio:.0%}"
        )

    return FilterDecision(
        accepted=len(reasons) == 0,
        reasons=reasons,
        checks=checks,
        metrics={
            "rr": round(rr, 3), "edge_r": round(edge_r, 3),
            "charge_ratio": round(charge_ratio, 3),
            "net_reward": round(net_reward, 2), "risk_value": round(risk_value, 2),
        },
    )
