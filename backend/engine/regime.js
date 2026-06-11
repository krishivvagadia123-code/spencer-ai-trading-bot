// ─── Market regime detector ──────────────────────────────────────────────────
// Classifies the current market so the bot can run the RIGHT strategy:
//   TREND_UP / TREND_DOWN → momentum & breakout strategies work
//   RANGE                 → mean-reversion works (buy support, sell resistance)
//   VOLATILE              → stand aside / tight risk
//
// Pure math on real bars. No AI, no lookahead.

import { ema, atr, highest, lowest } from "./indicators.js";

// ADX-style trend strength via directional movement (simplified, robust)
function trendStrength(bars, period = 14) {
  if (bars.length < period + 2) return 0;
  let plusDM = 0, minusDM = 0, trSum = 0;
  for (let i = bars.length - period; i < bars.length; i++) {
    const up = bars[i].high - bars[i - 1].high;
    const down = bars[i - 1].low - bars[i].low;
    if (up > down && up > 0) plusDM += up;
    if (down > up && down > 0) minusDM += down;
    const tr = Math.max(
      bars[i].high - bars[i].low,
      Math.abs(bars[i].high - bars[i - 1].close),
      Math.abs(bars[i].low - bars[i - 1].close)
    );
    trSum += tr;
  }
  if (trSum === 0) return 0;
  const diPlus = (plusDM / trSum) * 100;
  const diMinus = (minusDM / trSum) * 100;
  const dx = Math.abs(diPlus - diMinus) / Math.max(diPlus + diMinus, 1) * 100;
  return dx; // 0..100 — higher = stronger trend
}

export function detectRegime(bars) {
  if (bars.length < 50) {
    return { regime: "RANGE", confidence: 0, reason: "Not enough bars — defaulting to RANGE" };
  }

  const ema20 = ema(bars, 20);
  const ema50 = ema(bars, 50);
  const last = bars[bars.length - 1].close;
  const a = atr(bars, 14) || 0;

  // Channel width over last 30 bars relative to price
  const hi = highest(bars.slice(-30), 30);
  const lo = lowest(bars.slice(-30), 30);
  const channelPct = ((hi - lo) / last) * 100;

  const dx = trendStrength(bars, 14);
  const emaGapPct = ema20 && ema50 ? ((ema20 - ema50) / ema50) * 100 : 0;
  const atrPct = (a / last) * 100;

  // Decision logic
  // Strong trend: high DX + EMAs separated in the same direction
  const trending = dx >= 22 && Math.abs(emaGapPct) >= 0.12;
  const veryVolatile = atrPct >= 0.9 && channelPct >= 3.5 && dx < 22;

  let regime, reason, confidence;
  if (veryVolatile) {
    regime = "VOLATILE";
    confidence = Math.min(100, Math.round(atrPct * 60));
    reason = `High volatility (ATR ${atrPct.toFixed(2)}%, channel ${channelPct.toFixed(1)}%) without clear direction`;
  } else if (trending && emaGapPct > 0) {
    regime = "TREND_UP";
    confidence = Math.min(100, Math.round(dx * 2.5));
    reason = `Uptrend: DX ${dx.toFixed(0)}, EMA20 ${emaGapPct.toFixed(2)}% above EMA50`;
  } else if (trending && emaGapPct < 0) {
    regime = "TREND_DOWN";
    confidence = Math.min(100, Math.round(dx * 2.5));
    reason = `Downtrend: DX ${dx.toFixed(0)}, EMA20 ${emaGapPct.toFixed(2)}% below EMA50`;
  } else {
    regime = "RANGE";
    confidence = Math.min(100, Math.round((30 - dx) * 3));
    reason = `Range-bound: DX ${dx.toFixed(0)} (weak trend), price oscillating in ${channelPct.toFixed(1)}% channel`;
  }

  return {
    regime,
    confidence,
    reason,
    metrics: {
      dx: +dx.toFixed(1),
      emaGapPct: +emaGapPct.toFixed(2),
      atrPct: +atrPct.toFixed(2),
      channelPct: +channelPct.toFixed(1),
    },
  };
}

// Which strategy id fits a regime (used by the bot's auto-selector)
export function strategyForRegime(regime) {
  switch (regime) {
    case "TREND_UP":   return "vwap_breakout";   // momentum/breakout in uptrends
    case "TREND_DOWN": return null;              // long-only bot stands aside in downtrends
    case "RANGE":      return "mean_reversion";  // buy support / sell resistance
    case "VOLATILE":   return null;              // stand aside
    default:           return "vwap_breakout";
  }
}
