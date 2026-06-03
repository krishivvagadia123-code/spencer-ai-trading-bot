"""
NSE exchange holiday registry.

For paper testing, weekend-only is acceptable — the registry starts empty.
Real holidays should be loaded annually from NSE's official communication:
    https://www.nseindia.com/resources/exchange-communication-holidays

Designed for both static (year-load) and dynamic (test/runtime) population.
The default module-level registry is mutable; tests should snapshot+restore
via the `holiday_registry_fixture` (see tests/conftest.py).
"""

from datetime import date
from typing import Iterable, Set


class HolidayRegistry:
    """A mutable set of dates flagged as exchange holidays."""

    def __init__(self, initial: Iterable[date] = ()):
        self._dates: Set[date] = set(initial)

    def add(self, d: date) -> None:
        self._dates.add(d)

    def add_many(self, dates: Iterable[date]) -> None:
        self._dates.update(dates)

    def remove(self, d: date) -> None:
        self._dates.discard(d)

    def clear(self) -> None:
        self._dates.clear()

    def is_holiday(self, d: date) -> bool:
        return d in self._dates

    def all(self) -> frozenset:
        return frozenset(self._dates)

    def snapshot(self) -> Set[date]:
        return set(self._dates)

    def restore(self, snapshot: Set[date]) -> None:
        self._dates = set(snapshot)


# ── Default module-level registry ────────────────────────────────────────────
# Starts empty for paper testing. Populate from NSE official list when going live.
DEFAULT_REGISTRY = HolidayRegistry()


def is_nse_holiday(d: date, registry: HolidayRegistry = None) -> bool:
    """Returns True if d is a registered NSE holiday."""
    return (registry or DEFAULT_REGISTRY).is_holiday(d)


# ── Example structure for future use (commented out — verify before activating)
# NSE_HOLIDAYS_2026: Set[date] = {
#     date(2026, 1, 26),  # Republic Day
#     date(2026, 3, 5),   # Holi
#     # ... etc — verify against official NSE communication
# }
# DEFAULT_REGISTRY.add_many(NSE_HOLIDAYS_2026)
