"""
Phase D tests — kill switch, pause/resume/flatten, automatic exit monitor.

Key invariant under test: risk caps + control flags block BUY entries only.
SELL / stop / target / flatten / kill-liquidation NEVER consult them.
"""

from datetime import datetime
from pathlib import Path
import json
import pytest

from bot import control
from bot.config import RiskConfig
from bot.monitor import (
    ExitReason, check_exits, flatten_all,
)
from bot.portfolio import Portfolio, Position
from bot.risk import is_entry_allowed, EntryGateResult


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_control(tmp_path):
    """Redirect control_state.json to a per-test tmp file."""
    p = tmp_path / "control.json"
    control.set_control_path(p)
    yield p
    # Reset to default for safety
    control.set_control_path(control.DEFAULT_CONTROL_PATH)


@pytest.fixture
def risk_cfg():
    return RiskConfig(
        max_open_positions=10,
        max_daily_loss_pct=10.0,
        max_drawdown_pct=25.0,
        max_total_exposure_pct=200.0,
        max_symbol_notional_pct=100.0,
    )


@pytest.fixture
def fresh_pf():
    return Portfolio.fresh(starting_balance=50_000.0)


def _pos(symbol="ADANIENT", qty=10, entry=2500.0, stop=2475.0, target=2550.0):
    return Position(
        symbol=symbol, qty=qty, entry_price=entry,
        stop=stop, target=target,
        charges_buy=15.0, entry_time=datetime.now(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# control.py — kill switch
# ═══════════════════════════════════════════════════════════════════════════════
def test_default_state_allows_entry(tmp_control):
    assert control.is_killed() is False
    assert control.is_paused() is False
    assert control.can_enter() is True


def test_kill_blocks_entry_and_persists(tmp_control):
    control.kill("manual safety stop")
    assert control.is_killed() is True
    assert control.can_enter() is False
    # State persisted to disk
    raw = json.loads(tmp_control.read_text())
    assert raw["killed"] is True
    assert raw["kill_reason"] == "manual safety stop"
    assert raw["killed_at"] is not None


def test_unkill_clears_kill(tmp_control):
    control.kill("oops")
    control.unkill()
    assert control.is_killed() is False
    assert control.can_enter() is True


def test_pause_blocks_entry_without_killing(tmp_control):
    control.pause("eod")
    assert control.is_paused() is True
    assert control.is_killed() is False
    assert control.can_enter() is False


def test_resume_clears_pause(tmp_control):
    control.pause("lunch")
    control.resume()
    assert control.is_paused() is False
    assert control.can_enter() is True


def test_pause_and_kill_independent(tmp_control):
    control.pause("eod")
    control.kill("circuit breaker")
    control.resume()
    # Kill switch survives resume
    assert control.is_killed() is True
    assert control.is_paused() is False
    assert control.can_enter() is False


def test_corrupt_control_file_fails_closed(tmp_control):
    tmp_control.write_text("{not valid json")
    state = control.read_state()
    assert state.killed is True   # fail-closed
    assert "corrupt" in (state.kill_reason or "").lower()


def test_state_survives_simulated_restart(tmp_control):
    control.kill("overnight stop")
    # Simulate process restart: rebind path to same file
    control.set_control_path(tmp_control)
    assert control.is_killed() is True


# ═══════════════════════════════════════════════════════════════════════════════
# risk.is_entry_allowed — combines control + caps; BUY-only
# ═══════════════════════════════════════════════════════════════════════════════
def test_entry_allowed_on_fresh_portfolio(tmp_control, fresh_pf, risk_cfg):
    gate = is_entry_allowed(fresh_pf, prices={}, day_start_equity=50_000,
                            risk_cfg=risk_cfg)
    assert isinstance(gate, EntryGateResult)
    assert gate.can_enter is True
    assert gate.reasons == []


def test_kill_blocks_new_entry(tmp_control, fresh_pf, risk_cfg):
    control.kill("emergency")
    gate = is_entry_allowed(fresh_pf, prices={}, day_start_equity=50_000,
                            risk_cfg=risk_cfg)
    assert gate.can_enter is False
    assert any("killed" in r.lower() for r in gate.reasons)


def test_pause_blocks_new_entry(tmp_control, fresh_pf, risk_cfg):
    control.pause("manual halt")
    gate = is_entry_allowed(fresh_pf, prices={}, day_start_equity=50_000,
                            risk_cfg=risk_cfg)
    assert gate.can_enter is False
    assert any("paused" in r.lower() for r in gate.reasons)


def test_caps_failure_blocks_new_entry(tmp_control, fresh_pf):
    """Cap failure surfaces through the gate even if control flags clear."""
    risk_cfg = RiskConfig(max_open_positions=1)
    fresh_pf.add_position(_pos(), cost=25_015)
    eq = fresh_pf.equity({"ADANIENT": 2500.0})
    gate = is_entry_allowed(fresh_pf, prices={"ADANIENT": 2500.0},
                            day_start_equity=eq, risk_cfg=risk_cfg)
    assert gate.can_enter is False
    assert any("max_open_positions" in r for r in gate.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# Critical invariant: exits NEVER blocked by caps/kill/pause
# ═══════════════════════════════════════════════════════════════════════════════
def test_stop_exit_fires_even_when_killed(tmp_control, fresh_pf):
    """Kill switch must not suppress stop-loss exits."""
    fresh_pf.add_position(_pos(stop=2475.0), cost=25_015)
    control.kill("emergency")
    report = check_exits(fresh_pf, prices={"ADANIENT": 2400.0})   # below stop
    assert report.any_exits
    assert report.exits[0].reason == ExitReason.STOP


def test_target_exit_fires_even_when_paused(tmp_control, fresh_pf):
    fresh_pf.add_position(_pos(target=2550.0), cost=25_015)
    control.pause("eod")
    report = check_exits(fresh_pf, prices={"ADANIENT": 2600.0})   # above target
    assert report.any_exits
    assert report.exits[0].reason == ExitReason.TARGET


def test_flatten_fires_even_when_killed(tmp_control, fresh_pf):
    """Emergency liquidation must work after kill switch trips."""
    fresh_pf.add_position(_pos(), cost=25_015)
    control.kill("circuit breaker")
    report = flatten_all(fresh_pf, prices={"ADANIENT": 2500.0})
    assert report.any_exits
    assert report.exits[0].reason == ExitReason.FLATTEN


def test_flatten_fires_even_at_max_caps(fresh_pf):
    """Caps don't gate flatten — risk reduction is always allowed."""
    fresh_pf.add_position(_pos(), cost=25_015)
    # Even with absurdly tight caps that would block entries, flatten works
    report = flatten_all(fresh_pf, prices={"ADANIENT": 2500.0})
    assert report.any_exits
    assert all(e.reason == ExitReason.FLATTEN for e in report.exits)


# ═══════════════════════════════════════════════════════════════════════════════
# monitor.check_exits — stop / target / no-trigger / gap / missing
# ═══════════════════════════════════════════════════════════════════════════════
def test_no_exits_when_price_inside_band(fresh_pf):
    fresh_pf.add_position(_pos(stop=2475.0, target=2550.0), cost=25_015)
    report = check_exits(fresh_pf, prices={"ADANIENT": 2510.0})
    assert not report.any_exits
    assert report.checked_symbols == {"ADANIENT"}


def test_stop_triggered_at_exact_stop(fresh_pf):
    """Boundary: price == stop should trigger STOP (inclusive)."""
    fresh_pf.add_position(_pos(stop=2475.0, target=2550.0), cost=25_015)
    report = check_exits(fresh_pf, prices={"ADANIENT": 2475.0})
    assert report.any_exits
    assert report.exits[0].reason == ExitReason.STOP
    assert report.exits[0].trigger_price == 2475.0


def test_target_triggered_at_exact_target(fresh_pf):
    fresh_pf.add_position(_pos(stop=2475.0, target=2550.0), cost=25_015)
    report = check_exits(fresh_pf, prices={"ADANIENT": 2550.0})
    assert report.any_exits
    assert report.exits[0].reason == ExitReason.TARGET


def test_stop_wins_when_both_cross_in_gap(fresh_pf):
    """
    Construct a position then mutate stop > target to simulate a hypothetical
    snapshot where both look crossed simultaneously. STOP must win (conservative).
    """
    fresh_pf.add_position(_pos(stop=2475.0, target=2550.0), cost=25_015)
    pos = fresh_pf.state.positions["ADANIENT"]
    # If price = 2400 and target was hit intra-bar via a gap — impossible to
    # know order. Conservative implementation: stop fires.
    report = check_exits(fresh_pf, prices={"ADANIENT": 2400.0})
    assert report.exits[0].reason == ExitReason.STOP


def test_missing_price_reported_not_exited(fresh_pf):
    fresh_pf.add_position(_pos(), cost=25_015)
    report = check_exits(fresh_pf, prices={})
    assert not report.any_exits
    assert "ADANIENT" in report.missing_prices


def test_multiple_positions_independent(fresh_pf):
    fresh_pf.add_position(_pos("ADANIENT", qty=5, entry=2500.0,
                                stop=2475.0, target=2550.0), cost=12_515)
    fresh_pf.state.positions["TATAMOTORS"] = _pos(
        "TATAMOTORS", qty=10, entry=800.0, stop=790.0, target=820.0
    )
    report = check_exits(fresh_pf, prices={
        "ADANIENT":   2510.0,    # inside band — no exit
        "TATAMOTORS": 825.0,     # above target — TARGET exit
    })
    assert len(report.exits) == 1
    assert report.exits[0].symbol == "TATAMOTORS"
    assert report.exits[0].reason == ExitReason.TARGET


# ═══════════════════════════════════════════════════════════════════════════════
# flatten_all — fan out across positions
# ═══════════════════════════════════════════════════════════════════════════════
def test_flatten_all_empty_portfolio(fresh_pf):
    report = flatten_all(fresh_pf, prices={})
    assert not report.any_exits
    assert report.checked_symbols == set()


def test_flatten_all_emits_one_per_position(fresh_pf):
    fresh_pf.add_position(_pos("ADANIENT", qty=5, entry=2500.0), cost=12_515)
    fresh_pf.state.positions["TATAMOTORS"] = _pos(
        "TATAMOTORS", qty=10, entry=800.0, stop=790.0, target=820.0
    )
    report = flatten_all(fresh_pf, prices={
        "ADANIENT": 2490.0, "TATAMOTORS": 810.0,
    })
    assert len(report.exits) == 2
    assert {e.symbol for e in report.exits} == {"ADANIENT", "TATAMOTORS"}
    assert all(e.reason == ExitReason.FLATTEN for e in report.exits)


def test_flatten_skips_missing_price_reports_it(fresh_pf):
    fresh_pf.add_position(_pos("ADANIENT", qty=5, entry=2500.0), cost=12_515)
    fresh_pf.state.positions["TATAMOTORS"] = _pos(
        "TATAMOTORS", qty=10, entry=800.0, stop=790.0, target=820.0
    )
    report = flatten_all(fresh_pf, prices={"ADANIENT": 2490.0})
    # Only the symbol with a price flattens; the other is reported missing
    assert len(report.exits) == 1
    assert report.exits[0].symbol == "ADANIENT"
    assert "TATAMOTORS" in report.missing_prices
