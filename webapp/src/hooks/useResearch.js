import { useState, useEffect } from "react";
import { SPENCER_API_BASE } from "../utils/constants";

export function useResearch(selectedStock) {
  const [row, setRow] = useState(null);
  const [status, setStatus] = useState("loading");

  const loadResearch = async () => {
    if (!selectedStock) return;
    setStatus("loading");
    try {
      const res = await fetch(`${SPENCER_API_BASE}/api/research`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      // Backend returns { ok, research: [ { symbol, trend, sma20, ... } ] }.
      // Unwrap the first research row instead of storing the whole envelope.
      const research = Array.isArray(data?.research) ? data.research[0] : (data?.research ?? null);
      setRow(research ?? null);
      setStatus(research ? "ready" : "empty");
    } catch {
      setStatus("error");
    }
  };

  useEffect(() => { loadResearch(); }, [selectedStock]);
  return { row, status, loadResearch };
}