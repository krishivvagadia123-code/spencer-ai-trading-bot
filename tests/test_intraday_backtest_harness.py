"""Synthetic-candle tests for the candidate-agnostic intraday harness."""

from datetime import date, datetime
import sqlite3
import math

import pytest

from bot.holidays import DEFAULT_REGISTRY
from bot.intraday_backtest import (
    BacktestResult,
    Candle,
    assert_not_forbidden_by_kill_registry,
    evaluate_rule,
    record_kill,
    run_backtest,
    _contextualize_candles,
    _is_monthly_expiry_session,
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


def _candle(day: int, hh: int, mm: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol="RELIANCE",
        interval="15m",
        ts=datetime(2026, 6, day, hh, mm, tzinfo=IST),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        source="synthetic unit test candles",
    )


def _basic_rows():
    return [
        {"ts": _ts(11, 9, 15), "open": 100, "high": 103, "low": 99, "close": 101},
        {"ts": _ts(11, 9, 30), "open": 110, "high": 113, "low": 109, "close": 112},
        {"ts": _ts(11, 9, 45), "open": 120, "high": 123, "low": 119, "close": 122},
    ]


def test_candidate_validation_rejects_future_references_and_bad_shape():
    with pytest.raises(ValueError, match="future"):
        _candidate(entry_rule={"left": {"future": "close"}, "op": ">", "right": {"value": 1}})
    with pytest.raises(ValueError, match="unknown context"):
        _candidate(entry_rule={"left": {"context": "prev_session_typo"}, "op": ">", "right": {"value": 1}})
    _candidate(entry_rule={"left": {"context": "session_minute"}, "op": ">=", "right": {"value": 0}})
    with pytest.raises(ValueError, match="RELIANCE"):
        _candidate(symbol="TCS")
    with pytest.raises(ValueError, match="capital"):
        _candidate(capital=10_000.0)
    with pytest.raises(ValueError, match="max_open_positions"):
        _candidate(max_open_positions=2)
    assert _candidate(side="SHORT").side == "SHORT"
    with pytest.raises(ValueError, match="side"):
        _candidate(side="FLAT")


def test_context_prev_session_range_gap_and_first_session_nan():
    candles = _contextualize_candles([
        _candle(10, 9, 15, 100, 110, 95, 105),
        _candle(10, 15, 15, 108, 115, 100, 110),
        _candle(11, 9, 15, 121, 123, 119, 122),
        _candle(11, 9, 30, 124, 126, 120, 125),
    ])

    assert math.isnan(candles[0].context["prev_session_range_pct"])
    assert math.isnan(candles[0].context["prev_session_close"])
    assert math.isnan(candles[0].context["gap_pct"])
    assert evaluate_rule(
        {"left": {"context": "prev_session_range_pct"}, "op": ">", "right": {"value": 0}},
        [candles[0]],
        {},
    ) is False

    expected_range = (115 - 95) / 110 * 100
    expected_gap = (121 - 110) / 110 * 100
    assert candles[2].context["prev_session_close"] == 110
    assert candles[2].context["prev_session_range_pct"] == pytest.approx(expected_range)
    assert candles[2].context["gap_pct"] == pytest.approx(expected_gap)
    assert candles[3].context["prev_session_range_pct"] == pytest.approx(expected_range)
    assert candles[3].context["gap_pct"] == pytest.approx(expected_gap)

    assert evaluate_rule(
        {"left": {"context": "session_minute", "field": "close"}, "op": "==", "right": {"value": 0}},
        [candles[0]],
        {},
    ) is True


def test_context_session_minute_for_intraday_candles():
    candles = _contextualize_candles([
        _candle(11, 9, 15, 100, 101, 99, 100),
        _candle(11, 15, 15, 110, 111, 109, 110),
    ])

    assert candles[0].context["session_minute"] == 0
    assert candles[1].context["session_minute"] == 360


def test_context_monthly_expiry_and_holiday_shift():
    # 2026-06-25 is the last Thursday of June 2026. If that session is a
    # registered NSE holiday, the expiry session shifts to the prior trading day.
    assert _is_monthly_expiry_session(date(2026, 6, 25)) is True
    assert _is_monthly_expiry_session(date(2026, 6, 24)) is False

    snapshot = DEFAULT_REGISTRY.snapshot()
    try:
        DEFAULT_REGISTRY.add(date(2026, 6, 25))
        assert _is_monthly_expiry_session(date(2026, 6, 25)) is False
        assert _is_monthly_expiry_session(date(2026, 6, 24)) is True
    finally:
        DEFAULT_REGISTRY.restore(snapshot)


def test_context_has_no_lookahead_after_current_candle():
    candles = [
        _candle(10, 9, 15, 100, 110, 95, 105),
        _candle(10, 15, 15, 108, 115, 100, 110),
        _candle(11, 9, 15, 121, 123, 119, 122),
        _candle(11, 9, 30, 124, 140, 118, 125),
        _candle(12, 9, 15, 130, 132, 128, 131),
    ]

    full_context = _contextualize_candles(candles)[2].context
    truncated_context = _contextualize_candles(candles[:3])[2].context

    assert full_context == truncated_context


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


def test_short_candidate_pnl_uses_entry_minus_exit(tmp_path):
    rows = [
        {"ts": _ts(11, 9, 15), "open": 101, "high": 102, "low": 100, "close": 101},
        {"ts": _ts(11, 9, 30), "open": 100, "high": 101, "low": 98, "close": 98},
        {"ts": _ts(11, 9, 45), "open": 95, "high": 96, "low": 94, "close": 95},
    ]
    db_path = _make_db(tmp_path, rows)
    cand = _candidate(
        side="SHORT",
        exit_rule={"left": {"field": "close"}, "op": "<", "right": {"value": 99}},
        stop_rule={"type": "fixed_pct", "pct": 0.5},
    )

    result = run_backtest(cand, db_path=db_path, persist=False)

    trade = result.trades[0]
    assert trade["exit_reason"] == "RULE_EXIT"
    assert trade["entry_price"] < trade["entry_quote_price"]  # short entry is a SELL
    assert trade["exit_price"] > trade["exit_quote_price"]    # cover is a BUY
    assert trade["gross_pnl"] == round(trade["entry_price"] - trade["exit_price"], 2)
    assert trade["net_pnl"] == round(trade["gross_pnl"] - trade["charges"], 2)


def test_short_candidate_stop_triggers_on_upside(tmp_path):
    rows = [
        {"ts": _ts(11, 9, 15), "open": 100, "high": 101, "low": 99, "close": 101},
        {"ts": _ts(11, 9, 30), "open": 100, "high": 101, "low": 99, "close": 100},
        {"ts": _ts(11, 9, 45), "open": 100, "high": 103, "low": 99, "close": 102},
        {"ts": _ts(11, 10, 0), "open": 104, "high": 105, "low": 103, "close": 104},
    ]
    db_path = _make_db(tmp_path, rows)
    cand = _candidate(side="SHORT", stop_rule={"type": "fixed_pct", "pct": 0.02})

    result = run_backtest(cand, db_path=db_path, persist=False)

    trade = result.trades[0]
    assert trade["exit_reason"] == "STOP"
    assert trade["stop_price"] > trade["entry_price"]
    assert trade["gross_pnl"] < 0


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
    assert first.result_hash == "cda5c9a1f212e461b288b358307919d89f288b9a15f610978ff4f0b79bf85308"
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


def test_rolling_operand_is_not_shadowed_by_its_field_key():
    """A rolling spec carries a "field" key; operand resolution must hit the
    rolling branch first, otherwise "close > rolling mean(close)" silently
    becomes "close > close" and no rule referencing a rolling value can ever
    fire (the SPNCR-001 false-kill bug)."""
    from datetime import datetime, timedelta, timezone
    from bot.intraday_backtest import Candle, evaluate_rule

    ist = timezone(timedelta(hours=5, minutes=30))
    base = datetime(2026, 6, 1, 9, 15, tzinfo=ist)
    closes = [100.0, 101.0, 102.0, 103.0, 110.0]
    history = [
        Candle(symbol="RELIANCE", interval="15m", ts=base + timedelta(minutes=15 * i),
               open=c, high=c + 1, low=c - 1, close=c, volume=1000.0, source="test")
        for i, c in enumerate(closes)
    ]
    rule = {
        "left": {"field": "close"},
        "op": ">",
        "right": {"rolling": "mean", "field": "close", "window": 5},
    }
    # mean = 103.2, latest close = 110 -> must be True; the shadowed-field bug
    # evaluated right as the latest close (110 > 110 = False).
    assert evaluate_rule(rule, history, {}) is True
