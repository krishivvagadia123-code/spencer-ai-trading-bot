// ─── Backtest harness ────────────────────────────────────────────────────────
// Runs a strategy over real Yahoo history bar-by-bar (no lookahead) and reports
// honest aggregate stats. Used to validate exit logic before trusting the bot.

import * as yahoo from "./yahooClient.js";
import { getStrategy } from "./strategies/index.js";

export async function runBacktest({
  symbol = "RELIANCE",
  interval = "5m",
  range = "60d",
  strategyId = "vwap_breakout",
  budget = 5000,
  warmup = 120,
  minBarsBetweenTrades = 5,
} = {}) {
  const raw = await yahoo.getHistory(symbol, { interval, range }); // already sessionMinute-annotated
  if (!raw || raw.length < warmup + 20) {
    throw new Error(`Not enough bars for ${symbol} (${raw?.length || 0})`);
  }
  const strategy = getStrategy(strategyId);

  let cash = budget;
  let position = null;
  let lastExitIdx = -Infinity;
  const trades = [];
  const equityCurve = [];

  for (let i = warmup; i < raw.length; i++) {
    const bars = raw.slice(0, i + 1);
    const last = bars[bars.length - 1];

    if (position) {
      const ex = strategy.shouldExit(bars, position);
      if (ex.exit) {
        const pnl = (ex.price - position.entry) * position.qty;
        cash += ex.price * position.qty;
        trades.push({
          entry: position.entry, exit: ex.price, qty: position.qty,
          pnl: +pnl.toFixed(2),
          pnlPct: +(((ex.price - position.entry) / position.entry) * 100).toFixed(2),
          bars: i - position.openIdx,
          reason: ex.reason,
          openedAt: position.openedAt, closedAt: last.time,
        });
        position = null;
        lastExitIdx = i;
      }
    } else if (i - lastExitIdx >= minBarsBetweenTrades) {
      const sig = strategy.evaluate(bars);
      if (sig.signal === "BUY") {
        const qty = Math.max(1, Math.floor((cash * 0.95) / sig.entry));
        if (qty * sig.entry <= cash) {
          cash -= qty * sig.entry;
          position = {
            entry: sig.entry, qty, stopLoss: sig.stopLoss, target: sig.target,
            atrAtEntry: sig.atrAtEntry, peakPrice: sig.entry, breakevenMoved: false,
            openedAt: last.time, openIdx: i,
          };
        }
      }
    }

    // mark-to-market equity
    const mtm = position ? cash + position.qty * last.close : cash;
    equityCurve.push(mtm);
  }

  // Close any dangling position at the last price
  if (position) {
    const last = raw[raw.length - 1];
    const pnl = (last.close - position.entry) * position.qty;
    cash += last.close * position.qty;
    trades.push({
      entry: position.entry, exit: last.close, qty: position.qty,
      pnl: +pnl.toFixed(2),
      pnlPct: +(((last.close - position.entry) / position.entry) * 100).toFixed(2),
      reason: "Backtest end", openedAt: position.openedAt, closedAt: last.time,
    });
  }

  // ── Stats ──
  const wins = trades.filter(t => t.pnl > 0);
  const losses = trades.filter(t => t.pnl <= 0);
  const netPnl = trades.reduce((s, t) => s + t.pnl, 0);
  const grossWin = wins.reduce((s, t) => s + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnl, 0));
  const winRate = trades.length ? (wins.length / trades.length) * 100 : 0;
  const avgWin = wins.length ? grossWin / wins.length : 0;
  const avgLoss = losses.length ? grossLoss / losses.length : 0;
  const expectancy = trades.length ? netPnl / trades.length : 0;
  const profitFactor = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0);
  const avgHold = trades.length ? trades.reduce((s, t) => s + (t.bars || 0), 0) / trades.length : 0;

  // Max drawdown from equity curve
  let peak = -Infinity, maxDd = 0;
  for (const eq of equityCurve) {
    if (eq > peak) peak = eq;
    const dd = peak - eq;
    if (dd > maxDd) maxDd = dd;
  }

  return {
    symbol, interval, range, strategy: strategy.meta.name, budget,
    barsTested: raw.length - warmup,
    period: { from: raw[warmup]?.time, to: raw[raw.length - 1]?.time },
    trades: trades.length,
    wins: wins.length,
    losses: losses.length,
    winRate: +winRate.toFixed(1),
    netPnl: +netPnl.toFixed(2),
    netPnlPct: +((netPnl / budget) * 100).toFixed(2),
    avgWin: +avgWin.toFixed(2),
    avgLoss: +avgLoss.toFixed(2),
    expectancy: +expectancy.toFixed(2),
    profitFactor: profitFactor === Infinity ? "∞" : +profitFactor.toFixed(2),
    avgHoldBars: +avgHold.toFixed(1),
    maxDrawdown: +maxDd.toFixed(2),
    finalEquity: +cash.toFixed(2),
    sampleTrades: trades.slice(-8),
  };
}
