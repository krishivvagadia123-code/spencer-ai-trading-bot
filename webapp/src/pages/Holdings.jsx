import { StatusCard } from "../components/StatusCard";
import { asArray, money } from "../utils/helpers";

export function Holdings({
  botState,
  rows,
  title = "Holdings",
  emptyTitle = "No Holdings",
  emptyMessage = "Paper portfolio is currently empty.",
}) {
  // `rows` lets callers (e.g. Positions) supply a different source; defaults to holdings.
  const holdings = rows !== undefined ? asArray(rows) : asArray(botState?.holdings);

  if (!holdings.length) {
    return <StatusCard title={emptyTitle} message={emptyMessage} />;
  }

  return (
    <div className="liquid-glass-light rounded-2xl">
      <div className="border-b border-[var(--color-light-border)] px-6 py-4">
        <h2 className="text-lg font-medium">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-[rgba(0,0,0,0.02)] text-xs uppercase tracking-wider text-[var(--color-muted-dark-text)]">
            <tr>
              <th className="px-6 py-3 font-medium">Symbol</th>
              <th className="px-6 py-3 font-medium">Qty</th>
              <th className="px-6 py-3 font-medium">Avg Price</th>
              <th className="px-6 py-3 font-medium">LTP</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-light-border)]">
            {holdings.map((h, i) => (
              <tr key={i} className="hover:bg-[rgba(0,0,0,0.01)]">
                <td className="whitespace-nowrap px-6 py-4 font-medium">{h.symbol}</td>
                <td className="whitespace-nowrap px-6 py-4 font-mono">{h.qty}</td>
                <td className="whitespace-nowrap px-6 py-4 font-mono">{money(h.avg)}</td>
                <td className="whitespace-nowrap px-6 py-4 font-mono">{money(h.ltp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
