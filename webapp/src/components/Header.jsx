import { BrainCircuit, Search, UserCircle } from "lucide-react";
import { ONE_STOCK_SYMBOL } from "../utils/constants";
import { priceText } from "../utils/helpers";

const pageLabels = {
  WhatIsSpencer: "What is Spencer",
};

export function Header({ activePage, onNavigate, onChatOpen, backendStatus, quote }) {
  const isConnected = backendStatus === "connected";
  const isChecking = backendStatus === "checking";
  const hasQuote = Number.isFinite(Number(quote?.price));
  const statusLabel = isConnected
    ? "Backend connected"
    : isChecking
      ? "Backend checking"
      : hasQuote
        ? "Market data connected"
        : "Backend offline";
  const marketOpen = String(quote?.marketState || "").toUpperCase() === "OPEN";
  const change = Number(quote?.changePct ?? quote?.regularMarketChangePercent ?? NaN);
  const isUp = change > 0;
  const isDown = change < 0;
  const title = pageLabels[activePage] || activePage || "Dashboard";

  return (
    <header className="spencer-command-bar">
      <div className="command-title">
        <div className="hidden min-w-[132px] md:block">
          <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--theme-muted)]">
            Spencer AI
          </div>
          <div className="truncate text-[18px] font-bold leading-tight text-[var(--theme-text)]">{title}</div>
        </div>

        <div className="command-search">
          <Search className="h-4 w-4 text-[var(--theme-muted)]" />
          <span className="truncate text-[12px] font-medium text-[var(--theme-muted)]">
            Search Spencer, RELIANCE, research ledger...
          </span>
        </div>
      </div>

      <div className="command-market">
        <span className="command-chip">
          <span className={`h-1.5 w-1.5 rounded-full ${marketOpen ? "live-pulse bg-violet-300" : "bg-slate-500"}`} />
          {ONE_STOCK_SYMBOL}
        </span>
        <span className="command-chip">{priceText(quote?.price)}</span>
        {!Number.isNaN(change) && (
          <span className={`command-chip ${isUp ? "text-violet-100" : isDown ? "text-rose-200" : ""}`}>
            {isUp ? "+" : ""}{change.toFixed(2)}%
          </span>
        )}
      </div>

      <div className="command-actions">
        <span className="command-chip command-status">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: isConnected || hasQuote ? "#a78bfa" : "#64748b" }}
          />
          {statusLabel}
        </span>
        <button
          type="button"
          onClick={onChatOpen}
          className="command-action-button"
          aria-label="Ask Spencer brain"
        >
          <BrainCircuit className="h-4 w-4" />
          <span className="hidden text-[11px] font-bold uppercase tracking-[0.12em] xl:inline">Ask</span>
        </button>
        <button
          type="button"
          onClick={() => onNavigate("Profile")}
          className="command-profile"
          aria-label="Profile"
        >
          <span className="hidden text-[11px] font-bold uppercase tracking-[0.12em] md:inline">Krish</span>
          <UserCircle className="h-6 w-6" />
        </button>
      </div>
    </header>
  );
}
