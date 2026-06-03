"""
Pydantic configuration models.
All numeric constants are validated on load — corrupt config fails fast.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class RiskConfig(BaseModel):
    risk_per_trade_pct:      float = Field(1.0,  ge=0.1,  le=5.0)
    max_daily_loss_pct:      float = Field(3.0,  ge=0.5,  le=10.0)
    max_drawdown_pct:        float = Field(10.0, ge=2.0,  le=25.0)
    max_open_positions:      int   = Field(1,    ge=1,    le=10)
    max_symbol_notional_pct: float = Field(30.0, ge=5.0,  le=100.0)
    max_total_exposure_pct:  float = Field(100.0, ge=10.0, le=200.0)
    # Absolute caps override percentage caps when set. This is critical when
    # an external paper platform shows a huge demo USD balance but the operator
    # wants the bot to behave as if only a small INR sandbox exists.
    max_symbol_notional_inr: Optional[float] = Field(None, ge=0.0)
    max_total_notional_inr:  Optional[float] = Field(None, ge=0.0)


class IndicatorConfig(BaseModel):
    atr_period:     int   = Field(14, ge=5, le=50)
    atr_multiplier: float = Field(2.0, ge=0.5, le=5.0)
    min_stop_pct:   float = Field(0.005, ge=0.001, le=0.05)
    rsi_period:     int   = Field(14, ge=5, le=50)
    st_period:      int   = Field(10, ge=5, le=30)
    st_multiplier:  float = Field(3.0, ge=1.0, le=6.0)


class FeeConfig(BaseModel):
    broker:                Literal["zerodha", "crypto_paper"] = "zerodha"
    intraday_slippage_bps: float = Field(5.0,  ge=0.0, le=100.0)
    delivery_slippage_bps: float = Field(10.0, ge=0.0, le=100.0)
    # Crypto-only: flat round-trip fee % (taker/maker average). 0.1% = 10 bps per side.
    crypto_fee_bps:        float = Field(10.0, ge=0.0, le=200.0)
    crypto_slippage_bps:   float = Field(15.0, ge=0.0, le=200.0)
    # Phase I.1 — fractional crypto support:
    #   qty is floored to crypto_qty_step (0.0001 ≈ 1e-4 BTC).
    #   trade is rejected if qty * price < crypto_min_notional_inr.
    crypto_qty_step:           float = Field(0.0001, gt=0.0, le=1.0)
    crypto_min_notional_inr:   float = Field(500.0,  ge=0.0)
    equity_min_notional_inr:   float = Field(1.0,    ge=0.0)


class MarketConfig(BaseModel):
    exchange:     Literal["NSE", "CRYPTO"] = "NSE"
    open_hour:    int = Field(9,  ge=0, le=23)
    open_minute:  int = Field(15, ge=0, le=59)
    close_hour:   int = Field(15, ge=0, le=23)
    close_minute: int = Field(30, ge=0, le=59)
    stale_quote_threshold_sec:  int = Field(60, ge=5, le=600,
                                            description="Reject quotes older than this")
    future_skew_tolerance_sec:  int = Field(2,  ge=0, le=60,
                                            description="Accept quote timestamps up to this many seconds in the future "
                                                        "(clock skew tolerance). Beyond this, reject.")
    # When True: skip NSE-hours + NSE-holiday checks. Used for crypto 24/7 mode.
    market_hours_24x7:          bool = Field(False, description="Skip session-hours and holiday checks")
    use_nse_holidays:           bool = Field(True,  description="Honor NSE holiday registry")


class AssetClassConfig(BaseModel):
    """Top-level switch between Indian equities and crypto-INR paper trading."""
    asset_class:    Literal["equity", "crypto"] = "equity"
    quote_currency: Literal["INR", "USD"]       = "INR"
    use_zerodha:    bool = True


class SupervisorConfig(BaseModel):
    """Tuning for the run-all loop and auto-buy gates."""
    monitor_interval_sec:     int   = Field(45,  ge=5,  le=300)
    scan_interval_sec:        int   = Field(240, ge=30, le=3600)
    auto_buy_interval_sec:    int   = Field(60,  ge=10, le=600)
    dashboard_interval_sec:   int   = Field(60,  ge=10, le=600)
    heartbeat_interval_sec:   int   = Field(30,  ge=5,  le=300)
    cooldown_sec_per_symbol:  int   = Field(1800, ge=60, description="Min seconds between auto-buys of same symbol")
    min_total_score_to_buy:   float = Field(0.65, ge=0.0, le=1.0)
    max_quote_age_sec:        int   = Field(120, ge=5,  le=600)
    max_signal_age_sec:       int   = Field(600, ge=30, le=3600)


class LiveTradingGate(BaseModel):
    """
    Explicit, auditable double-gate for live order placement.

    Spencer ships PAPER-ONLY. Today there is no live order path at all, but this
    gate makes "off" an enforced guarantee rather than an accident of omission:
    a future live adapter MUST call `live_trading_allowed()` and refuse unless BOTH
    switches are independently True. Two switches by design, so neither a stray
    config flag nor leaked credentials alone can enable real money.
    """
    live_enabled:         bool = False   # SWITCH 1: operator intent
    has_live_credentials: bool = False   # SWITCH 2: real broker creds present


class BotConfig(BaseModel):
    starting_balance: float = Field(50_000.0, ge=1_000.0)
    asset:      AssetClassConfig = AssetClassConfig()
    risk:       RiskConfig       = RiskConfig()
    indicators: IndicatorConfig  = IndicatorConfig()
    fees:       FeeConfig        = FeeConfig()
    market:     MarketConfig     = MarketConfig()
    supervisor: SupervisorConfig = SupervisorConfig()
    live:       LiveTradingGate  = LiveTradingGate()

    def live_trading_allowed(self) -> bool:
        """Live trading requires BOTH switches. Default: False (paper-only)."""
        return self.live.live_enabled and self.live.has_live_credentials


def assert_paper_only(cfg: "BotConfig") -> None:
    """Guard any execution path must pass before placing an order. Paper-only today."""
    if cfg.live_trading_allowed():
        raise PermissionError(
            "Live trading gate is OPEN but no audited live adapter exists. Refusing. "
            "Set live.live_enabled=False to restore paper-only operation."
        )


def default_config() -> BotConfig:
    return BotConfig()


def crypto_inr_config() -> BotConfig:
    """24/7 crypto-INR paper trading preset."""
    return BotConfig(
        starting_balance=5_000.0,
        asset=AssetClassConfig(asset_class="crypto", quote_currency="INR",
                               use_zerodha=False),
        risk=RiskConfig(
            risk_per_trade_pct=0.5,
            max_daily_loss_pct=1.0,
            max_drawdown_pct=3.0,
            max_open_positions=3,
            max_symbol_notional_pct=10.0,
            max_total_exposure_pct=30.0,
            max_symbol_notional_inr=2_000.0,
            max_total_notional_inr=5_000.0,
        ),
        fees=FeeConfig(broker="crypto_paper"),
        market=MarketConfig(exchange="CRYPTO", market_hours_24x7=True,
                            use_nse_holidays=False,
                            stale_quote_threshold_sec=300),
        supervisor=SupervisorConfig(dashboard_interval_sec=10),
    )
