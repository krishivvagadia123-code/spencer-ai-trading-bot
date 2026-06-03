"""
Mean-reversion challenger:
  Bollinger Bands(20, 2) + RSI(14). Only active in RANGE regimes.

BUY when:
  price <= lower band   (oversold from mean)
  RSI <= 30             (momentum exhausted)
  context['regime']  ∈  {'RANGE', None}     (disabled in strong trend)

Stop      = lower band - 1 * ATR
Target    = midline (mean reversion to mean)
"""

from __future__ import annotations
from typing import List, Optional

from bot.strategies.base import (
    BacktestBar, Strategy, StrategyAction, StrategySignal,
    atr, bollinger, rsi,
)


class MeanReversionBBands:
    name                 = "mean_reversion_bbands"
    required_indicators  = ["bb_mid", "bb_upper", "bb_lower", "rsi", "atr"]
    backtest_safe        = True

    def generate_signal(self, bars: List[BacktestBar],
                        context: Optional[dict] = None) -> StrategySignal:
        ind: dict = {}
        if len(bars) < 25:
            return self._reject([f"need 25 bars, have {len(bars)}"], ind)

        last  = bars[-1]
        price = last.close
        ind["price"] = price

        closes = [b.close for b in bars]
        bb = bollinger(closes, 20, 2.0)
        a  = atr(bars, 14);   ind["atr"] = a or 0
        r  = rsi(closes, 14); ind["rsi"] = r or 0
        if bb is None or a is None or r is None:
            return self._reject(["indicators not ready"], ind)
        mid, upper, lower = bb
        ind["bb_mid"]   = mid
        ind["bb_upper"] = upper
        ind["bb_lower"] = lower

        # Regime gate — disabled in strong trends
        regime = (context or {}).get("regime", "RANGE")
        if regime in ("TREND_BULL", "TREND_BEAR"):
            return StrategySignal(
                strategy_name=self.name, action=StrategyAction.HOLD,
                confidence=0.0,
                reasons=[f"mean-reversion disabled in {regime} regime"],
                indicators=ind,
            )

        reasons: List[str] = []
        if price > lower:
            reasons.append(f"price {price:.2f} above lower band {lower:.2f}")
        if r > 30:
            reasons.append(f"RSI {r:.1f} > 30 (not oversold)")
        if reasons:
            return StrategySignal(
                strategy_name=self.name, action=StrategyAction.HOLD,
                confidence=0.0, reasons=reasons, indicators=ind,
            )

        stop   = round(lower - a, 4)
        target = round(mid, 4)
        # Confidence: depth below band, RSI extreme, band width sanity
        depth      = min(1.0, (lower - price) / a) if a > 0 else 0
        rsi_score  = min(1.0, (30 - r) / 15)
        band_width = (upper - lower) / mid if mid > 0 else 0
        band_score = 1.0 - abs(band_width - 0.04) / 0.08
        conf = round(0.4 * depth + 0.3 * rsi_score + 0.3 * max(0, band_score), 4)
        return StrategySignal(
            strategy_name=self.name, action=StrategyAction.BUY,
            confidence=conf,
            reasons=[f"below lower band {lower:.2f}", f"RSI {r:.1f} oversold",
                     f"regime={regime}"],
            indicators=ind, stop=stop, target=target,
        )

    def _reject(self, reasons, ind):
        return StrategySignal(
            strategy_name=self.name, action=StrategyAction.REJECT,
            confidence=0.0, reasons=reasons, indicators=ind,
        )

    def explain_signal(self, signal: StrategySignal) -> str:
        if signal.action == StrategyAction.BUY:
            return (f"BUY ({self.name}): mean-reversion setup — price below lower "
                    f"BB and RSI oversold in RANGE regime. "
                    f"stop={signal.stop} target={signal.target} conf={signal.confidence:.2f}")
        return f"{signal.action.value} ({self.name}): " + "; ".join(signal.reasons)
