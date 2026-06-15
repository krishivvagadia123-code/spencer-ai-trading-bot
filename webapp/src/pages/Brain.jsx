import { StatusCard } from "../components/StatusCard";
import { displayName, fmtIST, isMissing, money, pct } from "../utils/helpers";

const researchValue = (value, formatter = (next) => next) =>
  isMissing(value) ? "N/A" : formatter(value);

export function Brain({ row, status, loadResearch, botState }) {
  if (status === "loading") return <StatusCard title="Loading Brain Data" message="Analyzing latest backend state..." />;
  if (status === "error" || status === "disconnected") return <StatusCard title="Connection Error" message="Could not reach the Brain module." />;
  if (status === "empty" || !row) return <StatusCard title="No Data" message="No active brain research row." />;

  const regimes = Object.values(botState?.regimeTrust?.regimes || {});
  const source = row.source || "Backend research endpoint";

  return (
    <div className="liquid-glass-light rounded-[24px] p-6 text-[var(--color-primary-dark-text)] sm:p-8">
      <div className="mb-12 border-b border-[var(--color-light-border)] pb-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-3xl font-light tracking-tight">{row.symbol || "RELIANCE"}</h2>
            <div className="mt-2 font-mono text-sm text-[var(--color-muted-dark-text)]">{fmtIST(row.asof)}</div>
          </div>
          <div className="rounded-full border border-black/10 bg-black/[0.03] px-4 py-2 font-mono text-xs text-black/55">
            {source}
          </div>
        </div>
      </div>

      <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-5">
        <div>
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Trend</div>
          <div className="font-mono text-xl capitalize">{row.trend || "N/A"}</div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Last Price</div>
          <div className="font-mono text-xl">{researchValue(row.lastPrice, (value) => money(value, 2))}</div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">SMA 20</div>
          <div className="font-mono text-xl">{researchValue(row.sma20, (value) => money(value, 2))}</div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">SMA 50</div>
          <div className="font-mono text-xl">{researchValue(row.sma50, (value) => money(value, 2))}</div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Return 20d</div>
          <div className="font-mono text-xl">
            {researchValue(row.return20d, (value) => pct(Number(value) * 100))}
          </div>
        </div>
      </div>

      <div className="mt-12 rounded-xl bg-black/[0.03] p-6">
        <div className="mb-4 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Verified Reading</div>
        <p className="leading-relaxed text-black/65">
          The backend classifies the current trend as <span className="text-black/85">{row.trend || "unavailable"}</span>.
          This is a descriptive market snapshot from {source}; it is not a validated edge or trade instruction.
        </p>
      </div>

      <div className="mt-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div>
            <div className="text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Regime Trust</div>
            <p className="mt-2 text-sm text-black/50">Historical backend evidence by market regime.</p>
          </div>
          {botState?.regimeTrust?.last_updated && (
            <div className="font-mono text-xs text-black/40">
              Updated {fmtIST(botState.regimeTrust.last_updated)}
            </div>
          )}
        </div>

        {regimes.length ? (
          <div className="grid gap-3 md:grid-cols-3">
            {regimes.map((regime) => (
              <div key={regime.regime} className="rounded-2xl border border-black/10 bg-black/[0.03] p-5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium">{displayName(regime.regime)}</span>
                  <span className="font-mono text-sm text-black/60">{pct(Number(regime.trust) * 100, 1)} trust</span>
                </div>
                <div className="mt-5 grid grid-cols-3 gap-3 font-mono text-xs">
                  <div>
                    <div className="text-black/40">Trades</div>
                    <div className="mt-1 text-black/70">{regime.trades ?? "N/A"}</div>
                  </div>
                  <div>
                    <div className="text-black/40">Win rate</div>
                    <div className="mt-1 text-black/70">{pct(Number(regime.win_rate) * 100, 1)}</div>
                  </div>
                  <div>
                    <div className="text-black/40">Net PnL</div>
                    <div className="mt-1 text-black/70">{money(regime.net_pnl, 2)}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-2xl border border-black/10 bg-black/[0.03] p-5 text-sm text-black/50">
            No regime-trust evidence is currently available from the backend.
          </p>
        )}
      </div>

      <button type="button" onClick={loadResearch} className="mt-8 rounded-lg bg-[var(--color-primary-black)] px-6 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90">
        Refresh Analysis
      </button>
    </div>
  );
}
