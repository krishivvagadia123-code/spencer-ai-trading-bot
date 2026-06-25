import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";

const STAGES = [
  {
    id: 1,
    label: "Observe",
    color: "#a78bfa",
    tint: "rgba(124, 92, 255, 0.14)",
    desc: "Ingest verified RELIANCE price and volume from the market feed.",
  },
  {
    id: 2,
    label: "Hypothesis",
    color: "#c4b5fd",
    tint: "rgba(196, 181, 253, 0.12)",
    desc: "Shape one falsifiable edge from the signal, not from a narrative.",
  },
  {
    id: 3,
    label: "Test",
    color: "#b6a6e8",
    tint: "rgba(166, 146, 214, 0.12)",
    desc: "Paper-trade the hypothesis under real conditions with no invented results.",
  },
  {
    id: 4,
    label: "Costs",
    color: "#a39bb8",
    tint: "rgba(163, 155, 184, 0.12)",
    desc: "Subtract fees and slippage before calling any result an edge.",
  },
  {
    id: 5,
    label: "Confirm",
    color: "#8b7cf6",
    tint: "rgba(139, 124, 246, 0.13)",
    desc: "Keep only evidence that remains profitable after costs.",
  },
];

export function SpencerCore3D() {
  const reduceMotion = useReducedMotion();
  const [activeIndex, setActiveIndex] = useState(0);
  const activeStage = STAGES[activeIndex];

  return (
    <div
      className="liquid-glass-panel relative min-h-[500px] overflow-hidden rounded-[34px] p-5 sm:min-h-[440px] sm:p-8 lg:p-10"
      style={{
        background: `
          radial-gradient(circle at 14% 18%, ${activeStage.tint}, transparent 34%),
          radial-gradient(circle at 86% 78%, ${activeStage.tint}, transparent 32%),
          linear-gradient(145deg, rgba(255,255,255,0.28), rgba(255,255,255,0.07))
        `,
      }}
    >
      <div className="relative z-10 flex h-full flex-col">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-black/45">
              Spencer Research Core
            </p>
            <p className="mt-2 max-w-md text-[13px] leading-relaxed text-black/55">
              One evidence loop shaped by verified data and paper-only discipline.
            </p>
          </div>
          <div className="liquid-glass-chip hidden sm:flex">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-verified-accent)]" />
            Inspection mode
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center py-7 sm:py-5">
          <motion.div
            key={activeStage.id}
            className="glass-shimmer flex min-h-[210px] w-full max-w-[430px] flex-col items-center justify-center overflow-hidden rounded-[32px] border px-7 py-7 text-center sm:px-10"
            style={{
              borderColor: `${activeStage.color}55`,
              background: `linear-gradient(145deg, rgba(255,255,255,0.3), ${activeStage.tint})`,
              boxShadow: `inset 0 1px 0 rgba(255,255,255,0.95), 0 18px 48px ${activeStage.tint}`,
            }}
            initial={reduceMotion ? false : { opacity: 0.35, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
          >
            <span
              className="font-mono text-[10px] font-semibold uppercase tracking-[0.24em]"
              style={{ color: activeStage.color }}
            >
              0{activeStage.id} / 05
            </span>
            <h3 className="mt-3 font-display text-[clamp(27px,4vw,36px)] font-semibold leading-none tracking-[-0.03em] text-black/85">
              {activeStage.label}
            </h3>
            <p className="mt-4 max-w-[330px] text-[13px] leading-6 text-black/60">
              {activeStage.desc}
            </p>
          </motion.div>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {STAGES.map((stage, index) => {
            const isActive = activeIndex === index;
            return (
              <motion.button
                key={stage.id}
                type="button"
                onClick={() => setActiveIndex(index)}
                onFocus={() => setActiveIndex(index)}
                aria-pressed={isActive}
                className="glass-shimmer relative flex min-h-[68px] flex-col items-center justify-center overflow-hidden rounded-[18px] border px-2 py-3 text-center outline-none transition-[background-color,border-color,box-shadow,color] duration-200"
                style={{
                  borderColor: isActive ? `${stage.color}55` : "rgba(255,255,255,0.5)",
                  backgroundColor: isActive ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.08)",
                  boxShadow: isActive
                    ? "inset 0 1px 0 rgba(255,255,255,0.95), 0 8px 20px rgba(31,38,57,0.1)"
                    : "inset 0 1px 0 rgba(255,255,255,0.5)",
                }}
                whileTap={reduceMotion ? undefined : { scale: 0.98 }}
                transition={{ duration: 0.15 }}
              >
                <span className="font-mono text-[9px] tracking-[0.16em] text-black/35">
                  0{stage.id}
                </span>
                <span
                  className="mt-1 text-[10px] font-semibold uppercase tracking-[0.09em] sm:text-[11px]"
                  style={{ color: isActive ? stage.color : "rgba(15,15,15,0.58)" }}
                >
                  {stage.label}
                </span>
              </motion.button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
