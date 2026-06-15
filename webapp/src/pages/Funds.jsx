import { money } from "../utils/helpers";

export function Funds({ botState }) {
  const cap = botState?.capital || {};

  return (
    <div className="liquid-glass-light mx-auto max-w-2xl rounded-[24px] p-10">
      <h2 className="mb-8 text-2xl font-light tracking-tight">Paper Capital</h2>
      <div className="grid gap-6 sm:grid-cols-2">
        <div className="rounded-xl bg-[rgba(0,0,0,0.02)] p-6">
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Allocated Budget</div>
          <div className="font-mono text-3xl">{money(cap.budget)}</div>
        </div>
        <div className="rounded-xl bg-[rgba(0,0,0,0.02)] p-6">
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Available Cash</div>
          <div className="font-mono text-3xl">{money(cap.cash)}</div>
        </div>
      </div>
      <div className="mt-8 rounded-lg bg-[var(--color-primary-black)] p-6 text-sm text-[var(--color-primary-light-text)]">
        <h3 className="mb-2 font-medium">Capital Guard</h3>
        <p className="text-[var(--color-muted-light-text)]">Spencer uses a strictly enforced paper-only budget for forward testing.</p>
      </div>
    </div>
  );
}
