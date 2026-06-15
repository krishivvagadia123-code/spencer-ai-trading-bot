# Spencer editable local app

Recovered and editable Vite + React + Tailwind v4 version of the Spencer
dashboard.

- App: http://localhost:5180/
- Backend: http://127.0.0.1:8787
- The original app on port 5175 is untouched.
- The app is paper-only and does not expose live order execution.
- The compact header contains the market and backend state; there is no separate
  announcement ticker above it.

## Run

Double-click `Run_Spencer_2026.bat` on the desktop. It now starts:

- The AI TRADE backend on port `8787`.
- This editable frontend on port `5180`.
- The browser at `http://localhost:5180/`.

The launcher detects services that are already running, so it can be used again
without starting duplicate backend or frontend processes.

To run only the frontend, double-click `START_SPENCER_APP.bat` or use:

```powershell
npm install
npm run dev
```

## Live data bindings

- Dashboard: portfolio value, budget, invested capital, cash, quote, candidate
  count, brain availability, and lifetime metrics.
- Research Core: a click-stable liquid-glass stage selector over a generated
  hand-sketched musical-instrument collage.
- Brain: RELIANCE trend, moving averages, 20-day return, and research timestamp.
- Research: candidate ledger, stages, verdicts, trade counts, net results, and
  kill reasons.
- Orders, Holdings, Positions, Bids, and Trade Tracker: backend records or
  explicit empty states.
- Funds: paper budget, available cash, realised P&L, and trade metrics.
- Governance: backend `capabilities.actions` only; no hardcoded policy rows.
- Profile: browser-local persistence.

## Verified checkpoint

Verified on June 13, 2026 against the local backend:

- RELIANCE quote displayed as INR 1,293.00 with market-closed treatment.
- Portfolio displayed as INR 5,000 with INR 0 invested and INR 5,000 cash.
- Research displayed 2 tested and 2 killed candidates.
- Brain displayed a -3.25% 20-day return from the backend ratio.
- Zero realised P&L displayed as INR 0 rather than unavailable.
- Candidate details drawer opened and closed correctly.
- Profile values survived a reload; the test value was restored afterward.
- Desktop 1280x800 and mobile 390x844 had no horizontal overflow.
- Browser console had no warnings or errors.
- `npm run build` completed successfully.

## Project layout

- `src/`: editable React source
- `public/`: static assets
- `START_SPENCER_APP.bat`: local launcher
- `../mirror/`: original static snapshot retained for reference
