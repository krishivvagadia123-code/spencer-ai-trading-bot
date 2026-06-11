// ─── Yahoo Finance data client (free, no auth, real NSE prices) ──────────────
// Uses the public v8 chart endpoint. CORS doesn't apply server-side, so this
// works from Node even though it fails in the browser.
//
// Prices are ~15 min delayed — fine for swing training. NOT for HFT.

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36";

// Small in-memory cache so we don't hammer Yahoo (15s TTL)
const cache = new Map();
const TTL_MS = 15000;

function nseSymbol(sym) {
  // RELIANCE → RELIANCE.NS ; indices (^NSEI, ^BSESN) and suffixed stay as-is
  const s = sym.trim().toUpperCase();
  if (s.startsWith("^")) return s;
  return s.endsWith(".NS") || s.endsWith(".BO") ? s : `${s}.NS`;
}

async function fetchChart(symbol, { interval = "1m", range = "1d" } = {}) {
  const ysym = nseSymbol(symbol);
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ysym)}?interval=${interval}&range=${range}`;
  const res = await fetch(url, { headers: { "User-Agent": UA }, cache: "no-store" });
  if (!res.ok) throw new Error(`Yahoo ${res.status} for ${ysym}`);
  const data = await res.json();
  const result = data?.chart?.result?.[0];
  if (!result) throw new Error(`No data for ${ysym}`);
  return result;
}

// ─── Live quote for one symbol ───────────────────────────────────────────────
export async function getQuote(symbol) {
  const key = `q:${symbol.toUpperCase()}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.val;

  const r = await fetchChart(symbol, { interval: "1m", range: "1d" });
  const m = r.meta || {};
  const price = m.regularMarketPrice ?? null;
  const prevClose = m.previousClose ?? m.chartPreviousClose ?? null;
  const quote = {
    symbol: symbol.toUpperCase(),
    price,
    previousClose: prevClose,
    open: m.regularMarketDayOpen ?? null,
    dayHigh: m.regularMarketDayHigh ?? null,
    dayLow: m.regularMarketDayLow ?? null,
    fiftyTwoWeekHigh: m.fiftyTwoWeekHigh ?? null,
    fiftyTwoWeekLow: m.fiftyTwoWeekLow ?? null,
    volume: m.regularMarketVolume ?? null,
    currency: m.currency || "INR",
    exchange: m.exchangeName || m.fullExchangeName || "NSE",
    marketState: m.marketState || null, // REGULAR / CLOSED / PRE / POST
    changePct: (price != null && prevClose) ? ((price - prevClose) / prevClose) * 100 : null,
    change: (price != null && prevClose != null) ? (price - prevClose) : null,
    fetchedAt: Date.now(),
    source: "Yahoo Finance",
  };
  cache.set(key, { at: Date.now(), val: quote });
  return quote;
}

// ─── Batch quotes ────────────────────────────────────────────────────────────
export async function getQuotes(symbols) {
  const out = {};
  await Promise.all(symbols.map(async (s) => {
    try { out[s.toUpperCase()] = await getQuote(s); }
    catch { out[s.toUpperCase()] = null; }
  }));
  return out;
}

// ─── Historical bars ─────────────────────────────────────────────────────────
// interval: "1m","5m","15m","1d"  ·  range: "1d","5d","1mo","3mo","6mo","1y"
export async function getHistory(symbol, { interval = "1d", range = "3mo" } = {}) {
  const r = await fetchChart(symbol, { interval, range });
  const ts = r.timestamp || [];
  const q = r.indicators?.quote?.[0] || {};
  const bars = [];
  const OPEN_UTC_MIN = 3 * 60 + 45; // NSE 09:15 IST = 03:45 UTC
  for (let i = 0; i < ts.length; i++) {
    const o = q.open?.[i], h = q.high?.[i], l = q.low?.[i], c = q.close?.[i], v = q.volume?.[i];
    if ([o, h, l, c].some(x => x == null)) continue;
    const d = new Date(ts[i] * 1000);
    const sessionMinute = Math.max(0, (d.getUTCHours() * 60 + d.getUTCMinutes()) - OPEN_UTC_MIN);
    bars.push({
      time: d.toISOString(),
      sessionMinute,
      open: round2(o), high: round2(h), low: round2(l), close: round2(c),
      volume: v ?? 0,
    });
  }
  return bars;
}

function round2(n) { return Math.round(n * 100) / 100; }

export function isMarketLive(quote) {
  return quote?.marketState === "REGULAR";
}
