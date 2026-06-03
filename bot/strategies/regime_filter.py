"""
BTC/ETH regime filter — gates altcoin risk based on benchmark trend.

Returns a RegimeTag from the latest benchmark bars (BTC primary, ETH fallback).
The supervisor consults this before any altcoin BUY and may zero-out risk in
TREND_BEAR or scale down in RANGE.

Pure / deterministic. No external calls.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from bot.strategies.base import BacktestBar, ema


class RegimeTag(str, Enum):
    TREND_BULL = "TREND_BULL"     # BTC above EMA50 and EMA200, EMA50 > EMA200
    TREND_BEAR = "TREND_BEAR"     # BTC below EMA200 and EMA50 < EMA200
    RANGE      = "RANGE"          # neither
    UNKNOWN    = "UNKNOWN"        # insufficient data


@dataclass(frozen=True)
class RegimeAssessment:
    tag:               RegimeTag
    benchmark_symbol:  str
    benchmark_price:   Optional[float]
    ema50:             Optional[float]
    ema200:            Optional[float]
    reasons:           List[str]

    def allows_altcoin_risk(self) -> bool:
        return self.tag in (RegimeTag.TREND_BULL, RegimeTag.RANGE)

    def risk_multiplier(self) -> float:
        """Multiplier applied to the capital governor's per-trade risk."""
        return {
            RegimeTag.TREND_BULL: 1.0,
            RegimeTag.RANGE:      0.5,
            RegimeTag.TREND_BEAR: 0.0,    # blocks altcoin buys
            RegimeTag.UNKNOWN:    0.5,
        }[self.tag]


class RegimeFilter:
    name                 = "regime_filter"
    required_indicators  = ["ema50", "ema200"]
    backtest_safe        = True

    def __init__(self, benchmark_symbol: str = "BTC-INR"):
        self.benchmark_symbol = benchmark_symbol

    def assess(self, benchmark_bars: List[BacktestBar]) -> RegimeAssessment:
        if len(benchmark_bars) < 200:
            return RegimeAssessment(
                tag=RegimeTag.UNKNOWN, benchmark_symbol=self.benchmark_symbol,
                benchmark_price=None, ema50=None, ema200=None,
                reasons=[f"need 200 bars, have {len(benchmark_bars)}"],
            )
        closes = [b.close for b in benchmark_bars]
        e50    = ema(closes, 50)
        e200   = ema(closes, 200)
        price  = benchmark_bars[-1].close
        if not (e50 and e200):
            return RegimeAssessment(
                tag=RegimeTag.UNKNOWN, benchmark_symbol=self.benchmark_symbol,
                benchmark_price=price, ema50=e50, ema200=e200,
                reasons=["EMA not ready"],
            )
        if price > e200 and e50 > e200:
            tag = RegimeTag.TREND_BULL
            reasons = [f"BTC {price:.2f} > EMA200 {e200:.2f}",
                       f"EMA50 {e50:.2f} > EMA200"]
        elif price < e200 and e50 < e200:
            tag = RegimeTag.TREND_BEAR
            reasons = [f"BTC {price:.2f} < EMA200 {e200:.2f}",
                       f"EMA50 {e50:.2f} < EMA200"]
        else:
            tag = RegimeTag.RANGE
            reasons = ["mixed EMA signals → RANGE"]
        return RegimeAssessment(
            tag=tag, benchmark_symbol=self.benchmark_symbol,
            benchmark_price=price, ema50=e50, ema200=e200, reasons=reasons,
        )

    # Strategy-protocol shims (so it can sit in ALL_STRATEGIES if ever needed)
    def generate_signal(self, bars, context=None):
        from bot.strategies.base import StrategySignal, StrategyAction
        a = self.assess(bars)
        return StrategySignal(
            strategy_name=self.name, action=StrategyAction.HOLD,
            confidence=1.0 if a.tag == RegimeTag.TREND_BULL else 0.0,
            reasons=a.reasons,
            indicators={"price": a.benchmark_price or 0,
                        "ema50": a.ema50 or 0, "ema200": a.ema200 or 0,
                        "risk_multiplier": a.risk_multiplier()},
        )

    def explain_signal(self, signal) -> str:
        return f"regime={signal.reasons[0] if signal.reasons else 'unknown'}"
