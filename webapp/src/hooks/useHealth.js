import { useCallback, useEffect, useState } from "react";
import { SPENCER_API_BASE } from "../utils/constants";

export function useHealth() {
  const [health, setHealth] = useState(null);
  const [status, setStatus] = useState("loading");

  const loadHealth = useCallback(async () => {
    setStatus((current) => (current === "ready" ? "refreshing" : "loading"));
    try {
      const response = await fetch(`${SPENCER_API_BASE}/api/health`, { cache: "no-store" });
      if (!response.ok) throw new Error("health unavailable");
      const data = await response.json();
      if (!data?.ok) throw new Error("health returned ok=false");
      setHealth(data);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    loadHealth();
    const timer = window.setInterval(loadHealth, 30000);
    return () => window.clearInterval(timer);
  }, [loadHealth]);

  return { health, status, loadHealth };
}
