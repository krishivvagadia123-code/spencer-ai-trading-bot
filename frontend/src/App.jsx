import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  Bell,
  Brain,
  CircleDollarSign,
  ClipboardList,
  LineChart,
  LogOut,
  MessageCircle,
  PieChart,
  Plus,
  Search,
  Send,
  ShieldCheck,
  UserRound,
  Wallet,
  X,
} from "lucide-react";
import { NSE_STOCKS } from "./stocks";
import { NIFTY50_SYMS, ONE_STOCK_SYMBOL, SPENCER_API_BASE } from "./utils/constants";

const LOCAL_USER = { id: "local", name: "Trader", email: "" };
const DEFAULT_PROFILE = {
  name: "Trader",
  botName: "Spencer",
  tradeType: "Paper Journal",
  risk: "Capital Defense",
  budget: 5000,
  selectedStocks: [ONE_STOCK_SYMBOL],
};
const PAGES = [
  ["Dashboard", BarChart3],
  ["Orders", ClipboardList],
  ["Holdings", Wallet],
  ["Positions", LineChart],
  ["Funds", CircleDollarSign],
  ["Bids", ClipboardList],
  ["Brain", Brain],
  ["Research", BarChart3],
  ["Governance", ShieldCheck],
  ["Trade Tracker", PieChart],
];

const isMissing = (value) =>
  value === null || value === undefined || value === "" || !Number.isFinite(Number(value));
const asArray = (value) => (Array.isArray(value) ? value : []);
const safeNumber = (value, fallback = 0) => {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
};
const money = (value, digits = 0) =>
  isMissing(value)
    ? "N/A"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: digits,
      }).format(Number(value));
const qty = (value) =>
  isMissing(value) ? "N/A" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const pct = (value, digits = 2) => (isMissing(value) ? "N/A" : `${Number(value).toFixed(digits)}%`);
// P&L colors derive from the live sign; zero/unavailable stays neutral — a
// zero is not a profit and must never render green.
const pnlSign = (value) => (safeNumber(value) > 0 ? "+" : "");
const pnlTone = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "text-[#64748b]";
  return n > 0 ? "text-emerald-600" : "text-red-600";
};
const pnlChipTone = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "border-[#e2e8f0] bg-[#f8fafc] text-[#475569]";
  return n > 0 ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700";
};
const fmtIST = (ts) => {
  const d = new Date(ts);
  if (!ts || Number.isNaN(d.getTime())) return String(ts || "N/A");
  return `${d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })} IST`;
};
const dateOnly = (ts) => (ts ? String(ts).slice(0, 10) : "N/A");
const normalizeResearchSymbol = (symbol) => {
  const raw = String(symbol || "").trim().toUpperCase();
  if (!raw) return "RELIANCE.NS";
  return raw.includes(".") ? raw : `${raw}.NS`;
};
const displayName = (value) =>
  String(value || "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
// Human-facing symbol: ".NS" is a Yahoo internal suffix, never shown to users.
const prettySymbol = (value) => {
  const raw = String(value || "").trim().toUpperCase();
  const base = raw.replace(/\.(NS|BO)$/i, "");
  return base ? `${base} · NSE` : "RELIANCE · NSE";
};
const sanitizeReason = (value) =>
  String(value || "N/A")
    .replace(/\s*score=[\d.]+/gi, "")
    .replace(/strategy=[^\s]+/gi, "strategy=backend-paper")
    .trim() || "N/A";
const timeLabel = () =>
  new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const statusLabel = (status) => {
  if (status === "ready" || status === "refreshing" || status === "connected") return "OK";
  if (status === "checking" || status === "loading") return "Checking";
  if (status === "empty" || status === "unavailable") return "Data unavailable";
  if (status === "disconnected") return "Backend disconnected";
  if (status === "error") return "Error";
  return "Data unavailable";
};
const statusTone = (value) => {
  const text = String(value || "").toLowerCase();
  if (text === "ok" || text === "enabled" || text === "disabled") return "text-emerald-700";
  if (text.includes("checking")) return "text-amber-700";
  if (text.includes("unavailable") || text.includes("disconnected") || text.includes("error")) return "text-red-600";
  return "text-[#020617]";
};
const oneStockProfile = (profile = {}) => ({
  ...DEFAULT_PROFILE,
  ...profile,
  budget: 5000,
  selectedStocks: [ONE_STOCK_SYMBOL],
});
const priceText = (value) => (isMissing(value) ? "awaiting first real quote" : money(value, 2));
const priceMeta = (source) => source?.priceLabel || source?.marketStateLabel || "awaiting first real quote";

function PriceStack({ value, source, align = "right" }) {
  return (
    <span className={`block ${align === "right" ? "text-right" : "text-left"}`}>
      <span className="block font-semibold">{priceText(value)}</span>
      <span className="block text-[10px] font-medium normal-case tracking-normal text-[#94a3b8]">{priceMeta(source)}</span>
    </span>
  );
}

function useLocalProfile() {
  const [profile, setProfile] = useState(() => {
    try {
      return oneStockProfile(JSON.parse(localStorage.getItem("spencer-profile") || "null") || {});
    } catch {
      return oneStockProfile();
    }
  });
  const setOneStockProfile = useCallback((next) => {
    setProfile((previous) => oneStockProfile(typeof next === "function" ? next(previous) : next));
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem("spencer-profile", JSON.stringify(oneStockProfile(profile)));
    } catch {
      // Local profile persistence is best-effort only.
    }
  }, [profile]);
  return [profile, setOneStockProfile];
}

function useBotState(profile) {
  const [botState, setBotState] = useState(null);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [botHealth, setBotHealth] = useState({ status: "checking", lastSuccess: null, lastError: null });

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(`${SPENCER_API_BASE}/api/bot/state`, { cache: "no-store" });
        if (!res.ok) throw new Error("state unavailable");
        const data = await res.json();
        if (!cancelled) {
          setBotState(data);
          setBackendStatus("connected");
          setBotHealth({ status: "connected", lastSuccess: timeLabel(), lastError: null });
        }
      } catch (error) {
        if (!cancelled) {
          setBackendStatus("disconnected");
          setBotHealth({
            status: "disconnected",
            lastSuccess: null,
            lastError: error?.message || "Bot State API request failed",
          });
        }
      }
    };
    const pushConfig = async () => {
      try {
        await fetch(`${SPENCER_API_BASE}/api/bot/config`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ budget: 5000, symbol: ONE_STOCK_SYMBOL }),
        });
      } catch {
        // The state poll owns visible backend status.
      }
    };

    poll();
    pushConfig();
    const timer = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [profile?.budget]);

  return { botState, backendStatus, botHealth };
}

function useQuotes(symbols) {
  const [quotes, setQuotes] = useState({});
  const [quoteStatus, setQuoteStatus] = useState("checking");
  const [quoteHealth, setQuoteHealth] = useState({ status: "checking", lastSuccess: null, lastError: null });

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const clean = asArray(symbols).filter(Boolean);
      if (!clean.length) {
        setQuoteStatus("unavailable");
        setQuoteHealth({ status: "unavailable", lastSuccess: null, lastError: "No quote symbols selected" });
        return;
      }
      setQuoteStatus((previous) => (previous === "ready" ? "refreshing" : "checking"));
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 25000);
      try {
        const res = await fetch(`${SPENCER_API_BASE}/api/quotes?symbols=${encodeURIComponent(clean.join(","))}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!res.ok) throw new Error("quotes unavailable");
        const data = await res.json();
        const next = {};
        for (const item of asArray(data?.quotes)) {
          if (item?.symbol) next[item.symbol.replace(/\.NS$/i, "")] = item;
        }
        if (!cancelled) {
          setQuotes(next);
          const hasQuotes = Object.keys(next).length > 0;
          setQuoteStatus(hasQuotes ? "ready" : "unavailable");
          setQuoteHealth({
            status: hasQuotes ? "ready" : "unavailable",
            lastSuccess: hasQuotes ? timeLabel() : null,
            lastError: hasQuotes ? null : "Quotes API returned no rows",
          });
        }
      } catch (error) {
        if (!cancelled) {
          setQuoteStatus("unavailable");
          setQuoteHealth({
            status: error?.name === "AbortError" ? "error" : "unavailable",
            lastSuccess: null,
            lastError: error?.name === "AbortError" ? "Quotes API request timed out" : error?.message || "Quotes API request failed",
          });
        }
      } finally {
        clearTimeout(timeout);
      }
    };
    load();
    const timer = setInterval(load, 60000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [symbols]);

  return { quotes, quoteStatus, quoteHealth };
}

function StatusCard({ title, message, icon: Icon = ClipboardList }) {
  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-10 text-center shadow-sm">
      <Icon className="mx-auto mb-3 h-10 w-10 text-[#64748b]" />
      <div className="text-[14px] font-semibold text-[#111827]">{title}</div>
      <p className="mx-auto mt-1.5 max-w-sm text-[12px] leading-5 text-[#64748b]">{message}</p>
    </div>
  );
}

function Header({ onMenuOpen, backendStatus }) {
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
          <div className="min-w-0 flex-1 truncate px-3 text-center font-display text-[20px] font-semibold tracking-tight text-[#0f172a]">Spencer AI</div>
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
        <div className="flex flex-wrap items-center justify-center gap-2 border-t border-[#f1f5f9] bg-[#fafbfc] px-4 py-2 text-[11px] font-medium">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-0.5 text-blue-600">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
            Paper mode
          </span>
          {backendStatus !== "disconnected" && (
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 ${
                backendStatus === "connected"
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-amber-50 text-amber-700"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  backendStatus === "connected" ? "bg-emerald-500" : "bg-amber-400"
                }`}
              />
              {backendLabel}
            </span>
          )}
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-slate-500">Live trading off</span>
        </div>
      </header>
    </>
  );
}

function TickerBar({ stocks, quotes }) {
  // Single-line items so nothing ever clips; the bar scrolls only while the
  // market is OPEN — a closed market is static data and the instrument should
  // hold still (also spares the compositor an endless repaint).
  const marketOpen = stocks.some((stock) => {
    const state = String(quotes[stock.symbol]?.marketState || "").toUpperCase();
    return state === "OPEN";
  });
  const items = marketOpen ? [...stocks, ...stocks] : stocks;
  const meta = priceMeta(quotes[stocks[0]?.symbol] || {});
  return (
    <div className="flex h-9 items-center overflow-hidden border-b border-white/10 bg-[#0b1220] text-white">
      <div className={`flex min-w-max items-center gap-10 px-5 ${marketOpen ? "animate-[marquee_45s_linear_infinite]" : ""}`}>
        {items.map((stock, index) => {
          const quote = quotes[stock.symbol] || {};
          const change = Number(quote.changePct ?? quote.regularMarketChangePercent);
          const up = Number.isFinite(change) ? change > 0 : null;
          const flat = Number.isFinite(change) && change === 0;
          return (
            <span key={`${stock.symbol}-${index}`} className="flex items-center gap-2.5 whitespace-nowrap text-[12px]">
              <span className={`h-1.5 w-1.5 rounded-full ${up === null || flat ? "bg-slate-400" : up ? "bg-emerald-400" : "bg-red-400"}`} />
              <span className="font-semibold tracking-wide">{stock.symbol}</span>
              <span className="font-display tabular-nums text-white/90">{priceText(quote.price)}</span>
              {!isMissing(change) && (
                <span className={`tabular-nums ${flat ? "text-slate-400" : up ? "text-emerald-400" : "text-red-400"}`}>
                  {change > 0 ? "+" : ""}{change.toFixed(2)}%
                </span>
              )}
            </span>
          );
        })}
      </div>
      <div className="ml-auto hidden shrink-0 items-center gap-2 border-l border-white/10 px-4 text-[10px] font-medium uppercase tracking-[0.18em] text-white/55 sm:flex">
        {meta}
      </div>
    </div>
  );
}

function Drawer({ open, activePage, setActivePage, onClose }) {
  if (!open) return null;
  const navigate = (page) => {
    setActivePage(page);
    onClose();
  };
  return (
    <>
      <button aria-label="Close menu overlay" className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-[2px]" onClick={onClose} />
      <aside className="fixed left-0 top-0 z-50 flex h-full w-[270px] flex-col border-r border-[#e5e7eb] bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-100 px-4 py-4">
          <div>
            <div className="text-[13px] font-semibold text-[#020617]">Trader</div>
            <div className="text-[11px] text-[#64748b]">Paper Trading Studio</div>
          </div>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full text-[#94a3b8] hover:bg-gray-100">
            <X className="h-4 w-4" />
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-2">
          {PAGES.map(([name, Icon]) => (
            <button
              key={name}
              onClick={() => navigate(name)}
              className={`mb-0.5 flex w-full items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium ${
                activePage === name ? "bg-[#eff6ff] text-[#1d4ed8]" : "text-[#111827] hover:bg-[#f1f5f9]"
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {name}
              {activePage === name && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#2563eb]" />}
            </button>
          ))}
          <div className="my-2 h-px bg-gray-100" />
          <button
            onClick={() => navigate("Profile")}
            className={`mb-0.5 flex w-full items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium ${
              activePage === "Profile" ? "bg-[#eff6ff] text-[#1d4ed8]" : "text-[#111827] hover:bg-[#f1f5f9]"
            }`}
          >
            <UserRound className="h-4 w-4 shrink-0" />
            Profile
          </button>
        </nav>
      </aside>
    </>
  );
}

function Sidebar({ selectedStock, setSelectedStock, allowedStocks, quoteMap, quoteStatus }) {
  const [query, setQuery] = useState("");
  const rows = useMemo(() => {
    const term = query.toLowerCase().trim();
    const source = term
      ? allowedStocks.filter((s) => `${s.symbol} ${s.name} ${s.sector}`.toLowerCase().includes(term))
      : allowedStocks;
    return source;
  }, [query, allowedStocks]);

  return (
    <aside className="hidden w-[280px] shrink-0 flex-col border-r border-[#e5e7eb] bg-white p-3 md:flex">
      <div className="mb-3 px-2">
        <div className="text-sm font-semibold text-[#020617]">Stocks</div>
        <div className="text-xs text-[#64748b]">RELIANCE only</div>
      </div>
      <label className="mb-2 flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2.5">
        <Search className="h-3.5 w-3.5 text-[#94a3b8]" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search stock, sector..."
          className="w-full bg-transparent text-sm text-[#020617] outline-none placeholder:text-[#64748b]"
        />
      </label>
      <div className="mb-2 rounded-md border border-blue-100 bg-[#eff6ff] px-3 py-2 text-center text-[10px] font-semibold text-[#2563eb]">
        {quoteStatus === "ready" || quoteStatus === "refreshing" ? "Quote feed connected" : "Quote feed unavailable"}
      </div>
      <div className="flex-1 overflow-y-auto pr-1">
        {rows.map((stock) => {
          const quote = quoteMap[stock.symbol] || {};
          const change = Number(quote.changePct ?? quote.regularMarketChangePercent);
          const up = Number.isFinite(change) ? change >= 0 : null;
          return (
            <button
              key={stock.symbol}
              onClick={() => setSelectedStock(stock.symbol)}
              className={`mb-1 flex w-full items-center justify-between rounded-md px-3 py-2 text-left ${
                selectedStock === stock.symbol ? "bg-[#eff6ff] text-[#2563eb]" : "hover:bg-[#f8fafc]"
              }`}
            >
              <span className="min-w-0">
                <span className="block text-[13px] font-semibold">{stock.symbol}</span>
                <span className="block truncate text-[11px] text-[#64748b]">{stock.name}</span>
              </span>
              <span className="shrink-0 text-right text-[12px] font-semibold text-[#020617]">
                <PriceStack value={quote.price} source={quote} />
                {!isMissing(change) && <span className={`block text-[10px] ${up ? "text-emerald-600" : "text-red-600"}`}>{up ? "+" : ""}{change.toFixed(2)}%</span>}
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

function PortfolioOverview({ botState, backendStatus, watchlistCount = 0 }) {
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
              <div className="font-display text-[40px] font-semibold leading-none tracking-tight text-[#020617] tabular-nums">{isMissing(totalValue) ? "awaiting first real quote" : money(totalValue)}</div>
              <div className={`mt-2 inline-flex rounded-md border px-2 py-1 text-[12px] font-semibold tabular-nums ${pnlChipTone(totalPnl)}`}>
                {isMissing(totalPnl) ? "awaiting first real quote" : `${pnlSign(totalPnl)}${money(totalPnl)} (${pct(capital.pnlPct)}) total P&L`}
              </div>
            </div>
            <div className="space-y-0.5 text-right text-[11px] text-[#64748b]">
              <div>Budget: <span className="font-semibold text-[#111827]">{money(capital.budget)}</span></div>
              <div>Invested: <span className="font-semibold text-[#111827]">{money(capital.invested)}</span></div>
              <div>Free cash: <span className="font-semibold text-[#111827]">{money(capital.cash)}</span></div>
            </div>
          </div>
          <div className="mt-5 flex h-20 items-center justify-center rounded-lg border border-dashed border-[#e2e8f0] bg-[#fafbfd] px-4 text-center text-[12px] text-[#94a3b8]">
            No equity history yet in this epoch — the curve begins with the first paper trade.
          </div>
        </section>
        <section className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm">
          <div className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-[#94a3b8]">P&L Breakdown</div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#64748b]">Unrealised</span>
              <span className={`font-semibold tabular-nums ${pnlTone(capital.unrealisedPnl)}`}>
                {pnlSign(capital.unrealisedPnl)}{money(capital.unrealisedPnl)}
              </span>
            </div>
            <div className="h-px bg-gray-100" />
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#64748b]">Realised</span>
              <span className={`font-semibold tabular-nums ${pnlTone(capital.realisedPnl)}`}>
                {pnlSign(capital.realisedPnl)}{money(capital.realisedPnl)}
              </span>
            </div>
            <div className="text-right text-[11px] text-[#94a3b8]">{metrics.closedTrades ?? "N/A"} closed trades</div>
          </div>
        </section>
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          ["Holdings", holdings.length, holdings.length === 1 ? "1 position open" : `${holdings.length} positions open`],
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
}

function WidgetShell({ title, icon: Icon, badge, children }) {
  return (
    <section className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="h-4 w-4 text-[#2563eb]" />}
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#94a3b8]">{title}</span>
        </div>
        {badge && <span className="rounded border border-blue-100 bg-blue-50 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-blue-600">{badge}</span>}
      </div>
      {children}
    </section>
  );
}

function CapitalGuardWidget({ botState }) {
  const capital = botState?.capital || {};
  const budget = capital.budget ?? 5000;
  const invested = capital.invested ?? 0;
  const cash = capital.cash ?? 0;
  const deployedPct = budget > 0 ? Math.min((safeNumber(invested) / budget) * 100, 100) : 0;
  return (
    <WidgetShell title="Capital Guard" icon={ShieldCheck} badge="Backend capital">
      <div className="text-[11px] uppercase tracking-wider text-[#94a3b8]">Bot Budget</div>
      <div className="text-[28px] font-semibold text-[#020617]">{money(budget)}</div>
      <div className="mt-2 flex justify-between text-[11px] text-[#64748b]">
        <span>Deployed: <b>{money(invested)}</b></span>
        <span>Free: <b>{money(cash)}</b></span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100">
        <div className="h-full rounded-full bg-[#2563eb]" style={{ width: `${deployedPct}%` }} />
      </div>
      <div className="mt-3 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-[12px] leading-5 text-emerald-800">
        Spencer is paper-only and only displays backend capital state.
      </div>
    </WidgetShell>
  );
}

function StrategyWidget({ botState, backendStatus }) {
  const strategy = botState?.activeStrategy;
  return (
    <WidgetShell title="Active Strategy" icon={ShieldCheck} badge={backendStatus === "connected" ? "Backend state" : "Data unavailable"}>
      {backendStatus !== "connected" ? (
        <div className="text-[12px] text-[#64748b]">Backend disconnected. Strategy state unavailable.</div>
      ) : strategy ? (
        <>
          <div className="text-[15px] font-semibold capitalize text-[#020617]">{displayName(strategy.name || strategy.id || "Backend strategy")}</div>
          <p className="mt-3 text-[11px] leading-5 text-[#64748b]">Backend strategy state loaded. No frontend success metrics, P&L, or progress is fabricated.</p>
        </>
      ) : (
        <StatusCard title="No verified strategy tests found." message="The backend has not published an active strategy or verified strategy-test dataset." icon={ShieldCheck} />
      )}
    </WidgetShell>
  );
}

function BrainWidget({ selectedStock }) {
  const { row, status } = useResearch(selectedStock);
  return (
    <WidgetShell title={`Brain Check · ${prettySymbol(selectedStock)}`} icon={Brain} badge={status === "ready" ? "Real backend data" : "Data unavailable"}>
      {status === "loading" ? (
        <div className="rounded-md border border-blue-100 bg-[#eff6ff] px-3 py-2 text-[12px] text-[#2563eb]">Checking Spencer research engine...</div>
      ) : status !== "ready" ? (
        <div className="text-[12px] text-[#64748b]">{researchStatusText(status)}</div>
      ) : (
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          {researchMetrics(row).map(([label, value]) => (
            <div key={label} className="rounded-md border border-gray-100 bg-[#f8fafc] px-2 py-1.5">
              <div className="text-[9px] uppercase text-[#94a3b8]">{label}</div>
              <div className="text-[12px] font-semibold text-[#111827]">{value}</div>
            </div>
          ))}
        </div>
      )}
    </WidgetShell>
  );
}

function MarketPulseWidget() {
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
}

function ActivityWidget({ botState, backendStatus }) {
  const activity = asArray(botState?.activity);
  return (
    <WidgetShell title="Bot Activity" icon={Activity} badge={backendStatus === "connected" ? "Backend journal" : "Data unavailable"}>
      {backendStatus !== "connected" ? (
        <div className="text-[12px] text-[#64748b]">Backend disconnected. Activity unavailable.</div>
      ) : activity.length ? (
        <div className="space-y-1.5">
          {activity.slice(0, 5).map((event, index) => (
            <div key={`${event.time}-${index}`} className="rounded-md border border-gray-100 bg-[#f8fafc] px-3 py-2">
              <div className="truncate text-[12px] font-medium text-[#111827]">{event.text || event.message || "Activity unavailable"}</div>
              <div className="mt-0.5 text-[10px] text-[#94a3b8]">{event.time || "N/A"}</div>
            </div>
          ))}
        </div>
      ) : (
        <StatusCard title="No bot activity yet" message="Backend activity will appear here once paper events are recorded." icon={Activity} />
      )}
    </WidgetShell>
  );
}

function TrustWidget({ backendStatus, botHealth, quoteHealth, selectedStock }) {
  const { health: researchHealth } = useResearch(selectedStock);
  const lastSuccess =
    researchHealth.lastSuccess || quoteHealth?.lastSuccess || botHealth?.lastSuccess || "Not yet";
  const lastError =
    researchHealth.lastError || quoteHealth?.lastError || botHealth?.lastError || "None";
  const rows = [
    ["Backend URL", "127.0.0.1:8787"],
    ["Bot State endpoint status", statusLabel(botHealth?.status || backendStatus)],
    ["Quotes endpoint status", statusLabel(quoteHealth?.status)],
    ["Research endpoint status", statusLabel(researchHealth.status)],
    ["Last API success", lastSuccess],
    ["Last API error", lastError],
    ["Paper Mode", "Enabled"],
    ["Live Trading", "Disabled"],
    ["Broker Execution", "Disabled"],
  ];
  return (
    <WidgetShell title="Frontend Trust Check" icon={ShieldCheck} badge={backendStatus === "connected" ? "Backend state" : "Backend disconnected"}>
      <div className="space-y-2 text-[11px]">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between">
            <span className="text-[#64748b]">{label}</span>
            <span className={`max-w-[58%] truncate text-right font-semibold ${statusTone(value)}`}>{value}</span>
          </div>
        ))}
      </div>
    </WidgetShell>
  );
}

function DashboardPage({ botState, backendStatus, selectedStock, openAddWidget, botHealth, quoteHealth, watchlistCount }) {
  if (backendStatus !== "connected") {
    return (
      <div className="space-y-4">
        <PortfolioOverview botState={botState} backendStatus={backendStatus} watchlistCount={watchlistCount} />
        <ResearchLedgerPanel />
        <BrainWidget selectedStock={selectedStock} />
        <TrustWidget backendStatus={backendStatus} botHealth={botHealth} quoteHealth={quoteHealth} selectedStock={selectedStock} />
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <PortfolioOverview botState={botState} backendStatus={backendStatus} watchlistCount={watchlistCount} />
      <ResearchLedgerPanel />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
        <CapitalGuardWidget botState={botState} />
        <StrategyWidget botState={botState} backendStatus={backendStatus} />
        <BrainWidget selectedStock={selectedStock} />
        <MarketPulseWidget />
        <ActivityWidget botState={botState} backendStatus={backendStatus} />
        <TrustWidget backendStatus={backendStatus} botHealth={botHealth} quoteHealth={quoteHealth} selectedStock={selectedStock} />
      </div>
      <AddWidgetModalLauncher onClick={openAddWidget} />
    </div>
  );
}

function AddWidgetModalLauncher({ onClick }) {
  return (
    <button onClick={onClick} className="sr-only">
      Open add widget panel
    </button>
  );
}

function AddWidgetPanel({ onClose }) {
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-white/70 p-4 backdrop-blur-xl" onClick={onClose}>
      <section className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-5 shadow-xl" onClick={(event) => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <div className="font-semibold text-[#020617]">Add widget</div>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full bg-gray-100">
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="text-sm text-[#64748b]">All backend-backed widgets are already on the dashboard.</p>
      </section>
    </div>
  );
}

function backendGate(backendStatus, message, Icon) {
  if (backendStatus === "connected") return null;
  return (
    <StatusCard
      title={backendStatus === "checking" ? "Checking backend" : "Backend disconnected"}
      message={message}
      icon={Icon}
    />
  );
}

function OrdersPage({ botState, backendStatus, onTradeClick }) {
  const gate = backendGate(backendStatus, "Orders and trades require the Spencer backend state API.", ClipboardList);
  if (gate) return gate;
  const orders = asArray(botState?.orders);
  const closed = asArray(botState?.trades).filter((trade) => !isMissing(trade.pnl));
  const metrics = botState?.metrics || {};
  const realisedPnl = botState?.capital?.realisedPnl ?? closed.reduce((sum, trade) => sum + safeNumber(trade.pnl), 0);
  return (
    <div className="space-y-4">
      <SummaryGrid
        cards={[
          ["Orders", orders.length],
          ["Closed Trades", metrics.closedTrades ?? closed.length],
          ["Wins / Losses", `${metrics.wins ?? 0} / ${metrics.losses ?? 0}`],
          ["Realised P&L", `${pnlSign(realisedPnl)}${money(realisedPnl)}`],
        ]}
      />
      <TradeTable title={`Closed Paper Trades - ${closed.length}`} rows={closed} onTradeClick={onTradeClick} />
      <OrderTable title={`Order Book - ${orders.length}`} rows={orders} />
    </div>
  );
}

function HoldingsPage({ botState, backendStatus }) {
  const gate = backendGate(backendStatus, "Holdings require the Spencer backend state API.", Wallet);
  if (gate) return gate;
  const holdings = asArray(botState?.holdings);
  const capital = botState?.capital || {};
  return (
    <div className="space-y-4">
      <SummaryGrid
        cards={[
          ["Holdings", holdings.length],
          ["Invested", money(capital.invested)],
          ["Current Value", isMissing(capital.currentValue) ? "awaiting first real quote" : money(capital.currentValue)],
          ["Unrealised P&L", isMissing(capital.unrealisedPnl) ? "awaiting first real quote" : `${pnlSign(capital.unrealisedPnl)}${money(capital.unrealisedPnl)} ${pct(capital.unrealisedPnlPct)}`],
        ]}
      />
      <HoldingsTable rows={holdings} />
    </div>
  );
}

function PositionsPage({ botState, backendStatus }) {
  const gate = backendGate(backendStatus, "Open paper positions require backend holdings data.", LineChart);
  if (gate) return gate;
  return <PositionsTable rows={asArray(botState?.holdings)} />;
}

function FundsPage({ botState, backendStatus, profile }) {
  const gate = backendGate(backendStatus, "Funds require backend capital data.", CircleDollarSign);
  if (gate) return gate;
  const capital = botState?.capital || {};
  const budget = capital.budget ?? profile?.budget ?? 5000;
  const invested = capital.invested ?? 0;
  const cash = capital.cash ?? 0;
  const investedPct = budget > 0 ? Math.min((safeNumber(invested) / budget) * 100, 100) : 0;
  const cashPct = budget > 0 ? Math.min((safeNumber(cash) / budget) * 100, 100) : 0;
  return (
    <div className="space-y-4">
      <SummaryGrid
        cards={[
          ["Bot Budget", money(budget)],
          ["Invested", money(invested)],
          ["Free Cash", money(cash)],
          ["Unrealised P&L", isMissing(capital.unrealisedPnl) ? "awaiting first real quote" : `${pnlSign(capital.unrealisedPnl)}${money(capital.unrealisedPnl)}`],
        ]}
      />
      <section className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm">
        <div className="mb-3 text-[13px] font-semibold text-[#020617]">Capital Allocation</div>
        <div className="flex h-2 overflow-hidden rounded-full bg-gray-100">
          <div className="bg-[#2563eb]" style={{ width: `${investedPct}%` }} />
          <div className="bg-[#cbd5e1]" style={{ width: `${cashPct}%` }} />
        </div>
        <div className="mt-3 flex gap-5 text-[11px] text-[#64748b]">
          <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#2563eb]" />Invested {investedPct.toFixed(1)}%</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#cbd5e1]" />Free cash {cashPct.toFixed(1)}%</span>
        </div>
      </section>
    </div>
  );
}

function BidsPage({ botState, backendStatus }) {
  const gate = backendGate(backendStatus, "Bids require a backend bids dataset.", ClipboardList);
  if (gate) return gate;
  if (!Array.isArray(botState?.bids)) {
    return <StatusCard title="Data unavailable" message="The backend state response does not currently publish a bids dataset." icon={ClipboardList} />;
  }
  const bids = botState.bids;
  return (
    <section className="rounded-xl border border-[#e5e7eb] bg-white shadow-sm">
      <div className="border-b border-gray-100 px-5 py-3 text-[13px] font-semibold text-[#020617]">Pending Paper Bids - {bids.length}</div>
      {bids.length === 0 ? (
        <StatusCard title="No pending paper bids recorded yet" message="Backend returned an empty bids list." icon={ClipboardList} />
      ) : (
        <SimpleTable headings={["Symbol", "Qty", "Price", "Status"]} rows={bids.map((bid) => [bid.symbol || "N/A", qty(bid.qty), money(bid.price ?? bid.trigger, 2), bid.status || "N/A"])} />
      )}
    </section>
  );
}

function BrainPage({ selectedStock }) {
  const research = useResearch(selectedStock);
  return <ResearchPanel selectedStock={selectedStock} {...research} />;
}

function ResearchPage() {
  return <ResearchLedgerPanel />;
}

function TradeTrackerPage({ botState, backendStatus, onTradeClick }) {
  const gate = backendGate(backendStatus, "Trade Tracker requires backend paper trade data.", PieChart);
  if (gate) return gate;
  const closed = asArray(botState?.trades).filter((trade) => !isMissing(trade.pnl));
  const realisedPnl = botState?.capital?.realisedPnl ?? closed.reduce((sum, trade) => sum + safeNumber(trade.pnl), 0);
  return (
    <div className="space-y-4">
      <SummaryGrid
        cards={[
          ["Realised P&L", `${pnlSign(realisedPnl)}${money(realisedPnl)}`],
          ["Closed Trades", closed.length],
          ["Wins", botState?.metrics?.wins ?? 0],
          ["Losses", botState?.metrics?.losses ?? 0],
        ]}
      />
      {closed.length === 0 ? (
        <StatusCard title="No real paper trades recorded yet" message="Closed backend paper trades will appear here after the journal records realised P&L." icon={Activity} />
      ) : (
        <TradeTable title="Backend Paper Trade Tracker" rows={closed} onTradeClick={onTradeClick} />
      )}
    </div>
  );
}

function GovernancePage({ botState, backendStatus }) {
  if (backendStatus !== "connected") {
    return <StatusCard title="Backend disconnected" message="Governance contract unavailable until the backend is running." icon={ShieldCheck} />;
  }
  const capabilities = botState?.governance?.capabilities || botState?.capabilities || {};
  const actions = capabilities.actions || {};
  return (
    <div className="space-y-3">
      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#64748b]">Backend authority</div>
        <div className="mt-1 text-[18px] font-semibold text-[#020617]">{capabilities.mode || botState?.governance?.mode || "paper-only"}</div>
        <div className="mt-1 text-[12px] leading-5 text-[#475569]">{capabilities.sourceOfTruth || botState?.source || "backend"}</div>
      </section>
      <section className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        {Object.entries(actions).map(([key, action]) => (
          <div key={key} className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[13px] font-semibold text-[#020617]">{action.label || key}</div>
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${action.allowed ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
                {action.allowed ? "Allowed" : "Blocked"}
              </span>
            </div>
            <div className="mt-2 text-[11px] uppercase tracking-[0.12em] text-[#64748b]">Owner: {action.owner || "backend"}</div>
            {asArray(action.reasons).slice(0, 2).map((reason, index) => (
              <div key={index} className="mt-2 text-[12px] leading-5 text-[#475569]">{reason}</div>
            ))}
          </div>
        ))}
      </section>
      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="text-[12px] font-semibold text-[#020617]">Workflow state</div>
        <div className="mt-1 text-[12px] text-[#475569]">{botState?.workflow?.source || "Waiting for backend workflow status"}</div>
        <div className="mt-2 text-[11px] text-[#64748b]">Live trading: blocked | Broker execution: blocked | AI order approval: blocked</div>
      </section>
    </div>
  );
}

function ProfilePage({ profile, setProfile }) {
  const [draft, setDraft] = useState(profile);
  useEffect(() => setDraft(profile), [profile]);
  const save = () => setProfile({ ...profile, ...draft });
  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm">
        <div className="grid gap-3 md:grid-cols-2">
          <label>
            <div className="mb-1 text-xs text-[#64748b]">Display name</div>
            <input value={draft.name || ""} onChange={(event) => setDraft((p) => ({ ...p, name: event.target.value }))} className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-[#020617] outline-none focus:border-blue-400" />
          </label>
          <label>
            <div className="mb-1 text-xs text-[#64748b]">Bot profile name</div>
            <input value={draft.botName || ""} onChange={(event) => setDraft((p) => ({ ...p, botName: event.target.value }))} className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-[#020617] outline-none focus:border-blue-400" />
          </label>
        </div>
      </section>
      <section className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#64748b]">Trade Type</div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
          {["Paper Journal", "Observe Only", "Manual Review"].map((item) => (
            <button key={item} onClick={() => setDraft((p) => ({ ...p, tradeType: item }))} className={`rounded-lg border p-3 text-left text-xs font-semibold ${draft.tradeType === item ? "border-blue-400 bg-blue-50 text-blue-700" : "border-gray-200 bg-gray-50"}`}>
              {item}
            </button>
          ))}
        </div>
      </section>
      <section className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#64748b]">Risk Mode</div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
          {["Capital Defense", "Balanced", "Manual Approval Only", "Conservative Swing"].map((item) => (
            <button key={item} onClick={() => setDraft((p) => ({ ...p, risk: item }))} className={`rounded-lg border p-3 text-left text-xs font-semibold ${draft.risk === item ? "border-emerald-400 bg-emerald-50 text-emerald-700" : "border-gray-200 bg-gray-50"}`}>
              {item}
            </button>
          ))}
        </div>
      </section>
      <section className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#64748b]">Preferences</div>
        {["Push Notifications", "Email Alerts", "Sound Alerts", "Compact Mode"].map((label) => (
          <div key={label} className="flex items-center justify-between border-b border-gray-100 py-2 last:border-b-0">
            <div>
              <div className="text-sm font-medium text-[#020617]">{label}</div>
              <div className="text-xs text-[#64748b]">Local preference only</div>
            </div>
            <span className="h-6 w-11 rounded-full bg-gray-200" />
          </div>
        ))}
      </section>
      <div className="flex gap-3">
        <button onClick={save} className="flex-1 rounded-xl bg-[#2563eb] py-3 text-sm font-semibold text-white">Save Changes</button>
        <button disabled title="This local dashboard has no remote session to sign out from." className="flex w-full cursor-not-allowed items-center justify-center gap-2 rounded-xl border border-gray-200 bg-[#f8fafc] py-3 text-sm font-semibold text-[#94a3b8]">
          <LogOut className="h-4 w-4" />
          Local profile only
        </button>
      </div>
    </div>
  );
}

function SummaryGrid({ cards }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {cards.map(([label, value]) => (
        <section key={label} className="rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-sm">
          <div className="mb-1 text-[11px] uppercase tracking-wider text-[#94a3b8]">{label}</div>
          <div className="text-[20px] font-semibold text-[#020617]">{value}</div>
        </section>
      ))}
    </div>
  );
}

function SimpleTable({ headings, rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead className="border-b border-gray-100 bg-[#f8fafc]">
          <tr>{headings.map((heading) => <th key={heading} className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-[#64748b]">{heading}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-gray-50 hover:bg-[#f8fafc]">
              {row.map((cell, cellIndex) => <td key={cellIndex} className="px-4 py-3 text-[#374151]">{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeTable({ title, rows, onTradeClick }) {
  return (
    <section className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
        <div className="text-[13px] font-semibold text-[#020617]">{title}</div>
        <span className="rounded border border-blue-100 bg-blue-50 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-blue-600">Backend journal</span>
      </div>
      {rows.length === 0 ? (
        <StatusCard title="No real paper trades recorded yet" message="Backend returned an empty closed-trades list." icon={ClipboardList} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="border-b border-gray-100 bg-[#f8fafc]">
              <tr>{["Time", "Symbol", "Side", "Qty", "Price", "P&L", "Reason", "Status"].map((heading) => <th key={heading} className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-[#64748b]">{heading}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((trade, index) => (
                <tr key={`${trade.time}-${trade.symbol}-${index}`} onClick={() => onTradeClick?.(trade)} className="cursor-pointer border-b border-gray-50 hover:bg-[#eff6ff]/40">
                  <td className="px-4 py-3 font-mono text-[11px] text-[#64748b]">{trade.time || "N/A"}</td>
                  <td className="px-4 py-3 font-semibold text-[#020617]">{trade.symbol || "N/A"}</td>
                  <td className={`px-4 py-3 font-semibold ${trade.side === "BUY" ? "text-emerald-600" : trade.side === "SELL" ? "text-red-600" : "text-[#64748b]"}`}>{trade.side || "N/A"}</td>
                  <td className="px-4 py-3 text-[#374151]">{qty(trade.qty)}</td>
                  <td className="px-4 py-3 text-[#374151]"><PriceStack value={trade.price} source={{ priceLabel: trade.priceLabel || (trade.time ? `journaled at ${trade.time}` : null) }} /></td>
                  <td className={`px-4 py-3 font-semibold tabular-nums ${pnlTone(trade.pnl)}`}>{isMissing(trade.pnl) ? "N/A" : `${pnlSign(trade.pnl)}${money(trade.pnl)}`}</td>
                  <td className="px-4 py-3 text-[#64748b]">{sanitizeReason(trade.reason)}</td>
                  <td className="px-4 py-3 text-[#64748b]">{trade.status || "N/A"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function OrderTable({ title, rows }) {
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
            <PriceStack value={order.price} source={{ priceLabel: order.priceLabel || (order.time ? `journaled at ${order.time}` : null) }} />,
            sanitizeReason(order.reason),
            order.status || "N/A",
          ])}
        />
      )}
    </section>
  );
}

function HoldingsTable({ rows }) {
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
              hasLtp ? `${pnlSign(rowPnl)}${money(rowPnl)} (${pct(rowPct)})` : "awaiting first real quote",
            ];
          })}
        />
      )}
    </section>
  );
}

function PositionsTable({ rows }) {
  return (
    <section className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
        <div className="text-[13px] font-semibold text-[#020617]">Open Paper Positions - {rows.length}</div>
        <span className="rounded border border-blue-100 bg-blue-50 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-blue-600">Backend holdings</span>
      </div>
      {rows.length === 0 ? (
        <StatusCard title="No open paper positions" message="Backend returned an empty holdings list." icon={LineChart} />
      ) : (
        <SimpleTable
          headings={["Symbol", "Qty", "Avg", "LTP", "Unrealised P&L"]}
          rows={rows.map((position) => {
            const hasLtp = !isMissing(position.ltp);
            const rowPnl = hasLtp ? (safeNumber(position.ltp) - safeNumber(position.avg)) * safeNumber(position.qty) : null;
            return [
              position.symbol || "N/A",
              qty(position.qty),
              money(position.avg, 2),
              <PriceStack value={position.ltp} source={position} />,
              hasLtp ? `${pnlSign(rowPnl)}${money(rowPnl)}` : "awaiting first real quote",
            ];
          })}
        />
      )}
    </section>
  );
}

function useResearch(selectedStock) {
  const [row, setRow] = useState(null);
  const [status, setStatus] = useState("loading");
  const [health, setHealth] = useState({ status: "loading", lastSuccess: null, lastError: null });
  const researchSymbol = normalizeResearchSymbol(selectedStock);
  const loadResearch = useCallback(async () => {
    setStatus("loading");
    setHealth((previous) => ({ ...previous, status: "loading" }));
    setRow(null);
    try {
      const res = await fetch(`${SPENCER_API_BASE}/api/research?symbols=${encodeURIComponent(researchSymbol)}`, { cache: "no-store" });
      if (!res.ok) {
        setStatus("error");
        setHealth({ status: "error", lastSuccess: null, lastError: "Research API returned an error" });
        return;
      }
      const json = await res.json();
      if (!json?.ok) {
        setStatus("error");
        setHealth({ status: "error", lastSuccess: null, lastError: "Research API returned ok=false" });
        return;
      }
      const next = asArray(json.research)[0] || null;
      setRow(next);
      setStatus(next ? "ready" : "empty");
      setHealth({
        status: next ? "ready" : "empty",
        lastSuccess: next ? timeLabel() : null,
        lastError: next ? null : "Research API returned no rows",
      });
    } catch (error) {
      setStatus("disconnected");
      setHealth({
        status: "disconnected",
        lastSuccess: null,
        lastError: error?.message || "Research API request failed",
      });
    }
  }, [researchSymbol]);
  useEffect(() => {
    loadResearch();
  }, [loadResearch]);
  return { row, status, health, loadResearch };
}

function useResearchLedger() {
  const [ledger, setLedger] = useState(null);
  const [status, setStatus] = useState("loading");
  const [health, setHealth] = useState({ status: "loading", lastSuccess: null, lastError: null });
  const loadLedger = useCallback(async () => {
    setStatus((previous) => (previous === "ready" ? "refreshing" : "loading"));
    setHealth((previous) => ({ ...previous, status: "loading" }));
    try {
      const res = await fetch(`${SPENCER_API_BASE}/api/research/ledger`, { cache: "no-store" });
      if (!res.ok) throw new Error("Research ledger API returned an error");
      const json = await res.json();
      if (!json?.ok) throw new Error("Research ledger API returned ok=false");
      setLedger(json);
      const hasCandidates = asArray(json.candidates).length > 0;
      setStatus(hasCandidates ? "ready" : "empty");
      setHealth({
        status: hasCandidates ? "ready" : "empty",
        lastSuccess: timeLabel(),
        lastError: hasCandidates ? null : "Research ledger returned no candidates",
      });
    } catch (error) {
      setStatus("error");
      setHealth({
        status: "error",
        lastSuccess: null,
        lastError: error?.message || "Research ledger API request failed",
      });
    }
  }, []);
  useEffect(() => {
    loadLedger();
  }, [loadLedger]);
  return { ledger, status, health, loadLedger };
}

function researchStatusText(status) {
  if (status === "loading") return "Checking Spencer research engine...";
  if (status === "empty") return "No research metrics available from backend.";
  if (status === "disconnected") return "Backend disconnected. Brain Check unavailable.";
  if (status === "error") return "Research check failed. Retry after backend is running.";
  return "Real backend research metrics";
}

function researchMetrics(row) {
  return [
    ["Trend", row?.trend || "N/A"],
    ["SMA 20", isMissing(row?.sma20) ? "N/A" : money(row.sma20, 2)],
    ["SMA 50", isMissing(row?.sma50) ? "N/A" : money(row.sma50, 2)],
    ["Return 20d", isMissing(row?.return20d) ? "N/A" : `${(Number(row.return20d) * 100).toFixed(1)}%`],
    ["Avg Volume 20d", isMissing(row?.avgVolume20d) ? "N/A" : Number(row.avgVolume20d).toLocaleString("en-IN", { maximumFractionDigits: 0 })],
  ];
}

const apiCount = (value) =>
  isMissing(value) ? "N/A" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const apiMoney = (value) => (isMissing(value) ? "N/A" : money(value, 2));
const apiPct = (value) => (isMissing(value) ? "N/A" : pct(value, 3));
const apiText = (value) => (value === null || value === undefined || value === "" ? "N/A" : String(value));
const verdictClass = (status) => {
  const text = String(status || "").toUpperCase();
  if (text === "KILLED") return "border-red-200 bg-red-50 text-red-700";
  if (text === "PASSED") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
};
const stageRange = (stage) => {
  const dataset = stage?.dataset || {};
  const start = dataset.start ? dateOnly(dataset.start) : null;
  const end = dataset.end ? dateOnly(dataset.end) : null;
  if (start && end) return `${start} → ${end}`;
  return start || end || "N/A";
};

function ResearchLedgerPanel() {
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
    <section className="research-ledger-panel rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm" aria-labelledby="research-ledger-title" data-research-ledger-panel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">Research Ledger</div>
          <h2 id="research-ledger-title" className="mt-1 text-[18px] font-semibold text-[#020617]">Tested candidates and verdicts</h2>
          {scoreboard.updatedAt && (
            <div className="mt-1 text-[11px] text-[#64748b]">Scoreboard updated {fmtIST(scoreboard.updatedAt)}</div>
          )}
        </div>
        <button onClick={loadLedger} disabled={status === "loading"} className="flex items-center justify-center gap-2 rounded-lg bg-[#2563eb] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[#1d4ed8] disabled:cursor-wait disabled:opacity-70">
          {status === "loading" ? "Checking" : "Refresh"}
        </button>
      </div>

      {status === "loading" && (
        <div className="research-ledger-loading mt-4 rounded-lg border border-blue-100 bg-[#eff6ff] px-4 py-3 text-[12px] text-[#2563eb]">Checking research ledger.</div>
      )}

      {status === "error" && (
        <div className="research-ledger-error mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-[12px] text-red-700">
          Research ledger unavailable. {health.lastError ? apiText(health.lastError) : ""}
        </div>
      )}

      {status !== "loading" && status !== "error" && candidates.length === 0 && (
        <div className="research-ledger-empty mt-4 rounded-lg border border-gray-200 bg-[#f8fafc] px-4 py-6 text-center text-[13px] font-semibold text-[#475569]">No candidates tested yet.</div>
      )}

      {status !== "loading" && status !== "error" && (
        <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="research-ledger-candidates space-y-3">
            {candidates.map((candidate) => (
              <article key={`${candidate.candidateId}-${candidate.version}`} className="research-ledger-candidate rounded-lg border border-gray-200 bg-[#f8fafc] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-[15px] font-semibold text-[#020617]">{apiText(candidate.candidateId)}</h3>
                      <span className="rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#64748b]">v{apiText(candidate.version)}</span>
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${verdictClass(candidate.status)}`}>{apiText(candidate.status)}</span>
                    </div>
                    {candidate.kill?.date && (
                      <div className="mt-1 text-[11px] font-medium text-red-700">Killed {fmtIST(candidate.kill.date)}</div>
                    )}
                  </div>
                  {candidate.kill?.reason && (
                    <div className="max-w-xs rounded-md border border-red-100 bg-white px-3 py-2 text-[11px] font-medium text-red-700">{candidate.kill.reason}</div>
                  )}
                </div>

                <details className="research-ledger-hypothesis mt-3 rounded-md border border-gray-200 bg-white px-3 py-2 text-[12px] text-[#475569]">
                  <summary className="cursor-pointer truncate font-medium text-[#020617]">{apiText(candidate.hypothesis)}</summary>
                  <p className="mt-2 leading-5">{apiText(candidate.hypothesis)}</p>
                </details>

                {asArray(candidate.stages).length === 0 ? (
                  <div className="mt-3 rounded-md border border-gray-200 bg-white px-3 py-2 text-[12px] text-[#64748b]">No stage rows recorded.</div>
                ) : (
                  <div className="research-ledger-stage-table mt-3 overflow-x-auto rounded-md border border-gray-200 bg-white">
                    <table className="min-w-full text-left text-[12px]">
                      <thead className="bg-gray-50 text-[10px] uppercase tracking-wider text-[#64748b]">
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
                      <tbody className="divide-y divide-gray-100">
                        {asArray(candidate.stages).map((stage, index) => (
                          <tr key={`${stage.stage}-${index}`} className="text-[#334155]">
                            <td className="whitespace-nowrap px-3 py-2 font-semibold">{apiText(stage.stage)}</td>
                            <td className="whitespace-nowrap px-3 py-2">{apiText(stage.status)}</td>
                            <td className="whitespace-nowrap px-3 py-2 text-right">{apiCount(stage.trades)}</td>
                            <td className="whitespace-nowrap px-3 py-2 text-right">{apiMoney(stage.gross_pnl)}</td>
                            <td className="whitespace-nowrap px-3 py-2 text-right">{apiMoney(stage.total_costs)}</td>
                            <td className="whitespace-nowrap px-3 py-2 text-right font-semibold">{apiMoney(stage.net_pnl)}</td>
                            <td className="whitespace-nowrap px-3 py-2 text-right">{apiPct(stage.net_edge_pct)}</td>
                            <td className="whitespace-nowrap px-3 py-2 text-right">{apiPct(stage.cost_bar_required_pct)}</td>
                            <td className="min-w-[260px] px-3 py-2 text-[11px] text-[#64748b]">{stageRange(stage)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </article>
            ))}
          </div>

          <aside className="space-y-3">
            <section className="research-ledger-scoreboard rounded-lg border border-gray-200 bg-[#f8fafc] p-4">
              <div className="text-[12px] font-semibold text-[#020617]">Scoreboard</div>
              {scoreItems.length === 0 ? (
                <div className="mt-3 text-[12px] text-[#64748b]">Scoreboard unavailable from API.</div>
              ) : (
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {scoreItems.map(([label, value]) => (
                    <div key={label} className="rounded-md border border-gray-200 bg-white px-3 py-2">
                      <div className="text-[10px] uppercase tracking-wider text-[#94a3b8]">{label}</div>
                      <div className="mt-1 text-[16px] font-semibold text-[#020617]">{apiCount(value)}</div>
                    </div>
                  ))}
                </div>
              )}
              {scoreboard.basis && <div className="mt-3 text-[11px] leading-5 text-[#64748b]">{scoreboard.basis}</div>}
            </section>

            <section className="research-ledger-coverage rounded-lg border border-gray-200 bg-[#f8fafc] p-4">
              <div className="text-[12px] font-semibold text-[#020617]">Data Coverage</div>
              <div className="mt-3 space-y-2 text-[12px] text-[#334155]">
                {intraday.length === 0 ? (
                  <div className="rounded-md border border-gray-200 bg-white px-3 py-2 text-[#64748b]">No intraday coverage rows recorded.</div>
                ) : (
                  intraday.map((row) => (
                    <div key={row.interval} className="rounded-md border border-gray-200 bg-white px-3 py-2">
                      <div className="font-semibold">{apiText(row.interval)}: {apiCount(row.sessions)} sessions, growing daily</div>
                      <div className="mt-1 text-[11px] text-[#64748b]">{apiCount(row.candles)} candles</div>
                      <div className="mt-1 text-[11px] text-[#64748b]">{apiText(row.firstTs)} to {apiText(row.lastTs)}</div>
                    </div>
                  ))
                )}
                {coverage.daily?.lastTradeDate && (
                  <div className="rounded-md border border-gray-200 bg-white px-3 py-2">
                    <div className="font-semibold">Daily close last stored</div>
                    <div className="mt-1 text-[11px] text-[#64748b]">{coverage.daily.lastTradeDate}</div>
                  </div>
                )}
              </div>
            </section>
          </aside>
        </div>
      )}
    </section>
  );
}

function ResearchPanel({ selectedStock, row, status, loadResearch }) {
  const researchSymbol = normalizeResearchSymbol(selectedStock);
  return (
    <section className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <div className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">Brain Check · {prettySymbol(selectedStock)}</div>
            <span className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${
              status === "ready" ? "border-blue-100 bg-blue-50 text-blue-600" : status === "loading" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-red-100 bg-red-50 text-red-600"
            }`}>
              {status === "ready" ? "Real backend data" : status === "loading" ? "Checking" : status === "empty" ? "Data unavailable" : "Unavailable"}
            </span>
          </div>
          <div className="mt-3 rounded-lg border border-gray-200 bg-[#f8fafc] px-4 py-3 text-[13px] font-medium text-[#374151]">{researchStatusText(status)}</div>
        </div>
        <button onClick={loadResearch} disabled={status === "loading"} className="flex items-center justify-center gap-2 rounded-lg bg-[#2563eb] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[#1d4ed8] disabled:cursor-wait disabled:opacity-70">
          {status === "loading" ? "Checking" : "Retry"}
        </button>
      </div>
      {status === "ready" && (
        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {researchMetrics(row).map(([label, value]) => (
            <div key={label} className="rounded-lg border border-gray-200 bg-[#f8fafc] p-3">
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-[#94a3b8]">{label}</div>
              <div className="text-[13px] font-semibold text-[#020617]">{value}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function TradeDetailModal({ trade, onClose }) {
  if (!trade) return null;
  const win = safeNumber(trade.pnl) >= 0;
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-white/40 p-4 backdrop-blur-xl" onClick={(event) => event.target === event.currentTarget && onClose()}>
      <section className="w-full max-w-[460px] rounded-2xl border border-gray-200 bg-white p-6 shadow-xl">
        <div className="mb-5 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[20px] font-bold text-[#020617]">{trade.symbol || "N/A"}</span>
              <span className={`rounded-md border px-2 py-0.5 text-[11px] font-semibold ${trade.side === "BUY" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"}`}>
                {trade.side || "N/A"}
              </span>
            </div>
            <div className="mt-1 text-[12px] text-[#64748b]">{trade.time || "N/A"}</div>
          </div>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full text-[#94a3b8] hover:bg-gray-100">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className={`mb-4 rounded-xl border p-4 ${win ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
          <div className="mb-1 text-[11px] uppercase tracking-wider text-[#64748b]">Realised P&L</div>
          <div className={`text-[28px] font-bold ${win ? "text-emerald-700" : "text-red-700"}`}>{win ? "+" : ""}{money(trade.pnl)}</div>
        </div>
        <div className="mb-4 grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-gray-200 p-3">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-[#94a3b8]">Qty</div>
            <div className="text-[16px] font-semibold text-[#020617]">{qty(trade.qty)}</div>
          </div>
          <div className="rounded-lg border border-gray-200 p-3">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-[#94a3b8]">Price</div>
            <div className="text-[16px] font-semibold text-[#020617]"><PriceStack value={trade.price} source={{ priceLabel: trade.priceLabel || (trade.time ? `journaled at ${trade.time}` : null) }} align="left" /></div>
          </div>
        </div>
        <div className="rounded-lg border border-gray-100 bg-[#f8fafc] px-4 py-3">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[#64748b]">Backend reason</div>
          <p className="text-[12px] leading-5 text-gray-700">{sanitizeReason(trade.reason)}</p>
        </div>
      </section>
    </div>
  );
}

function SpencerChat({ selectedStock }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: "spencer", text: `Ask Spencer chat is disabled because no approved backend chat route is configured. Use Brain Check for real research metrics on NSE:${selectedStock}.` },
  ]);

  const send = async (event) => {
    event.preventDefault();
    setMessages((previous) => previous);
  };

  return (
    <div className="fixed bottom-5 right-5 z-40">
      {open && (
        <section className="mb-3 w-[min(360px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <div>
              <div className="text-[13px] font-semibold text-[#020617]">Ask Spencer</div>
              <div className="text-[10px] text-[#94a3b8]">No approved chat endpoint</div>
            </div>
            <button onClick={() => setOpen(false)} className="text-[#94a3b8] hover:text-gray-700">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex max-h-[320px] flex-col gap-2 overflow-y-auto p-3">
            {messages.map((message, index) => (
              <div key={index} className={`rounded-xl px-3 py-2.5 text-[13px] leading-5 ${message.role === "you" ? "ml-8 bg-[#2563eb] text-white" : "mr-8 border border-gray-100 bg-[#f8fafc] text-[#111827]"}`}>
                {message.text}
              </div>
            ))}
          </div>
          <form onSubmit={send} className="flex gap-2 border-t border-gray-100 p-3">
            <input
              value=""
              onChange={() => {}}
              placeholder="No approved chat endpoint configured"
              disabled
              className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-[13px] text-[#020617] outline-none placeholder:text-[#94a3b8] disabled:opacity-60"
            />
            <button type="submit" disabled title="No approved chat endpoint configured." className="grid h-9 w-9 shrink-0 cursor-not-allowed place-items-center rounded-lg bg-[#2563eb] text-white opacity-50">
              <Send className="h-3.5 w-3.5" />
            </button>
          </form>
        </section>
      )}
      <button onClick={() => setOpen((value) => !value)} className="flex items-center gap-2.5 rounded-full bg-[#2563eb] px-5 py-3 text-[13px] font-semibold text-white shadow-lg">
        <MessageCircle className="h-4 w-4" />
        Ask Spencer
      </button>
    </div>
  );
}

export default function App() {
  const [profile, setProfile] = useLocalProfile();
  const { botState, backendStatus, botHealth } = useBotState(profile);
  const [activePage, setActivePage] = useState("Dashboard");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedStock, setSelectedStock] = useState(ONE_STOCK_SYMBOL);
  const [showAddWidget, setShowAddWidget] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState(null);
  const niftyStocks = useMemo(() => NSE_STOCKS.filter((stock) => NIFTY50_SYMS.includes(stock.symbol)), []);
  const allowedStocks = useMemo(() => NSE_STOCKS.filter((stock) => stock.symbol === ONE_STOCK_SYMBOL), []);
  const tickerStocks = useMemo(() => (allowedStocks.length ? allowedStocks : niftyStocks).slice(0, 8), [allowedStocks, niftyStocks]);
  const quoteSymbols = useMemo(() => [ONE_STOCK_SYMBOL], []);
  const { quotes, quoteStatus, quoteHealth } = useQuotes(quoteSymbols);

  const page = (() => {
    if (activePage === "Orders") return <OrdersPage botState={botState} backendStatus={backendStatus} onTradeClick={setSelectedTrade} />;
    if (activePage === "Holdings") return <HoldingsPage botState={botState} backendStatus={backendStatus} />;
    if (activePage === "Positions") return <PositionsPage botState={botState} backendStatus={backendStatus} />;
    if (activePage === "Funds") return <FundsPage botState={botState} backendStatus={backendStatus} profile={profile} />;
    if (activePage === "Bids") return <BidsPage botState={botState} backendStatus={backendStatus} />;
    if (activePage === "Brain") return <BrainPage selectedStock={selectedStock} />;
    if (activePage === "Research") return <ResearchPage />;
    if (activePage === "Governance") return <GovernancePage botState={botState} backendStatus={backendStatus} />;
    if (activePage === "Trade Tracker") return <TradeTrackerPage botState={botState} backendStatus={backendStatus} onTradeClick={setSelectedTrade} />;
    if (activePage === "Profile") return <ProfilePage profile={profile} setProfile={setProfile} />;
    return (
      <DashboardPage
        botState={botState}
        backendStatus={backendStatus}
        selectedStock={selectedStock}
        openAddWidget={() => setShowAddWidget(true)}
        botHealth={botHealth}
        quoteHealth={quoteHealth}
        watchlistCount={allowedStocks.length}
      />
    );
  })();

  return (
    <div className="dashboard-light h-screen w-full overflow-hidden bg-transparent text-[#020617]">
      <TickerBar stocks={tickerStocks} quotes={quotes} />
      <Header backendStatus={backendStatus} onMenuOpen={() => setDrawerOpen(true)} />
      <Drawer open={drawerOpen} activePage={activePage} setActivePage={setActivePage} onClose={() => setDrawerOpen(false)} />
      <div className="flex h-[calc(100vh-100px)] overflow-hidden">
        <Sidebar selectedStock={selectedStock} setSelectedStock={setSelectedStock} allowedStocks={allowedStocks} quoteMap={quotes} quoteStatus={quoteStatus} />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[18px] font-semibold tracking-tight text-[#020617]">{activePage}</div>
              {activePage === "Dashboard" && <div className="text-[12px] text-[#64748b]">Backend-owned paper dashboard</div>}
              {activePage === "Brain" && <div className="text-[12px] text-[#64748b]">Analysing <span className="font-semibold text-gray-700">{selectedStock}</span></div>}
              {activePage === "Research" && <div className="text-[12px] text-[#64748b]">Journaled candidate verdicts and coverage</div>}
              {activePage === "Governance" && <div className="text-[12px] text-[#64748b]">Backend-owned tool boundaries and action permissions</div>}
            </div>
            {activePage === "Dashboard" && (
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-[#eff6ff] px-4 py-2 text-[12px] font-semibold text-[#2563eb]">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Paper-only mode
                </span>
                <button onClick={() => setShowAddWidget(true)} title="Add widget" className="grid h-9 w-9 place-items-center rounded-full border border-[#e5e7eb] bg-white">
                  <Plus className="h-4 w-4" />
                </button>
              </div>
            )}
          </div>
          {page}
        </main>
      </div>
      <SpencerChat selectedStock={selectedStock} />
      {showAddWidget && <AddWidgetPanel onClose={() => setShowAddWidget(false)} />}
      {selectedTrade && <TradeDetailModal trade={selectedTrade} onClose={() => setSelectedTrade(null)} />}
    </div>
  );
}
