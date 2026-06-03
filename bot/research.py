"""
Cached daily research.

Why this exists: fundamentals / sentiment / liquidity do not move
intra-minute. Fetching them inside the intraday scan loop wastes tokens,
API quota, and latency. We fetch ONCE per (symbol, asof_date) and persist
the snapshot. Every subsequent intraday scan reads the cached row.

No LLM is called from any function in this module's hot path. The provider
protocol is intentionally synchronous and side-effect-isolated so we can
swap a real fundamentals API in later without touching the scanner.

Design constraints (Phase H.1):
  - Pure / deterministic scoring functions (testable, auditable).
  - Cache check happens BEFORE provider.fetch() is called — true once/day.
  - Stub default provider returns neutral source_data; real providers plug
    in via dependency injection (see scanner.scan_once).
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Protocol, Tuple

from bot.db import get_conn
from bot.logger_config import get_logger

log = get_logger("kite-bot.research")


# ── Snapshot model ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ResearchSnapshot:
    id:                  Optional[int]   # None until persisted
    symbol:              str
    asof:                date
    source_data:         dict
    fundamentals_score:  float
    sentiment_score:     float
    liquidity_score:     float
    computed_at:         datetime


# ── Provider protocol ────────────────────────────────────────────────────────
class ResearchProvider(Protocol):
    """
    Fetches raw research data for one symbol/day. Must be idempotent for a
    given (symbol, asof). Return value is opaque dict; scoring is separate.
    Implementations may call external APIs — but the cache layer ensures
    .fetch() runs AT MOST once per (symbol, asof).
    """
    def fetch(self, symbol: str, asof: date) -> dict: ...


class NeutralResearchProvider:
    """
    Default provider — returns neutral source_data and no external calls.
    Useful as a baseline so Phase H.1 ships without committing to a data
    source. Real providers (FundamentalsAPIProvider, NewsLLMProvider, ...)
    can be added in Phase H.2.
    """
    def fetch(self, symbol: str, asof: date) -> dict:
        return {
            "provider": "neutral",
            "symbol": symbol,
            "asof": asof.isoformat(),
            "placeholder": True,
        }


# ── Scoring (pure, deterministic) ────────────────────────────────────────────
def score_source_data(source: dict) -> Tuple[float, float, float]:
    """
    Pure: (source_data dict) → (fundamentals, sentiment, liquidity) ∈ [0, 1].

    Recognized keys (any subset; missing keys default to neutral 0.5):
      fundamentals_raw: float in [0,1] OR dict with "score" key
      sentiment_raw:    float in [0,1]
      liquidity_raw:    float in [0,1] OR dict with "avg_volume" + "ref_volume"
    """
    fundamentals = _read_score(source, "fundamentals_raw")
    sentiment    = _read_score(source, "sentiment_raw")
    liquidity    = _read_score(source, "liquidity_raw")
    return _clip(fundamentals), _clip(sentiment), _clip(liquidity)


def _read_score(source: dict, key: str) -> float:
    if key not in source:
        return 0.5
    v = source[key]
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict) and "score" in v:
        return float(v["score"])
    return 0.5


def _clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


# ── Cache + persistence ──────────────────────────────────────────────────────
def _load_cached(symbol: str, asof: date) -> Optional[ResearchSnapshot]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, symbol, asof, source_data, fundamentals_score, "
            "       sentiment_score, liquidity_score, computed_at "
            "FROM research_snapshots WHERE symbol = ? AND asof = ?",
            (symbol, asof.isoformat()),
        ).fetchone()
    if row is None:
        return None
    return ResearchSnapshot(
        id=row["id"], symbol=row["symbol"],
        asof=date.fromisoformat(row["asof"]),
        source_data=json.loads(row["source_data"]),
        fundamentals_score=row["fundamentals_score"],
        sentiment_score=row["sentiment_score"],
        liquidity_score=row["liquidity_score"],
        computed_at=datetime.fromisoformat(row["computed_at"]),
    )


def _persist(symbol: str, asof: date, source: dict, fund: float,
             sent: float, liq: float) -> ResearchSnapshot:
    computed_at = datetime.now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO research_snapshots "
            "(symbol, asof, source_data, fundamentals_score, sentiment_score, "
            " liquidity_score, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (symbol, asof.isoformat(), json.dumps(source, sort_keys=True),
             fund, sent, liq, computed_at.isoformat()),
        )
        new_id = cur.lastrowid
    return ResearchSnapshot(
        id=new_id, symbol=symbol, asof=asof, source_data=source,
        fundamentals_score=fund, sentiment_score=sent, liquidity_score=liq,
        computed_at=computed_at,
    )


def get_or_fetch(symbol: str, asof: date,
                 provider: ResearchProvider) -> ResearchSnapshot:
    """
    Idempotent daily cache. Returns existing snapshot if present;
    otherwise calls provider.fetch(), scores, persists, returns.

    Critically: when cache hits, provider.fetch() is NOT called.
    """
    cached = _load_cached(symbol, asof)
    if cached is not None:
        return cached
    source = provider.fetch(symbol, asof)
    fund, sent, liq = score_source_data(source)
    snap = _persist(symbol, asof, source, fund, sent, liq)
    log.info(f"research cached: {symbol}@{asof.isoformat()} "
             f"fund={fund:.2f} sent={sent:.2f} liq={liq:.2f}")
    return snap


def list_snapshots_for_date(asof: date) -> list:
    """Read-only: list all snapshots for one asof date (for dashboard)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, symbol, asof, fundamentals_score, sentiment_score, "
            "       liquidity_score, computed_at FROM research_snapshots "
            "WHERE asof = ? ORDER BY symbol",
            (asof.isoformat(),),
        ).fetchall()
    return [dict(r) for r in rows]
