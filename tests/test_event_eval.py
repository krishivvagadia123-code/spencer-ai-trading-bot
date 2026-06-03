"""Deterministic tests for the event-study window + metrics (no network)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from bot import event_eval as EE


def _price(n=40, start=100.0, step=1.0):
    idx = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    close = np.array([start + i * step for i in range(n)], float)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.full(n, 1000.0)}, index=idx)


def test_forward_record_basic_and_horizon():
    px = _price(n=40, start=100.0, step=1.0)   # +1/day
    rec = EE.forward_record(px, date(2024, 1, 10), strictly_after=False)
    assert rec is not None
    # entry at 2024-01-10 (index 9, close 109); +HORIZON days -> close 109+H
    assert abs(rec["fwd"] - (HORIZON_ret := (109 + EE.HORIZON) / 109 - 1)) < 1e-9


def test_forward_record_strictly_after_shifts_entry():
    px = _price()
    a = EE.forward_record(px, date(2024, 1, 10), strictly_after=False)
    b = EE.forward_record(px, date(2024, 1, 10), strictly_after=True)
    assert b["date"] > a["date"]               # strictly-after enters one session later


def test_forward_record_none_at_series_end():
    px = _price(n=40)
    assert EE.forward_record(px, date(2024, 2, 20), strictly_after=False) is None


def test_metrics_and_costs():
    recs = [{"date": date(2024, 1, 1), "fwd": 0.05, "max_adv": -0.02},
            {"date": date(2024, 1, 2), "fwd": -0.01, "max_adv": -0.03}]
    m = EE._metrics(recs)
    assert m["events"] == 2 and m["win_rate"] == 0.5
    assert abs(m["avg_fwd"] - 0.02) < 1e-9
    assert abs(m["cost_adj"] - (0.02 - EE.COST)) < 1e-9


def test_gap_events_detects_threshold_jump():
    px = _price(n=10)
    px.loc[px.index[5], "open"] = px["close"].iloc[4] * 1.05   # +5% gap up
    up, down = EE.gap_events(px)
    assert px.index[5] in up and px.index[5] not in down


def test_walkforward_insufficient_sample():
    recs = [{"date": date(2024, 1, i + 1), "fwd": 0.01, "max_adv": -0.01} for i in range(5)]
    wf = EE._split_and_walkforward(recs)
    assert wf["walk_forward"] == "insufficient"
