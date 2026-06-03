"""Deterministic tests for predictive features + IC (no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bot import features as F
from bot.feature_eval import spearman_ic, quintile_spread


def _df(closes, vols=None):
    n = len(closes)
    c = np.asarray(closes, float)
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": (vols if vols is not None else np.full(n, 1000.0))})


def test_relative_strength_sign():
    close = pd.Series(np.linspace(100, 130, 60))     # +30%
    bench = pd.Series(np.linspace(100, 110, 60))     # +10%
    rs = F.relative_strength(close, bench, 20)
    assert rs.iloc[-1] > 0                            # outperforming the benchmark


def test_breakout_quality_positive_on_new_high():
    closes = list(np.full(30, 100.0)) + [110.0]      # flat then breakout
    bq = F.breakout_quality(_df(closes))
    assert bq.iloc[-1] > 0


def test_volume_expansion_zscore():
    vols = list(np.full(30, 1000.0)) + [5000.0]      # spike
    df = _df(list(np.linspace(100, 101, 31)), vols=vols)
    vq = F.volume_expansion_quality(df)
    assert vq.iloc[-1] > 1.0


def test_mean_reversion_after_failure_fires_on_failed_breakout():
    # Build: long flat base ~100, a spike to 110 (breakout), then close back below the base high.
    closes = list(np.full(25, 100.0)) + [110.0, 101.0, 99.0]
    highs_extra = [111.0, 102.0, 100.0]
    n = len(closes)
    c = np.asarray(closes, float)
    df = pd.DataFrame({"open": c, "high": c + 1.0, "low": c - 1.0, "close": c,
                       "volume": np.full(n, 1000.0)})
    df.loc[df.index[-3:], "high"] = highs_extra      # the spike made a recent high
    mr = F.mean_reversion_after_failure(df, lookback=20, recent=5)
    assert mr.iloc[-1] > 0          # price is back below the prior high after a recent breakout
    # A bar with no prior breakout shows no failure signal.
    assert mr.iloc[10] == 0.0


def test_spearman_ic_monotonic():
    x = pd.Series(np.arange(200, dtype=float))
    y = x * 2.0 + 1.0                                 # perfectly monotonic
    assert spearman_ic(x, y) > 0.99


def test_spearman_ic_noise_near_zero():
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(size=500))
    y = pd.Series(rng.normal(size=500))
    assert abs(spearman_ic(x, y)) < 0.15              # unrelated -> ~0


def test_quintile_spread_runs():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(size=500))
    y = x * 0.1 + pd.Series(rng.normal(size=500))     # weak positive
    qs = quintile_spread(x, y)
    assert qs is not None and "spread" in qs
