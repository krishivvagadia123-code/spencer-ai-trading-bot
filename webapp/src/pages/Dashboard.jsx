import { useEffect, useRef } from "react";
import { motion, useMotionValue, useTransform, useSpring } from "motion/react";
import { BentoGrid } from "../components/BentoGrid";
import { ScrollStory } from "../components/ScrollStory";
import { MetricsSection } from "../components/MetricsSection";
import { SpencerCore3D } from "../components/SpencerCore3D";
import { DataHealthPanel } from "../components/DataHealthPanel";
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
  const cap = botState?.capital || {};
  const totalValue = cap.totalValue;
  const totalPnl   = cap.totalPnl;
  const isConnected = backendStatus === "connected";

  // Hero scroll parallax
  const scrollY      = useMotionValue(0);
  useEffect(() => {
    const el = mainRef?.current;
    if (!el) return;
    const fn = () => scrollY.set(el.scrollTop);
    el.addEventListener("scroll", fn, { passive: true });
    return () => el.removeEventListener("scroll", fn);
  }, [mainRef, scrollY]);

  const heroOpacity = useSpring(useTransform(scrollY, [0, 500], [1, 0]),   { stiffness: 70, damping: 18 });
  const heroY       = useSpring(useTransform(scrollY, [0, 500], [0, -32]), { stiffness: 70, damping: 18 });

  return (
    <div className="-mb-6 md:-mb-10">

      {/* ── HERO ───────────────────────────────────────────────────── */}
      <motion.div
        style={{ opacity: heroOpacity, y: heroY }}
      >
        {/* Depth blob — moves slightly slower (parallax) */}
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

        <div className="liquid-glass-light relative overflow-hidden rounded-[28px] px-10 py-14 md:px-16 md:py-20">
          {/* Ghost RELIANCE */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none select-none overflow-hidden">
            <span
              className="font-display font-bold"
              style={{ fontSize: "clamp(90px,16vw,200px)", opacity: 0.025, letterSpacing: "-0.04em", lineHeight: 1 }}
            >
              RELIANCE
            </span>
          </div>

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

            {/* Row 2: value + capital columns */}
            <div className="flex flex-col gap-8 md:flex-row md:items-end md:justify-between">
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

              <div className="flex items-center gap-8">
                {[
                  { label: "Budget",    val: cap.budget   !== undefined ? money(cap.budget)   : "---" },
                  { label: "Invested",  val: cap.invested !== undefined ? money(cap.invested) : "---" },
                  { label: "Free Cash", val: cap.cash     !== undefined ? money(cap.cash)     : "---" },
                ].map((col, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.1 + i * 0.08, ease: EASE }}
                  >
                    <div className="mb-1.5 text-[11px] font-medium text-[var(--color-muted-dark-text)]">{col.label}</div>
                    <div className="font-display text-[20px] font-semibold tabular-nums">{col.val}</div>
                  </motion.div>
                ))}

                <div className="hidden md:flex flex-col items-center gap-1.5 pl-8 border-l border-[var(--color-light-border)]">
                  <CapitalGuardRing invested={cap.invested} budget={cap.budget} />
                  <span className="text-[10px] font-medium text-[var(--color-muted-dark-text)]">Guard</span>
                </div>
              </div>
            </div>

            {/* Row 3: status row */}
            <div className="mt-10 pt-6 border-t border-[var(--color-light-border)] flex flex-wrap gap-6">
              {[
                { label: "RELIANCE",   val: quote?.price ? money(quote.price, 2) : "---" },
                { label: "Candidates", val: String(ledger?.candidates?.length ?? "---") },
                { label: "Brain",      val: botState?.regimeTrust ? "Active" : "Unavailable", accent: !!botState?.regimeTrust },
              ].map((s, i) => (
                <motion.div
                  key={i}
                  className="flex items-center gap-2"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.5, delay: 0.3 + i * 0.07 }}
                >
                  <span className="text-[11px] font-medium text-[var(--color-muted-dark-text)]">{s.label}</span>
                  <span className="font-mono text-[13px]" style={{ color: s.accent ? "var(--color-verified-accent)" : "var(--color-primary-dark-text)" }}>
                    {s.val}
                  </span>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </motion.div>

      <div className="mt-8">
        <DataHealthPanel health={health} status={healthStatus} onRefresh={refreshHealth} />
      </div>

      {/* ── SYSTEM MODULES ─────────────────────────────────────────── */}
      <div className="module-glass-section mt-36 rounded-[36px] p-5 md:p-8">
        <div className="module-glass-heading mb-10 max-w-xl rounded-[26px] p-7 md:p-9">
          <Reveal>
            <SceneHeading
              label="System Modules"
              title="How Spencer works"
              sub="Eight principles that define the system's research and capital discipline."
            />
          </Reveal>
        </div>
        <BentoGrid onNavigate={(p) => { setActivePage(p); mainRef?.current?.scrollTo({ top: 0, behavior: "smooth" }); }} />
      </div>

      {/* ── RESEARCH CORE ──────────────────────────────────────────── */}
      <div className="research-core-section relative mt-28 w-screen left-1/2 -translate-x-1/2 overflow-hidden py-28 md:py-36">
        <div className="relative z-10 mx-auto max-w-[1480px] px-5 md:px-10">
          <div className="liquid-glass-heading mb-12 max-w-xl rounded-[26px] p-7 md:p-9">
            <Reveal>
              <SceneHeading
                label="Research Core"
                title="The instrument panel"
                sub="A fluid view of the research pipeline from observation to validation."
              />
            </Reveal>
          </div>
          <Reveal delay={0.1}>
            <SpencerCore3D />
          </Reveal>
        </div>
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

      {/* ── SPENCER SYSTEM (moved to the bottom; dark, blends into footer) ─ */}
      <div className="mt-36">
        <ScrollStory mainRef={mainRef} quote={quote} botState={botState} ledger={ledger} />
      </div>

      {/* ── FOOTER (same #0a0a0a as the scroll section — seamless) ──────── */}
      <footer
        className="glass-footer px-5 pt-14 pb-10 md:px-10"
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
