from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from bot import delivery_eval as DE
from bot import nse_delivery as ND


def test_parse_bhavcopy_csv_extracts_real_delivery_columns():
    raw = """SYMBOL,SERIES,DATE1,TTL_TRD_QNTY,DELIV_QTY,DELIV_PER
RELIANCE,EQ,01-Jan-2026,"1,000","650",65.00
RELIANCE,BE,01-Jan-2026,10,5,50.00
TCS,EQ,01-Jan-2026,2000,1000,50.00
"""

    parsed = ND.parse_bhavcopy_csv(raw)

    assert parsed is not None
    assert parsed["symbol"].tolist() == ["RELIANCE", "TCS"]
    rel = parsed[parsed["symbol"] == "RELIANCE"].iloc[0]
    assert rel["traded_qty"] == 1000
    assert rel["deliverable_qty"] == 650
    assert rel["delivery_pct"] == 65.0


def test_delivery_history_returns_none_when_archive_missing(tmp_path):
    def missing_day(*args, **kwargs):
        return None

    assert ND.delivery_history("RELIANCE", start=date(2026, 1, 1), end=date(2026, 1, 5),
                               cache_dir=tmp_path, fetch_day=missing_day) is None


def test_add_delivery_features_marks_spike_only_with_delivery_and_volume():
    idx = pd.date_range("2026-01-01", periods=25, freq="B")
    df = pd.DataFrame({
        "delivery_pct": [50.0] * 20 + [85.0, 52.0, 53.0, 54.0, 55.0],
        "traded_qty": [1000.0] * 20 + [2500.0, 900.0, 950.0, 970.0, 990.0],
    }, index=idx)

    out = DE.add_delivery_features(df)

    assert out["delivery_spike"].iloc[20] == 1.0
    assert out["delivery_spike"].iloc[21] == 0.0
    assert np.isfinite(out["delivery_pct_zscore"].iloc[20])


def test_evaluate_panel_reports_required_delivery_metrics():
    rows = []
    start = date(2025, 1, 1)
    for sym_i, symbol in enumerate(["AAA", "BBB", "CCC"]):
        for i in range(160):
            d = start + timedelta(days=i)
            delivery = 30 + (i % 40) + sym_i
            fwd = (delivery - 50) / 1000.0
            rows.append({
                "symbol": symbol,
                "date": d,
                "delivery_pct": float(delivery),
                "delivery_pct_zscore": float((delivery - 50) / 10),
                "delivery_spike": float(delivery > 62),
                "traded_qty": 1000 + i,
                "deliverable_qty": (1000 + i) * delivery / 100,
                "fwd": fwd,
            })
    panel = pd.DataFrame(rows)
    availability = {
        "symbols_requested": 3,
        "price_symbols": 3,
        "delivery_symbols": 3,
        "symbols_used": 3,
        "unavailable_symbols": [],
        "observations": len(panel),
        "source": "test fixture",
    }

    result = DE.evaluate_panel(panel, universe="fixture", availability=availability)

    assert result["data_availability"]["symbols_used"] == 3
    assert result["features"]["delivery_pct"]["ic_in_sample"] is not None
    assert result["features"]["delivery_pct"]["ic_out_sample"] is not None
    assert result["features"]["delivery_pct"]["oos_quintile_spread"] is not None
    assert "cost_adjusted_edge" in result["features"]["delivery_pct"]
    assert "walk_forward_survives" in result["features"]["delivery_pct"]
    assert result["limitations"]


def test_evaluate_returns_honest_data_unavailable(monkeypatch):
    monkeypatch.setattr(DE, "fetch_history", lambda symbol, years: None)

    result = DE.evaluate(["RELIANCE"], years=1)

    assert result["features"] == {}
    assert result["usable_features"] == []
    assert result["verdict"].startswith("DATA UNAVAILABLE")
    assert "Do NOT build a strategy" in result["verdict"]
