"""
Portfolio — separates cash, realized P&L, unrealized P&L, equity.
Fail-closed on missing market prices: NEVER silently substitutes entry_price.
"""

from typing import Dict, Set
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class MissingPriceError(ValueError):
    """Raised when a required current-market price is not provided.
    Includes the set of missing symbols for callers to act on."""

    def __init__(self, missing: Set[str]):
        self.missing = set(missing)
        super().__init__(
            f"Missing market price(s) for: {sorted(self.missing)}. "
            f"Risk checks must never use entry_price as a fallback."
        )


class Position(BaseModel):
    symbol:      str
    # qty is float to allow fractional crypto sizing (e.g. 0.0025 BTC).
    # For equity products the engine rounds qty to int before constructing
    # a Position (NSE doesn't trade fractional shares). Pydantic still
    # rejects qty <= 0 here.
    qty:         float = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop:        float = Field(gt=0)
    target:      float = Field(gt=0)
    charges_buy: float = Field(ge=0)
    entry_time:  datetime

    @field_validator("stop")
    @classmethod
    def stop_below_entry_for_long(cls, v, info):
        entry = info.data.get("entry_price")
        if entry and v >= entry:
            raise ValueError(f"stop ({v}) must be below entry_price ({entry}) for long position")
        return v


class PortfolioState(BaseModel):
    cash:           float = Field(ge=0)
    realized_pnl:   float = Field(0.0)
    peak_equity:    float = Field(ge=0)
    total_trades:   int   = Field(0, ge=0)
    winning_trades: int   = Field(0, ge=0)
    positions:      Dict[str, Position] = Field(default_factory=dict)
    created_at:     datetime
    last_updated:   datetime

    @field_validator("winning_trades")
    @classmethod
    def winning_le_total(cls, v, info):
        total = info.data.get("total_trades", 0)
        if v > total:
            raise ValueError(f"winning_trades ({v}) > total_trades ({total})")
        return v


class Portfolio:
    def __init__(self, state: PortfolioState):
        self.state = state

    @classmethod
    def fresh(cls, starting_balance: float) -> "Portfolio":
        now = datetime.now()
        return cls(PortfolioState(
            cash=starting_balance, realized_pnl=0.0,
            peak_equity=starting_balance, total_trades=0, winning_trades=0,
            positions={}, created_at=now, last_updated=now,
        ))

    # ── Price-coverage helpers ────────────────────────────────────────────────
    def missing_prices(self, prices: Dict[str, float]) -> Set[str]:
        """Return set of open-position symbols not present in `prices`."""
        return {sym for sym in self.state.positions if sym not in prices}

    def _require_prices(self, prices: Dict[str, float]) -> None:
        missing = self.missing_prices(prices)
        if missing:
            raise MissingPriceError(missing)

    # ── Derived values — all fail closed ──────────────────────────────────────
    def positions_market_value(self, prices: Dict[str, float]) -> float:
        """Sum of qty * current_price. Raises MissingPriceError if any symbol missing."""
        self._require_prices(prices)
        total = 0.0
        for sym, pos in self.state.positions.items():
            total += pos.qty * prices[sym]
        return round(total, 2)

    def unrealized_pnl(self, prices: Dict[str, float]) -> float:
        """Raises MissingPriceError if any symbol missing."""
        self._require_prices(prices)
        total = 0.0
        for sym, pos in self.state.positions.items():
            total += (prices[sym] - pos.entry_price) * pos.qty
        return round(total, 2)

    def equity(self, prices: Dict[str, float]) -> float:
        """Total equity = cash + market value. Raises MissingPriceError if any missing."""
        return round(self.state.cash + self.positions_market_value(prices), 2)

    def gross_exposure(self, prices: Dict[str, float]) -> float:
        return abs(self.positions_market_value(prices))

    def drawdown_pct(self, prices: Dict[str, float]) -> float:
        eq = self.equity(prices)
        if self.state.peak_equity <= 0 or eq >= self.state.peak_equity:
            return 0.0
        return (self.state.peak_equity - eq) / self.state.peak_equity * 100

    def update_peak(self, prices: Dict[str, float]) -> None:
        eq = self.equity(prices)
        if eq > self.state.peak_equity:
            self.state.peak_equity = eq

    @property
    def total_pnl(self) -> float:
        return round(self.state.realized_pnl, 2)

    @property
    def win_rate_pct(self) -> float:
        if self.state.total_trades == 0:
            return 0.0
        return self.state.winning_trades / self.state.total_trades * 100

    def add_position(self, pos: Position, cost: float) -> None:
        if pos.symbol in self.state.positions:
            raise ValueError(f"Already have position in {pos.symbol}")
        if cost > self.state.cash:
            raise ValueError(f"Cost {cost} exceeds cash {self.state.cash}")
        self.state.cash = round(self.state.cash - cost, 2)
        self.state.positions[pos.symbol] = pos
        self.state.last_updated = datetime.now()

    def close_position(self, symbol: str, exit_price: float, sell_charges: float) -> float:
        if symbol not in self.state.positions:
            raise ValueError(f"No open position in {symbol}")
        pos       = self.state.positions[symbol]
        gross_pnl = (exit_price - pos.entry_price) * pos.qty
        net_pnl   = gross_pnl - pos.charges_buy - sell_charges
        proceeds  = exit_price * pos.qty - sell_charges

        self.state.cash         = round(self.state.cash + proceeds, 2)
        self.state.realized_pnl = round(self.state.realized_pnl + net_pnl, 2)
        self.state.total_trades += 1
        if net_pnl > 0:
            self.state.winning_trades += 1
        del self.state.positions[symbol]
        self.state.last_updated = datetime.now()
        return round(net_pnl, 2)
