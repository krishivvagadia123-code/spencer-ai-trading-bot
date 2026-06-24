"""Tests for the live paper-trading execution engine (bot/live_paper_trader.py).

Covers the safety gates (paper-only, candidate-passed/killed), the forward state
machine (entry at next bar open, stop exit, rule exit, forced session-end
square-off, one position max), journaling isolation from the epoch trades table,
determinism, live context-field support, and the no-broker invariant.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from bot.live_paper_trader import (
    CandidateNotApprovedError,
    GateError,
    LivePaperTrader,
    assert_candidate_passed,
    assert_paper_only,
    run_dry_run,
    run_dry_run_range,
)
from bot.intraday_backtest import run_backtest
from bot.intraday_backtest import (
    Candle,
    _contextualize_candles,
    ensure_backtest_tables,
    record_kill,
)
from bot.research_candidates import candidate_from_dict

IST = timezone(timedelta(hours=5, minutes=30))


# ── builders ──────────────────────────────────────────────────────────────────

def _candidate(*, entry, exit_, stop, cid="TEST-001", version="1",
               no_trade=None, parameters=None, interval="15m", side="LONG"):
    return candidate_from_dict({
        "id": cid,
        "version": version,
        "hypothesis": "synthetic test candidate for the live engine",
        "symbol": "RELIANCE",
        "interval": interval,
        "entry_rule": entry,
        "exit_rule": exit_,
        "stop_rule": stop,
        "sizing_rule": {"type": "max_affordable", "capital_fraction": 1.0},
        "no_trade_conditions": no_trade or [],
        "execution_assumption": {"entry_fill": "next_candle_open", "exit_fill": "next_candle_open"},
        "parameters": parameters or {},
        "tunable_parameters": [],
        "capital": 5000.0,
        "max_open_positions": 1,
        "side": side,
    })


ALWAYS = {"left": {"field": "close"}, "op": ">", "right": {"value": 0}}
NEVER = {"left": {"field": "close"}, "op": "<", "right": {"value": 0}}


def _candle(minute_idx, o, h, l, c, *, day=12):
    ts = datetime(2026, 6, day, 9, 15, tzinfo=IST) + timedelta(minutes=15 * minute_idx)
    return Candle(symbol="RELIANCE", interval="15m", ts=ts,
                  open=float(o), high=float(h), low=float(l), close=float(c),
                  volume=1000.0, source="test")


def _gate(path: Path, **overrides):
    data = {
        "paperOnly": True, "liveTradingAllowed": False,
        "brokerExecutionAllowed": False, "aiOrderApprovalAllowed": False,
    }
    data.update(overrides)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _seed_walk_forward_pass(db_path: Path, candidate):
    with sqlite3.connect(str(db_path)) as conn:
        ensure_backtest_tables(conn)
        conn.execute(
            """
            INSERT INTO backtest_runs
                (created_at, stage, candidate_id, candidate_version, params_hash,
                 result_hash, status, dataset_start, dataset_end, data_rows,
                 summary_json, trades_json, equity_json, candidate_json)
            VALUES (?, 'WALK_FORWARD', ?, ?, ?, 'rh', 'PASS', '', '', 0, '{}', '[]', '[]', '{}')
            """,
            (datetime.now(IST).isoformat(), candidate.id, candidate.version,
             candidate.params_hash),
        )
        conn.commit()


# ── safety gates ──────────────────────────────────────────────────────────────

def test_assert_paper_only_passes_clean_gate(tmp_path):
    assert assert_paper_only(_gate(tmp_path / "gate.json"))["paperOnly"] is True


def test_assert_paper_only_refuses_when_live_enabled(tmp_path):
    with pytest.raises(GateError):
        assert_paper_only(_gate(tmp_path / "gate.json", liveTradingAllowed=True))


def test_assert_paper_only_refuses_when_broker_enabled(tmp_path):
    with pytest.raises(GateError):
        assert_paper_only(_gate(tmp_path / "gate.json", brokerExecutionAllowed=True))


def test_live_refuses_candidate_without_pass(tmp_path):
    db = tmp_path / "k.db"
    cand = _candidate(entry=ALWAYS, exit_=NEVER, stop={"type": "fixed_pct", "pct": 0.01})
    with pytest.raises(CandidateNotApprovedError):
        assert_candidate_passed(db, cand)


def test_live_refuses_killed_candidate(tmp_path):
    db = tmp_path / "k.db"
    cand = _candidate(entry=ALWAYS, exit_=NEVER, stop={"type": "fixed_pct", "pct": 0.01})
    _seed_walk_forward_pass(db, cand)          # even WITH a pass row...
    record_kill(db, cand, "killed in a later cycle")  # ...a kill must veto.
    with pytest.raises(CandidateNotApprovedError):
        assert_candidate_passed(db, cand)


def test_live_allows_passed_candidate(tmp_path):
    db = tmp_path / "k.db"
    cand = _candidate(entry=ALWAYS, exit_=NEVER, stop={"type": "fixed_pct", "pct": 0.01})
    _seed_walk_forward_pass(db, cand)
    rec = assert_candidate_passed(db, cand)
    assert rec is not None


# ── state machine ─────────────────────────────────────────────────────────────

def test_entry_fills_next_open_and_session_end_squareoff():
    cand = _candidate(entry=ALWAYS, exit_=NEVER, stop={"type": "fixed_pct", "pct": 0.5})
    t = LivePaperTrader(cand, mode="DRY_RUN")
    candles = [_candle(0, 100, 101, 99, 100),
               _candle(1, 100, 102, 100, 101),
               _candle(2, 101, 103, 101, 102)]
    t.on_bar(candles[0])                              # entry signal -> pending
    assert not t.in_position
    t.on_bar(candles[1])                              # fill at bar1 open
    assert t.in_position
    t.on_bar(candles[2], is_session_final=True)       # forced square-off
    assert not t.in_position
    assert len(t.trades) == 1
    trade = t.trades[0]
    assert trade["exit_reason"] == "SESSION_END"
    # BUY at bar1 open (100, slipped UP); SELL at bar2 close (102, slipped DOWN).
    assert trade["entry_price"] >= 100
    assert 101 < trade["exit_price"] <= 102


def test_stop_exit_fires_at_next_open():
    cand = _candidate(entry=ALWAYS, exit_=NEVER, stop={"type": "fixed_pct", "pct": 0.02})
    t = LivePaperTrader(cand, mode="DRY_RUN")
    t.on_bar(_candle(0, 100, 100, 100, 100))   # entry signal
    t.on_bar(_candle(1, 100, 101, 99.6, 100))  # fill ~100, stop ~98
    assert t.in_position
    t.on_bar(_candle(2, 100, 100, 97, 99))     # low 97 < stop ~98 -> stop pending
    t.on_bar(_candle(3, 98, 99, 98, 98), is_session_final=True)  # stop fills at bar3 open
    assert len(t.trades) == 1
    assert t.trades[0]["exit_reason"] == "STOP"


def test_rule_exit_fires_at_next_open():
    cand = _candidate(
        entry=ALWAYS,
        exit_={"left": {"field": "close"}, "op": "<", "right": {"value": 98}},
        stop={"type": "fixed_pct", "pct": 0.5},
    )
    t = LivePaperTrader(cand, mode="DRY_RUN")
    t.on_bar(_candle(0, 100, 100, 100, 100))   # entry signal
    t.on_bar(_candle(1, 100, 101, 99, 99))     # fill; close 99 not < 98 -> hold
    t.on_bar(_candle(2, 99, 99, 97, 97))       # close 97 < 98 -> exit pending
    t.on_bar(_candle(3, 97, 98, 97, 98), is_session_final=True)
    assert len(t.trades) == 1
    assert t.trades[0]["exit_reason"] == "RULE_EXIT"


def test_one_position_max():
    cand = _candidate(entry=ALWAYS, exit_=NEVER, stop={"type": "fixed_pct", "pct": 0.5})
    t = LivePaperTrader(cand, mode="DRY_RUN")
    t.on_bar(_candle(0, 100, 100, 100, 100))   # signal
    t.on_bar(_candle(1, 100, 100, 100, 100))   # fill -> in position
    assert t.in_position
    # Entry rule is still true on every later bar, but no second position opens.
    t.on_bar(_candle(2, 100, 100, 100, 100))
    t.on_bar(_candle(3, 100, 100, 100, 100))
    assert sum(1 for d in t.decisions if d["kind"] == "FILL_BUY") == 1


def test_determinism_same_input_same_hash():
    def run():
        cand = _candidate(entry=ALWAYS, exit_=NEVER, stop={"type": "fixed_pct", "pct": 0.5})
        t = LivePaperTrader(cand, mode="DRY_RUN")
        for i, c in enumerate([_candle(0, 100, 101, 99, 100), _candle(1, 100, 102, 100, 101),
                               _candle(2, 101, 103, 101, 102)]):
            t.on_bar(c, is_session_final=(i == 2))
        return t.summary()["result_hash"]
    assert run() == run()


def test_context_field_candidate_evaluates_live():
    # Entry uses a context field (gap_pct); must evaluate without error.
    cand = _candidate(
        entry={"left": {"context": "gap_pct"}, "op": ">=", "right": {"value": -1000}},
        exit_=NEVER,
        stop={"type": "fixed_pct", "pct": 0.5},
    )
    prev = [_candle(i, 100, 101, 99, 100, day=11) for i in range(3)]
    today = [_candle(i, 100, 101, 99, 100, day=12) for i in range(3)]
    ctx = _contextualize_candles(prev + today)
    t = LivePaperTrader(cand, mode="DRY_RUN")
    t.seed_history(ctx[:3])
    session = ctx[3:]
    for i, c in enumerate(session):
        t.on_bar(c, is_session_final=(i == len(session) - 1))
    assert len(t.trades) == 1  # gap_pct >= -1000 always true -> trades once


# ── journaling isolation ──────────────────────────────────────────────────────

def _make_intraday_db(db_path: Path):
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE intraday_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, interval TEXT,
                ts TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT
            )""")
        conn.execute("""
            CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT)""")
        conn.execute("INSERT INTO trades (symbol) VALUES ('PRE-EXISTING')")
        base = datetime(2026, 6, 12, 9, 15, tzinfo=IST)
        for i in range(6):
            ts = (base + timedelta(minutes=15 * i)).isoformat()
            conn.execute(
                "INSERT INTO intraday_prices (symbol, interval, ts, open, high, low, close, volume, source)"
                " VALUES ('RELIANCE','15m',?,100,101,99,100,1000,'test')", (ts,))
        conn.commit()


def test_dry_run_isolated_from_epoch_trades(tmp_path):
    db = tmp_path / "iso.db"
    _make_intraday_db(db)
    cand = _candidate(entry=ALWAYS, exit_=NEVER, stop={"type": "fixed_pct", "pct": 0.5})
    summary = run_dry_run(cand, db_path=db, session_date="2026-06-12",
                          gate_path=_gate(tmp_path / "gate.json"))
    assert summary["trades"] == 1
    with sqlite3.connect(str(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM live_paper_trades").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM live_paper_runs").fetchone()[0] == 1
        # the epoch trades table is untouched: still just the pre-existing row
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 1


# ── backtest parity (the live engine must reproduce the backtest exactly) ─────

def _make_multi_session_db(db_path: Path, sessions=3, bars=5):
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE intraday_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, interval TEXT,
                ts TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT
            )""")
        for day in range(11, 11 + sessions):
            base = datetime(2026, 6, day, 9, 15, tzinfo=IST)
            for i in range(bars):
                ts = (base + timedelta(minutes=15 * i)).isoformat()
                price = 100 + i  # gently rising — a trivial pattern
                conn.execute(
                    "INSERT INTO intraday_prices (symbol, interval, ts, open, high, low, close, volume, source)"
                    " VALUES ('RELIANCE','15m',?,?,?,?,?,1000,'test')",
                    (ts, price, price + 1, price - 1, price))
        conn.commit()


def test_live_engine_matches_backtest_exactly(tmp_path):
    """The live execution path must produce the SAME trades and net P&L as the
    backtest over the same data — otherwise a candidate would behave differently
    live than it tested. This is the trust guarantee."""
    db = tmp_path / "parity.db"
    _make_multi_session_db(db, sessions=3, bars=5)
    cand = _candidate(entry=ALWAYS, exit_=NEVER, stop={"type": "fixed_pct", "pct": 0.5})

    bt = run_backtest(cand, db_path=db, stage="IN_SAMPLE", persist=False)
    live = run_dry_run_range(cand, db_path=db, gate_path=_gate(tmp_path / "gate.json"),
                             persist=False)

    assert live["trades"] == bt.summary["trades"]
    assert live["net_pnl"] == bt.summary["net_pnl"]
    assert live["trades"] == 3  # one squared-off trade per session


def test_live_engine_matches_backtest_exactly_for_short(tmp_path):
    """SHORT candidates must preserve the same backtest/live parity guarantee:
    entry SELL, cover BUY, upside stop, and identical P&L over the same bars."""
    db = tmp_path / "short_parity.db"
    _make_multi_session_db(db, sessions=3, bars=5)
    cand = _candidate(
        entry=ALWAYS,
        exit_=NEVER,
        stop={"type": "fixed_pct", "pct": 0.5},
        side="SHORT",
    )

    bt = run_backtest(cand, db_path=db, stage="IN_SAMPLE", persist=False)
    live = run_dry_run_range(cand, db_path=db, gate_path=_gate(tmp_path / "gate.json"),
                             persist=False)

    assert live["trades"] == bt.summary["trades"]
    assert live["net_pnl"] == bt.summary["net_pnl"]
    assert live["trades"] == 3


# ── no-broker invariant ───────────────────────────────────────────────────────

def test_no_broker_or_exchange_sdk_imported():
    src = (Path(__file__).resolve().parents[1] / "bot" / "live_paper_trader.py").read_text(encoding="utf-8")
    lowered = src.lower()
    for needle in ("kiteconnect", "import kite", "place_order", "transaction_type",
                   "ccxt", "binance"):
        assert needle not in lowered, f"forbidden broker reference: {needle}"
