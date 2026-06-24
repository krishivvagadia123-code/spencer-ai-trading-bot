"""Live paper-trading execution engine for an APPROVED RELIANCE candidate.

This is the forward (real-time / replay) counterpart of `bot.intraday_backtest`.
It runs a mechanical candidate one bar at a time, on paper only, and journals
every decision. It NEVER places a broker order and never writes to the epoch
`trades` journal — its output lives in dedicated `live_paper_*` tables.

Safety model
------------
- Paper-only is asserted from `workflow/deployment_gate.json` before any run.
- LIVE mode additionally requires the candidate to carry a journaled
  WALK_FORWARD ``PASS`` and to be absent from the kill registry. With no
  candidate passed yet, LIVE correctly refuses — that is the point.
- DRY_RUN mode is a simulation over already-collected real candles (like a
  backtest); it does not require a pass, but is still paper-only and clearly
  labelled.

Backtest parity
---------------
The state machine reuses the backtest's own rule evaluation, sizing, stop and
fill helpers, so a candidate behaves identically live and in backtest. A
decision on bar N executes at bar N+1's open (the backtest's "fill at next
candle open"); a stop is detected on a bar's low and exits at the next open; an
open position is force-squared-off at the session's final bar / 15:25 IST.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

from bot.config import default_config
from bot.execution_sim import simulate_fill
from bot.market_data import IST, Quote, now_ist
from bot.research_candidates import CAPITAL_BASIS_INR, ResearchCandidate, rule_to_dict
from bot.intraday_backtest import (
    Candle,
    PRODUCT,
    _contextualize_candles,
    _entry_fill_side,
    _exit_fill_side,
    _gross_pnl,
    _qty_from_sizing,
    _same_session,
    _stop_hit,
    _stop_price,
    evaluate_rule,
    load_candles,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "kite_bot.db"
GATE_PATH = BASE_DIR / "workflow" / "deployment_gate.json"

# NSE regular session. An open position is squared off at SQUARE_OFF_TIME or at
# the session's final bar, whichever comes first — no overnight intraday risk.
SESSION_OPEN = dtime(9, 15)
SQUARE_OFF_TIME = dtime(15, 25)
SESSION_CLOSE = dtime(15, 30)

MODES = {"DRY_RUN", "LIVE"}


LIVE_SCHEMA = """
CREATE TABLE IF NOT EXISTS live_paper_runs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at         TEXT NOT NULL,
    mode               TEXT NOT NULL,
    candidate_id       TEXT NOT NULL,
    candidate_version  TEXT NOT NULL,
    params_hash        TEXT NOT NULL,
    session_date       TEXT,
    status             TEXT NOT NULL,
    summary_json       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS live_paper_trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    entry_ts     TEXT NOT NULL,
    exit_ts      TEXT NOT NULL,
    qty          REAL NOT NULL,
    entry_price  REAL NOT NULL,
    exit_price   REAL NOT NULL,
    gross_pnl    REAL NOT NULL,
    charges      REAL NOT NULL,
    slippage     REAL NOT NULL,
    net_pnl      REAL NOT NULL,
    exit_reason  TEXT NOT NULL,
    stop_price   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS live_paper_decisions (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id  INTEGER NOT NULL,
    ts      TEXT NOT NULL,
    kind    TEXT NOT NULL,
    detail  TEXT NOT NULL
);
"""


class LivePaperError(Exception):
    """Base error for the live paper engine."""


class GateError(LivePaperError):
    """The deployment gate forbids running (live rails are not safely down)."""


class CandidateNotApprovedError(LivePaperError):
    """The candidate has no journaled WALK_FORWARD PASS, or has been killed."""


def ensure_live_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(LIVE_SCHEMA)


# ── Safety gates ──────────────────────────────────────────────────────────────

def assert_paper_only(gate_path: str | Path = GATE_PATH) -> dict:
    """Refuse unless the deployment gate keeps live money fully disabled.

    The live PAPER engine is allowed to run while deployment is blocked (paper
    is the safe sandbox), but it must NEVER run if someone has flipped on live
    trading or broker execution — that would mean the safety rails are down.
    """
    path = Path(gate_path)
    if not path.exists():
        raise GateError(f"deployment gate not found at {path}")
    gate = json.loads(path.read_text(encoding="utf-8"))
    if not gate.get("paperOnly", False):
        raise GateError("deployment gate is not paperOnly — refusing to run")
    if gate.get("liveTradingAllowed", False):
        raise GateError("liveTradingAllowed is true — refusing (paper engine only)")
    if gate.get("brokerExecutionAllowed", False):
        raise GateError("brokerExecutionAllowed is true — refusing (paper engine only)")
    if gate.get("aiOrderApprovalAllowed", False):
        raise GateError("aiOrderApprovalAllowed is true — refusing")
    return gate


def candidate_pass_record(db_path: str | Path, candidate: ResearchCandidate) -> dict | None:
    """Return the journaled WALK_FORWARD PASS run for this exact candidate
    version, or None. Read-only."""
    path = Path(db_path)
    if not path.exists():
        return None
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT id, created_at, summary_json
                FROM backtest_runs
                WHERE candidate_id = ? AND candidate_version = ?
                  AND stage = 'WALK_FORWARD' AND status = 'PASS'
                ORDER BY id DESC LIMIT 1
                """,
                (candidate.id, candidate.version),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
    return dict(row) if row else None


def candidate_is_killed(db_path: str | Path, candidate: ResearchCandidate) -> bool:
    """True if this exact candidate (id + version) is in the kill registry.

    Stricter than the backtest's anti-overfit check, which deliberately allows
    re-running the exact killed params. For LIVE trading a killed candidate must
    be refused outright — no second chances with real (paper) capital.
    """
    path = Path(db_path)
    if not path.exists():
        return False
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        try:
            row = conn.execute(
                "SELECT 1 FROM backtest_kills WHERE candidate_id = ? AND candidate_version = ? LIMIT 1",
                (candidate.id, candidate.version),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
    return row is not None


def assert_candidate_passed(db_path: str | Path, candidate: ResearchCandidate) -> dict:
    """LIVE-mode gate: the candidate must be unkilled AND carry a WALK_FORWARD
    PASS. Raises CandidateNotApprovedError otherwise (the expected state today —
    nothing has passed)."""
    if candidate_is_killed(db_path, candidate):
        raise CandidateNotApprovedError(
            f"{candidate.id} v{candidate.version} is in the kill registry - refusing live"
        )
    record = candidate_pass_record(db_path, candidate)
    if record is None:
        raise CandidateNotApprovedError(
            f"{candidate.id} v{candidate.version} has no journaled WALK_FORWARD PASS - "
            "a candidate must clear the full testing ladder before live paper trading"
        )
    return record


# ── Execution state machine ───────────────────────────────────────────────────

@dataclass
class _Position:
    qty: float
    entry_ts: datetime
    entry_price: float
    entry_charges: float
    entry_slippage: float
    stop_price: float


class LivePaperTrader:
    """Forward, one-bar-at-a-time paper executor for a single candidate.

    Feed completed bars via :meth:`on_bar`. The class holds no I/O; drivers
    persist the resulting ``trades`` / ``decisions`` after the run.
    """

    def __init__(
        self,
        candidate: ResearchCandidate,
        *,
        mode: str,
        capital: float | None = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"invalid mode: {mode!r}")
        self.candidate = candidate
        self.mode = mode
        self.capital = float(capital if capital is not None else CAPITAL_BASIS_INR)
        self.params = candidate.parameters_dict
        self._entry_rule = rule_to_dict(candidate.entry_rule)
        self._exit_rule = rule_to_dict(candidate.exit_rule)
        self._stop_rule = rule_to_dict(candidate.stop_rule)
        self._sizing_rule = rule_to_dict(candidate.sizing_rule)
        self._no_trade_rules = [rule_to_dict(r) for r in candidate.no_trade_conditions]
        self._history: list[Candle] = []
        self._pending: tuple[str, str | None] | None = None
        self._position: _Position | None = None
        self.trades: list[dict] = []
        self.decisions: list[dict] = []

    # -- public API ----------------------------------------------------------

    def seed_history(self, candles: Sequence[Candle]) -> None:
        """Prime prior-session bars so rolling windows and context fields are
        populated from the first live bar (no fabricated warm-up)."""
        self._history = list(candles)

    @property
    def in_position(self) -> bool:
        return self._position is not None

    def on_bar(self, candle: Candle, *, is_session_final: bool = False) -> None:
        history_prev = self._history
        self._history = history_prev + [candle]

        # Step 1 — execute any pending order at THIS bar's open.
        if self._pending is not None:
            kind, reason = self._pending
            self._pending = None
            if kind == "ENTER" and self._position is None:
                self._open_position(candle, history_prev)
            elif kind == "EXIT" and self._position is not None:
                self._close_position(candle.open, candle.ts, reason or "RULE_EXIT")

        # Step 2 — manage an open position.
        if self._position is not None:
            if is_session_final:
                self._record(candle.ts, "SESSION_END", "forced square-off at session close")
                self._close_position(candle.close, candle.ts, "SESSION_END")
                return
            if _stop_hit(self.candidate.side, candle, self._position.stop_price):
                self._record(
                    candle.ts, "STOP",
                    f"{self.candidate.side.lower()} stop hit at {self._position.stop_price}",
                )
                self._pending = ("EXIT", "STOP")
            elif evaluate_rule(self._exit_rule, self._history, self.params):
                self._record(candle.ts, "EXIT_SIGNAL", "exit rule matched")
                self._pending = ("EXIT", "RULE_EXIT")
            return

        # Step 3 — flat: consider an entry (never on the final bar — no time to
        # square off the same session).
        if is_session_final:
            return
        if any(evaluate_rule(rule, self._history, self.params) for rule in self._no_trade_rules):
            self._record(candle.ts, "NO_TRADE", "no-trade condition matched")
            return
        if evaluate_rule(self._entry_rule, self._history, self.params):
            self._record(candle.ts, "ENTER_SIGNAL", "entry rule matched")
            self._pending = ("ENTER", None)

    def summary(self) -> dict:
        net = round(sum(t["net_pnl"] for t in self.trades), 2)
        gross = round(sum(t["gross_pnl"] for t in self.trades), 2)
        charges = round(sum(t["charges"] for t in self.trades), 2)
        slippage = round(sum(t["slippage"] for t in self.trades), 2)
        return {
            "mode": self.mode,
            "candidate_id": self.candidate.id,
            "candidate_version": self.candidate.version,
            "params_hash": self.candidate.params_hash,
            "trades": len(self.trades),
            "wins": sum(1 for t in self.trades if t["net_pnl"] > 0),
            "gross_pnl": gross,
            "total_charges": charges,
            "total_slippage": slippage,
            "net_pnl": net,
            "open_at_end": self._position is not None,
            "result_hash": self._result_hash(),
        }

    # -- internals -----------------------------------------------------------

    def _open_position(self, candle: Candle, history_prev: Sequence[Candle]) -> None:
        qty = _qty_from_sizing(self._sizing_rule, candle.open, self.capital)
        fill = self._fill(_entry_fill_side(self.candidate.side), qty, candle.open, candle.ts)
        # Stop is decided from the signal-time history (history before this fill
        # bar) and the realised fill price — identical to the backtest.
        stop = _stop_price(
            self._stop_rule,
            fill.fill_price,
            history_prev,
            self.params,
            self.candidate.side,
        )
        self._position = _Position(
            qty=fill.qty,
            entry_ts=candle.ts,
            entry_price=fill.fill_price,
            entry_charges=fill.charges.total,
            entry_slippage=fill.total_slippage,
            stop_price=stop,
        )
        self._record(
            candle.ts, f"FILL_{fill.side}",
            f"qty={fill.qty} price={fill.fill_price} stop={stop}",
        )

    def _close_position(self, price: float, ts: datetime, reason: str) -> None:
        pos = self._position
        assert pos is not None
        fill = self._fill(_exit_fill_side(self.candidate.side), pos.qty, price, ts)
        gross = _gross_pnl(self.candidate.side, pos.entry_price, fill.fill_price, pos.qty)
        charges = round(pos.entry_charges + fill.charges.total, 2)
        slippage = round(pos.entry_slippage + fill.total_slippage, 2)
        net = round(gross - charges, 2)
        self.trades.append({
            "symbol": self.candidate.symbol,
            "entry_ts": pos.entry_ts.isoformat(),
            "exit_ts": ts.isoformat(),
            "qty": pos.qty,
            "entry_price": pos.entry_price,
            "exit_price": fill.fill_price,
            "gross_pnl": gross,
            "charges": charges,
            "slippage": slippage,
            "net_pnl": net,
            "exit_reason": reason,
            "stop_price": pos.stop_price,
        })
        self._record(ts, f"FILL_{fill.side}", f"price={fill.fill_price} net={net} reason={reason}")
        self._position = None

    def _fill(self, side: str, qty: float, price: float, ts: datetime):
        quote = Quote(symbol=self.candidate.symbol, price=price, timestamp=ts,
                      is_stale=False, reject_reason=None)
        fill = simulate_fill(quote, side, qty, default_config().fees, product=PRODUCT)
        if not fill.is_executed:
            raise LivePaperError(fill.reject_reason or "fill rejected")
        return fill

    def _record(self, ts: datetime, kind: str, detail: str) -> None:
        self.decisions.append({"ts": ts.isoformat(), "kind": kind, "detail": detail})

    def _result_hash(self) -> str:
        payload = json.dumps(self.trades, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Persistence (append-only, isolated from the epoch journal) ────────────────

def _persist_run(
    db_path: str | Path,
    candidate: ResearchCandidate,
    mode: str,
    session_date: str | None,
    status: str,
    summary: dict,
    trades: Sequence[dict],
    decisions: Sequence[dict],
) -> int:
    now = datetime.now(IST).isoformat()
    with sqlite3.connect(str(db_path)) as conn:
        ensure_live_tables(conn)
        cur = conn.execute(
            """
            INSERT INTO live_paper_runs
                (created_at, mode, candidate_id, candidate_version, params_hash,
                 session_date, status, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, mode, candidate.id, candidate.version, candidate.params_hash,
             session_date, status, json.dumps(summary, sort_keys=True)),
        )
        run_id = int(cur.lastrowid)
        for t in trades:
            conn.execute(
                """
                INSERT INTO live_paper_trades
                    (run_id, created_at, symbol, entry_ts, exit_ts, qty,
                     entry_price, exit_price, gross_pnl, charges, slippage,
                     net_pnl, exit_reason, stop_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, now, t["symbol"], t["entry_ts"], t["exit_ts"], t["qty"],
                 t["entry_price"], t["exit_price"], t["gross_pnl"], t["charges"],
                 t["slippage"], t["net_pnl"], t["exit_reason"], t["stop_price"]),
            )
        for d in decisions:
            conn.execute(
                "INSERT INTO live_paper_decisions (run_id, ts, kind, detail) VALUES (?, ?, ?, ?)",
                (run_id, d["ts"], d["kind"], d["detail"]),
            )
        conn.commit()
        return run_id


def _record_refusal(db_path: str | Path, candidate: ResearchCandidate, mode: str, reason: str) -> int:
    summary = {"mode": mode, "status": "REFUSED", "reason": reason}
    return _persist_run(db_path, candidate, mode, None, "REFUSED", summary, [], [])


# ── Drivers ──────────────────────────────────────────────────────────────────

def run_dry_run(
    candidate: ResearchCandidate,
    *,
    db_path: str | Path = DB_PATH,
    session_date: date | str,
    gate_path: str | Path = GATE_PATH,
    persist: bool = True,
) -> dict:
    """Replay the candidate over one already-collected session's real candles.

    A simulation (no PASS gate) but still paper-only. Prior sessions are seeded
    for context/rolling windows. Journals mode=DRY_RUN to the live tables.
    """
    assert_paper_only(gate_path)
    sd = date.fromisoformat(str(session_date))
    candles = _contextualize_candles(load_candles(db_path, candidate, end=sd))
    session_candles = [c for c in candles if c.session_date == sd]
    prior = [c for c in candles if c.session_date < sd]

    trader = LivePaperTrader(candidate, mode="DRY_RUN")
    trader.seed_history(prior)
    if not session_candles:
        summary = trader.summary()
        summary["status_reason"] = "NO_CANDLES_FOR_SESSION"
        if persist:
            summary["run_id"] = _persist_run(
                db_path, candidate, "DRY_RUN", str(sd), "DONE", summary, [], [])
        return summary

    last = len(session_candles) - 1
    for idx, candle in enumerate(session_candles):
        trader.on_bar(candle, is_session_final=(idx == last))

    summary = trader.summary()
    summary["session_date"] = str(sd)
    summary["bars"] = len(session_candles)
    if persist:
        summary["run_id"] = _persist_run(
            db_path, candidate, "DRY_RUN", str(sd), "DONE",
            summary, trader.trades, trader.decisions)
    return summary


def run_dry_run_range(
    candidate: ResearchCandidate,
    *,
    db_path: str | Path = DB_PATH,
    start: date | str | None = None,
    end: date | str | None = None,
    gate_path: str | Path = GATE_PATH,
    persist: bool = True,
) -> dict:
    """Replay the candidate forward across EVERY collected session in the range,
    one continuous run with daily square-off — the same loop shape as the
    backtest. Used to cross-check that the live execution path reproduces the
    backtest's verdict over the full dataset.
    """
    assert_paper_only(gate_path)
    candles = _contextualize_candles(load_candles(db_path, candidate, start=start, end=end))
    trader = LivePaperTrader(candidate, mode="DRY_RUN")
    for i, candle in enumerate(candles):
        nxt = candles[i + 1] if i + 1 < len(candles) else None
        is_final = nxt is None or not _same_session(candle, nxt)
        trader.on_bar(candle, is_session_final=is_final)

    # Per-session P&L breakdown from the journaled trades.
    by_session: dict[str, dict] = {}
    for t in trader.trades:
        sd = t["exit_ts"][:10]
        agg = by_session.setdefault(sd, {"session": sd, "trades": 0, "net_pnl": 0.0})
        agg["trades"] += 1
        agg["net_pnl"] = round(agg["net_pnl"] + t["net_pnl"], 2)

    summary = trader.summary()
    summary["sessions"] = sorted(by_session.values(), key=lambda r: r["session"])
    summary["session_count"] = len({c.session_date for c in candles})
    summary["dataset_start"] = candles[0].ts.isoformat() if candles else None
    summary["dataset_end"] = candles[-1].ts.isoformat() if candles else None
    if persist:
        sd_label = f"{start or 'all'}..{end or 'all'}"
        summary["run_id"] = _persist_run(
            db_path, candidate, "DRY_RUN_RANGE", sd_label, "DONE",
            summary, trader.trades, trader.decisions)
    return summary


def _interval_minutes(candidate: ResearchCandidate) -> int:
    return 1 if candidate.interval == "1m" else 15


def run_live(
    candidate: ResearchCandidate,
    *,
    db_path: str | Path = DB_PATH,
    quote_fn: Callable[[], Quote],
    clock: Callable[[], datetime] = now_ist,
    gate_path: str | Path = GATE_PATH,
    sleep_fn: Callable[[float], None] | None = None,
    poll_seconds: float = 15.0,
    max_iterations: int | None = None,
    persist: bool = True,
) -> dict:
    """Market-hours forward runner. Gated by paper-only AND a journaled PASS, so
    it correctly refuses until a candidate graduates the ladder.

    Quotes from ``quote_fn`` are aggregated into the candidate's interval bars;
    a completed bar is fed to the state machine; an open position is squared off
    at 15:25 IST. ``quote_fn``/``clock``/``sleep_fn`` are injectable for tests.
    """
    assert_paper_only(gate_path)
    try:
        assert_candidate_passed(db_path, candidate)
    except CandidateNotApprovedError as exc:
        if persist:
            _record_refusal(db_path, candidate, "LIVE", str(exc))
        raise

    import time as _time
    sleep = sleep_fn or _time.sleep
    interval = timedelta(minutes=_interval_minutes(candidate))

    trader = LivePaperTrader(candidate, mode="LIVE")
    sd = clock().astimezone(IST).date()
    seed = _contextualize_candles(load_candles(db_path, candidate, end=sd))
    trader.seed_history([c for c in seed if c.session_date < sd])

    bucket_start: datetime | None = None
    bar: dict | None = None
    iterations = 0

    def _bucket_floor(ts: datetime) -> datetime:
        minutes = (ts.hour - SESSION_OPEN.hour) * 60 + (ts.minute - SESSION_OPEN.minute)
        floored = (minutes // _interval_minutes(candidate)) * _interval_minutes(candidate)
        base = ts.replace(hour=SESSION_OPEN.hour, minute=SESSION_OPEN.minute,
                          second=0, microsecond=0)
        return base + timedelta(minutes=floored)

    def _finalize(final: bool) -> None:
        nonlocal bar
        if bar is None:
            return
        candle = Candle(
            symbol=candidate.symbol, interval=candidate.interval, ts=bar["ts"],
            open=bar["open"], high=bar["high"], low=bar["low"], close=bar["close"],
            volume=bar["volume"], source="live_quote_aggregate",
        )
        # Contextualize against accumulated history.
        ctx_seq = _contextualize_candles(trader._history + [candle])
        trader.on_bar(ctx_seq[-1], is_session_final=final)
        bar = None

    while True:
        if max_iterations is not None and iterations >= max_iterations:
            break
        iterations += 1
        nowt = clock().astimezone(IST)
        # Square off and stop at the cutoff.
        if nowt.time() >= SQUARE_OFF_TIME:
            _finalize(final=True)
            break
        if nowt.time() < SESSION_OPEN or nowt.time() >= SESSION_CLOSE:
            break
        quote = quote_fn()
        if quote is not None and quote.is_usable:
            floor = _bucket_floor(nowt)
            if bucket_start is not None and floor != bucket_start:
                _finalize(final=False)
            if bar is None:
                bucket_start = floor
                bar = {"ts": floor, "open": quote.price, "high": quote.price,
                       "low": quote.price, "close": quote.price, "volume": 0.0}
            else:
                bar["high"] = max(bar["high"], quote.price)
                bar["low"] = min(bar["low"], quote.price)
                bar["close"] = quote.price
        sleep(poll_seconds)

    summary = trader.summary()
    summary["session_date"] = str(sd)
    if persist:
        summary["run_id"] = _persist_run(
            db_path, candidate, "LIVE", str(sd), "DONE",
            summary, trader.trades, trader.decisions)
    return summary
