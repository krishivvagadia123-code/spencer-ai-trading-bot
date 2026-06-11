import json
import sqlite3
from pathlib import Path

from bot.config import ONE_STOCK_UNIVERSE, default_config
from bot.portfolio import Portfolio, Position
from paper_engine import CFG, WATCHLIST, cmd_buy
from spencer_quote_server import (
    ACCOUNT_BASIS_INR,
    ACCOUNT_EPOCH,
    _closed_trade_metrics,
    _epoch_context,
    _portfolio_from_epoch_trades,
)


def test_default_config_is_reliance_only_one_position_rs5000():
    cfg = default_config()
    assert cfg.universe == ("RELIANCE",)
    assert cfg.starting_balance == 5_000.0
    assert cfg.risk.max_open_positions == 1
    assert list(WATCHLIST) == ["RELIANCE"]
    assert CFG.risk.max_open_positions == 1
    assert CFG.risk.max_total_notional_inr == 5_000.0
    assert ONE_STOCK_UNIVERSE == ("RELIANCE",)


def test_paper_engine_rejects_second_concurrent_position():
    pf = Portfolio.fresh(starting_balance=5_000.0)
    pf.add_position(
        Position(
            symbol="RELIANCE",
            qty=1,
            entry_price=2_800.0,
            stop=2_700.0,
            target=3_000.0,
            charges_buy=1.0,
            entry_time="2026-06-11T10:00:00",
        ),
        cost=2_801.0,
    )

    cmd_buy("RELIANCE", pf)
    assert len(pf.state.positions) == 1
    assert set(pf.state.positions) == {"RELIANCE"}


def test_paper_engine_rejects_non_reliance_symbol(capsys):
    pf = Portfolio.fresh(starting_balance=5_000.0)
    cmd_buy("TCS", pf)
    out = capsys.readouterr().out
    assert "TCS not in watchlist" in out
    assert pf.state.positions == {}


def test_no_price_simulator_references_in_code():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    simulator_name = "price" + "Simulator"
    bar_generator = "generate" + "NextBar"
    for path in list(root.rglob("*.js")) + list(root.rglob("*.py")):
        if any(part in {".git", ".venv", "__pycache__", "node_modules"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if simulator_name in text or bar_generator in text:
            offenders.append(path.relative_to(root).as_posix())
    assert offenders == []


def _insert_trade(conn, *, symbol, action, price, qty, charges=0.0, pnl=None):
    conn.execute(
        """
        INSERT INTO trades
            (ts, symbol, action, price, qty, value, charges, stop, target, pnl,
             balance_after, entry_reason, exit_reason, signal_snapshot, slippage, equity_after)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-11 10:00:00",
            symbol,
            action,
            price,
            qty,
            price * qty,
            charges,
            None,
            None,
            pnl,
            0.0,
            "test" if action == "BUY" else None,
            "TEST_EXIT" if action == "SELL" else None,
            None,
            0.0,
            None,
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_portfolio_stats_derive_from_current_epoch_journal_rows():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL NOT NULL,
            qty REAL NOT NULL,
            value REAL NOT NULL,
            charges REAL NOT NULL,
            stop REAL,
            target REAL,
            pnl REAL,
            balance_after REAL NOT NULL,
            entry_reason TEXT,
            exit_reason TEXT,
            signal_snapshot TEXT,
            slippage REAL,
            equity_after REAL
        );
        CREATE TABLE bot_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
    )
    _insert_trade(conn, symbol="POWERGRID", action="BUY", price=300.0, qty=100)
    old_cutoff = _insert_trade(conn, symbol="POWERGRID", action="SELL", price=301.0, qty=100, pnl=100.0)
    conn.execute("INSERT INTO bot_state(key, value) VALUES (?, ?)", ("account_epoch", json.dumps(ACCOUNT_EPOCH)))
    conn.execute("INSERT INTO bot_state(key, value) VALUES (?, ?)", ("account_epoch_basis_inr", json.dumps(ACCOUNT_BASIS_INR)))
    conn.execute("INSERT INTO bot_state(key, value) VALUES (?, ?)", ("account_epoch_trade_id_start", json.dumps(old_cutoff)))

    _insert_trade(conn, symbol="RELIANCE", action="BUY", price=2_000.0, qty=1, charges=2.0)
    _insert_trade(conn, symbol="RELIANCE", action="SELL", price=2_100.0, qty=1, charges=2.0, pnl=96.0)

    ctx = _epoch_context(conn)
    state = _portfolio_from_epoch_trades(conn, ctx)
    metrics = _closed_trade_metrics(conn, ctx)

    assert ctx["basis"] == 5_000.0
    assert state["cash"] == 5_096.0
    assert state["realized_pnl"] == 96.0
    assert state["positions"] == {}
    assert metrics["closedTrades"] == 1
    assert metrics["wins"] == 1
