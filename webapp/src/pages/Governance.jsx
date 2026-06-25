export function Governance({ botState }) {
  // Capabilities live at the top level of bot state (botState.capabilities),
  // not under governance (which only holds roles/principle).
  const gov = botState?.capabilities || {};
  const mode = gov.mode || "Unknown";
  const actions = gov.actions || {};

  return (
    <div className="liquid-glass-light page-card rounded-[24px] p-6 md:p-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="metric-label">Safety Gate</div>
          <h2 className="mt-2 font-display text-[28px] font-semibold tracking-tight">Governance Matrix</h2>
        </div>
        <div className="reference-pill font-mono uppercase">
          Mode: <span className="text-[var(--color-info-accent)]">{mode}</span>
        </div>
      </div>

      <div className="space-y-4">
        {Object.entries(actions).map(([key, a]) => (
          <div key={key} className="page-subcard flex items-start justify-between gap-5 rounded-xl p-5">
            <div className="min-w-0">
              <h3 className="font-medium">{a.label}</h3>
              <p className="mt-1 text-sm">{a.reasons?.[0] || "No reason provided"}</p>
              <div className="mt-3 font-mono text-xs uppercase">Owner: {a.owner}</div>
            </div>
            <div className={`shrink-0 rounded px-3 py-1 font-mono text-xs font-bold uppercase ${a.allowed ? 'bg-[rgba(45,212,160,0.12)] text-[var(--color-verified-accent)]' : 'bg-[rgba(240,112,128,0.12)] text-[var(--color-failure-accent)]'}`}>
              {a.allowed ? "Allowed" : "Blocked"}
            </div>
          </div>
        ))}
        {!Object.keys(actions).length && (
          <div className="page-subcard rounded-xl p-5 text-sm">
            No capability data is currently available from the backend.
          </div>
        )}
      </div>
    </div>
  );
}
