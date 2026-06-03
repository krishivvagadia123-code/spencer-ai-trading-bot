"""Deterministic tests for the Mistake Review Engine."""

from __future__ import annotations

from bot.mistake_review import (
    MistakeConfig, analyze, classify, setup_of, lookup_trust, _trust,
)


def _t(**kw):
    base = dict(symbol="X", regime="TREND_UP", entry_date="2024-01-01",
                exit_date="2024-01-03", entry=100.0, stop=98.0, target=106.0,
                exit=98.0, qty=50, entry_score=0.72, exit_reason="stop",
                bars_held=5, gross_pnl=-100.0, charges=10.0, pnl=-110.0)
    base.update(kw)
    return base


def _ctx(**kw):
    base = dict(bad_regimes=set(), bad_symbols=set(), bad_setups=set(),
                symbol_counts={}, reentry_after_loss=set())
    base.update(kw)
    return base


def test_setup_bands():
    cfg = MistakeConfig()
    assert setup_of(0.80, cfg) == "strong"
    assert setup_of(0.70, cfg) == "moderate"
    assert setup_of(0.66, cfg) == "marginal"
    assert setup_of(None, cfg) == "unknown"


def test_classify_weak_entry_and_bad_rr():
    cfg = MistakeConfig()
    # entry 100/stop 98/target 101 -> RR 0.5 (bad); score 0.66 (weak)
    t = _t(entry_score=0.66, target=101.0)
    rs = classify(t, _ctx(), cfg)
    assert "weak_entry" in rs and "bad_risk_reward" in rs


def test_classify_high_charges():
    cfg = MistakeConfig()
    # target reward = (106-100)*50 = 300; charges 80 -> 26% >= 20%
    rs = classify(_t(charges=80.0), _ctx(), cfg)
    assert "high_charges" in rs


def test_classify_stop_too_tight():
    cfg = MistakeConfig()
    # stopped in 1 bar with a 0.5% stop
    t = _t(entry=100.0, stop=99.6, exit_reason="stop", bars_held=1, target=102.0)
    rs = classify(t, _ctx(), cfg)
    assert "stop_too_tight" in rs


def test_classify_overtrading_and_bad_symbol_regime_setup():
    cfg = MistakeConfig()
    ctx = _ctx(bad_regimes={"TREND_UP"}, bad_symbols={"X"}, bad_setups={"moderate"},
               symbol_counts={"X": 99})
    rs = classify(_t(), ctx, cfg)
    for r in ("bad_regime", "bad_symbol", "bad_setup", "overtrading"):
        assert r in rs


def test_trust_is_down_only():
    cfg = MistakeConfig()
    assert _trust(50.0, -40.0, cfg) == 1.0          # positive expectancy -> neutral, not >1
    t = _trust(-9999.0, -40.0, cfg)
    assert cfg.trust_floor <= t <= 1.0 and t == cfg.trust_floor


def test_lookup_trust_takes_minimum_and_defaults_neutral():
    trust = {
        "symbol": {"X": {"trust": 0.4}},
        "regime": {"TREND_UP": {"trust": 0.8}},
        "setup":  {"strong": {"trust": 1.0}},
    }
    # min of 0.4/0.8/1.0 = 0.4; unknown strategy defaults to 1.0 (neutral)
    assert lookup_trust(trust, symbol="X", regime="TREND_UP", strategy="zzz", setup="strong") == 0.4
    # nothing known -> fully neutral
    assert lookup_trust(trust, symbol="UNKNOWN") == 1.0


def test_analyze_thin_sample_stays_neutral():
    cfg = MistakeConfig(min_sample=20)
    trades = [_t(symbol="THIN", pnl=-100.0) for _ in range(5)]  # < min_sample
    rep = analyze(trades, cfg)
    assert rep["trust_tables"]["symbol"]["THIN"]["trust"] == 1.0
    assert rep["trust_tables"]["symbol"]["THIN"]["sufficient"] is False


def test_analyze_sufficient_losing_symbol_downweighted():
    cfg = MistakeConfig(min_sample=20)
    trades = [_t(symbol="LOSE", pnl=-100.0) for _ in range(25)]
    rep = analyze(trades, cfg)
    assert rep["trust_tables"]["symbol"]["LOSE"]["trust"] < 1.0
    # All losers share the same reasons -> should-have-rejected removes net loss.
    assert rep["should_have_been_rejected"]["net_pnl_removed"] <= 0
