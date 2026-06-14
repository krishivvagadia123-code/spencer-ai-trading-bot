"""
NSE exchange holiday registry.

The default registry includes the official 2026 NSE Capital Market trading
holidays. Future years should be loaded from NSE's official communications.

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


# Official NSE Capital Market (CM) sources, verified 2026-06-14:
# - Annual list (NSE/CMTR/71775):
#   https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf
# - January 15 amendment (NSE/CMTR/72260):
#   https://nsearchives.nseindia.com/content/circulars/CMTR72260.pdf
# - Current holiday API:
#   https://www.nseindia.com/api/holiday-master?type=trading
NSE_TRADING_HOLIDAYS_2026 = frozenset({
    date(2026, 1, 15),   # Municipal Corporation Election - Maharashtra
    date(2026, 1, 26),   # Republic Day
    date(2026, 2, 15),   # Mahashivratri (Sunday)
    date(2026, 3, 3),    # Holi
    date(2026, 3, 21),   # Id-Ul-Fitr (Saturday)
    date(2026, 3, 26),   # Shri Ram Navami
    date(2026, 3, 31),   # Shri Mahavir Jayanti
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 28),   # Bakri Id
    date(2026, 6, 26),   # Muharram
    date(2026, 8, 15),   # Independence Day (Saturday)
    date(2026, 9, 14),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 8),   # Diwali Laxmi Pujan (Sunday; Muhurat trading)
    date(2026, 11, 10),  # Diwali-Balipratipada
    date(2026, 11, 24),  # Prakash Gurpurb Sri Guru Nanak Dev
    date(2026, 12, 25),  # Christmas
})


DEFAULT_REGISTRY = HolidayRegistry(NSE_TRADING_HOLIDAYS_2026)


def is_nse_holiday(d: date, registry: HolidayRegistry = None) -> bool:
    """Returns True if d is a registered NSE holiday."""
    return (registry or DEFAULT_REGISTRY).is_holiday(d)
