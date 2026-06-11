"""
Local quote, chart, and research server for Spencer AI.

This is read-only. It never places orders. It uses Yahoo Finance's public
chart/quote endpoints directly so the UI can show latest available NSE prices
after market close without needing yfinance or pandas installed locally.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

from bot.governance import build_action_capabilities, build_governance_snapshot

PORT = 8787
YAHOO_QUOTE = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols}"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_name}&interval={interval}&includePrePost=false&events=history"
BASE_DIR = Path(__file__).resolve().parent
BOT_INTERVAL_SEC = 300
_BOT_LOCK = threading.Lock()
_BOT_THREAD: threading.Thread | None = None
_BOT_STOP = threading.Event()
_BOT_STATE = {
    "running": False,
    "startedAt": None,
    "lastRunAt": None,
    "nextRunAt": None,
    "lastResult": None,
    "lastError": None,
    "runCount": 0,
}


def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    try:
        length = int(handler.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    except Exception:
        return {}


def _env_value(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value.strip()
    for env_path in (BASE_DIR / "backend" / ".env", BASE_DIR / ".env"):
        try:
            if not env_path.exists():
                continue
            for line in env_path.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                key, val = raw.split("=", 1)
                if key.strip() == name:
                    return val.strip().strip('"').strip("'")
        except Exception:
            continue
    return ""


def _call_gemini(prompt: str, temperature: float = 0.3, max_output_tokens: int = 600) -> dict:
    api_key = _env_value("GEMINI_API_KEY")
    model = _env_value("GEMINI_MODEL") or "gemini-1.5-flash"
    if not api_key:
        return {"ok": False, "status": 500, "error": "GEMINI_API_KEY is missing in backend/.env"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": float(temperature or 0.3),
            "maxOutputTokens": int(max_output_tokens or 600),
            "topP": 0.9,
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model)}:generateContent?key={quote(api_key)}"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "SpencerAI/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "status": 502, "error": f"Gemini request failed: {exc}"}
    text = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0].get("text", "").strip()
    if not text:
        return {"ok": False, "status": 502, "error": "Gemini returned an empty response"}
    return {"ok": True, "text": text, "model": model}


def _get_json(url: str) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 SpencerAI/1.0",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _symbols(raw: str) -> list[str]:
    out: list[str] = []
    for item in (raw or "").split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in out:
            out.append(symbol)
    return out[:160]


def _ticker(symbol: str) -> str:
    if symbol.endswith(".NS") or symbol.startswith("^"):
        return symbol
    return f"{symbol}.NS"


def _clean_symbol(ticker: str) -> str:
    return (ticker or "").replace(".NS", "").upper()


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _chart(symbol: str, interval: str = "5m", range_name: str | None = None) -> dict:
    interval = interval if interval in {"1m", "2m", "5m", "15m", "30m", "60m", "1d"} else "5m"
    range_name = range_name or ("7d" if interval != "1d" else "1y")
    ticker = _ticker(symbol)
    url = YAHOO_CHART.format(
        ticker=quote(ticker),
        range_name=quote(range_name),
        interval=quote(interval),
    )
    data = _get_json(url)
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        return {
            "symbol": symbol,
            "ticker": ticker,
            "interval": interval,
            "candles": [],
            "source": "Yahoo Finance chart",
        }

    timestamps = result.get("timestamp") or []
    quote_rows = (result.get("indicators", {}).get("quote") or [{}])[0]
    opens = quote_rows.get("open") or []
    highs = quote_rows.get("high") or []
    lows = quote_rows.get("low") or []
    closes = quote_rows.get("close") or []
    volumes = quote_rows.get("volume") or []

    candles = []
    start = max(0, len(timestamps) - 260)
    for idx in range(start, len(timestamps)):
        ts = timestamps[idx]
        try:
            o = opens[idx]
            h = highs[idx]
            l = lows[idx]
            c = closes[idx]
            if o is None or h is None or l is None or c is None:
                continue
            candles.append({
                "time": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                "open": round(float(o), 2),
                "high": round(float(h), 2),
                "low": round(float(l), 2),
                "close": round(float(c), 2),
                "volume": round(float(volumes[idx] or 0), 2) if idx < len(volumes) else 0,
            })
        except Exception:
            continue

    return {
        "symbol": symbol,
        "ticker": ticker,
        "interval": interval,
        "candles": candles,
        "source": "Yahoo Finance chart",
    }


def _quote_fallback(symbol: str) -> dict:
    chart = _chart(symbol, "1m", "1d")
    if not chart.get("candles"):
        chart = _chart(symbol, "5m", "5d")
    if not chart.get("candles"):
        chart = _chart(symbol, "1d", "7d")
    candles = chart.get("candles", [])
    price = candles[-1]["close"] if candles else None
    previous = None
    try:
        daily = _chart(symbol, "1d", "7d").get("candles", [])
        previous = daily[-2]["close"] if len(daily) > 1 else None
    except Exception:
        previous = candles[-2]["close"] if len(candles) > 1 else None
    change_pct = ((price - previous) / previous * 100) if price is not None and previous else None
    return {
        "symbol": symbol,
        "price": round(price, 2) if price is not None else None,
        "previousClose": round(previous, 2) if previous is not None else None,
        "changePct": round(change_pct, 3) if change_pct is not None else None,
        "timestamp": candles[-1]["time"] if candles else datetime.now(timezone.utc).isoformat(),
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "status": "intraday_snapshot" if candles else "unavailable",
        "source": "Yahoo Finance intraday chart fallback",
    }


def _quote_rows(symbols: list[str]) -> list[dict]:
    if not symbols:
        return []

    rows_by_symbol: dict[str, dict] = {}
    for batch in _chunks(symbols, 50):
        tickers = ",".join(quote(_ticker(symbol)) for symbol in batch)
        try:
            data = _get_json(YAHOO_QUOTE.format(symbols=tickers))
            results = data.get("quoteResponse", {}).get("result") or []
        except Exception:
            results = []

        for item in results:
            symbol = _clean_symbol(item.get("symbol"))
            if not symbol:
                continue
            price = item.get("regularMarketPrice") or item.get("postMarketPrice") or item.get("previousClose")
            previous = item.get("regularMarketPreviousClose") or item.get("previousClose")
            change_pct = item.get("regularMarketChangePercent")
            timestamp = item.get("regularMarketTime")
            if timestamp:
                timestamp = datetime.fromtimestamp(int(timestamp), timezone.utc).isoformat()
            rows_by_symbol[symbol] = {
                "symbol": symbol,
                "price": round(float(price), 2) if price is not None else None,
                "previousClose": round(float(previous), 2) if previous is not None else None,
                "changePct": round(float(change_pct), 3) if change_pct is not None else None,
                "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
                "fetchedAt": datetime.now(timezone.utc).isoformat(),
                "status": (item.get("marketState") or "last_close").lower(),
                "source": "Yahoo Finance quote",
            }

    rows = []
    for symbol in symbols:
        row = rows_by_symbol.get(symbol)
        if row is None or row.get("price") is None:
            try:
                row = _quote_fallback(symbol)
            except Exception as exc:
                row = {
                    "symbol": symbol,
                    "price": None,
                    "previousClose": None,
                    "changePct": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "fetchedAt": datetime.now(timezone.utc).isoformat(),
                    "status": "unavailable",
                    "source": "Yahoo Finance fallback",
                    "error": str(exc),
                }
        rows.append(row)
    return rows


def _handoff_payload() -> dict:
    bot = _bot_status()
    return {
        "ok": True,
        "project": "Spencer AI",
        "projectPath": str(BASE_DIR),
        "frontendUrl": "http://localhost:5175/",
        "localApiBase": f"http://127.0.0.1:{PORT}",
        "endpoints": {
            "quotes": "/api/quotes?symbols=RELIANCE,TCS,INFY,NHPC,NESTLEIND,POWERGRID",
            "chart": "/api/chart?symbol=RELIANCE&interval=5m",
            "research": "/api/research?symbols=RELIANCE,TCS,INFY",
            "botStart": "POST /api/bot/start",
            "botStatus": "GET /api/bot/status",
            "governance": "GET /api/governance",
            "workflowStatus": "GET /api/workflow/status",
            "handoff": "GET /api/handoff",
        },
        "preserve": [
            "Do not change the onboarding step order, trade type flow, risk mode flow, or bot platform selection flow.",
            "Do not change Spencer's trading methods or paper-trading guardrails during a visual redesign.",
            "Keep Indian equities as the focus. Do not reintroduce crypto trading.",
            "Keep paper trading only unless a real broker integration is explicitly added and authenticated.",
            "Available bot budget is Rs.5,000; losses reduce usable paper budget and profits may be reinvested.",
        ],
        "visualDirection": [
            "Cinematic full-screen home page with fixed video, bottom-only blur mask, liquid glass buttons, Inter typography, and a soft blue cloud tone.",
            "Dashboard should stay clean, readable, scrollable, and theme-safe in dark and light modes.",
            "Watchlist and top ticker must show latest available prices or clear loading/unavailable state, never fake animation-only prices.",
        ],
        "bot": bot,
        "governance": build_governance_snapshot(bot, journal_present=DB_PATH.exists()),
        "workflow": _workflow_status(),
    }


def _run_engine_command(*args: str) -> dict:
    command = [sys.executable, str(BASE_DIR / "paper_engine.py"), *args]
    started = datetime.now(timezone.utc).isoformat()
    try:
        completed = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            text=True,
            capture_output=True,
            timeout=240,
        )
        return {
            "ok": completed.returncode == 0,
            "startedAt": started,
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "returnCode": completed.returncode,
            "stdout": completed.stdout[-5000:],
            "stderr": completed.stderr[-3000:],
            "command": " ".join(args),
        }
    except Exception as exc:
        return {
            "ok": False,
            "startedAt": started,
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
            "command": " ".join(args),
        }


def _bot_loop() -> None:
    while not _BOT_STOP.is_set():
        with _BOT_LOCK:
            _BOT_STATE["lastRunAt"] = datetime.now(timezone.utc).isoformat()
            _BOT_STATE["lastError"] = None
        research = _run_engine_command("research-once")
        auto_buy = _run_engine_command("auto-buy-once")
        with _BOT_LOCK:
            _BOT_STATE["runCount"] = int(_BOT_STATE.get("runCount") or 0) + 1
            _BOT_STATE["lastResult"] = {
                "research": research,
                "autoBuy": auto_buy,
            }
            if not research.get("ok") or not auto_buy.get("ok"):
                _BOT_STATE["lastError"] = research.get("error") or auto_buy.get("error") or "backend command rejected"
            _BOT_STATE["nextRunAt"] = datetime.fromtimestamp(time.time() + BOT_INTERVAL_SEC, timezone.utc).isoformat()
        _BOT_STOP.wait(BOT_INTERVAL_SEC)


def _start_bot_loop() -> dict:
    global _BOT_THREAD
    with _BOT_LOCK:
        if _BOT_THREAD is not None and _BOT_THREAD.is_alive():
            status = {**_BOT_STATE, "alreadyRunning": True}
            status["capabilities"] = build_action_capabilities(status, journal_present=DB_PATH.exists())
            return status
        capabilities = build_action_capabilities(_BOT_STATE, journal_present=DB_PATH.exists())
        start_capability = capabilities["actions"]["startPaperBot"]
        if not start_capability["allowed"]:
            _BOT_STATE.update({
                "running": False,
                "lastError": "; ".join(start_capability["reasons"]) or "start blocked by backend authority",
                "nextRunAt": None,
            })
            return {
                **_BOT_STATE,
                "alreadyRunning": False,
                "blocked": True,
                "reason": _BOT_STATE["lastError"],
                "capabilities": capabilities,
            }
        _BOT_STOP.clear()
        _BOT_STATE.update({
            "running": True,
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "lastError": None,
            "nextRunAt": "starting now",
        })
        _BOT_THREAD = threading.Thread(target=_bot_loop, name="spencer-paper-bot", daemon=True)
        _BOT_THREAD.start()
        status = {**_BOT_STATE, "alreadyRunning": False}
        status["capabilities"] = build_action_capabilities(status, journal_present=DB_PATH.exists())
        return status


def _bot_status() -> dict:
    with _BOT_LOCK:
        running = _BOT_THREAD is not None and _BOT_THREAD.is_alive()
        _BOT_STATE["running"] = running
        status = dict(_BOT_STATE)
        status["capabilities"] = build_action_capabilities(status, journal_present=DB_PATH.exists())
        status["governanceMode"] = "paper-only"
        return status


# ── REAL bot state (reads the actual paper journal, kite_bot.db) ─────────────
# This replaces the old simulated Node engine as the dashboard's source of truth.
# Everything here is computed from real journaled paper trades — no fabricated
# numbers, no Math.random, no synthetic prices. If the journal is empty, we return
# honest zeros with a note rather than inventing activity.
DB_PATH = BASE_DIR / "kite_bot.db"
PROFILE_PATH = BASE_DIR / "strategy_profile.json"
REGIME_TRUST_PATH = BASE_DIR / "regime_trust.json"
WORKFLOW_DIR = BASE_DIR / "workflow"
WORKFLOW_TASKS_DIR = WORKFLOW_DIR / "tasks"
WORKFLOW_STATUS_DIR = WORKFLOW_TASKS_DIR / ".status"
WORKFLOW_LOGS_DIR = WORKFLOW_DIR / "logs"
WORKFLOW_DEPLOYMENT_GATE_PATH = WORKFLOW_DIR / "deployment_gate.json"
WORKFLOW_AGENT_POLICY_PATH = WORKFLOW_DIR / "agents" / "agent_policy.json"


def _state_json(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return default


def _load_json_file(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _workflow_status() -> dict:
    tasks = []
    if WORKFLOW_TASKS_DIR.exists():
        for path in sorted(WORKFLOW_TASKS_DIR.glob("*")):
            if path.name.startswith(".") or path.suffix.lower() not in {".md", ".json"}:
                continue
            status_path = WORKFLOW_STATUS_DIR / f"{path.stem}.status.json"
            status = _load_json_file(status_path) or {}
            tasks.append({
                "name": path.name,
                "path": str(path.relative_to(BASE_DIR)),
                "status": status.get("status", "pending"),
                "updatedAt": status.get("updatedAt"),
                "logJson": status.get("logJson"),
                "logMarkdown": status.get("logMarkdown"),
                "failures": status.get("failures", []),
                "safetyFailures": status.get("safetyFailures", []),
                "researchDecision": status.get("researchDecision"),
                "researchModule": status.get("researchModule"),
                "deploymentBlocked": status.get("deploymentBlocked"),
                "createdTasks": status.get("createdTasks", []),
                "existingTasks": status.get("existingTasks", []),
                "reason": status.get("reason"),
                "agentHandoff": status.get("agentHandoff", []),
            })

    logs = []
    if WORKFLOW_LOGS_DIR.exists():
        for path in sorted(WORKFLOW_LOGS_DIR.glob("*.json"), reverse=True)[:10]:
            payload = _load_json_file(path) or {}
            logs.append({
                "path": str(path.relative_to(BASE_DIR)),
                "taskId": payload.get("task_id") or payload.get("taskId"),
                "status": payload.get("status"),
                "module": payload.get("module"),
                "decision": payload.get("decision"),
                "deploymentBlocked": payload.get("deploymentBlocked"),
                "validationPassed": payload.get("validationPassed"),
                "reason": payload.get("reason"),
                "candidates": payload.get("candidates", []),
                "finishedAt": payload.get("finished_at") or payload.get("finishedAt"),
                "failures": payload.get("failures", []),
                "reviewerNotes": payload.get("reviewer_notes") or payload.get("reviewerNotes", []),
                "agentHandoff": payload.get("agent_handoff") or payload.get("agentHandoff", []),
            })

    deployment_gate = _load_json_file(WORKFLOW_DEPLOYMENT_GATE_PATH) or {}
    agent_policy = _load_json_file(WORKFLOW_AGENT_POLICY_PATH) or {}
    return {
        "ok": True,
        "source": "workflow/tasks, workflow/tasks/.status, workflow/logs, workflow/deployment_gate.json, workflow/agents/agent_policy.json",
        "asof": datetime.now(timezone.utc).isoformat(),
        "deploymentGate": deployment_gate,
        "agentPolicy": agent_policy,
        "tasks": tasks,
        "latestLogs": logs,
    }


def _closed_trade_metrics(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT pnl FROM trades WHERE action='SELL' AND pnl IS NOT NULL"
    ).fetchall()
    pnls = [r[0] for r in rows]
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    return {
        "closedTrades": n,
        "wins": wins,
        "losses": losses,
        # Win rate is computed ONLY from real closed trades; 0 closed -> 0, not faked.
        "winRate": round(wins / n * 100, 1) if n else 0.0,
    }


def _recent_orders(conn: sqlite3.Connection, limit: int = 25) -> list[dict]:
    rows = conn.execute(
        "SELECT ts, symbol, action, price, qty, pnl, entry_reason, exit_reason "
        "FROM trades ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for ts, symbol, action, price, qty, pnl, entry_reason, exit_reason in rows:
        out.append({
            "time": ts, "symbol": symbol, "side": action,
            "qty": qty, "price": round(price, 2) if price is not None else None,
            "status": "COMPLETE", "pnl": round(pnl, 2) if pnl is not None else None,
            "reason": exit_reason or entry_reason or "",
        })
    return out


def _real_bot_state() -> dict:
    """Build the dashboard state object from the real paper journal."""
    if not DB_PATH.exists():
        bot = _bot_status()
        governance = build_governance_snapshot(bot, journal_present=False)
        return {"ok": True, "simulated": False, "source": "kite_bot.db (absent)",
                "note": "No journal yet — run the paper engine to populate real data.",
                "capital": None, "holdings": [], "orders": [], "activity": [],
                "metrics": {"closedTrades": 0, "wins": 0, "losses": 0, "winRate": 0.0},
                "capabilities": governance["capabilities"], "governance": governance,
                "workflow": _workflow_status()}

    conn = sqlite3.connect(str(DB_PATH))
    try:
        portfolio = _state_json(conn, "portfolio", {}) or {}
        budget = _state_json(conn, "paper_budget_inr", 5000.0) or 5000.0
        selected = _state_json(conn, "selected_strategy", None)
        heartbeat = _state_json(conn, "last_heartbeat", {}) or {}

        # Open positions -> holdings, priced with REAL live quotes where possible.
        positions = portfolio.get("positions") or {}
        sym_prices: dict[str, float] = {}
        if positions:
            try:
                for row in _quote_rows(list(positions.keys())):
                    if row.get("price") is not None:
                        sym_prices[row["symbol"]] = row["price"]
            except Exception:
                pass

        holdings, invested, current_value = [], 0.0, 0.0
        for sym, p in positions.items():
            qty = float(p.get("qty") or p.get("quantity") or 0)
            avg = float(p.get("entry_price") or p.get("avg_price")
                        or p.get("avg") or p.get("entry") or 0)
            ltp = float(sym_prices.get(sym) or avg)
            invested += qty * avg
            current_value += qty * ltp
            holdings.append({"symbol": sym, "qty": qty, "avg": round(avg, 2),
                             "ltp": round(ltp, 2), "sector": "—"})

        cash = float(portfolio.get("cash", budget))
        realised = float(portfolio.get("realized_pnl", 0.0))
        unrealised = current_value - invested
        total_value = cash + current_value
        total_pnl = realised + unrealised

        capital = {
            "budget": round(float(budget), 2),
            "cash": round(cash, 2),
            "invested": round(invested, 2),
            "currentValue": round(current_value, 2),
            "totalValue": round(total_value, 2),
            "unrealisedPnl": round(unrealised, 2),
            "realisedPnl": round(realised, 2),
            "totalPnl": round(total_pnl, 2),
            "pnlPct": round(total_pnl / budget * 100, 2) if budget else 0.0,
            "unrealisedPnlPct": round(unrealised / invested * 100, 2) if invested else 0.0,
        }

        metrics = _closed_trade_metrics(conn)
        orders = _recent_orders(conn)
        activity = [
            {"type": "trade",
             "text": f"{o['side']} {o['qty']} {o['symbol']} @ Rs.{o['price']}"
                     + (f" · P&L Rs.{o['pnl']}" if o.get("pnl") is not None else ""),
             "time": o["time"]}
            for o in orders[:30]
        ]
        control = heartbeat.get("control") or {}
        bot = _bot_status()
        governance = build_governance_snapshot(bot, journal_present=True)
        return {
            "ok": True,
            "simulated": False,
            "source": "real paper_engine journal (kite_bot.db)",
            "asof": datetime.now(timezone.utc).isoformat(),
            "running": bot.get("running", False),
            "control": {"killed": bool(control.get("killed")),
                        "paused": bool(control.get("paused"))},
            "botWatching": selected,
            "capital": capital,
            "metrics": metrics,
            "holdings": holdings,
            "openPosition": holdings[0] if holdings else None,
            "orders": orders,
            "trades": orders,
            "activity": activity,
            # Real learning outputs (honest; may be defaults until enough trades).
            "learner": _load_json_file(PROFILE_PATH),
            "regimeTrust": _load_json_file(REGIME_TRUST_PATH),
            "capabilities": governance["capabilities"],
            "governance": governance,
            "workflow": _workflow_status(),
        }
    finally:
        conn.close()


def _set_budget(amount: float) -> dict:
    """Persist the operator paper budget to the same store paper_engine reads."""
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "budget must be a number"}
    amount = max(1_000.0, min(10_000_000.0, amount))   # sane clamp
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO bot_state(key, value) VALUES('paper_budget_inr', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps(amount),),
        )
        conn.commit()
    return {"ok": True, "paper_budget_inr": amount}


def _stop_bot_loop() -> dict:
    _BOT_STOP.set()
    with _BOT_LOCK:
        _BOT_STATE["running"] = False
    return {"ok": True, "running": False}


def _research(symbols: list[str]) -> list[dict]:
    rows = []
    for quote_row in _quote_rows(symbols):
        symbol = quote_row["symbol"]
        sma20 = sma50 = ret20 = avg_volume = None
        trend = "unavailable"
        try:
            chart = _chart(symbol, "1d", "1y")
            candles = chart.get("candles", [])
            closes = [float(c["close"]) for c in candles if c.get("close") is not None]
            volumes = [float(c.get("volume") or 0) for c in candles]
            if len(closes) >= 30:
                sma20 = sum(closes[-20:]) / 20
                sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
                ret20 = (closes[-1] / closes[-21] - 1) if len(closes) >= 21 and closes[-21] else 0
                avg_volume = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 0
                trend = "bullish" if closes[-1] > sma20 and (sma50 is None or sma20 > sma50) else "mixed"
            elif closes:
                trend = "thin data"
        except Exception:
            pass

        rows.append({
            "symbol": symbol,
            "lastPrice": quote_row.get("price"),
            "changePct": quote_row.get("changePct"),
            "trend": trend,
            "sma20": round(sma20, 2) if sma20 else None,
            "sma50": round(sma50, 2) if sma50 else None,
            "return20d": round(ret20, 4) if ret20 is not None else None,
            "avgVolume20d": round(avg_volume, 2) if avg_volume is not None else None,
            "asof": datetime.now(timezone.utc).isoformat(),
            "source": "Yahoo Finance chart research",
        })
    return rows


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        _json(self, 200, {"ok": True})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/ai/chat":
            payload = _read_json_body(self)
            prompt = str(payload.get("prompt") or "").strip()
            if not prompt:
                _json(self, 400, {"ok": False, "error": "Prompt is required"})
                return
            result = _call_gemini(
                prompt,
                payload.get("temperature", 0.3),
                payload.get("maxOutputTokens", 600),
            )
            _json(self, 200 if result.get("ok") else int(result.get("status") or 500), result)
            return
        if parsed.path == "/api/bot/start":
            _json(self, 200, {"ok": True, "bot": _start_bot_loop()})
            return
        if parsed.path == "/api/bot/status":
            _json(self, 200, {"ok": True, "bot": _bot_status()})
            return
        if parsed.path == "/api/bot/stop":
            _json(self, 200, _stop_bot_loop())
            return
        if parsed.path == "/api/bot/config":
            payload = _read_json_body(self)
            _json(self, 200, _set_budget(payload.get("budget", 5000.0)))
            return
        if parsed.path == "/api/bot/reset":
            # Intentionally does NOT wipe the journal — that is the real record.
            _json(self, 200, {"ok": True,
                              "note": "reset is a no-op; the paper journal is preserved."})
            return
        _json(self, 404, {"ok": False, "error": "unknown endpoint"})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/quotes":
                symbols = _symbols(qs.get("symbols", [""])[0])
                _json(self, 200, {"ok": True, "quotes": _quote_rows(symbols)})
                return
            if parsed.path == "/api/chart":
                symbols = _symbols(qs.get("symbol", ["RELIANCE"])[0]) or ["RELIANCE"]
                interval = qs.get("interval", ["5m"])[0]
                _json(self, 200, {"ok": True, **_chart(symbols[0], interval)})
                return
            if parsed.path == "/api/research":
                symbols = _symbols(qs.get("symbols", ["RELIANCE,TCS,INFY"])[0])
                _json(self, 200, {"ok": True, "research": _research(symbols)})
                return
            if parsed.path == "/api/bot/status":
                _json(self, 200, {"ok": True, "bot": _bot_status()})
                return
            if parsed.path == "/api/bot/state":
                _json(self, 200, _real_bot_state())
                return
            if parsed.path == "/api/governance":
                bot = _bot_status()
                _json(self, 200, build_governance_snapshot(bot, journal_present=DB_PATH.exists()))
                return
            if parsed.path == "/api/workflow/status":
                _json(self, 200, _workflow_status())
                return
            if parsed.path == "/api/handoff":
                _json(self, 200, _handoff_payload())
                return
            _json(self, 404, {"ok": False, "error": "unknown endpoint"})
        except Exception as exc:
            _json(self, 500, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Spencer quote server running at http://127.0.0.1:{PORT}")
    server.serve_forever()
