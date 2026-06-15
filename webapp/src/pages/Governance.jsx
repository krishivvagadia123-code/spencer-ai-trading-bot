export function Governance({ botState }) {
  // Capabilities live at the top level of bot state (botState.capabilities),
  // not under governance (which only holds roles/principle).
  const gov = botState?.capabilities || {};
  const mode = gov.mode || "Unknown";
  const actions = gov.actions || {};

  return (
    <div className="liquid-glass-light rounded-[24px] p-10 text-[var(--color-primary-dark-text)]">
      <div className="mb-10">
        <h2 className="text-3xl font-light tracking-tight">Governance Matrix</h2>
        <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-black/10 bg-black/[0.03] px-4 py-1.5 font-mono text-sm uppercase">
          Mode: <span className="text-[var(--color-info-accent)]">{mode}</span>
        </div>
      </div>

      <div className="space-y-4">
        {Object.entries(actions).map(([key, a]) => (
          <div key={key} className="flex items-start justify-between rounded-xl border border-black/10 bg-black/[0.03] p-5">
            <div>
              <h3 className="font-medium">{a.label}</h3>
              <p className="mt-1 text-sm text-black/55">{a.reasons?.[0] || "No reason provided"}</p>
              <div className="mt-3 font-mono text-xs uppercase text-[var(--color-muted-dark-text)]">Owner: {a.owner}</div>
            </div>
            <div className={`shrink-0 rounded px-3 py-1 font-mono text-xs font-bold uppercase ${a.allowed ? 'bg-[rgba(45,212,160,0.12)] text-[var(--color-verified-accent)]' : 'bg-[rgba(240,112,128,0.12)] text-[var(--color-failure-accent)]'}`}>
              {a.allowed ? "Allowed" : "Blocked"}
            </div>
          </div>
        ))}
        {!Object.keys(actions).length && (
          <div className="rounded-xl border border-black/10 bg-black/[0.03] p-5 text-sm text-black/55">
            No capability data is currently available from the backend.
          </div>
        )}
      </div>
    </div>
  );
}
