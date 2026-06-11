// ─── Polished exit manager (long positions) ─────────────────────────────────
// The professional "cut losers, ride winners" exit logic:
//   1. Wide initial stop (ATR-based) so noise doesn't shake you out
//   2. Move stop to BREAKEVEN once the trade earns +1 ATR (now risk-free)
//   3. TRAIL the stop behind the peak once in profit (let winners run)
//   4. Exit on TREND REVERSAL (close back below the fast EMA after a run)
//   5. Hard target cap for outsized moves
//   6. Intraday time-stop at session end
//
// Mutates `position` to track peak / breakeven / trailing stop across bars.

import { atr, ema } from "./indicators.js";

export const DEFAULT_EXIT = {
  slMult: 1.6,          // initial stop = entry - 1.6*ATR (room to breathe)
  beTrigger: 1.0,       // move to breakeven after +1.0*ATR of peak profit
  trailMult: 2.2,       // trail 2.2*ATR behind the peak once in profit
  hardTargetMult: 6.0,  // cap target at +6*ATR
  emaExit: 9,           // exit on close below 9 EMA (only after breakeven)
  sessionEndMinute: 360, // 15:15 IST — square off intraday
};

export function manageExit(bars, position, cfg = {}) {
  const p = { ...DEFAULT_EXIT, ...cfg };
  const last = bars[bars.length - 1];
  if (!last) return { exit: false };

  const a = atr(bars, 14) || position.atrAtEntry || (position.entry * 0.01);
  const entry = position.entry;

  // Track the highest price seen since entry
  position.peakPrice = Math.max(position.peakPrice ?? entry, last.high);
  const peakGain = position.peakPrice - entry;

  // 1. Move to breakeven once enough profit banked
  if (!position.breakevenMoved && peakGain >= p.beTrigger * a) {
    position.stopLoss = Math.max(position.stopLoss, +entry.toFixed(2));
    position.breakevenMoved = true;
  }

  // 2. Trail the stop behind the peak once past breakeven (ride the winner)
  if (position.breakevenMoved) {
    const trail = position.peakPrice - p.trailMult * a;
    position.stopLoss = Math.max(position.stopLoss, +trail.toFixed(2));
  }

  // ── Exit checks (priority order) ──
  // a. Stop / trailing-stop hit
  if (last.low <= position.stopLoss) {
    return {
      exit: true,
      price: position.stopLoss,
      reason: position.breakevenMoved ? "Trailing stop hit — profit locked" : "Stop loss hit",
    };
  }

  // b. Trend reversal — only once we're in profit (don't bail on entry noise)
  if (position.breakevenMoved) {
    const fast = ema(bars, p.emaExit);
    if (fast && last.close < fast) {
      return { exit: true, price: last.close, reason: "Trend reversal — closed below 9 EMA" };
    }
  }

  // c. Hard target cap (rare, huge move)
  const hardTarget = entry + p.hardTargetMult * a;
  if (last.high >= hardTarget) {
    return { exit: true, price: +hardTarget.toFixed(2), reason: "Hard target hit" };
  }

  // d. Intraday time stop
  if (last.sessionMinute >= p.sessionEndMinute) {
    return { exit: true, price: last.close, reason: "Intraday time stop (session end)" };
  }

  return { exit: false };
}
