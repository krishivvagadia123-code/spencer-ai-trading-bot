import { StatusCard } from "../components/StatusCard";
import { DetailsDrawer } from "../components/DetailsDrawer";
import { useState } from "react";
import { dateOnly, money, pct } from "../utils/helpers";

export function Research({ ledger, status }) {
  const [selectedID, setSelectedID] = useState(null);
  const candidates = ledger?.candidates || [];

  if (status === "loading") return <StatusCard title="Loading Ledger" message="Fetching candidate history..." />;
  if (status === "error") return <StatusCard title="Ledger Error" message="Failed to load research ledger." />;
  if (!candidates.length) return <StatusCard title="Empty Ledger" message="No research candidates found." />;

  const activeCandidate = candidates.find(c => c.candidateId === selectedID);
  const activeStage = activeCandidate?.stages?.[activeCandidate.stages.length - 1] || {};

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-light tracking-tight">Research Ledger</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {candidates.map(c => {
          const lastStage = c.stages?.[c.stages.length - 1] || {};
          const verdict = c.status || lastStage.status || "pending";
          const isFailed = ["KILLED", "REJECTED", "FAIL"].includes(String(verdict).toUpperCase());
          return (
            <button
              type="button"
              key={c.candidateId}
              onClick={() => setSelectedID(c.candidateId)}
              className={`w-full cursor-pointer rounded-xl border p-6 text-left transition-transform hover:-translate-y-1 ${isFailed ? 'border-[var(--color-failure-accent)] bg-[#fff0f2]' : 'border-[var(--color-light-border)] bg-[var(--color-surface)]'}`}
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="font-mono text-sm font-medium">{c.candidateId}</span>
                <span className="rounded bg-[rgba(0,0,0,0.05)] px-2 py-0.5 text-xs">v{c.version}</span>
              </div>
              <p className="mb-4 text-sm text-[var(--color-muted-dark-text)] line-clamp-2">{c.hypothesis}</p>
              <div className="flex items-center justify-between font-mono text-xs">
                <span className="uppercase tracking-widest">{lastStage.stage || "Unknown"}</span>
                <span className={isFailed ? "text-[var(--color-failure-accent)]" : "text-[var(--color-primary-dark-text)]"}>{verdict}</span>
              </div>
            </button>
          )
        })}
      </div>

      <DetailsDrawer open={!!selectedID} title="Candidate Details" onClose={() => setSelectedID(null)}>
        {activeCandidate && (
          <div className="space-y-6">
            <div>
              <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">ID</div>
              <div className="font-mono text-lg">{activeCandidate.candidateId} (v{activeCandidate.version})</div>
            </div>
            <div>
              <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">Hypothesis</div>
              <p className="text-sm leading-relaxed">{activeCandidate.hypothesis}</p>
            </div>
            <div>
              <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">Stage</div>
              <div className="font-mono text-sm uppercase">{activeStage.stage}</div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">Trades</div>
                <div className="font-mono">{activeStage.trades || 0}</div>
              </div>
              <div>
                <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">Gross PnL</div>
                <div className="font-mono">{money(activeStage.gross_pnl, 2)}</div>
              </div>
              <div>
                <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">Total Costs</div>
                <div className="font-mono">{money(activeStage.total_costs, 2)}</div>
              </div>
              <div>
                <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">Net Result</div>
                <div className="font-mono">{money(activeStage.net_pnl, 2)}</div>
              </div>
              <div>
                <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">Net Edge</div>
                <div className="font-mono">{pct(activeStage.net_edge_pct, 4)}</div>
              </div>
              <div>
                <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">Dataset Rows</div>
                <div className="font-mono">{activeStage.dataset?.rows ?? "N/A"}</div>
              </div>
            </div>
            <div>
              <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">Test Window</div>
              <div className="font-mono text-sm">
                {dateOnly(activeStage.dataset?.start)} to {dateOnly(activeStage.dataset?.end)}
              </div>
            </div>
            <div>
              <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted-light-text)]">Verdict</div>
              <div className={`font-mono text-sm uppercase ${String(activeCandidate.status).toUpperCase() === 'KILLED' ? 'text-[var(--color-failure-accent)]' : 'text-[var(--color-verified-accent)]'}`}>
                {activeCandidate.status || "Pending"}
                {activeCandidate.killReason ? ` — ${activeCandidate.killReason}` : ""}
              </div>
              {activeCandidate.killDate && (
                <div className="mt-2 font-mono text-xs text-[var(--color-muted-light-text)]">
                  Recorded {dateOnly(activeCandidate.killDate)}
                </div>
              )}
            </div>
          </div>
        )}
      </DetailsDrawer>
    </div>
  );
}
