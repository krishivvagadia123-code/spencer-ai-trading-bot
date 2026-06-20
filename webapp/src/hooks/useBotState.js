import { useState, useEffect } from "react";
import { SPENCER_API_BASE, ONE_STOCK_SYMBOL } from "../utils/constants";
import { timeLabel } from "../utils/helpers";

export function useBotState(profile) {
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
          setBotHealth({ status: "disconnected", lastSuccess: null, lastError: error?.message });
        }
      }
    };
    const pushConfig = async () => {
      try {
        await fetch(`${SPENCER_API_BASE}/api/bot/config`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Spencer-Token": import.meta.env.VITE_SPENCER_API_TOKEN || "",
          },
          body: JSON.stringify({ budget: 5000, symbol: ONE_STOCK_SYMBOL }),
        });
      } catch {}
    };

    poll();
    pushConfig();
    const timer = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [profile?.budget]);

  return { botState, backendStatus, botHealth };
}