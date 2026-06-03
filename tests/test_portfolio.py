"""Portfolio tests."""
from datetime import datetime
import pytest
from pydantic import ValidationError

from bot.portfolio import Portfolio, Position, PortfolioState


@pytest.fixture
def fresh_pf():
    return Portfolio.fresh(starting_balance=50_000.0)


@pytest.fixture
def position():
    return Position(
        symbol="ADANIENT", qty=10, entry_price=2500.0,
        stop=2450.0, target=2600.0, charges_buy=15.0,
        entry_time=datetime.now(),
    )


def test_fresh_portfolio_initial_state(fresh_pf):
    assert fresh_pf.state.cash == 50_000.0
    assert fresh_pf.state.realized_pnl == 0.0
    assert fresh_pf.state.peak_equity == 50_000.0
    assert fresh_pf.state.positions == {}


def test_fresh_portfolio_equity_with_no_positions(fresh_pf):
    assert fresh_pf.equity({}) == 50_000.0


def test_fresh_portfolio_drawdown_is_zero(fresh_pf):
    assert fresh_pf.drawdown_pct({}) == 0.0


def test_buy_reduces_cash(fresh_pf, position):
    fresh_pf.add_position(position, cost=2500.0 * 10 + 15)
    assert fresh_pf.state.cash == pytest.approx(50_000 - 25_015, abs=0.01)


def test_buy_records_position(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    assert "ADANIENT" in fresh_pf.state.positions
    assert fresh_pf.state.positions["ADANIENT"].qty == 10


def test_buy_twice_same_symbol_raises(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    with pytest.raises(ValueError, match="Already have"):
        fresh_pf.add_position(position, cost=25_015)


def test_buy_exceeds_cash_raises(fresh_pf, position):
    with pytest.raises(ValueError, match="exceeds cash"):
        fresh_pf.add_position(position, cost=100_000)


def test_equity_includes_unrealized_gain(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    prices = {"ADANIENT": 2600.0}
    assert fresh_pf.equity(prices) == pytest.approx(50_985, abs=0.5)


def test_equity_reflects_unrealized_loss(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    prices = {"ADANIENT": 2400.0}
    assert fresh_pf.equity(prices) == pytest.approx(48_985, abs=0.5)


def test_unrealized_pnl_separate_from_realized(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    prices = {"ADANIENT": 2600.0}
    assert fresh_pf.unrealized_pnl(prices) == pytest.approx(1000.0)
    assert fresh_pf.state.realized_pnl == 0.0


def test_sell_at_profit_updates_realized_pnl(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    net = fresh_pf.close_position("ADANIENT", exit_price=2600.0, sell_charges=20.0)
    assert net == pytest.approx(965.0, abs=0.5)
    assert fresh_pf.state.realized_pnl == pytest.approx(965.0, abs=0.5)
    assert fresh_pf.state.total_trades == 1
    assert fresh_pf.state.winning_trades == 1


def test_sell_at_loss_does_not_count_as_winning(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    net = fresh_pf.close_position("ADANIENT", exit_price=2400.0, sell_charges=20.0)
    assert net < 0
    assert fresh_pf.state.total_trades == 1
    assert fresh_pf.state.winning_trades == 0


def test_sell_removes_position(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    fresh_pf.close_position("ADANIENT", exit_price=2500.0, sell_charges=20.0)
    assert "ADANIENT" not in fresh_pf.state.positions


def test_sell_nonexistent_position_raises(fresh_pf):
    with pytest.raises(ValueError, match="No open position"):
        fresh_pf.close_position("XYZ", exit_price=100.0, sell_charges=10.0)


def test_sell_credits_cash_correctly(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    fresh_pf.close_position("ADANIENT", exit_price=2600.0, sell_charges=20.0)
    assert fresh_pf.state.cash == pytest.approx(50_965, abs=0.5)


def test_drawdown_calculated_from_peak(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    fresh_pf.update_peak({"ADANIENT": 2700.0})
    assert fresh_pf.state.peak_equity > 50_000
    dd = fresh_pf.drawdown_pct({"ADANIENT": 2500.0})
    assert dd > 0


def test_drawdown_zero_when_at_peak(fresh_pf, position):
    fresh_pf.add_position(position, cost=25_015)
    fresh_pf.update_peak({"ADANIENT": 2600.0})
    assert fresh_pf.drawdown_pct({"ADANIENT": 2600.0}) == 0.0


def test_position_stop_must_be_below_entry():
    with pytest.raises(ValidationError, match="stop"):
        Position(
            symbol="X", qty=1, entry_price=100.0,
            stop=110.0, target=120.0, charges_buy=1.0,
            entry_time=datetime.now(),
        )


def test_position_qty_must_be_positive():
    with pytest.raises(ValidationError):
        Position(
            symbol="X", qty=0, entry_price=100.0,
            stop=90.0, target=110.0, charges_buy=1.0,
            entry_time=datetime.now(),
        )


def test_portfolio_winning_cannot_exceed_total():
    with pytest.raises(ValidationError, match="winning_trades"):
        PortfolioState(
            cash=1000, realized_pnl=0, peak_equity=1000,
            total_trades=1, winning_trades=5,
            created_at=datetime.now(), last_updated=datetime.now(),
        )


def test_portfolio_cash_cannot_be_negative():
    with pytest.raises(ValidationError):
        PortfolioState(
            cash=-100, realized_pnl=0, peak_equity=0,
            created_at=datetime.now(), last_updated=datetime.now(),
        )
