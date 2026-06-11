// ─── Stock analysis — real computed indicators from real Yahoo data ──────────
// Works any time (market open or closed) — analyses the latest available bars.
// Returns VWAP position, 9/21 EMA stack, RSI(14), Volume, ATR, S/R + day stats.

import * as yahoo from "./yahooClient.js";
import { vwap, ema, rsi, atr, avgVolume, findSessionStart, highest, lowest } from "./indicators.js";

const r2 = (n) => (n == null ? null : Math.round(n * 100) / 100);

export async function analyzeStock(symbol) {
  const bars = await yahoo.getHistory(symbol, { interval: "5m", range: "5d" });
  if (!bars || bars.length < 30) throw new Error(`Not enough data for ${symbol}`);
  let quote = null;
  try { quote = await yahoo.getQuote(symbol); } catch { /* fall back to bars */ }

  const last = bars[bars.length - 1];
  const sessionStart = findSessionStart(bars);
  const vwapVal = vwap(bars, sessionStart);
  const ema9 = ema(bars, 9);
  const ema21 = ema(bars, 21);
  const rsiVal = rsi(bars, 14);
  const atrVal = atr(bars, 14);
  const avgVol = avgVolume(bars, 20) || 0;
  const dayBars = bars.slice(-78); // ~1 session of 5m bars
  const support = lowest(dayBars, dayBars.length);
  const resistance = highest(dayBars, dayBars.length);

  const aboveVwap = vwapVal != null && last.close > vwapVal;
  const emaBull = ema9 != null && ema21 != null && ema9 > ema21;

  const metrics = {
    vwap: {
      value: r2(vwapVal),
      label: vwapVal == null ? "n/a" : aboveVwap ? "Above VWAP — buyers in control" : "Below VWAP — sellers in control",
      bullish: aboveVwap,
    },
    volume: {
      last: last.volume,
      avg: Math.round(avgVol),
      label: avgVol === 0 ? "n/a"
        : last.volume > avgVol * 1.5 ? `High — ${(last.volume / avgVol).toFixed(1)}× avg`
        : last.volume < avgVol * 0.7 ? "Low — below average"
        : "Normal",
      ratio: avgVol ? +(last.volume / avgVol).toFixed(2) : null,
    },
    ema: {
      ema9: r2(ema9),
      ema21: r2(ema21),
      label: ema9 == null ? "n/a" : emaBull ? "9 > 21 — bullish stack" : "9 < 21 — bearish stack",
      bullish: emaBull,
    },
    rsi: {
      value: r2(rsiVal),
      label: rsiVal == null ? "n/a"
        : rsiVal >= 70 ? "Overbought (>70)"
        : rsiVal <= 30 ? "Oversold (<30)"
        : rsiVal >= 50 ? "Bullish (50–70)"
        : "Bearish (30–50)",
    },
    atr: r2(atrVal),
    support: r2(support),
    resistance: r2(resistance),
    price: r2(quote?.price ?? last.close),
    open: r2(quote?.open),
    prevClose: r2(quote?.previousClose),
    dayHigh: r2(quote?.dayHigh),
    dayLow: r2(quote?.dayLow),
    changePct: r2(quote?.changePct),
    marketState: quote?.marketState || null,
  };

  // Simple rule-based bias (deterministic, always available even if Gemini is down)
  let bullCount = 0;
  if (metrics.vwap.bullish) bullCount++;
  if (metrics.ema.bullish) bullCount++;
  if (rsiVal != null && rsiVal >= 50 && rsiVal < 70) bullCount++;
  if (metrics.volume.ratio && metrics.volume.ratio > 1.2) bullCount++;
  const ruleBias = bullCount >= 3 ? "BULLISH" : bullCount <= 1 ? "BEARISH" : "NEUTRAL";

  return { symbol, metrics, ruleBias, asOf: last.time, fetchedAt: Date.now() };
}
