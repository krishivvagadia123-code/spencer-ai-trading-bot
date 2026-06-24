import { useEffect, useRef, useState } from "react";
import { SPENCER_API_BASE } from "../utils/constants";

const IST_OFFSET_SECONDS = 5.5 * 60 * 60;

function marketLabel(marketState, marketStateLabel) {
  const state = String(marketState || "").toUpperCase();
  if (state === "OPEN") return "OPEN · NSE";
  if (marketStateLabel) return marketStateLabel;
  if (state) return "Market closed";
  return "Status unavailable";
}

export function RelianceLiveChart({ marketState, marketStateLabel, onLatestPoint }) {
  const containerRef = useRef(null);
  const dotRef = useRef(null);
  const lastPointRef = useRef(null);
  const onLatestPointRef = useRef(onLatestPoint);
  const [chartStatus, setChartStatus] = useState("loading");
  const [latestPrice, setLatestPrice] = useState(null);
  const isMarketOpen = String(marketState || "").toUpperCase() === "OPEN";

  useEffect(() => {
    onLatestPointRef.current = onLatestPoint;
  }, [onLatestPoint]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    let cancelled = false;
    let chart;
    let series;
    let resizeObserver;
    let pollId;
    let frameId;
    let activeRequest;
    let hasData = false;

    const positionEndDot = () => {
      const dot = dotRef.current;
      const point = lastPointRef.current;
      if (!dot || !point || !chart || !series) return;

      const x = chart.timeScale().timeToCoordinate(point.time);
      const y = series.priceToCoordinate(point.value);
      if (x == null || y == null) {
        dot.style.display = "none";
        return;
      }

      dot.style.display = "block";
      dot.style.left = `${x}px`;
      dot.style.top = `${y}px`;
    };

    const loadCandles = async () => {
      activeRequest?.abort();
      activeRequest = new AbortController();

      try {
        const response = await fetch(
          `${SPENCER_API_BASE}/api/chart?symbol=RELIANCE&interval=5m`,
          { cache: "no-store", signal: activeRequest.signal },
        );
        if (!response.ok) throw new Error(`Chart request failed: ${response.status}`);

        const payload = await response.json();
        const seen = new Set();
        const points = [];

        for (const candle of payload.candles || []) {
          const timestamp = Date.parse(candle.time);
          const value = Number(candle.close);
          if (!Number.isFinite(timestamp) || !Number.isFinite(value)) continue;

          // lightweight-charts formats numeric timestamps as UTC. Shifting the
          // epoch lets the visible axis read in IST while preserving spacing.
          const time = Math.floor(timestamp / 1000) + IST_OFFSET_SECONDS;
          if (seen.has(time)) continue;
          seen.add(time);
          points.push({ time, value });
        }

        points.sort((left, right) => left.time - right.time);
        if (cancelled) return;
        if (points.length === 0) {
          if (!hasData) setChartStatus("unavailable");
          return;
        }

        series.setData(points);
        chart.timeScale().fitContent();
        lastPointRef.current = points[points.length - 1];
        onLatestPointRef.current?.({
          price: lastPointRef.current.value,
          timestamp: new Date(
            (lastPointRef.current.time - IST_OFFSET_SECONDS) * 1000,
          ).toISOString(),
        });
        setLatestPrice(lastPointRef.current.value);
        hasData = true;
        setChartStatus("ready");

        cancelAnimationFrame(frameId);
        frameId = requestAnimationFrame(positionEndDot);
      } catch (error) {
        if (cancelled || error?.name === "AbortError") return;
        if (!hasData) setChartStatus("unavailable");
      }
    };

    const initialize = async () => {
      try {
        const { AreaSeries, createChart } = await import("lightweight-charts");
        if (cancelled) return;

        chart = createChart(container, {
          autoSize: true,
          layout: {
            attributionLogo: true,
            background: { color: "transparent" },
            textColor: "rgba(15, 23, 42, 0.72)",
            fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
            fontSize: 11,
          },
          grid: {
            vertLines: { visible: false },
            horzLines: { color: "rgba(15, 23, 42, 0.08)" },
          },
          rightPriceScale: {
            borderVisible: false,
            scaleMargins: { top: 0.16, bottom: 0.16 },
          },
          timeScale: {
            borderVisible: false,
            timeVisible: true,
            secondsVisible: false,
            fixLeftEdge: true,
            fixRightEdge: true,
            rightOffset: 3,
          },
          crosshair: {
            mode: 1,
            vertLine: { color: "rgba(15, 23, 42, 0.28)", labelVisible: true },
            horzLine: { color: "rgba(15, 23, 42, 0.28)", labelVisible: true },
          },
          handleScroll: false,
          handleScale: false,
        });

        series = chart.addSeries(AreaSeries, {
          lineColor: "rgba(15, 23, 42, 0.94)",
          topColor: "rgba(15, 23, 42, 0.16)",
          bottomColor: "rgba(15, 23, 42, 0)",
          lineWidth: 2,
          priceFormat: { type: "price", precision: 2, minMove: 0.05 },
          priceLineVisible: false,
          lastValueVisible: true,
          crosshairMarkerVisible: true,
        });

        await loadCandles();
        if (cancelled) return;

        pollId = window.setInterval(loadCandles, 30_000);
        resizeObserver = new ResizeObserver(() => {
          cancelAnimationFrame(frameId);
          frameId = requestAnimationFrame(positionEndDot);
        });
        resizeObserver.observe(container);
      } catch {
        if (!cancelled) setChartStatus("unavailable");
      }
    };

    initialize();

    return () => {
      cancelled = true;
      activeRequest?.abort();
      window.clearInterval(pollId);
      cancelAnimationFrame(frameId);
      resizeObserver?.disconnect();
      chart?.remove();
    };
  }, []);

  return (
    <div
      className="reliance-live-chart relative h-full w-full min-w-0 overflow-hidden"
      role="img"
      aria-label={`RELIANCE five-minute market line chart${
        latestPrice === null ? "" : `, latest price ₹${latestPrice.toFixed(2)}`
      }`}
      data-latest-price={latestPrice ?? ""}
    >
      <div ref={containerRef} className="h-full w-full pt-4" />

      <div
        ref={dotRef}
        className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-1/2"
        style={{ display: "none" }}
      >
        <span
          className={`block h-3 w-3 rounded-full border-2 border-white/90 ${
            isMarketOpen ? "live-pulse bg-emerald-500" : "bg-slate-600"
          }`}
        />
      </div>

      <div className="pointer-events-none absolute left-0 top-0 z-10 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-800">
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${
            isMarketOpen ? "live-pulse bg-emerald-500" : "bg-slate-500"
          }`}
        />
        {marketLabel(marketState, marketStateLabel)}
      </div>

      {chartStatus !== "ready" && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-[11px] font-medium text-slate-700">
          {chartStatus === "loading" ? "Loading market chart…" : "Chart unavailable"}
        </div>
      )}
    </div>
  );
}
