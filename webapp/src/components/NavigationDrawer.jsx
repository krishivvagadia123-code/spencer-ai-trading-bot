import { motion } from "motion/react";

const PAGES = [
  { id: "Dashboard" },
  { id: "Profile" },
  { id: "Orders" },
  { id: "Funds" },
  { id: "Bids" },
  { id: "Brain" },
  { id: "Governance" },
  { id: "WhatIsSpencer", label: "What is Spencer" },
];

function NavItem({ page, activePage, onNavigate, compact = false }) {
  const isActive = activePage === page.id;
  const label = page.label || page.id;

  if (compact) {
    return (
      <button
        type="button"
        onClick={() => onNavigate(page.id)}
        className={`flex min-w-[68px] flex-col items-center justify-center gap-1 rounded-2xl px-3 py-2 text-[10px] font-semibold transition ${
          isActive ? "bg-[var(--theme-accent)] text-white shadow-[0_10px_26px_rgba(124,92,255,0.22)]" : "text-slate-500"
        }`}
      >
        <span className="max-w-[72px] truncate">{label}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onNavigate(page.id)}
      className={`group relative flex w-full items-center rounded-xl px-4 py-3 text-left text-[13px] font-semibold transition ${
        isActive
          ? "bg-[var(--theme-accent)] text-white shadow-[0_16px_38px_rgba(124,92,255,0.24)]"
          : "text-zinc-400 hover:bg-white/[0.07] hover:text-zinc-100"
      }`}
    >
      {isActive && (
        <motion.span
          layoutId="sidebarActiveGlow"
          className="absolute inset-0 rounded-xl bg-white/10"
          transition={{ type: "spring", stiffness: 340, damping: 34 }}
        />
      )}
      <span className="relative">{label}</span>
    </button>
  );
}

export function NavigationDrawer({ activePage, onNavigate }) {
  return (
    <>
      <aside className="spencer-sidebar hidden h-dvh w-[240px] shrink-0 flex-col px-6 py-8 text-white lg:flex">
        <div className="mb-10">
          <div className="logo-font text-[25px] leading-none tracking-[-0.04em]">Spencer</div>
          <div className="mt-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-zinc-500">
            AI Trading
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-2">
          {PAGES.map((page) => (
            <NavItem key={page.id} page={page} activePage={activePage} onNavigate={onNavigate} />
          ))}
        </nav>

        <div className="mt-8 rounded-[24px] border border-white/10 bg-white/[0.04] p-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
            Doctrine
          </div>
          <div className="mt-2 text-[13px] font-semibold text-white">Paper-only RELIANCE</div>
          <p className="mt-2 text-[11px] leading-relaxed text-zinc-400">
            Real data. No broker execution. No fake values.
          </p>
        </div>

        <button
          type="button"
          className="mt-5 inline-flex items-center justify-center gap-2 rounded-full bg-[var(--theme-accent)] px-4 py-3 text-[12px] font-bold text-white shadow-[0_16px_38px_rgba(124,92,255,0.24)]"
          aria-label="Paper mode only"
        >
          PAPER MODE
        </button>
      </aside>

      <nav className="fixed inset-x-3 bottom-3 z-40 flex items-center gap-2 overflow-x-auto rounded-[26px] border border-white/10 bg-[rgba(12,13,22,0.92)] p-2 shadow-[0_20px_60px_rgba(3,4,12,0.35)] backdrop-blur-md lg:hidden">
        {PAGES.map((page) => (
          <NavItem key={page.id} page={page} activePage={activePage} onNavigate={onNavigate} compact />
        ))}
      </nav>
    </>
  );
}
