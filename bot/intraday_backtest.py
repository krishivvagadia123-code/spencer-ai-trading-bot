"""Forward-only intraday replay harness for mechanical RELIANCE candidates.

The harness consumes stored final candles, evaluates declarative rules without
future data, fills at the next candle open with the paper engine's slippage
model, charges every leg, and persists results away from the live trades table.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

from bot.config import default_config
from bot.execution_sim import simulate_fill
from bot.holidays import is_nse_holiday
from bot.market_data import IST, Quote
from bot.research_candidates import (
    ALLOWED_CONTEXT_FIELDS,
    CAPITAL_BASIS_INR,
    ResearchCandidate,
    candidate_hash,
    rule_to_dict,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "kite_bot.db"
PRODUCT = "INTRADAY"
STAGES = {"IN_SAMPLE", "OUT_OF_SAMPLE", "WALK_FORWARD"}


BACKTEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    stage TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    candidate_version TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    dataset_start TEXT,
    dataset_end TEXT,
    data_rows INTEGER NOT NULL,
    summary_json TEXT NOT NULL,
    trades_json TEXT NOT NULL,
    equity_json TEXT NOT NULL,
    candidate_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backtest_kills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    candidate_version TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    hypothesis_hash TEXT NOT NULL,
    reason TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Candle:
    symbol: str
    interval: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = ""
    context: dict[str, float] = field(default_factory=dict, compare=False, repr=False)

    @property
    def session_date(self) -> date:
        return self.ts.astimezone(IST).date()

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "ts": self.ts.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source,
        }


@dataclass(frozen=True)
class BacktestResult:
    stage: str
    status: str
    candidate_id: str
    candidate_version: str
    params_hash: str
    result_hash: str
    dataset: dict
    trades: list[dict]
    equity_curve: list[dict]
    summary: dict


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp missing timezone: {value}")
    return parsed.astimezone(IST)


def ensure_backtest_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(BACKTEST_SCHEMA)


def load_candles(
    db_path: str | Path,
    candidate: ResearchCandidate,
    *,
    start: date | str | None = None,
    end: date | str | None = None,
) -> list[Candle]:
    start_date = date.fromisoformat(str(start)) if start is not None else None
    end_date = date.fromisoformat(str(end)) if end is not None else None
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT symbol, interval, ts, open, high, low, close, volume, source
            FROM intraday_prices
            WHERE symbol=? AND interval=?
            ORDER BY ts
            """,
            (candidate.symbol, candidate.interval),
        ).fetchall()

    candles = []
    for row in rows:
        ts = _parse_ts(row["ts"])
        session = ts.date()
        if start_date is not None and session < start_date:
            continue
        if end_date is not None and session > end_date:
            continue
        candles.append(
            Candle(
                symbol=row["symbol"],
                interval=row["interval"],
                ts=ts,
                open=round(float(row["open"]), 2),
                high=round(float(row["high"]), 2),
                low=round(float(row["low"]), 2),
                close=round(float(row["close"]), 2),
                volume=round(float(row["volume"] or 0), 2),
                source=row["source"] or "",
            )
        )
    return candles


SESSION_START_HOUR = 9
SESSION_START_MINUTE = 15


def _session_minute(ts: datetime) -> float:
    local_ts = ts.astimezone(IST)
    session_open = local_ts.replace(
        hour=SESSION_START_HOUR,
        minute=SESSION_START_MINUTE,
        second=0,
        microsecond=0,
    )
    return (local_ts - session_open).total_seconds() / 60.0


def _last_thursday(year: int, month: int) -> date:
    if month == 12:
        cursor = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)
    while cursor.weekday() != 3:
        cursor -= timedelta(days=1)
    return cursor


def _is_trading_day(session: date) -> bool:
    return session.weekday() < 5 and not is_nse_holiday(session)


def _monthly_expiry_session(year: int, month: int) -> date:
    """NSE monthly F&O expiry is the last Thursday, shifted to the prior
    trading day when that Thursday is a registered exchange holiday."""
    expiry = _last_thursday(year, month)
    while not _is_trading_day(expiry):
        expiry -= timedelta(days=1)
    return expiry


def _is_monthly_expiry_session(session: date) -> bool:
    return session == _monthly_expiry_session(session.year, session.month)


def _nan_context() -> dict[str, float]:
    return {name: float("nan") for name in ALLOWED_CONTEXT_FIELDS}


def _contextualize_candles(candles: Sequence[Candle]) -> list[Candle]:
    enriched: list[Candle] = []
    current_session: date | None = None
    current_stats: dict[str, float] | None = None
    previous_stats: dict[str, float] | None = None
    session_base_context = _nan_context()

    for candle in candles:
        session = candle.session_date
        if session != current_session:
            if current_stats is not None:
                previous_stats = current_stats
            current_session = session
            current_stats = {
                "high": float(candle.high),
                "low": float(candle.low),
                "close": float(candle.close),
            }
            session_base_context = _nan_context()
            if previous_stats is not None and previous_stats["close"] != 0:
                prev_close = previous_stats["close"]
                session_base_context["prev_session_close"] = prev_close
                session_base_context["prev_session_range_pct"] = (
                    (previous_stats["high"] - previous_stats["low"]) / prev_close * 100.0
                )
                session_base_context["gap_pct"] = (float(candle.open) - prev_close) / prev_close * 100.0
            session_base_context["is_expiry_session"] = 1.0 if _is_monthly_expiry_session(session) else 0.0

        context = dict(session_base_context)
        context["session_minute"] = _session_minute(candle.ts)
        enriched.append(replace(candle, context=context))

        if current_stats is not None:
            current_stats["high"] = max(current_stats["high"], float(candle.high))
            current_stats["low"] = min(current_stats["low"], float(candle.low))
            current_stats["close"] = float(candle.close)

    return enriched


def _operand_value(spec: Any, history: Sequence[Candle], params: dict) -> float | bool:
    if isinstance(spec, (int, float, bool)):
        return spec
    if isinstance(spec, str):
        return float(spec)
    if not isinstance(spec, dict):
        raise ValueError(f"invalid operand: {spec!r}")

    if "value" in spec:
        return spec["value"]
    if "param" in spec:
        name = str(spec["param"])
        if name not in params:
            raise ValueError(f"unknown parameter: {name}")
        return params[name]
    if "rolling" in spec:
        # Must be checked before "field": a rolling spec carries a "field" key
        # too, and falling into the field branch silently turns e.g.
        # "close > rolling mean(close)" into "close > close" (never true).
        return _rolling_value(spec, history)
    if "context" in spec:
        # Resolution order is explicit: context sits before generic field
        # handling, while rolling remains before both because rolling operands
        # also carry a field key.
        return _context_value(spec, history)
    if "field" in spec:
        return getattr(history[-1], str(spec["field"]))
    if "lag" in spec:
        periods = int(spec.get("periods", 1))
        if periods < 0:
            raise ValueError("lag periods cannot be negative")
        idx = len(history) - 1 - periods
        if idx < 0:
            return float("nan")
        return getattr(history[idx], str(spec["lag"]))
    raise ValueError(f"unknown operand: {spec!r}")


def _context_value(spec: dict, history: Sequence[Candle]) -> float:
    name = str(spec["context"])
    if name not in ALLOWED_CONTEXT_FIELDS:
        raise ValueError(f"unknown context field: {name}")
    value = history[-1].context.get(name, float("nan"))
    return float(value) if value is not None else float("nan")


def _rolling_value(spec: dict, history: Sequence[Candle]) -> float:
    fn = str(spec["rolling"])
    field = str(spec["field"])
    window = int(spec["window"])
    if window <= 0:
        raise ValueError("rolling window must be positive")
    if len(history) < window:
        return float("nan")
    vals = [float(getattr(c, field)) for c in history[-window:]]
    if fn == "mean":
        return sum(vals) / len(vals)
    if fn == "min":
        return min(vals)
    if fn == "max":
        return max(vals)
    if fn == "sum":
        return sum(vals)
    raise ValueError(f"unsupported rolling function: {fn}")


def evaluate_rule(rule: Any, history: Sequence[Candle], params: dict) -> bool:
    if not history:
        return False
    if isinstance(rule, bool):
        return rule
    if not isinstance(rule, dict):
        raise ValueError(f"invalid rule: {rule!r}")
    if "all" in rule:
        return all(evaluate_rule(item, history, params) for item in rule["all"])
    if "any" in rule:
        return any(evaluate_rule(item, history, params) for item in rule["any"])
    if "not" in rule:
        return not evaluate_rule(rule["not"], history, params)
    if "left" not in rule or "op" not in rule or "right" not in rule:
        raise ValueError(f"invalid comparison rule: {rule!r}")

    left = _operand_value(rule["left"], history, params)
    right = _operand_value(rule["right"], history, params)
    if isinstance(left, float) and math.isnan(left):
        return False
    if isinstance(right, float) and math.isnan(right):
        return False
    op = str(rule["op"])
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    raise ValueError(f"unsupported rule operator: {op}")


def _same_session(a: Candle, b: Candle) -> bool:
    return a.session_date == b.session_date


def _quote(symbol: str, price: float, ts: datetime) -> Quote:
    return Quote(symbol=symbol, price=price, timestamp=ts, is_stale=False, reject_reason=None)


def _fill(symbol: str, side: str, qty: float, price: float, ts: datetime):
    fill = simulate_fill(_quote(symbol, price, ts), side, qty, default_config().fees, product=PRODUCT)
    if not fill.is_executed:
        raise ValueError(fill.reject_reason or "fill rejected")
    return fill


def _qty_from_sizing(sizing_rule: dict, entry_quote: float, capital: float) -> int:
    kind = str(sizing_rule.get("type") or sizing_rule.get("kind"))
    if kind == "fixed_qty":
        qty = int(sizing_rule["qty"])
    elif kind == "max_affordable":
        fraction = float(sizing_rule.get("capital_fraction", 1.0))
        qty = int((capital * fraction) // entry_quote)
    else:
        raise ValueError(f"unsupported sizing rule: {kind}")
    if qty <= 0:
        raise ValueError("sizing rule produced no tradable quantity")
    return qty


def _stop_price(stop_rule: dict, entry_price: float, history: Sequence[Candle], params: dict) -> float:
    kind = str(stop_rule.get("type") or stop_rule.get("kind"))
    if kind == "fixed_pct":
        stop = entry_price * (1 - float(stop_rule["pct"]))
    elif kind == "fixed_points":
        stop = entry_price - float(stop_rule["points"])
    elif kind == "price":
        stop = float(_operand_value(stop_rule["value"], history, params))
    else:
        raise ValueError(f"unsupported stop rule: {kind}")
    if stop <= 0 or stop >= entry_price:
        raise ValueError(f"invalid long stop {stop} for entry {entry_price}")
    return round(stop, 2)


def _dataset(candles: Sequence[Candle]) -> dict:
    return {
        "start": candles[0].ts.isoformat() if candles else None,
        "end": candles[-1].ts.isoformat() if candles else None,
        "rows": len(candles),
        "data_hash": _hash_json([c.as_dict() for c in candles]),
        "source": "intraday_prices",
    }


def _max_drawdown(curve: Sequence[dict]) -> float:
    if not curve:
        return 0.0
    peak = float(curve[0]["equity"])
    max_dd = 0.0
    for point in curve:
        equity = float(point["equity"])
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, peak - equity)
    return round(max_dd, 2)


def _summarize(trades: Sequence[dict], equity_curve: Sequence[dict]) -> dict:
    gross = round(sum(t["gross_pnl"] for t in trades), 2)
    charges = round(sum(t["charges"] for t in trades), 2)
    slippage = round(sum(t["slippage"] for t in trades), 2)
    net = round(sum(t["net_pnl"] for t in trades), 2)
    notional = round(sum(t["entry_price"] * t["qty"] for t in trades), 2)
    net_edge_pct = round((net / notional * 100), 6) if notional else 0.0
    round_trip_cost_pct = round(((charges + slippage) / notional * 100), 6) if notional else 0.0
    required = round(round_trip_cost_pct * 3, 6)
    return {
        "trades": len(trades),
        "win_count": sum(1 for t in trades if t["net_pnl"] > 0),
        "gross_pnl": gross,
        "total_charges": charges,
        "total_slippage": slippage,
        "total_costs": round(charges + slippage, 2),
        "net_pnl": net,
        "max_drawdown": _max_drawdown(equity_curve),
        "net_edge_per_trade_pct_of_notional": net_edge_pct,
        "round_trip_cost_pct_of_notional": round_trip_cost_pct,
        "cost_bar_required_pct": required,
        "cost_bar_pass": bool(trades) and net_edge_pct >= required,
    }


def _result_hash(payload: dict) -> str:
    return _hash_json(payload)


def _persist_result(db_path: Path, candidate: ResearchCandidate, result: BacktestResult) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        ensure_backtest_tables(conn)
        cur = conn.execute(
            """
            INSERT INTO backtest_runs
                (created_at, stage, candidate_id, candidate_version, params_hash,
                 result_hash, status, dataset_start, dataset_end, data_rows,
                 summary_json, trades_json, equity_json, candidate_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(IST).isoformat(),
                result.stage,
                result.candidate_id,
                result.candidate_version,
                result.params_hash,
                result.result_hash,
                result.status,
                result.dataset.get("start"),
                result.dataset.get("end"),
                result.dataset.get("rows", 0),
                _canonical_json(result.summary),
                _canonical_json(result.trades),
                _canonical_json(result.equity_curve),
                candidate.to_json(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def replay_candidate(
    candidate: ResearchCandidate,
    candles: Sequence[Candle],
    *,
    stage: str = "IN_SAMPLE",
    persist: bool = True,
    db_path: str | Path = DB_PATH,
) -> BacktestResult:
    if stage not in STAGES:
        raise ValueError(f"invalid stage: {stage}")
    params = candidate.parameters_dict
    entry_rule = rule_to_dict(candidate.entry_rule)
    exit_rule = rule_to_dict(candidate.exit_rule)
    stop_rule = rule_to_dict(candidate.stop_rule)
    sizing_rule = rule_to_dict(candidate.sizing_rule)
    no_trade_rules = [rule_to_dict(rule) for rule in candidate.no_trade_conditions]
    candles = _contextualize_candles(list(candles))
    if len(candles) < 2:
        dataset = _dataset(candles)
        payload = {
            "stage": stage,
            "candidate": candidate.canonical_dict,
            "dataset": dataset,
            "trades": [],
            "equity_curve": [],
            "summary": {"trades": 0, "status_reason": "DATA_INSUFFICIENT"},
        }
        result = BacktestResult(
            stage=stage,
            status="DATA_INSUFFICIENT",
            candidate_id=candidate.id,
            candidate_version=candidate.version,
            params_hash=candidate.params_hash,
            result_hash=_result_hash(payload),
            dataset=dataset,
            trades=[],
            equity_curve=[],
            summary=payload["summary"],
        )
        if persist:
            _persist_result(Path(db_path), candidate, result)
        return result

    capital = CAPITAL_BASIS_INR
    equity = capital
    open_position: dict | None = None
    trades: list[dict] = []
    equity_curve = [{"ts": candles[0].ts.isoformat(), "equity": round(equity, 2)}]

    for i, candle in enumerate(candles):
        history = candles[: i + 1]
        next_candle = candles[i + 1] if i + 1 < len(candles) else None

        if open_position is not None:
            must_square_off = next_candle is None or not _same_session(candle, next_candle)
            stop_hit = candle.low <= open_position["stop_price"]
            exit_signal = evaluate_rule(exit_rule, history, params)
            if stop_hit or exit_signal or must_square_off:
                if must_square_off:
                    quote_price = candle.close
                    exit_ts = candle.ts
                    exit_reason = "SESSION_END"
                else:
                    quote_price = next_candle.open
                    exit_ts = next_candle.ts
                    exit_reason = "STOP" if stop_hit else "RULE_EXIT"
                sell = _fill(candidate.symbol, "SELL", open_position["qty"], quote_price, exit_ts)
                gross = round((sell.fill_price - open_position["entry_price"]) * open_position["qty"], 2)
                charges = round(open_position["entry_charges"] + sell.charges.total, 2)
                slippage = round(open_position["entry_slippage"] + sell.total_slippage, 2)
                net = round(gross - charges, 2)
                equity = round(equity + net, 2)
                trade = {
                    "symbol": candidate.symbol,
                    "entry_ts": open_position["entry_ts"].isoformat(),
                    "exit_ts": exit_ts.isoformat(),
                    "entry_price": open_position["entry_price"],
                    "exit_price": sell.fill_price,
                    "entry_quote_price": open_position["entry_quote_price"],
                    "exit_quote_price": quote_price,
                    "qty": open_position["qty"],
                    "gross_pnl": gross,
                    "charges": charges,
                    "slippage": slippage,
                    "net_pnl": net,
                    "exit_reason": exit_reason,
                    "stop_price": open_position["stop_price"],
                }
                trades.append(trade)
                equity_curve.append({"ts": exit_ts.isoformat(), "equity": equity})
                open_position = None
                if not must_square_off and next_candle is not None:
                    continue

        if open_position is None and next_candle is not None and _same_session(candle, next_candle):
            if any(evaluate_rule(rule, history, params) for rule in no_trade_rules):
                continue
            if not evaluate_rule(entry_rule, history, params):
                continue
            buy = _fill(candidate.symbol, "BUY", _qty_from_sizing(sizing_rule, next_candle.open, capital), next_candle.open, next_candle.ts)
            stop = _stop_price(stop_rule, buy.fill_price, history, params)
            open_position = {
                "qty": buy.qty,
                "entry_ts": next_candle.ts,
                "entry_price": buy.fill_price,
                "entry_quote_price": next_candle.open,
                "entry_charges": buy.charges.total,
                "entry_slippage": buy.total_slippage,
                "stop_price": stop,
            }

    dataset = _dataset(candles)
    summary = _summarize(trades, equity_curve)
    status = "PASS" if summary["net_pnl"] > 0 and summary["cost_bar_pass"] else "FAIL"
    payload = {
        "stage": stage,
        "candidate": candidate.canonical_dict,
        "dataset": dataset,
        "trades": trades,
        "equity_curve": equity_curve,
        "summary": summary,
        "status": status,
    }
    result = BacktestResult(
        stage=stage,
        status=status,
        candidate_id=candidate.id,
        candidate_version=candidate.version,
        params_hash=candidate.params_hash,
        result_hash=_result_hash(payload),
        dataset=dataset,
        trades=trades,
        equity_curve=equity_curve,
        summary=summary,
    )
    if persist:
        _persist_result(Path(db_path), candidate, result)
    return result


def run_backtest(
    candidate: ResearchCandidate,
    *,
    db_path: str | Path = DB_PATH,
    stage: str = "IN_SAMPLE",
    start: date | str | None = None,
    end: date | str | None = None,
    persist: bool = True,
) -> BacktestResult:
    candles = load_candles(db_path, candidate, start=start, end=end)
    return replay_candidate(candidate, candles, stage=stage, persist=persist, db_path=db_path)


def record_kill(db_path: str | Path, candidate: ResearchCandidate, reason: str) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        ensure_backtest_tables(conn)
        conn.execute(
            """
            INSERT INTO backtest_kills
                (created_at, candidate_id, candidate_version, params_hash, hypothesis_hash, reason)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(IST).isoformat(),
                candidate.id,
                candidate.version,
                candidate.params_hash,
                candidate.hypothesis_hash,
                reason,
            ),
        )
        conn.commit()


def assert_not_forbidden_by_kill_registry(db_path: str | Path, candidate: ResearchCandidate) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        ensure_backtest_tables(conn)
        rows = conn.execute(
            """
            SELECT candidate_version, params_hash, hypothesis_hash
            FROM backtest_kills
            WHERE candidate_id=?
            """,
            (candidate.id,),
        ).fetchall()
    if not rows:
        return
    killed_params = {row[1] for row in rows}
    if candidate.params_hash in killed_params:
        return
    killed_versions = {row[0] for row in rows}
    killed_hypotheses = {row[2] for row in rows}
    if candidate.version in killed_versions or candidate.hypothesis_hash in killed_hypotheses:
        raise ValueError(
            "candidate id was killed; changed params require a new version and a new hypothesis"
        )


def stage_passed(result: BacktestResult) -> bool:
    return result.status == "PASS" and result.summary.get("net_pnl", 0) > 0 and bool(result.summary.get("cost_bar_pass"))


def output_hash_for_candidate(candidate: ResearchCandidate) -> str:
    return candidate_hash(candidate)
