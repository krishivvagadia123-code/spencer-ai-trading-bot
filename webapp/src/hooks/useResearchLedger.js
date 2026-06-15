import { useState, useEffect } from "react";
import { SPENCER_API_BASE } from "../utils/constants";

export function useResearchLedger() {
  const [ledger, setLedger] = useState({ candidates: [], scoreboard: {}, dataCoverage: {} });
  const [status, setStatus] = useState("loading");

  const loadLedger = async () => {
    setStatus("loading");
    try {
      const res = await fetch(`${SPENCER_API_BASE}/api/research/ledger`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setLedger(data);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  };

  useEffect(() => { loadLedger(); }, []);
  return { ledger, status, loadLedger };
}