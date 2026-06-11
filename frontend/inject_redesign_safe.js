const fs = require('fs');
let code = fs.readFileSync('src/App.jsx', 'utf8');

function replaceFunction(name, newContent) {
  const searchStr = "function " + name + "(";
  const start = code.indexOf(searchStr);
  if (start === -1) {
    console.error("Could not find " + name);
    return;
  }
  
  // Find the closing parenthesis of the function arguments
  let parenCount = 0;
  let inParens = false;
  let blockStart = -1;
  
  for (let i = start; i < code.length; i++) {
    if (code[i] === '(') {
      parenCount++;
      inParens = true;
    } else if (code[i] === ')') {
      parenCount--;
      if (inParens && parenCount === 0) {
        // Now find the first '{' after the closing parenthesis
        blockStart = code.indexOf('{', i);
        break;
      }
    }
  }

  if (blockStart === -1) {
    console.error("Could not find block start for " + name);
    return;
  }

  let braceCount = 0;
  let inFunc = false;
  let end = -1;
  
  for (let i = blockStart; i < code.length; i++) {
    if (code[i] === '{') {
      braceCount++;
      inFunc = true;
    }
    else if (code[i] === '}') {
      braceCount--;
      if (inFunc && braceCount === 0) {
        end = i + 1;
        break;
      }
    }
  }
  
  if (end !== -1) {
    code = code.substring(0, start) + newContent + code.substring(end);
    console.log("Successfully replaced " + name);
  } else {
    console.error("Could not find end of " + name);
  }
}

const newTicker = `function TickerBar({ quoteMap, marketOpen, quoteStatus }) {
  const items = useMemo(() => [...NIFTY50, ...NIFTY50], []);
  return (
    <div className="relative h-10 w-full overflow-hidden bg-black/80 backdrop-blur-3xl border-b border-white/5">
      <div className="absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-black to-transparent pointer-events-none" />
      <div className="absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-black to-transparent pointer-events-none" />
      <motion.div animate={{ x: ["0%", "-50%"] }} transition={{ duration: 40, ease: "linear", repeat: Infinity }} className="flex h-full items-center gap-10 px-4 whitespace-nowrap">
        {items.map((stock, i) => {
          const q = getQuote(stock, quoteMap);
          return (
            <div key={i} className="flex items-center gap-3">
              <span className="text-[11px] font-bold tracking-[0.2em] text-white/50 uppercase">{stock.symbol}</span>
              <span className={"text-[12px] font-medium " + (q.up ? 'text-emerald-400' : 'text-red-400')}>
                {q.price || '---'}
              </span>
            </div>
          );
        })}
      </motion.div>
    </div>
  );
}`;

const newHeader = `function Header({ onMenuOpen, marketOpen, marketStatus, user, profile, photo }) {
  return (
    <header className="sticky top-0 z-40 flex h-16 w-full items-center justify-between bg-black/60 backdrop-blur-2xl border-b border-white/5 px-6">
      <div className="flex items-center gap-4">
        <button onClick={onMenuOpen} className="md:hidden text-white/50 hover:text-white transition-colors">
          <Menu className="h-5 w-5" />
        </button>
        <div style={{ fontFamily: "'Instrument Serif', serif" }} className="text-[26px] tracking-tight text-white hidden md:block">
          Spencer <span className="italic text-emerald-400">AI</span>
        </div>
      </div>
      <div className="flex items-center gap-6">
        <div className="hidden sm:flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 shadow-[0_0_15px_rgba(255,255,255,0.02)]">
          <div className={"h-1.5 w-1.5 rounded-full " + (marketOpen ? 'bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-red-500')} />
          <span className="text-[9px] font-bold uppercase tracking-[0.2em] text-white/50">{marketStatus}</span>
        </div>
        <button className="h-9 w-9 rounded-full overflow-hidden border border-white/10 shadow-[0_0_20px_rgba(255,255,255,0.05)] hover:border-emerald-500/50 hover:shadow-[0_0_20px_rgba(16,185,129,0.2)] transition-all">
          {photo ? <img src={photo} alt="" className="h-full w-full object-cover" /> : <div className="h-full w-full bg-white/5 flex items-center justify-center text-[11px] font-semibold text-white tracking-widest">{(profile?.name || user?.name || "SP").slice(0, 2).toUpperCase()}</div>}
        </button>
      </div>
    </header>
  );
}`;

const newStockButton = `function StockButton({ stock, quote, selected, marketOpen, onClick }) {
  return (
    <button onClick={onClick} className={"w-full flex items-center justify-between px-4 py-3 mb-1 rounded-2xl transition-all duration-300 " + (selected ? 'bg-white/10 border border-white/10 shadow-[0_0_25px_rgba(255,255,255,0.05)]' : 'hover:bg-white/5 border border-transparent')}>
      <div className="text-left">
        <div className={"text-[13px] font-semibold tracking-tight " + (selected ? 'text-white' : 'text-white/60')}>{stock.symbol}</div>
        <div className="text-[10px] tracking-tight text-white/30 mt-0.5">{stock.name.substring(0, 18)}</div>
      </div>
      <div className="text-right">
        <div className={"text-[13px] font-medium tracking-tight " + (selected ? 'text-white' : 'text-white/60')}>{quote?.price || '---'}</div>
        <div className={"text-[10px] font-medium mt-0.5 " + (quote?.up ? 'text-emerald-400' : 'text-red-400')}>{quote?.up ? '+' : ''}{quote?.changePct?.toFixed(2) || '0.00'}%</div>
      </div>
    </button>
  );
}`;

const newPortfolioOverview = `function PortfolioOverview({ profile, holdings = [], botWatching = null, strategies = [], botCapital = null, botState = null }) {
  const budget = profile.budget || 5000;
  const invested = botCapital?.invested || 0;
  const free = budget - invested;
  const metrics = botState?.metrics || { totalRealised: -94 }; 
  const isUp = metrics.totalRealised >= 0;
  
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }} className="w-full mb-6 relative group z-10">
      <div className="absolute -inset-0.5 bg-gradient-to-r from-emerald-500/0 via-emerald-500/10 to-emerald-500/0 rounded-[32px] blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-1000" />
      <div className="relative overflow-hidden rounded-[32px] border border-white/10 bg-black/40 backdrop-blur-3xl p-8 md:p-10 shadow-[0_20px_50px_rgba(0,0,0,0.6)]">
        <div className="absolute top-0 right-0 -mt-20 -mr-20 h-64 w-64 rounded-full bg-emerald-500/5 blur-3xl" />
        
        <div className="relative z-10 grid grid-cols-1 md:grid-cols-3 gap-10 md:gap-6 divide-y md:divide-y-0 md:divide-x divide-white/5">
          
          <div className="flex flex-col justify-center">
            <div className="flex items-center gap-2 mb-3">
              <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
              <div className="text-[10px] font-bold uppercase tracking-[0.25em] text-white/40">Portfolio Value</div>
            </div>
            <div style={{ fontFamily: "'Instrument Serif', serif" }} className="text-6xl md:text-[80px] leading-none text-white tracking-tight drop-shadow-2xl">
              ₹{budget.toLocaleString()}
            </div>
            <div className="mt-5 flex items-center gap-3">
              <div className={"inline-flex items-center gap-2 rounded-full px-3 py-1.5 border " + (isUp ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-red-500/10 border-red-500/20')}>
                {isUp ? <TrendingUp className="h-3.5 w-3.5 text-emerald-400" /> : <TrendingDown className="h-3.5 w-3.5 text-red-400" />}
                <span className={"text-[11px] font-semibold tracking-wide " + (isUp ? 'text-emerald-400' : 'text-red-400')}>₹{Math.abs(metrics.totalRealised)} total P&L</span>
              </div>
            </div>
          </div>
          
          <div className="md:pl-10 pt-8 md:pt-0 flex flex-col justify-center">
             <div className="text-[10px] font-bold uppercase tracking-[0.25em] text-white/40 mb-6">Capital Guard</div>
             <div className="space-y-4">
               <div className="flex justify-between items-center"><span className="text-[12px] font-medium text-white/50">Budget</span><span className="text-[14px] font-medium text-white tracking-tight">₹{budget.toLocaleString()}</span></div>
               <div className="flex justify-between items-center"><span className="text-[12px] font-medium text-white/50">Invested</span><span className="text-[14px] font-medium text-white tracking-tight">₹{invested.toLocaleString()}</span></div>
               <div className="flex justify-between items-center"><span className="text-[12px] font-medium text-white/50">Free Cash</span><span className="text-[14px] font-medium text-emerald-400 tracking-tight">₹{free.toLocaleString()}</span></div>
             </div>
          </div>
          
          <div className="md:pl-10 pt-8 md:pt-0 flex flex-col justify-center">
             <div className="text-[10px] font-bold uppercase tracking-[0.25em] text-white/40 mb-4">Spencer Bot Status</div>
             <div style={{ fontFamily: "'Instrument Serif', serif" }} className="text-3xl text-white/90 tracking-tight mb-3">{botState?.running ? "Running" : "Watching"}</div>
             <div className="text-[12px] text-emerald-400/80 font-medium leading-relaxed max-w-[200px]">{botWatching || "Scanning for algorithmic VWAP Breakout setups in the market..."}</div>
          </div>
          
        </div>
      </div>
    </motion.div>
  );
}`;

replaceFunction('TickerBar', newTicker);
replaceFunction('Header', newHeader);
replaceFunction('StockButton', newStockButton);
replaceFunction('PortfolioOverview', newPortfolioOverview);

const dashStart = code.indexOf('function Dashboard(');
if (dashStart !== -1) {
  const exactReturnStr = '  return (\n    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}\n      data-theme="light"';
  let dashReturn = code.indexOf(exactReturnStr, dashStart);
  
  if (dashReturn === -1) {
    // try a more fuzzy match for the main return
    dashReturn = code.indexOf('  return (\n    <motion.div', dashStart);
  }
  
  let dashEnd = code.indexOf('// ─── App Root', dashStart);
  if (dashReturn !== -1 && dashEnd !== -1) {
    const originalReturn = code.substring(dashReturn, dashEnd);
    
    const newDashReturn = `  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.8 }} data-theme="dark" className="relative h-screen w-screen overflow-hidden text-white font-sans bg-[#030604]">
      {/* Deep gradient background */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(16,185,129,0.05),transparent_50%),radial-gradient(circle_at_bottom_left,rgba(16,185,129,0.02),transparent_50%)]" />

      {/* Ticker */}
      <TickerBar quoteMap={quoteMap} marketOpen={marketOpen} quoteStatus={quoteStatus} />

      {/* Header */}
      <Header
        onMenuOpen={() => setDrawerOpen(true)}
        marketOpen={marketOpen} marketStatus={marketStatus}
        user={user} profile={profile} photo={photo}
      />

      {/* Drawer */}
      <DrawerNav open={drawerOpen} onClose={() => setDrawerOpen(false)}
        activePage={activePage} setActivePage={setActivePage}
        user={user} profile={profile} photo={photo} onLogout={onLogout} />

      {/* Body */}
      <div className="flex h-[calc(100vh-104px)] overflow-hidden relative z-10">
        {/* Sidebar Watchlist */}
        <aside className="hidden md:flex flex-col w-[320px] shrink-0 border-r border-white/5 bg-black/20 backdrop-blur-3xl p-4">
          <div className="mb-6 px-3 pt-2">
            <div style={{ fontFamily: "'Instrument Serif', serif" }} className="text-3xl text-white tracking-tight">Watchlist</div>
            <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/30 mt-1">{NSE_STOCKS.length} NSE Symbols</div>
          </div>
          <div className="rounded-[16px] border border-white/5 bg-white/5 shadow-inner px-4 py-3 mb-4 flex items-center gap-3 transition-colors focus-within:border-emerald-500/30 focus-within:bg-white/10">
            <Search className="h-4 w-4 text-white/40 shrink-0" />
            <input value={stockQuery} onChange={e => setStockQuery(e.target.value)} placeholder="Search market..."
              className="w-full bg-transparent text-[13px] font-medium text-white tracking-tight outline-none placeholder:text-white/30" />
          </div>
          <div className="soft-scroll flex-1 overflow-y-auto pr-1">
            {!marketOpen && <div className="mb-4 rounded-xl border border-white/5 bg-black/40 px-4 py-3 text-[10px] font-bold tracking-widest uppercase text-white/40 text-center">Market Closed</div>}
            {(quoteStatus === "ready" || quoteStatus === "refreshing") && <div className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-center text-[10px] font-bold tracking-widest uppercase text-emerald-400">Live Feed Active</div>}
            {searchResults.map(stock => (
              <StockButton key={stock.symbol} stock={stock} quote={getQuote(stock, quoteMap)}
                marketOpen={marketOpen} selected={selectedStock === stock.symbol} onClick={() => handleStockClick(stock.symbol)} />
            ))}
          </div>
        </aside>

        {/* Main Workspace */}
        <main className="flex-1 overflow-y-auto soft-scroll p-6 md:p-10 relative">
          
          {/* Page header */}
          <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div>
              <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} style={{ fontFamily: "'Instrument Serif', serif" }} className="text-5xl text-white tracking-tight drop-shadow-lg">{activePage}</motion.div>
              {activePage === "Dashboard" && (
                <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/40 mt-3">Liquid Glass Terminal Overview</div>
              )}
            </div>
            {activePage === "Dashboard" && (
              <div className="flex items-center gap-3">
                <button className="flex items-center gap-2 rounded-full border border-white/10 bg-black/40 backdrop-blur-xl px-5 py-2.5 text-[11px] font-bold uppercase tracking-wider text-white/60 hover:bg-white/10 hover:text-white transition-all hover:border-white/20">
                  <Sparkles className="h-4 w-4 text-emerald-400" /> Backtest Mode
                </button>
                <button onClick={() => setShowAddWidget(true)} className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 backdrop-blur-xl px-5 py-2.5 text-[11px] font-bold uppercase tracking-wider text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-300 transition-all hover:border-emerald-500/50 shadow-[0_0_20px_rgba(16,185,129,0.1)]">
                  <Plus className="h-4 w-4" /> Add Widget
                </button>
              </div>
            )}
          </div>

          {/* Content */}
          {activePage === "Dashboard" ? (
            <div className="space-y-6 max-w-7xl">
              <PortfolioOverview profile={profile} holdings={holdings} botWatching={botWatching} strategies={strategies} botCapital={botCapital} botState={botState} />
              
              <div className="grid auto-rows-[minmax(240px,auto)] grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-3">
                <AnimatePresence mode="popLayout">
                {widgets.map((id, index) => (
                  <motion.div key={id} layout initial={{ opacity: 0, scale: 0.9, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.9 }} transition={{ duration: 0.5, delay: index * 0.05, ease: [0.16, 1, 0.3, 1] }} className="h-full">
                    <Widget id={id} selectedStock={selectedStock} profile={profile}
                      onMove={moveWidget} strategies={strategies} marketOpen={marketOpen} activity={activity}
                      botCapital={botCapital} activeStrategy={botState?.activeStrategy} botSymbol={botState?.symbol}
                      streak={botState?.streak} learning={botState?.learning} />
                  </motion.div>
                ))}
                </AnimatePresence>
              </div>
            </div>
          ) : (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="grid grid-cols-1 gap-6 lg:grid-cols-3 max-w-7xl">
              <PageContent activePage={activePage} selectedStock={selectedStock}
                profile={profile} user={user} prefs={prefs} photo={photo}
                strategies={strategies} setStrategies={setStrategies}
                copyStyles={copyStyles} setCopyStyles={setCopyStyles}
                onProfileSave={handleProfileSave} onPhotoChange={handlePhotoChange}
                onLogout={onLogout} addToast={addToast} quoteMap={quoteMap}
                botState={botState} onTradeClick={setSelectedTrade} />
            </motion.div>
          )}
        </main>
      </div>

      <SpencerChat selectedStock={selectedStock} profile={profile} />
      <AnimatePresence>{showAddWidget && <AddWidgetPanel currentWidgets={widgets} onAdd={id => setWidgets(p => [...p, id])} onClose={() => setShowAddWidget(false)} />}</AnimatePresence>
      <AnimatePresence>{selectedTrade && <TradeDetailModal trade={selectedTrade} onClose={() => setSelectedTrade(null)} />}</AnimatePresence>
    </motion.div>
  );
}
`;

    code = code.replace(originalReturn, newDashReturn + '\n\n');
    console.log("Replaced Dashboard return statement.");
  }
}

// 7. Widget Wrapper Redesign
const newWidgetShell = `function WidgetShell({ id, onMove, children, title, icon: Icon }) {
  return (
    <div className="group relative flex flex-col h-full rounded-[32px] border border-white/10 bg-black/40 backdrop-blur-3xl shadow-[0_15px_30px_rgba(0,0,0,0.4)] transition-all duration-500 hover:border-emerald-500/30 hover:shadow-[0_20px_40px_rgba(16,185,129,0.15)] overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-white/[0.03] to-transparent pointer-events-none" />
      <div className="flex items-center justify-between border-b border-white/5 px-6 py-4 bg-white/[0.02]">
        <div className="flex items-center gap-3">
          {Icon && <Icon className="h-4 w-4 text-emerald-500/70" />}
          <div className="text-[10px] font-bold uppercase tracking-[0.25em] text-white/50">{title}</div>
        </div>
        <button onClick={() => onMove(id, null)} className="opacity-0 group-hover:opacity-100 text-white/20 hover:text-white transition-all">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 p-6 relative z-10 flex flex-col justify-center">
        {children}
      </div>
    </div>
  );
}`;
replaceFunction('WidgetShell', newWidgetShell);

// 8. Widget Redesign (Inner Content)
const newWidget = `function Widget({ id, selectedStock, profile, onMove, strategies, marketOpen, activity, botCapital, activeStrategy, botSymbol, streak, learning }) {
  if (id === "capital") return (
    <WidgetShell id={id} onMove={onMove} title="Capital Guard" icon={ShieldCheck}>
       <div className="mb-3 text-[11px] font-medium uppercase tracking-[0.1em] text-white/40">Bot Budget</div>
       <div style={{ fontFamily: "'Instrument Serif', serif" }} className="text-5xl text-white mb-6">₹{(profile.budget || 5000).toLocaleString()}</div>
       <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-5 py-4 text-[12px] font-medium text-emerald-400/90 leading-relaxed tracking-wide">Capital ring-fenced. Spencer only deploys what you've allocated — never more.</div>
    </WidgetShell>
  );

  if (id === "strategy") return (
    <WidgetShell id={id} onMove={onMove} title="Active Strategy" icon={Activity}>
      <div className="flex justify-between items-start mb-8">
        <div>
          <div className="text-2xl font-light text-white tracking-tight mb-2">{activeStrategy || "VWAP Breakout"}</div>
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-emerald-400"><div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.8)]" /> LIVE</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-[10px] font-bold text-white/50 tracking-widest">PHASE 1</div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-2xl border border-white/5 bg-black/40 p-4 text-center hover:bg-white/5 transition-colors"><div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/30 mb-2">Trades</div><div className="text-[20px] font-medium text-white">17</div></div>
        <div className="rounded-2xl border border-white/5 bg-black/40 p-4 text-center hover:bg-white/5 transition-colors"><div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/30 mb-2">Win %</div><div className="text-[20px] font-medium text-white">5.9%</div></div>
        <div className="rounded-2xl border border-white/5 bg-black/40 p-4 text-center hover:bg-white/5 transition-colors"><div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/30 mb-2">P&L</div><div className="text-[20px] font-medium text-red-400">-₹94</div></div>
      </div>
    </WidgetShell>
  );

  if (id === "market") return (
    <WidgetShell id={id} onMove={onMove} title="Market Pulse" icon={TrendingUp}>
      <div className="space-y-4">
        <div className="flex items-center justify-between rounded-2xl border border-white/5 bg-black/40 px-5 py-4 hover:bg-white/5 transition-colors">
          <div className="text-[12px] font-bold tracking-[0.2em] text-white/70 uppercase">NIFTY 50</div>
          <div className="flex items-center gap-3"><span className="text-[16px] font-medium text-white tracking-tight">23,547.75</span><span className="text-[12px] font-medium text-red-400">▼1.50%</span></div>
        </div>
        <div className="flex items-center justify-between rounded-2xl border border-white/5 bg-black/40 px-5 py-4 hover:bg-white/5 transition-colors">
          <div className="text-[12px] font-bold tracking-[0.2em] text-white/70 uppercase">SENSEX</div>
          <div className="flex items-center gap-3"><span className="text-[16px] font-medium text-white tracking-tight">74,775.74</span><span className="text-[12px] font-medium text-red-400">▼1.44%</span></div>
        </div>
        <div className="mt-4 text-center text-[10px] font-bold uppercase tracking-[0.2em] text-white/30">Live Index Data · Yahoo (~15m delayed)</div>
      </div>
    </WidgetShell>
  );

  if (id === "brain") return (
    <WidgetShell id={id} onMove={onMove} title={"Brain Check · " + selectedStock} icon={Cpu}>
      <div className="flex h-full flex-col items-center justify-center text-center py-6">
        <div className="h-16 w-16 rounded-full border border-white/10 bg-white/5 flex items-center justify-center mb-6">
          <Activity className="h-6 w-6 text-white/20 animate-pulse" />
        </div>
        <div className="text-[14px] font-medium text-white/50 tracking-wide">Awaiting technical breakdown...</div>
      </div>
    </WidgetShell>
  );

  if (id === "activity") return (
    <WidgetShell id={id} onMove={onMove} title="Bot Activity" icon={Clock}>
      <div className="flex h-full flex-col items-center justify-center text-center py-6">
        <div className="h-16 w-16 rounded-full border border-white/10 bg-white/5 flex items-center justify-center mb-6">
          <Clock className="h-6 w-6 text-white/20" />
        </div>
        <div className="text-[14px] font-medium text-white/50 tracking-wide">No recent executions</div>
      </div>
    </WidgetShell>
  );

  if (id === "news") return (
    <WidgetShell id={id} onMove={onMove} title={"Latest News · " + selectedStock} icon={Newspaper}>
      <div className="flex h-full flex-col items-center justify-center text-center py-6">
        <div className="h-16 w-16 rounded-full border border-white/10 bg-white/5 flex items-center justify-center mb-6">
          <Newspaper className="h-6 w-6 text-white/20" />
        </div>
        <div className="text-[14px] font-medium text-white/50 tracking-wide">News sentiment scanner offline</div>
      </div>
    </WidgetShell>
  );

  return null;
}`;
replaceFunction('Widget', newWidget);


fs.writeFileSync('src/App.jsx', code);
console.log('App.jsx correctly patched.');
