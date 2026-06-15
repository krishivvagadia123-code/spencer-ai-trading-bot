export const isMissing = (value) =>
  value === null || value === undefined || value === "" || !Number.isFinite(Number(value));
export const asArray = (value) => (Array.isArray(value) ? value : []);
export const safeNumber = (value, fallback = 0) => {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
};
export const money = (value, digits = 0) =>
  isMissing(value)
    ? "N/A"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: digits,
      }).format(Number(value));
export const qty = (value) =>
  isMissing(value) ? "N/A" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });
export const pct = (value, digits = 2) => (isMissing(value) ? "N/A" : `${Number(value).toFixed(digits)}%`);
export const pnlSign = (value) => (safeNumber(value) > 0 ? "+" : "");
export const pnlTone = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "text-[var(--color-muted-dark-text)]";
  return n > 0 ? "text-[var(--color-primary-dark-text)]" : "text-[var(--color-failure-accent)]";
};
export const fmtIST = (ts) => {
  const d = new Date(ts);
  if (!ts || Number.isNaN(d.getTime())) return String(ts || "N/A");
  return `${d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })} IST`;
};
export const dateOnly = (ts) => (ts ? String(ts).slice(0, 10) : "N/A");
export const normalizeResearchSymbol = (symbol) => {
  const raw = String(symbol || "").trim().toUpperCase();
  if (!raw) return "RELIANCE.NS";
  return raw.includes(".") ? raw : `${raw}.NS`;
};
export const displayName = (value) =>
  String(value || "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
export const sanitizeReason = (value) =>
  String(value || "N/A")
    .replace(/\s*score=[\d.]+/gi, "")
    .replace(/strategy=[^\s]+/gi, "strategy=backend-paper")
    .trim() || "N/A";
export const priceText = (value) => (isMissing(value) ? "awaiting first real quote" : money(value, 2));
export const priceMeta = (source) => source?.priceLabel || source?.marketStateLabel || "awaiting first real quote";
export const timeLabel = () =>
  new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });