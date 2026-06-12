from datetime import date
import sqlite3

import pytest

from scripts import daily_price_snapshot as snap


TRADE_DATE = date(2026, 6, 11)


def _quote_row(symbol: str = "RELIANCE", price: float = 2500.5) -> dict:
    return {
        "symbol": symbol,
        "price": price,
        "previousClose": 2499.0,
        "changePct": 0.06,
        "timestamp": "2026-06-11T10:00:00+00:00",
        "fetchedAt": "2026-06-11T12:40:00+00:00",
        "source": "test quote path",
        "marketState": "CLOSED",
    }


def _daily_rows(db_path):
    if not db_path.exists():
        return []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM daily_prices ORDER BY symbol").fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(row) for row in rows]


def test_snapshot_writes_exactly_one_row_per_symbol_date(tmp_path):
    db_path = tmp_path / "snapshot.db"
    log_path = tmp_path / "snapshot.log"

    result = snap.snapshot_prices(
        db_path=db_path,
        trade_date=TRADE_DATE,
        symbols=("RELIANCE",),
        quote_func=lambda symbols: [_quote_row(symbols[0])],
        log_path=log_path,
    )

    rows = _daily_rows(db_path)
    assert result.exit_code == 0
    assert result.inserted == 1
    assert len(rows) == 1
    assert rows[0]["symbol"] == "RELIANCE"
    assert rows[0]["trade_date"] == "2026-06-11"
    assert rows[0]["close"] == pytest.approx(2500.5)


def test_snapshot_rerun_same_day_no_duplicate_and_exit_zero(tmp_path):
    db_path = tmp_path / "snapshot.db"
    log_path = tmp_path / "snapshot.log"
    calls = 0

    def fake_quotes(symbols):
        nonlocal calls
        calls += 1
        return [_quote_row(symbols[0], price=2500.0 + calls)]

    first = snap.snapshot_prices(
        db_path=db_path,
        trade_date=TRADE_DATE,
        symbols=("RELIANCE",),
        quote_func=fake_quotes,
        log_path=log_path,
    )
    second = snap.snapshot_prices(
        db_path=db_path,
        trade_date=TRADE_DATE,
        symbols=("RELIANCE",),
        quote_func=fake_quotes,
        log_path=log_path,
    )

    rows = _daily_rows(db_path)
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "already snapshotted" in second.message
    assert calls == 1
    assert len(rows) == 1
    assert rows[0]["close"] == pytest.approx(2501.0)


def test_api_failure_writes_no_row_and_exits_nonzero(tmp_path):
    db_path = tmp_path / "snapshot.db"
    log_path = tmp_path / "snapshot.log"

    def failing_quotes(symbols):
        raise RuntimeError("quote API down")

    result = snap.snapshot_prices(
        db_path=db_path,
        trade_date=TRADE_DATE,
        symbols=("RELIANCE",),
        quote_func=failing_quotes,
        log_path=log_path,
    )

    assert result.exit_code == 1
    assert _daily_rows(db_path) == []
    assert "quote API down" in log_path.read_text(encoding="utf-8")


def test_no_symbol_outside_configured_universe_is_snapshotted(tmp_path):
    db_path = tmp_path / "snapshot.db"
    log_path = tmp_path / "snapshot.log"
    requested_symbols = []

    def fake_quotes(symbols):
        requested_symbols.extend(symbols)
        return [_quote_row("RELIANCE"), _quote_row("TCS", price=3900.0)]

    result = snap.snapshot_prices(
        db_path=db_path,
        trade_date=TRADE_DATE,
        quote_func=fake_quotes,
        log_path=log_path,
    )

    rows = _daily_rows(db_path)
    assert result.exit_code == 0
    assert requested_symbols == ["RELIANCE"]
    assert [row["symbol"] for row in rows] == ["RELIANCE"]
