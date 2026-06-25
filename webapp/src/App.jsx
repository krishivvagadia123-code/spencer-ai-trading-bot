import { useState, useRef } from "react";
import { Header } from "./components/Header";
import { NavigationDrawer } from "./components/NavigationDrawer";
import { SpencerChat } from "./components/SpencerChat";

import { Dashboard } from "./pages/Dashboard";
import { Orders } from "./pages/Orders";
import { Holdings } from "./pages/Holdings";
import { Positions } from "./pages/Positions";
import { Funds } from "./pages/Funds";
import { Bids } from "./pages/Bids";
import { Brain } from "./pages/Brain";
import { Research } from "./pages/Research";
import { Governance } from "./pages/Governance";
import { TradeTracker } from "./pages/TradeTracker";
import { TradesResets } from "./pages/TradesResets";
import { Profile } from "./pages/Profile";
import { WhatIsSpencer } from "./pages/WhatIsSpencer";

import { useBotState } from "./hooks/useBotState";
import { useQuotes } from "./hooks/useQuotes";
import { useResearch } from "./hooks/useResearch";
import { useResearchLedger } from "./hooks/useResearchLedger";
import { useTradesResets } from "./hooks/useTradesResets";
import { useHealth } from "./hooks/useHealth";
import { useLocalProfile } from "./hooks/useLocalProfile";
import { ONE_STOCK_SYMBOL } from "./utils/constants";

function Section({ title, children }) {
  return (
    <section className="page-section">
      <h2 className="section-title">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function App() {
  const [profile, setProfile] = useLocalProfile();
  const { botState, backendStatus } = useBotState(profile);
  const { quotes } = useQuotes([ONE_STOCK_SYMBOL]);
  const { row: researchRow, status: researchStatus, loadResearch } = useResearch(ONE_STOCK_SYMBOL);
  const { ledger, status: ledgerStatus } = useResearchLedger();
  const { health, status: healthStatus, loadHealth } = useHealth();
  const { data: tradesResets, status: tradesResetsStatus, reload: reloadTradesResets } = useTradesResets();

  const [activePage, setActivePage] = useState("Dashboard");
  const [chatOpen, setChatOpen] = useState(false);

  const mainRef = useRef(null);
  const quote = quotes[ONE_STOCK_SYMBOL] || {};
  const navigate = (page) => {
    setActivePage(page);
    mainRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="app-shell flex h-screen font-sans text-[var(--color-primary-dark-text)]">
      <NavigationDrawer
        activePage={activePage}
        onNavigate={navigate}
      />

      <main
        ref={mainRef}
        className="content-scroll soft-scroll relative flex-1 overflow-y-auto pb-24 lg:pb-0"
      >
        <div className="mx-auto w-full max-w-[1480px] min-w-0 px-4 py-4 md:px-8 md:py-6">
          <Header
            activePage={activePage}
            onNavigate={navigate}
            onChatOpen={() => setChatOpen(true)}
            backendStatus={backendStatus}
            quote={quote}
          />

          <div className="page-content mt-5 md:mt-7">
          {activePage === "Dashboard" && (
            <Dashboard
              mainRef={mainRef}
              botState={botState}
              backendStatus={backendStatus}
              quote={quote}
              ledger={ledger}
              health={health}
              healthStatus={healthStatus}
              refreshHealth={loadHealth}
              setActivePage={setActivePage}
            />
          )}

          {activePage === "Orders" && (
            <div className="page-stack">
              <Section title="Orders"><Orders botState={botState} /></Section>
              <Section title="Holdings"><Holdings botState={botState} /></Section>
              <Section title="Positions"><Positions botState={botState} /></Section>
            </div>
          )}

          {activePage === "Funds" && (
            <div className="page-stack">
              <Section title="Funds"><Funds botState={botState} /></Section>
              <Section title="Trade Tracker"><TradeTracker botState={botState} /></Section>
              <Section title="Trades & Resets">
                <TradesResets data={tradesResets} status={tradesResetsStatus} reload={reloadTradesResets} />
              </Section>
            </div>
          )}

          {activePage === "Brain" && (
            <div className="page-stack">
              <Section title="Brain"><Brain row={researchRow} status={researchStatus} loadResearch={loadResearch} botState={botState} /></Section>
              <Section title="Research"><Research ledger={ledger} status={ledgerStatus} /></Section>
            </div>
          )}

          {activePage === "Bids" && <Bids botState={botState} />}
          {activePage === "Governance" && <Governance botState={botState} />}
          {activePage === "Profile" && <Profile profile={profile} setProfile={setProfile} />}
          {activePage === "WhatIsSpencer" && (
            <WhatIsSpencer
              mainRef={mainRef}
              quote={quote}
              botState={botState}
              ledger={ledger}
              onNavigate={navigate}
            />
          )}
          </div>
        </div>
      </main>
      <SpencerChat open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
