"""
Real NSE/Nifty-50 backtest harness — replays the ACTUAL Spencer decision logic
over real historical price data. No fabricated outcomes anywhere.

Faithfulness:
  - Indicators come from bot.indicators (the same RSI/ATR/Supertrend used live).
  - The entry/exit decision comes from bot.signals (compute_total_score,
    classify_signal) — the same pure scoring engine the live scanner uses.
  - Position sizing comes from bot.risk.calculate_position_size — the same
    volatility-scaled sizer with the same caps.
  - Charges come from bot.charges.round_trip_cost.

Honesty / limitations (stated, not hidden):
  - Data: yfinance daily bars for NSE symbols (real, free). Not tick data.
  - Research scores (sentiment/fundamentals/liquidity) are NOT available
    historically, so they are held NEUTRAL (0.5). This makes the backtest a
    TECHNICAL replay; live trading adds those research signals on top.
  - Intrabar order is unknown, so when a bar spans BOTH stop and target we count
    the STOP (pessimistic — never the flattering outcome).
  - No look-ahead: the decision at bar i uses only indicator values at/through i;
    the entry fills at bar i's close; exits are searched in bars strictly after i.

Output: writes every simulated trade to a SEPARATE SQLite journal
(backtest_journal.db by default) — the live kite_bot.db is never touched.
Each trade is tagged with the market regime at entry so the Phase-3 learning
layer can attribute performance per regime.

Usage:
    python -m bot.backtest --years 2 --top 50
    python -m bot.backtest --symbols RELIANCE TCS INFY --years 3
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from collections import Counter

from bot import indicators as ind
from bot.charges import round_trip_cost
from bot.config import default_config
from bot.risk import calculate_position_size
from bot.signals import (
    TechnicalSnapshot, build_candidate, Signal, BUY_THRESHOLD, SELL_THRESHOLD,
)
from bot.trade_filter import TradeFilterConfig, FilterDecision, evaluate_trade
from bot.entry_policy import (
    EntryConfig, decide_entry, variants as entry_variants,
    quality_variants as entry_quality_variants,
)

# Nifty-50 constituents (yfinance uses the .NS suffix).
NIFTY50 = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "SBIN", "BHARTIARTL",
    "ITC", "LT", "AXISBANK", "KOTAKBANK", "HINDUNILVR", "BAJFINANCE", "ASIANPAINT",
    "MARUTI", "SUNPHARMA", "TITAN", "WIPRO", "TATAMOTORS", "ADANIENT", "HCLTECH",
    "TECHM", "ULTRACEMCO", "NESTLEIND", "POWERGRID", "ONGC", "NTPC", "COALINDIA",
    "JSWSTEEL", "TATASTEEL", "CIPLA", "DRREDDY", "DIVISLAB", "EICHERMOT",
    "HEROMOTOCO", "BAJAJFINSV", "M&M", "GRASIM", "HDFCLIFE", "SBILIFE",
    "APOLLOHOSP", "BRITANNIA", "ADANIPORTS", "BPCL", "HINDALCO", "INDUSINDBK",
    "TATACONSUM", "SHRIRAMFIN", "BAJAJ-AUTO", "TRENT",
]

NEUTRAL = 0.5            # research scores unavailable historically -> neutral
EMA_FAST, EMA_SLOW = 9, 21
TARGET_R = 2.0          # target = entry + 2 * stop_distance (2R)
PRODUCT = "DELIVERY"    # multi-day swing holding
VOL_PERIOD = 20         # volume SMA window (Upgrade 1)
BOLL_PERIOD, BOLL_STD = 20, 2.0   # Bollinger band for RANGE mean-reversion (Upgrade 2)
BREAKOUT_LOOKBACK = 20  # prior-high window for TREND_UP breakout (Upgrade 2)


# ── Journal (separate DB, never the live one) ────────────────────────────────
BT_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, params TEXT, symbols INTEGER, trades INTEGER, net_pnl REAL
);
CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    symbol TEXT, regime TEXT,
    entry_date TEXT, exit_date TEXT,
    entry REAL, stop REAL, target REAL, exit REAL, qty REAL,
    entry_score REAL, exit_reason TEXT, bars_held INTEGER,
    gross_pnl REAL, charges REAL, pnl REAL
);
"""


class BacktestJournal:
    def __init__(self, path: str | Path = "backtest_journal.db"):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(BT_SCHEMA)
        self.conn.commit()

    def start_run(self, params: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO backtest_runs (ts, params, symbols, trades, net_pnl) VALUES (?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), json.dumps(params), 0, 0, 0.0),
        )
        self.conn.commit()
        return cur.lastrowid

    def record(self, run_id: int, t: "Trade") -> None:
        self.conn.execute(
            """INSERT INTO backtest_trades
               (run_id, symbol, regime, entry_date, exit_date, entry, stop, target,
                exit, qty, entry_score, exit_reason, bars_held, gross_pnl, charges, pnl)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, t.symbol, t.regime, t.entry_date, t.exit_date, t.entry, t.stop,
             t.target, t.exit, t.qty, t.entry_score, t.exit_reason, t.bars_held,
             t.gross_pnl, t.charges, t.pnl),
        )
        self.conn.commit()

    def finish_run(self, run_id: int, n_symbols: int, trades: int, net_pnl: float) -> None:
        self.conn.execute(
            "UPDATE backtest_runs SET symbols=?, trades=?, net_pnl=? WHERE id=?",
            (n_symbols, trades, round(net_pnl, 2), run_id),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


@dataclass
class Trade:
    symbol: str
    regime: str
    entry_date: str
    exit_date: Optional[str]
    entry: float
    stop: float
    target: float
    exit: float
    qty: float
    entry_score: float
    exit_reason: str
    bars_held: int
    gross_pnl: float
    charges: float
    pnl: float


# ── Data ─────────────────────────────────────────────────────────────────────
def fetch_history(symbol: str, years: int) -> Optional[pd.DataFrame]:
    import yfinance as yf
    ticker = f"{symbol}.NS"
    try:
        # download() avoids the .info/tz metadata call that 404s for some tickers.
        raw = yf.download(ticker, period=f"{years}y", interval="1d",
                          auto_adjust=False, progress=False, threads=False)
    except Exception:
        return None
    if raw is None or raw.empty or len(raw) < EMA_SLOW + 30:
        return None
    if isinstance(raw.columns, pd.MultiIndex):           # yf.download multi-index
        raw.columns = raw.columns.get_level_values(0)
    df = raw.rename(columns={c: str(c).lower() for c in raw.columns})
    needed = ["open", "high", "low", "close", "volume"]
    if any(c not in df.columns for c in needed):
        return None
    df = df[needed].dropna()
    return df if len(df) >= EMA_SLOW + 30 else None


def _regime(ema_fast: float, ema_slow: float, trend: str) -> str:
    """Simple, explainable regime label for per-regime attribution."""
    if ema_fast > ema_slow and trend == "green":
        return "TREND_UP"
    if ema_fast < ema_slow and trend == "red":
        return "TREND_DOWN"
    return "RANGE"


# ── Core replay for one symbol ───────────────────────────────────────────────
def add_indicators(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Attach the real indicators used by the live scanner (causal, no look-ahead)."""
    df = df.copy()
    df["rsi"] = ind.rsi(df)
    df["atr"] = ind.atr(df, cfg.indicators.atr_period)
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    df["st_trend"] = ind.supertrend(df, cfg.indicators.st_period,
                                    cfg.indicators.st_multiplier)["trend"]
    # Extra causal features for the entry-signal experiments:
    df["vol_sma"] = df["volume"].rolling(VOL_PERIOD, min_periods=VOL_PERIOD).mean()
    mid = df["close"].rolling(BOLL_PERIOD, min_periods=BOLL_PERIOD).mean()
    std = df["close"].rolling(BOLL_PERIOD, min_periods=BOLL_PERIOD).std()
    df["boll_lower"] = mid - BOLL_STD * std
    # Prior N-bar high EXCLUDING the current bar (shift(1)) — true breakout reference.
    df["prior_high"] = df["high"].rolling(BREAKOUT_LOOKBACK).max().shift(1)
    return df


def backtest_symbol(symbol: str, df: pd.DataFrame, cfg) -> List[Trade]:
    df = add_indicators(df, cfg)

    trades: List[Trade] = []
    n = len(df)
    warmup = EMA_SLOW + cfg.indicators.atr_period
    i = warmup
    equity = cfg.starting_balance

    while i < n - 1:
        row = df.iloc[i]
        price = float(row["close"])
        atr_v = float(row["atr"])
        if not np.isfinite(price) or not np.isfinite(atr_v) or price <= 0:
            i += 1
            continue

        # Size first so entry_blocked reflects a real, sizeable position.
        sizing = calculate_position_size(
            equity=equity, price=price, atr=atr_v,
            risk_cfg=cfg.risk, indi_cfg=cfg.indicators, fee_cfg=cfg.fees,
            product=PRODUCT,
        )
        snap = TechnicalSnapshot(
            price=price, rsi=float(row["rsi"]) if np.isfinite(row["rsi"]) else None,
            ema_fast=float(row["ema_fast"]), ema_slow=float(row["ema_slow"]),
            supertrend_trend=row["st_trend"], vwap=None, atr=atr_v,
        )
        cand = build_candidate(
            ts=df.index[i].to_pydatetime(), symbol=symbol, tech=snap,
            fundamentals_score=NEUTRAL, sentiment_score=NEUTRAL, liquidity_score=NEUTRAL,
            has_position=False, entry_blocked=sizing.rejected,
            block_reasons=sizing.reasons, research_snapshot_id=None,
            sizing_preview=None,
        )

        if cand.signal != Signal.BUY_CANDIDATE:
            i += 1
            continue

        # ENTRY at close of bar i.
        qty = sizing.qty
        stop_distance = sizing.stop_distance
        entry = price
        stop = entry - stop_distance
        target = entry + TARGET_R * stop_distance
        regime = _regime(float(row["ema_fast"]), float(row["ema_slow"]), row["st_trend"])

        # EXIT search in bars strictly after i.
        exit_price, exit_reason, exit_idx = None, None, None
        for j in range(i + 1, n):
            bj = df.iloc[j]
            hi, lo, cl = float(bj["high"]), float(bj["low"]), float(bj["close"])
            stop_hit = lo <= stop
            target_hit = hi >= target
            if stop_hit and target_hit:
                exit_price, exit_reason, exit_idx = stop, "stop", j      # pessimistic
                break
            if stop_hit:
                exit_price, exit_reason, exit_idx = stop, "stop", j
                break
            if target_hit:
                exit_price, exit_reason, exit_idx = target, "target", j
                break
            # Signal exit: recompute score with position held; SELL if score <= 0.35.
            snap_j = TechnicalSnapshot(
                price=cl, rsi=float(bj["rsi"]) if np.isfinite(bj["rsi"]) else None,
                ema_fast=float(bj["ema_fast"]), ema_slow=float(bj["ema_slow"]),
                supertrend_trend=bj["st_trend"], vwap=None,
                atr=float(bj["atr"]) if np.isfinite(bj["atr"]) else None,
            )
            cand_j = build_candidate(
                ts=df.index[j].to_pydatetime(), symbol=symbol, tech=snap_j,
                fundamentals_score=NEUTRAL, sentiment_score=NEUTRAL, liquidity_score=NEUTRAL,
                has_position=True, entry_blocked=False, block_reasons=[],
                research_snapshot_id=None, sizing_preview=None,
            )
            if cand_j.signal == Signal.SELL_CANDIDATE:
                exit_price, exit_reason, exit_idx = cl, "signal", j
                break

        if exit_idx is None:  # never exited -> close at final bar (honest: end_of_data)
            exit_idx = n - 1
            exit_price = float(df.iloc[-1]["close"])
            exit_reason = "end_of_data"

        gross = (exit_price - entry) * qty
        charges = round_trip_cost(entry, qty, PRODUCT)
        pnl = gross - charges
        equity += pnl

        trades.append(Trade(
            symbol=symbol, regime=regime,
            entry_date=str(df.index[i].date()), exit_date=str(df.index[exit_idx].date()),
            entry=round(entry, 2), stop=round(stop, 2), target=round(target, 2),
            exit=round(exit_price, 2), qty=qty, entry_score=cand.scores.total,
            exit_reason=exit_reason, bars_held=exit_idx - i,
            gross_pnl=round(gross, 2), charges=round(charges, 2), pnl=round(pnl, 2),
        ))
        # One position per symbol at a time: resume after the exit bar.
        i = exit_idx + 1

    return trades


# ── Aggregation / reporting (all numbers from real simulated trades) ─────────
def summarize(trades: List[Trade]) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "note": "No trades triggered — nothing to report."}
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    by_regime: dict = {}
    for t in trades:
        r = by_regime.setdefault(t.regime, {"trades": 0, "wins": 0, "pnl": 0.0})
        r["trades"] += 1
        r["wins"] += 1 if t.pnl > 0 else 0
        r["pnl"] += t.pnl
    for r in by_regime.values():
        r["win_rate"] = round(r["wins"] / r["trades"], 4)
        r["pnl"] = round(r["pnl"], 2)
    exit_reasons: dict = {}
    for t in trades:
        exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1
    gross = sum(t.gross_pnl for t in trades)
    charges = sum(t.charges for t in trades)
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n, 4),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "gross_pnl": round(gross, 2),
        "total_charges": round(charges, 2),
        "net_pnl": round(sum(pnls), 2),
        "avg_pnl_per_trade": round(sum(pnls) / n, 2),
        "by_regime": by_regime,
        "exit_reasons": exit_reasons,
    }


# ── Portfolio-level engine (needed for per-day caps + post-loss cooldown) ────
def _load_regime_trust(path: str | Path = "regime_trust.json") -> Dict[str, float]:
    """Read the Phase-3 trust table {regime: trust}. Missing -> all-neutral (1.0)."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {k: float(v.get("trust", 1.0)) for k, v in raw.get("regimes", {}).items()}
    except Exception:
        return {}


def _index_regime_series(years: int):
    """Index (Nifty) regime per date — the INDEPENDENT regime used for trust + tagging."""
    try:
        from bot.regime_learner import fetch_index, classify_index_regimes
        idx = fetch_index(years)
        if idx is None:
            return None
        return classify_index_regimes(idx)
    except Exception:
        return None


def _regime_on(series, day) -> str:
    if series is None:
        return "RANGE"
    r = series.get(day)
    if r is not None:
        return r
    prior = series[series.index <= day]
    return prior.iloc[-1] if len(prior) else "RANGE"


def _prepare(symbols: List[str], years: int, cfg):
    """Fetch + compute indicators ONCE so every experiment variant reuses the same data."""
    prepared: Dict[str, pd.DataFrame] = {}
    rowmap: Dict[str, Dict] = {}
    for sym in symbols:
        df = fetch_history(sym, years)
        if df is None:
            continue
        df = add_indicators(df, cfg).reset_index().rename(columns={"index": "ts", "Date": "ts"})
        df["d"] = [pd.to_datetime(x).date() for x in df["ts"]]
        prepared[sym] = df
        rowmap[sym] = {d: i for i, d in enumerate(df["d"])}
    return prepared, rowmap


def _indi_with_atr_mult(indi, mult: float):
    """Return an IndicatorConfig with a different ATR stop multiple (pydantic v1/v2 safe)."""
    try:
        return indi.model_copy(update={"atr_multiplier": mult})
    except AttributeError:
        return indi.copy(update={"atr_multiplier": mult})


def run_portfolio(
    symbols: List[str],
    years: int,
    filter_cfg: Optional[TradeFilterConfig],
    journal_path: Optional[str] = None,
    trust_table: Optional[Dict[str, float]] = None,
    index_regimes=None,
) -> dict:
    """Baseline/filtered run (back-compat wrapper). Prepares data then simulates."""
    cfg = default_config()
    prepared, rowmap = _prepare(symbols, years, cfg)
    return _simulate(prepared, rowmap, symbols, cfg, entry_cfg=None,
                     filter_cfg=filter_cfg, trust_table=trust_table or {},
                     index_regimes=index_regimes, journal_path=journal_path)


def _simulate(
    prepared, rowmap, symbols, cfg, *, entry_cfg, filter_cfg,
    trust_table, index_regimes, journal_path=None,
) -> dict:
    """
    Event-driven, portfolio-wide replay across ALL symbols by trading date.

    entry_cfg=None  -> use the base technical BUY signal (optionally with filter_cfg).
    entry_cfg set   -> use the experimental entry policy (volume/regime/target upgrades);
                       filter_cfg is ignored so the SIGNAL change is measured in isolation.
    """
    warmup = EMA_SLOW + cfg.indicators.atr_period
    trust_table = trust_table or {}
    # ATR stop override (Upgrade 3) re-sizes qty consistently via the sizer.
    size_indi = cfg.indicators
    target_r = TARGET_R
    if entry_cfg is not None:
        target_r = entry_cfg.target_r
        if entry_cfg.atr_stop_mult is not None:
            size_indi = _indi_with_atr_mult(cfg.indicators, entry_cfg.atr_stop_mult)

    all_dates = sorted({d for rm in rowmap.values() for d in rm})
    equity = cfg.starting_balance
    open_pos: Dict[str, dict] = {}
    last_loss_row: Dict[str, int] = {}     # symbol -> row idx where a losing trade exited
    day_count: Dict[object, int] = {}
    trades: List[Trade] = []
    rejects: Counter = Counter()
    realized_curve: List[float] = [equity]

    def _close(sym, pos, exit_price, exit_reason, exit_idx, df):
        nonlocal equity
        gross = (exit_price - pos["entry"]) * pos["qty"]
        charges = round_trip_cost(pos["entry"], pos["qty"], PRODUCT)
        pnl = gross - charges
        equity += pnl
        realized_curve.append(equity)
        if pnl < 0:
            last_loss_row[sym] = exit_idx
        trades.append(Trade(
            symbol=sym, regime=pos["regime"],
            entry_date=str(pos["entry_date"]), exit_date=str(df["d"].iloc[exit_idx]),
            entry=round(pos["entry"], 2), stop=round(pos["stop"], 2),
            target=round(pos["target"], 2), exit=round(exit_price, 2), qty=pos["qty"],
            entry_score=pos["score"], exit_reason=exit_reason,
            bars_held=exit_idx - pos["entry_idx"], gross_pnl=round(gross, 2),
            charges=round(charges, 2), pnl=round(pnl, 2),
        ))

    for day in all_dates:
        # 1) Manage exits for open positions on this date's bar.
        for sym in list(open_pos.keys()):
            idx = rowmap[sym].get(day)
            pos = open_pos[sym]
            if idx is None or idx <= pos["entry_idx"]:
                continue
            df = prepared[sym]
            bar = df.iloc[idx]
            hi, lo, cl = float(bar["high"]), float(bar["low"]), float(bar["close"])
            exit_price = exit_reason = None
            if lo <= pos["stop"]:                       # pessimistic: stop first
                exit_price, exit_reason = pos["stop"], "stop"
            elif hi >= pos["target"]:
                exit_price, exit_reason = pos["target"], "target"
            else:
                snap = TechnicalSnapshot(
                    price=cl, rsi=float(bar["rsi"]) if np.isfinite(bar["rsi"]) else None,
                    ema_fast=float(bar["ema_fast"]), ema_slow=float(bar["ema_slow"]),
                    supertrend_trend=bar["st_trend"], vwap=None,
                    atr=float(bar["atr"]) if np.isfinite(bar["atr"]) else None,
                )
                c = build_candidate(
                    ts=df["ts"].iloc[idx], symbol=sym, tech=snap,
                    fundamentals_score=NEUTRAL, sentiment_score=NEUTRAL,
                    liquidity_score=NEUTRAL, has_position=True, entry_blocked=False,
                    block_reasons=[], research_snapshot_id=None, sizing_preview=None,
                )
                if c.signal == Signal.SELL_CANDIDATE:
                    exit_price, exit_reason = cl, "signal"
            if exit_price is not None:
                _close(sym, pos, exit_price, exit_reason, idx, df)
                del open_pos[sym]

        # 2) Entries for symbols with no open position.
        regime = _regime_on(index_regimes, day)
        trust = trust_table.get(regime, 1.0)
        for sym in symbols:
            if sym not in rowmap or sym in open_pos:
                continue
            idx = rowmap[sym].get(day)
            if idx is None or idx < warmup or idx >= len(prepared[sym]) - 1:
                continue
            df = prepared[sym]
            bar = df.iloc[idx]
            price, atr_v = float(bar["close"]), float(bar["atr"])
            if not np.isfinite(price) or not np.isfinite(atr_v) or price <= 0:
                continue
            sizing = calculate_position_size(
                equity=equity, price=price, atr=atr_v, risk_cfg=cfg.risk,
                indi_cfg=size_indi, fee_cfg=cfg.fees, product=PRODUCT,
            )
            snap = TechnicalSnapshot(
                price=price, rsi=float(bar["rsi"]) if np.isfinite(bar["rsi"]) else None,
                ema_fast=float(bar["ema_fast"]), ema_slow=float(bar["ema_slow"]),
                supertrend_trend=bar["st_trend"], vwap=None, atr=atr_v,
            )
            cand = build_candidate(
                ts=df["ts"].iloc[idx], symbol=sym, tech=snap,
                fundamentals_score=NEUTRAL, sentiment_score=NEUTRAL, liquidity_score=NEUTRAL,
                has_position=False, entry_blocked=sizing.rejected,
                block_reasons=sizing.reasons, research_snapshot_id=None, sizing_preview=None,
            )
            base_is_buy = cand.signal == Signal.BUY_CANDIDATE
            qty = sizing.qty
            stop_distance = sizing.stop_distance
            entry = price
            if sizing.rejected or qty < 1:     # no tradable size -> skip (both paths)
                continue
            charges = round_trip_cost(entry, qty, PRODUCT)

            if entry_cfg is None:
                # ── Base technical signal (optionally anti-overtrading filtered) ──
                if not base_is_buy:
                    continue
                stop = entry - stop_distance
                target = entry + target_r * stop_distance
                if filter_cfg is not None:
                    ssl = (idx - last_loss_row[sym]) if sym in last_loss_row else None
                    decision = evaluate_trade(
                        trust=trust, entry=entry, stop=stop, target=target, qty=qty,
                        charges=charges, trades_today=day_count.get(day, 0),
                        sessions_since_loss=ssl, cfg=filter_cfg,
                    )
                    if not decision.accepted:
                        cat = next((k for k, ok in decision.checks.items() if not ok), "other")
                        rejects[cat] += 1
                        continue
            else:
                # ── Experimental entry policy (signal upgrades, measured in isolation) ──
                action, payload = decide_entry(
                    regime=regime, base_is_buy=base_is_buy, price=price, atr=atr_v,
                    rsi=float(bar["rsi"]) if np.isfinite(bar["rsi"]) else None,
                    ema_fast=float(bar["ema_fast"]),
                    boll_lower=float(bar["boll_lower"]) if np.isfinite(bar["boll_lower"]) else float("nan"),
                    prior_high=float(bar["prior_high"]) if np.isfinite(bar["prior_high"]) else float("nan"),
                    volume=float(bar["volume"]),
                    vol_sma=float(bar["vol_sma"]) if np.isfinite(bar["vol_sma"]) else float("nan"),
                    stop_distance=stop_distance, qty=qty, charges=charges, cfg=entry_cfg,
                    entry_score=cand.scores.total,
                    ema_slow=float(bar["ema_slow"]),
                    st_trend=bar["st_trend"],
                )
                if action == "skip":
                    continue
                if action == "reject":
                    rejects[payload] += 1
                    continue
                stop = entry - stop_distance
                target = entry + payload.target_r * stop_distance

            open_pos[sym] = {
                "entry": entry, "stop": stop, "target": target, "qty": qty,
                "regime": regime, "entry_date": day, "entry_idx": idx,
                "score": cand.scores.total,
            }
            day_count[day] = day_count.get(day, 0) + 1

    # 3) Close any still-open positions at their last bar (honest end_of_data).
    for sym, pos in list(open_pos.items()):
        df = prepared[sym]
        last_idx = len(df) - 1
        _close(sym, pos, float(df["close"].iloc[last_idx]), "end_of_data", last_idx, df)
        del open_pos[sym]

    summary = summarize(trades)
    summary["max_drawdown_pct"] = _max_drawdown_pct(realized_curve)
    summary["rejected_trades"] = dict(rejects)
    summary["rejected_total"] = int(sum(rejects.values()))
    summary["ending_equity"] = round(equity, 2)
    summary["symbols_used"] = len(prepared)

    if journal_path:
        mode = entry_cfg.name if entry_cfg is not None else (
            "filtered" if filter_cfg else "baseline")
        journal = BacktestJournal(journal_path)
        run_id = journal.start_run({"mode": mode, "symbols": len(symbols)})
        for t in trades:
            journal.record(run_id, t)
        journal.finish_run(run_id, len(prepared), len(trades), summary.get("net_pnl", 0.0))
        journal.close()
        summary["run_id"] = run_id
    return summary


def _max_drawdown_pct(curve: List[float]) -> float:
    peak, max_dd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak * 100)
    return round(max_dd, 2)


def compare(symbols: List[str], years: int) -> dict:
    """Run baseline vs filtered on the SAME data/engine and return both summaries."""
    trust_table = _load_regime_trust()
    index_regimes = _index_regime_series(years)
    print(f"Regime trust loaded: {trust_table or '(none — neutral)'}")
    print("Running BASELINE (no filter)…")
    base = run_portfolio(symbols, years, None, journal_path="backtest_baseline.db",
                         trust_table=trust_table, index_regimes=index_regimes)
    print("Running FILTERED (anti-overtrading)…")
    filt = run_portfolio(symbols, years, TradeFilterConfig(),
                         journal_path="backtest_filtered.db",
                         trust_table=trust_table, index_regimes=index_regimes)
    return {"baseline": base, "filtered": filt}


def run_experiments(symbols: List[str], years: int, variant_list=None) -> dict:
    """
    Controlled entry-signal experiment: ONE upgrade group at a time, then combined.
    All variants share ONE data fetch and the SAME index regimes, so differences are
    attributable to the entry signal alone. The anti-overtrading filter is OFF here
    (we are isolating the SIGNAL, not re-testing the filter).
    """
    cfg = default_config()
    trust_table = _load_regime_trust()
    index_regimes = _index_regime_series(years)
    variant_list = variant_list if variant_list is not None else entry_variants()
    print("Preparing data once (fetch + indicators)…")
    prepared, rowmap = _prepare(symbols, years, cfg)
    print(f"Prepared {len(prepared)} symbols. Running {len(variant_list)} variants…")

    results: dict = {}
    for ecfg in variant_list:
        print(f"  variant: {ecfg.name}")
        results[ecfg.name] = _simulate(
            prepared, rowmap, symbols, cfg, entry_cfg=ecfg, filter_cfg=None,
            trust_table=trust_table, index_regimes=index_regimes,
            journal_path=f"backtest_{ecfg.name}.db",
        )
    return results


def _print_experiments(results: dict) -> None:
    order = list(results.keys())
    metrics = [
        ("trades taken",   "trades",            lambda v: str(v)),
        ("win rate",       "win_rate",          lambda v: f"{v:.1%}"),
        ("avg win",        "avg_win",           lambda v: f"{v:,.0f}"),
        ("avg loss",       "avg_loss",          lambda v: f"{v:,.0f}"),
        ("net P&L",        "net_pnl",           lambda v: f"{v:,.0f}"),
        ("charges",        "total_charges",     lambda v: f"{v:,.0f}"),
        ("max drawdown %", "max_drawdown_pct",  lambda v: f"{v:.1f}"),
        ("rejected",       "rejected_total",    lambda v: str(v)),
    ]
    w = 13
    print("\n=== ENTRY-SIGNAL EXPERIMENT (same data, one group at a time) ===")
    header = f"{'metric':<16}" + "".join(f"{name:>{w}}" for name in order)
    print(header)
    print("-" * len(header))
    for label, key, fmt in metrics:
        row = f"{label:<16}"
        for name in order:
            val = results[name].get(key, 0)
            row += f"{fmt(val):>{w}}"
        print(row)

    # Regime-wise net P&L per variant.
    print("\n=== REGIME-WISE net P&L (Rs.) ===")
    regimes = ["TREND_UP", "TREND_DOWN", "RANGE"]
    rhead = f"{'regime':<16}" + "".join(f"{name:>{w}}" for name in order)
    print(rhead)
    print("-" * len(rhead))
    for reg in regimes:
        row = f"{reg:<16}"
        for name in order:
            br = results[name].get("by_regime", {}).get(reg)
            if br:
                row += f"{br['pnl']:>{w},.0f}"
            else:
                row += f"{'—':>{w}}"
        print(row)
    # Per-variant win rate by regime (trades in parens).
    print("\n=== REGIME-WISE win rate (trades) ===")
    print(rhead)
    print("-" * len(rhead))
    for reg in regimes:
        row = f"{reg:<16}"
        for name in order:
            br = results[name].get("by_regime", {}).get(reg)
            if br:
                cell = "{:.0%} ({})".format(br["win_rate"], br["trades"])
            else:
                cell = "—"
            row += f"{cell:>{w}}"
        print(row)

    print("\nRejections by reason (per variant):")
    for name in order:
        rj = results[name].get("rejected_trades", {})
        if rj:
            print(f"  {name:<12} " + ", ".join(f"{k}={v}" for k, v in sorted(rj.items())))


def _print_quality_verdict(results: dict) -> None:
    """Honest old-vs-new readout. The GOAL is higher win rate + fewer weak entries —
    NOT merely a smaller trade count. We say so explicitly."""
    old, new = results.get("baseline"), results.get("q_highquality")
    if not old or not new:
        return
    wr_old, wr_new = old["win_rate"], new["win_rate"]
    n_old, n_new = old["trades"], new["trades"]
    print("\n=== OLD vs NEW VERDICT (goal: higher win rate, fewer weak entries) ===")
    print(f"  win rate : {wr_old:.1%} -> {wr_new:.1%}   ({(wr_new - wr_old) * 100:+.1f} pts)")
    print(f"  trades   : {n_old} -> {n_new}   ({(n_new - n_old) / n_old * 100:+.0f}%)")
    print(f"  net P&L  : {old['net_pnl']:,.0f} -> {new['net_pnl']:,.0f}")
    print(f"  avg win  : {old['avg_win']:,.0f} -> {new['avg_win']:,.0f}")
    print(f"  avg loss : {old['avg_loss']:,.0f} -> {new['avg_loss']:,.0f}")
    print(f"  max DD % : {old['max_drawdown_pct']} -> {new['max_drawdown_pct']}")
    rej = new.get("rejected_trades", {})
    print("  weak entries removed: " +
          (", ".join(f"{k}={v}" for k, v in sorted(rej.items())) or "none"))
    delta = wr_new - wr_old
    if delta >= 0.03:
        print(f"  VERDICT: win rate improved by {delta * 100:.1f} pts — a real quality gain.")
    elif n_new < n_old:
        print("  VERDICT: win rate basically unchanged — this mostly REDUCED COUNT, "
              "not entry quality. Selectivity alone did not create edge.")
    else:
        print("  VERDICT: no win-rate improvement; the entry signal still lacks edge.")


def run(symbols: List[str], years: int, journal_path: str = "backtest_journal.db") -> dict:
    cfg = default_config()
    journal = BacktestJournal(journal_path)
    run_id = journal.start_run({"symbols": symbols, "years": years, "product": PRODUCT})

    all_trades: List[Trade] = []
    used = 0
    skipped = []
    for sym in symbols:
        df = fetch_history(sym, years)
        if df is None:
            skipped.append(sym)
            continue
        used += 1
        t = backtest_symbol(sym, df, cfg)
        for tr in t:
            journal.record(run_id, tr)
        all_trades.extend(t)
        print(f"  {sym:12s} bars={len(df):4d} trades={len(t)}")

    summary = summarize(all_trades)
    journal.finish_run(run_id, used, len(all_trades), summary.get("net_pnl", 0.0))
    journal.close()
    summary["symbols_used"] = used
    summary["symbols_skipped"] = skipped
    summary["run_id"] = run_id
    summary["journal"] = journal_path
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="bot.backtest", description="Real NSE backtest")
    p.add_argument("--symbols", nargs="*", default=None, help="override symbol list (no .NS)")
    p.add_argument("--top", type=int, default=50, help="use first N Nifty-50 names")
    p.add_argument("--years", type=int, default=2)
    p.add_argument("--journal", default="backtest_journal.db")
    p.add_argument("--compare", action="store_true",
                   help="run baseline vs anti-overtrading filter and compare")
    p.add_argument("--experiment", action="store_true",
                   help="run the controlled entry-signal upgrade experiment")
    p.add_argument("--quality", action="store_true",
                   help="run the 'fewer, higher-quality entries' experiment (old vs new)")
    args = p.parse_args(argv)

    symbols = args.symbols if args.symbols else NIFTY50[: args.top]
    print(f"Backtest: {len(symbols)} symbols, {args.years}y daily, product={PRODUCT}")
    print("Research scores held neutral (0.5) — TECHNICAL replay. See module docstring.")

    if args.quality:
        results = run_experiments(symbols, args.years, entry_quality_variants())
        _print_experiments(results)
        _print_quality_verdict(results)
        return 0

    if args.experiment:
        results = run_experiments(symbols, args.years)
        _print_experiments(results)
        return 0

    if args.compare:
        res = compare(symbols, args.years)
        _print_comparison(res["baseline"], res["filtered"])
        print("\n=== RAW ===")
        print(json.dumps(res, indent=2))
        return 0

    summary = run(symbols, args.years, args.journal)
    print("\n=== SUMMARY (real trades, no fabrication) ===")
    print(json.dumps(summary, indent=2))
    return 0


def _print_comparison(base: dict, filt: dict) -> None:
    def g(d, k, default=0):
        return d.get(k, default)
    rows = [
        ("trades taken",     g(base, "trades"),        g(filt, "trades")),
        ("win rate",         g(base, "win_rate"),      g(filt, "win_rate")),
        ("net P&L (Rs.)",    g(base, "net_pnl"),       g(filt, "net_pnl")),
        ("gross P&L (Rs.)",  g(base, "gross_pnl"),     g(filt, "gross_pnl")),
        ("charges (Rs.)",    g(base, "total_charges"), g(filt, "total_charges")),
        ("max drawdown %",   g(base, "max_drawdown_pct"), g(filt, "max_drawdown_pct")),
        ("avg P&L/trade",    g(base, "avg_pnl_per_trade"), g(filt, "avg_pnl_per_trade")),
        ("rejected trades",  g(base, "rejected_total"), g(filt, "rejected_total")),
    ]
    print("\n=== BASELINE vs FILTERED (same data, same engine) ===")
    print(f"{'metric':<18}{'baseline':>14}{'filtered':>14}")
    print("-" * 46)
    for name, b, f in rows:
        print(f"{name:<18}{str(b):>14}{str(f):>14}")
    print("\nRejections by rule (filtered):")
    for rule, n in sorted(filt.get("rejected_trades", {}).items(), key=lambda x: -x[1]):
        print(f"  {rule:<22}{n}")


if __name__ == "__main__":
    raise SystemExit(main())
