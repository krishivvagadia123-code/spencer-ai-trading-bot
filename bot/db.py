"""
SQLite persistence with Pydantic-validated rows.
init_db() applies migrations (backup only if needed) then ensures schema.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator

from bot.logger_config import get_logger
from bot.migrations import migrate, set_schema_version, CURRENT_SCHEMA_VERSION

log = get_logger("kite-bot.db")
_DB_PATH = Path(__file__).parent.parent / "kite_bot.db"


def set_db_path(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)


def get_db_path() -> Path:
    return _DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Pydantic row model ────────────────────────────────────────────────────────
class TradeRow(BaseModel):
    ts:              str
    symbol:          str
    action:          Literal["BUY", "SELL"]
    price:           float = Field(gt=0)
    # qty is float to allow fractional crypto (e.g. 0.0025 BTC). Equity
    # paths still pass whole numbers — Pydantic accepts int as float.
    qty:             float = Field(gt=0)
    value:           float = Field(ge=0)
    charges:         float = Field(ge=0)
    stop:            Optional[float] = None
    target:          Optional[float] = None
    pnl:             Optional[float] = None
    balance_after:   float = Field(ge=0)
    entry_reason:    Optional[str]   = None
    exit_reason:     Optional[str]   = None
    signal_snapshot: Optional[str]   = None
    slippage:        Optional[float] = None
    equity_after:    Optional[float] = None

    @field_validator("signal_snapshot")
    @classmethod
    def signal_snapshot_must_be_valid_json(cls, v):
        """When present, signal_snapshot must parse as JSON."""
        if v is None:
            return v
        try:
            json.loads(v)
        except (ValueError, TypeError) as e:
            raise ValueError(f"signal_snapshot is not valid JSON: {e}") from e
        return v


# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA = """
    CREATE TABLE IF NOT EXISTS trades (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        ts              TEXT    NOT NULL,
        symbol          TEXT    NOT NULL,
        action          TEXT    NOT NULL,
        price           REAL    NOT NULL,
        qty             REAL    NOT NULL,   -- REAL for fractional crypto (Phase I.1)
        value           REAL    NOT NULL,
        charges         REAL    NOT NULL,
        stop            REAL,
        target          REAL,
        pnl             REAL,
        balance_after   REAL    NOT NULL,
        entry_reason    TEXT,
        exit_reason     TEXT,
        signal_snapshot TEXT,
        slippage        REAL,
        equity_after    REAL
    );
    CREATE TABLE IF NOT EXISTS bot_state (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS signal_log (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        TEXT NOT NULL,
        scan_no   INTEGER NOT NULL,
        symbol    TEXT NOT NULL,
        price     REAL,
        rsi       REAL,
        st_trend  TEXT,
        signal    TEXT NOT NULL,
        reason    TEXT
    );
    CREATE TABLE IF NOT EXISTS research_snapshots (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol              TEXT NOT NULL,
        asof                TEXT NOT NULL,      -- ISO date (YYYY-MM-DD)
        source_data         TEXT NOT NULL,      -- JSON blob from provider
        fundamentals_score  REAL NOT NULL,
        sentiment_score     REAL NOT NULL,
        liquidity_score     REAL NOT NULL,
        computed_at         TEXT NOT NULL,
        UNIQUE(symbol, asof)
    );
    CREATE TABLE IF NOT EXISTS signal_candidates (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        ts                    TEXT NOT NULL,
        symbol                TEXT NOT NULL,
        signal                TEXT NOT NULL,    -- BUY_CANDIDATE/SELL_CANDIDATE/HOLD/REJECTED
        total_score           REAL NOT NULL,
        technical_score       REAL NOT NULL,
        sentiment_score       REAL NOT NULL,
        fundamentals_score    REAL NOT NULL,
        liquidity_score       REAL NOT NULL,
        risk_score            REAL NOT NULL,
        indicators            TEXT,             -- JSON
        research_snapshot_id  INTEGER,
        entry_blocked         INTEGER NOT NULL, -- 0/1
        block_reasons         TEXT,             -- JSON list
        sizing_preview        TEXT,             -- JSON
        rejection_reason      TEXT
    );
"""


def init_db() -> dict:
    """
    Initialize DB. Idempotent — safe to call on every startup.
    Backup happens automatically only when a real schema migration is needed.
    """
    migration_result = migrate(_DB_PATH)

    with get_conn() as conn:
        conn.executescript(SCHEMA)
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
        for col, decl in [
            ("entry_reason",    "TEXT"),
            ("exit_reason",     "TEXT"),
            ("signal_snapshot", "TEXT"),
            ("slippage",        "REAL"),
            ("equity_after",    "REAL"),
        ]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {decl}")
                log.info(f"Added column trades.{col}")
        set_schema_version(conn, CURRENT_SCHEMA_VERSION)
        conn.commit()

    log.info(f"DB ready at {_DB_PATH}")
    return migration_result


def log_trade(trade: dict) -> None:
    row = TradeRow(**trade)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO trades
                (ts, symbol, action, price, qty, value, charges,
                 stop, target, pnl, balance_after,
                 entry_reason, exit_reason, signal_snapshot, slippage, equity_after)
            VALUES
                (:ts, :symbol, :action, :price, :qty, :value, :charges,
                 :stop, :target, :pnl, :balance_after,
                 :entry_reason, :exit_reason, :signal_snapshot, :slippage, :equity_after)
        """, row.model_dump())


def get_all_trades() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM trades ORDER BY ts").fetchall()
    return [dict(r) for r in rows]


def get_pnl_summary() -> dict:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 END) AS wins,
                SUM(CASE WHEN pnl < 0 THEN 1 END) AS losses,
                ROUND(SUM(COALESCE(pnl, 0)), 2)   AS total_pnl
            FROM trades WHERE action = 'SELL'
        """).fetchone()
    return dict(row) if row else {}


def save_state(key: str, value) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)",
            (key, json.dumps(value, default=str))
        )


def load_state(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM bot_state WHERE key = ?", (key,)
        ).fetchone()
    return json.loads(row["value"]) if row else default


def log_signal(scan_no: int, symbol: str, price: float,
               rsi: float, st_trend: str, signal: str, reason: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO signal_log (ts, scan_no, symbol, price, rsi, st_trend, signal, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), scan_no, symbol, price, rsi, st_trend, signal, reason)
        )


def get_today_signals() -> list:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM signal_log WHERE ts LIKE ? ORDER BY ts DESC",
            (f"{today}%",)
        ).fetchall()
    return [dict(r) for r in rows]
