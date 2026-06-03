"""Deterministic tests for the 3 controlled entry-signal upgrades."""

from __future__ import annotations

import math

from bot.entry_policy import EntryConfig, decide_entry


def _call(**kw):
    args = dict(
        regime="TREND_UP", base_is_buy=True, price=100.0, atr=2.0, rsi=55.0,
        ema_fast=100.0, boll_lower=95.0, prior_high=99.0, volume=200.0, vol_sma=100.0,
        stop_distance=2.0, qty=50, charges=10.0, cfg=EntryConfig(),
    )
    args.update(kw)
    return decide_entry(**args)


# ── Baseline ─────────────────────────────────────────────────────────────────
def test_baseline_takes_on_buy_signal():
    action, payload = _call()
    assert action == "take" and payload.archetype == "baseline"


def test_baseline_skips_without_buy():
    action, _ = _call(base_is_buy=False)
    assert action == "skip"


# ── Upgrade 1: volume confirmation ───────────────────────────────────────────
def test_volume_confirmation_rejects_weak_volume():
    cfg = EntryConfig(volume_confirmation=True, vol_expansion_mult=1.2)
    action, reason = _call(cfg=cfg, volume=100.0, vol_sma=100.0)   # no expansion
    assert action == "reject" and reason == "weak_volume"


def test_volume_confirmation_allows_expansion():
    cfg = EntryConfig(volume_confirmation=True, vol_expansion_mult=1.2)
    action, _ = _call(cfg=cfg, volume=150.0, vol_sma=100.0)        # 1.5x > 1.2x
    assert action == "take"


# ── Upgrade 2: regime-specific entries ───────────────────────────────────────
def test_regime_trend_down_avoided():
    cfg = EntryConfig(regime_specific=True)
    action, reason = _call(cfg=cfg, regime="TREND_DOWN", base_is_buy=True)
    assert action == "reject" and reason == "trend_down_avoid"


def test_regime_range_requires_mean_reversion_setup():
    cfg = EntryConfig(regime_specific=True, rsi_oversold=35.0)
    # Not oversold / not at band -> skip
    assert _call(cfg=cfg, regime="RANGE", rsi=55.0, price=100.0, boll_lower=95.0)[0] == "skip"
    # Oversold AND at/below lower band -> take (mean reversion)
    action, payload = _call(cfg=cfg, regime="RANGE", rsi=28.0, price=94.0, boll_lower=95.0)
    assert action == "take" and payload.archetype == "mean_reversion"


def test_regime_trend_up_requires_continuation_setup():
    cfg = EntryConfig(regime_specific=True, pullback_atr=0.5)
    # Far from EMA and below prior high -> no setup
    assert _call(cfg=cfg, regime="TREND_UP", price=110.0, ema_fast=100.0,
                 atr=2.0, prior_high=120.0)[0] == "skip"
    # Breakout above prior high -> take
    action, payload = _call(cfg=cfg, regime="TREND_UP", price=121.0, ema_fast=100.0,
                            atr=2.0, prior_high=120.0)
    assert action == "take" and payload.archetype == "continuation"


# ── Upgrade 3: target/stop + charge guard ────────────────────────────────────
def test_charge_guard_rejects_expensive_trades():
    # target = price + 3*stop_distance = 100 + 6 = 106; reward_gross=(6)*50=300
    # charges 100 -> ratio 0.33 > 0.25 cap
    cfg = EntryConfig(target_r=3.0, max_charge_ratio=0.25)
    action, reason = _call(cfg=cfg, charges=100.0, stop_distance=2.0, qty=50)
    assert action == "reject" and reason == "charge_ratio"


def test_wider_target_carried_in_proposal():
    cfg = EntryConfig(target_r=3.0)
    action, payload = _call(cfg=cfg)
    assert action == "take" and payload.target_r == 3.0


def test_determinism():
    a = _call(cfg=EntryConfig(volume_confirmation=True), volume=150, vol_sma=100)
    b = _call(cfg=EntryConfig(volume_confirmation=True), volume=150, vol_sma=100)
    assert a[0] == b[0]


# ── Quality experiment: stricter cutoff / confluence / no-downtrend ──────────
def test_min_score_rejects_marginal():
    cfg = EntryConfig(min_score=0.72)
    # base_is_buy True (score>=0.65) but score 0.66 < 0.72 -> reject as marginal
    action, reason = _call(cfg=cfg, base_is_buy=True, entry_score=0.66)
    assert action == "reject" and reason == "below_min_score"


def test_min_score_allows_strong():
    cfg = EntryConfig(min_score=0.72)
    action, payload = _call(cfg=cfg, base_is_buy=True, entry_score=0.80)
    assert action == "take" and payload.archetype == "high_quality"


def test_confluence_requires_momentum_agreement():
    cfg = EntryConfig(require_confluence=True)
    # ema_fast < ema_slow OR red supertrend OR rsi out of band -> reject
    assert _call(cfg=cfg, ema_fast=100, ema_slow=101, st_trend="green", rsi=60)[1] == "no_confluence"
    assert _call(cfg=cfg, ema_fast=101, ema_slow=100, st_trend="red", rsi=60)[1] == "no_confluence"
    assert _call(cfg=cfg, ema_fast=101, ema_slow=100, st_trend="green", rsi=80)[1] == "no_confluence"
    # all agree -> take
    action, _ = _call(cfg=cfg, ema_fast=101, ema_slow=100, st_trend="green", rsi=60)
    assert action == "take"


def test_avoid_trend_down_rejects_long():
    cfg = EntryConfig(avoid_trend_down=True)
    action, reason = _call(cfg=cfg, regime="TREND_DOWN", base_is_buy=True)
    assert action == "reject" and reason == "trend_down_avoid"
    # other regimes unaffected
    assert _call(cfg=cfg, regime="TREND_UP", base_is_buy=True)[0] == "take"
