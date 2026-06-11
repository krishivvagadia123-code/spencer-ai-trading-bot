from __future__ import annotations

import json
from datetime import date
from email.message import Message
from urllib.error import HTTPError

from bot import gdelt_news as GN


def _timeline(value: float = 1.0) -> str:
    return json.dumps({"timeline": [{"date": "2026-01-01", "value": value}]})


def _http_error(status: int, retry_after: str | None = None) -> HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError("https://example.test", status, "error", headers, None)


def test_fetch_company_timeline_uses_persistent_cache_before_network(tmp_path):
    mapping = GN.mapped_companies(["RELIANCE"])[0]
    query = GN.build_company_query(mapping)
    start = date(2026, 1, 1)
    end = date(2026, 1, 30)
    tone_path = GN._cache_path(tmp_path, "RELIANCE", "timelinetone", start, end, query)
    volume_path = GN._cache_path(tmp_path, "RELIANCE", "timelinevolraw", start, end, query)
    tone_path.write_text(_timeline(-2.0), encoding="utf-8")
    volume_path.write_text(_timeline(5.0), encoding="utf-8")

    state = GN.RateLimitState()
    frame = GN.fetch_company_timeline(
        mapping,
        start=start,
        end=end,
        cache_dir=tmp_path,
        refresh=True,
        rate_state=state,
        fetch_text=lambda url, timeout: (_ for _ in ()).throw(AssertionError("network should not be used")),
    )

    assert frame is not None
    assert frame.iloc[0]["tone"] == -2.0
    assert frame.iloc[0]["article_count"] == 5.0
    assert [event["event"] for event in state.events] == ["disk_cache_hit", "disk_cache_hit"]


def test_429_uses_exponential_backoff_and_retries(tmp_path):
    calls = []
    sleeps = []

    def fetcher(url: str, timeout: int) -> str:
        calls.append(url)
        if len(calls) == 1:
            raise _http_error(429)
        return _timeline(1.0)

    raw = GN._load_or_fetch_raw(
        cache_dir=tmp_path,
        symbol="RELIANCE",
        query='"Reliance Industries"',
        mode="timelinetone",
        start=date(2026, 1, 1),
        end=date(2026, 1, 30),
        fetch_text=fetcher,
        refresh=True,
        timeout=1,
        retries=1,
        min_request_delay=0,
        backoff_base=3,
        sleep_func=sleeps.append,
        rate_state=GN.RateLimitState(),
    )

    assert raw == _timeline(1.0)
    assert len(calls) == 2
    assert sleeps == [3.0]


def test_retry_after_header_is_honored_for_503(tmp_path):
    calls = []
    sleeps = []

    def fetcher(url: str, timeout: int) -> str:
        calls.append(url)
        if len(calls) == 1:
            raise _http_error(503, retry_after="7")
        return _timeline(2.0)

    raw = GN._load_or_fetch_raw(
        cache_dir=tmp_path,
        symbol="TCS",
        query='"Tata Consultancy Services"',
        mode="timelinetone",
        start=date(2026, 1, 1),
        end=date(2026, 1, 30),
        fetch_text=fetcher,
        refresh=True,
        timeout=1,
        retries=1,
        min_request_delay=0,
        backoff_base=2,
        sleep_func=sleeps.append,
        rate_state=GN.RateLimitState(),
    )

    assert raw == _timeline(2.0)
    assert sleeps == [7.0]


def test_minimum_inter_request_delay_is_applied_between_network_fetches(tmp_path):
    sleeps = []
    now_values = iter([100.0, 100.0, 101.0, 101.0])
    state = GN.RateLimitState()

    def now_func() -> float:
        return next(now_values)

    def fetcher(url: str, timeout: int) -> str:
        return _timeline(1.0)

    for symbol in ("RELIANCE", "TCS"):
        GN._load_or_fetch_raw(
            cache_dir=tmp_path,
            symbol=symbol,
            query=f'"{symbol}"',
            mode="timelinetone",
            start=date(2026, 1, 1),
            end=date(2026, 1, 30),
            fetch_text=fetcher,
            refresh=True,
            timeout=1,
            retries=0,
            min_request_delay=5,
            sleep_func=sleeps.append,
            now_func=now_func,
            rate_state=state,
        )

    assert sleeps == [5.0]


def test_empty_response_does_not_fabricate_news(tmp_path):
    raw = GN._load_or_fetch_raw(
        cache_dir=tmp_path,
        symbol="INFY",
        query='"Infosys"',
        mode="timelinetone",
        start=date(2026, 1, 1),
        end=date(2026, 1, 30),
        fetch_text=lambda url, timeout: "",
        refresh=True,
        timeout=1,
        retries=0,
        min_request_delay=0,
        rate_state=GN.RateLimitState(),
    )

    assert raw is None
    assert list(tmp_path.glob("*.json")) == []


def test_coverage_probe_reports_decision_and_window_rows(tmp_path):
    def fetcher(url: str, timeout: int) -> str:
        if "timelinetone" in url:
            return _timeline(-1.5)
        return _timeline(6.0)

    result = GN.coverage_probe(
        symbols=["RELIANCE"],
        as_of=date(2026, 6, 3),
        cache_dir=tmp_path,
        fetch_text=fetcher,
        refresh=True,
        min_request_delay=0,
        retries=0,
    )

    assert result["decision"] == "DATA_AVAILABLE_FOR_RESEARCH"
    assert result["symbols_mapped"] == 1
    assert len(result["windows"]) == 4
    assert all(row["merged_points"] == 1 for row in result["windows"])
    assert result["request_summary"]["network_fetches"] == 8


def test_cache_only_probe_marks_unprobed_windows_as_cache_miss(tmp_path):
    mapping = GN.mapped_companies(["RELIANCE"])[0]
    query = GN.build_company_query(mapping)
    start = date(2026, 5, 5)
    end = date(2026, 6, 3)
    GN._cache_path(tmp_path, "RELIANCE", "timelinetone", start, end, query).write_text(_timeline(-1.0), encoding="utf-8")
    GN._cache_path(tmp_path, "RELIANCE", "timelinevolraw", start, end, query).write_text(_timeline(4.0), encoding="utf-8")

    result = GN.coverage_probe(
        symbols=["RELIANCE"],
        as_of=date(2026, 6, 3),
        cache_dir=tmp_path,
        refresh=False,
    )

    assert result["decision"] == "DATA_UNAVAILABLE_INSUFFICIENT_HISTORY"
    assert result["windows"][0]["status"] == "DATA_AVAILABLE"
    assert any(row["status"] == "NOT_PROBED_CACHE_MISS" for row in result["windows"])
