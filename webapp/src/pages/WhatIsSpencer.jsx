import { motion } from "motion/react";
import { BentoGrid } from "../components/BentoGrid";
import { ScrollStory } from "../components/ScrollStory";
import { SpencerCore3D } from "../components/SpencerCore3D";

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

export function WhatIsSpencer({
  mainRef,
  quote,
  botState,
  ledger,
  onNavigate,
}) {
  return (
    <div className="-mb-6 md:-mb-10">
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
        <BentoGrid onNavigate={onNavigate} />
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

      {/* ── SPENCER SYSTEM ─────────────────────────────────────────── */}
      <div className="mt-36">
        <ScrollStory mainRef={mainRef} quote={quote} botState={botState} ledger={ledger} />
      </div>
    </div>
  );
}
