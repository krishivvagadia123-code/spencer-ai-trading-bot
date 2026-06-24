from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from scripts import daily_history
from scripts import research_scan_daily
from scripts import research_scan_multiday


def _bars(start: date, count: int):
    rows = []
    price = 100.0
    day = start
    while len(rows) < count:
        if day.weekday() < 5:
            close = price + 1.0
            idx = len(rows)
            wide = idx in {20, 30}
            rows.append(
                daily_history.DailyBar(
                    trade_date=day,
                    open=price,
                    high=close + (8.0 if wide else 0.5),
                    low=price - (8.0 if wide else 0.5),
                    close=close,
                    volume=1_000_000 + len(rows),
                    adj_close=close,
                )
            )
            price = close
        day += timedelta(days=1)
    return rows


def test_daily_history_appends_ohlcv_idempotently_and_extends_existing_schema(tmp_path):
    db_path = tmp_path / "history.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE daily_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL NOT NULL,
                quote_timestamp TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                source TEXT NOT NULL,
                market_state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(symbol, trade_date)
            )
            """
        )

    fetched = _bars(date(2026, 6, 8), 3)

    def fake_fetch(**kwargs):
        return fetched

    first = daily_history.append_daily_history(db_path=db_path, fetch_func=fake_fetch)
    second = daily_history.append_daily_history(db_path=db_path, fetch_func=fake_fetch)

    assert first.inserted == 3
    assert second.inserted == 0
    assert second.skipped_existing == 3
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row[1] for row in conn.execute("PRAGMA table_info(daily_prices)")}
        rows = conn.execute("SELECT * FROM daily_prices ORDER BY trade_date").fetchall()
    assert {"open", "high", "low", "adj_close", "volume"}.issubset(columns)
    assert len(rows) == 3
    assert rows[0]["open"] == 100.0
    assert rows[0]["source"] == daily_history.SOURCE


def test_daily_research_scan_writes_json_and_brain_note_from_real_rows(tmp_path):
    db_path = tmp_path / "daily_scan.db"
    out_path = tmp_path / "workflow" / "research_findings_daily.json"
    brain_note = tmp_path / "brain" / "Latest Daily Research Scan.md"
    fetched = _bars(date(2026, 1, 5), 35)
    history = daily_history.append_daily_history(db_path=db_path, fetch_func=lambda **kwargs: fetched)

    report = research_scan_daily.run_scan(db_path=db_path, out_path=out_path, brain_note=brain_note)

    assert report["sessions_analyzed"] == history.inserted
    assert out_path.exists()
    assert brain_note.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    names = {finding["name"] for finding in payload["findings"]}
    assert {
        "close_to_close_drift",
        "one_day_momentum_up",
        "gap_up_intraday",
        "volatility_breakout_followthrough",
    }.issubset(names)
    assert "Hypotheses only" in brain_note.read_text(encoding="utf-8")


def _multiday_reversion_bars(start: date, cycles: int = 12):
    rows = []
    price = 120.0
    day = start

    def next_trade_day(current: date) -> date:
        current += timedelta(days=1)
        while current.weekday() >= 5:
            current += timedelta(days=1)
        return current

    while len(rows) < 25:
        if day.weekday() < 5:
            rows.append(
                daily_history.DailyBar(
                    trade_date=day,
                    open=price,
                    high=price + 1,
                    low=price - 1,
                    close=price,
                    volume=1_000_000,
                    adj_close=price,
                )
            )
        day = next_trade_day(day)
    for cycle in range(cycles):
        # Three-session selloff followed by a multi-day rebound. This is
        # synthetic test data only; the scanner itself reads real daily_prices.
        for step in (0.99, 0.98, 0.97):
            price = round(price * step, 2)
            rows.append(
                daily_history.DailyBar(
                    trade_date=day,
                    open=price + 1,
                    high=price + 2,
                    low=price - 1,
                    close=price,
                    volume=1_100_000 + cycle,
                    adj_close=price,
                )
            )
            day = next_trade_day(day)
        for step in (1.04, 1.03, 1.02):
            price = round(price * step, 2)
            rows.append(
                daily_history.DailyBar(
                    trade_date=day,
                    open=price - 1,
                    high=price + 2,
                    low=price - 2,
                    close=price,
                    volume=1_200_000 + cycle,
                    adj_close=price,
                )
            )
            day = next_trade_day(day)
    return rows


def test_multiday_scan_finds_cost_aware_reversion_hypotheses_and_writes_outputs(tmp_path):
    db_path = tmp_path / "multiday.db"
    out_path = tmp_path / "workflow" / "research_findings_multiday.json"
    brain_note = tmp_path / "brain" / "Latest Multi-Day Research Scan.md"
    daily_history.append_daily_history(
        db_path=db_path,
        fetch_func=lambda **kwargs: _multiday_reversion_bars(date(2026, 1, 5)),
    )
    before = db_path.read_bytes()

    report = research_scan_multiday.run_scan(db_path=db_path, out_path=out_path, brain_note=brain_note)

    assert db_path.read_bytes() == before
    assert out_path.exists()
    assert brain_note.exists()
    assert report["cost_model"].startswith("bot.charges.round_trip_cost")
    drop_revert = [
        finding for finding in report["findings"]
        if finding["name"] == "drop_revert_3d"
    ][0]
    assert drop_revert["side"] == "LONG"
    assert drop_revert["mean"] > 0
    assert drop_revert["avg_delivery_cost"] > 0
    assert drop_revert["clears_cost_bar"] is True


def test_multiday_scan_reports_data_insufficient_when_no_samples(tmp_path):
    report = research_scan_multiday.scan_multiday(_bars(date(2026, 6, 8), 5))

    assert report["sessions_analyzed"] == 5
    assert all(
        finding.get("status") == "DATA_INSUFFICIENT"
        for finding in report["findings"]
        if finding["horizon_sessions"] == 10
    )
