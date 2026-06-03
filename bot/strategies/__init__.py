"""
Strategy package — pure, testable trading strategies for the tournament.

Each strategy module exposes:
  name                 : str
  required_indicators  : List[str]
  backtest_safe        : bool          (True iff strategy never peeks ahead)
  generate_signal(bars, context) -> StrategySignal
  explain_signal(signal) -> str

`bars` is a list of BacktestBar dicts ordered oldest → newest. The strategy
MUST only read bars[: len(bars)] — no future indexing. The tournament passes
a progressively-growing prefix so look-ahead is impossible by construction.
"""

from bot.strategies.base import (
    BacktestBar, Strategy, StrategyAction, StrategySignal,
)
from bot.strategies.trend_ema_supertrend  import TrendEmaSupertrend
from bot.strategies.breakout_donchian     import BreakoutDonchian
from bot.strategies.mean_reversion_bbands import MeanReversionBBands
from bot.strategies.regime_filter         import RegimeFilter, RegimeTag

ALL_STRATEGIES = [
    TrendEmaSupertrend(),
    BreakoutDonchian(),
    MeanReversionBBands(),
]

__all__ = [
    "ALL_STRATEGIES",
    "BacktestBar", "Strategy", "StrategyAction", "StrategySignal",
    "TrendEmaSupertrend", "BreakoutDonchian", "MeanReversionBBands",
    "RegimeFilter", "RegimeTag",
]
