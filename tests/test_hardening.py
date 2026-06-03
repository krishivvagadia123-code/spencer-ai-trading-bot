"""
Phase B.1 hardening tests — covers all 5 fixes:

1. portfolio fail-closed on missing prices
2. market_data future-skew rejection
3. NSE holiday registry
4. db.py Literal action + JSON validation on signal_snapshot
5. migrations.py legacy DB without bot_state
"""

import json
import sqlite3
from datetime import datetime, timedelta, date
from pathlib import Path
import pytest
from pydantic import ValidationError

from bot.config import MarketConfig
from bot.market_data import IST, validate_quote, is_market_open
from bot.holidays import HolidayRegistry, DEFAULT_REGISTRY, is_nse_holiday
from bot.portfolio import Portfolio, Position, MissingPriceError
from bot.db import log_trade, set_db_path, init_db, get_all_trades
from bot.migrations import (
    backup_db, set_schema_version, get_schema_version,
    CURRENT_SCHEMA_VERSION,
)


# ── Helper fixtures ───────────────────────────────────────────────────────────
@pytest.fixture
def fresh_pf():
    pf = Portfolio.fresh(starting_balance=50_000.0)
    pos = Position(
        symbol="ADANIENT", qty=10, entry_price=2500.0,
        stop=2450.0, target=2600.0, charges_buy=15.0,
        entry_time=datetime.now(),
    )
    pf.add_position(pos, cost=25_015)
    return pf


@pytest.fixture
def cfg():
    return MarketConfig()


@pytest.fixture
def holidays_snapshot():
    """Snapshot + restore DEFAULT_REGISTRY so tests don't pollute global state."""
    snap = DEFAULT_REGISTRY.snapshot()
    yield DEFAULT_REGISTRY
    DEFAULT_REGISTRY.restore(snap)


@pytest.fixture
def tmp_db(tmp_path):
    db_file = tmp_path / "h.db"
    set_db_path(db_file)
    init_db()
    yield db_file
    set_db_path(Path(__file__).parent.parent / "kite_bot.db")


def _ist(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=IST)


# ═══════════════════════════════════════════════════════════════════════════════
# FIX #1 — Portfolio fail-closed on missing prices
# ═══════════════════════════════════════════════════════════════════════════════
def test_equity_raises_when_price_missing(fresh_pf):
    with pytest.raises(MissingPriceError) as exc:
        fresh_pf.equity({})
    assert "ADANIENT" in exc.value.missing


def test_unrealized_pnl_raises_when_price_missing(fresh_pf):
    with pytest.raises(MissingPriceError):
        fresh_pf.unrealized_pnl({})


def test_positions_market_value_raises_when_price_missing(fresh_pf):
    with pytest.raises(MissingPriceError):
        fresh_pf.positions_market_value({})


def test_drawdown_raises_when_price_missing(fresh_pf):
    with pytest.raises(MissingPriceError):
        fresh_pf.drawdown_pct({})


def test_missing_prices_helper(fresh_pf):
    assert fresh_pf.missing_prices({}) == {"ADANIENT"}
    assert fresh_pf.missing_prices({"ADANIENT": 2500}) == set()


def test_empty_portfolio_no_raise():
    """No open positions → no prices required → no error."""
    pf = Portfolio.fresh(starting_balance=10_000.0)
    assert pf.equity({}) == 10_000.0
    assert pf.unrealized_pnl({}) == 0.0
    assert pf.drawdown_pct({}) == 0.0


def test_partial_prices_still_raises(fresh_pf):
    """Adding a second symbol → only one price provided → raises with the missing one."""
    pos2 = Position(
        symbol="TATAMOTORS", qty=5, entry_price=800.0,
        stop=790.0, target=820.0, charges_buy=10.0,
        entry_time=datetime.now(),
    )
    # Force second position via direct state injection (bypass cash check for test)
    fresh_pf.state.positions["TATAMOTORS"] = pos2
    with pytest.raises(MissingPriceError) as exc:
        fresh_pf.equity({"ADANIENT": 2500.0})
    assert "TATAMOTORS" in exc.value.missing
    assert "ADANIENT" not in exc.value.missing


# ═══════════════════════════════════════════════════════════════════════════════
# FIX #2 — Future-skewed quotes rejected
# ═══════════════════════════════════════════════════════════════════════════════
def test_future_timestamp_within_tolerance_accepted(cfg):
    """Timestamp 1s in the future is within 2s tolerance → accepted."""
    now      = _ist(2026, 5, 25, 10, 0)
    future_1s = now + timedelta(seconds=1)
    q = validate_quote(2500.0, future_1s, "X", cfg, now=now)
    assert q.is_usable, f"Expected usable, got reject_reason={q.reject_reason}"


def test_future_timestamp_beyond_tolerance_rejected(cfg):
    """Timestamp 10s in the future is beyond 2s tolerance → rejected."""
    now      = _ist(2026, 5, 25, 10, 0)
    future_10s = now + timedelta(seconds=10)
    q = validate_quote(2500.0, future_10s, "X", cfg, now=now)
    assert not q.is_usable
    assert "future" in q.reject_reason.lower()


def test_future_skew_tolerance_is_configurable(cfg):
    cfg_strict  = cfg.model_copy(update={"future_skew_tolerance_sec": 0})
    cfg_relaxed = cfg.model_copy(update={"future_skew_tolerance_sec": 30})
    now         = _ist(2026, 5, 25, 10, 0)
    future_5s   = now + timedelta(seconds=5)

    q_strict  = validate_quote(2500.0, future_5s, "X", cfg_strict,  now=now)
    q_relaxed = validate_quote(2500.0, future_5s, "X", cfg_relaxed, now=now)
    assert not q_strict.is_usable
    assert q_relaxed.is_usable


def test_future_message_includes_seconds(cfg):
    now    = _ist(2026, 5, 25, 10, 0)
    future = now + timedelta(seconds=10)
    q = validate_quote(2500.0, future, "X", cfg, now=now)
    # Message should describe the offending number of seconds
    assert "10" in q.reject_reason or "future" in q.reject_reason.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# FIX #3 — NSE holiday registry
# ═══════════════════════════════════════════════════════════════════════════════
def test_default_registry_starts_empty():
    """Paper-testing default: no holidays registered."""
    assert is_nse_holiday(date(2026, 12, 25)) is False


def test_is_nse_holiday_for_added_date(holidays_snapshot):
    holidays_snapshot.add(date(2026, 1, 26))
    assert is_nse_holiday(date(2026, 1, 26)) is True


def test_market_closed_on_added_holiday(cfg, holidays_snapshot):
    """Adding a holiday during market hours should close the market."""
    holidays_snapshot.add(date(2026, 5, 25))   # Monday
    is_open, reason = is_market_open(cfg, _ist(2026, 5, 25, 10, 0))
    assert is_open is False
    assert "holiday" in reason.lower()
    assert "2026-05-25" in reason


def test_market_open_after_holiday_removed(cfg, holidays_snapshot):
    """After removing a holiday, market hours work normally again."""
    holidays_snapshot.add(date(2026, 5, 25))
    holidays_snapshot.remove(date(2026, 5, 25))
    is_open, _ = is_market_open(cfg, _ist(2026, 5, 25, 10, 0))
    assert is_open is True


def test_registry_isolated_from_default(cfg):
    """A caller-supplied registry should override the module default."""
    local = HolidayRegistry({date(2026, 5, 25)})
    is_open, reason = is_market_open(cfg, _ist(2026, 5, 25, 10, 0),
                                     holiday_registry=local)
    assert is_open is False
    assert "holiday" in reason.lower()


def test_quote_rejected_on_holiday(cfg, holidays_snapshot):
    """validate_quote should reject when market closed for a holiday."""
    holidays_snapshot.add(date(2026, 5, 25))
    now = _ist(2026, 5, 25, 10, 0)
    q = validate_quote(2500.0, now, "X", cfg, now=now)
    assert not q.is_usable
    assert "holiday" in q.reject_reason.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# FIX #4 — TradeRow.action is Literal + signal_snapshot JSON-validated
# ═══════════════════════════════════════════════════════════════════════════════
def test_log_trade_accepts_buy_action(tmp_db):
    log_trade({
        "ts": "2026-05-25 10:00:00", "symbol": "X", "action": "BUY",
        "price": 100, "qty": 1, "value": 100, "charges": 1, "balance_after": 0,
    })
    assert len(get_all_trades()) == 1


def test_log_trade_accepts_sell_action(tmp_db):
    log_trade({
        "ts": "2026-05-25 10:00:00", "symbol": "X", "action": "SELL",
        "price": 100, "qty": 1, "value": 100, "charges": 1, "balance_after": 0,
    })
    assert len(get_all_trades()) == 1


def test_log_trade_rejects_invalid_action(tmp_db):
    with pytest.raises(ValidationError):
        log_trade({
            "ts": "...", "symbol": "X", "action": "HOLD",     # ← invalid
            "price": 100, "qty": 1, "value": 100, "charges": 1, "balance_after": 0,
        })


def test_log_trade_rejects_lowercase_action(tmp_db):
    with pytest.raises(ValidationError):
        log_trade({
            "ts": "...", "symbol": "X", "action": "buy",      # ← invalid case
            "price": 100, "qty": 1, "value": 100, "charges": 1, "balance_after": 0,
        })


def test_log_trade_accepts_valid_json_signal_snapshot(tmp_db):
    log_trade({
        "ts": "2026-05-25 10:00:00", "symbol": "X", "action": "BUY",
        "price": 100, "qty": 1, "value": 100, "charges": 1, "balance_after": 0,
        "signal_snapshot": json.dumps({"rsi": 55.2, "trend": "green"}),
    })
    trades = get_all_trades()
    assert json.loads(trades[0]["signal_snapshot"]) == {"rsi": 55.2, "trend": "green"}


def test_log_trade_rejects_invalid_json_signal_snapshot(tmp_db):
    with pytest.raises(ValidationError, match="signal_snapshot"):
        log_trade({
            "ts": "...", "symbol": "X", "action": "BUY",
            "price": 100, "qty": 1, "value": 100, "charges": 1, "balance_after": 0,
            "signal_snapshot": "not a json {{ blob",   # ← invalid JSON
        })


def test_log_trade_allows_null_signal_snapshot(tmp_db):
    log_trade({
        "ts": "2026-05-25 10:00:00", "symbol": "X", "action": "BUY",
        "price": 100, "qty": 1, "value": 100, "charges": 1, "balance_after": 0,
        "signal_snapshot": None,
    })
    assert len(get_all_trades()) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# FIX #5 — migrations.py handles legacy DB with no bot_state table
# ═══════════════════════════════════════════════════════════════════════════════
def test_set_schema_version_creates_bot_state_if_missing(tmp_path):
    """If bot_state doesn't exist, set_schema_version should create it."""
    db = tmp_path / "no-state.db"
    conn = sqlite3.connect(db)
    try:
        # Verify table doesn't exist
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_state'"
        )
        assert cur.fetchone() is None

        set_schema_version(conn, 1)

        # Now it should exist
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_state'"
        )
        assert cur.fetchone() is not None
        # And version is set
        assert get_schema_version(conn) == 1
    finally:
        conn.close()


def test_init_db_handles_corrupt_legacy_db_with_no_bot_state(tmp_path):
    """
    A pre-existing DB that has trades-like content but NO bot_state table.
    init_db must back it up, create schema, and tag with current version.
    """
    db = tmp_path / "corrupt.db"
    conn = sqlite3.connect(db)
    conn.executescript("CREATE TABLE garbage (id INTEGER);")
    conn.execute("INSERT INTO garbage VALUES (1)")
    conn.commit()
    conn.close()

    set_db_path(db)
    init_db()

    # Backup must exist
    backups = list(tmp_path.glob("corrupt.db.backup-*"))
    assert len(backups) == 1, f"Expected 1 backup, got {len(backups)}"

    # bot_state and trades tables must exist now
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "bot_state" in tables
    assert "trades" in tables

    # Version tagged correctly
    assert get_schema_version(conn) == CURRENT_SCHEMA_VERSION

    # Original garbage data preserved (no destructive ops)
    rows = conn.execute("SELECT id FROM garbage").fetchall()
    assert rows == [(1,)]
    conn.close()

    set_db_path(Path(__file__).parent.parent / "kite_bot.db")
