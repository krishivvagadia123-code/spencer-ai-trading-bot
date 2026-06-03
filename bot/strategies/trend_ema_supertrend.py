"""
Trend-following champion candidate:
  EMA 20 + EMA 50 + EMA 200 + Supertrend + ADX trend filter + RSI sanity.

BUY when:
  EMA20 > EMA50 > EMA200       (multi-timeframe trend alignment)
  Supertrend = green
  ADX        >= 20             (trend strength filter)
  RSI 50-70                    (uptrending but not exhausted)

Otherwise HOLD. Never shorts in paper mode.

Stop      = close - 2 * ATR
Target    = close + 3 * ATR     (1.5R)
Confidence = blend of distance from 200-EMA, ADX strength, RSI midrange.
"""

from __future__ import annotations
from typing import List, Optional

from bot.strategies.base import (
    BacktestBar, Strategy, StrategyAction, StrategySignal,
    adx, atr, ema, rsi, supertrend,
)


class TrendEmaSupertrend:
    name                 = "trend_ema_supertrend"
    required_indicators  = ["ema20", "ema50", "ema200", "supertrend", "adx", "rsi", "atr"]
    backtest_safe        = True

    def generate_signal(self, bars: List[BacktestBar],
                        context: Optional[dict] = None) -> StrategySignal:
        ind: dict = {}
        reasons: List[str] = []
        if len(bars) < 200:
            return self._reject(reasons + [f"need 200 bars, have {len(bars)}"], ind)

        closes = [b.close for b in bars]
        e20  = ema(closes, 20);   ind["ema20"]  = e20  or 0
        e50  = ema(closes, 50);   ind["ema50"]  = e50  or 0
        e200 = ema(closes, 200);  ind["ema200"] = e200 or 0
        st   = supertrend(bars, 10, 3.0)
        a    = atr(bars, 14);     ind["atr"]    = a    or 0
        r    = rsi(closes, 14);   ind["rsi"]    = r    or 0
        adx_ = adx(bars, 14);     ind["adx"]    = adx_ or 0

        price = bars[-1].close
        ind["price"] = price

        if st is None:
            return self._reject(["supertrend not ready"], ind)
        st_trend, st_line = st
        ind["supertrend_trend"] = 1.0 if st_trend == "green" else 0.0
        ind["supertrend_line"]  = st_line

        if not (e20 and e50 and e200 and a and r and adx_):
            return self._reject(["indicators not ready"], ind)

        # Trend alignment
        if not (e20 > e50 > e200):
            reasons.append(f"EMAs not aligned (20={e20:.2f} 50={e50:.2f} 200={e200:.2f})")
        if st_trend != "green":
            reasons.append("supertrend red")
        if adx_ < 20:
            reasons.append(f"ADX {adx_:.1f} < 20 (weak trend)")
        if not (50 <= r <= 70):
            reasons.append(f"RSI {r:.1f} outside [50, 70]")

        if reasons:
            return StrategySignal(
                strategy_name=self.name, action=StrategyAction.HOLD,
                confidence=0.0, reasons=reasons, indicators=ind,
            )

        stop   = round(price - 2 * a, 4)
        target = round(price + 3 * a, 4)
        # Confidence: blend of ADX (capped at 50), RSI sweet-spot, EMA20 distance vs EMA200
        adx_score = min(1.0, (adx_ - 20) / 30)
        rsi_score = 1.0 - abs(r - 60) / 20         # peaks at RSI 60
        ema_score = min(1.0, max(0.0, (e20 - e200) / e200 * 20))
        conf = round(0.4 * adx_score + 0.3 * rsi_score + 0.3 * ema_score, 4)
        return StrategySignal(
            strategy_name=self.name, action=StrategyAction.BUY,
            confidence=conf,
            reasons=["EMA aligned bullish", "supertrend green",
                     f"ADX {adx_:.1f}", f"RSI {r:.1f}"],
            indicators=ind, stop=stop, target=target,
        )

    def _reject(self, reasons, ind):
        return StrategySignal(
            strategy_name=self.name, action=StrategyAction.REJECT,
            confidence=0.0, reasons=reasons, indicators=ind,
        )

    def explain_signal(self, signal: StrategySignal) -> str:
        if signal.action == StrategyAction.BUY:
            return (f"BUY ({self.name}): multi-EMA bullish + Supertrend green + "
                    f"ADX trend confirmed + RSI in healthy zone. "
                    f"stop={signal.stop} target={signal.target} conf={signal.confidence:.2f}")
        return f"{signal.action.value} ({self.name}): " + "; ".join(signal.reasons)
