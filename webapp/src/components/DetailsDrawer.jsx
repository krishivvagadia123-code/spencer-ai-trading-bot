import { motion, AnimatePresence } from "motion/react";
import { X } from "lucide-react";

export function DetailsDrawer({ open, title, onClose, children }) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 0.2 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black backdrop-blur-sm" onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[49] backdrop-blur-[2px] pointer-events-none"
          />
          <motion.div
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 200 }}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-[var(--color-elevated-black)] text-[var(--color-primary-light-text)] shadow-2xl dark-panel-glow border-l border-[rgba(255,255,255,0.1)]"
          >
            <div className="flex items-center justify-between border-b border-[var(--color-dark-border)] p-6">
              <h2 className="text-lg font-medium tracking-tight">{title}</h2>
              <button type="button" aria-label={`Close ${title}`} onClick={onClose} className="rounded-full p-2 hover:bg-[rgba(255,255,255,0.1)] transition-colors">
                <X className="h-5 w-5" />
              </button>
            </div>
            <motion.div
              initial="hidden"
              animate="visible"
              variants={{
                hidden: { opacity: 0 },
                visible: { opacity: 1, transition: { staggerChildren: 0.05, delayChildren: 0.1 } }
              }}
              className="flex-1 overflow-y-auto p-6"
            >
              <motion.div variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}>
                {children}
              </motion.div>
            </motion.div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
