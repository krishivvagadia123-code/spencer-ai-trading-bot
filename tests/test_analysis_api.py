from __future__ import annotations

import json
import threading
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import spencer_quote_server


FIXTURE = Path(__file__).parent / "fixtures" / "analysis_latest.json"


def _get_analysis(monkeypatch, analysis_path, latest_trading_day):
    monkeypatch.setattr(
        spencer_quote_server,
        "WORKFLOW_ANALYSIS_LATEST_PATH",
        analysis_path,
    )
    monkeypatch.setattr(
        spencer_quote_server,
        "_latest_nse_trading_day",
        lambda: latest_trading_day,
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), spencer_quote_server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/api/analysis", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_analysis_endpoint_returns_latest_analysis_fixture(tmp_path, monkeypatch):
    analysis_path = tmp_path / "analysis_latest.json"
    analysis_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    payload = _get_analysis(
        monkeypatch,
        analysis_path,
        latest_trading_day=date(2026, 6, 19),
    )

    assert payload == {
        "rating": "HOLD",
        "executive_summary": "RELIANCE setup is constructive but still gated by paper-only validation.",
        "time_horizon": "1-5 trading days",
        "analysis_date": "2026-06-19",
        "generated_at": "2026-06-19T18:10:00+05:30",
        "is_stale": False,
    }


def test_analysis_endpoint_absent_file_returns_no_analysis_yet(tmp_path, monkeypatch):
    payload = _get_analysis(
        monkeypatch,
        tmp_path / "missing_analysis.json",
        latest_trading_day=date(2026, 6, 19),
    )

    assert payload == {
        "rating": None,
        "executive_summary": "no analysis yet",
        "time_horizon": None,
        "analysis_date": None,
        "generated_at": None,
        "is_stale": True,
    }


def test_analysis_endpoint_marks_old_analysis_stale(tmp_path, monkeypatch):
    analysis_path = tmp_path / "analysis_latest.json"
    analysis_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    payload = _get_analysis(
        monkeypatch,
        analysis_path,
        latest_trading_day=date(2026, 6, 22),
    )

    assert payload["analysis_date"] == "2026-06-19"
    assert payload["is_stale"] is True
