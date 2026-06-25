import { motion } from "motion/react";
import { BentoGrid } from "../components/BentoGrid";
import { ScrollStory } from "../components/ScrollStory";
import { SpencerCore3D } from "../components/SpencerCore3D";

const EASE = [0.16, 1, 0.3, 1];

function Reveal({ children, delay = 0, className = "" }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

function SceneHeading({ label, title, sub }) {
  return (
    <div>
      {label && (
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.45, ease: EASE }}
          className="metric-label"
        >
          {label}
        </motion.p>
      )}
      {title && (
        <motion.h2
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: 0.05, ease: EASE }}
          className="mt-2 font-display text-[clamp(28px,4vw,42px)] font-semibold leading-tight text-slate-100"
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
          transition={{ duration: 0.5, delay: 0.1, ease: EASE }}
          className="mt-3 max-w-md text-[15px] leading-relaxed text-slate-400"
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
    <div className="what-spencer-page space-y-8 pb-8">
      <div className="module-glass-section rounded-[24px] p-5 md:p-8">
        <div className="module-glass-heading mb-8 max-w-xl rounded-[22px] p-6 md:p-8">
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

      <div className="research-core-section relative overflow-hidden rounded-[24px] p-5 md:p-8">
        <div className="relative z-10">
          <div className="liquid-glass-heading mb-8 max-w-xl rounded-[22px] p-6 md:p-8">
            <Reveal>
              <SceneHeading
                label="Research Core"
                title="The instrument panel"
                sub="A compact view of the research pipeline from observation to validation."
              />
            </Reveal>
          </div>
          <Reveal delay={0.08}>
            <SpencerCore3D />
          </Reveal>
        </div>
      </div>

      <ScrollStory mainRef={mainRef} quote={quote} botState={botState} ledger={ledger} />
    </div>
  );
}
