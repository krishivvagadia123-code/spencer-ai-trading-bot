from datetime import date

import pytest

from bot.holidays import NSE_TRADING_HOLIDAYS_2026, is_nse_holiday


OFFICIAL_NSE_TRADING_HOLIDAYS_2026 = {
    date(2026, 1, 15),
    date(2026, 1, 26),
    date(2026, 2, 15),
    date(2026, 3, 3),
    date(2026, 3, 21),
    date(2026, 3, 26),
    date(2026, 3, 31),
    date(2026, 4, 3),
    date(2026, 4, 14),
    date(2026, 5, 1),
    date(2026, 5, 28),
    date(2026, 6, 26),
    date(2026, 8, 15),
    date(2026, 9, 14),
    date(2026, 10, 2),
    date(2026, 10, 20),
    date(2026, 11, 8),
    date(2026, 11, 10),
    date(2026, 11, 24),
    date(2026, 12, 25),
}


def test_2026_holiday_calendar_matches_official_nse_list():
    assert NSE_TRADING_HOLIDAYS_2026 == OFFICIAL_NSE_TRADING_HOLIDAYS_2026


@pytest.mark.parametrize("holiday", sorted(OFFICIAL_NSE_TRADING_HOLIDAYS_2026))
def test_each_official_2026_nse_holiday_is_registered(holiday):
    assert is_nse_holiday(holiday) is True


def test_adjacent_normal_trading_day_is_not_a_holiday():
    assert is_nse_holiday(date(2026, 4, 15)) is False
