"""Anti-overfit guarantees for the Phase 3 per-regime trust layer. Offline, deterministic."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bot.regime_learner import (
    classify_index_regimes, compute_regime_trust, _trust_from_expectancy,
    MIN_TRADES_PER_REGIME, TRUST_FLOOR,
)


def _index(closes):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes}, index=idx)


def test_index_regime_labels_uptrend():
    reg = classify_index_regimes(_index(np.linspace(100, 200, 120)))
    assert reg.iloc[-1] == "TREND_UP"


def test_index_regime_labels_downtrend():
    reg = classify_index_regimes(_index(np.linspace(200, 100, 120)))
    assert reg.iloc[-1] == "TREND_DOWN"


def test_trust_never_exceeds_one_and_never_below_floor():
    # Positive expectancy -> full trust, never amplified above 1.0.
    assert _trust_from_expectancy(500.0, -40.0) == 1.0
    # Very negative -> clamped at the floor, never below.
    t = _trust_from_expectancy(-10_000.0, -40.0)
    assert TRUST_FLOOR <= t <= 1.0
    assert t == TRUST_FLOOR


def test_thin_sample_stays_neutral():
    # Fewer than MIN_TRADES_PER_REGIME losing trades must NOT be penalized.
    reg = classify_index_regimes(_index(np.linspace(100, 200, 120)))
    day = reg.index[-1]
    trades = [{"symbol": "X", "entry_date": str(day), "pnl": -100.0}
              for _ in range(MIN_TRADES_PER_REGIME - 1)]
    prof = compute_regime_trust(trades, reg)
    assert prof.regimes["TREND_UP"]["trust"] == 1.0
    assert prof.regimes["TREND_UP"]["sufficient"] is False


def test_sufficient_losing_regime_is_downweighted():
    reg = classify_index_regimes(_index(np.linspace(100, 200, 120)))
    day = reg.index[-1]
    trades = [{"symbol": "X", "entry_date": str(day), "pnl": -100.0}
              for _ in range(MIN_TRADES_PER_REGIME + 5)]
    prof = compute_regime_trust(trades, reg)
    r = prof.regimes["TREND_UP"]
    assert r["sufficient"] is True
    assert r["trust"] < 1.0           # losing regime shrinks size
    assert r["trust"] >= TRUST_FLOOR


def test_determinism():
    reg = classify_index_regimes(_index(np.linspace(100, 200, 120)))
    day = reg.index[-1]
    trades = [{"symbol": "X", "entry_date": str(day), "pnl": float(p)}
              for p in (range(-30, 0))]
    a = compute_regime_trust(trades, reg)
    b = compute_regime_trust(trades, reg)
    assert a.regimes == b.regimes
