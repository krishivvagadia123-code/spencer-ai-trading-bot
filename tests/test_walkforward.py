"""Unit tests for the walk-forward metrics + verdict thresholds (no network)."""

from __future__ import annotations

from bot import walkforward as wf


def _t(pnl, charges=10.0, entry="2024-01-01", exit="2024-01-03"):
    return {"pnl": pnl, "charges": charges, "entry_date": entry, "exit_date": exit}


def test_metrics_empty():
    m = wf._metrics([])
    assert m["trades"] == 0 and m["win_rate"] == 0.0


def test_metrics_basic_win_loss_and_drawdown():
    trades = [_t(100), _t(-50), _t(200), _t(-30)]
    m = wf._metrics(trades)
    assert m["trades"] == 4
    assert m["win_rate"] == 0.5
    assert m["net_pnl"] == 220.0
    assert m["avg_win"] == 150.0          # (100+200)/2
    assert m["avg_loss"] == -40.0         # (-50-30)/2
    assert m["max_drawdown_pct"] >= 0.0


def test_breakeven_constant_reasonable():
    # Sanity: breakeven win-rate bar sits near the 2R theoretical (~33%).
    assert 0.30 <= wf.BREAKEVEN_WR <= 0.45
