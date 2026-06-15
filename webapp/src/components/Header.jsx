import { BrainCircuit } from "lucide-react";
import { ONE_STOCK_SYMBOL } from "../utils/constants";
import { priceText } from "../utils/helpers";

export function Header({ onMenuOpen, onNavigate, onChatOpen, backendStatus, quote }) {
  const isConnected = backendStatus === "connected";
  const isChecking = backendStatus === "checking";
  const marketOpen = String(quote?.marketState || "").toUpperCase() === "OPEN";
  const change = Number(quote?.changePct ?? quote?.regularMarketChangePercent ?? NaN);
  const isUp = change > 0;
  const isDown = change < 0;

  return (
    <header className="site-header sticky top-0 z-30">
      <div className="relative flex min-h-14 items-center justify-between gap-4 px-5 py-2 md:px-8">
        <button
          onClick={onMenuOpen}
          className="glass-pill flex flex-col gap-[5px] p-3 text-slate-700 transition-colors hover:text-slate-950"
          aria-label="Menu"
        >
          <span className="block h-px w-[18px] bg-current" />
          <span className="block h-px w-[14px] bg-current" />
          <span className="block h-px w-[18px] bg-current" />
        </button>

        <button
          type="button"
          onClick={() => onNavigate("WhatIsSpencer")}
          className="glass-pill inline-flex px-3.5 py-2 text-[11px] font-semibold text-slate-700 transition-colors hover:text-slate-950"
        >
          What is Spencer
        </button>

        {/* Centered wordmark */}
        <div
          className="logo-font absolute left-1/2 hidden -translate-x-1/2 text-[22px] sm:block"
          style={{ color: "#0f172a" }}
        >
          Spencer
        </div>

        <div className="ml-auto flex items-center gap-2">
          {/* Quote chip */}
          <div className="glass-pill hidden items-center gap-2 px-3 py-1.5 2xl:flex">
            <span className="text-[12px] font-semibold text-slate-900">
              {ONE_STOCK_SYMBOL}
            </span>
            <span className="text-[12px] text-slate-600">
              {priceText(quote?.price)}
            </span>
            {!Number.isNaN(change) && (
              <span
                className="text-[12px] font-medium"
                style={{ color: isUp ? "#087f5b" : isDown ? "#c2415d" : "#475569" }}
              >
                {isUp ? "+" : ""}{change.toFixed(2)}%
              </span>
            )}
            <span className="rounded-full bg-white/45 px-2.5 py-0.5 text-[10px] font-semibold text-slate-700">
              {marketOpen ? "Live" : "Closed"}
            </span>
          </div>

          <span
            className="glass-pill hidden items-center gap-1.5 px-3 py-1.5 text-[10px] font-semibold text-slate-700 sm:inline-flex"
          >
            <span
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ background: isConnected ? "var(--color-verified-accent)" : "#94a3b8" }}
            />
            {isConnected ? "Backend connected" : isChecking ? "Backend checking" : "Backend offline"}
          </span>

          <span className="glass-pill hidden px-3 py-1.5 text-[10px] font-semibold text-blue-700 md:inline">Paper mode</span>
          <span className="glass-pill hidden px-3 py-1.5 text-[10px] font-semibold text-rose-700 lg:inline">Live trading off</span>
          <span className="glass-pill hidden px-3 py-1.5 text-[10px] font-semibold text-slate-700 lg:inline">Broker execution off</span>

          <button
            type="button"
            onClick={onChatOpen}
            className="glass-pill inline-flex h-9 items-center gap-2 px-3 text-[11px] font-semibold text-slate-800"
          >
            <BrainCircuit className="h-4 w-4" />
            <span className="hidden xl:inline">Ask brain</span>
          </button>

          <button
            onClick={onMenuOpen}
            aria-label="Open navigation"
            className="glass-pill flex h-9 w-9 items-center justify-center text-[10px] font-semibold text-slate-900"
          >
            TR
          </button>
        </div>
      </div>
    </header>
  );
}
