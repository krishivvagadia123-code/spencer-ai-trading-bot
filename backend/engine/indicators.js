// ─── Indicator math — pure functions, no side effects ───────────────────────
// Bar shape: { time, open, high, low, close, volume }

export function sma(bars, period, key = "close") {
  if (bars.length < period) return null;
  const slice = bars.slice(-period);
  const sum = slice.reduce((s, b) => s + b[key], 0);
  return sum / period;
}

export function ema(bars, period, key = "close") {
  if (bars.length < period) return null;
  const k = 2 / (period + 1);
  let e = bars.slice(0, period).reduce((s, b) => s + b[key], 0) / period;
  for (let i = period; i < bars.length; i++) {
    e = bars[i][key] * k + e * (1 - k);
  }
  return e;
}

export function rsi(bars, period = 14) {
  if (bars.length < period + 1) return null;
  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i++) {
    const ch = bars[i].close - bars[i - 1].close;
    if (ch >= 0) gains += ch; else losses -= ch;
  }
  let avgG = gains / period;
  let avgL = losses / period;
  for (let i = period + 1; i < bars.length; i++) {
    const ch = bars[i].close - bars[i - 1].close;
    const g = ch > 0 ? ch : 0;
    const l = ch < 0 ? -ch : 0;
    avgG = (avgG * (period - 1) + g) / period;
    avgL = (avgL * (period - 1) + l) / period;
  }
  if (avgL === 0) return 100;
  const rs = avgG / avgL;
  return 100 - 100 / (1 + rs);
}

export function atr(bars, period = 14) {
  if (bars.length < period + 1) return null;
  const trs = [];
  for (let i = 1; i < bars.length; i++) {
    const h = bars[i].high;
    const l = bars[i].low;
    const pc = bars[i - 1].close;
    const tr = Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc));
    trs.push(tr);
  }
  if (trs.length < period) return null;
  // Wilder's smoothed average
  let a = trs.slice(0, period).reduce((s, t) => s + t, 0) / period;
  for (let i = period; i < trs.length; i++) {
    a = (a * (period - 1) + trs[i]) / period;
  }
  return a;
}

// Intraday VWAP — resets at the start of each trading session
export function vwap(bars, sessionStartIdx = 0) {
  let pv = 0;
  let v = 0;
  for (let i = sessionStartIdx; i < bars.length; i++) {
    const typical = (bars[i].high + bars[i].low + bars[i].close) / 3;
    pv += typical * bars[i].volume;
    v += bars[i].volume;
  }
  return v > 0 ? pv / v : null;
}

// Average volume over the last `period` bars
export function avgVolume(bars, period) {
  if (bars.length < period) return null;
  const slice = bars.slice(-period);
  return slice.reduce((s, b) => s + b.volume, 0) / period;
}

// Find the index where the current trading session began.
// A bar marks a new session if it's the first bar at or after 09:15 IST
// (sessionMinute === 0) of a given calendar day.
export function findSessionStart(bars) {
  for (let i = bars.length - 1; i >= 0; i--) {
    if (bars[i].sessionMinute === 0) return i;
  }
  return 0;
}

// N-period high / low
export function highest(bars, period, key = "high") {
  if (bars.length < period) return null;
  const slice = bars.slice(-period);
  return Math.max(...slice.map(b => b[key]));
}
export function lowest(bars, period, key = "low") {
  if (bars.length < period) return null;
  const slice = bars.slice(-period);
  return Math.min(...slice.map(b => b[key]));
}
