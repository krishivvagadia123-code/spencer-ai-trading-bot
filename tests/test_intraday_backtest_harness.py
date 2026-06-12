"""Synthetic-candle tests for the candidate-agnostic intraday harness."""

from datetime import datetime
import sqlite3

import pytest

from bot.intraday_backtest import (
    BacktestResult,
    assert_not_forbidden_by_kill_registry,
    record_kill,
    run_backtest,
)
from bot.market_data import IST
from bot.research_candidates import candidate_from_dict
from scripts.run_testing_ladder import run_ladder


def _candidate(**updates):
    data = {
        "id": "candidate_test",
        "version": "v1",
        "hypothesis": "Synthetic harness test candidate, not a real technique.",
        "symbol": "RELIANCE",
        "interval": "15m",
        "entry_rule": {"left": {"field": "close"}, "op": ">", "right": {"value": 100}},
        "exit_rule": {"left": {"field": "close"}, "op": "<", "right": {"value": 0}},
        "stop_rule": {"type": "fixed_pct", "pct": 0.05},
        "sizing_rule": {"type": "fixed_qty", "qty": 1},
        "no_trade_conditions": [],
        "execution_assumption": {
            "entry_fill": "next_candle_open",
            "exit_fill": "next_candle_open",
        },
        "parameters": {"threshold": 100},
        "capital": 5000.0,
        "max_open_positions": 1,
    }
    data.update(updates)
    return candidate_from_dict(data)


def _make_db(tmp_path, rows):
    db_path = tmp_path / "synthetic_intraday.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE intraday_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                ts TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                source TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(symbol, interval, ts)
            )
            """
        )
        for row in rows:
            conn.execute(
                """
                INSERT INTO intraday_prices
                    (symbol, interval, ts, open, high, low, close,
                     volume, source, fetched_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "RELIANCE",
                    "15m",
                    row["ts"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row.get("volume", 1000),
                    "synthetic unit test candles",
                    row["ts"],
                    row["ts"],
                ),
            )
        conn.commit()
    return db_path


def _ts(day: int, hh: int, mm: int) -> str:
    return datetime(2026, 6, day, hh, mm, tzinfo=IST).isoformat()


def _basic_rows():
    return [
        {"ts": _ts(11, 9, 15), "open": 100, "high": 103, "low": 99, "close": 101},
        {"ts": _ts(11, 9, 30), "open": 110, "high": 113, "low": 109, "close": 112},
        {"ts": _ts(11, 9, 45), "open": 120, "high": 123, "low": 119, "close": 122},
    ]


def test_candidate_validation_rejects_future_references_and_bad_shape():
    with pytest.raises(ValueError, match="future"):
        _candidate(entry_rule={"left": {"future": "close"}, "op": ">", "right": {"value": 1}})
    with pytest.raises(ValueError, match="RELIANCE"):
        _candidate(symbol="TCS")
    with pytest.raises(ValueError, match="capital"):
        _candidate(capital=10_000.0)
    with pytest.raises(ValueError, match="max_open_positions"):
        _candidate(max_open_positions=2)


def test_engine_fills_at_next_open_with_charges_and_slippage(tmp_path):
    db_path = _make_db(tmp_path, _basic_rows())
    result = run_backtest(_candidate(), db_path=db_path, persist=True)

    assert result.status == "PASS"
    trade = result.trades[0]
    assert trade["entry_ts"] == _ts(11, 9, 30)
    assert trade["entry_quote_price"] == 110
    assert trade["entry_price"] > trade["entry_quote_price"]
    assert trade["charges"] > 0
    assert trade["slippage"] > 0
    assert trade["net_pnl"] < trade["gross_pnl"]

    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="no such table: trades"):
            conn.execute("SELECT COUNT(*) FROM trades").fetchone()


def test_session_end_square_off_closes_without_overnight_position(tmp_path):
    rows = [
        {"ts": _ts(11, 15, 0), "open": 100, "high": 103, "low": 99, "close": 101},
        {"ts": _ts(11, 15, 15), "open": 110, "high": 113, "low": 109, "close": 112},
        {"ts": _ts(12, 9, 15), "open": 130, "high": 131, "low": 129, "close": 130},
    ]
    db_path = _make_db(tmp_path, rows)
    result = run_backtest(_candidate(), db_path=db_path, persist=False)

    trade = result.trades[0]
    assert trade["exit_reason"] == "SESSION_END"
    assert trade["exit_ts"] == _ts(11, 15, 15)


def test_reproducibility_and_cost_bar_math_are_stable(tmp_path):
    db_path = _make_db(tmp_path, _basic_rows())
    cand = _candidate()
    first = run_backtest(cand, db_path=db_path, persist=False)
    second = run_backtest(cand, db_path=db_path, persist=False)

    assert first.result_hash == second.result_hash
    assert first.summary == second.summary
    assert first.summary["cost_bar_pass"] is True
    assert first.summary["net_edge_per_trade_pct_of_notional"] >= first.summary["cost_bar_required_pct"]


def _fake_result(candidate, stage, status, *, net=0.0, cost_bar=False):
    return BacktestResult(
        stage=stage,
        status=status,
        candidate_id=candidate.id,
        candidate_version=candidate.version,
        params_hash=candidate.params_hash,
        result_hash=f"{stage}:{status}:{net}:{cost_bar}",
        dataset={"rows": 3},
        trades=[],
        equity_curve=[],
        summary={"net_pnl": net, "cost_bar_pass": cost_bar},
    )


def test_ladder_gates_oos_until_in_sample_passes(tmp_path):
    cand = _candidate()
    calls = []

    def fail_in_sample(candidate, stage, date_range, db_path):
        calls.append(stage)
        return _fake_result(candidate, stage, "FAIL", net=-1, cost_bar=False)

    out = run_ladder(
        cand,
        {
            "in_sample": {"start": "2026-06-11", "end": "2026-06-11"},
            "out_of_sample": {"start": "2026-06-12", "end": "2026-06-12"},
        },
        db_path=tmp_path / "ladder.db",
        stage_runner=fail_in_sample,
    )

    assert out["verdict"] == "FAIL"
    assert calls == ["IN_SAMPLE"]


def test_ladder_runs_oos_and_walk_forward_after_prior_passes(tmp_path):
    cand = _candidate()
    calls = []

    def pass_all(candidate, stage, date_range, db_path):
        calls.append(stage)
        return _fake_result(candidate, stage, "PASS", net=10, cost_bar=True)

    out = run_ladder(
        cand,
        {
            "in_sample": {"start": "2026-06-10", "end": "2026-06-10"},
            "out_of_sample": {"start": "2026-06-11", "end": "2026-06-11"},
            "walk_forward": [{"start": "2026-06-12", "end": "2026-06-12"}],
        },
        db_path=tmp_path / "ladder.db",
        stage_runner=pass_all,
    )

    assert out["verdict"] == "PASS"
    assert calls == ["IN_SAMPLE", "OUT_OF_SAMPLE", "WALK_FORWARD"]


def test_killed_candidate_refuses_tweaked_params_without_new_hypothesis(tmp_path):
    db_path = tmp_path / "ladder.db"
    killed = _candidate(parameters={"threshold": 100})
    record_kill(db_path, killed, "IN_SAMPLE failed")

    tweaked = _candidate(parameters={"threshold": 101})
    with pytest.raises(ValueError, match="killed"):
        assert_not_forbidden_by_kill_registry(db_path, tweaked)

    new_candidate = _candidate(
        version="v2",
        hypothesis="New mechanical hypothesis after prior kill.",
        parameters={"threshold": 101},
    )
    assert_not_forbidden_by_kill_registry(db_path, new_candidate)
