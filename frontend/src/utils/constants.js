export const VIDEO_URL = "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260406_094145_4a271a6c-3869-4f1c-8aa7-aeb0cb227994.mp4";
export const IST_OFFSET = 5.5 * 3600 * 1000;

export const NIFTY50_SYMS = [
  "RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","SBIN","BHARTIARTL","ITC","LT","AXISBANK",
  "KOTAKBANK","HINDUNILVR","BAJFINANCE","ASIANPAINT","MARUTI","SUNPHARMA","TITAN","WIPRO",
  "TATAMOTORS","ADANIENT","HCLTECH","TECHM","ULTRACEMCO","NESTLEIND","POWERGRID","ONGC",
  "NTPC","COALINDIA","JSWSTEEL","TATASTEEL","CIPLA","DRREDDY","DIVISLAB","EICHERMOT",
  "HEROMOTOCO","BAJAJFINSV","M&M","GRASIM","HDFCLIFE","SBILIFE","APOLLOHOSP","BRITANNIA",
  "ADANIPORTS","BPCL","HINDALCO","INDUSINDBK","TATACONSUM","SHRIRAMFIN","BAJAJ-AUTO","TRENT",
];

export const TRADE_TYPES = [
  { key: "Paper Journal", desc: "Displays recorded paper orders and holdings from the local backend journal only." },
  { key: "Observe Only", desc: "Displays backend market and paper-journal state without placing orders." },
  { key: "Manual Review", desc: "Keeps Spencer in a review-only workflow with no live execution authority." },
];

export const RISK_MODES = [
  { key: "Capital Defense", desc: "Show backend capital state with conservative paper-only controls." },
  { key: "Balanced", desc: "Local display preference only; it does not authorize trading." },
  { key: "Manual Approval Only", desc: "Local display preference only; backend remains paper-only." },
  { key: "Conservative Review", desc: "Read-only review mode for paper journal and research metrics." },
];

export const WIDGET_DEFAULTS = ["capital","strategy","brain","market","activity","trust"];
export const SPENCER_API_BASE = import.meta.env.VITE_SPENCER_API_BASE || "http://127.0.0.1:8787";
