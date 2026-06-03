"""Deterministic tests for the gap_up confirmation math (no network)."""

from __future__ import annotations

from datetime import date

from bot import gapup_confirm as G


def _rec(d, fwd, atr_pct=0.02, near=False, max_adv=-0.02):
    return {"symbol": "X", "date": d, "fwd": fwd, "max_adv": max_adv,
            "atr_pct": atr_pct, "near_earnings": near}


def test_realistic_cost_scales_with_atr():
    lo = G.realistic_cost(_rec(date(2024, 1, 1), 0.0, atr_pct=0.01))
    hi = G.realistic_cost(_rec(date(2024, 1, 1), 0.0, atr_pct=0.05))
    assert hi > lo                                   # more volatile gap day -> higher cost
    # brokerage + 2*0.10*0.02 = 0.001 + 0.004 = 0.005
    assert abs(G.realistic_cost(_rec(date(2024, 1, 1), 0.0, atr_pct=0.02)) - 0.005) < 1e-9


def test_summary_net_subtracts_cost():
    recs = [_rec(date(2024, 1, 1), 0.05, atr_pct=0.02),
            _rec(date(2024, 1, 8), -0.01, atr_pct=0.02)]
    s = G._summ(recs, G.realistic_cost)
    # gross avg 0.02; cost 0.005 each -> net avg 0.015
    assert abs(s["avg_gross"] - 0.02) < 1e-9
    assert abs(s["avg_net"] - 0.015) < 1e-9
    assert s["events"] == 2


def test_avg_net_none_on_empty():
    assert G._avg_net([], G.realistic_cost) is None


def test_drawdown_nonnegative():
    recs = [_rec(date(2024, 1, i + 1), r, atr_pct=0.0) for i, r in enumerate([0.1, -0.2, 0.05])]
    s = G._summ(recs, lambda r: 0.0)
    assert s["seq_drawdown"] >= 0.0
