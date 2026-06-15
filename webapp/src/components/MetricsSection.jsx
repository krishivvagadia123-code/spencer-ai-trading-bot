import { motion, useInView } from "motion/react";
import { useRef, useEffect, useState } from "react";
import { money } from "../utils/helpers";

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1];

function useCountUp(target, active, duration = 1400) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!active || typeof target !== "number") return;
    const start = performance.now();
    let raf;
    const frame = (now) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 4);
      setCount(Math.round(eased * target));
      if (t < 1) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [target, active, duration]);
  return count;
}

function Metric({ label, raw, index }) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-40px" });
  const numericVal = typeof raw === "number" ? raw : null;
  const isMonetary = typeof raw === "string" && raw.startsWith("₹");
  const numericMoney = isMonetary
    ? parseFloat(raw.replace(/[₹,]/g, ""))
    : null;

  const count = useCountUp(numericVal ?? numericMoney ?? 0, isInView, 1200 + index * 100);

  const displayValue = () => {
    if (!isInView) return raw;
    if (numericVal !== null) return count.toLocaleString("en-IN");
    if (isMonetary)          return `₹${count.toLocaleString("en-IN")}`;
    return raw;
  };

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.7, delay: index * 0.1, ease: EASE_OUT_EXPO }}
      className="liquid-glass-light flex flex-col gap-3 rounded-[20px] p-8"
    >
      <div className="text-[11px] font-medium text-[var(--color-muted-dark-text)]">
        {label}
      </div>
      <div
        className="font-display tabular-nums leading-none"
        style={{
          fontSize: "clamp(28px,4vw,42px)",
          fontWeight: 600,
          letterSpacing: "-0.02em",
          color: "var(--color-primary-dark-text)",
        }}
      >
        {displayValue()}
      </div>
    </motion.div>
  );
}

export function MetricsSection({ botState, ledger, health }) {
  const candidates = ledger?.candidates || [];
  const tested = ledger?.scoreboard?.candidatesTested ?? candidates.length;
  const killed = ledger?.scoreboard?.candidatesKilled
    ?? candidates.filter((candidate) => String(candidate?.status || "").toUpperCase() === "KILLED").length;
  const validated = ledger?.scoreboard?.validatedEdges
    ?? candidates.filter((candidate) => String(candidate?.status || "").toUpperCase() === "VALIDATED").length;

  const metrics = [
    { label: "Paper Capital",  raw: botState?.capital?.budget == null ? "---" : money(botState.capital.budget) },
    { label: "Total P&L",      raw: botState?.capital?.totalPnl == null ? "---" : money(botState.capital.totalPnl) },
    { label: "Closed Trades",  raw: botState?.metrics?.closedTrades       ?? "---" },
    { label: "Win Rate",       raw: botState?.metrics?.winRate == null ? "---" : `${Number(botState.metrics.winRate).toFixed(1)}%` },
    { label: "Tested",         raw: tested },
    { label: "Killed",         raw: killed },
    { label: "Validated",      raw: validated },
    { label: "15m Sessions",   raw: health?.readiness?.fifteenMinSessions ?? "---" },
    { label: "1m Sessions",    raw: health?.readiness?.oneMinSessions ?? "---" },
    { label: "Data Integrity", raw: health?.integrity?.overall ?? "---" },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-5">
      {metrics.map((m, i) => (
        <Metric key={i} label={m.label} raw={m.raw} index={i} />
      ))}
    </div>
  );
}
