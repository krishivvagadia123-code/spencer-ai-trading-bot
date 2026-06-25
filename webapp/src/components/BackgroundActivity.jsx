import { useMemo } from "react";

function fmtTimeIST(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })} IST`;
}

export function BackgroundActivity({ health, ledger }) {
  const today = health?.todayActivity || {};
  const readiness = health?.readiness || {};
  const integrity = health?.integrity?.overall;

  const candidates = useMemo(() => {
    const list = Array.isArray(ledger?.candidates) ? ledger.candidates : [];
    return list.map((c) => ({
      id: c.candidateId || c.id || "—",
      verdict: String(c.status || c.verdict || "—").toUpperCase(),
    }));
  }, [ledger]);

  const have = Number(readiness.fifteenMinSessions);
  const need = Number(readiness.required);
  const remaining = Number(readiness.sessionsRemaining);
  const collected15 = Number(today.candles15m) || 0;
  const collected1 = Number(today.candles1m) || 0;
  const collectingNow = collected15 > 0 || collected1 > 0;

  const Stat = ({ label, value, tone }) => (
    <div className="background-stat-card rounded-[18px] p-4">
      <div className="metric-label">{label}</div>
      <div className={`mt-1 font-display text-[18px] font-semibold ${tone || "text-slate-100"}`}>{value}</div>
    </div>
  );

  return (
    <section className="liquid-glass-light rounded-[22px] p-6 md:p-8" aria-label="Background activity">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="metric-label">Background Activity</div>
          <h2 className="mt-1 font-display text-[20px] font-semibold text-slate-100">What Spencer did today</h2>
        </div>
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold ${collectingNow ? "bg-violet-500/10 text-violet-200" : "bg-white/[0.06] text-slate-400"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${collectingNow ? "live-pulse bg-violet-300" : "bg-slate-500"}`} />
          {collectingNow ? "Collector running" : "Idle - outside market hours"}
        </span>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Candles today (15m)" value={collected15} />
        <Stat label="Candles today (1m)" value={collected1} />
        <Stat label="Last collected" value={fmtTimeIST(today.lastCollectedAt)} />
        <Stat label="Data integrity" value={integrity || "—"} tone={integrity === "PASS" ? "text-violet-200" : integrity === "FAIL" ? "text-rose-300" : "text-slate-400"} />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Data readiness"
          value={Number.isFinite(have) && Number.isFinite(need) ? `${have} / ${need}` : "—"}
        />
        <Stat
          label="Sessions to next test"
          value={Number.isFinite(remaining) ? remaining : "—"}
        />
        <Stat label="Experiments run" value={candidates.length} />
        <Stat label="Validated edges" value="0" tone="text-slate-400" />
      </div>

      <div className="background-stat-card mt-5 rounded-[18px] p-4">
        <div className="metric-label">Research so far</div>
        {candidates.length === 0 ? (
          <div className="mt-2 text-[13px] text-slate-400">No experiments recorded yet.</div>
        ) : (
          <div className="mt-2 flex flex-wrap gap-2">
            {candidates.map((c) => (
              <span key={c.id} className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.07] px-3 py-1 text-[12px] font-medium text-slate-300">
                {c.id}
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${c.verdict === "KILLED" ? "bg-rose-500/10 text-rose-300" : c.verdict === "PASSED" ? "bg-violet-500/10 text-violet-200" : "bg-white/[0.08] text-slate-400"}`}>
                  {c.verdict}
                </span>
              </span>
            ))}
          </div>
        )}
      </div>

      <p className="mt-5 text-[12px] leading-relaxed text-slate-400">
        Spencer collects RELIANCE market data every trading day and audits it. It does not run a new
        experiment every day: the next experiment (SPNCR-003) runs once data readiness reaches{" "}
        {Number.isFinite(need) ? need : 70} sessions. No trades have been placed; nothing here is estimated.
      </p>
    </section>
  );
}
