import { money } from "../utils/helpers";

export function Funds({ botState }) {
  const cap = botState?.capital || {};

  return (
    <div className="liquid-glass-light page-card rounded-[24px] p-6 md:p-8">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="metric-label">Capital</div>
          <h2 className="mt-2 font-display text-[28px] font-semibold tracking-tight">Paper Capital</h2>
        </div>
        <span className="reference-pill">Paper-only</span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="page-subcard rounded-xl p-6">
          <div className="metric-label">Allocated Budget</div>
          <div className="font-mono text-3xl">{money(cap.budget)}</div>
        </div>
        <div className="page-subcard rounded-xl p-6">
          <div className="metric-label">Available Cash</div>
          <div className="font-mono text-3xl">{money(cap.cash)}</div>
        </div>
      </div>
      <div className="page-subcard mt-5 rounded-lg p-6 text-sm">
        <h3 className="mb-2 font-medium">Capital Guard</h3>
        <p>Spencer uses a strictly enforced paper-only budget for forward testing.</p>
      </div>
    </div>
  );
}
