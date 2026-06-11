import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
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

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
