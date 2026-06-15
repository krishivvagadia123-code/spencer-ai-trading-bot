import { useState } from "react";
import { motion } from "motion/react";
import { MetricsSection } from "../components/MetricsSection";
import { DataHealthPanel } from "../components/DataHealthPanel";
import { BackgroundActivity } from "../components/BackgroundActivity";
import { RelianceLiveChart } from "../components/RelianceLiveChart";
import { money, pct, pnlSign, pnlTone } from "../utils/helpers";

const EASE = [0.16, 1, 0.3, 1];

function Reveal({ children, delay = 0, className = "" }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.75, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

function SceneHeading({ label, title, sub }) {
  return (
    <div className="mb-14">
      {label && (
        <motion.p
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, ease: EASE }}
          className="mb-3 text-[12px] font-medium text-[var(--color-muted-dark-text)]"
        >
          {label}
        </motion.p>
      )}
      {title && (
        <motion.h2
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, delay: 0.07, ease: EASE }}
          className="font-display text-[clamp(28px,4vw,42px)] font-semibold leading-tight"
          style={{ letterSpacing: "-0.02em" }}
        >
          {title}
        </motion.h2>
      )}
      {sub && (
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, delay: 0.14, ease: EASE }}
          className="mt-3 max-w-md text-[15px] leading-relaxed text-[var(--color-muted-dark-text)]"
        >
          {sub}
        </motion.p>
      )}
    </div>
  );
}

function CapitalGuardRing({ invested, budget }) {
  const size = 56;
  const sw = 3;
  const r = (size - sw) / 2;
  const circ = r * 2 * Math.PI;
  const inv = Number.isFinite(invested) ? invested : 0;
  const bud = Number.isFinite(budget) && budget > 0 ? budget : 1;
  const ratio = Math.min(Math.max(inv / bud, 0), 1);
  const offset = circ - ratio * circ;

  if (!budget) {
    return (
      <svg width={size} height={size} className="rotate-[-90deg] opacity-20">
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="currentColor" strokeWidth={sw} strokeDasharray="3 3" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} className="rotate-[-90deg]">
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(0,0,0,0.07)" strokeWidth={sw} />
      <circle
        cx={size/2} cy={size/2} r={r}
        fill="none"
        stroke="var(--color-verified-accent)"
        strokeWidth={sw}
        strokeDasharray={circ}
        strokeDashoffset={offset}
        strokeLinecap="round"
        className="transition-all duration-1000 ease-out"
      />
    </svg>
  );
}

const finiteNumber = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

const signedMoney = (value) => {
  const number = finiteNumber(value);
  return number === null ? "—" : `${pnlSign(number)}${money(number, 2)}`;
};

const signedPct = (value) => {
  const number = finiteNumber(value);
  return number === null ? "—" : `${pnlSign(number)}${pct(number, 2)}`;
};

function DashboardMetric({ label, value, detail, tone = "" }) {
  return (
    <div className="glass-metric rounded-[22px] px-5 py-5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">
        {label}
      </div>
      <div className={`mt-2 font-display text-[24px] font-semibold leading-tight tabular-nums ${tone || "text-slate-950"}`}>
        {value}
      </div>
      <div className="mt-2 text-[11px] leading-relaxed text-slate-600">
        {detail}
      </div>
    </div>
  );
}

export function Dashboard({
  mainRef,
  botState,
  backendStatus,
  quote,
  ledger,
  health,
  healthStatus,
  refreshHealth,
  setActivePage,
}) {
  const [chartPoint, setChartPoint] = useState(null);
  const cap = botState?.capital || {};
  const totalValue = cap.totalValue;
  const totalPnl   = cap.totalPnl;
  const isConnected = backendStatus === "connected";
  const dayChange = finiteNumber(quote?.changePct ?? quote?.regularMarketChangePercent);
  const dayHigh = finiteNumber(quote?.dayHigh ?? quote?.regularMarketDayHigh);
  const dayLow = finiteNumber(quote?.dayLow ?? quote?.regularMarketDayLow);
  const unrealisedPnl = finiteNumber(cap.unrealisedPnl);
  const realisedPnl = finiteNumber(cap.realisedPnl);
  const invested = finiteNumber(cap.invested);
  const budget = finiteNumber(cap.budget);
  const exposure = invested !== null && budget !== null && budget > 0
    ? (invested / budget) * 100
    : null;
  const openPositions = botState == null
    ? null
    : Array.isArray(botState.openPosition)
      ? botState.openPosition.length
      : botState.openPosition
        ? 1
        : Array.isArray(botState.holdings)
          ? botState.holdings.length
          : null;
  const closedTrades = finiteNumber(botState?.metrics?.closedTrades);
  const wins = finiteNumber(botState?.metrics?.wins);
  const losses = finiteNumber(botState?.metrics?.losses);
  const fifteenMinSessions = finiteNumber(health?.readiness?.fifteenMinSessions);
  const requiredSessions = finiteNumber(health?.readiness?.required);
  const displayedReliancePrice = finiteNumber(chartPoint?.price) ?? finiteNumber(quote?.price);
  const readinessPct = (
    fifteenMinSessions !== null
    && requiredSessions !== null
    && requiredSessions > 0
  )
    ? Math.min(100, (fifteenMinSessions / requiredSessions) * 100)
    : null;

  return (
    <div className="-mb-6 md:-mb-10">

      {/* ── HERO ───────────────────────────────────────────────────── */}
      <div>
        {/* Static depth blobs behind the portfolio glass */}
        <motion.div
          className="absolute pointer-events-none"
          style={{
            y: 0,
            top: -80, left: "5%", width: "60%", height: 500,
            background: "radial-gradient(ellipse at center, rgba(45,212,160,0.08), transparent 70%)",
          }}
        />
        <motion.div
          className="absolute pointer-events-none"
          style={{
            y: 0,
            top: 20, right: "0%", width: "45%", height: 400,
            background: "radial-gradient(ellipse at center, rgba(107,143,255,0.06), transparent 70%)",
          }}
        />

        <div className="portfolio-glass liquid-glass-light relative overflow-hidden rounded-[28px] px-10 py-14 md:px-16 md:py-20">
          <div className="relative z-10">
            {/* Row 1: label + pills */}
            <div className="mb-6 flex flex-wrap items-center gap-2.5">
              <span className="text-[13px] font-medium text-[var(--color-muted-dark-text)]">Portfolio Value</span>
              <span className={`pill ${isConnected ? "pill-green" : "pill-muted"}`}>
                <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: isConnected ? "var(--color-verified-accent)" : "#ccc" }} />
                {isConnected ? "Connected" : "Offline"}
              </span>
              <span className="pill pill-blue">Paper</span>
              <span className="pill pill-muted">Live trading off</span>
              <span className="pill pill-muted">Broker execution off</span>
            </div>

            {/* Row 2: portfolio details and live chart */}
            <div className="grid gap-10 xl:grid-cols-[minmax(0,0.85fr)_minmax(520px,1.15fr)] xl:items-stretch">
              <div className="flex min-w-0 flex-col justify-between gap-10">
                <div>
                  <div className="font-display tabular-nums leading-none" style={{ fontSize: "clamp(52px,8vw,96px)", fontWeight: 600, letterSpacing: "-0.03em" }}>
                    {totalValue != null
                      ? money(totalValue)
                      : <span style={{ color: "var(--color-muted-dark-text)" }}>---</span>}
                  </div>
                  <div className="mt-4 flex items-center gap-3">
                    <span
                      className="font-mono text-[15px] tabular-nums"
                      style={{ color: totalPnl > 0 ? "var(--color-verified-accent)" : totalPnl < 0 ? "var(--color-failure-accent)" : "var(--color-muted-dark-text)" }}
                    >
                      {totalPnl != null ? `${pnlSign(totalPnl)}${money(totalPnl)}` : "---"}
                    </span>
                    <span className="text-[13px] text-[var(--color-muted-dark-text)]">{pct(cap.pnlPct)}</span>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-5">
                  {[
                    { label: "Budget",    val: cap.budget   !== undefined ? money(cap.budget)   : "---" },
                    { label: "Invested",  val: cap.invested !== undefined ? money(cap.invested) : "---" },
                    { label: "Free Cash", val: cap.cash     !== undefined ? money(cap.cash)     : "---" },
                  ].map((col, i) => (
                    <motion.div
                      key={col.label}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.6, delay: 0.1 + i * 0.08, ease: EASE }}
                    >
                      <div className="mb-1.5 text-[11px] font-medium text-[var(--color-muted-dark-text)]">{col.label}</div>
                      <div className="font-display text-[20px] font-semibold tabular-nums">{col.val}</div>
                    </motion.div>
                  ))}
                </div>
              </div>

              <div className="portfolio-chart-panel min-h-[300px] min-w-0 rounded-[24px] px-3 pb-2 pt-10 md:min-h-[340px] md:px-4">
                <RelianceLiveChart
                  marketState={quote?.marketState}
                  marketStateLabel={quote?.marketStateLabel}
                  onLatestPoint={setChartPoint}
                />
              </div>
            </div>

            {/* Row 3: status row */}
            <div className="mt-9 flex flex-wrap items-center gap-x-7 gap-y-3 border-t border-[var(--color-light-border)] pt-6">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-medium text-[var(--color-muted-dark-text)]">RELIANCE</span>
                <span className="font-mono text-[13px] text-[var(--color-primary-dark-text)]">
                  {displayedReliancePrice === null ? "—" : money(displayedReliancePrice, 2)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-medium text-[var(--color-muted-dark-text)]">Candidates</span>
                <span className="font-mono text-[13px] text-[var(--color-primary-dark-text)]">
                  {String(ledger?.candidates?.length ?? "—")}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-medium text-[var(--color-muted-dark-text)]">Brain</span>
                <span
                  className="font-mono text-[13px]"
                  style={{ color: botState?.regimeTrust ? "var(--color-verified-accent)" : "var(--color-primary-dark-text)" }}
                >
                  {botState?.regimeTrust ? "Active" : "Unavailable"}
                </span>
              </div>
              <div className="ml-auto hidden items-center gap-2 md:flex">
                <CapitalGuardRing invested={cap.invested} budget={cap.budget} />
                <span className="text-[10px] font-medium text-[var(--color-muted-dark-text)]">Capital guard</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-8">
        <DataHealthPanel health={health} status={healthStatus} onRefresh={refreshHealth} />
      </div>

      <div className="mt-6">
        <BackgroundActivity health={health} ledger={ledger} />
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <DashboardMetric
          label="RELIANCE day change"
          value={signedPct(dayChange)}
          detail="Latest real quote change"
          tone={pnlTone(dayChange)}
        />
        <DashboardMetric
          label="Day high / low"
          value={dayHigh === null || dayLow === null ? "—" : `${money(dayHigh, 2)} / ${money(dayLow, 2)}`}
          detail="Session range from quote"
        />
        <DashboardMetric
          label="Unrealised P&L"
          value={signedMoney(unrealisedPnl)}
          detail="Open paper positions"
          tone={pnlTone(unrealisedPnl)}
        />
        <DashboardMetric
          label="Realised P&L"
          value={signedMoney(realisedPnl)}
          detail="Closed paper trades"
          tone={pnlTone(realisedPnl)}
        />
        <DashboardMetric
          label="Exposure"
          value={exposure === null ? "—" : pct(exposure, 1)}
          detail="Invested / paper budget"
        />
        <DashboardMetric
          label="Open positions"
          value={openPositions === null ? "—" : openPositions.toLocaleString("en-IN")}
          detail="Current journal state"
        />
        <DashboardMetric
          label="Closed trades"
          value={closedTrades === null ? "—" : closedTrades.toLocaleString("en-IN")}
          detail="Completed journal exits"
        />
        <DashboardMetric
          label="Wins / losses"
          value={wins === null || losses === null ? "—" : `${wins.toLocaleString("en-IN")} / ${losses.toLocaleString("en-IN")}`}
          detail="Real closed-trade outcomes"
        />
        <DashboardMetric
          label="SPNCR-003 readiness"
          value={readinessPct === null ? "—" : pct(readinessPct, 0)}
          detail={fifteenMinSessions === null || requiredSessions === null
            ? "Data readiness unavailable"
            : `${fifteenMinSessions} / ${requiredSessions} verified 15m sessions`}
        />
      </div>

      {/* ── LIFETIME PERFORMANCE ───────────────────────────────────── */}
      <div className="mt-36">
        <div className="mb-16 flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <Reveal>
            <SceneHeading
              label="Lifetime Performance"
              title="By the numbers"
              sub="Real metrics from paper trading, never estimated."
            />
          </Reveal>
        </div>
        <MetricsSection botState={botState} ledger={ledger} health={health} />
      </div>

      {/* ── FOOTER (same #0a0a0a as the scroll section — seamless) ──────── */}
      <footer
        className="glass-footer mt-28 px-5 pt-14 pb-10 md:mt-36 md:px-10"
        style={{ width: "100vw", position: "relative", left: "50%", marginLeft: "-50vw" }}
      >
        <div className="mx-auto max-w-[1480px]">
          <div className="flex flex-col gap-10 md:flex-row md:items-start md:justify-between">
            {/* Left — small logo */}
            <div>
              <div className="logo-font text-[24px] text-slate-950">Spencer</div>
              <p className="mt-2 text-[12px] text-slate-600">
                One stock. Real edges. Paper-only.
              </p>
            </div>

            {/* Right — navigable menu */}
            <nav className="grid grid-cols-2 gap-x-12 gap-y-2.5 sm:grid-cols-3 md:text-right">
              {["Dashboard", "Orders", "Funds", "Bids", "Brain", "Governance", "Profile"].map((id) => (
                <button
                  key={id}
                  onClick={() => { setActivePage(id); mainRef?.current?.scrollTo({ top: 0, behavior: "smooth" }); }}
                  className="text-[13px] text-slate-600 transition-colors hover:text-slate-950 md:text-right"
                >
                  {id}
                </button>
              ))}
            </nav>
          </div>

          <div className="mt-12 flex flex-col gap-2 border-t border-white/40 pt-6 text-[11px] text-slate-500 sm:flex-row sm:items-center sm:justify-between">
            <span>© 2026 Spencer · Paper trading only</span>
            <span className="font-mono">RELIANCE · epoch one_stock_reliance_v1</span>
          </div>
        </div>
      </footer>

    </div>
  );
}
