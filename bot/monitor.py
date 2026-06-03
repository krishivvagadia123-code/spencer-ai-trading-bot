"""
Automatic stop/target monitor + flatten.

Pure functions over Portfolio + price snapshots. The functions produce
ExitDecision objects describing *what to exit and why*. They never place
broker orders — the engine consumes the decisions and calls execution_sim.

Critically: nothing in this module checks risk caps, control flags, or any
gate. Exits must always be allowed.

Trigger semantics (long-only positions, matching Portfolio.Position):
  STOP   — current_price <= position.stop
  TARGET — current_price >= position.target
  FLATTEN — explicit manual/emergency liquidation, regardless of price

If a current price is missing for an open position, that position is reported
as MissingPrice and is NOT exited — fail-loud, never silent.

The monitor is designed to be run by a scheduler (cron / Windows Task
Scheduler) on a short interval so that exits fire even when the interactive
engine is not running. Each invocation is one snapshot pass.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Set

from bot.portfolio import Portfolio


class ExitReason(str, Enum):
    STOP    = "STOP"
    TARGET  = "TARGET"
    FLATTEN = "FLATTEN"


@dataclass(frozen=True)
class ExitDecision:
    symbol:        str
    qty:           float          # float to mirror Position.qty (fractional crypto)
    reason:        ExitReason
    trigger_price: float
    stop:          float
    target:        float
    entry_price:   float
    ts:            datetime


@dataclass(frozen=True)
class MonitorReport:
    exits:           List[ExitDecision]
    missing_prices:  Set[str]
    checked_symbols: Set[str]

    @property
    def any_exits(self) -> bool:
        return len(self.exits) > 0


def _now() -> datetime:
    return datetime.now()


def check_exits(portfolio: Portfolio, prices: Dict[str, float]) -> MonitorReport:
    """
    Inspect every open long position. Produce STOP/TARGET exit decisions
    for any whose current price has crossed its level.

    Tie-break when both stop and target are crossed in the same snapshot
    (would only happen on a huge gap): STOP wins. Conservative — assume
    the adverse leg printed first.
    """
    exits:   List[ExitDecision] = []
    missing: Set[str]           = set()
    checked: Set[str]           = set()
    ts = _now()

    for sym, pos in portfolio.state.positions.items():
        checked.add(sym)
        if sym not in prices:
            missing.add(sym)
            continue

        price = prices[sym]

        if price <= pos.stop:
            exits.append(ExitDecision(
                symbol=sym, qty=pos.qty, reason=ExitReason.STOP,
                trigger_price=price, stop=pos.stop, target=pos.target,
                entry_price=pos.entry_price, ts=ts,
            ))
        elif price >= pos.target:
            exits.append(ExitDecision(
                symbol=sym, qty=pos.qty, reason=ExitReason.TARGET,
                trigger_price=price, stop=pos.stop, target=pos.target,
                entry_price=pos.entry_price, ts=ts,
            ))

    return MonitorReport(exits=exits, missing_prices=missing, checked_symbols=checked)


def flatten_all(portfolio: Portfolio, prices: Dict[str, float]) -> MonitorReport:
    """
    Produce a FLATTEN exit decision for every open position regardless of
    price level. Used by the manual `flatten` command and by the kill-switch
    emergency liquidation path.

    Missing prices are reported but do NOT prevent flatten decisions for
    other symbols — risk reduction is best-effort.
    """
    exits:   List[ExitDecision] = []
    missing: Set[str]           = set()
    checked: Set[str]           = set()
    ts = _now()

    for sym, pos in portfolio.state.positions.items():
        checked.add(sym)
        if sym not in prices:
            missing.add(sym)
            continue
        exits.append(ExitDecision(
            symbol=sym, qty=pos.qty, reason=ExitReason.FLATTEN,
            trigger_price=prices[sym], stop=pos.stop, target=pos.target,
            entry_price=pos.entry_price, ts=ts,
        ))

    return MonitorReport(exits=exits, missing_prices=missing, checked_symbols=checked)
