import { RefreshCw } from "lucide-react";

const statusTone = {
  PASS: "var(--color-verified-accent)",
  FAIL: "var(--color-failure-accent)",
  WARN: "#c77a12",
};

function MetricBlock({ label, value, detail }) {
  return (
    <div className="glass-metric rounded-[20px] px-5 py-4">
      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">
        {label}
      </div>
      <div className="mt-2 font-display text-[25px] font-semibold leading-none text-slate-950">
        {value}
      </div>
      <div className="mt-2 text-[11px] leading-relaxed text-slate-600">{detail}</div>
    </div>
  );
}

export function DataHealthPanel({ health, status, onRefresh }) {
  const readiness = health?.readiness;
  const checks = health?.integrity?.checks || [];
  const fifteenMin = Number(readiness?.fifteenMinSessions);
  const required = Number(readiness?.required);
  const remaining = Number(readiness?.sessionsRemaining);
  const oneMin = Number(readiness?.oneMinSessions);
  const progress = Number.isFinite(fifteenMin) && Number.isFinite(required) && required > 0
    ? Math.min(100, (fifteenMin / required) * 100)
    : 0;
  const warnCount = checks.filter((check) => check.status === "WARN").length;
  const failCount = checks.filter((check) => check.status === "FAIL").length;
  const integrity = health?.integrity?.overall || "Unavailable";
  const verdict = readiness?.verdict || "Unavailable";

  return (
    <section className="liquid-glass-light rounded-[28px] p-6 md:p-8" aria-label="Data health and research readiness">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
            Data Health
          </p>
          <h2 className="mt-2 font-display text-[26px] font-semibold tracking-[-0.025em] text-slate-950">
            Research readiness
          </h2>
          <p className="mt-2 max-w-xl text-[13px] leading-relaxed text-slate-700">
            Live, read-only checks from the Spencer auditor. Warnings are reported without pretending the data is complete.
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={status === "loading" || status === "refreshing"}
          className="glass-pill inline-flex items-center gap-2 px-3.5 py-2 text-[11px] font-semibold text-slate-700 disabled:opacity-55"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${status === "refreshing" ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {status === "error" || !health ? (
        <div className="glass-metric mt-6 rounded-[20px] p-5 text-[13px] text-slate-700">
          {status === "loading" ? "Checking the data clock..." : "Health endpoint unavailable."}
        </div>
      ) : (
        <>
          <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricBlock
              label="Integrity"
              value={integrity}
              detail={`${checks.length} checks, ${failCount} failed, ${warnCount} warning${warnCount === 1 ? "" : "s"}`}
            />
            <MetricBlock
              label="15m sessions"
              value={Number.isFinite(fifteenMin) ? `${fifteenMin} / ${required}` : "---"}
              detail={Number.isFinite(remaining) ? `${remaining} sessions remaining` : "Readiness unavailable"}
            />
            <MetricBlock
              label="1m sessions"
              value={Number.isFinite(oneMin) ? oneMin.toLocaleString("en-IN") : "---"}
              detail="Distinct verified market sessions"
            />
            <MetricBlock
              label="SPNCR-003"
              value={verdict}
              detail={`Threshold: ${Number.isFinite(required) ? required : "---"} 15m sessions`}
            />
          </div>

          <div className="mt-5">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[11px] font-medium text-slate-700">
              <span>Data collected toward next test (SPNCR-003) — not a performance score</span>
              <span className="tabular-nums">
                {Number.isFinite(fifteenMin) ? `${fifteenMin} / ${required} sessions` : "---"} ({Math.round(progress)}%)
              </span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/45 shadow-inner">
              <div
                className="h-full rounded-full bg-gradient-to-r from-cyan-500 via-blue-500 to-violet-500 transition-[width] duration-700"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            {checks.map((check) => (
              <span
                key={check.id}
                className="glass-pill inline-flex items-center gap-2 px-3 py-1.5 text-[10px] font-semibold text-slate-700"
              >
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: statusTone[check.status] || "#64748b" }}
                />
                {check.name}: {check.status}
              </span>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
