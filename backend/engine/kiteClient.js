// ─── Zerodha Kite Connect integration ────────────────────────────────────────
// Read-only market data for now. NO order execution (that comes later,
// only after weeks of proven paper results). The api_secret stays server-side.
//
// Auth flow:
//   1. GET /api/kite/login-url → user opens it, logs into Zerodha
//   2. Zerodha redirects to /api/kite/callback?request_token=xxx
//   3. We exchange request_token + api_secret → access_token (valid until ~6am)
//   4. access_token cached to disk; used for all quote/historical calls

import { KiteConnect } from "kiteconnect";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SESSION_FILE = path.join(__dirname, "..", "state", "kite-session.json");

const API_KEY = process.env.KITE_API_KEY || "";
const API_SECRET = process.env.KITE_API_SECRET || "";

let kc = null;
let accessToken = null;
let profileName = null;

export function isConfigured() {
  return Boolean(API_KEY && API_SECRET);
}

function client() {
  if (!kc) kc = new KiteConnect({ api_key: API_KEY });
  return kc;
}

// Persist / restore the daily access token
function saveSession() {
  try {
    fs.mkdirSync(path.dirname(SESSION_FILE), { recursive: true });
    fs.writeFileSync(SESSION_FILE, JSON.stringify({ accessToken, profileName, savedAt: Date.now() }, null, 2));
  } catch (e) { console.warn("[kite] save session failed:", e.message); }
}
export function restoreSession() {
  try {
    if (!fs.existsSync(SESSION_FILE)) return false;
    const s = JSON.parse(fs.readFileSync(SESSION_FILE, "utf-8"));
    // Kite tokens die at ~6am IST. If saved before today's 6am, treat as stale.
    const sixAmToday = new Date();
    sixAmToday.setHours(6, 0, 0, 0);
    if (s.savedAt && s.savedAt < sixAmToday.getTime()) {
      console.log("[kite] stored token is stale (pre-6am) — re-login needed");
      return false;
    }
    accessToken = s.accessToken;
    profileName = s.profileName;
    if (accessToken) {
      client().setAccessToken(accessToken);
      console.log("[kite] restored session for", profileName);
      return true;
    }
  } catch (e) { console.warn("[kite] restore failed:", e.message); }
  return false;
}

export function loginUrl() {
  if (!isConfigured()) return null;
  return client().getLoginURL();
}

// Exchange the request_token for an access_token
export async function completeLogin(requestToken) {
  if (!isConfigured()) throw new Error("Kite api_key/api_secret not configured in .env");
  const session = await client().generateSession(requestToken, API_SECRET);
  accessToken = session.access_token;
  profileName = session.user_name || session.user_id;
  client().setAccessToken(accessToken);
  saveSession();
  return { name: profileName };
}

export function status() {
  return {
    configured: isConfigured(),
    connected: Boolean(accessToken),
    profileName,
  };
}

// ─── Live quote for one or more NSE symbols ──────────────────────────────────
// symbols: ["RELIANCE", "TCS"] → returns { RELIANCE: {...}, ... }
export async function getQuotes(symbols) {
  if (!accessToken) throw new Error("Not authenticated with Kite");
  const keys = symbols.map(s => `NSE:${s}`);
  const data = await client().getQuote(keys);
  const out = {};
  for (const s of symbols) {
    const q = data[`NSE:${s}`];
    if (q) {
      out[s] = {
        symbol: s,
        price: q.last_price,
        previousClose: q.ohlc?.close,
        open: q.ohlc?.open,
        high: q.ohlc?.high,
        low: q.ohlc?.low,
        volume: q.volume,
        changePct: q.ohlc?.close ? ((q.last_price - q.ohlc.close) / q.ohlc.close) * 100 : null,
        fetchedAt: Date.now(),
      };
    }
  }
  return out;
}

// ─── Historical 1-min bars for backfilling ──────────────────────────────────
// Requires the instrument token. We look it up from the instruments dump.
let instrumentCache = null;
async function instrumentToken(symbol) {
  if (!instrumentCache) {
    instrumentCache = await client().getInstruments("NSE");
  }
  const row = instrumentCache.find(i => i.tradingsymbol === symbol && i.segment === "NSE");
  return row ? row.instrument_token : null;
}

export async function getHistorical(symbol, interval = "minute", days = 5) {
  if (!accessToken) throw new Error("Not authenticated with Kite");
  const token = await instrumentToken(symbol);
  if (!token) throw new Error(`Instrument token not found for ${symbol}`);
  const to = new Date();
  const from = new Date(to.getTime() - days * 24 * 60 * 60 * 1000);
  const candles = await client().getHistoricalData(token, interval, from, to);
  // Normalize to our bar shape
  return candles.map(c => ({
    time: new Date(c.date).toISOString(),
    open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume,
  }));
}
