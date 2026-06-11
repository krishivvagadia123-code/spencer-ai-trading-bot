// ─── Spencer AI bot backend ──────────────────────────────────────────────────
// Express server + 1-min bot loop. Frontend polls /api/bot/state every 5s.

import "dotenv/config";
import express from "express";
import cors from "cors";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  state, start, stop, reset, tick, snapshot, loadFromSnapshot, configure,
} from "./engine/botEngine.js";
import { strategyList, getStrategy } from "./engine/strategies/index.js";
import * as kite from "./engine/kiteClient.js";
import * as yahoo from "./engine/yahooClient.js";
import { runBacktest } from "./engine/backtest.js";
import { analyzeStock } from "./engine/analysis.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 8787);
const STATE_FILE = path.join(__dirname, "state", "state.json");
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || "";
// Try models in order — if one is overloaded (503), fall back to the next.
const GEMINI_MODELS = (process.env.GEMINI_MODEL || "gemini-2.5-flash,gemini-2.0-flash,gemini-flash-latest")
  .split(",").map(m => m.trim()).filter(Boolean);

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function callGeminiModel(model, prompt, { temperature, maxOutputTokens }) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(GEMINI_API_KEY)}`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { temperature, maxOutputTokens, topP: 0.9 },
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(data?.error?.message || `Gemini request failed (${response.status})`);
    err.status = response.status;
    throw err;
  }
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
  if (!text) { const e = new Error("Gemini returned an empty response"); e.status = 502; throw e; }
  return text;
}

async function callGemini(prompt, { temperature = 0.3, maxOutputTokens = 600 } = {}) {
  if (!GEMINI_API_KEY) {
    return { ok: false, status: 500, error: "GEMINI_API_KEY is missing in backend/.env" };
  }
  let lastErr = null;
  for (const model of GEMINI_MODELS) {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const text = await callGeminiModel(model, prompt, { temperature, maxOutputTokens });
        return { ok: true, text, model };
      } catch (e) {
        lastErr = e;
        // Retry the same model once on overload/rate-limit, else move to next model
        if ((e.status === 503 || e.status === 429) && attempt === 0) {
          await sleep(900);
          continue;
        }
        break; // try next model
      }
    }
  }
  return { ok: false, status: lastErr?.status || 502, error: lastErr?.message || "All Gemini models failed" };
}

// ─── Persistence ─────────────────────────────────────────────────────────────
function saveState() {
  try {
    // Don't persist the chart or replay buffer (too big) — refetched on restart
    const { bars, fullHistory, ...persistable } = state;
    fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
    fs.writeFileSync(STATE_FILE, JSON.stringify(persistable, null, 2));
  } catch (e) {
    console.warn("[persist] save failed:", e.message);
  }
}
function restoreState() {
  try {
    if (!fs.existsSync(STATE_FILE)) return;
    const raw = JSON.parse(fs.readFileSync(STATE_FILE, "utf-8"));
    loadFromSnapshot(raw);
    if (state.running) {
      state.running = false;
      console.log("[persist] restored prior state; bot marked stopped until preflight passes");
    } else {
      console.log("[persist] restored prior state");
    }
  } catch (e) {
    console.warn("[persist] restore failed:", e.message);
  }
}

// Persist every 30s while running
setInterval(() => { if (state.running) saveState(); }, 30000);
restoreState();

// Restore any saved Kite session (daily token may still be valid)
if (kite.isConfigured()) {
  const ok = kite.restoreSession();
  console.log(`[kite] configured · session ${ok ? "restored" : "needs login"}`);
} else {
  console.log("[kite] not configured (set KITE_API_KEY / KITE_API_SECRET in .env to enable)");
}

// ─── Express app ─────────────────────────────────────────────────────────────
const app = express();
app.use(cors({ origin: true, credentials: true }));
app.use(express.json());

// Pull candidate NSE symbols out of a chat prompt (all-caps tokens, 2-15 chars)
function extractSymbols(text) {
  const matches = String(text).toUpperCase().match(/\b[A-Z][A-Z&-]{1,14}\b/g) || [];
  // Filter out common English words that look like tickers
  const stop = new Set(["THE","AND","FOR","WAS","ARE","WHAT","WHEN","HOW","WHY","BUY","SELL","AI","NSE","BSE","STOCK","PRICE","TODAY","NOW","SL","TP","BTST","P&L","PNL","RSI","VWAP","EMA","ATR"]);
  return [...new Set(matches.filter(m => !stop.has(m)))].slice(0, 5);
}

// Fetch real quotes for symbols mentioned + the bot's active symbol, build a
// data block the model MUST use (and forbid it from inventing prices).
async function buildRealDataContext(prompt) {
  const candidates = new Set(extractSymbols(prompt));
  if (state.symbol) candidates.add(state.symbol.toUpperCase());
  const symbols = [...candidates].slice(0, 6);
  if (symbols.length === 0) return "";

  const quotes = await yahoo.getQuotes(symbols);
  const lines = [];
  for (const s of symbols) {
    const q = quotes[s];
    if (q && q.price != null) {
      lines.push(
        `${s}: ₹${q.price.toFixed(2)} (prev close ₹${q.previousClose?.toFixed(2) ?? "n/a"}, ` +
        `${q.changePct >= 0 ? "+" : ""}${q.changePct?.toFixed(2) ?? "n/a"}% today, ` +
        `day H ₹${q.dayHigh?.toFixed(2) ?? "n/a"} / L ₹${q.dayLow?.toFixed(2) ?? "n/a"}, ` +
        `52w H ₹${q.fiftyTwoWeekHigh?.toFixed(2) ?? "n/a"} / L ₹${q.fiftyTwoWeekLow?.toFixed(2) ?? "n/a"}, ` +
        `market ${q.marketState || "?"}, source Yahoo, ~15min delayed)`
      );
    }
  }
  if (lines.length === 0) return "";
  return `REAL-TIME MARKET DATA (the ONLY source of truth for prices):\n${lines.join("\n")}\n`;
}

app.post("/api/ai/chat", async (req, res) => {
  const { prompt, temperature = 0.3, maxOutputTokens = 600 } = req.body || {};
  if (!prompt || typeof prompt !== "string") {
    return res.status(400).json({ ok: false, error: "Prompt is required" });
  }

  // Inject real prices so the model never has to guess
  let dataBlock = "";
  try { dataBlock = await buildRealDataContext(prompt); } catch { /* non-fatal */ }

  const guard =
    "STRICT RULES:\n" +
    "1. For ANY stock price, you MUST use ONLY the numbers in REAL-TIME MARKET DATA below. " +
    "NEVER invent, estimate, or recall a price from memory.\n" +
    "2. If a price the user asks about is NOT in the data block, say: " +
    "\"I don't have live data for that symbol right now\" — do NOT guess.\n" +
    "3. Prices are ~15 min delayed from Yahoo Finance. Mention that when quoting.\n" +
    "4. Do NOT claim prices are 'simulated' — this data is real NSE data from Yahoo.\n\n";

  const finalPrompt = dataBlock
    ? `${guard}${dataBlock}\nUSER QUESTION: ${prompt}`
    : prompt;

  const result = await callGemini(finalPrompt, { temperature, maxOutputTokens });
  if (!result.ok) return res.status(result.status || 500).json({ ok: false, error: result.error });
  res.json({ ok: true, text: result.text, model: result.model });
});

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, version: "0.1.0", running: state.running, uptime: process.uptime() });
});

app.get("/api/bot/state", (_req, res) => {
  res.json(snapshot());
});

// Set the bot's budget (from the user's signup choice) + symbol.
app.post("/api/bot/config", (req, res) => {
  const { budget, symbol } = req.body || {};
  const result = configure({ budget, symbol });
  if (!result.ok) return res.status(400).json(result);
  saveState();
  res.json({ ok: true, budget: result.budget, symbol: result.symbol });
});

app.post("/api/bot/start", async (_req, res) => {
  const result = await start();
  const snap = snapshot();
  res.json({
    ok: Boolean(result?.ok),
    bot: {
      running: state.running,
      alreadyRunning: Boolean(result?.alreadyRunning),
      blocked: !result?.ok,
      reason: result?.reason || null,
      guard: snap.guardStatus,
      metrics: snap.metrics,
    },
  });
});

app.post("/api/bot/stop", (_req, res) => {
  stop();
  saveState();
  res.json({ ok: true, bot: { running: state.running } });
});

app.post("/api/bot/reset", (_req, res) => {
  reset();
  saveState();
  res.json({ ok: true });
});

app.get("/api/bot/status", (_req, res) => {
  const snap = snapshot();
  res.json({
    ok: true,
    bot: {
      running: state.running,
      alreadyRunning: state.running,
      blocked: !snap.guardStatus?.ok,
      reason: snap.guardStatus?.issues?.join(" ") || null,
      guard: snap.guardStatus,
      metrics: snap.metrics,
    },
  });
});

app.get("/api/strategies", (_req, res) => {
  res.json({ strategies: strategyList() });
});

// ─── Kite Connect (Zerodha) — read-only market data ──────────────────────────
app.get("/api/kite/status", (_req, res) => {
  res.json(kite.status());
});

// Step 1: get the Zerodha login URL (user opens this in browser)
app.get("/api/kite/login-url", (_req, res) => {
  if (!kite.isConfigured()) {
    return res.status(400).json({ ok: false, error: "Set KITE_API_KEY and KITE_API_SECRET in backend/.env first" });
  }
  res.json({ ok: true, url: kite.loginUrl() });
});

// Step 2: Zerodha redirects here with ?request_token=...
app.get("/api/kite/callback", async (req, res) => {
  const requestToken = req.query.request_token;
  if (!requestToken) {
    return res.status(400).send("Missing request_token. Did the Zerodha login complete?");
  }
  try {
    const { name } = await kite.completeLogin(requestToken);
    // Bounce the browser back to the frontend with a success flag
    res.send(`<!doctype html><html><body style="font-family:Inter,sans-serif;text-align:center;padding:60px">
      <h2 style="color:#16a34a">✓ Connected to Zerodha</h2>
      <p>Logged in as <b>${name}</b>. You can close this tab and return to Spencer AI.</p>
      <script>setTimeout(()=>{ window.location.href="http://localhost:5174"; }, 2500)</script>
      </body></html>`);
  } catch (e) {
    res.status(500).send(`Kite login failed: ${e.message}`);
  }
});

// Live quote(s) — e.g. /api/kite/quote?symbols=RELIANCE,TCS
app.get("/api/kite/quote", async (req, res) => {
  try {
    const symbols = String(req.query.symbols || state.symbol).split(",").map(s => s.trim()).filter(Boolean);
    const data = await kite.getQuotes(symbols);
    res.json({ ok: true, quotes: data });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// Historical bars — e.g. /api/kite/history?symbol=RELIANCE&interval=minute&days=5
app.get("/api/kite/history", async (req, res) => {
  try {
    const symbol = req.query.symbol || state.symbol;
    const interval = req.query.interval || "minute";
    const days = Number(req.query.days || 5);
    const bars = await kite.getHistorical(symbol, interval, days);
    res.json({ ok: true, symbol, interval, bars });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// Switch active strategy
app.post("/api/bot/strategy", (req, res) => {
  const { id } = req.body || {};
  const s = strategyList().find(m => m.id === id);
  if (!s) return res.status(400).json({ ok: false, error: "Unknown strategy id" });
  state.activeStrategyId = s.id;
  // Update strategy stats statuses
  for (const k of Object.keys(state.strategyStats)) {
    state.strategyStats[k].status = k === s.id ? "Testing" : "Queued";
  }
  saveState();
  res.json({ ok: true, activeStrategy: s });
});

// Compatibility shims for the older frontend endpoints
// Real Yahoo quotes for the watchlist. /api/quotes?symbols=RELIANCE,TCS,INFY
app.get("/api/quotes", async (req, res) => {
  const symbols = String(req.query.symbols || state.symbol)
    .split(",").map(s => s.trim()).filter(Boolean).slice(0, 40);
  try {
    const map = await yahoo.getQuotes(symbols);
    const quotes = Object.values(map).filter(Boolean).map(q => ({
      symbol: q.symbol,
      price: q.price,
      previousClose: q.previousClose,
      changePct: q.changePct,
      up: q.changePct != null ? q.changePct >= 0 : null,
      status: q.marketState === "REGULAR" ? "live" : "cached",
      source: "Yahoo Finance",
      fetchedAt: q.fetchedAt,
    }));
    res.json({ quotes });
  } catch (e) {
    res.status(500).json({ quotes: [], error: e.message });
  }
});

// Deep analysis of a stock: real indicators + AI interpretation. /api/analyze?symbol=RELIANCE
app.get("/api/analyze", async (req, res) => {
  const symbol = (req.query.symbol || state.symbol || "RELIANCE").toUpperCase();
  try {
    const analysis = await analyzeStock(symbol);
    const m = analysis.metrics;
    // Ask Gemini to interpret the REAL numbers (it can't invent — we hand it the data)
    let ai = null;
    const prompt =
`You are Spencer, a disciplined Indian-market trading analyst. Here are the REAL, computed indicators for NSE:${symbol} (do not invent any numbers — use only these):
- Price: ₹${m.price} (prev close ₹${m.prevClose}, ${m.changePct}% today)
- VWAP: ₹${m.vwap.value} → ${m.vwap.label}
- EMA: 9=₹${m.ema.ema9}, 21=₹${m.ema.ema21} → ${m.ema.label}
- RSI(14): ${m.rsi.value} → ${m.rsi.label}
- Volume: ${m.volume.label}
- ATR: ₹${m.atr} · Support ₹${m.support} · Resistance ₹${m.resistance}
- Rule-based bias: ${analysis.ruleBias}

Respond in this EXACT format (no markdown):
DECISION: ALLOW or BLOCK or REVIEW
REASONING: 2 sentences explaining the technical picture using the numbers above
RISK: Low or Medium or High
TIP: one actionable insight (<20 words)`;
    const g = await callGemini(prompt, { temperature: 0.25, maxOutputTokens: 400 });
    if (g.ok) ai = g.text;
    res.json({ ok: true, analysis, ai });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// Backtest a strategy over real history: /api/backtest?symbol=RELIANCE&strategyId=vwap_breakout
app.get("/api/backtest", async (req, res) => {
  try {
    const result = await runBacktest({
      symbol: req.query.symbol || state.symbol,
      interval: req.query.interval || process.env.BOT_INTERVAL || "5m",
      range: req.query.range || process.env.BOT_RANGE || "60d",
      strategyId: req.query.strategyId || state.activeStrategyId,
      budget: Number(req.query.budget || state.budget || 5000),
    });
    res.json({ ok: true, result });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// Single real quote: /api/quote?symbol=RELIANCE
app.get("/api/quote", async (req, res) => {
  try {
    const q = await yahoo.getQuote(req.query.symbol || state.symbol);
    res.json({ ok: true, quote: q });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

app.get("/api/chart", (req, res) => {
  const snap = snapshot();
  res.json({
    symbol: req.query.symbol || snap.symbol,
    candles: snap.chartTail.map(b => ({
      time: b.time, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume,
    })),
  });
});

// ─── Graceful shutdown ───────────────────────────────────────────────────────
function gracefulExit() {
  console.log("\n[server] shutting down — saving state…");
  saveState();
  process.exit(0);
}
process.on("SIGINT", gracefulExit);
process.on("SIGTERM", gracefulExit);

// ─── Start server ────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.warn("============================================================");
  console.warn("[server] WARNING: this is the LEGACY SIMULATION engine.");
  console.warn("[server] It serves SYNTHETIC prices + simulated trades (demo only).");
  console.warn("[server] For REAL paper data run: python spencer_quote_server.py");
  console.warn("[server] Do NOT run this on port 8787 alongside the real server.");
  console.warn("============================================================");
  console.log(`[server] Spencer AI (SIMULATION) listening on http://127.0.0.1:${PORT}`);
  console.log(`[server] Endpoints:`);
  console.log(`   GET  /api/health
   POST /api/ai/chat`);
  console.log(`   GET  /api/bot/state`);
  console.log(`   POST /api/bot/start`);
  console.log(`   POST /api/bot/stop`);
  console.log(`   POST /api/bot/reset`);
  console.log(`   POST /api/bot/strategy { id }`);
  console.log(`   GET  /api/strategies`);
  if (process.env.AUTO_START_BOT === "true") {
    start().catch(e => console.warn("[server] auto-start failed:", e.message));
  } else {
    console.log("[server] Bot auto-start disabled; frontend start requests still run guard checks.");
  }
});
