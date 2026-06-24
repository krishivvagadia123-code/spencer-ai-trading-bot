from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from scripts import daily_history
from scripts import research_scan_daily


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
