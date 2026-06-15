import { StatusCard } from "../components/StatusCard";
import { asArray, fmtIST } from "../utils/helpers";

export function Orders({ botState }) {
  const orders = asArray(botState?.orders);

  if (!orders.length) {
    return <StatusCard title="No Orders" message="No paper orders have been recorded yet." />;
  }

  return (
    <div className="liquid-glass-light rounded-2xl">
      <div className="border-b border-[var(--color-light-border)] px-6 py-4">
        <h2 className="text-lg font-medium">Orders</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-[rgba(0,0,0,0.02)] text-xs uppercase tracking-wider text-[var(--color-muted-dark-text)]">
            <tr>
              <th className="px-6 py-3 font-medium">Time</th>
              <th className="px-6 py-3 font-medium">Symbol</th>
              <th className="px-6 py-3 font-medium">Side</th>
              <th className="px-6 py-3 font-medium">Qty</th>
              <th className="px-6 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-light-border)]">
            {orders.map((o, i) => (
              <tr key={i} className="hover:bg-[rgba(0,0,0,0.01)]">
                <td className="whitespace-nowrap px-6 py-4 font-mono">{fmtIST(o.time)}</td>
                <td className="whitespace-nowrap px-6 py-4 font-medium">{o.symbol}</td>
                <td className="whitespace-nowrap px-6 py-4 font-mono">{o.side}</td>
                <td className="whitespace-nowrap px-6 py-4 font-mono">{o.qty}</td>
                <td className="whitespace-nowrap px-6 py-4">{o.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
