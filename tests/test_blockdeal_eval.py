from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from bot import blockdeal_eval as BE
from bot import nse_block_deals as NB


def test_parse_deals_payload_normalizes_csv_rows():
    raw = """Date,Symbol,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price
01-Jan-2026,RELIANCE,Fund A,BUY,"1,000",2500.50
01-Jan-2026,TCS,Fund B,SELL,200,3100.00
"""

    parsed = NB.parse_deals_payload(raw, deal_type="bulk")

    assert parsed is not None
    assert parsed["symbol"].tolist() == ["RELIANCE", "TCS"]
    assert parsed["side"].tolist() == ["BUY", "SELL"]
    assert parsed["deal_type"].tolist() == ["bulk", "bulk"]
    assert parsed.iloc[0]["qty"] == 1000.0


def test_parse_deals_payload_normalizes_json_rows():
    raw = """{"data":[{"BD_DT_DATE":"01-Jan-2026","BD_SYMBOL":"INFY","BD_CLIENT_NAME":"Fund","BD_BUY_SELL":"B","BD_QTY_TRD":"300","BD_TP_WATP":"1500.25"}]}"""

    parsed = NB.parse_deals_payload(raw, deal_type="block")

    assert parsed is not None
    row = parsed.iloc[0]
    assert row["symbol"] == "INFY"
    assert row["side"] == "BUY"
    assert row["deal_type"] == "block"


def test_deals_history_returns_none_without_real_rows(tmp_path):
    def missing_range(*args, **kwargs):
        return None

    assert NB.deals_history(["RELIANCE"], start=date(2026, 1, 1), end=date(2026, 1, 5),
                            cache_dir=tmp_path, manual_dir=tmp_path / "manual",
                            fetch_static=lambda *args, **kwargs: None,
                            fetch_range=missing_range) is None


def test_forward_record_uses_next_session_and_side_direction():
    idx = pd.date_range("2026-01-01", periods=12, freq="B")
    price = pd.DataFrame({
        "close": [100 + i for i in range(12)],
        "low": [99 + i for i in range(12)],
    }, index=idx)

    buy = BE.forward_record(price, idx[2].date(), "BUY")
    sell = BE.forward_record(price, idx[2].date(), "SELL")

    assert buy["date"] == idx[3].date()
    assert buy["directional_return"] > 0
    assert sell["directional_return"] < 0


def test_summarize_bucket_reports_event_metrics_and_pass_status():
    records = []
    start = date(2025, 1, 1)
    for i in range(80):
        records.append({
            "date": start + timedelta(days=i),
            "fwd": 0.01,
            "directional_return": 0.01,
            "max_adv": -0.002,
            "side": "BUY",
        })

    summary = BE.summarize_bucket(records)

    assert summary["events"] == 80
    assert summary["win_rate"] == 1.0
    assert summary["avg_return"] == 0.01
    assert summary["cost_adj"] == 0.0075
    assert summary["is_avg"] is not None
    assert summary["oos_avg"] is not None
    assert summary["walk_forward"] == "survives"
    assert summary["status"] == "PASS"


def test_evaluate_reports_fail_without_fake_nse_data(monkeypatch):
    monkeypatch.setattr(BE.nse_block_deals, "deals_history", lambda symbols, years: None)

    result = BE.evaluate(["RELIANCE"], years=1)

    assert result["events"] == 0
    assert result["usable_features"] == []
    assert result["verdict"].startswith("FAIL: DATA_UNAVAILABLE")
    assert "Do NOT build a strategy" in result["verdict"]


def test_evaluate_reports_data_unavailable_for_sparse_real_events(monkeypatch):
    deals = pd.DataFrame([
        {
            "date": date(2026, 1, 2 + i),
            "symbol": "RELIANCE",
            "side": "BUY",
            "qty": 1000.0 + i,
            "price": 2500.0,
            "client": f"Fund {i}",
            "deal_type": "bulk",
            "source": "manual_csv",
        }
        for i in range(5)
    ])
    deals.attrs["source_counts"] = {"manual_csv": 5}

    price = pd.DataFrame(
        {
            "close": [100 + i for i in range(30)],
            "low": [99 + i for i in range(30)],
        },
        index=pd.date_range("2026-01-01", periods=30, freq="B"),
    )

    monkeypatch.setattr(BE.nse_block_deals, "deals_history", lambda symbols, years: deals)
    monkeypatch.setattr(BE, "fetch_history", lambda symbol, years: price)

    result = BE.evaluate(["RELIANCE"], years=1)

    assert result["events"] == 5
    assert result["data_availability"]["source_counts"] == {"manual_csv": 5}
    assert result["verdict"].startswith("FAIL: DATA_UNAVAILABLE")
    assert "minimum required" in result["verdict"]
