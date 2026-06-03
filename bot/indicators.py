"""
Pure-function technical indicators.
No state, no side effects.
"""

import pandas as pd
import numpy as np


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — Wilder smoothing."""
    _require_columns(df, ["high", "low", "close"])
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    """Relative Strength Index — Wilder smoothing. RSI=100 when no losses, 0 when no gains."""
    _require_columns(df, [column])
    delta    = df[column].diff()
    gain     = delta.where(delta > 0, 0.0)
    loss     = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    result   = 100 - (100 / (1 + rs))
    # Pure uptrend: avg_loss=0 → result=NaN → 100
    result   = result.where(avg_loss != 0, 100.0)
    return result


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Supertrend — returns DataFrame[supertrend, trend]."""
    _require_columns(df, ["high", "low", "close"])
    hl2        = (df["high"] + df["low"]) / 2
    atr_series = atr(df, period)
    upper_band = hl2 + multiplier * atr_series
    lower_band = hl2 - multiplier * atr_series

    final_upper = upper_band.copy()
    final_lower = lower_band.copy()
    st          = pd.Series(index=df.index, dtype=float)
    trend       = pd.Series(index=df.index, dtype=object)

    for i in range(len(df)):
        if i == 0:
            st.iloc[i]    = upper_band.iloc[i]
            trend.iloc[i] = "red"
            continue
        if df["close"].iloc[i-1] <= final_upper.iloc[i-1]:
            final_upper.iloc[i] = min(upper_band.iloc[i], final_upper.iloc[i-1])
        if df["close"].iloc[i-1] >= final_lower.iloc[i-1]:
            final_lower.iloc[i] = max(lower_band.iloc[i], final_lower.iloc[i-1])

        prev_st = st.iloc[i-1]
        if prev_st == final_upper.iloc[i-1] and df["close"].iloc[i] <= final_upper.iloc[i]:
            st.iloc[i] = final_upper.iloc[i]; trend.iloc[i] = "red"
        elif prev_st == final_upper.iloc[i-1] and df["close"].iloc[i] >  final_upper.iloc[i]:
            st.iloc[i] = final_lower.iloc[i]; trend.iloc[i] = "green"
        elif prev_st == final_lower.iloc[i-1] and df["close"].iloc[i] >= final_lower.iloc[i]:
            st.iloc[i] = final_lower.iloc[i]; trend.iloc[i] = "green"
        elif prev_st == final_lower.iloc[i-1] and df["close"].iloc[i] <  final_lower.iloc[i]:
            st.iloc[i] = final_upper.iloc[i]; trend.iloc[i] = "red"
        else:
            st.iloc[i]    = prev_st
            trend.iloc[i] = trend.iloc[i-1]

    return pd.DataFrame({"supertrend": st, "trend": trend})


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session-anchored VWAP."""
    _require_columns(df, ["high", "low", "close", "volume"])
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_pv        = (typical_price * df["volume"]).cumsum()
    cum_vol       = df["volume"].cumsum().replace(0, np.nan)
    return cum_pv / cum_vol


def _require_columns(df: pd.DataFrame, cols: list) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}. "
                         f"Got: {list(df.columns)}")
