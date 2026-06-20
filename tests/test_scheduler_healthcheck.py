from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts import scheduler_healthcheck as healthcheck


FIXTURE = Path(__file__).parent / "fixtures" / "schtasks_sample.txt"


def test_parse_captured_schtasks_fixture_and_flags_failures():
    tasks = healthcheck.parse_schtasks_list_output(FIXTURE.read_text(encoding="utf-8"))

    assert set(tasks) == set(healthcheck.TASK_NAMES)
    assert tasks["SpencerIntradayCollect"].present is True
    assert tasks["SpencerIntradayCollect"].last_result == 0
    assert tasks["SpencerIntradayCollect"].last_run_time.date() == date(2026, 6, 19)
    assert tasks["SpencerDailySnapshot"].last_result == 0
    assert tasks["SpencerDryRun"].last_result == 1

    report = healthcheck.evaluate_tasks(
        tasks,
        latest_trading_day=date(2026, 6, 19),
    )

    by_name = {item.task.name: item for item in report}
    assert by_name["SpencerIntradayCollect"].status == "OK"
    assert by_name["SpencerDailySnapshot"].status == "OK"
    assert by_name["SpencerDryRun"].status == "FLAG"
    assert by_name["SpencerDryRun"].flags == ("last result non-zero (1)",)


def test_intraday_success_older_than_latest_trading_day_is_flagged():
    tasks = healthcheck.parse_schtasks_list_output(FIXTURE.read_text(encoding="utf-8"))

    report = healthcheck.evaluate_tasks(
        tasks,
        latest_trading_day=date(2026, 6, 22),
    )

    intraday = next(item for item in report if item.task.name == "SpencerIntradayCollect")
    assert intraday.status == "FLAG"
    assert "older than latest NSE trading day 2026-06-22" in intraday.flags[0]


def test_parse_iso_date_with_ampm_from_windows_schtasks():
    parsed = healthcheck.parse_last_run_time("2026-06-20 9:08:17 AM")

    assert parsed is not None
    assert parsed.date() == date(2026, 6, 20)
    assert parsed.hour == 9
    assert parsed.minute == 8
