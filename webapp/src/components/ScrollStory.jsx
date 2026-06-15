import {
  motion,
  AnimatePresence,
  useMotionValue,
  useTransform,
  useSpring,
} from "motion/react";
import { useRef, useEffect, useState } from "react";
import { WireframeOrb } from "./WireframeOrb";
import { money } from "../utils/helpers";

const EASE = [0.16, 1, 0.3, 1];

const STEPS = [
  { id: 1, title: "Observe",    sub: "Real-time NSE price feed for RELIANCE",        accent: "#2DD4A0" },
  { id: 2, title: "Research",   sub: "Active hypothesis pipeline and candidate list", accent: "#6B8FFF" },
  { id: 3, title: "Test",       sub: "Paper trading performance under real conditions", accent: "#2DD4A0" },
  { id: 4, title: "Confirm",    sub: "Statistical edge validated before any trade",   accent: "#6B8FFF" },
  { id: 5, title: "Govern",     sub: "Paper-only capital protection always active",   accent: "#2DD4A0" },
];

function LeftIndex({ activeStep, progress }) {
  return (
    <div className="relative flex flex-col justify-center gap-1 py-8">
      {/* Vertical progress line */}
      <div className="absolute left-0 top-8 bottom-8 w-px bg-white/10">
        <motion.div
          className="w-full origin-top bg-white/40"
          style={{ scaleY: progress, height: "100%" }}
        />
      </div>

      {STEPS.map((s, i) => {
        const isActive = i === activeStep;
        return (
          <div
            key={s.id}
            className="flex items-center gap-5 pl-6 py-3 transition-all duration-500"
            style={{ opacity: isActive ? 1 : 0.28 }}
          >
            <span
              className="font-mono text-[11px] tabular-nums"
              style={{ color: isActive ? s.accent : "rgba(255,255,255,0.66)" }}
            >
              {String(s.id).padStart(2, "0")}
            </span>
            <span
              className="font-display text-[15px] font-medium"
              style={{ color: isActive ? "#f8fafc" : "rgba(255,255,255,0.62)" }}
            >
              {s.title}
            </span>
            {isActive && (
              <motion.div
                layoutId="active-dot"
                className="ml-auto h-1.5 w-1.5 rounded-full"
                style={{ background: s.accent }}
                transition={{ type: "spring", stiffness: 300, damping: 28 }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function RightPanel({ step, value }) {
  return (
    <motion.div
      key={step.id}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.55, ease: EASE }}
      className="absolute inset-0 flex flex-col justify-center px-10 lg:px-16"
    >
      {/* Big ghost number */}
      <div
        className="mb-4 font-display font-bold leading-none select-none"
        style={{
          fontSize: "clamp(80px, 14vw, 148px)",
          color: step.accent,
          opacity: 0.09,
          letterSpacing: "-0.04em",
        }}
      >
        {String(step.id).padStart(2, "0")}
      </div>

      {/* Title */}
      <h2
        className="font-display font-semibold leading-none"
        style={{
          fontSize: "clamp(40px, 6.5vw, 76px)",
          letterSpacing: "-0.03em",
          color: "#f8fafc",
          marginTop: "-1.5rem",
        }}
      >
        {step.title}
      </h2>

      {/* Sub */}
      <p className="mt-5 max-w-md text-[16px] leading-relaxed" style={{ color: "rgba(241,245,249,0.72)" }}>
        {step.sub}
      </p>

      {/* Value pill */}
      <div
        className="mt-8 inline-flex w-fit items-center gap-2.5 rounded-full px-5 py-2.5"
        style={{
          background: `${step.accent}12`,
          border: `1px solid ${step.accent}28`,
        }}
      >
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: step.accent, boxShadow: `0 0 8px ${step.accent}` }}
        />
        <span className="font-mono text-[14px]" style={{ color: step.accent }}>
          {value}
        </span>
      </div>
    </motion.div>
  );
}

export function ScrollStory({ mainRef, quote, botState, ledger }) {
  const sectionRef  = useRef(null);
  const rawProgress = useMotionValue(0);
  const progress    = useSpring(rawProgress, { stiffness: 50, damping: 14, restDelta: 0.001 });
  const chapterIdx  = useTransform(progress, [0, 1], [0, STEPS.length - 1]);
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    return chapterIdx.on("change", (v) => {
      setActiveStep(Math.min(STEPS.length - 1, Math.max(0, Math.round(v))));
    });
  }, [chapterIdx]);

  useEffect(() => {
    const container = mainRef?.current;
    const section   = sectionRef.current;
    if (!container || !section) return;
    const update = () => {
      const scrollable = section.offsetHeight - container.clientHeight;
      if (scrollable <= 0) return;
      const pct = Math.max(0, Math.min(1, (container.scrollTop - section.offsetTop) / scrollable));
      rawProgress.set(pct);
    };
    container.addEventListener("scroll", update, { passive: true });
    update();
    return () => container.removeEventListener("scroll", update);
  }, [mainRef, rawProgress]);

  const values = [
    quote?.price ? money(quote.price, 2) : "awaiting quote",
    `${ledger?.candidates?.length ?? "---"} candidates`,
    botState?.capital?.totalPnl != null ? money(botState.capital.totalPnl) : "---",
    String(ledger?.scoreboard?.validatedEdges ?? "---"),
    "Active",
  ];

  const currentStep = STEPS[activeStep];

  return (
    <div
      ref={sectionRef}
      className="story-scroll-track"
      style={{
        width: "100vw",
        position: "relative",
        left: "50%",
        marginLeft: "-50vw",
        marginRight: "-50vw",
      }}
    >
      {/* ── STICKY FRAME (full-bleed: spans the whole viewport width) ── */}
      <div className="glass-story story-sticky-frame w-full overflow-hidden">
        {/* Ambient glow */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `radial-gradient(ellipse 60% 70% at 75% 50%, ${currentStep.accent}09, transparent)`,
            transition: "background 0.8s ease",
          }}
        />

        {/* Desktop: sticky split index layout */}
        <div className="hidden md:flex h-full w-full">

          {/* LEFT — sticky index */}
          <div
            className="flex w-[280px] shrink-0 flex-col justify-center border-r border-white/10 px-8"
          >
            <p className="mb-8 text-[11px] font-medium text-white/55" style={{ letterSpacing: "0.1em" }}>
              The Spencer System
            </p>
            <LeftIndex activeStep={activeStep} progress={progress} />
          </div>

          {/* RIGHT — one step panel at a time */}
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 right-[44%]">
              <AnimatePresence mode="wait">
                <RightPanel key={currentStep.id} step={currentStep} value={values[activeStep]} />
              </AnimatePresence>
            </div>
            <div className="absolute inset-y-12 right-8 w-[42%]">
              <WireframeOrb accent={currentStep.accent} />
            </div>
          </div>
        </div>

        {/* Mobile: single centered step (no pinning complexity) */}
        <div className="flex md:hidden h-full flex-col items-center justify-center px-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentStep.id}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -14 }}
              transition={{ duration: 0.5, ease: EASE }}
              className="w-full text-center"
            >
              <p className="mb-2 font-mono text-[11px]" style={{ color: currentStep.accent }}>
                {String(activeStep + 1).padStart(2, "0")} / {STEPS.length}
              </p>
              <h2
                className="font-display font-semibold"
                style={{ fontSize: "clamp(36px,10vw,60px)", letterSpacing: "-0.03em", color: "#f8fafc" }}
              >
                {currentStep.title}
              </h2>
              <p className="mt-3 text-[14px] text-white/55">
                {currentStep.sub}
              </p>
              <div
                className="mx-auto mt-6 inline-flex items-center gap-2 rounded-full px-5 py-2"
                style={{ background: `${currentStep.accent}12`, border: `1px solid ${currentStep.accent}28` }}
              >
                <span className="font-mono text-[13px]" style={{ color: currentStep.accent }}>
                  {values[activeStep]}
                </span>
              </div>
            </motion.div>
          </AnimatePresence>

          {/* Dot nav */}
          <div className="absolute bottom-10 flex gap-2">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className="rounded-full transition-all duration-300"
                style={{
                  width: i === activeStep ? 20 : 6,
                  height: 6,
                  background: i === activeStep ? STEPS[i].accent : "rgba(255,255,255,0.2)",
                }}
              />
            ))}
          </div>
        </div>

        {/* Scroll progress bar — bottom */}
        <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-white/10">
          <motion.div
            className="h-full origin-left"
            style={{
              scaleX: progress,
              background: `linear-gradient(90deg, #2DD4A0, #6B8FFF)`,
            }}
          />
        </div>
      </div>
    </div>
  );
}
