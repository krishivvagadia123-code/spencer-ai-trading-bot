#!/usr/bin/env python3
"""
kite-bot — NSE paper trading CLI.

Two invocation modes:

  Interactive REPL:
      python paper_engine.py

  Scheduler-safe one-shot (designed for Windows Task Scheduler / cron):
      python paper_engine.py monitor-once
      python paper_engine.py status
      python paper_engine.py kill <reason>
      python paper_engine.py unkill
      python paper_engine.py pause <reason>
      python paper_engine.py resume

Invariant (Phase D/E):
  BUY  →  goes through bot.risk.is_entry_allowed (caps + kill + pause).
  SELL / FLATTEN / STOP / TARGET  →  bypass ALL gates. Exits are always allowed.

Paper-only. No live broker order placement anywhere.
"""

from __future__ import annotations
import os
import sys
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from bot import control
from bot.config import ONE_STOCK_UNIVERSE, default_config
from bot.dashboard import (
    DEFAULT_DASHBOARD_PATH, export_dashboard, read_monitor_log_tail,
)
from bot.db import init_db, log_trade as db_log_trade, save_state, load_state, get_pnl_summary, get_all_trades
from bot.engine import (
    BuyResult, SellResult,
    do_buy, do_sell, do_flatten, do_monitor_once,
    serialize_portfolio, deserialize_portfolio,
)
from bot.capital_governor import GovernorDecision, adjusted_risk_cfg, assess as governor_assess
from bot.coach import (
    CoachState, ensure_coach_assets, update_live_coach_state,
)
from bot.learner import load_profile, update_profile
from bot.strategies import BacktestBar
from bot.strategies.regime_filter import RegimeFilter
from bot.strategy_tournament import (
    active_champion, load_leaderboard, run_tournament,
)
from bot.logger_config import get_logger
from bot.market_data import IST, Quote, now_ist, validate_quote
from bot.portfolio import Portfolio
from bot.research import NeutralResearchProvider, get_or_fetch, list_snapshots_for_date
from bot.scanner import list_recent_candidates, scan_once
from bot.signals import TechnicalSnapshot
from bot.supervisor import auto_buy_once, run_forever
from bot.watchdog import CircuitBreaker

log = get_logger("kite-bot")

BASE_DIR    = Path(__file__).parent
CONTROL_DIR = BASE_DIR / "control"
LOG_DIR     = CONTROL_DIR / "logs"
TERMINAL_PORT = 8765

# Spencer is now a one-stock paper account. All scanner and CLI entry paths
# derive from this map, so non-RELIANCE symbols cannot enter the paper engine.
WATCHLIST = {symbol: f"{symbol}.NS" for symbol in ONE_STOCK_UNIVERSE}

TRADINGVIEW_SYMBOLS = {symbol: f"NSE:{symbol}" for symbol in WATCHLIST}
LEGACY_CHART_SYMBOLS = {
    "BTC-INR": "BINANCE:BTCUSDT",
    "ETH-INR": "BINANCE:ETHUSDT",
    "DOGE-INR": "BINANCE:DOGEUSDT",
    "LINK-INR": "BINANCE:LINKUSDT",
    "XRP-INR": "BINANCE:XRPUSDT",
    "AVAX-INR": "BINANCE:AVAXUSDT",
}
INDEX_WATCH = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
}
DEFAULT_STRATEGY_ID = "equity_vwap_breakout"
STRATEGY_CATALOG = [
    {"id": "equity_vwap_breakout", "name": "VWAP Breakout", "built_by": "Institutional intraday playbook", "desc": "Trade only liquid NSE names that hold above VWAP, break a clean range, and pass risk caps.", "risk": "Best in trend days; avoid choppy opens.", "learn_url": "https://www.youtube.com/results?search_query=VWAP+breakout+trading+strategy"},
    {"id": "orb_15", "name": "15 Minute ORB", "built_by": "Opening range traders", "desc": "Use the first 15 minutes as the battle line, then buy strength only after confirmation.", "risk": "False breakouts are common after gap opens.", "learn_url": "https://www.youtube.com/results?search_query=15+minute+opening+range+breakout+Indian+market"},
    {"id": "ema_supertrend", "name": "EMA + Supertrend", "built_by": "Trend-following traders", "desc": "Require price above 20 EMA, 50 EMA, VWAP, and a green trend filter before entries.", "risk": "Late entries can occur after extended candles.", "learn_url": "https://www.youtube.com/results?search_query=EMA+Supertrend+strategy+Indian+stocks"},
    {"id": "darvas_box", "name": "Darvas Box", "built_by": "Nicolas Darvas", "desc": "Look for tight consolidation boxes, then participate only when price expands with volume.", "risk": "Needs disciplined stops below the box.", "learn_url": "https://www.youtube.com/results?search_query=Darvas+Box+trading+strategy"},
    {"id": "donchian_breakout", "name": "Donchian Breakout", "built_by": "Richard Donchian", "desc": "Buy fresh multi-period highs in liquid stocks while cutting failed breakouts quickly.", "risk": "Whipsaws in sideways markets.", "learn_url": "https://www.youtube.com/results?search_query=Donchian+breakout+strategy"},
    {"id": "bollinger_reversion", "name": "Bollinger Reversion", "built_by": "Mean reversion traders", "desc": "Fade stretched moves only when volume and trend filters confirm exhaustion.", "risk": "Dangerous during one-way trend days.", "learn_url": "https://www.youtube.com/results?search_query=Bollinger+Bands+mean+reversion+strategy"},
    {"id": "rsi_pullback", "name": "RSI Pullback", "built_by": "Momentum pullback traders", "desc": "Prefer healthy RSI resets in an uptrend rather than chasing overbought spikes.", "risk": "Pullbacks can turn into reversals.", "learn_url": "https://www.youtube.com/results?search_query=RSI+pullback+strategy+stocks"},
    {"id": "macd_momentum", "name": "MACD Momentum", "built_by": "Momentum traders", "desc": "Use MACD expansion as confirmation after trend and liquidity filters already agree.", "risk": "MACD lags fast reversals.", "learn_url": "https://www.youtube.com/results?search_query=MACD+momentum+trading+strategy"},
    {"id": "minervini_trend", "name": "Minervini Trend Template", "built_by": "Mark Minervini", "desc": "Screen for strong trend structure and avoid weak stocks below major moving averages.", "risk": "More useful for swing context than instant scalps.", "learn_url": "https://www.youtube.com/results?search_query=Mark+Minervini+trend+template"},
    {"id": "canslim_screen", "name": "CAN SLIM Screen", "built_by": "William O'Neil", "desc": "Blend earnings, leadership, institutional interest, and technical strength as a quality filter.", "risk": "Fundamental data must be refreshed from trusted feeds.", "learn_url": "https://www.youtube.com/results?search_query=CAN+SLIM+strategy"},
    {"id": "sector_rotation", "name": "Sector Rotation", "built_by": "Relative-strength managers", "desc": "Favor stocks from sectors outperforming NIFTY before individual entries are allowed.", "risk": "Sector leadership can rotate abruptly.", "learn_url": "https://www.youtube.com/results?search_query=sector+rotation+trading+strategy+India"},
    {"id": "gap_and_go", "name": "Gap and Go", "built_by": "Momentum day traders", "desc": "Trade strong news gaps only if price holds the gap and volume confirms continuation.", "risk": "Gap fills can be sharp.", "learn_url": "https://www.youtube.com/results?search_query=gap+and+go+trading+strategy"},
    {"id": "mean_reversion_vwap", "name": "VWAP Mean Reversion", "built_by": "Intraday reversion desks", "desc": "Use VWAP as fair value and enter only after stretched moves cool down.", "risk": "Avoid during strong trend sessions.", "learn_url": "https://www.youtube.com/results?search_query=VWAP+mean+reversion+strategy"},
    {"id": "atr_trailing", "name": "ATR Trailing Stop", "built_by": "Risk-first trend traders", "desc": "Let winners breathe with ATR-based exits while keeping position size modest.", "risk": "Can give back open profit before exit.", "learn_url": "https://www.youtube.com/results?search_query=ATR+trailing+stop+strategy"},
    {"id": "capital_defense", "name": "Capital Defense", "built_by": "Risk managers", "desc": "Reduce trade frequency after losses, cap daily damage, and wait for higher-quality setups.", "risk": "May skip profitable rebounds after a pause.", "learn_url": "https://www.youtube.com/results?search_query=risk+management+trading+strategy"},
]
BID_ROWS = [
    {"instrument": "HARIKANTA", "date": "20th - 27th May", "price": "86 - 91", "min_amount": "218400", "status": "Apply"},
    {"instrument": "MANIVENI", "date": "22nd - 26th May", "price": "51 - 52", "min_amount": "208000", "status": "Apply"},
    {"instrument": "YAASHVI", "date": "25th - 27th May", "price": "83", "min_amount": "265600", "status": "Apply"},
    {"instrument": "RFIL", "date": "26th - 29th May", "price": "59 - 63", "min_amount": "252000", "status": "Apply"},
]

_BASE_CFG = default_config()
CFG = _BASE_CFG.model_copy(update={
    "risk": _BASE_CFG.risk.model_copy(update={
        "risk_per_trade_pct": 0.35,
        "max_daily_loss_pct": 1.0,
        "max_drawdown_pct": 3.0,
        "max_open_positions": 1,
        "max_symbol_notional_pct": 100.0,
        "max_total_exposure_pct": 100.0,
        "max_symbol_notional_inr": 5_000.0,
        "max_total_notional_inr": 5_000.0,
    }),
    "supervisor": _BASE_CFG.supervisor.model_copy(update={
        "min_total_score_to_buy": 0.72,
        "cooldown_sec_per_symbol": 3600,
        "dashboard_interval_sec": 10,
    }),
})
PRODUCT = "INTRADAY"
breaker = CircuitBreaker(threshold=5)

# Heuristic ATR estimate — used only as a fallback when indicators absent
DEFAULT_ATR_PCT = 0.012
MAX_OPERATOR_BUDGET_INR = 5_000.0
DEFAULT_OPERATOR_BUDGET_INR = 5_000.0
_YFINANCE_IMPORT_CHECKED = False
_YFINANCE_MODULE = None


def _paper_budget_cap() -> float:
    try:
        raw = float(load_state("paper_budget_inr") or DEFAULT_OPERATOR_BUDGET_INR)
    except Exception:
        raw = DEFAULT_OPERATOR_BUDGET_INR
    return max(5_000.0, min(MAX_OPERATOR_BUDGET_INR, raw))


def _effective_risk_cfg():
    budget = _paper_budget_cap()
    return CFG.risk.model_copy(update={
        "max_total_notional_inr": budget,
        "max_symbol_notional_inr": min(15_000.0, max(2_500.0, budget * 0.30)),
    })


def _effective_config():
    return CFG.model_copy(update={"risk": _effective_risk_cfg()})


def _selected_strategy() -> str:
    try:
        strategy = load_state("selected_strategy", DEFAULT_STRATEGY_ID)
    except Exception:
        strategy = DEFAULT_STRATEGY_ID
    ids = {s["id"] for s in STRATEGY_CATALOG}
    return strategy if strategy in ids else DEFAULT_STRATEGY_ID


def _strategy_label(strategy_id: str) -> str:
    for s in STRATEGY_CATALOG:
        if s["id"] == strategy_id:
            return s["name"]
    return strategy_id


def _strategy_from_trade(row: dict) -> str:
    text = " ".join(str(row.get(k) or "") for k in ("entry_reason", "exit_reason"))
    marker = "strategy="
    if marker in text:
        strategy = text.split(marker, 1)[1].split()[0].strip()
        if strategy:
            return strategy
    snapshot = row.get("signal_snapshot")
    if snapshot:
        try:
            parsed = json.loads(snapshot)
            strategy = parsed.get("active_strategy") or parsed.get("strategy")
            if strategy:
                return strategy
        except Exception:
            pass
    return "manual/legacy"


def _position_strategy_map(trades: Optional[list] = None) -> dict:
    trades = trades if trades is not None else get_all_trades()
    active = {}
    for row in trades:
        symbol = row.get("symbol")
        if not symbol:
            continue
        action = str(row.get("action") or "").upper()
        if action == "BUY":
            active[symbol] = {
                "strategy": _strategy_from_trade(row),
                "reason": row.get("entry_reason") or "",
            }
        elif action == "SELL":
            active.pop(symbol, None)
    return active


def _trade_attribution_rows(positions_rows: list, trades: Optional[list] = None) -> list:
    trades = trades if trades is not None else get_all_trades()
    active = {}
    closed = []
    for row in trades:
        symbol = row.get("symbol")
        if not symbol:
            continue
        action = str(row.get("action") or "").upper()
        if action == "BUY":
            active[symbol] = {
                "strategy": _strategy_from_trade(row),
                "reason": row.get("entry_reason") or "",
            }
            continue
        if action == "SELL":
            meta = active.get(symbol, {})
            exit_reason = row.get("exit_reason") or "SELL"
            entry_reason = meta.get("reason") or row.get("entry_reason") or ""
            reason = f"{entry_reason} -> {exit_reason}" if entry_reason else exit_reason
            closed.append({
                "ts": row.get("ts"),
                "symbol": symbol,
                "action": "CLOSED",
                "strategy": meta.get("strategy") or _strategy_from_trade(row),
                "reason": reason,
                "pnl": row.get("pnl"),
            })
            active.pop(symbol, None)
    open_rows = []
    for row in positions_rows:
        open_rows.append({
            "ts": "OPEN",
            "symbol": row.get("symbol"),
            "action": "OPEN",
            "strategy": row.get("strategy") or _selected_strategy(),
            "reason": "Current open trade marked to latest available price",
            "pnl": row.get("pnl"),
        })
    return open_rows + list(reversed(closed[-60:]))


def _brain_notes(account: dict, attribution: list) -> list:
    notes = []
    realized = account.get("realized_pnl")
    try:
        realized_f = float(realized)
    except Exception:
        realized_f = 0.0
    if realized_f < 0:
        notes.append(
            f"Realized P&L is Rs.{realized_f:,.2f}. The bot is now equity-only, "
            "using tighter entries, 0.35% risk per trade, a 1% daily-loss cap, "
            "and a 3% drawdown cap."
        )
    else:
        notes.append(
            "Capital defense is active: entries must pass trend, VWAP/EMA alignment, "
            "score threshold, cooldown, and exposure caps before a paper buy is allowed."
        )
    for row in attribution[:6]:
        pnl = row.get("pnl")
        if pnl in ("", None):
            pnl_txt = "open"
        else:
            try:
                pnl_txt = f"Rs.{float(pnl):+,.2f}"
            except Exception:
                pnl_txt = str(pnl)
        notes.append(
            f"{row.get('symbol')} {row.get('action')}: {pnl_txt} via "
            f"{row.get('strategy') or 'manual/legacy'}."
        )
    return notes


def _index_rows() -> list:
    rows = []
    yf = _import_yfinance()
    for name, ticker in INDEX_WATCH.items():
        item = {"name": name, "value": "", "change": ""}
        if yf is not None:
            try:
                h = yf.Ticker(ticker).history(period="2d", interval="1d")
                if not h.empty:
                    value = float(h.iloc[-1]["Close"])
                    prev = float(h.iloc[-2]["Close"]) if len(h) > 1 else value
                    item["value"] = round(value, 2)
                    item["change"] = round(value - prev, 2)
            except Exception:
                pass
        rows.append(item)
    return rows


def _terminal_token() -> str:
    token = load_state("terminal_token")
    if token:
        return token
    import secrets
    token = secrets.token_urlsafe(24)
    save_state("terminal_token", token)
    return token


def _terminal_host_ip() -> str:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def _terminal_base_url() -> str:
    return f"http://{_terminal_host_ip()}:{TERMINAL_PORT}"


# ── Quote provider (yfinance-backed, validated) ──────────────────────────────
def _import_yfinance():
    """Lazy import so control commands work without yfinance installed."""
    global _YFINANCE_IMPORT_CHECKED, _YFINANCE_MODULE
    if _YFINANCE_IMPORT_CHECKED:
        return _YFINANCE_MODULE
    try:
        import yfinance as yf
        _YFINANCE_MODULE = yf
    except ImportError as e:
        log.warning(f"yfinance not available; using Yahoo chart fallback: {e}")
        _YFINANCE_MODULE = None
    _YFINANCE_IMPORT_CHECKED = True
    return _YFINANCE_MODULE


def _fetch_yahoo_chart_rows(symbol: str, range_name: str = "6mo",
                            interval: str = "1d") -> list[dict]:
    """Small dependency-free Yahoo chart fetcher used for closed-market research."""
    from urllib.parse import quote
    from urllib.request import Request, urlopen

    ticker = WATCHLIST.get(symbol, symbol)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + quote(ticker)
        + f"?range={quote(range_name)}&interval={quote(interval)}"
        + "&includePrePost=false&events=history"
    )
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 SpencerAI/1.0",
        "Accept": "application/json",
    })
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        return []

    timestamps = result.get("timestamp") or []
    quote_rows = (result.get("indicators", {}).get("quote") or [{}])[0]
    opens = quote_rows.get("open") or []
    highs = quote_rows.get("high") or []
    lows = quote_rows.get("low") or []
    closes = quote_rows.get("close") or []
    volumes = quote_rows.get("volume") or []
    rows = []
    for idx, ts in enumerate(timestamps):
        try:
            o = opens[idx]
            h = highs[idx]
            l = lows[idx]
            c = closes[idx]
            if o is None or h is None or l is None or c is None:
                continue
            rows.append({
                "ts": datetime.fromtimestamp(int(ts), IST),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(volumes[idx] or 0) if idx < len(volumes) else 0.0,
            })
        except Exception:
            continue
    return rows


def _yahoo_quote_provider(symbol: str) -> Optional[Quote]:
    try:
        rows = _fetch_yahoo_chart_rows(symbol, range_name="1d", interval="5m")
        if not rows:
            return None
        last_bar = rows[-1]
        return validate_quote(
            round(float(last_bar["close"]), 4),
            last_bar["ts"],
            symbol,
            CFG.market,
        )
    except Exception as e:
        log.warning(f"Yahoo chart quote fallback failed for {symbol}: {e}")
        return None


def _yahoo_research_source(symbol: str, asof: date) -> dict:
    try:
        rows = _fetch_yahoo_chart_rows(symbol, range_name="6mo", interval="1d")
        closes = [r["close"] for r in rows]
        volumes = [r["volume"] for r in rows]
        if not closes:
            return NeutralResearchProvider().fetch(symbol, asof)
        last = closes[-1]
        sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
        ret20 = ((last / closes[-21]) - 1.0) if len(closes) >= 21 and closes[-21] else 0.0
        avg_volume = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 0.0
        trend_ok = bool(last and sma20 and last > sma20 and (sma50 is None or sma20 >= sma50))
        fundamentals_score = 0.62 if trend_ok else 0.48
        sentiment_score = max(0.0, min(1.0, 0.5 + ret20))
        liquidity_score = max(0.0, min(1.0, avg_volume / 2_000_000)) if avg_volume else 0.5
        return {
            "provider": "yahoo_chart_closed_market_research",
            "symbol": symbol,
            "ticker": WATCHLIST.get(symbol, symbol),
            "asof": asof.isoformat(),
            "last_close": round(last, 4) if last else None,
            "sma20": round(sma20, 4) if sma20 else None,
            "sma50": round(sma50, 4) if sma50 else None,
            "return_20d": round(ret20, 4),
            "avg_volume_20d": round(avg_volume, 2),
            "fundamentals_raw": fundamentals_score,
            "sentiment_raw": sentiment_score,
            "liquidity_raw": liquidity_score,
        }
    except Exception as e:
        log.warning(f"Yahoo research fallback failed for {symbol}: {e}")
        return NeutralResearchProvider().fetch(symbol, asof)


def _unavailable_symbols() -> set:
    raw = load_state("unavailable_symbols") or []
    return set(raw)


def tradingview_symbol_for(symbol: str) -> str:
    return TRADINGVIEW_SYMBOLS.get(symbol, LEGACY_CHART_SYMBOLS.get(symbol, symbol))


def tradingview_url_for(symbol: str) -> str:
    from urllib.parse import quote
    tv_symbol = tradingview_symbol_for(symbol)
    return "https://www.tradingview.com/chart/?symbol=" + quote(tv_symbol, safe="")


def tradingview_widget_url_for(symbol: str) -> str:
    from urllib.parse import quote
    tv_symbol = tradingview_symbol_for(symbol)
    return (
        "https://www.tradingview.com/widgetembed/?symbol="
        + quote(tv_symbol, safe="")
        + "&interval=5&theme=light&style=1&timezone=Asia%2FKolkata"
        + "&hide_top_toolbar=0&hide_side_toolbar=0&save_image=0"
    )


def _best_recent_candidate_symbol(limit: int = 50) -> Optional[str]:
    try:
        rows = list_recent_candidates(limit=limit)
    except Exception:
        return None
    ranked = sorted(
        rows,
        key=lambda r: float(r.get("total_score") or 0.0),
        reverse=True,
    )
    for row in ranked:
        sym = row.get("symbol")
        if sym in WATCHLIST and sym not in _unavailable_symbols():
            return sym
    return None


def select_visual_symbol(pf: Optional[Portfolio] = None) -> str:
    """
    Choose the chart the operator should see.

    Open positions are most important, then strongest recent candidate, then
    the first available watchlist symbol. This keeps TradingView and the live
    coach attached to the same coin the bot is actually focused on.
    """
    if pf is not None and pf.state.positions:
        return sorted(pf.state.positions.keys())[0]
    recent = _best_recent_candidate_symbol()
    if recent:
        return recent
    for symbol in WATCHLIST:
        if symbol not in _unavailable_symbols():
            return symbol
    return next(iter(WATCHLIST))


def yfinance_quote_provider(symbol: str) -> Optional[Quote]:
    """
    Fetch a live quote via yfinance and run it through validate_quote.

    Equity mode uses 5m NSE bars. Honors the symbol-availability cache so
    retries don't hammer unavailable symbols.
    """
    if symbol in _unavailable_symbols():
        return None
    if not breaker.check():
        log.warning(f"Circuit breaker open, skipping {symbol}")
        return None

    yf = _import_yfinance()
    if yf is None:
        return _yahoo_quote_provider(symbol)

    ticker = WATCHLIST.get(symbol, symbol)
    try:
        h = yf.Ticker(ticker).history(period="1d", interval="5m")
        if h.empty:
            breaker.record_failure(f"empty {symbol}")
            return None
        breaker.record_success()

        last_bar = h.iloc[-1]
        price    = round(float(last_bar["Close"]), 4)

        raw_ts = h.index[-1]
        bar_dt = raw_ts.to_pydatetime() if hasattr(raw_ts, "to_pydatetime") else raw_ts
        if bar_dt.tzinfo is None:
            from datetime import timezone as _tz
            bar_dt = bar_dt.replace(tzinfo=_tz.utc)
        bar_ts_ist = bar_dt.astimezone(IST)

        return validate_quote(price, bar_ts_ist, symbol, CFG.market)
    except Exception as e:
        breaker.record_failure(str(e))
        log.warning(f"Price error {symbol}: {e}")
        return _yahoo_quote_provider(symbol)


# ── Portfolio load/save ──────────────────────────────────────────────────────
def load_portfolio() -> Portfolio:
    raw = load_state("portfolio")
    if raw is None:
        pf = Portfolio.fresh(starting_balance=CFG.starting_balance)
        save_portfolio(pf)
        log.info(f"New portfolio Rs.{CFG.starting_balance:,.2f}")
        return pf
    pf = deserialize_portfolio(raw)
    _archive_non_equity_positions(pf)
    return pf


def save_portfolio(pf: Portfolio) -> None:
    save_state("portfolio", serialize_portfolio(pf))


# ── Day-start equity tracking (resets once per IST trading day) ──────────────
def _today_ist_key() -> str:
    return now_ist().date().isoformat()


def _current_equity_best_effort(pf: Portfolio) -> float:
    """
    Compute equity using whatever live prices we can fetch. If any open
    position has no quote, fall back to cash + sum(entry_price * qty) which
    is conservative for daily-loss tracking but never a substitute on the
    risk path (Portfolio.equity() still fails closed there).
    """
    if not pf.state.positions:
        return pf.state.cash
    prices: dict = {}
    for sym in pf.state.positions:
        q = yfinance_quote_provider(sym)
        if q is not None and q.is_usable:
            prices[sym] = q.price
    try:
        return pf.equity(prices)
    except Exception:
        # Fall back to entry-price valuation for day-start snapshotting only
        mv = sum(p.qty * p.entry_price for p in pf.state.positions.values())
        return round(pf.state.cash + mv, 2)


def _archive_non_equity_positions(pf: Portfolio) -> bool:
    """
    One-time safety migration for the switch back to NSE-only mode.
    Old paper crypto positions must not keep blocking the equity bot.
    """
    legacy = [
        (sym, pos) for sym, pos in list(pf.state.positions.items())
        if sym.endswith("-INR")
    ]
    if not legacy:
        return False
    for sym, pos in legacy:
        price = pos.entry_price
        price_source = "entry_price_fallback"
        try:
            q = yfinance_quote_provider(sym)
            if q is not None and q.is_usable:
                price = q.price
                price_source = "latest_quote"
        except Exception:
            pass
        gross_pnl = (float(price) - pos.entry_price) * pos.qty
        net_pnl = round(gross_pnl - pos.charges_buy, 2)
        proceeds = round(float(price) * pos.qty, 2)
        pf.state.cash = round(pf.state.cash + proceeds, 2)
        pf.state.realized_pnl = round(pf.state.realized_pnl + net_pnl, 2)
        pf.state.total_trades += 1
        if net_pnl > 0:
            pf.state.winning_trades += 1
        del pf.state.positions[sym]
        row = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": sym,
            "action": "SELL",
            "price": float(price),
            "qty": pos.qty,
            "value": proceeds,
            "charges": 0.0,
            "stop": pos.stop,
            "target": pos.target,
            "pnl": net_pnl,
            "balance_after": pf.state.cash,
            "entry_reason": None,
            "exit_reason": "EQUITY_ONLY_MIGRATION",
            "signal_snapshot": json.dumps({
                "legacy_symbol": sym,
                "price_source": price_source,
                "reason": "Archived legacy non-NSE paper position after equity-only switch",
            }, default=str),
            "slippage": 0.0,
            "equity_after": None,
        }
        try:
            db_log_trade(row)
        except Exception as e:
            log.warning(f"legacy position audit log failed for {sym}: {e}")
        log.warning(
            f"Archived legacy paper position {sym} at Rs.{float(price):,.2f} "
            f"({price_source}); pnl=Rs.{net_pnl:+,.2f}"
        )
    pf.state.last_updated = datetime.now()
    save_state("portfolio", serialize_portfolio(pf))
    return True


MONITOR_LOG_PATH = BASE_DIR / "monitor.log"


# ── Technical snapshot provider for scanner (no LLM, local-only) ─────────────
def _ema_values(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (span + 1)
    out = [float(values[0])]
    for value in values[1:]:
        out.append((float(value) * alpha) + (out[-1] * (1 - alpha)))
    return out


def _yahoo_technical_provider(symbol: str) -> Optional[TechnicalSnapshot]:
    try:
        rows = _fetch_yahoo_chart_rows(symbol, range_name="5d", interval="5m")
        if len(rows) < 20:
            rows = _fetch_yahoo_chart_rows(symbol, range_name="1mo", interval="15m")
        if len(rows) < 20:
            return None
        rows = rows[-160:]
        close = [float(r["close"]) for r in rows]
        high = [float(r["high"]) for r in rows]
        low = [float(r["low"]) for r in rows]
        volume = [float(r.get("volume") or 0.0) for r in rows]
        price = round(close[-1], 4)

        deltas = [close[i] - close[i - 1] for i in range(1, len(close))]
        recent = deltas[-14:] if len(deltas) >= 14 else deltas
        gains = [max(d, 0.0) for d in recent]
        losses = [abs(min(d, 0.0)) for d in recent]
        avg_gain = sum(gains) / len(gains) if gains else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        if avg_loss == 0:
            rsi = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        trs = []
        for i in range(1, len(rows)):
            trs.append(max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            ))
        atr = sum(trs[-14:]) / min(14, len(trs)) if trs else max(price * DEFAULT_ATR_PCT, 0.01)

        ema_fast = _ema_values(close, 20)[-1]
        ema_slow = _ema_values(close, 50)[-1]
        typical = [(high[i] + low[i] + close[i]) / 3 for i in range(len(rows))]
        vol_sum = sum(volume)
        vwap_proxy = sum(typical[i] * volume[i] for i in range(len(rows))) / vol_sum if vol_sum else sum(typical) / len(typical)
        trend_green = price > ema_fast > ema_slow and price > vwap_proxy

        return TechnicalSnapshot(
            price=price,
            rsi=round(rsi, 2),
            ema_fast=round(ema_fast, 2),
            ema_slow=round(ema_slow, 2),
            supertrend_trend="green" if trend_green else "red",
            vwap=round(vwap_proxy, 2),
            atr=round(atr, 2),
        )
    except Exception as e:
        log.warning(f"Yahoo technical fallback failed for {symbol}: {e}")
        return None


def yfinance_technical_provider(symbol: str) -> Optional[TechnicalSnapshot]:
    """
    Build a TechnicalSnapshot from yfinance intraday bars.
    Equity mode uses 5m NSE bars and returns enough trend fields for the
    scanner to avoid buying merely because RSI is high.
    """
    if symbol in _unavailable_symbols():
        return None
    yf = _import_yfinance()
    if yf is None:
        return _yahoo_technical_provider(symbol)
    if not breaker.check():
        return None
    ticker = WATCHLIST.get(symbol, symbol)
    try:
        h = yf.Ticker(ticker).history(period="1d", interval="5m")
        if h.empty or len(h) < 15:
            breaker.record_failure(f"thin history {symbol}")
            return None
        breaker.record_success()
        import pandas as pd
        close = h["Close"]
        high  = h["High"]
        low   = h["Low"]
        price = round(float(close.iloc[-1]), 4)

        # RSI(14)
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, float("nan"))
        rsi   = float((100 - 100 / (1 + rs)).iloc[-1])

        # ATR(14)
        tr = pd.concat([
            (high - low),
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])

        # VWAP-ish proxy: cumulative price-weighted mean for the session
        typical = (high + low + close) / 3
        vwap_proxy = float(((typical * h["Volume"]).cumsum()
                            / h["Volume"].cumsum().replace(0, float("nan"))).iloc[-1])
        ema_fast = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_slow = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        trend_green = price > ema_fast > ema_slow and price > vwap_proxy

        return TechnicalSnapshot(
            price=price,
            rsi=round(rsi, 2) if rsi == rsi else None,
            ema_fast=round(ema_fast, 2) if ema_fast == ema_fast else None,
            ema_slow=round(ema_slow, 2) if ema_slow == ema_slow else None,
            supertrend_trend="green" if trend_green else "red",
            vwap=round(vwap_proxy, 2) if vwap_proxy == vwap_proxy else None,
            atr=round(atr, 2) if atr == atr else None,
        )
    except Exception as e:
        breaker.record_failure(str(e))
        log.warning(f"technical fetch failed for {symbol}: {e}")
        return _yahoo_technical_provider(symbol)


def _chart_time(ts) -> int:
    raw_ts = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    if raw_ts.tzinfo is None:
        from datetime import timezone as _tz
        raw_ts = raw_ts.replace(tzinfo=_tz.utc)
    return int(raw_ts.timestamp())


def _round_price(value, digits: int = 4):
    try:
        value = float(value)
        if value != value:
            return None
        return round(value, digits)
    except Exception:
        return None


def _rsi_latest(close) -> Optional[float]:
    if close is None or len(close) < 15:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = _round_price((100 - 100 / (1 + rs)).iloc[-1], 2)
    if rsi is None:
        # Monotonic up/down runs can make the denominator zero.
        return 100.0 if float(gain.iloc[-1] or 0) > 0 else 0.0
    return rsi


def _line_points(series, limit: int) -> list[dict]:
    points = []
    for ts, value in series.tail(limit).items():
        rounded = _round_price(value)
        if rounded is not None:
            points.append({"time": _chart_time(ts), "value": rounded})
    return points


def _mtf_row(label: str, frame) -> dict:
    if frame is None or frame.empty or "Close" not in frame:
        return {"tf": label, "bias": "NO DATA", "rsi": "", "ema_fast": "", "ema_slow": ""}
    close = frame["Close"].dropna()
    if len(close) < 8:
        return {"tf": label, "bias": "THIN", "rsi": "", "ema_fast": "", "ema_slow": ""}
    ema_fast = close.ewm(span=20, adjust=False).mean()
    ema_slow = close.ewm(span=50, adjust=False).mean()
    last = float(close.iloc[-1])
    fast = float(ema_fast.iloc[-1])
    slow = float(ema_slow.iloc[-1])
    rsi = _rsi_latest(close)
    if last > fast > slow and (rsi is None or rsi >= 50):
        bias = "BULL"
    elif last < fast < slow and (rsi is None or rsi <= 50):
        bias = "BEAR"
    else:
        bias = "MIXED"
    return {
        "tf": label, "bias": bias, "rsi": rsi if rsi is not None else "",
        "ema_fast": _round_price(fast), "ema_slow": _round_price(slow),
    }


def yfinance_chart_payload(symbol: str, limit: int = 220) -> dict:
    """
    Build the local Live Coach visual payload.

    This replaces the Pine dependency: OHLC candles, EMA overlays,
    support/resistance, SL/TP reference bands, breakout markers, and
    multi-timeframe rows are all computed locally from yfinance data.
    """
    empty = {
        "chart_series": [], "candles": [], "ema20": [], "ema50": [],
        "ema200": [], "support_line": [], "resistance_line": [],
        "price_lines": [], "markers": [], "mtf": [],
    }
    if symbol in _unavailable_symbols():
        return empty
    yf = _import_yfinance()
    if yf is None:
        return empty

    ticker = WATCHLIST.get(symbol, symbol)
    try:
        import pandas as pd

        h = yf.Ticker(ticker).history(period="7d", interval="5m")
        if h is None or h.empty:
            return empty
        h = h.dropna(subset=["Open", "High", "Low", "Close"]).tail(limit)
        if h.empty:
            return empty

        close = h["Close"]
        high = h["High"]
        low = h["Low"]
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema200 = close.ewm(span=200, adjust=False).mean()

        candles = []
        chart_series = []
        for ts, row in h.iterrows():
            t = _chart_time(ts)
            candles.append({
                "time": t,
                "open": _round_price(row["Open"]),
                "high": _round_price(row["High"]),
                "low": _round_price(row["Low"]),
                "close": _round_price(row["Close"]),
            })
            chart_series.append({"time": t, "value": _round_price(row["Close"])})

        last_time = candles[-1]["time"]
        first_time = candles[0]["time"]
        last_close = float(close.iloc[-1])
        recent_high = float(high.tail(60).max())
        recent_low = float(low.tail(60).min())

        tr = pd.concat([
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        if atr != atr or atr <= 0:
            atr = last_close * DEFAULT_ATR_PCT

        markers = []
        if len(close) > 30:
            prior_high = float(high.iloc[-31:-1].max())
            prior_low = float(low.iloc[-31:-1].min())
            if last_close > prior_high:
                markers.append({
                    "time": last_time, "position": "aboveBar",
                    "color": "#3fb950", "shape": "arrowUp",
                    "text": "BO",
                })
            elif last_close < prior_low:
                markers.append({
                    "time": last_time, "position": "belowBar",
                    "color": "#f85149", "shape": "arrowDown",
                    "text": "BD",
                })
            elif (prior_high - prior_low) / max(last_close, 1e-9) < 0.035:
                markers.append({
                    "time": last_time, "position": "belowBar",
                    "color": "#d29922", "shape": "circle",
                    "text": "TRI",
                })

        mtf = [_mtf_row("5m", h)]
        for label, rule in (("15m", "15min"), ("1h", "1h"),
                            ("4h", "4h"), ("1D", "1D")):
            try:
                agg = h.resample(rule).agg({
                    "Open": "first", "High": "max",
                    "Low": "min", "Close": "last",
                }).dropna()
                mtf.append(_mtf_row(label, agg))
            except Exception:
                mtf.append(_mtf_row(label, None))

        return {
            "chart_series": chart_series,
            "candles": candles,
            "ema20": _line_points(ema20, limit),
            "ema50": _line_points(ema50, limit),
            "ema200": _line_points(ema200, limit),
            "support_line": [
                {"time": first_time, "value": _round_price(recent_low)},
                {"time": last_time, "value": _round_price(recent_low)},
            ],
            "resistance_line": [
                {"time": first_time, "value": _round_price(recent_high)},
                {"time": last_time, "value": _round_price(recent_high)},
            ],
            "price_lines": [
                {"price": _round_price(last_close), "color": "#58a6ff", "title": "LAST"},
                {"price": _round_price(last_close - 2.0 * atr), "color": "#f85149", "title": "ATR SL"},
                {"price": _round_price(last_close + 3.0 * atr), "color": "#3fb950", "title": "ATR TP"},
            ],
            "markers": markers,
            "mtf": mtf,
        }
    except Exception as e:
        log.warning(f"chart payload failed for {symbol}: {e}")
        return empty


def yfinance_chart_series(symbol: str, limit: int = 160) -> list[dict]:
    """Backward-compatible close-line series wrapper."""
    return yfinance_chart_payload(symbol, limit=limit).get("chart_series", [])


class YFinanceResearchProvider(NeutralResearchProvider):
    """
    Closed-market-safe research provider.

    It reads daily historical data and lightweight ticker metadata, so it can
    refresh research snapshots after NSE closes without approving any trade.
    """
    def fetch(self, symbol: str, asof: date) -> dict:
        yf = _import_yfinance()
        if yf is None:
            return _yahoo_research_source(symbol, asof)
        ticker = WATCHLIST.get(symbol, symbol)
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="6mo", interval="1d")
            closes = hist["Close"].dropna() if hist is not None and not hist.empty else []
            volume = hist["Volume"].dropna() if hist is not None and not hist.empty and "Volume" in hist else []
            last = float(closes.iloc[-1]) if len(closes) else None
            sma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else None
            sma50 = float(closes.tail(50).mean()) if len(closes) >= 50 else None
            ret20 = ((last / float(closes.iloc[-21])) - 1.0) if last and len(closes) >= 21 and float(closes.iloc[-21]) else 0.0
            avg_volume = float(volume.tail(20).mean()) if len(volume) else 0.0
            trend_ok = bool(last and sma20 and last > sma20 and (sma50 is None or sma20 >= sma50))
            fundamentals_score = 0.62 if trend_ok else 0.48
            sentiment_score = max(0.0, min(1.0, 0.5 + ret20))
            liquidity_score = max(0.0, min(1.0, avg_volume / 2_000_000)) if avg_volume else 0.5
            return {
                "provider": "yfinance_closed_market_research",
                "symbol": symbol,
                "ticker": ticker,
                "asof": asof.isoformat(),
                "last_close": round(last, 4) if last else None,
                "sma20": round(sma20, 4) if sma20 else None,
                "sma50": round(sma50, 4) if sma50 else None,
                "return_20d": round(ret20, 4),
                "avg_volume_20d": round(avg_volume, 2),
                "fundamentals_raw": fundamentals_score,
                "sentiment_raw": sentiment_score,
                "liquidity_raw": liquidity_score,
            }
        except Exception as e:
            log.warning(f"research fetch failed for {symbol}: {e}")
            return _yahoo_research_source(symbol, asof)


def _gather_prices(pf: Portfolio) -> dict:
    """Best-effort price snapshot for dashboard rendering. Never raises."""
    prices = {}
    for sym in pf.state.positions:
        try:
            q = yfinance_quote_provider(sym)
            if q is not None and q.is_usable:
                prices[sym] = q.price
        except Exception as e:
            log.warning(f"price gather failed for {sym}: {e}")
    return prices


def _refresh_dashboard(pf: Portfolio, *, prices: Optional[dict] = None) -> None:
    """
    Refresh the Excel dashboard. Never raises — observational only.
    Caller may pass a pre-gathered prices dict to avoid duplicate quote fetches.
    """
    try:
        day_start = get_day_start_equity(pf)
    except Exception:
        day_start = pf.state.cash
    if prices is None:
        prices = _gather_prices(pf)
    try:
        trades = get_all_trades()
    except Exception:
        trades = []
    tail = read_monitor_log_tail(MONITOR_LOG_PATH, n=50)
    hb_tail = read_monitor_log_tail(LOG_DIR / "heartbeat.log", n=20)

    # Mode banner for the Summary tab
    last_hb = load_state("last_heartbeat") or {}
    mode_info = {
        "mode":               f"{CFG.asset.asset_class}-{CFG.asset.quote_currency} paper",
        "asset_class":        CFG.asset.asset_class,
        "quote_currency":     CFG.asset.quote_currency,
        "market_hours_24x7":  CFG.market.market_hours_24x7,
        "last_heartbeat":     last_hb.get("ts", "n/a"),
        "tv_launch_status":   load_state("tv_launch_status") or "n/a",
        "unavailable_symbols": sorted(_unavailable_symbols()),
        "paper_budget_inr":    _paper_budget_cap(),
    }
    try:
        from dataclasses import asdict as _asdict
        learner_profile = _asdict(load_profile())
    except Exception:
        learner_profile = {}

    try:
        result = export_dashboard(
            DEFAULT_DASHBOARD_PATH,
            portfolio=pf, risk_cfg=_effective_risk_cfg(),
            day_start_equity=day_start, prices=prices,
            trades=trades, monitor_log_tail=tail,
            mode_info=mode_info, learner_profile=learner_profile,
            heartbeat_tail=hb_tail,
        )
        if result.used_fallback:
            log.warning(f"dashboard fallback used: {result.written_path} "
                        f"({result.fallback_reason})")
    except Exception as e:
        log.warning(f"dashboard refresh skipped: {e}")


def get_day_start_equity(pf: Portfolio) -> float:
    """
    Return today's day-start equity. Initializes once per IST date and
    persists in bot_state under key 'day_start_equity'.
    """
    today = _today_ist_key()
    raw = load_state("day_start_equity")
    if isinstance(raw, dict) and raw.get("date") == today:
        return float(raw["equity"])
    # New day — snapshot equity and persist
    equity = _current_equity_best_effort(pf)
    save_state("day_start_equity", {"date": today, "equity": equity})
    log.info(f"day_start_equity initialized for {today}: Rs.{equity:,.2f}")
    return equity


# ── Trade logging ────────────────────────────────────────────────────────────
def _log_trade_row(row: dict) -> None:
    db_log_trade(row)
    # CSV mirror
    import csv
    tf = BASE_DIR / "trades.csv"
    exists = tf.exists()
    with open(tf, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)


def _record_buy(symbol: str, result: BuyResult, pf: Portfolio) -> None:
    fill = result.fill
    pos  = result.position
    strategy = _selected_strategy()
    _log_trade_row({
        "ts":             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol":         symbol,
        "action":         "BUY",
        "price":          fill.fill_price,
        "qty":            fill.qty,
        "value":          round(fill.fill_price * fill.qty, 2),
        "charges":        fill.charges.total,
        "stop":           pos.stop,
        "target":         pos.target,
        "pnl":            None,
        "balance_after":  pf.state.cash,
        "entry_reason":   f"MANUAL strategy={strategy}",
        "exit_reason":    None,
        "signal_snapshot": json.dumps({"active_strategy": strategy, "source": "manual"}, default=str),
        "slippage":       fill.total_slippage,
        "equity_after":   None,
    })


def _record_sell(symbol: str, result: SellResult, pf: Portfolio,
                 stop: Optional[float], target: Optional[float]) -> None:
    fill = result.fill
    _log_trade_row({
        "ts":             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol":         symbol,
        "action":         "SELL",
        "price":          fill.fill_price,
        "qty":            fill.qty,
        "value":          round(fill.fill_price * fill.qty, 2),
        "charges":        fill.charges.total,
        "stop":           stop,
        "target":         target,
        "pnl":            result.net_pnl,
        "balance_after":  pf.state.cash,
        "entry_reason":   None,
        "exit_reason":    result.exit_reason,
        "signal_snapshot": None,
        "slippage":       fill.total_slippage,
        "equity_after":   None,
    })


# ── Command handlers ─────────────────────────────────────────────────────────
def print_status(pf: Portfolio) -> None:
    state = control.read_state()
    print("\n" + "-" * 54)
    print(f"  Balance      : Rs.{pf.state.cash:>10,.2f}")
    print(f"  Total Trades : {pf.state.total_trades}")
    if pf.state.total_trades > 0:
        print(f"  Win Rate     : {pf.win_rate_pct:.1f}%")
        print(f"  Realized P&L : Rs.{pf.state.realized_pnl:>+10,.2f}")
    if pf.state.positions:
        for sym, pos in pf.state.positions.items():
            print(f"  OPEN: {sym} | qty={pos.qty} | entry=Rs.{pos.entry_price} "
                  f"| stop=Rs.{pos.stop} | target=Rs.{pos.target}")
    else:
        print("  No open positions")
    summary = get_pnl_summary()
    if summary.get("total_trades"):
        print(f"  All-time: {summary['total_trades']} trades | "
              f"W:{summary['wins'] or 0} L:{summary['losses'] or 0} | "
              f"Rs.{summary['total_pnl']:+,.2f}")
    print(f"  Mode         : {CFG.asset.asset_class}-{CFG.asset.quote_currency} "
          f"(24x7={CFG.market.market_hours_24x7}, broker={CFG.fees.broker})")
    print(f"  Control      : killed={state.killed} paused={state.paused}")
    if state.killed:
        print(f"    kill: {state.kill_reason} @ {state.killed_at}")
    if state.paused:
        print(f"    pause: {state.pause_reason} @ {state.paused_at}")
    unavail = _unavailable_symbols()
    if unavail:
        print(f"  Unavailable  : {sorted(unavail)}")
    print("-" * 54)
    _refresh_dashboard(pf)


def print_help() -> None:
    print("""
  Trading:
    buy SYMBOL          place a paper BUY (gated by caps + kill + pause)
    sell SYMBOL         manual paper SELL (never gated)
    flatten             close ALL positions immediately (never gated)
    monitor-once        one auto-exit pass for stop/target hits
    research-once       refresh closed-market research cache (no orders)
    scan-once           one signal-only scan (no orders) — logs candidates
    auto-buy-once       try paper auto-buys for current candidates (gated)
    run-all             NSE equity supervisor loop (monitor + scan + auto-buy + dashboard)
                        --max-loops N : run only N iterations (for testing)
    brain-status        show learner profile + capital governor decision
    strategy-run-once   backtest every backend strategy once
    strategy-status     show tournament leaderboard + active champion
    runtime-audit       prove no LLM-vendor runtime dependency (Phase K)
    install-windows     create venv + install deps + write desktop .bat files
    refresh-coach-assets refresh local Live Coach assets
    open-chart [SYMBOL] open TradingView on active / selected NSE chart
    open-charts [N]    open top N active NSE charts (default 3)

  Control:
    kill <reason>       trip kill switch (blocks new BUYs, persists across restarts)
    unkill              clear kill switch
    pause <reason>      pause new BUYs (cleared by resume)
    resume              clear pause

  Info:
    status              portfolio + control state
    healthcheck         verify imports, DB, control file, portfolio, quote provider
    price SYMBOL        fetch a quote
    watchlist           list known symbols
    trades / logs       show file paths
    help                this message
    quit                exit interactive shell

  Symbols (NSE): RELIANCE TCS INFY HDFCBANK ICICIBANK SBIN LT AXISBANK
                 KOTAKBANK ITC BHARTIARTL HINDUNILVR MARUTI TITAN
""")


def cmd_buy(symbol: str, pf: Portfolio) -> None:
    if symbol not in WATCHLIST:
        print(f"  {symbol} not in watchlist."); return
    if symbol in pf.state.positions:
        print(f"  BUY rejected: already holding {symbol}")
        log.info(f"BUY {symbol} rejected: already holding")
        return
    day_start = get_day_start_equity(pf)
    quote = yfinance_quote_provider(symbol)
    if quote is None or not quote.is_usable:
        reason = quote.reject_reason if quote else "no quote"
        print(f"  BUY rejected: {reason}")
        return
    result = do_buy(
        symbol, pf, yfinance_quote_provider,
        day_start_equity=day_start,
        risk_cfg=_effective_risk_cfg(), indi_cfg=CFG.indicators, fee_cfg=CFG.fees,
        atr=DEFAULT_ATR_PCT * quote.price,
        product=PRODUCT,
    )
    if result.rejected:
        print(f"  BUY rejected: {'; '.join(result.reasons)}")
        log.info(f"BUY {symbol} rejected: {result.reasons}")
        return
    save_portfolio(pf)
    _record_buy(symbol, result, pf)
    fill = result.fill
    print(f"\n  BUY {symbol} @ Rs.{fill.fill_price} | qty={fill.qty} "
          f"| stop=Rs.{result.position.stop} | target=Rs.{result.position.target} "
          f"| cash=Rs.{pf.state.cash:,.2f}")
    log.info(f"BUY {symbol} @ Rs.{fill.fill_price} qty={fill.qty}")
    _refresh_dashboard(pf, prices={symbol: quote.price})


def cmd_sell(symbol: str, pf: Portfolio, exit_reason: str = "MANUAL") -> None:
    pos = pf.state.positions.get(symbol)
    if pos is None:
        print(f"  No position in {symbol}."); return
    stop, target = pos.stop, pos.target
    result = do_sell(symbol, pf, yfinance_quote_provider,
                     fee_cfg=CFG.fees, product=PRODUCT, exit_reason=exit_reason)
    if result.rejected:
        print(f"  SELL rejected: {'; '.join(result.reasons)}")
        return
    save_portfolio(pf)
    _record_sell(symbol, result, pf, stop, target)
    print(f"\n  SELL {symbol} @ Rs.{result.fill.fill_price} "
          f"| net P&L=Rs.{result.net_pnl:+,.2f} | cash=Rs.{pf.state.cash:,.2f} "
          f"| reason={exit_reason}")
    log.info(f"SELL {symbol} @ Rs.{result.fill.fill_price} net=Rs.{result.net_pnl:+,.2f}")
    _refresh_dashboard(pf)


def cmd_flatten(pf: Portfolio) -> None:
    if not pf.state.positions:
        print("  No open positions to flatten."); return
    snapshot = {sym: (pos.stop, pos.target) for sym, pos in pf.state.positions.items()}
    results = do_flatten(pf, yfinance_quote_provider, fee_cfg=CFG.fees, product=PRODUCT)
    save_portfolio(pf)
    for r in results:
        sym = r.fill.symbol if r.fill else "?"
        if r.rejected:
            print(f"  FLATTEN {sym}: REJECTED — {'; '.join(r.reasons)}")
            log.warning(f"FLATTEN {sym} rejected: {r.reasons}")
            continue
        stop, target = snapshot.get(r.fill.symbol, (None, None))
        _record_sell(r.fill.symbol, r, pf, stop, target)
        print(f"  FLATTEN {sym} @ Rs.{r.fill.fill_price} net=Rs.{r.net_pnl:+,.2f}")
        log.info(f"FLATTEN {sym} @ Rs.{r.fill.fill_price} net=Rs.{r.net_pnl:+,.2f}")
    _refresh_dashboard(pf)


def cmd_monitor_once(pf: Portfolio) -> int:
    """Returns count of successful exits — useful for scheduler health checks."""
    if not pf.state.positions:
        print("  monitor-once: no open positions")
        _refresh_dashboard(pf, prices={})
        return 0
    snapshot = {sym: (pos.stop, pos.target) for sym, pos in pf.state.positions.items()}
    results = do_monitor_once(pf, yfinance_quote_provider, fee_cfg=CFG.fees, product=PRODUCT)
    save_portfolio(pf)
    exits = 0
    for r in results:
        if r.rejected:
            print(f"  monitor-once: {r.exit_reason} — {'; '.join(r.reasons)}")
            log.warning(f"monitor-once rejected: {r.reasons}")
            continue
        stop, target = snapshot.get(r.fill.symbol, (None, None))
        _record_sell(r.fill.symbol, r, pf, stop, target)
        exits += 1
        print(f"  monitor-once: {r.exit_reason} {r.fill.symbol} "
              f"@ Rs.{r.fill.fill_price} net=Rs.{r.net_pnl:+,.2f}")
        log.info(f"AUTO-EXIT {r.exit_reason} {r.fill.symbol} "
                 f"@ Rs.{r.fill.fill_price} net=Rs.{r.net_pnl:+,.2f}")
    if exits == 0 and all(not r.rejected for r in results):
        print("  monitor-once: nothing to exit (inside band)")
    _refresh_dashboard(pf)
    return exits


def cmd_kill(reason: str) -> None:
    state = control.kill(reason)
    print(f"  KILL switch tripped: {state.kill_reason} (at {state.killed_at})")
    log.warning(f"KILL: {reason}")


def cmd_unkill() -> None:
    control.unkill()
    print("  KILL switch cleared")
    log.info("KILL cleared")


def cmd_pause(reason: str) -> None:
    state = control.pause(reason)
    print(f"  PAUSED: {state.pause_reason} (at {state.paused_at})")
    log.info(f"PAUSE: {reason}")


def cmd_resume() -> None:
    control.resume()
    print("  PAUSE cleared")
    log.info("PAUSE cleared")


# ── Scan-once (SIGNAL-ONLY — never places orders) ───────────────────────────
def cmd_scan_once(pf: Portfolio) -> int:
    """
    One signal-only scan across the watchlist. Generates and logs candidates;
    NEVER executes a BUY or SELL. Returns count of BUY_CANDIDATE signals.
    """
    day_start = get_day_start_equity(pf)
    available = [s for s in WATCHLIST.keys() if s not in _unavailable_symbols()]
    candidates = scan_once(
        portfolio=pf, watchlist=available,
        technical_provider=yfinance_technical_provider,
        research_provider=YFinanceResearchProvider(),
        risk_cfg=_effective_risk_cfg(), indi_cfg=CFG.indicators, fee_cfg=CFG.fees,
        day_start_equity=day_start, product=PRODUCT,
    )
    buy_count = sum(1 for c in candidates if c.signal.value == "BUY_CANDIDATE")
    print(f"\n  scan-once: {len(candidates)} candidates "
          f"(BUY={buy_count} REJECTED={sum(1 for c in candidates if c.signal.value=='REJECTED')})")
    for c in candidates:
        marker = "*" if c.signal.value == "BUY_CANDIDATE" else " "
        block  = "[BLOCKED]" if c.entry_blocked else ""
        print(f"  {marker} {c.symbol:<10} {c.signal.value:<16} "
              f"total={c.scores.total:.2f} tech={c.scores.technical:.2f} {block}")
    log.info(f"scan-once: {len(candidates)} candidates logged "
             f"(BUY_CANDIDATE={buy_count})")
    _refresh_dashboard(pf)
    return buy_count


# ── Auto-buy-once (paper only, gated) ───────────────────────────────────────
def cmd_research_once() -> int:
    """
    Refresh daily research snapshots even when NSE is closed.

    This is analysis-only. It does not call the quote validator and cannot place
    any order; auto-buy still requires a fresh usable market-hours quote.
    """
    asof = now_ist().date()
    provider = YFinanceResearchProvider()
    refreshed = 0
    for symbol in WATCHLIST:
        if symbol in _unavailable_symbols():
            continue
        get_or_fetch(symbol, asof, provider)
        refreshed += 1
    rows = list_snapshots_for_date(asof)
    print(f"\n  research-once: {refreshed} symbols checked for {asof.isoformat()}")
    for row in rows[:20]:
        print(f"  {row['symbol']:<10} fund={row['fundamentals_score']:.2f} "
              f"sent={row['sentiment_score']:.2f} liq={row['liquidity_score']:.2f}")
    if len(rows) > 20:
        print(f"  ... {len(rows) - 20} more cached snapshots")
    return refreshed


def cmd_auto_buy_once(pf: Portfolio) -> int:
    """
    One pass: scan, then run auto-buy on resulting candidates.
    All gates from supervisor.auto_buy_once apply (cooldown, freshness,
    score threshold, control state, risk caps).
    """
    day_start = get_day_start_equity(pf)
    available = [s for s in WATCHLIST.keys() if s not in _unavailable_symbols()]
    candidates = scan_once(
        portfolio=pf, watchlist=available,
        technical_provider=yfinance_technical_provider,
        research_provider=YFinanceResearchProvider(),
        risk_cfg=_effective_risk_cfg(), indi_cfg=CFG.indicators, fee_cfg=CFG.fees,
        day_start_equity=day_start, product=PRODUCT,
    )
    decisions = auto_buy_once(
        candidates=candidates, portfolio=pf,
        quote_provider=yfinance_quote_provider,
        risk_cfg=_effective_risk_cfg(), indi_cfg=CFG.indicators, fee_cfg=CFG.fees,
        sup_cfg=CFG.supervisor, day_start_equity=day_start,
        product=PRODUCT,
    )
    save_portfolio(pf)
    placed = sum(1 for d in decisions if d.placed)
    print(f"\n  auto-buy-once: {placed} paper BUY(s) placed, "
          f"{len(decisions) - placed} rejected/skipped")
    for d in decisions:
        marker = "+" if d.placed else "-"
        print(f"  {marker} {d.symbol:<10} {d.reason}")
    _refresh_dashboard(pf)
    return placed


def _capture_command(fn, *args, **kwargs) -> str:
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue().strip()


def start_terminal_server() -> str:
    """
    Start the phone/desktop web terminal server once.

    The static file works as a display, but real BUY/SELL buttons require this
    local HTTP server. It is token-protected and calls the same paper command
    handlers used by the desktop CLI.
    """
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse

    token = _terminal_token()
    base_url = _terminal_base_url()
    save_state("terminal_base_url", base_url)

    class TerminalHandler(BaseHTTPRequestHandler):
        server_version = "KiteBotTerminal/1.0"

        def log_message(self, fmt, *args):
            log.info("terminal: " + fmt, *args)

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-KiteBot-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            supplied = self.headers.get("X-KiteBot-Token", "")
            if supplied == token:
                return True
            cookie = self.headers.get("Cookie", "")
            return any(part.strip() == f"kb_token={token}" for part in cookie.split(";"))

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload, default=str).encode("utf-8"), "application/json")

        def do_OPTIONS(self):
            self._send(204, b"", "text/plain")

        def do_GET(self):
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            try:
                if path in ("/", "/terminal", "/index.html"):
                    query_token = (parse_qs(parsed_url.query).get("token") or [""])[0]
                    body = (CONTROL_DIR / "KiteBot-Live-Coach.html").read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    if query_token == token:
                        self.send_header("Set-Cookie", f"kb_token={token}; Path=/; SameSite=Lax")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path in ("/live-coach.json", "/api/state"):
                    self._send(200, (CONTROL_DIR / "live-coach.json").read_bytes(), "application/json")
                    return
                self._json(404, {"ok": False, "error": "not found"})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})

        def do_POST(self):
            path = urlparse(self.path).path
            if not self._authorized():
                self._json(403, {"ok": False, "error": "not paired; open PHONE_TERMINAL_URL.txt first"})
                return
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                payload = {}
            raw_symbol = str(payload.get("symbol") or "")
            symbol = raw_symbol.upper()
            reason = str(payload.get("reason") or "phone/manual")

            try:
                init_db()
                pf = load_portfolio()
                if path == "/api/buy":
                    if not symbol:
                        self._json(400, {"ok": False, "error": "symbol required"})
                        return
                    out = _capture_command(cmd_buy, symbol, pf)
                elif path == "/api/sell":
                    if not symbol:
                        self._json(400, {"ok": False, "error": "symbol required"})
                        return
                    out = _capture_command(cmd_sell, symbol, pf, f"PHONE:{reason}")
                elif path == "/api/flatten":
                    out = _capture_command(cmd_flatten, pf)
                elif path == "/api/pause":
                    out = _capture_command(cmd_pause, f"PHONE:{reason}")
                elif path == "/api/resume":
                    out = _capture_command(cmd_resume)
                elif path == "/api/scan":
                    out = _capture_command(cmd_scan_once, pf)
                elif path == "/api/auto-buy":
                    out = _capture_command(cmd_auto_buy_once, pf)
                elif path == "/api/allow-symbol":
                    if not symbol:
                        self._json(400, {"ok": False, "error": "symbol required"})
                        return
                    if symbol not in WATCHLIST:
                        self._json(400, {"ok": False, "error": f"{symbol} is not in the NSE watchlist"})
                        return
                    allowed = load_state("allowed_symbols", [])
                    if symbol not in allowed:
                        allowed.append(symbol)
                    save_state("allowed_symbols", sorted(set(allowed)))
                    out = f"{symbol} allowed for bot focus"
                elif path == "/api/apply-strategy":
                    strategy_id = raw_symbol or str(payload.get("strategy") or "")
                    valid = {s["id"] for s in STRATEGY_CATALOG}
                    if strategy_id not in valid:
                        self._json(400, {"ok": False, "error": "unknown strategy"})
                        return
                    save_state("selected_strategy", strategy_id)
                    out = f"strategy applied: {_strategy_label(strategy_id)}"
                elif path == "/api/set-capital":
                    try:
                        amount = float(payload.get("amount"))
                    except Exception:
                        self._json(400, {"ok": False, "error": "amount required"})
                        return
                    if amount < 5000 or amount > MAX_OPERATOR_BUDGET_INR:
                        self._json(
                            400,
                            {
                                "ok": False,
                                "error": f"capital must be between Rs.5,000 and Rs.{MAX_OPERATOR_BUDGET_INR:,.0f}",
                            },
                        )
                        return
                    save_state("paper_budget_inr", round(amount, 2))
                    out = f"capital cap set to Rs.{amount:,.2f}"
                else:
                    self._json(404, {"ok": False, "error": "not found"})
                    return
                fresh = load_portfolio()
                _refresh_dashboard(fresh)
                _refresh_live_coach(fresh, _gather_prices(fresh))
                self._json(200, {"ok": True, "message": out or "done"})
            except Exception as e:
                log.exception("terminal action failed")
                self._json(500, {"ok": False, "error": str(e)})

    try:
        server = ThreadingHTTPServer(("0.0.0.0", TERMINAL_PORT), TerminalHandler)
    except OSError as e:
        log.warning(f"terminal server not started: {e}")
        return base_url

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    (CONTROL_DIR / "PHONE_TERMINAL_URL.txt").write_text(
        f"{base_url}/?token={token}\nOpen this URL on your phone while the bot is running.\n",
        encoding="utf-8",
    )
    log.info(f"terminal server started at {base_url}")
    return base_url


# ── Run-all supervisor (24/7 paper loop) ─────────────────────────────────────
def cmd_run_all(max_loops: Optional[int] = None) -> None:
    """
    Long-running supervisor. Loops until Ctrl+C (or `max_loops` if provided).
    Paper only — calls do_buy/do_sell/do_monitor_once; never live broker orders.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # Idempotently ensure visual coach assets exist on disk
    assets = ensure_coach_assets()
    if not load_state("tv_launch_status"):
        save_state("tv_launch_status", "coach assets ready")
    terminal_url = start_terminal_server()
    run_cfg = _effective_config()

    print(f"\n  run-all: starting paper supervisor loop")
    print(f"    mode    : {CFG.asset.asset_class}-{CFG.asset.quote_currency} "
          f"(24x7={CFG.market.market_hours_24x7})")
    print(f"    tickers : {sorted(set(WATCHLIST) - _unavailable_symbols())}")
    print(f"    budget  : Rs.{_paper_budget_cap():,.2f} max operator paper capital")
    print(f"    cadence : monitor={run_cfg.supervisor.monitor_interval_sec}s "
          f"scan={run_cfg.supervisor.scan_interval_sec}s "
          f"autobuy={run_cfg.supervisor.auto_buy_interval_sec}s "
          f"dashboard={run_cfg.supervisor.dashboard_interval_sec}s")
    print(f"    logs    : {LOG_DIR}")
    print(f"    coach   : html={assets['html'].name} (Pine not required)")
    print(f"    phone   : {terminal_url}  (see PHONE_TERMINAL_URL.txt for pairing URL)")
    print(f"    champion: {active_champion() or '(none — tournament will run)'}")
    if max_loops is not None:
        print(f"    LIMITED : will exit after {max_loops} iterations")
    print(f"    Press Ctrl+C to stop gracefully\n")
    log.info(f"run-all started (max_loops={max_loops})")

    def _dashboard_refresh(pf, prices):
        # Refresh both Excel dashboard AND live-coach.json on every dashboard tick
        _refresh_dashboard(pf, prices=prices)
        _refresh_live_coach(pf, prices)

    def _watchlist_loader():
        return [s for s in WATCHLIST.keys() if s not in _unavailable_symbols()]

    final_state = run_forever(
        portfolio_loader=load_portfolio,
        save_portfolio=save_portfolio,
        quote_provider=yfinance_quote_provider,
        technical_provider=yfinance_technical_provider,
        research_provider=YFinanceResearchProvider(),
        refresh_dashboard=_dashboard_refresh,
        watchlist_loader=_watchlist_loader,
        cfg=run_cfg,
        day_start_equity_loader=get_day_start_equity,
        log_dir=LOG_DIR,
        tick_seconds=5.0 if max_loops is None else 0.1,    # fast for tests
        product=PRODUCT,
        max_loops=max_loops,
    )
    log.info(f"run-all stopped after {final_state.iterations} iterations, "
             f"errors={final_state.errors}")


def _refresh_live_coach(pf: Portfolio, prices: Optional[dict]) -> None:
    """Write live-coach.json read by the HTML dashboard. Never raises."""
    try:
        from dataclasses import asdict as _asdict
        state = control.read_state()
        if state.killed:
            running = "HALTED"
        elif state.paused:
            running = "PAUSED"
        else:
            running = "RUNNING"
        snap = load_leaderboard()
        decisions = []
        try:
            from bot.scanner import list_recent_candidates
            for c in list_recent_candidates(limit=20):
                block_reason = ""
                raw_reasons = c.get("block_reasons")
                if raw_reasons:
                    try:
                        parsed = json.loads(raw_reasons)
                        block_reason = "; ".join(parsed) if parsed else ""
                    except Exception:
                        block_reason = str(raw_reasons)
                if not block_reason:
                    block_reason = c.get("rejection_reason") or ""
                decisions.append({
                    "ts":     c.get("ts"),
                    "symbol": c.get("symbol"),
                    "signal": c.get("signal"),
                    "score":  round(c.get("total_score", 0.0), 3),
                    "reason": block_reason,
                })
        except Exception:
            pass
        leaderboard_rows = []
        if snap:
            for r in snap.results:
                status = "champion" if r.name == snap.champion \
                         else ("eligible" if r.eligible else r.reason or "ineligible")
                leaderboard_rows.append({
                    "name": r.name, "trades": r.trades,
                    "win_rate": r.win_rate, "profit_factor": r.profit_factor,
                    "max_dd_pct": r.max_dd_pct, "score": r.score,
                    "status": status,
                })
        # Capital governor preview
        decision = governor_assess(risk_cfg=_effective_risk_cfg(), profile=load_profile())
        active_symbol = select_visual_symbol(pf)
        active_score = 0.0
        for d in decisions:
            if d.get("symbol") == active_symbol:
                active_score = float(d.get("score") or 0.0)
                break
        active_pos = pf.state.positions.get(active_symbol)
        visual = yfinance_chart_payload(active_symbol)
        selected_strategy = _selected_strategy()
        try:
            all_trades = get_all_trades()
        except Exception:
            all_trades = []
        position_strategies = _position_strategy_map(all_trades)
        positions_rows = []
        usable_prices = dict(prices or {})
        for sym, pos in pf.state.positions.items():
            last_price = usable_prices.get(sym)
            if last_price is None:
                try:
                    q = yfinance_quote_provider(sym)
                    if q is not None and q.is_usable:
                        last_price = q.price
                        usable_prices[sym] = q.price
                except Exception:
                    last_price = None
            pnl = None
            if last_price is not None:
                pnl = round((float(last_price) - pos.entry_price) * pos.qty, 2)
            positions_rows.append({
                "symbol": sym,
                "exchange": tradingview_symbol_for(sym).split(":", 1)[0],
                "product": PRODUCT,
                "strategy": position_strategies.get(sym, {}).get("strategy") or selected_strategy,
                "qty": round(pos.qty, 8),
                "entry": round(pos.entry_price, 4),
                "last": round(float(last_price), 4) if last_price is not None else "",
                "stop": round(pos.stop, 4),
                "target": round(pos.target, 4),
                "invested": round(pos.qty * pos.entry_price, 2),
                "current_value": round(pos.qty * float(last_price), 2) if last_price is not None else "",
                "value": round(pos.qty * float(last_price), 2) if last_price is not None else "",
                "pnl": pnl if pnl is not None else "",
            })

        unrealized = 0.0
        unrealized_ok = True
        for row in positions_rows:
            if row.get("pnl") == "":
                unrealized_ok = False
                break
            unrealized += float(row.get("pnl") or 0.0)
        gross_exposure = sum(
            float(row.get("value") or row.get("invested") or 0.0)
            for row in positions_rows
        )
        equity = round(pf.state.cash + gross_exposure, 2)
        account = {
            "cash": round(pf.state.cash, 2),
            "equity": equity,
            "realized_pnl": round(pf.state.realized_pnl, 2),
            "unrealized_pnl": round(unrealized, 2) if unrealized_ok else "",
            "gross_exposure": round(gross_exposure, 2),
            "max_budget": getattr(_effective_risk_cfg(), "max_total_notional_inr", None) or CFG.starting_balance,
            "paper_budget": _paper_budget_cap(),
            "currency": "INR",
        }

        latest_by_symbol = {}
        for item in decisions:
            latest_by_symbol.setdefault(item.get("symbol"), item)
        watchlist_rows = []
        for sym in WATCHLIST:
            d = latest_by_symbol.get(sym, {})
            watchlist_rows.append({
                "symbol": sym,
                "exchange": tradingview_symbol_for(sym).split(":", 1)[0],
                "product": PRODUCT,
                "chart_url": tradingview_widget_url_for(sym),
                "tradingview_url": tradingview_url_for(sym),
                "ltp": round(float(usable_prices[sym]), 4) if sym in usable_prices else "",
                "signal": d.get("signal", ""),
                "score": d.get("score", ""),
                "reason": d.get("reason", ""),
            })

        next_buys = sorted(
            [w for w in watchlist_rows if w.get("signal")],
            key=lambda w: float(w.get("score") or 0.0),
            reverse=True,
        )[:8]

        trade_rows = []
        try:
            for row in positions_rows:
                trade_rows.append({
                    "ts": "OPEN",
                    "symbol": row.get("symbol"),
                    "exchange": row.get("exchange"),
                    "action": "OPEN",
                    "qty": row.get("qty"),
                    "price": row.get("entry"),
                    "value": row.get("invested"),
                    "charges": "",
                    "pnl": row.get("pnl"),
                    "stop": row.get("stop"),
                    "target": row.get("target"),
                })
            for t in reversed(all_trades[-40:]):
                trade_rows.append({
                    "ts": t.get("ts"),
                    "symbol": t.get("symbol"),
                    "exchange": tradingview_symbol_for(t.get("symbol", "")).split(":", 1)[0],
                    "action": t.get("action"),
                    "qty": t.get("qty"),
                    "price": t.get("price"),
                    "value": t.get("value"),
                    "charges": t.get("charges"),
                    "pnl": t.get("pnl"),
                    "stop": t.get("stop"),
                    "target": t.get("target"),
                })
        except Exception:
            trade_rows = []
        trade_attribution = _trade_attribution_rows(positions_rows, all_trades)

        price_lines = list(visual.get("price_lines", []))
        if active_pos:
            price_lines.extend([
                {"price": round(active_pos.entry_price, 4), "color": "#58a6ff", "title": "BOT ENTRY"},
                {"price": round(active_pos.stop, 4), "color": "#f85149", "title": "BOT SL"},
                {"price": round(active_pos.target, 4), "color": "#3fb950", "title": "BOT TP"},
            ])
        cs = CoachState(
            running_state=running,
            mode=f"{CFG.asset.asset_class}-{CFG.asset.quote_currency} paper",
            active_symbol=active_symbol,
            tradingview_url=tradingview_url_for(active_symbol),
            tradingview_widget_url=tradingview_widget_url_for(active_symbol),
            active_strategy=selected_strategy,
            capital_tier=decision.tier,
            effective_risk_pct=decision.effective_risk_pct,
            regime="(set by scanner)",
            confidence=active_score,
            stop=(active_pos.stop if active_pos else None),
            target=(active_pos.target if active_pos else None),
            realized_pnl=round(pf.state.realized_pnl, 2),
            open_positions=len(pf.state.positions),
            positions=positions_rows,
            account=account,
            watchlist=watchlist_rows,
            trades=trade_rows,
            indices=_index_rows(),
            holdings=positions_rows,
            trade_attribution=trade_attribution,
            strategy_catalog=STRATEGY_CATALOG,
            brain_notes=_brain_notes(account, trade_attribution),
            allowed_symbols=load_state("allowed_symbols", []),
            bids=BID_ROWS,
            next_buys=next_buys,
            exchange=tradingview_symbol_for(active_symbol).split(":", 1)[0],
            terminal_api_base=load_state("terminal_base_url") or _terminal_base_url(),
            mtf=visual.get("mtf", []),
            decisions=decisions,
            leaderboard=leaderboard_rows,
            chart_series=visual.get("chart_series", []),
            candles=visual.get("candles", []),
            ema20=visual.get("ema20", []),
            ema50=visual.get("ema50", []),
            ema200=visual.get("ema200", []),
            support_line=visual.get("support_line", []),
            resistance_line=visual.get("resistance_line", []),
            price_lines=price_lines,
            markers=visual.get("markers", []),
        )
        update_live_coach_state(cs)
    except Exception as e:
        log.warning(f"live coach update failed: {e}")


# ── Runtime audit (Phase K — proves no Claude dependency at runtime) ────────
def cmd_open_chart(symbol: Optional[str] = None, pf: Optional[Portfolio] = None) -> int:
    """
    Open TradingView on the relevant NSE equity chart.

    Uses a concrete chart URL instead of the bare tradingview: protocol, because
    the bare protocol simply restores whatever the app last showed. TradingView
    remains visual-only; execution stays in the paper ledger.
    """
    symbol = symbol or select_visual_symbol(pf)
    tv_symbol = tradingview_symbol_for(symbol)
    url = tradingview_url_for(symbol)
    try:
        import webbrowser
        opened = webbrowser.open(url, new=1, autoraise=True)
        status = f"opened {symbol} as {tv_symbol}: {url}"
        if not opened:
            status = f"open requested {symbol} as {tv_symbol}: {url}"
        save_state("tv_launch_status", status)
        print(f"  TradingView chart: {symbol} -> {tv_symbol}")
        print(f"  {url}")
        return 0
    except Exception as e:
        status = f"failed to open {symbol} as {tv_symbol}: {e}"
        save_state("tv_launch_status", status)
        log.warning(status)
        print(f"  TradingView launch failed: {e}")
        print(f"  Open manually: {url}")
        return 0


def cmd_open_charts(limit: int = 3, pf: Optional[Portfolio] = None) -> int:
    """Open a small set of active NSE equity charts for visual monitoring."""
    symbols: list[str] = []
    if pf is not None:
        symbols.extend(sorted(pf.state.positions.keys()))
    try:
        ranked = sorted(
            list_recent_candidates(limit=50),
            key=lambda r: float(r.get("total_score") or 0.0),
            reverse=True,
        )
        symbols.extend([r["symbol"] for r in ranked if r.get("symbol") in WATCHLIST])
    except Exception:
        pass
    symbols.extend([s for s in WATCHLIST if s not in _unavailable_symbols()])

    unique = []
    seen = set()
    for sym in symbols:
        if sym not in WATCHLIST or sym in seen or sym in _unavailable_symbols():
            continue
        seen.add(sym)
        unique.append(sym)
        if len(unique) >= limit:
            break
    if not unique:
        unique = [next(iter(WATCHLIST))]

    for sym in unique:
        cmd_open_chart(sym, pf)
    print(f"  Opened/requested {len(unique)} TradingView NSE chart(s): {unique}")
    return 0


def cmd_refresh_coach_assets() -> int:
    """Refresh local Live Coach assets without reinstalling the whole runtime."""
    assets = ensure_coach_assets()
    print("  Coach assets refreshed:")
    for name, path in assets.items():
        print(f"    {name}: {path}")
    return 0


def cmd_install_pine_assets() -> int:
    """Backward-compatible alias. Pine is no longer part of the run path."""
    return cmd_refresh_coach_assets()


def _build_forbidden_tokens() -> tuple:
    """
    Tokens are reconstructed at runtime via string concatenation so this
    source file itself does not contain the literal strings the audit hunts
    for — otherwise the audit would self-trigger.
    """
    a = "anthr" + "opic"
    c = "clau" + "de"
    return (
        a,
        f"{c}_api",
        f"{c}-cli",
        f"{c}.exe",
        f"{c.upper()}_API_KEY",
        f"{a.upper()}_API_KEY",
        f"{c} --",
    )


CLAUDE_FORBIDDEN_TOKENS = _build_forbidden_tokens()


def cmd_runtime_audit() -> int:
    """
    Prove the bot does NOT depend on any LLM-vendor runtime (the two big
    vendors whose tokens we forbid: see CLAUDE_FORBIDDEN_TOKENS).
    Scans:
      - bot/ Python source for forbidden tokens (excluding docs/comments
        about the absence of such deps)
      - paper_engine.py
      - KiteBot-Control/*.bat for shell-outs to the vendor CLI
      - pyproject.toml for vendor SDK packages
      - process environment for API keys
    Returns exit code 0 (clean) or 1 (issues found). Never modifies anything.
    """
    findings: list = []
    pkg_dir = BASE_DIR / "bot"

    def _scan(path: Path, label: str, tokens=CLAUDE_FORBIDDEN_TOKENS):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            findings.append(f"  ?  could not read {label}: {e}")
            return
        lower = text.lower()
        for tok in tokens:
            if tok.lower() in lower:
                findings.append(f"  X  {label}: contains forbidden token {tok!r}")

    # 1. Python source
    for py in pkg_dir.rglob("*.py"):
        _scan(py, f"bot/{py.relative_to(pkg_dir)}")
    _scan(BASE_DIR / "paper_engine.py", "paper_engine.py")

    # 2. Desktop .bat files — scan for bare vendor names too (built at runtime
    #    so this source file does not contain the literal strings).
    bat_tokens = ("clau" + "de", "anthr" + "opic")
    for bat in CONTROL_DIR.glob("*.bat"):
        _scan(bat, f"KiteBot-Control/{bat.name}", tokens=bat_tokens)

    # 3. pyproject deps
    py_toml = BASE_DIR / "pyproject.toml"
    if py_toml.exists():
        text = py_toml.read_text(encoding="utf-8").lower()
        a_tok = "anthr" + "opic"
        c_tok = "clau" + "de"
        for tok in (a_tok, f"{c_tok}-sdk", f"{c_tok}_agent"):
            if tok in text:
                findings.append(f"  X  pyproject.toml lists dep {tok!r}")

    # 4. Process env (warns only — env state is host-specific)
    upper_c = ("CLAU" + "DE").upper()
    upper_a = ("ANTHR" + "OPIC").upper()
    env_keys = [k for k in os.environ
                if upper_c in k.upper() or upper_a in k.upper()]
    if env_keys:
        findings.append(f"  !  env vars present (not used by bot): {env_keys}")

    # 5. Verify the venv python is actually usable
    venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        findings.append(f"  !  venv missing at {venv_py} (run install-windows)")

    print("\n" + "=" * 60)
    print("  Runtime audit — independence from LLM-vendor runtimes")
    print("=" * 60)
    print(f"  scanned bot/ Python files       : {sum(1 for _ in pkg_dir.rglob('*.py'))}")
    print(f"  scanned paper_engine.py         : yes")
    print(f"  scanned .bat files in {CONTROL_DIR.name}/ : "
          f"{sum(1 for _ in CONTROL_DIR.glob('*.bat'))}")
    print(f"  scanned pyproject.toml          : {'yes' if py_toml.exists() else 'no'}")
    print(f"  venv python                     : "
          f"{'OK' if venv_py.exists() else 'MISSING'}")
    print("")
    blockers = [f for f in findings if f.lstrip().startswith("X")]
    warnings = [f for f in findings if not f.lstrip().startswith("X")]
    if blockers:
        print("  BLOCKERS:")
        for f in blockers:
            print(f)
    if warnings:
        print("  Warnings (non-blocking):")
        for f in warnings:
            print(f)
    if not findings:
        print("  No LLM-vendor runtime dependencies found.")
    print("=" * 60)
    print(f"  result: {'PASS' if not blockers else 'FAIL'}")
    return 0 if not blockers else 1


# ── Install Windows runtime (Phase K) ───────────────────────────────────────
def cmd_install_windows() -> int:
    """
    Idempotent Windows setup:
      1. Ensure .venv exists (creates with sys.executable if missing).
      2. pip install -e .[dev] inside the venv.
      3. Write coach assets (Pine + HTML) into KiteBot-Control/.
      4. Write the 4 .bat files into KiteBot-Control/.
      5. Print final instructions.
    Never deletes user data.
    """
    import subprocess
    venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    print("\n" + "=" * 60)
    print("  install-windows")
    print("=" * 60)
    # 1. Venv
    if venv_py.exists():
        print(f"  [skip] venv already at {venv_py}")
    else:
        print(f"  [1/5] creating venv at {BASE_DIR / '.venv'}")
        subprocess.run([sys.executable, "-m", "venv", str(BASE_DIR / ".venv")],
                       check=True)
        print(f"        venv created")
    # 2. Editable install
    print(f"  [2/5] pip install -e .[dev] (using venv python)")
    try:
        subprocess.run([str(venv_py), "-m", "pip", "install", "-e", ".[dev]"],
                       cwd=BASE_DIR, check=True)
    except subprocess.CalledProcessError as e:
        print(f"  ERROR: pip install failed ({e})")
        return 1
    # 3. Coach assets
    print(f"  [3/5] writing coach assets to {CONTROL_DIR}")
    assets = ensure_coach_assets()
    for k, v in assets.items():
        print(f"        {k}: {v}")
    # 4. .bat files
    print(f"  [4/5] writing .bat launchers to {CONTROL_DIR}")
    _write_bat_files()
    # 5. Done
    print(f"  [5/5] done")
    print("")
    print("  Next steps:")
    print(f"    - double-click {CONTROL_DIR}\\RUN_BOT.bat")
    print(f"    - or run: {venv_py} paper_engine.py healthcheck")
    print("=" * 60)
    return 0


def _write_bat_files() -> None:
    """Idempotently write the 4 desktop .bat launchers. No EMERGENCY file."""
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    bot_dir_str  = str(BASE_DIR)
    venv_py_str  = str(BASE_DIR / ".venv" / "Scripts" / "python.exe")
    ctrl_dir_str = str(CONTROL_DIR)

    run_bot = f"""@echo off
REM ========================================================================
REM  KiteBot RUN_BOT — Phase K independent Windows runtime.
REM  No external LLM CLI dependency. No live broker. Paper only.
REM ========================================================================
set BOT_DIR={bot_dir_str}
set VENV_PY={venv_py_str}
set CTRL_DIR={ctrl_dir_str}

cd /d "%BOT_DIR%"
if not exist "%VENV_PY%" (
    echo ERROR: venv missing. Run:  python paper_engine.py install-windows
    pause
    exit /b 1
)
echo  [1/4] runtime-audit...
"%VENV_PY%" paper_engine.py runtime-audit
if errorlevel 1 (
    echo  runtime-audit FAILED -- aborting.
    pause
    exit /b 1
)
echo  [2/4] healthcheck...
"%VENV_PY%" paper_engine.py healthcheck
if errorlevel 1 (
    echo  healthcheck FAILED -- aborting.
    pause
    exit /b 1
)
echo  [3/4] opening KiteBot Equity Console...
start "" "%CTRL_DIR%\\KiteBot-Live-Coach.html" 2>nul
"%VENV_PY%" paper_engine.py open-charts 3
echo  [4/4] starting supervisor loop (Ctrl+C to stop)...
echo        Phone URL will be written to "%CTRL_DIR%\\PHONE_TERMINAL_URL.txt"
"%VENV_PY%" paper_engine.py run-all
pause
"""

    pause_bot = f"""@echo off
REM KiteBot PAUSE — blocks new BUYs only. Monitor exits keep running.
set BOT_DIR={bot_dir_str}
set VENV_PY={venv_py_str}
cd /d "%BOT_DIR%"
if not exist "%VENV_PY%" (
    echo ERROR: venv missing. Run install-windows.
    pause & exit /b 1
)
set REASON=%*
if "%REASON%"=="" set REASON=manual pause from KiteBot-Control
"%VENV_PY%" paper_engine.py pause %REASON%
echo  Supervisor exits keep firing. RESUME_BOT to re-enable BUYs.
pause
"""

    resume_bot = f"""@echo off
REM KiteBot RESUME — re-enable new BUYs.
set BOT_DIR={bot_dir_str}
set VENV_PY={venv_py_str}
cd /d "%BOT_DIR%"
if not exist "%VENV_PY%" (
    echo ERROR: venv missing. Run install-windows.
    pause & exit /b 1
)
"%VENV_PY%" paper_engine.py resume
"%VENV_PY%" paper_engine.py status
pause
"""

    status_bot = f"""@echo off
REM KiteBot STATUS — portfolio + control + dashboard refresh.
set BOT_DIR={bot_dir_str}
set VENV_PY={venv_py_str}
cd /d "%BOT_DIR%"
if not exist "%VENV_PY%" (
    echo ERROR: venv missing. Run install-windows.
    pause & exit /b 1
)
"%VENV_PY%" paper_engine.py status
pause
"""

    (CONTROL_DIR / "RUN_BOT.bat").write_text(run_bot, encoding="utf-8")
    old_pine_installer = CONTROL_DIR / "INSTALL_PINE_OVERLAY.bat"
    if old_pine_installer.exists():
        old_pine_installer.unlink()
    (CONTROL_DIR / "PAUSE_BOT.bat").write_text(pause_bot, encoding="utf-8")
    (CONTROL_DIR / "RESUME_BOT.bat").write_text(resume_bot, encoding="utf-8")
    (CONTROL_DIR / "STATUS_BOT.bat").write_text(status_bot, encoding="utf-8")


# ── Brain status (learner profile) ──────────────────────────────────────────
def cmd_brain_status() -> None:
    """Show the adaptive learner's current profile + capital governor decision."""
    profile = load_profile()
    print("\n" + "=" * 60)
    print("  Brain status (adaptive scoring profile)")
    print("=" * 60)
    print(f"  closed trades        : {profile.total_closed_trades}")
    print(f"  sample sufficient    : {profile.sample_size_sufficient}")
    print(f"  win rate             : {profile.win_rate}")
    print(f"  avg R multiple       : {profile.avg_r_multiple}")
    print(f"  losing streak        : {profile.losing_streak}")
    print(f"  max drawdown (%)     : {profile.max_drawdown_pct}")
    print(f"  cooled-down symbols  : {profile.cooled_down_symbols}")
    print(f"  last updated         : {profile.last_updated}")
    print(f"  notes                : {profile.notes}")
    print(f"  weights              : {profile.weights}")
    print("")
    decision = governor_assess(risk_cfg=_effective_risk_cfg(), profile=profile)
    print(f"  governor tier        : {decision.tier}")
    print(f"  effective risk %     : {decision.effective_risk_pct}")
    print(f"  halted               : {decision.halted}")
    for r in decision.reasons:
        print(f"    - {r}")
    print("=" * 60)


# ── Strategy status (tournament leaderboard) ────────────────────────────────
def cmd_strategy_status() -> None:
    snap = load_leaderboard()
    print("\n" + "=" * 60)
    print("  Strategy tournament leaderboard")
    print("=" * 60)
    if snap is None:
        print("  (no leaderboard yet — run-all triggers tournament on first start)")
        print("=" * 60)
        return
    print(f"  asof    : {snap.asof}")
    print(f"  champion: {snap.champion or '(none eligible)'}")
    print(f"  shadow  : {snap.shadow}")
    print("")
    print(f"  {'strategy':<28} {'trades':>7} {'win%':>6} {'PF':>6} "
          f"{'DD%':>6} {'score':>7}  eligible")
    print(f"  {'-' * 28} {'-' * 7} {'-' * 6} {'-' * 6} "
          f"{'-' * 6} {'-' * 7}  --------")
    for r in snap.results:
        print(f"  {r.name:<28} {r.trades:>7} {r.win_rate * 100:>6.1f} "
              f"{r.profit_factor:>6.2f} {r.max_dd_pct:>6.2f} "
              f"{r.score:>7.3f}  {'YES' if r.eligible else 'no ' + r.reason}")
    print("=" * 60)


# ── Symbol validation (used by healthcheck) ─────────────────────────────────
def _backtest_bars_for(symbol: str) -> list[BacktestBar]:
    yf = _import_yfinance()
    if yf is None:
        rows = _fetch_yahoo_chart_rows(symbol, range_name="6mo", interval="1d")
        return [
            BacktestBar(
                ts=row["ts"].isoformat(),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
            for row in rows[-180:]
        ]
    ticker = WATCHLIST.get(symbol, symbol)
    try:
        h = yf.Ticker(ticker).history(period="6mo", interval="1d")
        if h is None or h.empty:
            return []
        h = h.dropna(subset=["Open", "High", "Low", "Close"]).tail(180)
        bars = []
        for ts, row in h.iterrows():
            bars.append(BacktestBar(
                ts=ts.to_pydatetime().isoformat(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0) or 0),
            ))
        return bars
    except Exception as e:
        log.warning(f"strategy bars failed for {symbol}: {e}")
        rows = _fetch_yahoo_chart_rows(symbol, range_name="6mo", interval="1d")
        return [
            BacktestBar(
                ts=row["ts"].isoformat(),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
            for row in rows[-180:]
        ]


def cmd_strategy_run_once() -> int:
    """Run the backend strategy tournament once and persist the leaderboard."""
    bars_by_symbol = {}
    for symbol in WATCHLIST:
        if symbol in _unavailable_symbols():
            continue
        bars = _backtest_bars_for(symbol)
        if len(bars) >= 60:
            bars_by_symbol[symbol] = bars
    if not bars_by_symbol:
        print("  strategy-run-once: no historical bars available")
        return 1
    snap = run_tournament(bars_by_symbol, benchmark_symbol="NIFTY50")
    print(f"\n  strategy-run-once: tested {len(snap.results)} strategies "
          f"on {len(bars_by_symbol)} symbols")
    print(f"  champion: {snap.champion or '(none eligible)'}")
    for row in snap.results:
        print(f"  {row.name:<28} trades={row.trades:<4} "
              f"win={row.win_rate * 100:>5.1f}% pf={row.profit_factor:>5.2f} "
              f"dd={row.max_dd_pct:>5.2f}% eligible={'yes' if row.eligible else 'no'}")
    return 0


def validate_watchlist() -> tuple[list, list]:
    """
    Probe each WATCHLIST symbol via yfinance. Returns (available, unavailable).
    Persists the unavailable set so the supervisor and providers can skip them.
    """
    yf = _import_yfinance()
    if yf is None:
        return ([], list(WATCHLIST.keys()))
    available, unavailable = [], []
    for sym, ticker in WATCHLIST.items():
        try:
            h = yf.Ticker(ticker).history(period="1d", interval="5m")
            if h is None or h.empty:
                unavailable.append(sym)
            else:
                available.append(sym)
        except Exception:
            unavailable.append(sym)
    save_state("unavailable_symbols", unavailable)
    log.info(f"watchlist probe: available={available} unavailable={unavailable}")
    return available, unavailable


# ── Healthcheck ──────────────────────────────────────────────────────────────
def cmd_healthcheck() -> int:
    """
    Verify the engine is operationally ready. Returns exit code:
      0 = all required checks pass
      1 = a required check failed
    Quote-provider failure is reported as WARN (market may simply be closed),
    not a failure — control/exit paths must still work in that case.
    """
    ok      = True
    results = []

    def _check(name: str, fn, required: bool = True):
        nonlocal ok
        try:
            detail = fn()
            results.append(("OK", name, detail or ""))
        except Exception as e:
            results.append(("FAIL" if required else "WARN", name, str(e)))
            if required:
                ok = False

    _check("imports: bot.engine, control, portfolio, charges, risk, monitor",
           lambda: "loaded at module import")

    _check("DB init + read", lambda: (
        init_db(), get_pnl_summary(),
        f"db={BASE_DIR/'kite_bot.db'}"
    )[-1])

    _check("control file readable", lambda: (
        f"path={control.get_control_path()} "
        f"killed={control.is_killed()} paused={control.is_paused()}"
    ))

    def _portfolio_check():
        pf = load_portfolio()
        return (f"cash=Rs.{pf.state.cash:,.2f} "
                f"open_positions={len(pf.state.positions)}")
    _check("portfolio load", _portfolio_check)

    def _quote_check():
        yf = _import_yfinance()
        if yf is None:
            raise RuntimeError("yfinance not importable")
        # Don't actually fetch — just confirm provider callable + breaker state
        return f"yfinance available; breaker_open={not breaker.check()}"
    _check("quote provider availability", _quote_check, required=False)

    def _watchlist_probe():
        try:
            init_db()    # _persist of unavailable_symbols needs the DB ready
        except Exception:
            pass
        available, unavailable = validate_watchlist()
        return (f"available={available} unavailable={unavailable}"
                if available else f"NONE available; unavailable={unavailable}")
    _check("watchlist symbol probe (NSE equities)", _watchlist_probe, required=False)

    print("\n" + "=" * 54)
    print("  kite-bot healthcheck")
    print("=" * 54)
    for status, name, detail in results:
        marker = {"OK": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[status]
        print(f"  {marker}  {name}")
        if detail:
            print(f"          {detail}")
    print("=" * 54)
    print(f"  result: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# ── Entry points ─────────────────────────────────────────────────────────────
def run_one_shot(argv: list) -> int:
    """Non-interactive mode. Returns exit code (0 = ok, 1 = error)."""
    cmd = argv[0]
    rest = argv[1:]
    # healthcheck must run BEFORE init_db/load_portfolio so it can diagnose
    # those exact failures rather than crash before reporting.
    if cmd == "healthcheck":
        return cmd_healthcheck()
    if cmd == "runtime-audit":
        return cmd_runtime_audit()
    if cmd == "install-windows":
        return cmd_install_windows()
    if cmd == "refresh-coach-assets":
        return cmd_refresh_coach_assets()
    if cmd == "install-pine-assets":
        return cmd_install_pine_assets()

    init_db()
    # Control commands don't need a portfolio
    if cmd == "kill":
        cmd_kill(" ".join(rest) or "no reason given"); return 0
    if cmd == "unkill":
        cmd_unkill(); return 0
    if cmd == "pause":
        cmd_pause(" ".join(rest) or "no reason given"); return 0
    if cmd == "resume":
        cmd_resume(); return 0
    if cmd == "brain-status":
        init_db(); cmd_brain_status(); return 0
    if cmd == "strategy-status":
        cmd_strategy_status(); return 0
    if cmd == "strategy-run-once":
        return cmd_strategy_run_once()
    if cmd == "research-once":
        cmd_research_once(); return 0

    try:
        pf = load_portfolio()
        if cmd == "monitor-once":
            cmd_monitor_once(pf)
        elif cmd == "scan-once":
            cmd_scan_once(pf)
        elif cmd == "auto-buy-once":
            cmd_auto_buy_once(pf)
        elif cmd == "run-all":
            # Optional: run-all --max-loops N
            max_loops = None
            if rest and rest[0] == "--max-loops" and len(rest) >= 2:
                try:
                    max_loops = int(rest[1])
                except ValueError:
                    pass
            cmd_run_all(max_loops=max_loops)
        elif cmd == "open-chart":
            symbol = rest[0].upper() if rest else None
            if symbol and symbol not in WATCHLIST:
                print(f"unknown chart symbol: {symbol}")
                return 1
            return cmd_open_chart(symbol, pf)
        elif cmd == "open-charts":
            try:
                limit = int(rest[0]) if rest else 3
            except ValueError:
                limit = 3
            return cmd_open_charts(max(1, min(limit, 6)), pf)
        elif cmd == "status":
            print_status(pf)
        elif cmd == "flatten":
            cmd_flatten(pf)
        else:
            print(f"unknown one-shot command: {cmd}")
            return 1
        return 0
    except Exception as e:
        log.exception(f"one-shot command failed: {cmd}")
        print(f"  ERROR: {e}")
        return 1


def run_interactive() -> None:
    init_db()
    print("\n" + "=" * 54)
    print("  kite-bot | NSE Equity Paper Trading")
    print("=" * 54)
    pf = load_portfolio()
    get_day_start_equity(pf)   # initialize today's equity snapshot if needed
    log.info(f"Started. Cash Rs.{pf.state.cash:,.2f}")
    print_status(pf)
    print_help()

    while True:
        try:
            raw = input("  kite> ").strip()
        except (EOFError, KeyboardInterrupt):
            log.info("Stopped.")
            print("\n  Bye!")
            break
        if not raw:
            continue
        parts = raw.split()
        cmd  = parts[0].lower()
        arg  = parts[1] if len(parts) > 1 else None
        rest = " ".join(parts[1:])

        if cmd == "quit":
            print("  Bye!"); break
        elif cmd == "status":     print_status(pf)
        elif cmd == "help":       print_help()
        elif cmd == "watchlist":  print("  Symbols:", " ".join(WATCHLIST.keys()))
        elif cmd == "trades":     print(f"  CSV -> {BASE_DIR/'trades.csv'}\n"
                                        f"  DB  -> {BASE_DIR/'kite_bot.db'}")
        elif cmd == "logs":       print(f"  Log -> {BASE_DIR/'bot.log'}")
        elif cmd == "price":
            if not arg: print("  Usage: price SYMBOL")
            else:
                q = yfinance_quote_provider(arg.upper())
                print(f"  {arg.upper()}: Rs.{q.price:.2f}" if q else "  no quote")
        elif cmd == "buy":
            if not arg: print("  Usage: buy SYMBOL")
            else: cmd_buy(arg.upper(), pf)
        elif cmd == "sell":
            if not arg: print("  Usage: sell SYMBOL")
            else: cmd_sell(arg.upper(), pf)
        elif cmd == "flatten":         cmd_flatten(pf)
        elif cmd == "monitor-once":    cmd_monitor_once(pf)
        elif cmd == "research-once":   cmd_research_once()
        elif cmd == "scan-once":       cmd_scan_once(pf)
        elif cmd == "auto-buy-once":   cmd_auto_buy_once(pf)
        elif cmd == "run-all":         cmd_run_all()
        elif cmd == "open-chart":      cmd_open_chart(arg.upper() if arg else None, pf)
        elif cmd == "open-charts":
            try: limit = int(arg) if arg else 3
            except ValueError: limit = 3
            cmd_open_charts(max(1, min(limit, 6)), pf)
        elif cmd == "brain-status":    cmd_brain_status()
        elif cmd == "strategy-run-once": cmd_strategy_run_once()
        elif cmd == "strategy-status": cmd_strategy_status()
        elif cmd == "healthcheck":     cmd_healthcheck()
        elif cmd == "kill":            cmd_kill(rest or "no reason given")
        elif cmd == "unkill":          cmd_unkill()
        elif cmd == "pause":           cmd_pause(rest or "no reason given")
        elif cmd == "resume":          cmd_resume()
        else:
            print(f"  Unknown: {cmd}")


def main():
    if len(sys.argv) > 1:
        sys.exit(run_one_shot(sys.argv[1:]))
    run_interactive()


if __name__ == "__main__":
    main()
