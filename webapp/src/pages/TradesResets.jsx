import { RefreshCw, RotateCcw } from "lucide-react";
import { StatusCard } from "../components/StatusCard";
import { asArray, fmtIST, money, pnlSign, pnlTone, dateOnly } from "../utils/helpers";

function Stat({ label, value, tone, detail }) {
  return (
    <div className="liquid-glass-light rounded-xl p-6">
      <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">{label}</div>
      <div className={`font-mono text-2xl ${tone || ""}`}>{value}</div>
      {detail ? <div className="mt-2 text-[11px] leading-relaxed text-[var(--color-muted-dark-text)]">{detail}</div> : null}
    </div>
  );
}

// Honest Trades & Resets view. Every paper trade taken — epoch journal round
// trips plus forward paper-engine runs (dry-run replays / future live sessions)
// — and a count of how many times the account was reset to the ₹5,000 basis.
// All rows trace to kite_bot.db; nothing is fabricated.
export function TradesResets({ data, status, reload }) {
  if (status === "loading" && !data) {
    return <StatusCard title="Loading" message="Reading the paper journal…" />;
  }
  if (status === "error" || !data) {
    return <StatusCard title="Backend Unavailable" message="Could not reach the Trades & Resets endpoint." />;
  }
  if (data.journalPresent === false) {
    return <StatusCard title="No Journal Yet" message={data.note || "Run the paper engine to populate real data."} />;
  }

  const epochTrades = asArray(data.epochTrades);
  const engineTrades = asArray(data.engineTrades);
  const resets = asArray(data.resets);
  const totals = data.totals || {};

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <p className="max-w-2xl text-[13px] leading-relaxed text-[var(--color-muted-dark-text)]">
          Every paper trade on record and every reset to the {money(data.basis)} basis.
          Epoch <span className="font-mono">{data.epoch}</span> — all rows trace to the journal; none are invented.
          Forward-engine rows are dry-run replays / research, not the live epoch account.
        </p>
        <button
          type="button"
          onClick={reload}
          disabled={status === "loading"}
          className="glass-pill inline-flex items-center gap-2 px-3.5 py-2 text-[11px] font-semibold text-slate-700 disabled:opacity-55"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${status === "loading" ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Resets to ₹5,000" value={data.resetCount ?? 0} />
        <Stat label="Epoch Trades" value={totals.epochTrades ?? 0} detail="Live paper account round trips" />
        <Stat
          label="Engine Trades"
          value={totals.engineTrades ?? 0}
          detail="Dry-run / forward paper sessions"
        />
        <Stat
          label="Engine Net P&L"
          value={totals.engineNetPnl == null ? "N/A" : `${pnlSign(totals.engineNetPnl)}${money(totals.engineNetPnl, 2)}`}
          tone={pnlTone(totals.engineNetPnl)}
          detail="After all costs & slippage"
        />
      </div>

      {/* Resets */}
      <section>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--color-primary-dark-text)]">
          <RotateCcw className="h-4 w-4" /> Account resets to ₹5,000 basis
        </h3>
        {!resets.length ? (
          <StatusCard title="No Resets" message="The account has not been reset since this epoch began." />
        ) : (
          <div className="liquid-glass-light overflow-x-auto rounded-2xl">
            <table className="w-full text-left text-sm">
              <thead className="bg-[rgba(0,0,0,0.02)] text-xs uppercase tracking-wider text-[var(--color-muted-dark-text)]">
                <tr>
                  <th className="px-6 py-3 font-medium">Date</th>
                  <th className="px-6 py-3 font-medium">Positions Closed</th>
                  <th className="px-6 py-3 font-medium">Symbols</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-light-border)]">
                {resets.map((r, i) => (
                  <tr key={i} className="hover:bg-[rgba(0,0,0,0.01)]">
                    <td className="whitespace-nowrap px-6 py-4 font-mono">{dateOnly(r.at)}</td>
                    <td className="whitespace-nowrap px-6 py-4 font-mono">{r.positionsClosed}</td>
                    <td className="px-6 py-4 font-mono text-[var(--color-muted-dark-text)]">{asArray(r.symbols).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Epoch trades */}
      <section>
        <h3 className="mb-3 text-sm font-semibold text-[var(--color-primary-dark-text)]">
          Epoch paper trades (live account)
        </h3>
        {!epochTrades.length ? (
          <StatusCard
            title="No Epoch Trades Yet"
            message="No live epoch trade has been taken. A candidate must graduate the testing ladder first — the engine refuses until then."
          />
        ) : (
          <div className="liquid-glass-light overflow-x-auto rounded-2xl">
            <table className="w-full text-left text-sm">
              <thead className="bg-[rgba(0,0,0,0.02)] text-xs uppercase tracking-wider text-[var(--color-muted-dark-text)]">
                <tr>
                  <th className="px-6 py-3 font-medium">Time</th>
                  <th className="px-6 py-3 font-medium">Symbol</th>
                  <th className="px-6 py-3 font-medium">Side</th>
                  <th className="px-6 py-3 font-medium">Price</th>
                  <th className="px-6 py-3 font-medium">P&L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-light-border)]">
                {epochTrades.map((t, i) => (
                  <tr key={i} className="hover:bg-[rgba(0,0,0,0.01)]">
                    <td className="whitespace-nowrap px-6 py-4 font-mono">{fmtIST(t.ts)}</td>
                    <td className="whitespace-nowrap px-6 py-4 font-medium">{t.symbol}</td>
                    <td className="whitespace-nowrap px-6 py-4 font-mono">{t.side}</td>
                    <td className="whitespace-nowrap px-6 py-4 font-mono">{money(t.price, 2)}</td>
                    <td className={`whitespace-nowrap px-6 py-4 font-mono ${pnlTone(t.pnl)}`}>
                      {pnlSign(t.pnl)}{money(t.pnl, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Engine trades */}
      <section>
        <h3 className="mb-3 text-sm font-semibold text-[var(--color-primary-dark-text)]">
          Forward paper-engine trades (research / dry-run)
        </h3>
        {!engineTrades.length ? (
          <StatusCard title="No Engine Trades" message="No dry-run or forward paper sessions have produced a trade yet." />
        ) : (
          <div className="liquid-glass-light overflow-x-auto rounded-2xl">
            <table className="w-full text-left text-sm">
              <thead className="bg-[rgba(0,0,0,0.02)] text-xs uppercase tracking-wider text-[var(--color-muted-dark-text)]">
                <tr>
                  <th className="px-6 py-3 font-medium">Mode</th>
                  <th className="px-6 py-3 font-medium">Candidate</th>
                  <th className="px-6 py-3 font-medium">Entry</th>
                  <th className="px-6 py-3 font-medium">Exit</th>
                  <th className="px-6 py-3 font-medium">Qty</th>
                  <th className="px-6 py-3 font-medium">Net P&L</th>
                  <th className="px-6 py-3 font-medium">Exit Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-light-border)]">
                {engineTrades.map((t, i) => (
                  <tr key={i} className="hover:bg-[rgba(0,0,0,0.01)]">
                    <td className="whitespace-nowrap px-6 py-4 font-mono text-xs">{t.mode}</td>
                    <td className="whitespace-nowrap px-6 py-4 font-medium">{t.candidateId}</td>
                    <td className="whitespace-nowrap px-6 py-4 font-mono text-xs">{money(t.entryPrice, 2)} @ {fmtIST(t.entryTs)}</td>
                    <td className="whitespace-nowrap px-6 py-4 font-mono text-xs">{money(t.exitPrice, 2)} @ {fmtIST(t.exitTs)}</td>
                    <td className="whitespace-nowrap px-6 py-4 font-mono">{t.qty}</td>
                    <td className={`whitespace-nowrap px-6 py-4 font-mono ${pnlTone(t.netPnl)}`}>
                      {pnlSign(t.netPnl)}{money(t.netPnl, 2)}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 font-mono text-xs text-[var(--color-muted-dark-text)]">{t.exitReason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
