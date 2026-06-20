import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { BrainCircuit, X, Send } from "lucide-react";
import { SPENCER_API_BASE } from "../utils/constants";

export function SpencerChat({ open, onClose }) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Ask about Spencer's doctrine, research, decisions, data readiness, failures, or open questions. Answers are grounded in Obsidian notes.",
      citations: [],
    },
  ]);

  const submit = async (event) => {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt || sending) return;
    setMessages((current) => [...current, { role: "user", text: prompt, citations: [] }]);
    setInput("");
    setSending(true);
    try {
      const response = await fetch(`${SPENCER_API_BASE}/api/ai/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Spencer-Confirm": import.meta.env.VITE_SPENCER_WRITE_TOKEN || "",
        },
        body: JSON.stringify({ prompt, temperature: 0.2, maxOutputTokens: 700 }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Spencer could not answer");
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: data.text,
          citations: data.citations || [],
          mode: data.mode,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { role: "assistant", text: error.message || "Spencer could not answer.", citations: [] },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 25, stiffness: 200 }}
          className="fixed inset-y-0 right-0 z-40 flex w-80 flex-col border-l border-[var(--color-light-border)] bg-[var(--color-surface)] shadow-2xl"
        >
          <div className="flex items-center justify-between border-b border-[var(--color-light-border)] p-4">
            <div>
              <h3 className="flex items-center gap-2 font-medium"><BrainCircuit className="h-4 w-4" /> Spencer Chat</h3>
              <div className="mt-1 text-[10px] uppercase tracking-wider text-black/40">Obsidian grounded</div>
            </div>
            <button onClick={onClose} className="rounded-full p-1.5 hover:bg-[var(--color-light-border)]">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="soft-scroll flex-1 space-y-3 overflow-y-auto p-4">
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`rounded-xl p-3 text-sm leading-relaxed ${
                  message.role === "user"
                    ? "ml-8 bg-blue-600 text-white"
                    : "mr-4 border border-black/10 bg-white/70 text-black/70"
                }`}
              >
                <div className="whitespace-pre-wrap">{message.text}</div>
                {!!message.citations?.length && (
                  <div className="mt-3 border-t border-black/10 pt-2">
                    <div className="text-[10px] uppercase tracking-wider text-black/35">Sources</div>
                    {message.citations.map((citation) => (
                      <div key={citation.path} className="mt-1 font-mono text-[10px] text-black/45">
                        {citation.wikilink}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {sending && <div className="text-xs text-black/40">Searching Obsidian...</div>}
          </div>
          <div className="border-t border-[var(--color-light-border)] p-4">
            <form onSubmit={submit} className="flex items-center rounded-lg border border-[var(--color-light-border)] bg-white px-3 py-2">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                className="flex-1 bg-transparent text-sm outline-none"
                placeholder="Ask the brain..."
              />
              <button disabled={sending || !input.trim()} className="p-1 disabled:opacity-30" aria-label="Send">
                <Send className="h-4 w-4 text-[var(--color-muted-dark-text)]" />
              </button>
            </form>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
