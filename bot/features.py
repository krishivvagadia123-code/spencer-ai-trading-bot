"""
Candidate PREDICTIVE features (Option B). Deterministic, causal (no look-ahead).

These are NOT trading signals yet. Each is a number computed from data available at the
bar's close. Their predictive value is measured separately in bot/feature_eval.py (via
information coefficient vs forward returns) BEFORE any of them is used to take a trade.
This is the opposite of blind optimization: measure edge first, build entries later — and
only if the edge survives out-of-sample.

Features:
  1. relative_strength      — symbol return minus Nifty return over a lookback (leadership).
  2. breakout_quality       — how decisively price clears the prior-N high, in ATR units.
  3. volume_expansion_quality — today's volume as a z-score vs its recent average (conviction).
  4. sector_strength        — average relative strength of the symbol's sector peers
                              (computed at the panel level in feature_eval, needs peers).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bot import indicators as ind


def relative_strength(close: pd.Series, bench_close: pd.Series, period: int = 20) -> pd.Series:
    """Symbol return minus benchmark return over `period` bars. >0 = outperforming."""
    sym = close / close.shift(period) - 1.0
    bench = bench_close / bench_close.shift(period) - 1.0
    return sym - bench


def breakout_quality(df: pd.DataFrame, lookback: int = 20, atr_period: int = 14) -> pd.Series:
    """
    (close - prior_N_high) / ATR. Positive = trading above the prior high by that many ATRs
    (a clean, decisive breakout); negative = still inside/below the range.
    """
    prior_high = df["high"].rolling(lookback).max().shift(1)
    atr = ind.atr(df, atr_period).replace(0, np.nan)
    return (df["close"] - prior_high) / atr


def volume_expansion_quality(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Volume z-score vs its `period` average. High = unusual conviction behind the move."""
    v = df["volume"]
    sma = v.rolling(period).mean()
    std = v.rolling(period).std().replace(0, np.nan)
    return (v - sma) / std


def mean_reversion_after_failure(df: pd.DataFrame, lookback: int = 20, recent: int = 5,
                                 atr_period: int = 14) -> pd.Series:
    """
    Failed-breakout magnitude: price broke the prior-N high within the last `recent` bars
    but has closed BACK BELOW it. Value = (prior_high - close)/ATR when that happens, else 0.
    Hypothesis: a failed upside breakout tends to revert DOWN, so this should correlate with
    NEGATIVE forward returns if it has predictive power. Causal (no look-ahead).
    """
    # Resistance level BEFORE the recent breakout window (shift by `recent` so the
    # breakout spike itself does not get absorbed into the level).
    prior_high = df["high"].rolling(lookback).max().shift(recent)
    recent_high = df["high"].rolling(recent).max()
    atr = ind.atr(df, atr_period).replace(0, np.nan)
    broke = recent_high > prior_high          # cleared the breakout level recently
    back_inside = df["close"] < prior_high     # but is back below it now
    failure_mag = ((prior_high - df["close"]) / atr).clip(lower=0)
    return failure_mag.where(broke & back_inside, 0.0)


def forward_return(close: pd.Series, horizon: int = 5) -> pd.Series:
    """TARGET (look-ahead by design): return from t to t+horizon. Used only for evaluation."""
    return close.shift(-horizon) / close - 1.0
