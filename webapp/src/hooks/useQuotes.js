import { useState, useEffect } from "react";
import { SPENCER_API_BASE } from "../utils/constants";
import { asArray, timeLabel } from "../utils/helpers";

export function useQuotes(symbols) {
  const [quotes, setQuotes] = useState({});
  const [quoteStatus, setQuoteStatus] = useState("checking");
  const [quoteHealth, setQuoteHealth] = useState({ status: "checking", lastSuccess: null, lastError: null });

  // Stable key: callers pass a fresh [SYMBOL] array each render, so depending on
  // the array identity re-ran this effect every render (refetch loop + flickering
  // empty quote). Depend on the joined symbol string instead — fetch once per change.
  const symbolKey = asArray(symbols).filter(Boolean).join(",");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const clean = asArray(symbols).filter(Boolean);
      if (!clean.length) {
        setQuoteStatus("unavailable");
        return;
      }
      setQuoteStatus(p => p === "ready" ? "refreshing" : "checking");
      try {
        const res = await fetch(`${SPENCER_API_BASE}/api/quotes?symbols=${encodeURIComponent(clean.join(","))}`);
        if (!res.ok) throw new Error("unavailable");
        const data = await res.json();
        const next = {};
        for (const item of asArray(data?.quotes)) {
          if (item?.symbol) next[item.symbol.replace(/\.NS$/i, "")] = item;
        }
        if (!cancelled) {
          setQuotes(next);
          setQuoteStatus("ready");
        }
      } catch (error) {
        if (!cancelled) setQuoteStatus("unavailable");
      }
    };
    load();
    const timer = setInterval(load, 60000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [symbolKey]);

  return { quotes, quoteStatus, quoteHealth };
}