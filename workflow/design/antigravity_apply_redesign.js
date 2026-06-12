const fs = require('fs');
const path = 'C:\\Users\\krish\\OneDrive\\Desktop\\AI TRADE\\frontend\\src\\App.jsx';

let content = fs.readFileSync(path, 'utf8');

const headerOld = `function Header({ onMenuOpen, backendStatus }) {
  const marketClosed = true;
  const backendLabel =
    backendStatus === "connected"
      ? "Backend Connected"
      : backendStatus === "checking"
        ? "Backend Checking"
        : "Backend Disconnected";

  return (
    <>
      {backendStatus === "disconnected" && (
        <div className="relative z-50 bg-red-600 px-4 py-2 text-center text-[12px] font-semibold text-white">
          Backend disconnected. Start Spencer backend on 127.0.0.1:8787, then refresh.
        </div>
      )}
      <header className="sticky top-0 z-30 border-b border-[#e5e7eb] bg-white">
        <div className="flex items-center justify-between px-4 py-3 md:px-6">
          <button
            onClick={onMenuOpen}
            aria-label="Open menu"
            className="flex flex-col gap-[5px] px-1 py-1.5 text-[#374151] hover:text-[#111827]"
          >
            <span className="block h-[1.5px] w-[18px] rounded-full bg-current" />
            <span className="block h-[1.5px] w-[18px] rounded-full bg-current" />
            <span className="block h-[1.5px] w-[18px] rounded-full bg-current" />
          </button>
          <div className="absolute left-1/2 -translate-x-1/2 text-[20px] text-[#020617]">Spencer AI</div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-2.5 py-1 text-[11px] font-semibold text-red-600">
              <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
              {marketClosed ? "Closed" : "Open"}
            </div>
            <button
              disabled
              title="Notifications are not configured in the local backend."
              aria-label="Notifications unavailable"
              className="flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-lg text-[#94a3b8] opacity-60"
            >
              <Bell className="h-4 w-4" />
            </button>
            <button onClick={onMenuOpen} className="grid h-8 w-8 place-items-center rounded-full bg-[#2563eb] text-[10px] font-bold text-white">
              TR
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-3 bg-gray-900 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-300">
          <span className="text-blue-400">[Paper Mode]</span>
          <span className={backendStatus === "connected" ? "text-emerald-400" : backendStatus === "checking" ? "text-amber-300" : "text-red-400"}>
            [{backendLabel}]
          </span>
          <span className="text-gray-400">[Live Trading Disabled]</span>
          <span className="text-gray-400">[Broker Execution Disabled]</span>
        </div>
      </header>
    </>
  );
}`;

const headerNew = `function Header({ onMenuOpen, backendStatus }) {
  const marketClosed = true;
  const marketStateText = marketClosed ? "Market Closed — as of 15:30 IST" : "Market Open";
  
  return (
    <header className="border-b border-border-grid bg-bg-void text-text-data font-sans">
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-4">
          <button onClick={onMenuOpen} aria-label="Open menu" className="flex flex-col gap-[5px] px-1 py-1.5 text-text-muted hover:text-text-data">
            <span className="block h-[1.5px] w-[18px] rounded-full bg-current" />
            <span className="block h-[1.5px] w-[18px] rounded-full bg-current" />
            <span className="block h-[1.5px] w-[18px] rounded-full bg-current" />
          </button>
          <h1 className="text-lg font-medium tracking-tight">Spencer AI</h1>
          <span className="font-mono text-xs text-text-muted">Instrument Interface</span>
        </div>
        <div className="font-mono text-xs text-text-muted">
          {marketStateText}
        </div>
      </div>
      <div className="bg-bg-surface border-t border-border-grid px-6 py-2 flex items-center gap-6 font-mono text-[10px] uppercase tracking-widest text-status-warn">
        <span className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-status-warn animate-pulse"></span>
          PAPER MODE
        </span>
        <span>LIVE TRADING DISABLED</span>
      </div>
    </header>
  );
}`;

content = content.replace(headerOld, headerNew);


const appOld = `<div className="dashboard-light h-screen w-screen overflow-hidden bg-[#f8fafc] text-[#020617]">`;
const appNew = `<div className="h-screen w-screen overflow-hidden bg-bg-void text-text-data">`;
content = content.replace(appOld, appNew);


const portfolioOld = `function PortfolioOverview({ botState, backendStatus, watchlistCount = 0 }) {
  if (backendStatus !== "connected") {
    return (
      <StatusCard
        title={backendStatus === "checking" ? "Checking backend" : "Backend disconnected"}
        message={backendStatus === "checking" ? "Checking Spencer backend for verified paper journal data." : "Dashboard counts and paper journal data are unavailable."}
        icon={Wallet}
      />
    );
  }
  const holdings = asArray(botState?.holdings);
  const orders = asArray(botState?.orders);
  const closedTrades = asArray(botState?.trades).filter((trade) => !isMissing(trade.pnl));
  const bidsValue = Array.isArray(botState?.bids) ? botState.bids.length : "Data unavailable";
  const strategiesValue = botState?.activeStrategy ? 1 : "Data unavailable";
  const capital = botState?.capital || {};
  const metrics = botState?.metrics || {};
  const totalValue = capital.totalValue;
  const totalPnl = capital.totalPnl;
  const pricedHoldings = holdings.filter((holding) => !isMissing(holding.ltp));
  const top = pricedHoldings
    .map((h) => ({ ...h, chgPct: safeNumber(h.avg) > 0 ? ((safeNumber(h.ltp) - safeNumber(h.avg)) / safeNumber(h.avg)) * 100 : null }))
    .sort((a, b) => safeNumber(b.chgPct) - safeNumber(a.chgPct))[0];
  const worst = pricedHoldings
    .map((h) => ({ ...h, chgPct: safeNumber(h.avg) > 0 ? ((safeNumber(h.ltp) - safeNumber(h.avg)) / safeNumber(h.avg)) * 100 : null }))
    .sort((a, b) => safeNumber(a.chgPct) - safeNumber(b.chgPct))[0];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.6fr_1fr]">
        <section className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-[#94a3b8]">Portfolio Value</div>
              <div className="text-[32px] font-bold leading-none text-[#020617]">{isMissing(totalValue) ? "awaiting first real quote" : money(totalValue)}</div>
              <div className={\`mt-2 inline-flex rounded-md border px-2 py-1 text-[12px] font-semibold \${safeNumber(totalPnl) >= 0 ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"}\`}>
                {isMissing(totalPnl) ? "awaiting first real quote" : \`\${totalPnl >= 0 ? "+" : ""}\${money(totalPnl)} (\${pct(capital.pnlPct)}) total P&L\`}
              </div>
            </div>
            <div className="space-y-0.5 text-right text-[11px] text-[#64748b]">
              <div>Budget: <span className="font-semibold text-[#111827]">{money(capital.budget)}</span></div>
              <div>Invested: <span className="font-semibold text-[#111827]">{money(capital.invested)}</span></div>
              <div>Free cash: <span className="font-semibold text-[#111827]">{money(capital.cash)}</span></div>
            </div>
          </div>
          <div className="mt-5 h-20 rounded-lg border border-emerald-100 bg-gradient-to-r from-emerald-50 to-white" />
        </section>
        <section className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm">
          <div className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-[#94a3b8]">P&L Breakdown</div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#64748b]">Unrealised</span>
              <span className={\`font-semibold \${safeNumber(capital.unrealisedPnl) >= 0 ? "text-emerald-600" : "text-red-600"}\`}>
                {safeNumber(capital.unrealisedPnl) >= 0 ? "+" : ""}{money(capital.unrealisedPnl)}
              </span>
            </div>
            <div className="h-px bg-gray-100" />
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#64748b]">Realised</span>
              <span className={\`font-semibold \${safeNumber(capital.realisedPnl) >= 0 ? "text-emerald-600" : "text-red-600"}\`}>
                {safeNumber(capital.realisedPnl) >= 0 ? "+" : ""}{money(capital.realisedPnl)}
              </span>
            </div>
            <div className="text-right text-[11px] text-[#94a3b8]">{metrics.closedTrades ?? "N/A"} closed trades</div>
          </div>
        </section>
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          ["Holdings", holdings.length, holdings.length === 1 ? "1 position open" : \`\${holdings.length} positions open\`],
          ["Orders", orders.length, "Backend order journal"],
          ["Bids", bidsValue, Array.isArray(botState?.bids) ? "Backend bids dataset" : "Data unavailable"],
          ["Closed Trades", metrics.closedTrades ?? closedTrades.length, "Backend realised rows"],
          ["Strategies", strategiesValue, botState?.activeStrategy ? "Backend active strategy" : "No verified strategy tests found."],
          ["Watchlist", watchlistCount, "Local config"],
          ["Top Performer", top?.symbol || "No current position", top ? pct(top.chgPct) : "Data unavailable"],
          ["Worst Performer", worst?.symbol || "No current position", worst ? pct(worst.chgPct) : "Data unavailable"],
        ].map(([label, value, sub]) => (
          <section key={label} className="rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-sm">
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#94a3b8]">{label}</div>
            <div className="text-[20px] font-bold leading-tight text-[#020617]">{value}</div>
            <div className="mt-1.5 text-[11px] text-[#64748b]">{sub}</div>
          </section>
        ))}
      </div>
    </div>
  );
}`;

const portfolioNew = `function PortfolioOverview({ botState, backendStatus, watchlistCount = 0 }) {
  if (backendStatus !== "connected") {
    return null;
  }
  const capital = botState?.capital || {};
  const basis = capital.budget ?? 5000;
  const pnl = capital.totalPnl;
  const freeCash = capital.cash ?? 5000;
  
  const pnlClass = isMissing(pnl) ? "text-text-muted" : pnl > 0 ? "text-status-passed" : pnl < 0 ? "text-status-killed" : "text-text-muted";
  const pnlSign = !isMissing(pnl) && pnl > 0 ? "+" : "";

  return (
    <div className="space-y-4">
      <section className="bg-bg-surface border border-border-grid p-6 rounded-md font-sans text-text-data">
        <div className="text-[10px] uppercase tracking-widest text-text-muted mb-6 font-mono">Portfolio State</div>
        <div className="grid grid-cols-3 gap-8">
          <div>
            <div className="text-xs text-text-muted mb-1">Basis (Capital)</div>
            <div className="font-mono text-2xl tracking-tight">{money(basis)}</div>
          </div>
          <div>
            <div className="text-xs text-text-muted mb-1">P&L</div>
            <div className="flex flex-col gap-2">
              <div className={\`font-mono text-2xl tracking-tight \${pnlClass}\`}>
                {isMissing(pnl) ? "₹—" : \`\${pnlSign}\${money(pnl)}\`}
              </div>
            </div>
          </div>
          <div>
            <div className="text-xs text-text-muted mb-1">Free Cash</div>
            <div className="font-mono text-2xl tracking-tight">{money(freeCash)}</div>
          </div>
        </div>
      </section>
    </div>
  );
}`;

content = content.replace(portfolioOld, portfolioNew);

const marketPulseOld = `function MarketPulseWidget() {
  const { quotes, quoteStatus } = useQuotes([ONE_STOCK_SYMBOL]);
  const Row = ({ label, q }) => (
    <div className="flex items-center justify-between rounded-md border border-gray-100 bg-[#f8fafc] px-3 py-2">
      <span className="text-[12px] font-semibold text-[#111827]">{label}</span>
      {q && !isMissing(q.price) ? (
        <PriceStack value={q.price} source={q} />
      ) : (
        <span className="text-[11px] text-[#94a3b8]">{quoteStatus === "checking" ? "checking quote..." : "awaiting first real quote"}</span>
      )}
    </div>
  );
  return (
    <WidgetShell title="Market Pulse" icon={Activity} badge={quoteStatus === "ready" ? "Live market data" : "Data unavailable"}>
      <div className="space-y-2">
        <Row label={ONE_STOCK_SYMBOL} q={quotes[ONE_STOCK_SYMBOL]} />
        <div className="pt-1 text-center text-[10px] text-[#94a3b8]">Backend quote route only</div>
      </div>
    </WidgetShell>
  );
}`;

const marketPulseNew = `function MarketPulseWidget() {
  const { quotes, quoteStatus } = useQuotes([ONE_STOCK_SYMBOL]);
  const quote = quotes[ONE_STOCK_SYMBOL];
  
  return (
    <section className="bg-bg-surface border border-border-grid p-6 rounded-md h-full">
      <div className="flex justify-between items-baseline mb-6">
        <div className="flex items-baseline gap-3">
          <h2 className="text-xl font-medium text-text-data">RELIANCE · NSE</h2>
          <span className="font-mono text-xs text-text-muted">EQUITY</span>
        </div>
        <div className="text-right">
          <div className="font-mono text-2xl tracking-tight text-text-data">
            {quote && !isMissing(quote.price) ? money(quote.price, 2) : "₹—"}
          </div>
          <div className="font-mono text-sm text-text-muted">
            {quoteStatus === "checking" ? "Checking..." : quote && !isMissing(quote.price) ? "Live Quote" : "Quote Unavailable"}
          </div>
        </div>
      </div>
      <div className="h-48 border border-border-grid bg-bg-void rounded flex items-center justify-center">
        <span className="font-mono text-xs text-text-muted">[ Visualization Area ]</span>
      </div>
    </section>
  );
}`;

content = content.replace(marketPulseOld, marketPulseNew);

const orderTableOld = `function OrderTable({ title, rows }) {
  return (
    <section className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
        <div className="text-[13px] font-semibold text-[#020617]">{title}</div>
        <span className="rounded border border-blue-100 bg-blue-50 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-blue-600">Backend journal</span>
      </div>
      {rows.length === 0 ? (
        <StatusCard title="No backend orders recorded" message="Backend returned an empty orders list." icon={ClipboardList} />
      ) : (
        <SimpleTable
          headings={["Time", "Symbol", "Side", "Qty", "Price", "Reason", "Status"]}
          rows={rows.map((order) => [
            order.time || "N/A",
            order.symbol || "N/A",
            order.side || "N/A",
            qty(order.qty),
            <PriceStack value={order.price} source={{ priceLabel: order.priceLabel || (order.time ? \`journaled at \${order.time}\` : null) }} />,
            sanitizeReason(order.reason),
            order.status || "N/A",
          ])}
        />
      )}
    </section>
  );
}`;

const orderTableNew = `function OrderTable({ title, rows }) {
  return (
    <section className="bg-bg-surface border border-border-grid p-6 rounded-md h-full flex flex-col mt-4">
      <div className="text-[10px] uppercase tracking-widest text-text-muted mb-6 font-mono">{title}</div>
      {rows.length === 0 ? (
        <div className="border border-dashed border-border-grid rounded-md flex-1 flex items-center justify-center min-h-[160px] bg-bg-void/50">
          <div className="text-center">
            <p className="text-text-data font-sans text-sm mb-1.5">No orders recorded.</p>
            <p className="text-text-muted font-mono text-xs">Spencer trades only when rules fire.</p>
          </div>
        </div>
      ) : (
        <SimpleTable
          headings={["Time", "Symbol", "Side", "Qty", "Price", "Reason", "Status"]}
          rows={rows.map((order) => [
            order.time || "N/A",
            order.symbol || "N/A",
            order.side || "N/A",
            qty(order.qty),
            <PriceStack value={order.price} source={{ priceLabel: order.priceLabel || (order.time ? \`journaled at \${order.time}\` : null) }} />,
            sanitizeReason(order.reason),
            order.status || "N/A",
          ])}
        />
      )}
    </section>
  );
}`;
content = content.replace(orderTableOld, orderTableNew);

const holdingsTableOld = `function HoldingsTable({ rows }) {
  return (
    <section className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
        <div className="text-[13px] font-semibold text-[#020617]">Holdings - {rows.length}</div>
        <span className="rounded border border-blue-100 bg-blue-50 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-blue-600">Backend journal</span>
      </div>
      {rows.length === 0 ? (
        <StatusCard title="No backend holdings recorded" message="Backend returned an empty holdings list." icon={Wallet} />
      ) : (
        <SimpleTable
          headings={["Symbol", "Sector", "Qty", "Avg Cost", "LTP", "Value", "P&L"]}
          rows={rows.map((holding) => {
            const hasLtp = !isMissing(holding.ltp);
            const rowPnl = hasLtp ? (safeNumber(holding.ltp) - safeNumber(holding.avg)) * safeNumber(holding.qty) : null;
            const rowPct = hasLtp && safeNumber(holding.avg) > 0 ? ((safeNumber(holding.ltp) - safeNumber(holding.avg)) / safeNumber(holding.avg)) * 100 : null;
            return [
              holding.symbol || "N/A",
              holding.sector || "N/A",
              qty(holding.qty),
              money(holding.avg, 2),
              <PriceStack value={holding.ltp} source={holding} />,
              hasLtp ? money(safeNumber(holding.qty) * safeNumber(holding.ltp)) : "awaiting first real quote",
              hasLtp ? \`\${rowPnl >= 0 ? "+" : ""}\${money(rowPnl)} (\${pct(rowPct)})\` : "awaiting first real quote",
            ];
          })}
        />
      )}
    </section>
  );
}`;

const holdingsTableNew = `function HoldingsTable({ rows }) {
  return (
    <section className="bg-bg-surface border border-border-grid p-6 rounded-md h-full flex flex-col">
      <div className="text-[10px] uppercase tracking-widest text-text-muted mb-6 font-mono">Active Holdings</div>
      {rows.length === 0 ? (
        <div className="border border-dashed border-border-grid rounded-md flex-1 flex items-center justify-center min-h-[160px] bg-bg-void/50">
          <div className="text-center">
            <p className="text-text-data font-sans text-sm mb-1.5">No position.</p>
            <p className="text-text-muted font-mono text-xs">Spencer trades only when rules fire.</p>
          </div>
        </div>
      ) : (
        <SimpleTable
          headings={["Symbol", "Sector", "Qty", "Avg Cost", "LTP", "Value", "P&L"]}
          rows={rows.map((holding) => {
            const hasLtp = !isMissing(holding.ltp);
            const rowPnl = hasLtp ? (safeNumber(holding.ltp) - safeNumber(holding.avg)) * safeNumber(holding.qty) : null;
            const rowPct = hasLtp && safeNumber(holding.avg) > 0 ? ((safeNumber(holding.ltp) - safeNumber(holding.avg)) / safeNumber(holding.avg)) * 100 : null;
            return [
              holding.symbol || "N/A",
              holding.sector || "N/A",
              qty(holding.qty),
              money(holding.avg, 2),
              <PriceStack value={holding.ltp} source={holding} />,
              hasLtp ? money(safeNumber(holding.qty) * safeNumber(holding.ltp)) : "awaiting first real quote",
              hasLtp ? \`\${rowPnl >= 0 ? "+" : ""}\${money(rowPnl)} (\${pct(rowPct)})\` : "awaiting first real quote",
            ];
          })}
        />
      )}
    </section>
  );
}`;

content = content.replace(holdingsTableOld, holdingsTableNew);

const researchRegex = /function ResearchLedgerPanel\(\) \{[\s\S]*?(?=function ResearchPanel)/;
const researchOldMatch = content.match(researchRegex);

const researchNew = `function ResearchLedgerPanel() {
  const { ledger, status, health, loadLedger } = useResearchLedger();
  const candidates = asArray(ledger?.candidates);
  const scoreboard = ledger?.scoreboard || {};

  return (
    <section className="bg-bg-surface border border-border-grid p-6 rounded-md mt-4">
      <div className="flex justify-between items-center mb-6">
        <div className="text-[10px] uppercase tracking-widest text-text-muted font-mono">Research Ledger</div>
        <button onClick={loadLedger} disabled={status === "loading"} className="text-[10px] font-mono text-text-muted hover:text-text-data">
          {status === "loading" ? "Checking..." : "[ Refresh ]"}
        </button>
      </div>
      
      {status === "loading" && <div className="text-xs font-mono text-text-muted">Checking research ledger...</div>}
      {status === "error" && <div className="text-xs font-mono text-status-killed">Error loading ledger.</div>}

      {status !== "loading" && status !== "error" && (
        <div className="space-y-4">
          {candidates.length === 0 ? (
            <div className="text-xs font-mono text-text-muted">No candidates tested yet.</div>
          ) : (
            candidates.map((candidate) => {
              const trades = asArray(candidate.stages).reduce((sum, s) => sum + safeNumber(s.trades), 0);
              const gross = asArray(candidate.stages).reduce((sum, s) => sum + safeNumber(s.gross_pnl), 0);
              const costs = asArray(candidate.stages).reduce((sum, s) => sum + safeNumber(s.total_costs), 0);
              const net = asArray(candidate.stages).reduce((sum, s) => sum + safeNumber(s.net_pnl), 0);
              const isPassed = candidate.status?.toUpperCase() === "PASSED";
              const colorClasses = isPassed 
                ? "border-status-passed/30 bg-status-passed/10 text-status-passed" 
                : "border-status-killed/30 bg-status-killed/10 text-status-killed";
              
              return (
                <div key={\`\${candidate.candidateId}-\${candidate.version}\`} className="border border-border-grid bg-bg-void p-5 rounded-md flex flex-col gap-5">
                  <div className="flex justify-between items-start gap-4">
                    <div className="font-sans text-sm text-text-data leading-relaxed max-w-xl">
                      <span className="font-mono text-xs text-text-muted block mb-1">{candidate.candidateId}</span>
                      {apiText(candidate.hypothesis)}
                    </div>
                    <div className={\`px-2.5 py-1 border \${colorClasses} font-mono text-[10px] uppercase tracking-widest rounded-sm shrink-0\`}>
                      {apiText(candidate.status)}
                    </div>
                  </div>
                  <div className="grid grid-cols-4 gap-4 border-t border-border-grid pt-4 font-mono text-xs">
                    <div><span className="text-text-muted block mb-1 text-[10px] uppercase">Trades</span>{apiCount(trades)}</div>
                    <div><span className="text-text-muted block mb-1 text-[10px] uppercase">Gross</span><span className={gross >= 0 ? "text-status-passed" : "text-status-killed"}>{gross >= 0 ? "+" : ""}{apiMoney(gross)}</span></div>
                    <div><span className="text-text-muted block mb-1 text-[10px] uppercase">Costs</span>{apiMoney(costs)}</div>
                    <div><span className="text-text-muted block mb-1 text-[10px] uppercase">Net</span><span className={net >= 0 ? "text-status-passed" : "text-status-killed"}>{net >= 0 ? "+" : ""}{apiMoney(net)}</span></div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
      
      <div className="mt-8 border-t border-border-grid pt-6">
        <div className="text-[10px] uppercase tracking-widest text-text-muted mb-8 font-mono">System Scoreboard</div>
        <div className="flex justify-between items-center px-4">
          <div className="text-center">
            <div className="text-text-muted font-mono text-[10px] uppercase tracking-wider mb-3">Functional</div>
            <div className="text-4xl font-mono text-text-data tracking-tight">{apiCount(scoreboard.functional)}</div>
          </div>
          <div className="text-border-grid text-4xl font-light">/</div>
          <div className="text-center">
            <div className="text-text-muted font-mono text-[10px] uppercase tracking-wider mb-3">Profitability</div>
            <div className="text-4xl font-mono text-text-data tracking-tight">{apiCount(scoreboard.profitability)}</div>
          </div>
          <div className="text-border-grid text-4xl font-light">/</div>
          <div className="text-center">
            <div className="text-text-muted font-mono text-[10px] uppercase tracking-wider mb-3">Composite</div>
            <div className="text-4xl font-mono text-text-data tracking-tight">{apiCount(scoreboard.composite)}</div>
          </div>
        </div>
      </div>
    </section>
  );
}
`;

if (researchOldMatch) {
  content = content.replace(researchOldMatch[0], researchNew);
}

fs.writeFileSync(path, content, 'utf8');
console.log('Done!');
