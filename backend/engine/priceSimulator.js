// ─── Synthetic OHLCV generator with realistic chart patterns ─────────────────
// Produces 1-minute bars during NSE session hours (09:15 – 15:30 IST).
// Bot only sees the resulting bars — never the regime label or pattern script.
//
// Regimes that fire at random intervals:
//   - calm drift (random walk, low vol)
//   - trending up / down (5-30 day moves)
//   - double top / triple top reversals
//   - head & shoulders
//   - bull / bear flags (sharp move + tight consolidation)
//   - gap up / down (5% chance at session open)
//   - news shock (one big candle, ~once per week)

const BASE_PRICE = {
  RELIANCE: 2920,
  TCS: 3810,
  INFY: 1620,
};

const VOL_BASE = 8000;   // base per-minute volume
const SESSION_OPEN_MIN = 9 * 60 + 15;   // 9:15 in minutes-of-day
const SESSION_CLOSE_MIN = 15 * 60 + 30; // 15:30
const BARS_PER_DAY = SESSION_CLOSE_MIN - SESSION_OPEN_MIN; // 375

// Simple PRNG — deterministic from a seed so we can replay sequences
function rng(seed) {
  let s = seed | 0;
  return () => {
    s = Math.imul(48271, s) | 0;
    return ((s >>> 0) % 1000000) / 1000000;
  };
}

// Box-Muller normal random
function normal(rand, mu = 0, sigma = 1) {
  const u = Math.max(rand(), 1e-9);
  const v = Math.max(rand(), 1e-9);
  return mu + sigma * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// Build a sequence of regimes for `days` trading days
function buildRegimeScript(days, rand) {
  const script = [];
  let day = 0;
  while (day < days) {
    const r = rand();
    let regime;
    if (r < 0.30) {
      regime = { kind: "calm", days: 1 + Math.floor(rand() * 3) };
    } else if (r < 0.55) {
      const len = 3 + Math.floor(rand() * 5);
      const direction = rand() < 0.55 ? 1 : -1; // slight up bias
      regime = { kind: "trend", days: len, direction, strength: 0.001 + rand() * 0.002 };
    } else if (r < 0.70) {
      regime = { kind: "doubletop", days: 3 + Math.floor(rand() * 3) };
    } else if (r < 0.80) {
      regime = { kind: "tripletop", days: 4 + Math.floor(rand() * 3) };
    } else if (r < 0.88) {
      regime = { kind: "headshoulders", days: 5 + Math.floor(rand() * 3) };
    } else if (r < 0.95) {
      regime = { kind: "flag", days: 2 + Math.floor(rand() * 2), direction: rand() < 0.5 ? 1 : -1 };
    } else {
      regime = { kind: "shock", days: 1, direction: rand() < 0.5 ? 1 : -1, size: 0.04 + rand() * 0.03 };
    }
    script.push(regime);
    day += regime.days;
  }
  return script;
}

// Determine the price drift for a given simulated day based on the regime
function driftFor(regime, dayInRegime, totalDays) {
  switch (regime.kind) {
    case "calm":
      return 0;
    case "trend":
      return regime.direction * regime.strength;
    case "doubletop": {
      // up, down, up to same level, then sharp down
      const phase = dayInRegime / Math.max(regime.days - 1, 1);
      if (phase < 0.3)       return 0.0025;
      if (phase < 0.5)       return -0.0015;
      if (phase < 0.75)      return 0.0025;
      return -0.004;
    }
    case "tripletop": {
      const phase = dayInRegime / Math.max(regime.days - 1, 1);
      if (phase < 0.2)       return 0.0025;
      if (phase < 0.35)      return -0.001;
      if (phase < 0.5)       return 0.002;
      if (phase < 0.65)      return -0.001;
      if (phase < 0.8)       return 0.002;
      return -0.0045;
    }
    case "headshoulders": {
      const phase = dayInRegime / Math.max(regime.days - 1, 1);
      if (phase < 0.2)       return 0.002;       // left shoulder
      if (phase < 0.3)       return -0.001;
      if (phase < 0.5)       return 0.0035;      // head
      if (phase < 0.6)       return -0.0015;
      if (phase < 0.8)       return 0.002;       // right shoulder
      return -0.003;                              // neckline break
    }
    case "flag": {
      const phase = dayInRegime / Math.max(regime.days - 1, 1);
      if (phase < 0.3) return regime.direction * 0.005; // sharp pole
      if (phase < 0.7) return regime.direction * -0.0005; // tight pullback
      return regime.direction * 0.003; // continuation
    }
    case "shock":
      return regime.direction * regime.size;
    default:
      return 0;
  }
}

// Volatility per regime (standard deviation of minute returns)
function sigmaFor(regime) {
  switch (regime.kind) {
    case "calm":         return 0.0008;
    case "trend":        return 0.0014;
    case "doubletop":    return 0.0020;
    case "tripletop":    return 0.0020;
    case "headshoulders":return 0.0022;
    case "flag":         return 0.0018;
    case "shock":        return 0.0030;
    default:             return 0.0012;
  }
}

// ─── Main generator ─────────────────────────────────────────────────────────
// Returns an array of bars from `historyDays` ago up to `now` (latest bar).
// Each bar: { time, sessionMinute, open, high, low, close, volume }
//   time            — ISO timestamp (UTC)
//   sessionMinute   — 0..374, minute of the trading session
export function generateHistory({ symbol = "RELIANCE", historyDays = 60, seed = 42, now = Date.now() } = {}) {
  const base = BASE_PRICE[symbol] || 1000;
  const rand = rng(seed);

  // Build regime script for the whole history
  const regimes = buildRegimeScript(historyDays + 10, rand);

  const bars = [];
  let lastClose = base;

  // Walk backwards from `now`: build a list of trading-day start timestamps
  const today = new Date(now);
  const dayStarts = [];
  let cursor = new Date(today);
  cursor.setUTCHours(0, 0, 0, 0);
  while (dayStarts.length < historyDays) {
    const dow = cursor.getUTCDay(); // 0 sun, 6 sat
    if (dow !== 0 && dow !== 6) dayStarts.unshift(new Date(cursor));
    cursor.setUTCDate(cursor.getUTCDate() - 1);
  }

  // Determine which regime each day is in
  let regimeIdx = 0;
  let dayInRegime = 0;

  for (let d = 0; d < dayStarts.length; d++) {
    const dayDate = dayStarts[d];
    const regime = regimes[Math.min(regimeIdx, regimes.length - 1)];
    const drift = driftFor(regime, dayInRegime, regime.days);
    const sigma = sigmaFor(regime);

    // Optional opening gap (5% chance)
    let openPrice = lastClose;
    if (rand() < 0.05) {
      const gap = (rand() < 0.5 ? -1 : 1) * (0.005 + rand() * 0.02);
      openPrice = lastClose * (1 + gap);
    }
    lastClose = openPrice;

    // 375 minutes per session
    for (let m = 0; m < BARS_PER_DAY; m++) {
      // Intraday minute drift (smaller than daily drift)
      const minuteDrift = drift / BARS_PER_DAY;
      const ret = normal(rand, minuteDrift, sigma / Math.sqrt(BARS_PER_DAY) * 3);
      const open = lastClose;
      const close = open * (1 + ret);
      const hiNoise = Math.abs(normal(rand, 0, sigma * 0.4)) * open;
      const loNoise = Math.abs(normal(rand, 0, sigma * 0.4)) * open;
      const high = Math.max(open, close) + hiNoise;
      const low = Math.min(open, close) - loNoise;

      // Volume: spikes on big moves, dries up in calm regimes
      const moveSize = Math.abs(ret);
      const volMultiplier = 0.6 + moveSize * 1500 + (regime.kind === "shock" ? 4 : 0);
      const volume = Math.round(VOL_BASE * volMultiplier * (0.5 + rand()));

      // Bar timestamp = day start + session_open + m
      const ts = new Date(dayDate);
      ts.setUTCHours(0, 0, 0, 0);
      // IST 09:15 = 03:45 UTC
      ts.setUTCMinutes(3 * 60 + 45 + m);

      bars.push({
        time: ts.toISOString(),
        sessionMinute: m,
        open: round2(open),
        high: round2(high),
        low:  round2(low),
        close: round2(close),
        volume,
      });
      lastClose = close;
    }

    // Advance regime
    dayInRegime++;
    if (dayInRegime >= regime.days) {
      regimeIdx++;
      dayInRegime = 0;
    }
  }

  return bars;
}

// Generate ONE additional bar that follows the previous bar's price.
// Used by the live bot loop to extend the chart in real time.
export function generateNextBar(prevBar, sessionMinute, seed) {
  const rand = rng(seed);
  const sigma = 0.0014;
  const drift = 0.000002; // tiny long-term drift
  const ret = normal(rand, drift, sigma);
  const open = prevBar.close;
  const close = open * (1 + ret);
  const hiNoise = Math.abs(normal(rand, 0, sigma * 0.4)) * open;
  const loNoise = Math.abs(normal(rand, 0, sigma * 0.4)) * open;
  const high = Math.max(open, close) + hiNoise;
  const low  = Math.min(open, close) - loNoise;
  const moveSize = Math.abs(ret);
  const volMultiplier = 0.6 + moveSize * 1500;
  const volume = Math.round(VOL_BASE * volMultiplier * (0.5 + rand()));
  const ts = new Date(new Date(prevBar.time).getTime() + 60 * 1000);
  return {
    time: ts.toISOString(),
    sessionMinute,
    open: round2(open), high: round2(high), low: round2(low),
    close: round2(close), volume,
  };
}

function round2(n) { return Math.round(n * 100) / 100; }
