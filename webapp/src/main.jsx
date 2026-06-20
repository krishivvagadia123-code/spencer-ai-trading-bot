import React from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

// ─── Canonical origin redirect ────────────────────────────────────────────────
// localStorage is partitioned per-origin. `localhost:5174` and `127.0.0.1:5174`
// are SEPARATE buckets, so an account created on one can't be seen from the
// other. Force every visit to land on `localhost` so accounts stick.
(function enforceCanonicalOrigin() {
  try {
    const { hostname, protocol, port, pathname, search, hash } = window.location;
    // Treat 127.0.0.1 and 0.0.0.0 as aliases of localhost
    if (hostname === "127.0.0.1" || hostname === "0.0.0.0") {
      const portPart = port ? `:${port}` : "";
      const newUrl = `${protocol}//localhost${portPart}${pathname}${search}${hash}`;
      window.location.replace(newUrl);
    }
  } catch {
    /* if anything fails, just render the app */
  }
})();

async function loadRuntimeConfig() {
  window.__SPENCER_API_BASE__ = "";
  try {
    const response = await fetch("/spencer-config.json", { cache: "no-store" });
    if (!response.ok) return;
    const config = await response.json();
    window.__SPENCER_API_BASE__ = String(config?.apiBase || "").trim();
  } catch {
    window.__SPENCER_API_BASE__ = "";
  }
}

async function boot() {
  await loadRuntimeConfig();
  const { default: App } = await import("./App.jsx");
  createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

boot();
