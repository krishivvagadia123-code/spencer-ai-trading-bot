"""Read-only healthcheck for Spencer Windows scheduled tasks.

Diagnostics only:
- shells out to ``schtasks /query /fo LIST /v``
- never creates, updates, or deletes scheduled tasks
- never calls a broker SDK or mutates Spencer state
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.holidays import is_nse_holiday


TASK_NAMES = (
    "SpencerIntradayCollect",
    "SpencerDailySnapshot",
    "SpencerDryRun",
)

IST = timezone(timedelta(hours=5, minutes=30), name="IST")
NEVER_RUN_VALUES = {"", "N/A", "Never", "Never Run"}


@dataclass(frozen=True)
class ScheduledTask:
    name: str
    last_run_time: datetime | None
    last_result: int | None
    raw_last_run_time: str
    raw_last_result: str
    present: bool = True


@dataclass(frozen=True)
class TaskHealth:
    task: ScheduledTask
    status: str
    flags: tuple[str, ...]


def _normalize_task_name(value: str) -> str:
    return value.strip().lstrip("\\")


def _parse_task_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                blocks.append(current)
                current = {}
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        current[key.strip()] = value.strip()

    if current:
        blocks.append(current)

    return blocks


def parse_last_result(value: str) -> int | None:
    clean = (value or "").strip()
    if clean in NEVER_RUN_VALUES:
        return None
    try:
        return int(clean, 0)
    except ValueError:
        return None


def parse_last_run_time(value: str) -> datetime | None:
    clean = (value or "").strip()
    if clean in NEVER_RUN_VALUES:
        return None

    formats = (
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %I:%M:%S %p",
    )
    for fmt in formats:
        try:
            return datetime.strptime(clean, fmt).replace(tzinfo=IST)
        except ValueError:
            pass
    return None


def parse_schtasks_list_output(text: str, task_names: tuple[str, ...] = TASK_NAMES) -> dict[str, ScheduledTask]:
    wanted = {name.lower(): name for name in task_names}
    parsed: dict[str, ScheduledTask] = {}

    for block in _parse_task_blocks(text):
        raw_name = block.get("TaskName") or block.get("Task To Run") or ""
        normalized = _normalize_task_name(raw_name)
        canonical = wanted.get(normalized.lower())
        if not canonical:
            continue

        raw_last_run = block.get("Last Run Time", "")
        raw_last_result = block.get("Last Result", "")
        parsed[canonical] = ScheduledTask(
            name=canonical,
            last_run_time=parse_last_run_time(raw_last_run),
            last_result=parse_last_result(raw_last_result),
            raw_last_run_time=raw_last_run,
            raw_last_result=raw_last_result,
        )

    for name in task_names:
        if name not in parsed:
            parsed[name] = ScheduledTask(
                name=name,
                last_run_time=None,
                last_result=None,
                raw_last_run_time="missing",
                raw_last_result="missing",
                present=False,
            )

    return parsed


def most_recent_nse_trading_day(now: datetime | None = None) -> date:
    current = (now or datetime.now(IST)).astimezone(IST).date()
    while current.weekday() >= 5 or is_nse_holiday(current):
        current -= timedelta(days=1)
    return current


def evaluate_tasks(
    tasks: dict[str, ScheduledTask],
    *,
    latest_trading_day: date | None = None,
) -> list[TaskHealth]:
    latest_trading_day = latest_trading_day or most_recent_nse_trading_day()
    health: list[TaskHealth] = []

    for name in TASK_NAMES:
        task = tasks[name]
        flags: list[str] = []

        if not task.present:
            flags.append("task missing from schtasks output")
        if task.last_result is None:
            flags.append("last result unavailable")
        elif task.last_result != 0:
            flags.append(f"last result non-zero ({task.raw_last_result})")

        if name == "SpencerIntradayCollect" and task.last_result == 0:
            if task.last_run_time is None:
                flags.append("last successful intraday collection time unavailable")
            elif task.last_run_time.astimezone(IST).date() < latest_trading_day:
                flags.append(
                    "last successful intraday collection "
                    f"{task.last_run_time.astimezone(IST).date().isoformat()} "
                    f"is older than latest NSE trading day {latest_trading_day.isoformat()}"
                )

        health.append(TaskHealth(task=task, status="FLAG" if flags else "OK", flags=tuple(flags)))

    return health


def query_schtasks() -> str:
    result = subprocess.run(
        ["schtasks", "/query", "/fo", "LIST", "/v"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "schtasks query failed").strip()
        raise RuntimeError(message)
    return result.stdout


def _format_dt(value: datetime | None, raw: str) -> str:
    if value is None:
        return raw or "unavailable"
    return value.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def print_report(health: list[TaskHealth], latest_trading_day: date) -> None:
    print("Spencer scheduler healthcheck")
    print(f"Latest NSE trading day: {latest_trading_day.isoformat()}")
    print("")

    for item in health:
        task = item.task
        print(f"{task.name}: {item.status}")
        print(f"  Last Run Time: {_format_dt(task.last_run_time, task.raw_last_run_time)}")
        print(f"  Last Result: {task.raw_last_result or 'unavailable'}")
        if item.flags:
            for flag in item.flags:
                print(f"  FLAG: {flag}")
        print("")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Spencer Task Scheduler healthcheck.")
    parser.add_argument(
        "--sample",
        help="Parse a saved schtasks /query /fo LIST /v output file instead of shelling out.",
    )
    args = parser.parse_args(argv)

    try:
        text = open(args.sample, encoding="utf-8-sig").read() if args.sample else query_schtasks()
        tasks = parse_schtasks_list_output(text)
        latest = most_recent_nse_trading_day()
        health = evaluate_tasks(tasks, latest_trading_day=latest)
        print_report(health, latest)
        return 1 if any(item.flags for item in health) else 0
    except Exception as exc:
        print(f"Scheduler healthcheck unavailable: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
