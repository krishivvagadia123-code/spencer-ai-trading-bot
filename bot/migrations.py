"""
Database migrations with mandatory backup BEFORE schema changes.
Never overwrites or resets user data silently.

Versioning rules:
- CURRENT_SCHEMA_VERSION is THE single source of truth for what the code expects.
- get_schema_version() returns 0 only when version row doesn't exist (fresh DB).
- migrate() only backs up if (current < CURRENT_SCHEMA_VERSION). No backup spam.
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from bot.logger_config import get_logger

log = get_logger("kite-bot.migrations")

# ── THE source of truth for schema version ────────────────────────────────────
CURRENT_SCHEMA_VERSION = 2


def backup_db(db_path: Path) -> Path:
    """
    Copy db_path → db_path.backup-YYYYMMDD-HHMMSS.
    No-op if db_path doesn't exist.
    """
    if not db_path.exists():
        log.info(f"No existing DB at {db_path}, nothing to back up.")
        return db_path

    ts          = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.parent / f"{db_path.name}.backup-{ts}"
    shutil.copy2(db_path, backup_path)
    log.info(f"Backed up {db_path} -> {backup_path}")
    return backup_path


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Read schema_version from bot_state. Returns 0 if missing."""
    try:
        cur = conn.execute(
            "SELECT value FROM bot_state WHERE key = 'schema_version'"
        )
        row = cur.fetchone()
        if row is None:
            return 0
        v = row[0]
        # Stored as JSON string by save_state — strip quotes if present
        if isinstance(v, str):
            v = v.strip('"')
        return int(v)
    except sqlite3.OperationalError:
        # bot_state table doesn't exist yet
        return 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Persist the current schema version. Creates bot_state table if missing
    so legacy/corrupt DBs without bot_state can still be tagged."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS bot_state ("
        "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('schema_version', ?)",
        (str(version),)
    )


# ── Migration registry ───────────────────────────────────────────────────────
# Each entry: (target_version, description, fn_or_sql).
# v1 was the initial schema; columns are added by init_db() idempotently,
# so MIGRATIONS is currently empty. Future column drops/renames go here.
def _v2_trades_qty_to_real(conn: sqlite3.Connection) -> None:
    """
    Phase I.1 — change trades.qty from INTEGER to REAL so fractional crypto
    quantities (e.g. 0.0025 BTC) persist correctly. SQLite cannot ALTER COLUMN
    TYPE; we rebuild the table preserving rows.
    """
    # Skip if `trades` table doesn't exist yet (corrupt/empty legacy DB)
    has_trades = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='trades'"
    ).fetchone() is not None
    if not has_trades:
        return
    cols = {row[1]: row[2] for row in
            conn.execute("PRAGMA table_info(trades)").fetchall()}
    if cols.get("qty", "").upper() == "REAL":
        return   # already migrated
    # Legacy/empty `trades` table without our expected columns — leave alone;
    # init_db's CREATE TABLE IF NOT EXISTS will create the canonical schema
    # only if the table is empty AND lacks our columns. Operator can drop it
    # explicitly if they want to start fresh.
    expected = {"ts", "symbol", "action", "price", "qty", "value", "charges",
                "balance_after"}
    if not expected.issubset(cols):
        log.warning("trades table exists but lacks expected columns; "
                    "skipping qty REAL migration. Drop the table manually "
                    "if you want the new schema.")
        return
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades__new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT    NOT NULL,
            symbol          TEXT    NOT NULL,
            action          TEXT    NOT NULL,
            price           REAL    NOT NULL,
            qty             REAL    NOT NULL,
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
        INSERT INTO trades__new
            (id, ts, symbol, action, price, qty, value, charges, stop, target,
             pnl, balance_after, entry_reason, exit_reason, signal_snapshot,
             slippage, equity_after)
        SELECT id, ts, symbol, action, price, qty, value, charges, stop, target,
               pnl, balance_after, entry_reason, exit_reason, signal_snapshot,
               slippage, equity_after
        FROM trades;
        DROP TABLE trades;
        ALTER TABLE trades__new RENAME TO trades;
    """)


MIGRATIONS: list = [
    (2, "trades.qty INTEGER -> REAL (fractional crypto support)",
        _v2_trades_qty_to_real),
]


def migrate(db_path: Path) -> dict:
    """
    Apply pending migrations. Backup ONLY if a migration is actually needed.
    Returns {from_version, to_version, backup_path}.
    """
    if not db_path.exists():
        log.info("Fresh DB — no migrations needed.")
        return {"from_version": 0, "to_version": CURRENT_SCHEMA_VERSION,
                "backup_path": None}

    conn = sqlite3.connect(db_path)
    try:
        current = get_schema_version(conn)
    finally:
        conn.close()

    if current == CURRENT_SCHEMA_VERSION:
        log.debug(f"DB already at version {current}, no migrations needed.")
        return {"from_version": current, "to_version": current,
                "backup_path": None}

    if current > CURRENT_SCHEMA_VERSION:
        log.warning(f"DB version {current} > code version {CURRENT_SCHEMA_VERSION}. "
                    f"Refusing to downgrade.")
        return {"from_version": current, "to_version": current,
                "backup_path": None, "error": "downgrade refused"}

    # Backup only before actually applying migrations
    backup_path = backup_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        for v, desc, sql_or_fn in MIGRATIONS:
            if v <= current:
                continue
            log.info(f"Applying migration v{v}: {desc}")
            if callable(sql_or_fn):
                sql_or_fn(conn)
            else:
                conn.executescript(sql_or_fn)
            set_schema_version(conn, v)
            conn.commit()

        # No registered migrations yet but version bumped (legacy DBs)
        if current < CURRENT_SCHEMA_VERSION:
            set_schema_version(conn, CURRENT_SCHEMA_VERSION)
            conn.commit()
    finally:
        conn.close()

    return {"from_version": current, "to_version": CURRENT_SCHEMA_VERSION,
            "backup_path": backup_path}
