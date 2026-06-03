"""DB tests — Pydantic validation, migrations, backups (only when needed)."""
import sqlite3
from pathlib import Path
import pytest
from pydantic import ValidationError

from bot.db import (
    init_db, log_trade, get_all_trades, save_state, load_state,
    set_db_path,
)
from bot.migrations import backup_db, CURRENT_SCHEMA_VERSION, get_schema_version


@pytest.fixture
def tmp_db(tmp_path):
    db_file = tmp_path / "test_kite.db"
    set_db_path(db_file)
    init_db()
    yield db_file
    set_db_path(Path(__file__).parent.parent / "kite_bot.db")


def test_init_db_creates_all_tables(tmp_db):
    conn = sqlite3.connect(tmp_db)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "trades" in tables
    assert "bot_state" in tables
    assert "signal_log" in tables


def test_init_db_adds_extended_trade_columns(tmp_db):
    conn = sqlite3.connect(tmp_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
    for new_col in ["entry_reason", "exit_reason", "signal_snapshot",
                    "slippage", "equity_after"]:
        assert new_col in cols


def test_log_trade_basic(tmp_db):
    log_trade({
        "ts": "2026-05-25 10:00:00", "symbol": "ADANIENT", "action": "BUY",
        "price": 2500.0, "qty": 10, "value": 25000.0, "charges": 15.0,
        "stop": 2450.0, "target": 2600.0, "balance_after": 24985.0,
    })
    assert len(get_all_trades()) == 1


def test_log_trade_with_audit_fields(tmp_db):
    log_trade({
        "ts": "2026-05-25 10:00:00", "symbol": "ADANIENT", "action": "BUY",
        "price": 2500.0, "qty": 10, "value": 25000.0, "charges": 15.0,
        "balance_after": 24985.0,
        "entry_reason": "ST green + RSI 55 + above VWAP",
        "signal_snapshot": '{"rsi": 55.2, "st": "green"}',
        "slippage": 1.25, "equity_after": 50985.0,
    })
    trades = get_all_trades()
    assert trades[0]["entry_reason"] == "ST green + RSI 55 + above VWAP"
    assert trades[0]["slippage"] == 1.25


def test_log_trade_rejects_negative_price(tmp_db):
    with pytest.raises(ValidationError):
        log_trade({
            "ts": "...", "symbol": "X", "action": "BUY",
            "price": -100, "qty": 1, "value": 100, "charges": 1,
            "balance_after": 0,
        })


def test_log_trade_rejects_zero_qty(tmp_db):
    with pytest.raises(ValidationError):
        log_trade({
            "ts": "...", "symbol": "X", "action": "BUY",
            "price": 100, "qty": 0, "value": 0, "charges": 1,
            "balance_after": 0,
        })


def test_save_load_state_roundtrip(tmp_db):
    save_state("test_key", {"a": 1, "b": [1, 2, 3]})
    assert load_state("test_key") == {"a": 1, "b": [1, 2, 3]}


def test_load_state_missing_returns_default(tmp_db):
    assert load_state("missing_key", default=42) == 42


def test_backup_creates_timestamped_copy(tmp_path):
    src = tmp_path / "test.db"
    src.write_bytes(b"fake-sqlite-data")
    backup_path = backup_db(src)
    assert backup_path.exists()
    assert backup_path.name.startswith("test.db.backup-")
    assert backup_path.read_bytes() == b"fake-sqlite-data"


def test_backup_no_op_when_no_db(tmp_path):
    src = tmp_path / "missing.db"
    result = backup_db(src)
    assert result == src


def test_init_db_idempotent_does_not_create_backup(tmp_path):
    """
    Calling init_db twice on a current-version DB should NOT create a backup
    on the second call.
    """
    db_file = tmp_path / "test.db"
    set_db_path(db_file)

    init_db()  # first init — fresh DB, no backup expected
    backups_after_first = list(tmp_path.glob("*.backup-*"))
    init_db()  # second init — current version, no backup expected
    backups_after_second = list(tmp_path.glob("*.backup-*"))

    assert len(backups_after_second) == len(backups_after_first), (
        f"init_db on current-version DB should not create extra backups. "
        f"Got {len(backups_after_second)} after 2nd init vs {len(backups_after_first)} after 1st."
    )
    set_db_path(Path(__file__).parent.parent / "kite_bot.db")


def test_init_db_idempotent_preserves_data(tmp_db):
    log_trade({
        "ts": "2026-05-25 10:00:00", "symbol": "X", "action": "BUY",
        "price": 100, "qty": 1, "value": 100, "charges": 1,
        "balance_after": 0,
    })
    init_db()
    assert len(get_all_trades()) == 1


def test_schema_version_set_after_init(tmp_db):
    conn = sqlite3.connect(tmp_db)
    assert get_schema_version(conn) == CURRENT_SCHEMA_VERSION


def test_legacy_db_gets_backed_up_and_upgraded(tmp_path):
    """
    A pre-existing DB without schema_version row should be backed up
    on first init and bumped to CURRENT_SCHEMA_VERSION.
    """
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE bot_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE trades (id INTEGER PRIMARY KEY);
    """)
    conn.commit()
    conn.close()

    set_db_path(db_file)
    init_db()

    # Backup created (legacy DB had version 0, code wants 1)
    backups = list(tmp_path.glob("legacy.db.backup-*"))
    assert len(backups) == 1, f"Expected exactly 1 backup, got {len(backups)}"

    # Version is now current
    conn = sqlite3.connect(db_file)
    assert get_schema_version(conn) == CURRENT_SCHEMA_VERSION
    conn.close()

    set_db_path(Path(__file__).parent.parent / "kite_bot.db")
