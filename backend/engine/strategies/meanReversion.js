// ─── Mean Reversion (Range markets) ──────────────────────────────────────────
// Author: Larry Connors / Cesar Alvarez style
//
// Thesis: in a range-bound market, price stretched FAR below its mean tends to
// snap back. Buy oversold dips near support; the exit manager rides the bounce.
//
// Entry rule (LONG):
//   - Price is at/below the lower band (EMA20 - 1.8*ATR)  → stretched down
//   - RSI(14) <= 35                                       → oversold
//   - Price is near recent support (within 0.4*ATR of 20-bar low)
//   - At least 20 mins into session, not near close
//
// Exit: handled by the shared exit manager (breakeven → trail → reversal).
//   Initial stop is wide (below support); target back toward the mean.

import { ema, rsi, atr, lowest } from "../indicators.js";
import { manageExit } from "../exitManager.js";

export const meta = {
  id: "mean_reversion",
  name: "Mean Reversion",
  type: "Swing",
  author: "Connors / Alvarez style",
  edge: "Range markets revert ~70% of the time; buys oversold dips near support.",
  description: "Buys stretched-down, oversold price near support in range-bound markets; rides the snap-back.",
};

export function evaluate(bars) {
  if (bars.length < 40) return { signal: null, reason: "Not enough bars (need ≥40)" };

  const last = bars[bars.length - 1];
  if (last.sessionMinute < 20) return { signal: null, reason: "Too early in session" };
  if (last.sessionMinute > 350) return { signal: null, reason: "Too close to session end" };

  const ema20 = ema(bars, 20);
  const atrVal = atr(bars, 14);
  const rsiVal = rsi(bars, 14);
  if (ema20 == null || atrVal == null || rsiVal == null) {
    return { signal: null, reason: "Indicators unavailable" };
  }

  const lowerBand = ema20 - 1.8 * atrVal;
  const support = lowest(bars.slice(-20), 20);

  const stretchedDown = last.close <= lowerBand;
  const oversold = rsiVal <= 35;
  const nearSupport = last.low <= support + 0.4 * atrVal;

  if (!stretchedDown) {
    return { signal: null, reason: `Not stretched down (close ${last.close.toFixed(2)} > lower band ${lowerBand.toFixed(2)})` };
  }
  if (!oversold) {
    return { signal: null, reason: `RSI ${rsiVal.toFixed(0)} not oversold (need ≤35)` };
  }
  if (!nearSupport) {
    return { signal: null, reason: "Not near support yet" };
  }

  // SIGNAL — buy the oversold dip. Stop below support, target back to the mean.
  const entry = last.close;
  const stopLoss = +(Math.min(support, entry) - atrVal * 1.0).toFixed(2);
  const target   = +(ema20 + atrVal * 0.5).toFixed(2); // revert toward/above the mean

  return {
    signal: "BUY",
    reason: `Oversold bounce: RSI ${rsiVal.toFixed(0)}, price ${entry.toFixed(2)} at lower band ${lowerBand.toFixed(2)} near support ${support.toFixed(2)}`,
    entry,
    stopLoss,
    target,
    atrAtEntry: +atrVal.toFixed(2),
    indicators: {
      rsi: +rsiVal.toFixed(1),
      ema20: +ema20.toFixed(2),
      lowerBand: +lowerBand.toFixed(2),
      support: +support.toFixed(2),
      atr: +atrVal.toFixed(2),
    },
  };
}

export function shouldExit(bars, position) {
  // Reuse the polished exit manager, but mean-reversion exits a touch sooner on
  // reaching the mean (don't get greedy on a counter-trend bounce).
  return manageExit(bars, position, { trailMult: 1.8, hardTargetMult: 3.5 });
}
