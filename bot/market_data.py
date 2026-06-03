"""
NSE market data with timezone-aware IST checks.
Rejects: closed market, weekends, NSE holidays, stale quotes, future-skewed quotes.
Always exposes rejection reason.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, time as dtime
from typing import Optional

from bot.config import MarketConfig
from bot.holidays import is_nse_holiday, HolidayRegistry

# India Standard Time = UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class Quote:
    symbol:    str
    price:     float
    timestamp: datetime
    is_stale:  bool
    reject_reason: Optional[str] = None

    @property
    def is_usable(self) -> bool:
        return self.reject_reason is None


def now_ist() -> datetime:
    return datetime.now(IST)


def is_weekend(dt: datetime) -> bool:
    return dt.weekday() >= 5


def is_market_open(cfg: MarketConfig, dt: Optional[datetime] = None,
                   holiday_registry: Optional[HolidayRegistry] = None) -> tuple:
    """
    Returns (is_open, reason).
    Rejects: naive datetime, weekend, NSE holiday, outside session hours.

    When cfg.market_hours_24x7 is True (crypto mode), only the
    timezone-aware sanity check applies — the market is always open.
    """
    dt = dt or now_ist()
    if dt.tzinfo is None:
        return False, "datetime is timezone-naive; refusing to evaluate"

    if cfg.market_hours_24x7:
        return True, ""

    dt_ist = dt.astimezone(IST)
    if is_weekend(dt_ist):
        return False, f"weekend ({dt_ist.strftime('%A')})"

    if cfg.use_nse_holidays and is_nse_holiday(dt_ist.date(),
                                                registry=holiday_registry):
        return False, f"NSE holiday ({dt_ist.date().isoformat()})"

    market_open  = dtime(cfg.open_hour,  cfg.open_minute)
    market_close = dtime(cfg.close_hour, cfg.close_minute)
    now_time     = dt_ist.time()

    if now_time < market_open:
        return False, f"before open (now {now_time.strftime('%H:%M')} IST, opens {market_open.strftime('%H:%M')})"
    if now_time >= market_close:
        return False, f"after close (now {now_time.strftime('%H:%M')} IST, closed at {market_close.strftime('%H:%M')})"
    return True, ""


def validate_quote(quote_price: float, quote_timestamp: datetime,
                   symbol: str, cfg: MarketConfig,
                   now: Optional[datetime] = None,
                   holiday_registry: Optional[HolidayRegistry] = None) -> Quote:
    """Validate a quote. Sets reject_reason if anything is wrong."""
    now = now or now_ist()

    if quote_timestamp.tzinfo is None:
        return Quote(symbol=symbol, price=quote_price, timestamp=quote_timestamp,
                     is_stale=True, reject_reason="quote timestamp is timezone-naive")

    is_open, reason = is_market_open(cfg, now, holiday_registry=holiday_registry)
    if not is_open:
        return Quote(symbol=symbol, price=quote_price, timestamp=quote_timestamp,
                     is_stale=True, reject_reason=f"market closed: {reason}")

    age_sec = (now - quote_timestamp.astimezone(IST)).total_seconds()

    # Future-timestamp check (clock-skew tolerance)
    if age_sec < -cfg.future_skew_tolerance_sec:
        return Quote(symbol=symbol, price=quote_price, timestamp=quote_timestamp,
                     is_stale=True,
                     reject_reason=f"quote is {-age_sec:.1f}s in the future "
                                   f"(max tolerance {cfg.future_skew_tolerance_sec}s)")

    if age_sec > cfg.stale_quote_threshold_sec:
        return Quote(symbol=symbol, price=quote_price, timestamp=quote_timestamp,
                     is_stale=True,
                     reject_reason=f"quote is {age_sec:.1f}s old (max {cfg.stale_quote_threshold_sec}s)")

    if quote_price <= 0:
        return Quote(symbol=symbol, price=quote_price, timestamp=quote_timestamp,
                     is_stale=True, reject_reason=f"non-positive price: {quote_price}")

    return Quote(symbol=symbol, price=quote_price, timestamp=quote_timestamp,
                 is_stale=False, reject_reason=None)
