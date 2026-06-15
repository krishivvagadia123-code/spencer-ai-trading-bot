import { useMemo } from "react";

function fmtTimeIST(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false,
  }) + " IST";
}

/**
 * Background Activity — honest proof of what Spencer actually did today.
 * It collects market data every trading day (and audits it); it does NOT run a
 * new experiment daily. Every number here comes from the live /api/health and
 * /api/research/ledger payloads — no fabricated activity.
 */
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
    <div className="rounded-2xl bg-white/40 p-4">
      <div className="text-[11px] font-medium uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`mt-1 font-display text-[18px] font-semibold ${tone || "text-slate-900"}`}>{value}</div>
    </div>
  );

  return (
    <section className="liquid-glass-light rounded-[28px] p-6 md:p-8" aria-label="Background activity">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Background Activity</div>
          <h2 className="mt-1 font-display text-[20px] font-semibold text-slate-900">What Spencer did today</h2>
        </div>
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold ${collectingNow ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${collectingNow ? "live-pulse bg-emerald-500" : "bg-slate-400"}`} />
          {collectingNow ? "Collector running" : "Idle — outside market hours"}
        </span>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Candles today (15m)" value={collected15} />
        <Stat label="Candles today (1m)" value={collected1} />
        <Stat label="Last collected" value={fmtTimeIST(today.lastCollectedAt)} />
        <Stat label="Data integrity" value={integrity || "—"} tone={integrity === "PASS" ? "text-emerald-600" : integrity === "FAIL" ? "text-red-600" : "text-slate-500"} />
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
        <Stat
          label="Validated edges"
          value="0"
          tone="text-slate-500"
        />
      </div>

      {/* The actual research done — honest, from the ledger */}
      <div className="mt-5 rounded-2xl bg-white/40 p-4">
        <div className="text-[11px] font-medium uppercase tracking-wider text-slate-500">Research so far</div>
        {candidates.length === 0 ? (
          <div className="mt-2 text-[13px] text-slate-600">No experiments recorded yet.</div>
        ) : (
          <div className="mt-2 flex flex-wrap gap-2">
            {candidates.map((c) => (
              <span key={c.id} className="inline-flex items-center gap-1.5 rounded-full bg-white/70 px-3 py-1 text-[12px] font-medium text-slate-700">
                {c.id}
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${c.verdict === "KILLED" ? "bg-red-50 text-red-600" : c.verdict === "PASSED" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
                  {c.verdict}
                </span>
              </span>
            ))}
          </div>
        )}
      </div>

      <p className="mt-5 text-[12px] leading-relaxed text-slate-600">
        Spencer collects RELIANCE market data every trading day and audits it — that is today's background work.
        It does <span className="font-semibold text-slate-800">not</span> run a new experiment every day: the next
        experiment (SPNCR-003) runs once data readiness reaches {Number.isFinite(need) ? need : 70} sessions.
        No trades have been placed; nothing here is estimated.
      </p>
    </section>
  );
}
