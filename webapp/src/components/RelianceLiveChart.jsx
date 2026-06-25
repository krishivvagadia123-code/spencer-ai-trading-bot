import { useEffect, useRef, useState } from "react";
import { SPENCER_API_BASE } from "../utils/constants";

const IST_OFFSET_SECONDS = 5.5 * 60 * 60;
const CACHE_KEY = "spencer.reliance.chart.5m.v1";

function marketLabel(marketState, marketStateLabel) {
  const state = String(marketState || "").toUpperCase();
  if (state === "OPEN") return "OPEN - NSE";
  if (marketStateLabel) return marketStateLabel;
  if (state) return "Market closed";
  return "Status unavailable";
}

function toChartPoints(candles) {
  const seen = new Set();
  const points = [];

  for (const candle of candles || []) {
    const timestamp = Date.parse(candle.time);
    const value = Number(candle.close);
    if (!Number.isFinite(timestamp) || !Number.isFinite(value)) continue;

    const time = Math.floor(timestamp / 1000) + IST_OFFSET_SECONDS;
    if (seen.has(time)) continue;
    seen.add(time);
    points.push({ time, value });
  }

  return points.sort((left, right) => left.time - right.time);
}

// Pixel-space layout: coords are computed in the chart's actual pixel size, and
// the SVG viewBox is set to that same size (1:1), so there is no
// preserveAspectRatio distortion and the live dot (positioned by px) lands
// exactly on the line's last point. Robust to any container size / layout.
const PAD = { top: 16, bottom: 22, left: 2, right: 46 };

function buildPath(points, width, height) {
  const empty = { line: "", area: "", dot: null, min: null, max: null, coords: [] };
  if (points.length < 2 || !(width > 0) || !(height > 0)) return empty;

  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(1e-6, max - min);

  const plotW = Math.max(1, width - PAD.left - PAD.right);
  const plotH = Math.max(1, height - PAD.top - PAD.bottom);

  const coords = points.map((point, index) => {
    const x = PAD.left + (index / (points.length - 1)) * plotW;
    const y = PAD.top + (1 - (point.value - min) / range) * plotH;
    return { x, y };
  });

  const line = coords
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const last = coords[coords.length - 1];
  const first = coords[0];
  const area = `${line} L ${last.x.toFixed(2)} ${height} L ${first.x.toFixed(2)} ${height} Z`;
  const dot = last;
  return { line, area, dot, min, max, coords };
}

export function RelianceLiveChart({ marketState, marketStateLabel, onLatestPoint }) {
  const onLatestPointRef = useRef(onLatestPoint);
  const [status, setStatus] = useState("loading");
  const [points, setPoints] = useState([]);
  const [latestPrice, setLatestPrice] = useState(null);
  const [chartError, setChartError] = useState("");
  const [hoverIndex, setHoverIndex] = useState(null);
  const containerRef = useRef(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const isMarketOpen = String(marketState || "").toUpperCase() === "OPEN";

  // Measure the chart's real pixel size so the SVG viewBox is 1:1 (no
  // distortion) and the live dot can sit exactly on the line. Re-measures on
  // any layout/UI change.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    onLatestPointRef.current = onLatestPoint;
  }, [onLatestPoint]);

  useEffect(() => {
    let cancelled = false;

    const applyPoints = (nextPoints, stale = false) => {
      if (nextPoints.length < 2) return false;
      const latest = nextPoints[nextPoints.length - 1];
      setPoints(nextPoints);
      setLatestPrice(latest.value);
      setStatus(stale ? "stale" : "ready");
      onLatestPointRef.current?.({
        price: latest.value,
        timestamp: new Date((latest.time - IST_OFFSET_SECONDS) * 1000).toISOString(),
      });
      return true;
    };

    const loadCached = () => {
      try {
        const cached = JSON.parse(window.localStorage.getItem(CACHE_KEY) || "null");
        const cachedPoints = Array.isArray(cached?.points) ? cached.points : [];
        return cachedPoints
          .map((point) => ({ time: Number(point.time), value: Number(point.value) }))
          .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value));
      } catch {
        return [];
      }
    };

    const saveCached = (nextPoints) => {
      try {
        window.localStorage.setItem(CACHE_KEY, JSON.stringify({
          savedAt: new Date().toISOString(),
          points: nextPoints.slice(-500),
        }));
      } catch {
        /* cache is best-effort only */
      }
    };

    const fetchCandles = async () => {
      let lastError;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const response = await fetch(
            `${SPENCER_API_BASE}/api/chart?symbol=RELIANCE&interval=5m`,
            { cache: "no-store" },
          );
          if (!response.ok) throw new Error(`Chart request failed: ${response.status}`);
          return await response.json();
        } catch (error) {
          lastError = error;
          await new Promise((resolve) => window.setTimeout(resolve, 700 * (attempt + 1)));
        }
      }
      throw lastError;
    };

    const cachedPoints = loadCached();
    if (cachedPoints.length >= 2) {
      applyPoints(cachedPoints, true);
    }

    const loadCandles = async () => {
      try {
        const payload = await fetchCandles();
        const nextPoints = toChartPoints(payload.candles);
        if (cancelled) return;

        if (nextPoints.length < 2) {
          setChartError(cachedPoints.length >= 2 ? "Using last saved real candles" : "Not enough candles returned");
          if (cachedPoints.length < 2) setStatus("unavailable");
          return;
        }

        applyPoints(nextPoints, false);
        saveCached(nextPoints);
        setChartError("");
      } catch (error) {
        if (cancelled) return;
        setChartError(error?.message || String(error));
        if (cachedPoints.length >= 2) {
          applyPoints(cachedPoints, true);
        } else {
          setStatus("unavailable");
        }
      }
    };

    loadCandles();
    const pollId = window.setInterval(loadCandles, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(pollId);
    };
  }, []);

  const chart = buildPath(points, size.w, size.h);
  const firstPoint = points[0];
  const lastPoint = points[points.length - 1];
  const hoverPoint = hoverIndex !== null ? points[hoverIndex] : null;
  const hoverCoord = hoverIndex !== null ? chart.coords?.[hoverIndex] : null;

  const handlePointerMove = (event) => {
    const count = chart.coords?.length ?? 0;
    if (count < 2) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width === 0) return;
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    setHoverIndex(Math.round(ratio * (count - 1)));
  };

  return (
    <div
      ref={containerRef}
      className="reliance-live-chart relative h-full w-full min-w-0 overflow-hidden"
      role="img"
      aria-label={`RELIANCE five-minute market line chart${
        latestPrice === null ? "" : `, latest price Rs ${latestPrice.toFixed(2)}`
      }`}
      data-latest-price={latestPrice ?? ""}
      data-chart-error={chartError}
    >
      <div className="absolute left-0 top-0 z-10 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-300">
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${
            isMarketOpen ? "live-pulse bg-emerald-300" : "bg-slate-500"
          }`}
        />
        {marketLabel(marketState, marketStateLabel)}
      </div>

      {(status === "ready" || status === "stale") && chart.line ? (
        <>
          <svg
            className="absolute inset-0 h-full w-full overflow-visible"
            style={{ cursor: "crosshair" }}
            viewBox={`0 0 ${size.w || 1} ${size.h || 1}`}
            preserveAspectRatio="none"
            aria-hidden="true"
            onMouseMove={handlePointerMove}
            onMouseLeave={() => setHoverIndex(null)}
          >
            <defs>
              <linearGradient id="relianceLineFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="rgba(94,234,212,0.20)" />
                <stop offset="48%" stopColor="rgba(167,139,250,0.12)" />
                <stop offset="100%" stopColor="rgba(167,139,250,0)" />
              </linearGradient>
            </defs>
            <path d={chart.area} fill="url(#relianceLineFill)" />
            <path
              d={chart.line}
              fill="none"
              stroke="rgba(226,232,240,0.96)"
              strokeWidth="4"
              vectorEffect="non-scaling-stroke"
            />
            {/* Live dot lives INSIDE the svg so it shares the exact same
                coordinate transform as the line — it sits on the last point by
                construction, no cross-coordinate-system drift. viewBox == pixel
                size, so the circle is round. */}
            {chart.dot && (
              <circle
                cx={chart.dot.x}
                cy={chart.dot.y}
                r="5"
                fill={isMarketOpen ? "#5eead4" : "#c4b5fd"}
                stroke="rgba(9,10,17,0.95)"
                strokeWidth="3"
              >
                {isMarketOpen && (
                  <animate
                    attributeName="opacity"
                    values="1;0.35;1"
                    dur="1.4s"
                    repeatCount="indefinite"
                  />
                )}
              </circle>
            )}
            {hoverCoord && (
              <g>
                <line
                  x1={hoverCoord.x}
                  y1="0"
                  x2={hoverCoord.x}
                  y2={size.h}
                  stroke="rgba(226,232,240,0.35)"
                  strokeWidth="1.5"
                  strokeDasharray="5 5"
                  vectorEffect="non-scaling-stroke"
                />
                <circle
                  cx={hoverCoord.x}
                  cy={hoverCoord.y}
                  r="6"
                  fill="#f8fafc"
                  stroke="rgba(9,10,17,0.95)"
                  strokeWidth="3"
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            )}
          </svg>
          {hoverPoint && (
            <div className="absolute left-1/2 top-1 z-20 -translate-x-1/2 whitespace-nowrap rounded-full bg-white/[0.1] px-3 py-1 text-[10px] font-semibold text-slate-100">
              {`Rs ${hoverPoint.value.toFixed(2)}`} &middot; {new Date((hoverPoint.time - IST_OFFSET_SECONDS) * 1000).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false })}
            </div>
          )}
          <div className="absolute inset-x-0 bottom-1 flex items-center justify-between text-[10px] font-semibold text-slate-500">
            <span>{firstPoint ? new Date((firstPoint.time - IST_OFFSET_SECONDS) * 1000).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) : ""}</span>
            <span>{lastPoint ? new Date((lastPoint.time - IST_OFFSET_SECONDS) * 1000).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) : ""}</span>
          </div>
          <div className="absolute right-0 top-12 grid gap-1 text-right text-[10px] font-semibold text-slate-500">
            <span>{chart.max?.toFixed(2)}</span>
            <span>{chart.min?.toFixed(2)}</span>
          </div>
          {status === "stale" && (
            <div className="absolute bottom-1 left-1/2 -translate-x-1/2 rounded-full bg-white/[0.06] px-2 py-1 text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Last saved real candles
            </div>
          )}
        </>
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-[11px] font-medium text-slate-300">
          {status === "loading" ? "Loading market chart..." : "Chart unavailable"}
        </div>
      )}
    </div>
  );
}
