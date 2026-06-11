// ─── Strategy registry ───────────────────────────────────────────────────────
// Each strategy module exports: { meta, evaluate, shouldExit }
// Phase 1 ships with one. Phase 2 will add the other 19.

import * as vwapBreakout from "./vwapBreakout.js";

export const ALL_STRATEGIES = [
  vwapBreakout,
];

export function getStrategy(id) {
  return ALL_STRATEGIES.find(s => s.meta.id === id) || ALL_STRATEGIES[0];
}

export function strategyList() {
  return ALL_STRATEGIES.map(s => s.meta);
}
