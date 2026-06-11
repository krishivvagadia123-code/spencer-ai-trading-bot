from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from bot import gdelt_news as GN
from bot import news_sentiment_eval as NSE
from workflow import research_automation as RA


def test_company_mapping_is_auditable_for_nifty50():
    mapped = GN.mapped_companies(top=50)

    assert len(mapped) == 50
    assert GN.unmapped_symbols([row["symbol"] for row in mapped]) == []
    reliance = next(row for row in mapped if row["symbol"] == "RELIANCE")
    assert reliance["company_name"] == "Reliance Industries Limited"
    assert reliance["aliases"]
    assert reliance["source"]
    assert "sourcecountry:india" in GN.build_company_query(reliance)


def test_parse_timeline_payload_handles_json_and_csv():
    tone_raw = json.dumps({
        "timeline": [
            {"date": "2026-01-01", "value": -2.5},
            {"datetime": "2026-01-02T00:00:00Z", "tone": 1.25},
        ]
    })
    volume_raw = "date,value,norm\n2026-01-01,7,1000\n2026-01-02,9,1000\n"

    tone = GN.parse_timeline_payload(tone_raw, value_name="tone")
    volume = GN.parse_timeline_payload(volume_raw, value_name="article_count")

    assert tone is not None
    assert volume is not None
    assert tone["tone"].tolist() == [-2.5, 1.25]
    assert volume["article_count"].tolist() == [7, 9]


def test_fetch_company_timeline_caches_raw_without_fabrication(tmp_path):
    mapping = GN.mapped_companies(["RELIANCE"])[0]
    calls = []

    def fetcher(url: str, timeout: int) -> str:
        calls.append(url)
        if "timelinetone" in url:
            return json.dumps({"timeline": [{"date": "2026-01-01", "value": -1.0}]})
        return json.dumps({"timeline": [{"date": "2026-01-01", "value": 4}]})

    first = GN.fetch_company_timeline(
        mapping,
        start=date(2026, 1, 1),
        end=date(2026, 1, 2),
        cache_dir=tmp_path,
        fetch_text=fetcher,
        refresh=True,
    )
    second = GN.fetch_company_timeline(
        mapping,
        start=date(2026, 1, 1),
        end=date(2026, 1, 2),
        cache_dir=tmp_path,
        fetch_text=lambda url, timeout: (_ for _ in ()).throw(AssertionError("cache should be used")),
        refresh=False,
    )

    assert first is not None
    assert second is not None
    assert calls and len(list(tmp_path.glob("*.json"))) == 2
    assert second.iloc[0]["symbol"] == "RELIANCE"
    assert second.iloc[0]["article_count"] == 4


def test_add_features_and_build_panel_uses_next_session():
    news = pd.DataFrame([
        {"date": d.date(), "symbol": "RELIANCE", "tone": float(i), "article_count": 5}
        for i, d in enumerate(pd.date_range("2026-01-01", periods=30, freq="B"))
    ])
    featured = NSE.add_sentiment_features(news)
    price = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "close": [100.0, 101.0, 102.0, 104.0, 106.0, 108.0, 110.0],
        },
        index=pd.date_range("2026-01-01", periods=7, freq="B"),
    )

    panel = NSE.build_symbol_panel("RELIANCE", price, featured.head(1))

    assert panel is not None
    row = panel.iloc[0]
    assert row["entry_date"] == date(2026, 1, 2)
    assert row["fwd"] == (110.0 / 101.0) - 1.0
    assert "gap_confounded" in panel.columns


def test_evaluate_reports_data_unavailable_without_real_news(monkeypatch):
    monkeypatch.setattr(NSE.gdelt_news, "coverage_probe", lambda **kwargs: {"decision": "DATA_AVAILABLE_FOR_RESEARCH", "windows": []})
    monkeypatch.setattr(NSE.gdelt_news, "news_history", lambda **kwargs: None)

    result = NSE.evaluate(years=1, top=1)

    assert result["module"] == "news_sentiment_eval"
    assert result["verdict"].startswith("DATA_UNAVAILABLE")
    assert result["usable_features"] == []
    assert "Do NOT build a strategy" in result["verdict"]


def test_evaluate_stops_early_when_coverage_probe_is_rate_limited(monkeypatch):
    monkeypatch.setattr(
        NSE.gdelt_news,
        "coverage_probe",
        lambda **kwargs: {
            "decision": "DATA_UNAVAILABLE_RATE_LIMITED",
            "windows": [],
            "request_summary": {"rate_limited_requests": 2},
        },
    )
    monkeypatch.setattr(
        NSE.gdelt_news,
        "news_history",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("full ingest should not run")),
    )

    result = NSE.evaluate(years=1, top=3)

    assert result["coverage_decision"] == "DATA_UNAVAILABLE_RATE_LIMITED"
    assert result["verdict"].startswith("DATA_UNAVAILABLE")
    assert "HTTP 429/503" in result["verdict"]


def test_evaluate_panel_reports_pass_for_stable_cost_clearing_fixture():
    dates = pd.date_range("2025-01-01", periods=260, freq="B").date
    tone_z = np.linspace(-3.0, 3.0, len(dates))
    rows = []
    for idx, day in enumerate(dates):
        fwd = tone_z[idx] * 0.01
        rows.append({
            "symbol": "RELIANCE",
            "date": day,
            "entry_date": day,
            "tone": tone_z[idx],
            "article_count": 10,
            "tone_z": tone_z[idx],
            "shock_score": tone_z[idx],
            "tone_volume_z": tone_z[idx] * np.log1p(10),
            "is_sentiment_shock": float(abs(tone_z[idx]) >= NSE.SHOCK_Z),
            "fwd": fwd,
            "directional_return": fwd * np.sign(tone_z[idx]),
            "max_adverse": -0.002,
            "gap_pct": 0.0,
            "gap_confounded": False,
        })
    panel = pd.DataFrame(rows)
    availability = {"symbols_mapped": 1, "symbols_with_news": 1, "news_rows": len(panel)}

    result = NSE.evaluate_panel(panel, availability=availability, universe="fixture")

    assert result["verdict"].startswith("PASS")
    assert result["events"] >= NSE.MIN_EVENTS
    assert result["event_study"]["cost_adjusted_return"] > 0
    assert result["event_study"]["walk_forward_survives"] is True
    assert result["features"]["shock_score"]["ic_out_sample"] > 0.99


def test_research_automation_registration_includes_news_sentiment():
    assert RA.MODULE_FILES["news_sentiment_eval"] == "bot/news_sentiment_eval.py"
    assert RA.MODULE_TESTS["news_sentiment_eval"] == ["tests/test_news_sentiment_eval.py"]
