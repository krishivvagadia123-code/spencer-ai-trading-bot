import { StatusCard } from "../components/StatusCard";
import { asArray, fmtIST, money, pnlSign, pnlTone } from "../utils/helpers";

export function TradeTracker({ botState }) {
  const trades = asArray(botState?.trades).filter(t => t.pnl !== null && t.pnl !== undefined);
  const metrics = botState?.metrics || {};

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="liquid-glass-light rounded-xl p-6">
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Realised P&L</div>
          <div className={`font-mono text-2xl ${pnlTone(botState?.capital?.realisedPnl)}`}>
            {botState?.capital?.realisedPnl == null
              ? "N/A"
              : `${pnlSign(botState.capital.realisedPnl)}${money(botState.capital.realisedPnl)}`}
          </div>
        </div>
        <div className="liquid-glass-light rounded-xl p-6">
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Closed Trades</div>
          <div className="font-mono text-2xl">{metrics.closedTrades || 0}</div>
        </div>
        <div className="liquid-glass-light rounded-xl p-6">
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Wins</div>
          <div className="font-mono text-2xl text-[var(--color-verified-accent)]">{metrics.wins || 0}</div>
        </div>
        <div className="liquid-glass-light rounded-xl p-6">
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Losses</div>
          <div className="font-mono text-2xl text-[var(--color-failure-accent)]">{metrics.losses || 0}</div>
        </div>
      </div>

      {!trades.length ? (
        <StatusCard title="No Closed Trades" message="No trades have been completed yet." />
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
              {trades.map((t, i) => (
                <tr key={i} className="hover:bg-[rgba(0,0,0,0.01)]">
                  <td className="whitespace-nowrap px-6 py-4 font-mono">{fmtIST(t.time)}</td>
                  <td className="whitespace-nowrap px-6 py-4 font-medium">{t.symbol}</td>
                  <td className="whitespace-nowrap px-6 py-4 font-mono">{t.side}</td>
                  <td className="whitespace-nowrap px-6 py-4 font-mono">{money(t.price)}</td>
                  <td className={`whitespace-nowrap px-6 py-4 font-mono ${pnlTone(t.pnl)}`}>
                    {pnlSign(t.pnl)}{money(t.pnl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
