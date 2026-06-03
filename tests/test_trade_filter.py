"""Deterministic unit tests for the 6-rule anti-overtrading filter."""

from __future__ import annotations

from bot.trade_filter import TradeFilterConfig, evaluate_trade


def _base(**kw):
    """A trade that PASSES every rule by default; override one field per test."""
    args = dict(
        trust=0.8, entry=100.0, stop=98.0, target=106.0, qty=100, charges=20.0,
        trades_today=0, sessions_since_loss=None, cfg=TradeFilterConfig(),
    )
    args.update(kw)
    return evaluate_trade(**args)


def test_clean_trade_accepted():
    d = _base()
    assert d.accepted, d.reasons


def test_rule1_low_trust_rejected():
    d = _base(trust=0.25)
    assert not d.accepted and d.checks["min_trust"] is False


def test_rule2_low_rr_rejected():
    # target only 1 above entry, stop 2 below -> RR 0.5
    d = _base(entry=100, stop=98, target=101)
    assert not d.accepted and d.checks["min_rr"] is False


def test_rule3_edge_after_charges_rejected():
    # Huge charges wipe the edge below 1R even though RR looks fine.
    d = _base(charges=550.0)   # risk_value=(100-98)*100=200; reward_gross=600; net=50 -> 0.25R
    assert not d.accepted and d.checks["min_edge_r"] is False


def test_rule4_daily_cap_rejected():
    d = _base(trades_today=3, cfg=TradeFilterConfig(max_trades_per_day=3))
    assert not d.accepted and d.checks["max_trades_per_day"] is False


def test_rule5_cooldown_rejected_then_allowed():
    cfg = TradeFilterConfig(loss_cooldown_days=3)
    assert not _base(sessions_since_loss=1, cfg=cfg).accepted     # too soon
    assert _base(sessions_since_loss=3, cfg=cfg).accepted          # cooldown elapsed


def test_rule6_charge_ratio_rejected():
    # charges 200 of gross target profit 600 = 33% > 25% cap; keep edge ok via big qty.
    d = _base(qty=1000, charges=2000.0,
              cfg=TradeFilterConfig(max_charge_ratio=0.25, min_edge_r=0.0))
    assert not d.accepted and d.checks["charge_ratio"] is False


def test_filter_can_only_reject_never_force():
    # An accepted decision lists no reasons; a rejected one always explains itself.
    ok = _base()
    bad = _base(trust=0.0)
    assert ok.accepted and ok.reasons == []
    assert (not bad.accepted) and len(bad.reasons) >= 1


def test_determinism():
    a = _base(trust=0.4)
    b = _base(trust=0.4)
    assert a.accepted == b.accepted and a.reasons == b.reasons and a.checks == b.checks
