import { useState, useEffect } from "react";
import { SPENCER_API_BASE } from "../utils/constants";

// Reads the honest Trades & Resets view from the backend: every paper trade
// taken (epoch journal + forward paper engine) plus how many times the account
// was reset to the ₹5,000 basis. Real journal only — no fabricated rows.
export function useTradesResets() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("loading");

  const load = async () => {
    setStatus("loading");
    try {
      const res = await fetch(`${SPENCER_API_BASE}/api/trades-resets`);
      if (!res.ok) throw new Error();
      setData(await res.json());
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  };

  useEffect(() => { load(); }, []);
  return { data, status, reload: load };
}
