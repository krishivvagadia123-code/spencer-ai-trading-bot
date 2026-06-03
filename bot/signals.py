"""
Pure signal engine — pre-trade scoring + classification.

NO external calls. NO LLM. NO randomness. Same inputs → same outputs.

Public surface:
  TechnicalSnapshot       — minimal indicator inputs from the scanner.
  ScoreBundle             — 5 component scores + total.
  SignalCandidate         — full record (immutable) returned to scanner.
  Signal                  — enum: BUY_CANDIDATE / SELL_CANDIDATE / HOLD / REJECTED.

  compute_technical_score, compute_risk_score, compute_total_score
  classify_signal, build_candidate

All scoring functions return values in [0, 1]. Higher = stronger bullish
opportunity. risk_score is inverted internally (high stop_distance → low score).
"""

from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class Signal(str, Enum):
    BUY_CANDIDATE  = "BUY_CANDIDATE"
    SELL_CANDIDATE = "SELL_CANDIDATE"
    HOLD           = "HOLD"
    REJECTED       = "REJECTED"


@dataclass(frozen=True)
class TechnicalSnapshot:
    price:            float
    rsi:              Optional[float] = None     # 0..100
    ema_fast:         Optional[float] = None
    ema_slow:         Optional[float] = None
    supertrend_trend: Optional[str]   = None     # "green" / "red"
    vwap:             Optional[float] = None
    atr:              Optional[float] = None     # absolute price units

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class ScoreBundle:
    technical:    float
    sentiment:    float
    fundamentals: float
    liquidity:    float
    risk:         float
    total:        float


@dataclass(frozen=True)
class SizingPreview:
    qty:           float
    stop_distance: float
    expected_loss: float
    rejected:      bool
    reasons:       List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SignalCandidate:
    ts:                   datetime
    symbol:               str
    signal:               Signal
    scores:               ScoreBundle
    indicators:           dict
    research_snapshot_id: Optional[int]
    entry_blocked:        bool
    block_reasons:        List[str]
    sizing_preview:       Optional[SizingPreview]
    rejection_reason:     Optional[str]

    def as_log_row(self) -> dict:
        """Flatten to dict suitable for DB persistence."""
        return {
            "ts":                  self.ts.isoformat(timespec="seconds"),
            "symbol":              self.symbol,
            "signal":              self.signal.value,
            "total_score":         self.scores.total,
            "technical_score":     self.scores.technical,
            "sentiment_score":     self.scores.sentiment,
            "fundamentals_score":  self.scores.fundamentals,
            "liquidity_score":     self.scores.liquidity,
            "risk_score":          self.scores.risk,
            "indicators":          json.dumps(self.indicators, sort_keys=True),
            "research_snapshot_id": self.research_snapshot_id,
            "entry_blocked":       1 if self.entry_blocked else 0,
            "block_reasons":       json.dumps(self.block_reasons),
            "sizing_preview":      json.dumps(asdict(self.sizing_preview))
                                    if self.sizing_preview else None,
            "rejection_reason":    self.rejection_reason,
        }


# ── Score components ─────────────────────────────────────────────────────────
def compute_technical_score(snap: TechnicalSnapshot) -> float:
    """
    Equal-weighted across whichever indicators are populated.
    Each indicator contributes 0..1.

      RSI               → linearly mapped 0→0, 50→0.5, 100→1
      EMA fast > slow   → 1 if true else 0
      Supertrend trend  → green=1, red=0
      Price > VWAP      → 1 if true else 0
    """
    comps: List[float] = []
    if snap.rsi is not None:
        if 52 <= snap.rsi <= 64:
            rsi_score = 1.0
        elif 45 <= snap.rsi < 52:
            rsi_score = (snap.rsi - 45) / 7
        elif 64 < snap.rsi <= 75:
            rsi_score = 1.0 - ((snap.rsi - 64) / 11) * 0.55
        else:
            rsi_score = 0.0
        comps.append(_clip(rsi_score))
    if snap.ema_fast is not None and snap.ema_slow is not None:
        comps.append(1.0 if snap.ema_fast > snap.ema_slow else 0.0)
    if snap.supertrend_trend == "green":
        comps.append(1.0)
    elif snap.supertrend_trend == "red":
        comps.append(0.0)
    if snap.vwap is not None:
        comps.append(1.0 if snap.price > snap.vwap else 0.0)
    if not comps:
        return 0.5
    return round(sum(comps) / len(comps), 4)


def compute_risk_score(price: float, atr: Optional[float]) -> float:
    """
    Inverse of normalized volatility: tight ATR (low % of price) → higher
    risk_score (less volatile → more risk-adjusted opportunity).

    atr_pct = atr / price. Mapped: 0% → 1.0, 5%+ → 0.0, linear.
    Missing ATR → 0.5 (neutral).
    """
    if atr is None or price <= 0:
        return 0.5
    atr_pct = atr / price
    score = 1.0 - (atr_pct / 0.05)
    return round(_clip(score), 4)


def compute_total_score(*, technical: float, sentiment: float,
                        fundamentals: float, liquidity: float,
                        risk: float) -> float:
    """
    Weighted sum. Weights chosen so technical dominates the intraday
    decision while research + risk supply slower signals.
    """
    total = (
        0.40 * technical
        + 0.15 * sentiment
        + 0.20 * fundamentals
        + 0.10 * liquidity
        + 0.15 * risk
    )
    return round(_clip(total), 4)


# ── Classification ───────────────────────────────────────────────────────────
BUY_THRESHOLD  = 0.65
SELL_THRESHOLD = 0.35


def classify_signal(*, total_score: float, has_position: bool,
                    entry_blocked: bool) -> Signal:
    """
    Classification policy:
      no position + entry_blocked       → REJECTED
      no position + score >= BUY_TH     → BUY_CANDIDATE
      no position + score <  BUY_TH     → HOLD
      has position + score <= SELL_TH   → SELL_CANDIDATE
      has position + score >  SELL_TH   → HOLD
    """
    if not has_position:
        if entry_blocked:
            return Signal.REJECTED
        return Signal.BUY_CANDIDATE if total_score >= BUY_THRESHOLD else Signal.HOLD
    return Signal.SELL_CANDIDATE if total_score <= SELL_THRESHOLD else Signal.HOLD


# ── Builder ──────────────────────────────────────────────────────────────────
def build_candidate(
    *,
    ts:                   datetime,
    symbol:               str,
    tech:                 TechnicalSnapshot,
    fundamentals_score:   float,
    sentiment_score:      float,
    liquidity_score:      float,
    has_position:         bool,
    entry_blocked:        bool,
    block_reasons:        List[str],
    research_snapshot_id: Optional[int],
    sizing_preview:       Optional[SizingPreview],
    rejection_reason:     Optional[str] = None,
) -> SignalCandidate:
    technical = compute_technical_score(tech)
    risk      = compute_risk_score(tech.price, tech.atr)
    total     = compute_total_score(
        technical=technical, sentiment=sentiment_score,
        fundamentals=fundamentals_score, liquidity=liquidity_score, risk=risk,
    )
    scores = ScoreBundle(
        technical=technical, sentiment=sentiment_score,
        fundamentals=fundamentals_score, liquidity=liquidity_score,
        risk=risk, total=total,
    )
    signal = classify_signal(total_score=total, has_position=has_position,
                             entry_blocked=entry_blocked)
    return SignalCandidate(
        ts=ts, symbol=symbol, signal=signal,
        scores=scores, indicators=tech.as_dict(),
        research_snapshot_id=research_snapshot_id,
        entry_blocked=entry_blocked, block_reasons=list(block_reasons),
        sizing_preview=sizing_preview, rejection_reason=rejection_reason,
    )


def _clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))
