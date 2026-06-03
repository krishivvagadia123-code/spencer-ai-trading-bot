from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from bot import flows_eval as FE
from bot import nse_flows as NF


NSE_PAYLOAD = json.dumps([
    {"buyValue": "17530", "category": "DII", "date": "03-Jun-2026", "netValue": "5740.89", "sellValue": "11789.11"},
    {"buyValue": "17053.63", "category": "FII/FPI", "date": "03-Jun-2026", "netValue": "-5616.56", "sellValue": "22670.19"},
])


def test_parse_flows_payload_pivots_fii_and_dii_rows():
    parsed = NF.parse_flows_payload(NSE_PAYLOAD)

    assert parsed is not None
    row = parsed.iloc[0]
    assert row["date"] == date(2026, 6, 3)
    assert row["fii_net"] == -5616.56
    assert row["dii_net"] == 5740.89
    assert row["fii_buy"] == 17053.63
    assert row["dii_sell"] == 11789.11


def test_flow_history_combines_cache_and_current_without_fabrication(tmp_path):
    cached = [
        {"category": "DII", "date": "02-Jun-2026", "buyValue": "100", "sellValue": "70", "netValue": "30"},
        {"category": "FII/FPI", "date": "02-Jun-2026", "buyValue": "90", "sellValue": "110", "netValue": "-20"},
    ]
    (tmp_path / "fiidii_20260602.json").write_text(json.dumps(cached), encoding="utf-8")

    rows = NF.flow_history(
        start=date(2026, 6, 1),
        end=date(2026, 6, 4),
        cache_dir=tmp_path,
        fetch_current=lambda **kwargs: NF._with_source(NF.parse_flows_payload(NSE_PAYLOAD), "nse_fiidiiTradeReact"),
    )

    assert rows is not None
    assert rows["date"].tolist() == [date(2026, 6, 2), date(2026, 6, 3)]
    assert rows.attrs["source_counts"] == {"cache": 1, "nse_fiidiiTradeReact": 1}


def test_build_panel_uses_next_index_session_after_flow_publication():
    flows = pd.DataFrame([
        {"date": date(2026, 1, 2), "fii_net": 10.0, "dii_net": -5.0},
    ])
    index = pd.DataFrame(
        {"close": [100.0, 101.0, 104.0, 108.0, 110.0, 115.0, 120.0]},
        index=pd.date_range("2026-01-02", periods=7, freq="B"),
    )

    panel = FE.build_panel(flows, index)

    assert panel is not None
    row = panel.iloc[0]
    assert row["entry_date"] == date(2026, 1, 5)
    assert row["fwd_1d"] == (104.0 / 101.0) - 1.0
    assert row["fwd_5d"] == (120.0 / 101.0) - 1.0


def test_evaluate_reports_data_unavailable_without_real_flows(monkeypatch):
    monkeypatch.setattr(FE.nse_flows, "flow_history", lambda years: None)

    result = FE.evaluate(years=1)

    assert result["observations"] == 0
    assert result["results"] == {}
    assert result["verdict"].startswith("DATA_UNAVAILABLE")
    assert "Do NOT build a strategy" in result["verdict"]


def test_evaluate_short_circuits_sparse_real_flows(monkeypatch):
    flows = pd.DataFrame([
        {"date": date(2026, 6, 3), "fii_net": -5616.56, "dii_net": 5740.89}
    ])
    monkeypatch.setattr(FE.nse_flows, "flow_history", lambda years: flows)
    monkeypatch.setattr(FE, "fetch_index_history", lambda years: (_ for _ in ()).throw(AssertionError("index fetch should not run")))

    result = FE.evaluate(years=1)

    assert result["data_availability"]["flow_rows"] == 1
    assert result["verdict"].startswith("DATA_UNAVAILABLE")
    assert "100 required" in result["verdict"]


def test_evaluate_panel_reports_pass_for_stable_cost_clearing_fixture():
    dates = pd.date_range("2025-01-01", periods=240, freq="B").date
    x = np.arange(240, dtype=float)
    panel = pd.DataFrame({
        "date": dates,
        "entry_date": dates,
        "fii_net": x,
        "dii_net": x * 0.5,
        "fii_minus_dii": x * 0.5,
        "fii_plus_dii": x * 1.5,
        "fii_net_z": x,
        "dii_net_z": x,
        "fii_minus_dii_z": x,
        "fwd_1d": x / x.max() * 0.02,
        "fwd_5d": x / x.max() * 0.03,
    })
    availability = {"flow_rows": 240, "index_rows": 260, "source_counts": {"fixture": 240}}

    result = FE.evaluate_panel(panel, availability=availability)

    assert result["observations"] == 240
    assert result["verdict"].startswith("PASS")
    assert "fii_net_5d" in result["usable_features"]
    assert result["results"]["fii_net_5d"]["ic_in_sample"] > 0.99
    assert result["results"]["fii_net_5d"]["cost_adjusted_edge"] > 0
    assert result["results"]["fii_net_5d"]["walk_forward_survives"] is True
