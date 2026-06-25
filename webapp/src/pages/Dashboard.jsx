import { useState } from "react";
import { motion } from "motion/react";
import { Activity, DatabaseZap, ShieldCheck, TrendingUp } from "lucide-react";
import { MetricsSection } from "../components/MetricsSection";
import { DataHealthPanel } from "../components/DataHealthPanel";
import { BackgroundActivity } from "../components/BackgroundActivity";
import { RelianceLiveChart } from "../components/RelianceLiveChart";
import { money, pct, pnlSign, pnlTone } from "../utils/helpers";

const EASE = [0.16, 1, 0.3, 1];

const finiteNumber = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

const dash = "—";

const displayMoney = (value, digits = 0) => {
  const number = finiteNumber(value);
  return number === null ? dash : money(number, digits);
};

const signedMoney = (value) => {
  const number = finiteNumber(value);
  return number === null ? dash : `${pnlSign(number)}${money(number, 2)}`;
};

const signedPct = (value) => {
  const number = finiteNumber(value);
  return number === null ? dash : `${pnlSign(number)}${pct(number, 2)}`;
};

function Reveal({ children, delay = 0, className = "" }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

function DashboardCard({ children, className = "" }) {
  return <div className={`spencer-card ${className}`}>{children}</div>;
}

function MiniMetric({ label, value, detail, tone = "", icon: Icon, accent = "violet" }) {
  return (
    <DashboardCard className={`metric-card metric-card--${accent} min-h-[120px] p-5`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="metric-label">{label}</div>
          <div className={`metric-value ${tone || "text-slate-100"}`}>{value}</div>
        </div>
        {Icon && (
          <span className={`metric-icon metric-icon--${accent}`}>
            <Icon className="h-4 w-4" />
          </span>
        )}
      </div>
      <div className="mt-3 text-[12px] leading-relaxed text-slate-400">{detail}</div>
    </DashboardCard>
  );
}

function ReadinessRing({ value }) {
  const pctValue = finiteNumber(value);
  const display = pctValue === null ? null : Math.min(100, Math.max(0, pctValue));
  return (
    <div className="relative flex h-24 w-24 shrink-0 items-center justify-center rounded-full bg-[#141624] shadow-inner">
      <div
        className="absolute inset-0 rounded-full"
        style={{
          background: `conic-gradient(var(--theme-accent) ${display ?? 0}%, rgba(255,255,255,0.08) 0)`,
        }}
      />
      <div className="absolute inset-3 rounded-full bg-[#0b0c14]" />
      <div className="relative text-center">
        <div className="font-display text-[21px] font-bold text-slate-100">
          {display === null ? dash : `${Math.round(display)}%`}
        </div>
        <div className="text-[9px] font-bold uppercase tracking-[0.16em] text-slate-500">ready</div>
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
  const isConnected = backendStatus === "connected";
  const dayChange = finiteNumber(quote?.changePct ?? quote?.regularMarketChangePercent);
  const dayHigh = finiteNumber(quote?.dayHigh ?? quote?.regularMarketDayHigh);
  const dayLow = finiteNumber(quote?.dayLow ?? quote?.regularMarketDayLow);
  const unrealisedPnl = finiteNumber(cap.unrealisedPnl);
  const realisedPnl = finiteNumber(cap.realisedPnl);
  const invested = finiteNumber(cap.invested);
  const budget = finiteNumber(cap.budget);
  const exposure = invested !== null && budget !== null && budget > 0 ? (invested / budget) * 100 : null;
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
  const readinessPct = fifteenMinSessions !== null && requiredSessions !== null && requiredSessions > 0
    ? Math.min(100, (fifteenMinSessions / requiredSessions) * 100)
    : null;
  const displayedReliancePrice = finiteNumber(chartPoint?.price) ?? finiteNumber(quote?.price);
  const candidates = Array.isArray(ledger?.candidates) ? ledger.candidates : [];
  const marketLabel = quote?.marketStateLabel || (quote?.marketState ? String(quote.marketState) : "Market state unavailable");

  const footerNavigate = (id) => {
    setActivePage(id);
    mainRef?.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="dashboard-redesign space-y-6">
      <Reveal>
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_330px]">
          <div className="grid gap-4 md:grid-cols-3">
            <MiniMetric
              label="Portfolio Value"
              value={displayMoney(cap.totalValue)}
              detail={`P&L ${signedMoney(cap.totalPnl)} · ${cap.pnlPct == null ? dash : pct(cap.pnlPct, 2)}`}
              tone={pnlTone(cap.totalPnl)}
              icon={TrendingUp}
              accent="teal"
            />
            <MiniMetric
              label="RELIANCE"
              value={displayedReliancePrice === null ? dash : money(displayedReliancePrice, 2)}
              detail={`Day ${signedPct(dayChange)} · ${dayHigh === null || dayLow === null ? "Day range unavailable" : `${money(dayLow, 2)}-${money(dayHigh, 2)}`}`}
              tone={pnlTone(dayChange)}
              icon={Activity}
              accent="blue"
            />
            <MiniMetric
              label="Capital Guard"
              value={exposure === null ? dash : pct(exposure, 1)}
              detail={`Budget ${displayMoney(cap.budget)} · free ${displayMoney(cap.cash)}`}
              icon={ShieldCheck}
              accent="amber"
            />
          </div>

          <DashboardCard className="readiness-card metric-card--violet flex items-center justify-between gap-5 p-5">
            <div>
              <div className="metric-label">SPNCR-003 Readiness</div>
              <div className="mt-2 font-display text-[24px] font-bold text-slate-100">
                {fifteenMinSessions === null || requiredSessions === null ? "Data unavailable" : `${fifteenMinSessions} / ${requiredSessions}`}
              </div>
              <p className="mt-2 text-[12px] leading-relaxed text-slate-400">
                Real audited 15m sessions toward the next research ladder.
              </p>
            </div>
            <ReadinessRing value={readinessPct} />
          </DashboardCard>
        </section>
      </Reveal>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Reveal delay={0.04}>
          <DashboardCard className="chart-card p-5">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="metric-label">Live Market</div>
                <h1 className="mt-1 font-display text-[30px] font-bold tracking-[-0.04em] text-slate-100 md:text-[38px]">
                  RELIANCE price movement
                </h1>
                <p className="mt-2 text-[12px] text-slate-400">
                  Existing real 5-minute candles from Spencer's backend. No external embeds, no fake values.
                </p>
              </div>
              <div className="chart-status-cluster">
                <span className="reference-pill">{isConnected ? "Backend connected" : "Backend unavailable"}</span>
                <span className="reference-pill">{marketLabel}</span>
              </div>
            </div>
            <div className="chart-shell">
              <RelianceLiveChart
                marketState={quote?.marketState}
                marketStateLabel={quote?.marketStateLabel}
                onLatestPoint={setChartPoint}
              />
            </div>
          </DashboardCard>
        </Reveal>

        <Reveal delay={0.08} className="space-y-4">
          <DashboardCard className="p-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="metric-label">Safety</div>
                <div className="mt-2 font-display text-[23px] font-bold text-slate-100">
                  Paper-only system
                </div>
              </div>
              <span className="metric-icon metric-icon--rose h-12 w-12">
                <ShieldCheck className="h-5 w-5" />
              </span>
            </div>
            <div className="mt-5 grid gap-2 text-[12px] font-semibold text-slate-300">
              <div className="status-row"><span>Paper mode</span><span>ON</span></div>
              <div className="status-row"><span>Live trading off</span><span>OFF</span></div>
              <div className="status-row"><span>Broker execution off</span><span>OFF</span></div>
            </div>
          </DashboardCard>

          <MiniMetric
            label="Open / Closed"
            value={`${openPositions === null ? dash : openPositions} / ${closedTrades === null ? dash : closedTrades}`}
            detail="Real journal state from backend"
            icon={DatabaseZap}
            accent="teal"
          />
          <MiniMetric
            label="Wins / Losses"
            value={wins === null || losses === null ? dash : `${wins} / ${losses}`}
            detail={`Unrealised ${signedMoney(unrealisedPnl)} · realised ${signedMoney(realisedPnl)}`}
            tone={pnlTone((unrealisedPnl ?? 0) + (realisedPnl ?? 0))}
            accent="amber"
          />
          <MiniMetric
            label="Research Ledger"
            value={String(candidates.length)}
            detail="Candidates tested, killed, or awaiting validation"
            accent="violet"
          />
        </Reveal>
      </section>

      <Reveal delay={0.12}>
        <DataHealthPanel health={health} status={healthStatus} onRefresh={refreshHealth} />
      </Reveal>

      <Reveal delay={0.16}>
        <BackgroundActivity health={health} ledger={ledger} />
      </Reveal>

      <section className="pt-8">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="metric-label">Lifetime Performance</div>
            <h2 className="mt-1 font-display text-[30px] font-bold tracking-[-0.04em] text-slate-100">
              By the numbers
            </h2>
          </div>
          <p className="max-w-md text-[13px] leading-relaxed text-slate-400">
            Real metrics from paper trading and research ledger only. Missing backend fields stay unavailable.
          </p>
        </div>
        <MetricsSection botState={botState} ledger={ledger} health={health} />
      </section>

      <footer className="spencer-footer">
        <div>
          <div className="logo-font text-[24px] text-slate-100">Spencer</div>
          <p className="mt-1 text-[12px] text-slate-400">One stock. Real edges. Paper-only.</p>
        </div>
        <nav className="flex flex-wrap gap-3">
          {["Dashboard", "Orders", "Funds", "Bids", "Brain", "Governance", "Profile"].map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => footerNavigate(id)}
              className="rounded-full bg-white/[0.06] px-4 py-2 text-[12px] font-semibold text-slate-300 transition hover:bg-white/[0.1] hover:text-white"
            >
              {id}
            </button>
          ))}
        </nav>
      </footer>
    </div>
  );
}
