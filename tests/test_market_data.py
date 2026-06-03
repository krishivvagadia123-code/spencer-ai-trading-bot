"""Market data tests — IST awareness, weekends, staleness, rejection reasons."""
from datetime import datetime, timedelta
import pytest

from bot.config import MarketConfig
from bot.market_data import IST, is_market_open, validate_quote, is_weekend, now_ist


@pytest.fixture
def cfg():
    return MarketConfig()


def _ist(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=IST)


def test_market_open_monday_at_10am(cfg):
    is_open, reason = is_market_open(cfg, _ist(2026, 5, 25, 10, 0))
    assert is_open is True
    assert reason == ""


def test_market_closed_before_915(cfg):
    is_open, reason = is_market_open(cfg, _ist(2026, 5, 25, 9, 0))
    assert is_open is False
    assert "before open" in reason


def test_market_closed_after_1530(cfg):
    is_open, reason = is_market_open(cfg, _ist(2026, 5, 25, 15, 30))
    assert is_open is False
    assert "after close" in reason


def test_market_closed_on_saturday(cfg):
    is_open, reason = is_market_open(cfg, _ist(2026, 5, 30, 10, 0))
    assert is_open is False
    assert "weekend" in reason.lower()


def test_market_closed_on_sunday(cfg):
    is_open, reason = is_market_open(cfg, _ist(2026, 5, 31, 10, 0))
    assert is_open is False
    assert "weekend" in reason.lower()


def test_naive_datetime_rejected(cfg):
    is_open, reason = is_market_open(cfg, datetime(2026, 5, 25, 10, 0))
    assert is_open is False
    assert "timezone-naive" in reason.lower()


def test_market_boundary_at_open_exact(cfg):
    is_open, _ = is_market_open(cfg, _ist(2026, 5, 25, 9, 15))
    assert is_open is True


def test_market_boundary_at_close_exact(cfg):
    is_open, _ = is_market_open(cfg, _ist(2026, 5, 25, 15, 30))
    assert is_open is False


def test_is_weekend_saturday():
    assert is_weekend(_ist(2026, 5, 30, 12, 0)) is True


def test_is_weekend_friday():
    assert is_weekend(_ist(2026, 5, 29, 12, 0)) is False


def test_quote_during_market_hours_usable(cfg):
    now      = _ist(2026, 5, 25, 10, 0)
    quote_ts = now - timedelta(seconds=5)
    q = validate_quote(2500.0, quote_ts, "ADANIENT", cfg, now=now)
    assert q.is_usable
    assert q.reject_reason is None


def test_quote_rejected_when_stale(cfg):
    now      = _ist(2026, 5, 25, 10, 0)
    quote_ts = now - timedelta(seconds=120)
    q = validate_quote(2500.0, quote_ts, "ADANIENT", cfg, now=now)
    assert not q.is_usable
    assert "old" in q.reject_reason.lower()


def test_quote_rejected_when_market_closed(cfg):
    now = _ist(2026, 5, 31, 10, 0)
    q = validate_quote(2500.0, now, "ADANIENT", cfg, now=now)
    assert not q.is_usable
    assert "market closed" in q.reject_reason


def test_quote_rejected_when_timestamp_naive(cfg):
    now      = _ist(2026, 5, 25, 10, 0)
    naive_ts = datetime(2026, 5, 25, 10, 0)
    q = validate_quote(2500.0, naive_ts, "ADANIENT", cfg, now=now)
    assert not q.is_usable
    assert "naive" in q.reject_reason.lower()


def test_quote_rejected_when_price_zero(cfg):
    now = _ist(2026, 5, 25, 10, 0)
    q = validate_quote(0.0, now, "ADANIENT", cfg, now=now)
    assert not q.is_usable
    assert "non-positive" in q.reject_reason.lower()


def test_quote_rejected_when_price_negative(cfg):
    now = _ist(2026, 5, 25, 10, 0)
    q = validate_quote(-5.0, now, "ADANIENT", cfg, now=now)
    assert not q.is_usable


def test_now_ist_is_timezone_aware():
    n = now_ist()
    assert n.tzinfo is not None
    assert n.utcoffset() == timedelta(hours=5, minutes=30)
