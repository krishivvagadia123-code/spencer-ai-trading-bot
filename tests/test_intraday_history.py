import sqlite3

from scripts import intraday_history as hist


def _candle(ts="2026-06-11T09:15:00+00:00", close=2500.0):
    return {
        "time": ts,
        "open": close - 1,
        "high": close + 2,
        "low": close - 3,
        "close": close,
        "volume": 1000,
    }


def _chart(candles):
    return {"candles": candles, "source": "test Yahoo chart path"}


def _intraday_rows(db_path):
    if not db_path.exists():
        return []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM intraday_prices ORDER BY symbol, interval, ts"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(row) for row in rows]


def test_backfill_inserts_candles_and_rerun_inserts_zero(tmp_path):
    db_path = tmp_path / "intraday.db"
    log_path = tmp_path / "intraday.log"

    def fake_chart(symbol, interval, range_name):
        return _chart([
            _candle("2026-06-11T09:15:00+00:00", 2500.0),
            _candle("2026-06-11T09:30:00+00:00", 2501.0),
        ])

    first = hist.backfill_intraday_history(
        db_path=db_path,
        chart_func=fake_chart,
        log_path=log_path,
    )
    second = hist.backfill_intraday_history(
        db_path=db_path,
        chart_func=fake_chart,
        log_path=log_path,
    )

    assert first.exit_code == 0
    assert first.inserted == 4
    assert second.exit_code == 0
    assert second.inserted == 0
    assert len(_intraday_rows(db_path)) == 4


def test_null_ohlc_candles_are_skipped(tmp_path):
    db_path = tmp_path / "intraday.db"
    log_path = tmp_path / "intraday.log"

    def fake_chart(symbol, interval, range_name):
        return _chart([
            {**_candle("2026-06-11T09:15:00+00:00"), "open": None},
            _candle("2026-06-11T09:16:00+00:00", 2502.0),
        ])

    result = hist.backfill_intraday_history(
        db_path=db_path,
        intervals=("1m",),
        chart_func=fake_chart,
        log_path=log_path,
    )

    rows = _intraday_rows(db_path)
    assert result.exit_code == 0
    assert result.inserted == 1
    assert result.skipped_null_ohlc == 1
    assert len(rows) == 1
    assert rows[0]["close"] == 2502.0


def test_api_failure_writes_no_rows_and_exits_nonzero(tmp_path):
    db_path = tmp_path / "intraday.db"
    log_path = tmp_path / "intraday.log"

    def failing_chart(symbol, interval, range_name):
        raise RuntimeError("chart API down")

    result = hist.backfill_intraday_history(
        db_path=db_path,
        chart_func=failing_chart,
        log_path=log_path,
    )

    assert result.exit_code == 1
    assert _intraday_rows(db_path) == []
    assert "chart API down" in log_path.read_text(encoding="utf-8")


def test_candle_timestamps_are_stored_as_ist_session_times(tmp_path):
    db_path = tmp_path / "intraday.db"
    log_path = tmp_path / "intraday.log"

    def fake_chart(symbol, interval, range_name):
        return _chart([_candle("2026-06-11T20:00:00+00:00", 2500.0)])

    result = hist.backfill_intraday_history(
        db_path=db_path,
        intervals=("1m",),
        chart_func=fake_chart,
        log_path=log_path,
    )

    rows = _intraday_rows(db_path)
    report = hist.coverage_report(db_path=db_path, intervals=("1m",))
    assert result.exit_code == 0
    assert rows[0]["ts"] == "2026-06-12T01:30:00+05:30"
    assert "2026-06-12T01:30:00+05:30" in report


def test_non_universe_symbols_are_never_collected(tmp_path):
    db_path = tmp_path / "intraday.db"
    log_path = tmp_path / "intraday.log"
    called_symbols = []

    def fake_chart(symbol, interval, range_name):
        called_symbols.append(symbol)
        return _chart([_candle()])

    result = hist.backfill_intraday_history(
        db_path=db_path,
        symbols=("RELIANCE", "TCS"),
        intervals=("1m",),
        chart_func=fake_chart,
        log_path=log_path,
    )

    rows = _intraday_rows(db_path)
    assert result.exit_code == 0
    assert called_symbols == ["RELIANCE"]
    assert [row["symbol"] for row in rows] == ["RELIANCE"]


def test_in_progress_and_pseudo_candles_are_never_stored(tmp_path):
    """Yahoo appends a live pseudo-candle stamped at the current second and,
    during market hours, the latest boundary bar is still forming. Neither is
    a final candle; storing them would freeze partial values forever."""
    from datetime import datetime, timedelta
    from bot.market_data import IST

    db_path = tmp_path / "intraday.db"
    log_path = tmp_path / "intraday.log"

    now = datetime.now(IST)
    pseudo_ts = now.replace(microsecond=0).isoformat()  # current-second stamp
    forming = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    final = forming - timedelta(minutes=15)

    def fake_chart(symbol, interval, range_name):
        return _chart([
            _candle(final.isoformat(), 2500.0),     # completed -> stored
            _candle(forming.isoformat(), 2501.0),   # window not elapsed -> skipped
            _candle(pseudo_ts, 2502.0),             # off-grid pseudo bar -> skipped
        ])

    result = hist.backfill_intraday_history(
        db_path=db_path,
        intervals=("15m",),
        chart_func=fake_chart,
        log_path=log_path,
    )

    rows = _intraday_rows(db_path)
    assert result.exit_code == 0
    assert result.skipped_incomplete >= 2
    assert [r["ts"] for r in rows] == [final.isoformat()]
