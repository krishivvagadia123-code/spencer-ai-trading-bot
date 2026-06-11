// ─── VWAP Breakout (Intraday) ────────────────────────────────────────────────
// Author: Institutional VWAP standard
//
// Entry rule:
//   - Current close > VWAP (price above institutional benchmark)
//   - Latest bar's volume > 1.8× average of last 20 bars
//   - Price has been BELOW VWAP within the previous 5 bars (so it's an actual breakout)
//   - At least 15 minutes into the session (skip opening volatility)
//
// Exit rule:
//   - Target: entry + 2× ATR(14)
//   - Stop:   entry - 1× ATR(14)
//   - Time stop: close at 15:15 IST (5 mins before market close) if no SL/TP hit
//
// Returns: { signal: "BUY" | null, reason, stopLoss, target, indicators }

import { vwap, atr, avgVolume, findSessionStart } from "../indicators.js";
import { manageExit } from "../exitManager.js";

export const meta = {
  id: "vwap_breakout",
  name: "VWAP Breakout",
  type: "Intraday",
  author: "Institutional standard",
  edge: "Aligns with institutional VWAP anchoring; trades trend-continuation breakouts.",
  description: "Long entry when price breaks above VWAP with 2× average volume and confirmed trend.",
};

export function evaluate(bars) {
  if (bars.length < 30) {
    return { signal: null, reason: "Not enough bars (need ≥30)" };
  }

  const last = bars[bars.length - 1];

  // Must be at least 15 mins into session
  if (last.sessionMinute < 15) {
    return { signal: null, reason: "Too early in session" };
  }
  // Don't enter near close
  if (last.sessionMinute > 350) {
    return { signal: null, reason: "Too close to session end" };
  }

  // Calculate VWAP from the start of TODAY's session
  const sessionStart = findSessionStart(bars);
  const sessionBars = bars.slice(sessionStart);
  if (sessionBars.length < 5) {
    return { signal: null, reason: "Session just started" };
  }
  const vwapValue = vwap(bars, sessionStart);

  // Volume check
  const avgVol = avgVolume(bars, 20);
  if (!avgVol) return { signal: null, reason: "Volume avg unavailable" };

  // ATR for stop/target sizing
  const atrValue = atr(bars, 14);
  if (!atrValue) return { signal: null, reason: "ATR unavailable" };

  const aboveVwap = last.close > vwapValue;
  const bigVolume = last.volume > avgVol * 1.8;

  // Was the price recently BELOW vwap? (this is what makes it a "breakout")
  let wasBelow = false;
  for (let i = Math.max(sessionStart, bars.length - 6); i < bars.length - 1; i++) {
    if (bars[i].close < vwap(bars.slice(0, i + 1), sessionStart)) {
      wasBelow = true;
      break;
    }
  }

  if (!aboveVwap) {
    return { signal: null, reason: `Price below VWAP (${last.close.toFixed(2)} < ${vwapValue.toFixed(2)})`, indicators: { vwap: vwapValue, atr: atrValue, avgVol } };
  }
  if (!wasBelow) {
    return { signal: null, reason: "Already extended above VWAP — no fresh breakout", indicators: { vwap: vwapValue, atr: atrValue, avgVol } };
  }
  if (!bigVolume) {
    return { signal: null, reason: `Volume too thin (${last.volume} vs avg ${Math.round(avgVol)})`, indicators: { vwap: vwapValue, atr: atrValue, avgVol } };
  }

  // SIGNAL FIRES — wider initial stop (1.6 ATR) so the trade has room to breathe;
  // the exit manager then moves to breakeven and trails the winner.
  const entry = last.close;
  const stopLoss = +(entry - atrValue * 1.6).toFixed(2);
  const target   = +(entry + atrValue * 6.0).toFixed(2); // far cap; trail captures most exits

  return {
    signal: "BUY",
    reason: `Price ${entry.toFixed(2)} broke above VWAP ${vwapValue.toFixed(2)} on ${(last.volume / avgVol).toFixed(1)}× avg volume`,
    entry,
    stopLoss,
    target,
    atrAtEntry: +atrValue.toFixed(2),
    indicators: {
      vwap: +vwapValue.toFixed(2),
      atr:  +atrValue.toFixed(2),
      avgVol: Math.round(avgVol),
      volumeRatio: +(last.volume / avgVol).toFixed(2),
    },
  };
}

// Polished exit — breakeven move + ATR trailing + trend-reversal + time stop.
export function shouldExit(bars, position) {
  return manageExit(bars, position);
}
