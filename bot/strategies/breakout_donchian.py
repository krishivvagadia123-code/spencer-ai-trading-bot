"""
Donchian 20-bar breakout champion candidate.

BUY when:
  current close > 20-bar prior high   (true breakout)
  volume >= 1.2 * 20-bar average     (volume confirmation)
  ATR / price ∈ [0.5%, 5%]            (volatility regime filter)
  candle body < 3 * ATR              (not chasing an overextended candle)

Stop      = breakout level - 1 * ATR
Target    = breakout level + 2 * ATR
"""

from __future__ import annotations
from typing import List, Optional

from bot.strategies.base import (
    BacktestBar, Strategy, StrategyAction, StrategySignal,
    atr, donchian,
)


class BreakoutDonchian:
    name                 = "breakout_donchian"
    required_indicators  = ["donchian_upper", "donchian_lower", "atr", "vol_ratio"]
    backtest_safe        = True

    def generate_signal(self, bars: List[BacktestBar],
                        context: Optional[dict] = None) -> StrategySignal:
        ind: dict = {}
        if len(bars) < 25:
            return self._reject([f"need 25 bars, have {len(bars)}"], ind)

        last  = bars[-1]
        price = last.close
        ind["price"] = price

        donch = donchian(bars, 20)
        a     = atr(bars, 14); ind["atr"] = a or 0
        if donch is None or a is None or a == 0:
            return self._reject(["donchian/atr not ready"], ind)
        upper, lower = donch
        ind["donchian_upper"] = upper
        ind["donchian_lower"] = lower

        avg_vol = sum(b.volume for b in bars[-21:-1]) / 20
        vol_ratio = last.volume / avg_vol if avg_vol > 0 else 0.0
        ind["vol_ratio"] = vol_ratio

        reasons: List[str] = []
        if price <= upper:
            reasons.append(f"no breakout (price {price:.2f} <= upper {upper:.2f})")
        if vol_ratio < 1.2:
            reasons.append(f"weak volume confirm (ratio {vol_ratio:.2f} < 1.2)")
        atr_pct = a / price if price > 0 else 0
        if not (0.005 <= atr_pct <= 0.05):
            reasons.append(f"ATR% {atr_pct*100:.2f}% outside [0.5%, 5%]")
        body = abs(last.close - last.open)
        if body > 3 * a:
            reasons.append(f"overextended candle (body {body:.2f} > 3*ATR {3*a:.2f})")

        if reasons:
            return StrategySignal(
                strategy_name=self.name, action=StrategyAction.HOLD,
                confidence=0.0, reasons=reasons, indicators=ind,
            )

        stop   = round(upper - 1 * a, 4)
        target = round(upper + 2 * a, 4)
        # Confidence: how decisively price broke + volume strength + volatility sweet-spot
        break_score = min(1.0, (price - upper) / a)
        vol_score   = min(1.0, (vol_ratio - 1.2) / 1.0)
        vol_regime  = 1.0 - abs(atr_pct - 0.02) / 0.03
        conf = round(0.4 * break_score + 0.3 * vol_score + 0.3 * max(0, vol_regime), 4)
        return StrategySignal(
            strategy_name=self.name, action=StrategyAction.BUY,
            confidence=conf,
            reasons=[f"breakout above {upper:.2f}",
                     f"volume confirm {vol_ratio:.2f}x",
                     f"ATR% {atr_pct*100:.2f}%"],
            indicators=ind, stop=stop, target=target,
        )

    def _reject(self, reasons, ind):
        return StrategySignal(
            strategy_name=self.name, action=StrategyAction.REJECT,
            confidence=0.0, reasons=reasons, indicators=ind,
        )

    def explain_signal(self, signal: StrategySignal) -> str:
        if signal.action == StrategyAction.BUY:
            return (f"BUY ({self.name}): Donchian-20 breakout with volume "
                    f"and ATR in regime. stop={signal.stop} target={signal.target} "
                    f"conf={signal.confidence:.2f}")
        return f"{signal.action.value} ({self.name}): " + "; ".join(signal.reasons)
