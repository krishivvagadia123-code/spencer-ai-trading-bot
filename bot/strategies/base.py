"""
Strategy base types — pure dataclasses + indicator helpers.

Strategies are PURE FUNCTIONS over a window of past OHLCV bars. They never:
  - hit the network
  - call an LLM
  - mutate global state
  - peek at bars beyond the current index
Tournament + scanner pass progressively-growing bar prefixes, so look-ahead
is impossible by construction.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Protocol


class StrategyAction(str, Enum):
    BUY    = "BUY"
    SELL   = "SELL"
    HOLD   = "HOLD"
    REJECT = "REJECT"


@dataclass(frozen=True)
class BacktestBar:
    ts:     str           # ISO timestamp
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float


@dataclass(frozen=True)
class StrategySignal:
    strategy_name: str
    action:        StrategyAction
    confidence:    float                       # 0..1
    reasons:       List[str]                   # human-readable
    indicators:    Dict[str, float]            # for audit
    stop:          Optional[float] = None
    target:        Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "action":        self.action.value,
            "confidence":    self.confidence,
            "reasons":       list(self.reasons),
            "indicators":    dict(self.indicators),
            "stop":          self.stop,
            "target":        self.target,
        }


class Strategy(Protocol):
    name:                str
    required_indicators: List[str]
    backtest_safe:       bool
    def generate_signal(self, bars: List[BacktestBar],
                        context: Optional[dict] = None) -> StrategySignal: ...
    def explain_signal(self, signal: StrategySignal) -> str: ...


# ── Pure indicator helpers (no pandas dependency — Phase J keeps deps small) ─
def ema(values: List[float], period: int) -> Optional[float]:
    """Single-value EMA over `values` ending at the last element."""
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def stdev(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    sub = values[-period:]
    mean = sum(sub) / period
    return (sum((v - mean) ** 2 for v in sub) / period) ** 0.5


def rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(bars: List[BacktestBar], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period


def donchian(bars: List[BacktestBar], period: int) -> Optional[tuple]:
    """Returns (upper, lower) over the last `period` bars EXCLUDING the
    current bar — strict, so a break of upper means the current high > prior period high."""
    if len(bars) < period + 1:
        return None
    window = bars[-period - 1 : -1]
    upper = max(b.high for b in window)
    lower = min(b.low for b in window)
    return upper, lower


def adx(bars: List[BacktestBar], period: int = 14) -> Optional[float]:
    """Simplified ADX — directional movement strength."""
    if len(bars) < period * 2 + 1:
        return None
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, len(bars)):
        up   = bars[i].high - bars[i - 1].high
        down = bars[i - 1].low - bars[i].low
        plus_dm.append(up   if (up > down and up > 0)   else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if sum(trs[-period:]) == 0:
        return 0.0
    plus_di  = 100 * (sum(plus_dm[-period:])  / sum(trs[-period:]))
    minus_di = 100 * (sum(minus_dm[-period:]) / sum(trs[-period:]))
    denom = plus_di + minus_di
    if denom == 0:
        return 0.0
    dx = 100 * abs(plus_di - minus_di) / denom
    return dx   # single-bar DX as a serviceable proxy for ADX


def supertrend(bars: List[BacktestBar], period: int = 10,
               multiplier: float = 3.0) -> Optional[tuple]:
    """Returns (trend: 'green'|'red', line: float). Conservative: needs ≥ period+1 bars."""
    if len(bars) < period + 1:
        return None
    a = atr(bars, period)
    if a is None:
        return None
    last = bars[-1]
    median = (last.high + last.low) / 2
    upper = median + multiplier * a
    lower = median - multiplier * a
    # Trend by close vs midline (simple variant; sufficient for scoring)
    trend = "green" if last.close > median else "red"
    return trend, (lower if trend == "green" else upper)


def bollinger(closes: List[float], period: int = 20,
              k: float = 2.0) -> Optional[tuple]:
    m = sma(closes, period)
    s = stdev(closes, period)
    if m is None or s is None:
        return None
    return m, m + k * s, m - k * s
