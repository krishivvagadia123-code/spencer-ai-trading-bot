"""Sanity tests for intraday session-feature construction (no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bot import intraday_eval as IE


def _synth_day(date_str, n=12, base=100.0):
    ts = pd.date_range(f"{date_str} 03:45", periods=n, freq="15min", tz="UTC")
    close = base + np.arange(n, dtype=float)        # steadily rising within the day
    df = pd.DataFrame({
        "open": close, "high": close + 0.5, "low": close - 0.5,
        "close": close, "volume": np.full(n, 1000.0),
    }, index=ts)
    df["day"] = [t.date() for t in df.index]
    return df


def test_session_features_are_causal_and_anchored():
    df = pd.concat([_synth_day("2026-04-01"), _synth_day("2026-04-02", base=200.0)])
    bench = pd.Series(0.0, index=df.index)           # flat benchmark
    out = IE.per_symbol(df.copy(), bench)

    # Opening range position rises within a trending day (above OR high late in session).
    last = out[out["day"] == out["day"].iloc[0]].iloc[-1]
    assert last["opening_range"] > 1.0

    # VWAP distance is ~0 at the first bar of each day (price == vwap on bar 1).
    first_bars = out.groupby("day").head(1)
    assert (first_bars["vwap_distance"].abs() < 1e-6).all()

    # Forward return is NaN for the last HORIZON_BARS of each day (no look-ahead across days).
    for _, gdf in out.groupby("day"):
        assert gdf["fwd"].tail(IE.HORIZON_BARS).isna().all()


def test_relative_strength_zero_vs_self_benchmark():
    df = _synth_day("2026-04-01")
    # Benchmark return equal to the stock's own within-day return -> RS ~ 0.
    g = df.groupby("day")["close"]
    own = df["close"] / g.transform(lambda s: s.shift(IE.RS_BARS)) - 1.0
    out = IE.per_symbol(df.copy(), own)
    assert out["relative_strength"].abs().fillna(0).max() < 1e-9
