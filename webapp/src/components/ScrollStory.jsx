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
  { id: 1, title: "Observe", sub: "Real-time NSE price feed for RELIANCE", accent: "#a78bfa" },
  { id: 2, title: "Research", sub: "Active hypothesis pipeline and candidate list", accent: "#c4b5fd" },
  { id: 3, title: "Test", sub: "Paper trading performance under real conditions", accent: "#a78bfa" },
  { id: 4, title: "Confirm", sub: "Statistical edge validated before any trade", accent: "#c4b5fd" },
  { id: 5, title: "Govern", sub: "Paper-only capital protection always active", accent: "#a78bfa" },
];

function LeftIndex({ activeStep, progress }) {
  return (
    <div className="relative flex flex-col justify-center gap-1 py-8">
      <div className="absolute bottom-8 left-0 top-8 w-px bg-white/10">
        <motion.div
          className="h-full w-full origin-top bg-white/40"
          style={{ scaleY: progress }}
        />
      </div>

      {STEPS.map((step, index) => {
        const isActive = index === activeStep;
        return (
          <div
            key={step.id}
            className="flex items-center gap-5 py-3 pl-6 transition-opacity duration-500"
            style={{ opacity: isActive ? 1 : 0.34 }}
          >
            <span
              className="font-mono text-[11px] tabular-nums"
              style={{ color: isActive ? step.accent : "rgba(255,255,255,0.62)" }}
            >
              {String(step.id).padStart(2, "0")}
            </span>
            <span
              className="font-display text-[15px] font-medium"
              style={{ color: isActive ? "#f8fafc" : "rgba(255,255,255,0.62)" }}
            >
              {step.title}
            </span>
            {isActive && (
              <motion.div
                layoutId="active-dot"
                className="ml-auto h-1.5 w-1.5 rounded-full"
                style={{ background: step.accent }}
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
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -14 }}
      transition={{ duration: 0.45, ease: EASE }}
      className="absolute inset-0 flex flex-col justify-center px-10 lg:px-16"
    >
      <div
        className="mb-4 select-none font-display font-bold leading-none"
        style={{
          fontSize: "clamp(80px, 14vw, 148px)",
          color: step.accent,
          opacity: 0.08,
          letterSpacing: "-0.04em",
        }}
      >
        {String(step.id).padStart(2, "0")}
      </div>

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

      <p className="mt-5 max-w-md text-[16px] leading-relaxed text-slate-400">
        {step.sub}
      </p>

      <div
        className="mt-8 inline-flex w-fit items-center gap-2.5 rounded-full px-5 py-2.5"
        style={{
          background: `${step.accent}12`,
          border: `1px solid ${step.accent}28`,
        }}
      >
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: step.accent }} />
        <span className="font-mono text-[14px]" style={{ color: step.accent }}>
          {value}
        </span>
      </div>
    </motion.div>
  );
}

export function ScrollStory({ mainRef, quote, botState, ledger }) {
  const sectionRef = useRef(null);
  const rawProgress = useMotionValue(0);
  const progress = useSpring(rawProgress, { stiffness: 50, damping: 14, restDelta: 0.001 });
  const chapterIdx = useTransform(progress, [0, 1], [0, STEPS.length - 1]);
  const [activeStep, setActiveStep] = useState(0);
  // Measured, not guessed: the sticky frame must equal the real scroll-viewport
  // height so it pins cleanly, and the track is a multiple of it so each step
  // gets ~one screen of scroll. Measuring (vs a magic-number calc tied to the
  // header size) keeps this correct even if the layout/header/UI changes.
  const [dims, setDims] = useState({ frame: 0, track: 0 });

  useEffect(() => {
    return chapterIdx.on("change", (v) => {
      setActiveStep(Math.min(STEPS.length - 1, Math.max(0, Math.round(v))));
    });
  }, [chapterIdx]);

  useEffect(() => {
    const container = mainRef?.current;
    if (!container) return undefined;
    const measure = () => {
      const h = container.clientHeight;
      if (h > 0) setDims({ frame: h, track: h * STEPS.length });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(container);
    return () => ro.disconnect();
  }, [mainRef]);

  useEffect(() => {
    const container = mainRef?.current;
    const section = sectionRef.current;
    if (!container || !section) return undefined;
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
    `${ledger?.candidates?.length ?? "—"} candidates`,
    botState?.capital?.totalPnl != null ? money(botState.capital.totalPnl) : "—",
    String(ledger?.scoreboard?.validatedEdges ?? "—"),
    "Active",
  ];

  const currentStep = STEPS[activeStep];

  return (
    <div
      ref={sectionRef}
      className="story-scroll-track relative"
      style={dims.track ? { height: dims.track } : undefined}
    >
      <div
        className="glass-story story-sticky-frame w-full overflow-hidden rounded-[24px]"
        style={dims.frame ? { height: dims.frame } : undefined}
      >
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background: `radial-gradient(ellipse 60% 70% at 75% 50%, ${currentStep.accent}09, transparent)`,
            transition: "background 0.8s ease",
          }}
        />

        <div className="hidden h-full w-full md:flex">
          <div className="flex w-[280px] shrink-0 flex-col justify-center border-r border-white/10 px-8">
            <p className="mb-8 text-[11px] font-medium uppercase tracking-[0.1em] text-white/55">
              The Spencer System
            </p>
            <LeftIndex activeStep={activeStep} progress={progress} />
          </div>

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

        <div className="flex h-full flex-col items-center justify-center px-8 md:hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentStep.id}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -14 }}
              transition={{ duration: 0.45, ease: EASE }}
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

        <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-white/10">
          <motion.div
            className="h-full origin-left"
            style={{
              scaleX: progress,
              background: "linear-gradient(90deg, #7c5cff, #c4b5fd)",
            }}
          />
        </div>
      </div>
    </div>
  );
}
