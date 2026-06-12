const fs = require('fs');
const path = 'C:\\Users\\krish\\OneDrive\\Desktop\\AI TRADE\\frontend\\src\\App.jsx';

let content = fs.readFileSync(path, 'utf8');

// 1. App background
content = content.replace(
  /<div className="dashboard-light h-screen w-screen overflow-hidden bg-\[#f8fafc\] text-\[#020617\]">/,
  '<div className="h-screen w-screen overflow-hidden bg-bg-void text-text-data">'
);

// 2. Header
const headerRegex = /function Header\(\{ onMenuOpen, backendStatus \}\) \{[\s\S]*?return \([\s\S]*?\n\s*\);\n\}/;
const newHeader = `function Header({ onMenuOpen, backendStatus }) {
  const marketClosed = true;
  const backendLabel =
    backendStatus === "connected"
      ? "Backend Connected"
      : backendStatus === "checking"
        ? "Backend Checking"
        : "Backend Disconnected";
  const marketStateText = marketClosed ? "Market Closed — as of 15:30 IST" : "Market Open";

  return (
    <>
      {backendStatus === "disconnected" && (
        <div className="relative z-50 bg-status-killed px-4 py-2 text-center text-[12px] font-semibold text-text-data">
          Backend disconnected. Start Spencer backend on 127.0.0.1:8787, then refresh.
        </div>
      )}
      <header className="sticky top-0 z-30 border-b border-border-grid bg-bg-void text-text-data font-sans">
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <button
              onClick={onMenuOpen}
              aria-label="Open menu"
              className="flex flex-col gap-[5px] px-1 py-1.5 text-text-muted hover:text-text-data"
            >
              <span className="block h-[1.5px] w-[18px] rounded-full bg-current" />
              <span className="block h-[1.5px] w-[18px] rounded-full bg-current" />
              <span className="block h-[1.5px] w-[18px] rounded-full bg-current" />
            </button>
            <h1 className="text-lg font-medium tracking-tight">Spencer AI</h1>
            <span className="font-mono text-xs text-text-muted hidden md:inline">Instrument Interface</span>
          </div>
          <div className="font-mono text-xs text-text-muted">
            {marketStateText}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 rounded-full border border-status-warn/30 bg-status-warn/10 px-2.5 py-1 text-[11px] font-mono text-status-warn">
              <span className="h-1.5 w-1.5 rounded-full bg-status-warn animate-pulse" />
              {marketClosed ? "Closed" : "Open"}
            </div>
            <button
              disabled
              title="Notifications are not configured in the local backend."
              aria-label="Notifications unavailable"
              className="flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-lg text-text-muted opacity-60"
            >
              <Bell className="h-4 w-4" />
            </button>
            <button onClick={onMenuOpen} className="grid h-8 w-8 place-items-center rounded-full border border-border-grid bg-bg-surface text-[10px] font-mono text-text-muted hover:text-text-data">
              TR
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-6 bg-bg-surface border-t border-border-grid px-6 py-2 font-mono text-[10px] uppercase tracking-widest text-text-muted">
          <span className="flex items-center gap-2 text-status-warn">
            <span className="h-1.5 w-1.5 rounded-full bg-status-warn animate-pulse" />
            PAPER MODE
          </span>
          <span className={backendStatus === "connected" ? "text-status-passed" : backendStatus === "checking" ? "text-status-warn" : "text-status-killed"}>
            [{backendLabel}]
          </span>
          <span className="text-status-warn">LIVE TRADING DISABLED</span>
          <span className="text-text-muted">[Broker Execution Disabled]</span>
        </div>
      </header>
    </>
  );
}`;
content = content.replace(headerRegex, newHeader);

// 3. PortfolioOverview
const portfolioRegex = /function PortfolioOverview\(\{ botState, backendStatus, watchlistCount = 0 \}\) \{[\s\S]*?return \([\s\S]*?\n  \);\n\}/;
const newPortfolio = `function PortfolioOverview({ botState, backendStatus, watchlistCount = 0 }) {
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
        <section className="bg-bg-surface border border-border-grid p-6 rounded-md font-sans text-text-data">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="mb-6 text-[10px] uppercase tracking-widest text-text-muted font-mono">Portfolio Value</div>
              <div className="font-mono text-3xl tracking-tight text-text-data">{isMissing(totalValue) ? "awaiting first real quote" : money(totalValue)}</div>
              <div className={\`mt-3 inline-flex font-mono text-xs \${safeNumber(totalPnl) >= 0 ? "text-status-passed" : "text-status-killed"}\`}>
                {isMissing(totalPnl) ? "awaiting first real quote" : \`\${totalPnl >= 0 ? "+" : ""}\${money(totalPnl)} (\${pct(capital.pnlPct)}) total P&L\`}
              </div>
            </div>
            <div className="space-y-2 text-right font-mono text-xs text-text-muted">
              <div><span className="text-[10px] uppercase tracking-widest block mb-1">Budget</span> <span className="text-text-data text-sm">{money(capital.budget)}</span></div>
              <div><span className="text-[10px] uppercase tracking-widest block mb-1">Invested</span> <span className="text-text-data text-sm">{money(capital.invested)}</span></div>
              <div><span className="text-[10px] uppercase tracking-widest block mb-1">Free cash</span> <span className="text-text-data text-sm">{money(capital.cash)}</span></div>
            </div>
          </div>
        </section>
        <section className="bg-bg-surface border border-border-grid p-6 rounded-md font-sans text-text-data">
          <div className="mb-6 text-[10px] font-mono uppercase tracking-widest text-text-muted">P&L Breakdown</div>
          <div className="space-y-4 font-mono text-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-muted">Unrealised</span>
              <span className={\`\${safeNumber(capital.unrealisedPnl) >= 0 ? "text-status-passed" : "text-status-killed"}\`}>
                {safeNumber(capital.unrealisedPnl) >= 0 ? "+" : ""}{money(capital.unrealisedPnl)}
              </span>
            </div>
            <div className="h-px bg-border-grid" />
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-muted">Realised</span>
              <span className={\`\${safeNumber(capital.realisedPnl) >= 0 ? "text-status-passed" : "text-status-killed"}\`}>
                {safeNumber(capital.realisedPnl) >= 0 ? "+" : ""}{money(capital.realisedPnl)}
              </span>
            </div>
            <div className="text-right text-[10px] uppercase tracking-widest text-text-muted">{metrics.closedTrades ?? "N/A"} closed trades</div>
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
          <section key={label} className="bg-bg-surface border border-border-grid p-4 rounded-md font-sans text-text-data">
            <div className="mb-3 text-[10px] font-mono uppercase tracking-widest text-text-muted">{label}</div>
            <div className="font-mono text-xl tracking-tight text-text-data">{value}</div>
            <div className="mt-2 text-[10px] font-mono text-text-muted">{sub}</div>
          </section>
        ))}
      </div>
    </div>
  );
}`;
content = content.replace(portfolioRegex, newPortfolio);

// 4. WidgetShell
const shellRegex = /function WidgetShell\(\{ title, icon: Icon, badge, children \}\) \{[\s\S]*?return \([\s\S]*?\n  \);\n\}/;
const newShell = `function WidgetShell({ title, icon: Icon, badge, children }) {
  return (
    <section className="bg-bg-surface border border-border-grid p-6 rounded-md font-sans text-text-data">
      <div className="mb-6 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {Icon && <Icon className="h-4 w-4 text-text-muted" />}
          <span className="text-[10px] font-mono uppercase tracking-widest text-text-muted">{title}</span>
        </div>
        {badge && <span className="rounded-sm border border-border-grid bg-bg-void px-2 py-1 text-[9px] font-mono uppercase tracking-widest text-text-muted">{badge}</span>}
      </div>
      {children}
    </section>
  );
}`;
content = content.replace(shellRegex, newShell);

// 5. MarketPulseWidget
const marketRegex = /function MarketPulseWidget\(\) \{[\s\S]*?return \([\s\S]*?\n  \);\n\}/;
const newMarket = `function MarketPulseWidget() {
  const { quotes, quoteStatus } = useQuotes([ONE_STOCK_SYMBOL]);
  const Row = ({ label, q }) => (
    <div className="flex items-center justify-between rounded-md border border-border-grid bg-bg-void px-3 py-2">
      <span className="text-[12px] font-mono text-text-data">{label === ONE_STOCK_SYMBOL ? "RELIANCE · NSE" : label}</span>
      {q && !isMissing(q.price) ? (
        <PriceStack value={q.price} source={q} />
      ) : (
        <span className="text-[11px] font-mono text-text-muted">{quoteStatus === "checking" ? "checking quote..." : "awaiting first real quote"}</span>
      )}
    </div>
  );
  return (
    <WidgetShell title="Market Pulse" icon={Activity} badge={quoteStatus === "ready" ? "Live market data" : "Data unavailable"}>
      <div className="space-y-4">
        <Row label={ONE_STOCK_SYMBOL} q={quotes[ONE_STOCK_SYMBOL]} />
        <div className="h-32 border border-border-grid bg-bg-void rounded flex items-center justify-center">
          <span className="font-mono text-xs text-text-muted">[ Visualization Area ]</span>
        </div>
        <div className="text-center font-mono text-[10px] text-text-muted">Backend quote route only</div>
      </div>
    </WidgetShell>
  );
}`;
content = content.replace(marketRegex, newMarket);

// 6. ResearchLedgerPanel
const researchRegex = /function ResearchLedgerPanel\(\) \{[\s\S]*?return \([\s\S]*?\n\s*\);\n\}/;
const newResearch = `function ResearchLedgerPanel() {
  const { ledger, status, health, loadLedger } = useResearchLedger();
  const candidates = asArray(ledger?.candidates);
  const scoreboard = ledger?.scoreboard || {};
  const coverage = ledger?.dataCoverage || {};
  const intraday = asArray(coverage.intraday);
  const scoreItems = [
    ["Functional", scoreboard.functional],
    ["Profitability", scoreboard.profitability],
    ["Composite", scoreboard.composite],
    ["Candidates tested", scoreboard.candidatesTested],
    ["Candidates killed", scoreboard.candidatesKilled],
    ["Validated edges", scoreboard.validatedEdges],
  ].filter(([, value]) => !isMissing(value));

  return (
    <section className="bg-bg-surface border border-border-grid p-6 rounded-md font-sans text-text-data mt-4" aria-labelledby="research-ledger-title" data-research-ledger-panel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted">Research Ledger</div>
          <h2 id="research-ledger-title" className="mt-1 text-lg font-medium tracking-tight text-text-data">Tested candidates and verdicts</h2>
          {scoreboard.updatedAt && (
            <div className="mt-1 font-mono text-[10px] text-text-muted">Scoreboard updated {scoreboard.updatedAt}</div>
          )}
        </div>
        <button onClick={loadLedger} disabled={status === "loading"} className="font-mono text-[10px] text-text-muted hover:text-text-data disabled:cursor-wait disabled:opacity-70">
          {status === "loading" ? "Checking" : "[ Refresh ]"}
        </button>
      </div>

      {status === "loading" && (
        <div className="research-ledger-loading mt-4 font-mono text-xs text-text-muted">Checking research ledger.</div>
      )}

      {status === "error" && (
        <div className="research-ledger-error mt-4 font-mono text-xs text-status-killed">
          Research ledger unavailable. {health.lastError ? apiText(health.lastError) : ""}
        </div>
      )}

      {status !== "loading" && status !== "error" && candidates.length === 0 && (
        <div className="research-ledger-empty mt-4 font-mono text-xs text-text-muted">No candidates tested yet.</div>
      )}

      {status !== "loading" && status !== "error" && (
        <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="research-ledger-candidates space-y-4">
            {candidates.map((candidate) => {
              const isPassed = candidate.status?.toUpperCase() === "PASSED";
              const colorClasses = isPassed 
                ? "border-status-passed/30 bg-status-passed/10 text-status-passed" 
                : "border-status-killed/30 bg-status-killed/10 text-status-killed";
              return (
                <article key={\`\${candidate.candidateId}-\${candidate.version}\`} className="research-ledger-candidate border border-border-grid bg-bg-void p-5 rounded-md flex flex-col gap-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="font-sans text-sm text-text-data leading-relaxed max-w-xl">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className="font-mono text-xs text-text-muted">{apiText(candidate.candidateId)}</span>
                        <span className="font-mono text-[10px] text-text-muted">v{apiText(candidate.version)}</span>
                      </div>
                      <details className="research-ledger-hypothesis cursor-pointer mt-1">
                        <summary className="font-medium">{apiText(candidate.hypothesis)}</summary>
                        <p className="mt-2 text-text-muted text-xs leading-5">{apiText(candidate.hypothesis)}</p>
                      </details>
                      {candidate.kill?.date && (
                        <div className="mt-2 text-[10px] font-mono text-status-killed">Killed {candidate.kill.date}</div>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-2 shrink-0">
                      <span className={\`px-2.5 py-1 border \${colorClasses} font-mono text-[10px] uppercase tracking-widest rounded-sm\`}>
                        {apiText(candidate.status)}
                      </span>
                      {candidate.kill?.reason && (
                        <div className="max-w-xs text-right font-mono text-[10px] text-status-killed">{candidate.kill.reason}</div>
                      )}
                    </div>
                  </div>

                  {asArray(candidate.stages).length === 0 ? (
                    <div className="mt-3 font-mono text-xs text-text-muted">No stage rows recorded.</div>
                  ) : (
                    <div className="research-ledger-stage-table mt-3 overflow-x-auto border-t border-border-grid pt-4">
                      <table className="min-w-full text-left font-mono text-xs">
                        <thead className="text-[10px] uppercase tracking-widest text-text-muted">
                          <tr>
                            <th className="px-3 py-2">Stage</th>
                            <th className="px-3 py-2">Status</th>
                            <th className="px-3 py-2 text-right">Trades</th>
                            <th className="px-3 py-2 text-right">Gross</th>
                            <th className="px-3 py-2 text-right">Costs</th>
                            <th className="px-3 py-2 text-right">Net</th>
                            <th className="px-3 py-2 text-right">Edge</th>
                            <th className="px-3 py-2 text-right">Bar</th>
                            <th className="px-3 py-2">Dataset</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border-grid/50">
                          {asArray(candidate.stages).map((stage, index) => (
                            <tr key={\`\${stage.stage}-\${index}\`} className="text-text-data">
                              <td className="whitespace-nowrap px-3 py-2">{apiText(stage.stage)}</td>
                              <td className="whitespace-nowrap px-3 py-2">{apiText(stage.status)}</td>
                              <td className="whitespace-nowrap px-3 py-2 text-right">{apiCount(stage.trades)}</td>
                              <td className="whitespace-nowrap px-3 py-2 text-right">{apiMoney(stage.gross_pnl)}</td>
                              <td className="whitespace-nowrap px-3 py-2 text-right">{apiMoney(stage.total_costs)}</td>
                              <td className="whitespace-nowrap px-3 py-2 text-right">{apiMoney(stage.net_pnl)}</td>
                              <td className="whitespace-nowrap px-3 py-2 text-right">{apiPct(stage.net_edge_pct)}</td>
                              <td className="whitespace-nowrap px-3 py-2 text-right">{apiPct(stage.cost_bar_required_pct)}</td>
                              <td className="min-w-[260px] px-3 py-2 text-[10px] text-text-muted">{stageRange(stage)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </article>
              );
            })}
          </div>

          <aside className="space-y-6">
            <section className="research-ledger-scoreboard">
              <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-4">Scoreboard</div>
              {scoreItems.length === 0 ? (
                <div className="text-xs font-mono text-text-muted">Scoreboard unavailable from API.</div>
              ) : (
                <div className="grid grid-cols-2 gap-4">
                  {scoreItems.map(([label, value]) => (
                    <div key={label} className="border border-border-grid bg-bg-void px-3 py-3 rounded-md">
                      <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">{label}</div>
                      <div className="text-lg font-mono text-text-data">{apiCount(value)}</div>
                    </div>
                  ))}
                </div>
              )}
              {scoreboard.basis && <div className="mt-3 font-mono text-[10px] text-text-muted">{scoreboard.basis}</div>}
            </section>

            <section className="research-ledger-coverage border-t border-border-grid pt-6">
              <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-4">Data Coverage</div>
              <div className="space-y-4 font-mono text-xs">
                {intraday.length === 0 ? (
                  <div className="text-text-muted">No intraday coverage rows recorded.</div>
                ) : (
                  intraday.map((row) => (
                    <div key={row.interval} className="border border-border-grid bg-bg-void px-3 py-3 rounded-md">
                      <div className="text-text-data mb-1">{apiText(row.interval)}: {apiCount(row.sessions)} sessions, growing daily</div>
                      <div className="text-[10px] text-text-muted">{apiCount(row.candles)} candles</div>
                      <div className="text-[10px] text-text-muted">{apiText(row.firstTs)} to {apiText(row.lastTs)}</div>
                    </div>
                  ))
                )}
                {coverage.daily?.lastTradeDate && (
                  <div className="border border-border-grid bg-bg-void px-3 py-3 rounded-md">
                    <div className="text-text-data mb-1">Daily close last stored</div>
                    <div className="text-[10px] text-text-muted">{coverage.daily.lastTradeDate}</div>
                  </div>
                )}
              </div>
            </section>
          </aside>
        </div>
      )}
    </section>
  );
}`;
content = content.replace(researchRegex, newResearch);

// 7. OrderTable
const orderTableRegex = /function OrderTable\(\{ title, rows \}\) \{[\s\S]*?return \([\s\S]*?\n  \);\n\}/;
const newOrderTable = `function OrderTable({ title, rows }) {
  return (
    <section className="bg-bg-surface border border-border-grid p-6 rounded-md font-sans text-text-data">
      <div className="flex items-center justify-between mb-6">
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted">{title}</div>
        <span className="rounded-sm border border-border-grid bg-bg-void px-2 py-1 text-[9px] font-mono uppercase tracking-widest text-text-muted">Backend journal</span>
      </div>
      {rows.length === 0 ? (
        <div className="border border-dashed border-border-grid rounded-md flex-1 flex items-center justify-center min-h-[160px] bg-bg-void/50">
          <div className="text-center">
            <p className="text-text-data font-sans text-sm mb-1.5">No position.</p>
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
content = content.replace(orderTableRegex, newOrderTable);

// 8. HoldingsTable
const holdingsTableRegex = /function HoldingsTable\(\{ rows \}\) \{[\s\S]*?return \([\s\S]*?\n  \);\n\}/;
const newHoldingsTable = `function HoldingsTable({ rows }) {
  return (
    <section className="bg-bg-surface border border-border-grid p-6 rounded-md font-sans text-text-data">
      <div className="flex items-center justify-between mb-6">
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted">Holdings - {rows.length}</div>
        <span className="rounded-sm border border-border-grid bg-bg-void px-2 py-1 text-[9px] font-mono uppercase tracking-widest text-text-muted">Backend journal</span>
      </div>
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
content = content.replace(holdingsTableRegex, newHoldingsTable);

fs.writeFileSync(path, content, 'utf8');
console.log('App.jsx updated with styling only!');
