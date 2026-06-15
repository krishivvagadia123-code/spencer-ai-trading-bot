import { motion, useReducedMotion } from "motion/react";

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1];

const SPAN_CLASSES = {
  1: "md:col-span-1",
  2: "md:col-span-2",
  3: "md:col-span-3",
};

const CARDS = [
  { title: "Capital Guard", desc: "Strict budget limits and continuous portfolio monitoring.", span: 2, bg: "dark", page: "Funds" },
  { title: "One-Stock Doctrine", desc: "Singular focus on RELIANCE for maximum statistical edge.", span: 1, bg: "white", page: "Dashboard" },
  { title: "Brain Check", desc: "Technical indicators and price signals.", span: 1, bg: "white", page: "Brain" },
  { title: "Research Ledger", desc: "Historical backtests and forward validation tracking.", span: 2, bg: "dark", page: "Brain" },
  { title: "Backend Trust", desc: "Zero fake metrics. Real connections only.", span: 1, bg: "dark", page: "Governance" },
  { title: "Market Data", desc: "Live tick-level NSE price quotes and volume.", span: 1, bg: "white", page: "Dashboard" },
  { title: "Trade Journal", desc: "Immutable paper order history.", span: 1, bg: "white", page: "Funds" },
  { title: "Governance", desc: "Oversight protocol on AI trading capabilities.", span: 3, bg: "dark", page: "Governance" },
];

function BentoCard({ card, index, onNavigate }) {
  const reduceMotion = useReducedMotion();
  const isDark = card.bg === "dark";

  return (
    <motion.button
      type="button"
      initial={reduceMotion ? false : { opacity: 0, y: 22, scale: 0.985 }}
      whileInView={{ opacity: 1, y: 0, scale: 1 }}
      viewport={{ once: true, margin: "-40px" }}
      whileHover={reduceMotion ? undefined : { y: -4, scale: 1.005 }}
      whileTap={reduceMotion ? undefined : { scale: 0.99 }}
      transition={{
        duration: 0.55,
        delay: index * 0.045,
        ease: EASE_OUT_EXPO,
      }}
      onClick={() => onNavigate(card.page)}
      className={`module-glass-card module-glass-card--${isDark ? "dark" : "light"} ${SPAN_CLASSES[card.span]} relative min-h-[154px] overflow-hidden rounded-[24px] p-8 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-info-accent)] focus-visible:ring-offset-2`}
    >
      <span className="relative z-10 flex h-full flex-col justify-between">
        <span>
          <span className="mb-2.5 block font-display text-[17px] font-semibold tracking-[-0.01em] text-slate-950">
            {card.title}
          </span>
          <span className="block text-[13px] leading-relaxed text-slate-700">
            {card.desc}
          </span>
        </span>

        <span
          className="mt-6 flex items-center gap-2 text-[9px] font-semibold uppercase tracking-[0.18em] text-slate-600"
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: isDark ? "#5579ea" : "#18b98b" }}
          />
          Open module
        </span>
      </span>
    </motion.button>
  );
}

export function BentoGrid({ onNavigate }) {
  return (
    <div className="module-glass-grid grid grid-cols-1 gap-4 md:grid-cols-4">
      {CARDS.map((card, index) => (
        <BentoCard key={card.title} card={card} index={index} onNavigate={onNavigate} />
      ))}
    </div>
  );
}
