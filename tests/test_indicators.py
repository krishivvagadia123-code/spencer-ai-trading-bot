"""Indicator tests."""
import pandas as pd
import pytest
from bot.indicators import atr, rsi, supertrend, vwap


@pytest.fixture
def uptrend_bars():
    return pd.DataFrame({
        "open":   [100 + i for i in range(30)],
        "high":   [101 + i for i in range(30)],
        "low":    [99  + i for i in range(30)],
        "close":  [100.5 + i for i in range(30)],
        "volume": [1000] * 30,
    })


@pytest.fixture
def downtrend_bars():
    return pd.DataFrame({
        "open":   [200 - i for i in range(30)],
        "high":   [201 - i for i in range(30)],
        "low":    [199 - i for i in range(30)],
        "close":  [199.5 - i for i in range(30)],
        "volume": [1000] * 30,
    })


def test_atr_returns_series_same_length(uptrend_bars):
    result = atr(uptrend_bars, period=14)
    assert isinstance(result, pd.Series)
    assert len(result) == len(uptrend_bars)


def test_atr_positive_for_volatile_data(uptrend_bars):
    assert atr(uptrend_bars, period=14).iloc[-1] > 0


def test_atr_missing_columns_raises():
    bad_df = pd.DataFrame({"close": [1, 2, 3]})
    with pytest.raises(ValueError, match="high"):
        atr(bad_df)


def test_rsi_uptrend_above_50(uptrend_bars):
    assert rsi(uptrend_bars, period=14).iloc[-1] > 50


def test_rsi_downtrend_below_50(downtrend_bars):
    assert rsi(downtrend_bars, period=14).iloc[-1] < 50


def test_rsi_bounded_0_to_100(uptrend_bars, downtrend_bars):
    for df in [uptrend_bars, downtrend_bars]:
        result = rsi(df, period=14).dropna()
        assert (result >= 0).all() and (result <= 100).all()


def test_supertrend_returns_df_with_correct_columns(uptrend_bars):
    result = supertrend(uptrend_bars)
    assert "supertrend" in result.columns
    assert "trend" in result.columns


def test_supertrend_uptrend_is_green_eventually(uptrend_bars):
    assert supertrend(uptrend_bars, period=10, multiplier=3)["trend"].iloc[-1] == "green"


def test_supertrend_downtrend_is_red_eventually(downtrend_bars):
    assert supertrend(downtrend_bars, period=10, multiplier=3)["trend"].iloc[-1] == "red"


def test_vwap_between_high_and_low(uptrend_bars):
    result = vwap(uptrend_bars)
    assert result.iloc[-1] >= uptrend_bars["low"].min()
    assert result.iloc[-1] <= uptrend_bars["high"].max()


def test_vwap_requires_volume_column():
    df_no_vol = pd.DataFrame({"high": [1], "low": [1], "close": [1]})
    with pytest.raises(ValueError, match="volume"):
        vwap(df_no_vol)
