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
import { Profile } from "./pages/Profile";
import { WhatIsSpencer } from "./pages/WhatIsSpencer";

import { useBotState } from "./hooks/useBotState";
import { useQuotes } from "./hooks/useQuotes";
import { useResearch } from "./hooks/useResearch";
import { useResearchLedger } from "./hooks/useResearchLedger";
import { useHealth } from "./hooks/useHealth";
import { useLocalProfile } from "./hooks/useLocalProfile";
import { ONE_STOCK_SYMBOL } from "./utils/constants";

function Section({ title, children }) {
  return (
    <section>
      <h2 className="mb-5 font-display text-[20px] font-semibold tracking-tight text-[var(--color-primary-dark-text)]">
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

  const [activePage, setActivePage] = useState("Dashboard");
  const [menuOpen, setMenuOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const mainRef = useRef(null);
  const quote = quotes[ONE_STOCK_SYMBOL] || {};
  const navigate = (page) => {
    setActivePage(page);
    mainRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="app-shell flex h-screen flex-col font-sans text-[var(--color-primary-dark-text)]">
      <Header
        onMenuOpen={() => setMenuOpen(true)}
        onNavigate={navigate}
        onChatOpen={() => setChatOpen(true)}
        backendStatus={backendStatus}
        quote={quote}
      />

      <main
        ref={mainRef}
        className="content-scroll soft-scroll relative flex-1 overflow-y-auto"
      >
        <div className="mx-auto max-w-[1480px] px-5 py-6 md:px-10 md:py-10">
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
            <div className="space-y-12">
              <Section title="Orders"><Orders botState={botState} /></Section>
              <Section title="Holdings"><Holdings botState={botState} /></Section>
              <Section title="Positions"><Positions botState={botState} /></Section>
            </div>
          )}

          {activePage === "Funds" && (
            <div className="space-y-12">
              <Section title="Funds"><Funds botState={botState} /></Section>
              <Section title="Trade Tracker"><TradeTracker botState={botState} /></Section>
            </div>
          )}

          {activePage === "Brain" && (
            <div className="space-y-12">
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
      </main>

      <NavigationDrawer
        open={menuOpen}
        activePage={activePage}
        onNavigate={(page) => {
          navigate(page);
          setMenuOpen(false);
        }}
        onClose={() => setMenuOpen(false)}
      />
      <SpencerChat open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
