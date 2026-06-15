import { useState, useEffect, useCallback } from "react";
import { ONE_STOCK_SYMBOL } from "../utils/constants";

const DEFAULT = { name: "Trader", botName: "Spencer", tradeType: "Paper Journal", risk: "Capital Defense", budget: 5000, selectedStocks: [ONE_STOCK_SYMBOL] };

export function useLocalProfile() {
  const [profile, setProfile] = useState(() => {
    try {
      return { ...DEFAULT, ...JSON.parse(localStorage.getItem("spencer-profile") || "{}"), budget: 5000, selectedStocks: [ONE_STOCK_SYMBOL] };
    } catch {
      return DEFAULT;
    }
  });

  useEffect(() => {
    localStorage.setItem("spencer-profile", JSON.stringify(profile));
  }, [profile]);

  return [profile, setProfile];
}