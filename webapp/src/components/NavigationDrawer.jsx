import { X, LayoutDashboard, ListOrdered, IndianRupee, Gavel, BrainCircuit, ShieldAlert, User, CircleHelp } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

// Clubbed navigation: Orders also holds Holdings + Positions; Brain also holds
// Research; Funds also holds Trade Tracker.
const PAGES = [
  { id: "Dashboard", icon: LayoutDashboard },
  { id: "WhatIsSpencer", label: "What is Spencer", icon: CircleHelp },
  { id: "Orders", icon: ListOrdered },
  { id: "Funds", icon: IndianRupee },
  { id: "Bids", icon: Gavel },
  { id: "Brain", icon: BrainCircuit },
  { id: "Governance", icon: ShieldAlert },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.04, delayChildren: 0.1 }
  }
};

const itemVariants = {
  hidden: { opacity: 0, x: -20 },
  visible: { opacity: 1, x: 0 }
};

export function NavigationDrawer({ open, activePage, onNavigate, onClose }) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 0.5 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.aside
            initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 200 }}
            className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-[var(--color-elevated-black)] text-[var(--color-primary-light-text)] shadow-[24px_0_80px_rgba(0,0,0,0.5)] overflow-hidden"
          >
            {/* Subtle radial gradient */}
            <div className="absolute top-0 left-0 w-[300px] h-[300px] bg-white opacity-[0.02] blur-[80px] pointer-events-none" />

            <div className="relative flex items-center justify-between border-b border-[var(--color-dark-border)] p-5 z-10">
              <div>
                <div className="font-medium tracking-tight">Trader</div>
                <div className="text-xs text-[var(--color-muted-light-text)] font-mono tracking-widest uppercase mt-0.5">Spencer Studio</div>
              </div>
              <button type="button" aria-label="Close navigation" onClick={onClose} className="rounded-full p-2 hover:bg-[rgba(255,255,255,0.1)] transition-colors">
                <X className="h-4 w-4" />
              </button>
            </div>

            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              className="relative flex-1 overflow-y-auto p-4 z-10"
            >
              {PAGES.map(({ id, label, icon: Icon }) => {
                const isActive = activePage === id;
                return (
                  <motion.button
                    variants={itemVariants}
                    key={id}
                    onClick={() => onNavigate(id)}
                    className={`group relative mb-1.5 flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm transition-all ${isActive ? 'text-white bg-[rgba(255,255,255,0.05)]' : 'text-[var(--color-muted-light-text)] hover:bg-[rgba(255,255,255,0.03)] hover:text-white'}`}
                  >
                    {isActive && (
                      <motion.div
                        layoutId="activeNavRail"
                        className="absolute left-0 top-1/2 -translate-y-1/2 h-3/4 w-1 bg-[var(--color-verified-accent)] rounded-r-md"
                        transition={{ type: "spring", stiffness: 300, damping: 30 }}
                      />
                    )}
                    <Icon className={`h-4 w-4 ${isActive ? 'text-[var(--color-verified-accent)]' : 'group-hover:text-white'}`} />
                    <span className="font-medium">{label || id}</span>
                  </motion.button>
                );
              })}

              <div className="my-5 h-px bg-[var(--color-dark-border)]" />

              <motion.button
                variants={itemVariants}
                onClick={() => onNavigate("Profile")}
                className={`group relative flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm transition-all ${activePage === "Profile" ? 'text-white bg-[rgba(255,255,255,0.05)]' : 'text-[var(--color-muted-light-text)] hover:bg-[rgba(255,255,255,0.03)] hover:text-white'}`}
              >
                {activePage === "Profile" && (
                  <motion.div
                    layoutId="activeNavRail"
                    className="absolute left-0 top-1/2 -translate-y-1/2 h-3/4 w-1 bg-[var(--color-verified-accent)] rounded-r-md"
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                  />
                )}
                <User className="h-4 w-4" />
                <span className="font-medium">Profile</span>
              </motion.button>
            </motion.div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
