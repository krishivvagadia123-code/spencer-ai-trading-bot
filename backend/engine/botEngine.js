// ─── Bot Engine ──────────────────────────────────────────────────────────────
// The minute-by-minute loop:
//   1. Append a new bar to the chart
//   2. If a position is open → check stop/target/time-stop → maybe close
//   3. If no position → evaluate active strategy → maybe enter
//   4. Update P&L, holdings, activity log

import { generateHistory, generateNextBar } from "./priceSimulator.js";
import { ALL_STRATEGIES, getStrategy } from "./strategies/index.js";
import * as kite from "./kiteClient.js";
import * as yahoo from "./yahooClient.js";

const SYMBOL = process.env.BOT_SYMBOL || "RELIANCE";
const BUDGET = Number(process.env.BOT_BUDGET || 5000);
const TICK_INTERVAL_MS = Number(process.env.TICK_INTERVAL_MS || 60000);
const MIN_BARS_BETWEEN_TRADES = Number(process.env.MIN_BARS_BETWEEN_TRADES || 5);
// Real-data config: intraday bars for training. Yahoo supports 5m/15m up to 60d.
const BOT_INTERVAL = process.env.BOT_INTERVAL || "5m";
const BOT_RANGE = process.env.BOT_RANGE || "60d";
const REPLAY_WARMUP = Number(process.env.REPLAY_WARMUP || 120); // lookback before first decision
// Learning phase: trigger after 5 losses in a row, pause new entries 20 min
const LEARNING_PAUSE_MS = Number(process.env.LEARNING_PAUSE_MS || 20 * 60 * 1000);
const STREAK_TARGET = 5;

// NSE session opens 09:15 IST = 03:45 UTC = minute 225 of the UTC day.
function annotateSessionMinute(bars) {
  const OPEN_UTC_MIN = 3 * 60 + 45;
  for (const b of bars) {
    const d = new Date(b.time);
    const utcMin = d.getUTCHours() * 60 + d.getUTCMinutes();
    b.sessionMinute = Math.max(0, utcMin - OPEN_UTC_MIN);
  }
  return bars;
}

// Safety defaults:
// - This engine currently uses synthetic candles, not live NSE candles.
// - Gemini is available through the backend chat route, but not wired into execution approval yet.
// So autonomous trading stays blocked unless a developer explicitly opts into demo mode.
const ALLOW_SIMULATED_TRADING = process.env.ALLOW_SIMULATED_TRADING === "true";
const ALLOW_RULE_ONLY_TRADING = process.env.ALLOW_RULE_ONLY_TRADING === "true";

// ─── In-memory state — gets persisted by server.js ───────────────────────────
export const state = {
  running: false,
  symbol: SYMBOL,
  budget: BUDGET,
  cash: BUDGET,
  bars: [],
  activeStrategyId: ALL_STRATEGIES[0].meta.id,
  openPosition: null,
  holdings: [],
  orders: [],
  activity: [],
  trades: [],
  botWatching: null,
  strategyStats: {},
  equitySamples: [],   // [{ t, v }] total-value over time for the performance chart
  winStreak: 0,        // consecutive wins (5 → advance phase)
  lossStreak: 0,       // consecutive losses (5 → trigger learning phase)
  phase: 1,            // bot development phase, advances every 5-win streak
  learningUntil: null, // timestamp; bot pauses entries while < this
  lastLesson: null,    // { triggeredAt, lossSummary, takeaways }
  startedAt: null,
  lastTickAt: null,
  totalBarsEmitted: 0,
  lastExitBarIndex: null,
  guardStatus: { ok: false, issues: [] },
};

let tickHandle = null;

// Initialize stats for every strategy
function initStrategyStats() {
  for (const s of ALL_STRATEGIES) {
    if (!state.strategyStats[s.meta.id]) {
      state.strategyStats[s.meta.id] = {
        id: s.meta.id,
        name: s.meta.name,
        wins: 0,
        losses: 0,
        totalPnl: 0,
        trades: 0,
        winRate: 0,
        status: s.meta.id === state.activeStrategyId ? "Testing" : "Queued",
      };
    }
  }
}

function logActivity(kind, message) {
  const entry = {
    time: new Date().toISOString(),
    kind,
    message,
  };
  state.activity.unshift(entry);
  if (state.activity.length > 100) state.activity.length = 100;
}

function tradingGate() {
  const kiteStatus = kite.status();
  const issues = [];

  if (!ALLOW_SIMULATED_TRADING) {
    issues.push("Synthetic RELIANCE demo trading is disabled. Real NSE candle execution is not wired into the engine yet.");
  }
  if (!ALLOW_RULE_ONLY_TRADING) {
    issues.push("Rule-only auto trading is disabled. Gemini approval is not wired into the execution loop yet.");
  }

  return {
    ok: issues.length === 0,
    issues,
    dataSource: ALLOW_SIMULATED_TRADING ? "synthetic-demo" : "blocked",
    kiteConfigured: kiteStatus.configured,
    kiteConnected: kiteStatus.connected,
    aiApprovalWired: false,
    ruleOnlyTradingAllowed: ALLOW_RULE_ONLY_TRADING,
    simulatedTradingAllowed: ALLOW_SIMULATED_TRADING,
  };
}

function setGuardStatus() {
  state.guardStatus = tradingGate();
  return state.guardStatus;
}

// ─── Initialize chart history on first start — REAL Yahoo data ───────────────
export async function seedChart() {
  if (state.fullHistory && state.fullHistory.length > 0) return;
  try {
    const raw = await yahoo.getHistory(SYMBOL, { interval: BOT_INTERVAL, range: BOT_RANGE });
    if (!raw || raw.length < REPLAY_WARMUP + 10) {
      throw new Error(`only ${raw?.length || 0} bars returned`);
    }
    annotateSessionMinute(raw);
    state.fullHistory = raw;                       // complete real dataset
    state.replayIndex = Math.min(REPLAY_WARMUP, raw.length - 1);
    state.bars = raw.slice(0, state.replayIndex);  // what the strategy "knows so far" (no lookahead)
    state.replayDone = false;
    state.dataSource = "yahoo-replay";
    state.totalBarsEmitted = state.replayIndex;
    logActivity("scan", `Loaded ${raw.length} REAL ${SYMBOL} ${BOT_INTERVAL} bars from Yahoo — replaying ${raw.length - state.replayIndex} bars to train`);
  } catch (e) {
    // Yahoo failed → synthetic fallback so the bot still runs
    state.bars = generateHistory({ symbol: SYMBOL, historyDays: 60, seed: 42, now: Date.now() });
    state.fullHistory = null;
    state.replayDone = true;
    state.dataSource = "synthetic-fallback";
    state.totalBarsEmitted = state.bars.length;
    logActivity("risk", `Yahoo history unavailable (${e.message}) — using synthetic fallback`);
  }
  initStrategyStats();
}

// ─── Tick (called every TICK_INTERVAL_MS) ────────────────────────────────────
let tickBusy = false;
let sampleCounter = 0;
export async function tick() {
  if (!state.running || tickBusy) return;
  tickBusy = true;
  try {
    await advanceBar();
    runStrategyCycle();
    // Sample total equity for the performance chart (every few ticks, capped)
    sampleCounter++;
    if (sampleCounter % 3 === 0) {
      const cur = state.bars[state.bars.length - 1]?.close || 0;
      const mtm = state.cash + state.holdings.reduce((s, h) => s + h.qty * cur, 0);
      if (!state.equitySamples) state.equitySamples = [];
      state.equitySamples.push({ t: Date.now(), v: +mtm.toFixed(2) });
      if (state.equitySamples.length > 250) state.equitySamples = state.equitySamples.slice(-250);
    }
  } finally {
    tickBusy = false;
  }
}

// Advance the chart by one bar — REPLAY real history, then LIVE, then synthetic fallback
async function advanceBar() {
  state.lastTickAt = Date.now();

  if (state.fullHistory && !state.replayDone) {
    // REPLAY: reveal the next real historical bar (strategy never sees the future)
    if (state.replayIndex < state.fullHistory.length) {
      state.replayIndex++;
      state.bars = state.fullHistory.slice(0, state.replayIndex);
      state.totalBarsEmitted = state.replayIndex;
    }
    if (state.replayIndex >= state.fullHistory.length) {
      state.replayDone = true;
      state.dataSource = "yahoo-live";
      logActivity("scan", "Replay of real history complete — now tracking LIVE Yahoo bars");
    }
    return;
  }

  if (state.fullHistory && state.replayDone) {
    // LIVE: pull the newest real intraday bar from Yahoo (only changes during market hours)
    try {
      const recent = await yahoo.getHistory(SYMBOL, { interval: BOT_INTERVAL, range: "1d" });
      if (recent && recent.length) {
        annotateSessionMinute(recent);
        const latest = recent[recent.length - 1];
        const last = state.bars[state.bars.length - 1];
        if (!last || latest.time !== last.time) {
          state.bars.push(latest);
          state.fullHistory.push(latest);
          state.totalBarsEmitted++;
          if (state.bars.length > 3000) state.bars = state.bars.slice(-3000);
        }
      }
    } catch { /* market closed / fetch failed — keep last bar */ }
    return;
  }

  // SYNTHETIC FALLBACK (Yahoo was unavailable at seed time)
  const prev = state.bars[state.bars.length - 1];
  const nextSessionMinute = (prev.sessionMinute + 1) % 375;
  const nextBar = generateNextBar(prev, nextSessionMinute, (Date.now() & 0xffff) ^ state.totalBarsEmitted);
  state.bars.push(nextBar);
  state.totalBarsEmitted++;
  if (state.bars.length > 1500) state.bars = state.bars.slice(-1500);
}

function runStrategyCycle() {
  const strategy = getStrategy(state.activeStrategyId);
  if (!strategy) return;

  const gate = setGuardStatus();
  if (!gate.ok) {
    state.running = false;
    if (tickHandle) {
      clearInterval(tickHandle);
      tickHandle = null;
    }
    logActivity("risk", "Trading paused: " + gate.issues.join(" "));
    return;
  }

  // 2. Position management — exit logic if a position is open
  if (state.openPosition) {
    const exitCheck = strategy.shouldExit(state.bars, state.openPosition);
    if (exitCheck.exit) {
      closePosition(exitCheck.price, exitCheck.reason);
    }
  } else {
    // 3. Entry logic — only one position at a time
    // Skip entries while in learning phase (post-5-loss cooldown)
    if (state.learningUntil) {
      if (Date.now() < state.learningUntil) return;
      // Just exited the learning window
      state.learningUntil = null;
      logActivity("scan", "🧠 Learning phase complete — resuming entries with what was observed");
    }
    const barsSinceExit = state.lastExitBarIndex == null ? Infinity : state.totalBarsEmitted - state.lastExitBarIndex;
    if (barsSinceExit < MIN_BARS_BETWEEN_TRADES) {
      return;
    }
    const result = strategy.evaluate(state.bars);
    if (result.signal === "BUY") {
      openPosition(result, strategy.meta);
    } else if (Math.random() < 0.05) {
      // Sparse scan logging
      logActivity("scan", `${strategy.meta.name}: ${result.reason}`);
    }
  }

  // 4. Update mark-to-market on holdings using the latest bar's close
  const currentBar = state.bars[state.bars.length - 1];
  if (currentBar) {
    for (const h of state.holdings) {
      h.ltp = currentBar.close;
    }
  }
}

function openPosition(signal, strategyMeta) {
  const entry = signal.entry;
  // Position sizing — never deploy more than (cash * 0.95)
  const maxSpend = state.cash * 0.95;
  if (maxSpend < entry) {
    logActivity("risk", `BLOCKED entry: insufficient cash (need ≥ ₹${entry.toFixed(2)}, have ₹${state.cash.toFixed(2)})`);
    return;
  }
  const qty = Math.max(1, Math.floor(maxSpend / entry));
  const spend = qty * entry;
  state.cash -= spend;

  const position = {
    id: `t-${Date.now()}`,
    symbol: SYMBOL,
    side: "BUY",
    qty,
    entry,
    stopLoss: signal.stopLoss,
    target: signal.target,
    atrAtEntry: signal.atrAtEntry || null,  // for the trailing exit manager
    peakPrice: entry,                        // tracks the high-water mark
    breakevenMoved: false,
    strategy: strategyMeta.name,
    strategyId: strategyMeta.id,
    openedAt: new Date().toISOString(),
    reason: signal.reason,
    indicators: signal.indicators,
  };
  state.openPosition = position;

  // Push to holdings
  state.holdings = [{
    symbol: SYMBOL,
    qty,
    avg: entry,
    ltp: entry,
    sector: "—",
  }];

  // Push to order book
  state.orders.unshift({
    id: position.id,
    time: timeStr(),
    symbol: SYMBOL,
    side: "BUY",
    qty,
    price: entry,
    status: "COMPLETE",
    strategy: strategyMeta.name,
  });
  if (state.orders.length > 50) state.orders.length = 50;

  logActivity("trade", `BUY ${qty} ${SYMBOL} @ ₹${entry.toFixed(2)} · SL ₹${signal.stopLoss} TP ₹${signal.target} · ${signal.reason}`);
}

function closePosition(exitPrice, reason) {
  const p = state.openPosition;
  if (!p) return;
  const proceeds = exitPrice * p.qty;
  const pnl = (exitPrice - p.entry) * p.qty;
  const pnlPct = ((exitPrice - p.entry) / p.entry) * 100;
  state.cash += proceeds;

  // Update strategy stats
  const stats = state.strategyStats[p.strategyId];
  if (stats) {
    stats.trades++;
    stats.totalPnl += pnl;
    if (pnl > 0) stats.wins++; else stats.losses++;
    stats.winRate = stats.trades > 0 ? +(stats.wins / stats.trades * 100).toFixed(1) : 0;
  }

  // Record completed trade
  const trade = {
    id: p.id,
    symbol: SYMBOL,
    strategy: p.strategy,
    strategyId: p.strategyId,
    side: "BUY",
    qty: p.qty,
    entry: p.entry,
    exit: exitPrice,
    stopLoss: p.stopLoss,
    target: p.target,
    openedAt: p.openedAt,
    closedAt: new Date().toISOString(),
    pnl: +pnl.toFixed(2),
    pnlPct: +pnlPct.toFixed(2),
    exitReason: reason,
    entryReason: p.reason,
    indicators: p.indicators,
    outcome: pnl > 0 ? "WIN" : "LOSS",
  };
  state.trades.unshift(trade);
  if (state.trades.length > 100) state.trades.length = 100;

  // Push sell to order book
  state.orders.unshift({
    id: `${p.id}-exit`,
    time: timeStr(),
    symbol: SYMBOL,
    side: "SELL",
    qty: p.qty,
    price: exitPrice,
    status: "COMPLETE",
    strategy: p.strategy,
  });

  // Holdings cleared (single-position model)
  state.holdings = [];
  state.openPosition = null;
  state.lastExitBarIndex = state.totalBarsEmitted;

  logActivity(pnl >= 0 ? "win" : "loss",
    `SOLD ${p.qty} ${SYMBOL} @ ₹${exitPrice.toFixed(2)} · ${pnl >= 0 ? "+" : ""}₹${pnl.toFixed(2)} (${pnlPct.toFixed(2)}%) · ${reason}`);

  // ─── Win/loss streak + phase advancement + learning trigger ───
  if (pnl > 0) {
    state.winStreak = (state.winStreak || 0) + 1;
    state.lossStreak = 0;
    if (state.winStreak >= STREAK_TARGET) {
      state.phase = (state.phase || 1) + 1;
      state.winStreak = 0;
      logActivity("scan", `★ ${STREAK_TARGET} wins in a row — advanced to phase ${state.phase}`);
    }
  } else {
    state.lossStreak = (state.lossStreak || 0) + 1;
    state.winStreak = 0;
    if (state.lossStreak >= STREAK_TARGET) {
      triggerLearningPhase();
      state.lossStreak = 0;
    }
  }
}

// Build a deterministic "lesson" from the last 5 losing trades and pause
// new entries for LEARNING_PAUSE_MS. Honest, data-driven, no fake AI claim.
function triggerLearningPhase() {
  const lastLosses = state.trades.filter(t => t.outcome === "LOSS").slice(0, STREAK_TARGET);
  const reasons = {};
  let avgBars = 0;
  let avgLossPct = 0;
  for (const t of lastLosses) {
    reasons[t.exitReason] = (reasons[t.exitReason] || 0) + 1;
    avgBars += (t.bars || 0);
    avgLossPct += t.pnlPct || 0;
  }
  const n = Math.max(lastLosses.length, 1);
  avgBars = +(avgBars / n).toFixed(1);
  avgLossPct = +(avgLossPct / n).toFixed(2);
  const topReason = Object.entries(reasons).sort((a, b) => b[1] - a[1])[0];
  const takeaways = [];
  if (topReason && topReason[0].includes("Stop loss")) {
    takeaways.push("Most exits were stop-losses — entries triggered into reversals (likely false breakouts).");
  }
  if (avgBars <= 2) {
    takeaways.push(`Avg hold was only ${avgBars} bars — the strategy is firing in choppy conditions, not trending ones.`);
  }
  if (avgLossPct < -0.3) {
    takeaways.push(`Avg loss ${avgLossPct}% — initial stop may be too wide for current volatility.`);
  }
  if (takeaways.length === 0) {
    takeaways.push("Pattern unclear from data alone — will resume and re-evaluate after the cooldown.");
  }

  state.learningUntil = Date.now() + LEARNING_PAUSE_MS;
  state.lastLesson = {
    triggeredAt: new Date().toISOString(),
    losses: n,
    avgBars,
    avgLossPct,
    topReason: topReason ? `${topReason[0]} (${topReason[1]}/${n})` : "unknown",
    takeaways,
  };
  const mins = Math.round(LEARNING_PAUSE_MS / 60000);
  logActivity("risk", `🧠 LEARNING PHASE — ${STREAK_TARGET} losses in a row. Pausing entries ${mins} min. ${takeaways[0]}`);
}

function timeStr() {
  const d = new Date();
  return d.toTimeString().slice(0, 8);
}

// ─── Public lifecycle controls ───────────────────────────────────────────────
export async function start() {
  if (state.running && tickHandle) {
    return { ok: true, running: true, alreadyRunning: true, guard: setGuardStatus() };
  }
  if (state.running && !tickHandle) {
    state.running = false;
    logActivity("risk", "Recovered stale running state after backend restart; running preflight again.");
  }

  const gate = setGuardStatus();
  if (!gate.ok) {
    state.running = false;
    const reason = gate.issues.join(" ");
    logActivity("risk", "Trading blocked: " + reason);
    return { ok: false, running: false, alreadyRunning: false, reason, guard: gate };
  }

  await seedChart(); // fetch real Yahoo history (idempotent)
  state.running = true;
  state.startedAt = state.startedAt || new Date().toISOString();
  logActivity("scan", `Bot started on ${state.dataSource || "data"} - active strategy: ` + getStrategy(state.activeStrategyId).meta.name);
  if (tickHandle) clearInterval(tickHandle);
  tickHandle = setInterval(() => { tick(); }, TICK_INTERVAL_MS);
  setTimeout(() => { tick(); }, 200);
  return { ok: true, running: true, alreadyRunning: false, guard: gate };
}

export function stop() {
  state.running = false;
  if (tickHandle) {
    clearInterval(tickHandle);
    tickHandle = null;
  }
  logActivity("scan", "Bot stopped");
}

export function reset() {
  stop();
  state.bars = [];
  state.fullHistory = null;
  state.replayIndex = 0;
  state.replayDone = false;
  state.dataSource = null;
  state.equitySamples = [];
  state.winStreak = 0;
  state.lossStreak = 0;
  state.phase = 1;
  state.learningUntil = null;
  state.lastLesson = null;
  state.cash = state.budget;          // reset to whatever the configured budget is
  state.openPosition = null;
  state.holdings = [];
  state.orders = [];
  state.activity = [];
  state.trades = [];
  state.botWatching = null;
  state.strategyStats = {};
  state.totalBarsEmitted = 0;
  state.lastExitBarIndex = null;
  state.guardStatus = setGuardStatus();
  state.startedAt = null;
  logActivity("scan", "Bot state reset");
}

// Set the trading budget (from the user's onboarding choice). Enforces
// min ₹5,000 / max ₹1 crore. When the bot is flat (no open position),
// cash is re-synced to the new budget so the dashboard is consistent.
const MIN_BUDGET = 5000;
const MAX_BUDGET = 10000000;
export function configure({ budget, symbol } = {}) {
  if (budget != null) {
    const b = Number(budget);
    if (!Number.isFinite(b) || b < MIN_BUDGET) {
      return { ok: false, error: `Budget must be at least ₹${MIN_BUDGET.toLocaleString("en-IN")}` };
    }
    state.budget = Math.min(b, MAX_BUDGET);
    // ONLY initialize cash when the bot has never traded (truly fresh start).
    // A routine config push / page refresh must NEVER wipe accumulated P&L.
    const neverTraded = (state.trades?.length || 0) === 0 && !state.openPosition && state.holdings.length === 0;
    if (neverTraded) {
      state.cash = state.budget;
    }
  }
  if (symbol) state.symbol = String(symbol).toUpperCase();
  return { ok: true, budget: state.budget, symbol: state.symbol };
}

// ─── Public read-only state snapshot for the frontend ────────────────────────
export function snapshot() {
  const last = state.bars[state.bars.length - 1];
  const invested = state.holdings.reduce((s, h) => s + h.qty * h.avg, 0);
  const currentValue = state.holdings.reduce((s, h) => s + h.qty * h.ltp, 0);
  const totalValue = state.cash + currentValue;
  const totalPnl = totalValue - state.budget;
  const unrealisedPnl = currentValue - invested;
  const realisedPnl = totalPnl - unrealisedPnl;
  const allStats = Object.values(state.strategyStats || {});
  const totalClosedTrades = allStats.reduce((sum, s) => sum + (s.trades || 0), 0) || state.trades.length;
  const totalWins = allStats.reduce((sum, s) => sum + (s.wins || 0), 0) || state.trades.filter(t => t.pnl > 0).length;
  const totalLosses = allStats.reduce((sum, s) => sum + (s.losses || 0), 0) || Math.max(0, totalClosedTrades - totalWins);
  const guardStatus = setGuardStatus();

  const activeMeta = getStrategy(state.activeStrategyId).meta;
  const stats = state.strategyStats[state.activeStrategyId];

  return {
    running: state.running,
    symbol: state.symbol,
    startedAt: state.startedAt,
    lastTickAt: state.lastTickAt,
    dataSource: state.dataSource || (state.fullHistory ? "yahoo" : "synthetic"),
    replay: state.fullHistory ? {
      done: !!state.replayDone,
      index: state.replayIndex || 0,
      total: state.fullHistory.length,
    } : null,
    capital: {
      budget: state.budget,
      cash: +state.cash.toFixed(2),
      invested: +invested.toFixed(2),
      currentValue: +currentValue.toFixed(2),
      totalValue: +totalValue.toFixed(2),
      unrealisedPnl: +unrealisedPnl.toFixed(2),
      realisedPnl: +realisedPnl.toFixed(2),
      totalPnl: +totalPnl.toFixed(2),
      pnlPct: state.budget > 0 ? +(totalPnl / state.budget * 100).toFixed(2) : 0,
      unrealisedPnlPct: invested > 0 ? +(unrealisedPnl / invested * 100).toFixed(2) : 0,
    },
    metrics: {
      closedTrades: totalClosedTrades,
      wins: totalWins,
      losses: totalLosses,
      winRate: totalClosedTrades > 0 ? +(totalWins / totalClosedTrades * 100).toFixed(1) : 0,
    },
    equitySamples: state.equitySamples || [],
    streak: {
      wins: state.winStreak || 0,
      losses: state.lossStreak || 0,
      target: STREAK_TARGET,
      phase: state.phase || 1,
    },
    learning: state.learningUntil ? {
      until: state.learningUntil,
      remainingMs: Math.max(0, state.learningUntil - Date.now()),
      lesson: state.lastLesson,
    } : null,
    lastLesson: state.lastLesson || null,
    guardStatus,
    activeStrategy: {
      id: activeMeta.id,
      name: activeMeta.name,
      type: activeMeta.type,
      wins: stats?.wins || 0,
      losses: stats?.losses || 0,
      trades: stats?.trades || 0,
      totalPnl: +(stats?.totalPnl || 0).toFixed(2),
      winRate: stats?.winRate || 0,
    },
    openPosition: state.openPosition,
    holdings: state.holdings,
    orders: state.orders.slice(0, 25),
    activity: state.activity.slice(0, 30),
    trades: state.trades.slice(0, 25),
    strategyStats: Object.values(state.strategyStats),
    price: last ? {
      symbol: state.symbol,
      current: last.close,
      high: last.high,
      low: last.low,
      time: last.time,
      sessionMinute: last.sessionMinute,
    } : null,
    chartTail: state.bars.slice(-100), // last 100 bars for chart
  };
}

export function loadFromSnapshot(s) {
  if (!s) return;
  Object.assign(state, s);
}
