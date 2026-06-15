import { motion, AnimatePresence } from "motion/react";
import { X, Send } from "lucide-react";

export function SpencerChat({ open, onClose }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 25, stiffness: 200 }}
          className="fixed inset-y-0 right-0 z-40 flex w-80 flex-col border-l border-[var(--color-light-border)] bg-[var(--color-surface)] shadow-2xl"
        >
          <div className="flex items-center justify-between border-b border-[var(--color-light-border)] p-4">
            <h3 className="font-medium">Spencer Chat</h3>
            <button onClick={onClose} className="rounded-full p-1.5 hover:bg-[var(--color-light-border)]">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 p-4">
            <div className="rounded-lg bg-[var(--color-primary-black)] p-4 text-sm text-[var(--color-primary-light-text)]">
              No approved chat endpoint is configured. Use Brain Check for real research metrics.
            </div>
          </div>
          <div className="border-t border-[var(--color-light-border)] p-4">
            <div className="flex items-center rounded-lg border border-[var(--color-light-border)] bg-white px-3 py-2 opacity-50">
              <input disabled className="flex-1 bg-transparent text-sm outline-none" placeholder="Chat disabled..." />
              <Send className="h-4 w-4 text-[var(--color-muted-dark-text)]" />
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}