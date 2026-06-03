from __future__ import annotations

from datetime import date

import pandas as pd

from bot import nse_block_deals as NB


CSV = """Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks
02-JUN-2026,RELIANCE,Reliance Industries Ltd,Fund A,BUY,1000,2500.50,-
"""


def _deal_frame(symbol: str, source: str, *, client: str = "Fund A") -> pd.DataFrame:
    frame = pd.DataFrame([
        {
            "date": date(2026, 6, 2),
            "symbol": symbol,
            "side": "BUY",
            "qty": 1000.0,
            "price": 2500.5,
            "client": client,
            "deal_type": "bulk",
            "source": source,
            "source_file": "",
        }
    ])
    return frame


def test_load_manual_deals_reads_named_bulk_and_block_csvs(tmp_path):
    manual_dir = tmp_path / "block_deals"
    manual_dir.mkdir()
    (manual_dir / "operator_bulk_20260602.csv").write_text(CSV, encoding="utf-8")
    (manual_dir / "operator_block_20260602.csv").write_text(CSV.replace("RELIANCE", "TCS"), encoding="utf-8")
    (manual_dir / "unknown_20260602.csv").write_text(CSV.replace("RELIANCE", "INFY"), encoding="utf-8")

    parsed = NB.load_manual_deals(manual_dir=manual_dir)

    assert parsed is not None
    by_symbol = {row["symbol"]: row for row in parsed.to_dict(orient="records")}
    assert set(by_symbol) == {"RELIANCE", "TCS"}
    assert by_symbol["RELIANCE"]["deal_type"] == "bulk"
    assert by_symbol["TCS"]["deal_type"] == "block"
    assert {row["source"] for row in by_symbol.values()} == {"manual_csv"}
    assert "INFY" not in parsed["symbol"].tolist()


def test_fetch_static_archive_uses_archive_url_and_daily_cache(tmp_path):
    calls: list[str] = []

    def fake_fetch(url: str, timeout: int) -> str:
        calls.append(url)
        return CSV

    first = NB.fetch_static_archive("bulk", cache_dir=tmp_path, fetch_text=fake_fetch, fetch_day=date(2026, 6, 3))
    second = NB.fetch_static_archive(
        "bulk",
        cache_dir=tmp_path,
        fetch_text=lambda *_: (_ for _ in ()).throw(AssertionError("cache miss")),
        fetch_day=date(2026, 6, 3),
    )

    assert calls == ["https://archives.nseindia.com/content/equities/bulk.csv"]
    assert first is not None and second is not None
    assert first.iloc[0]["source"] == "static_archive"
    assert second.iloc[0]["symbol"] == "RELIANCE"


def test_deals_history_keeps_manual_duplicate_before_static_and_skips_dynamic(tmp_path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / "bulk_manual.csv").write_text(CSV, encoding="utf-8")
    dynamic_called = False

    def fake_static(deal_type: str, **kwargs):
        if deal_type != "bulk":
            return None
        return pd.concat([
            _deal_frame("RELIANCE", "static_archive"),
            _deal_frame("TCS", "static_archive", client="Fund B"),
        ], ignore_index=True)

    def fake_dynamic(*args, **kwargs):
        nonlocal dynamic_called
        dynamic_called = True
        return _deal_frame("INFY", "dynamic_api")

    rows = NB.deals_history(
        ["RELIANCE", "TCS"],
        start=date(2026, 6, 1),
        end=date(2026, 6, 3),
        manual_dir=manual_dir,
        cache_dir=tmp_path / "cache",
        fetch_static=fake_static,
        fetch_range=fake_dynamic,
    )

    assert rows is not None
    assert dynamic_called is False
    assert rows[rows["symbol"] == "RELIANCE"].iloc[0]["source"] == "manual_csv"
    assert rows[rows["symbol"] == "TCS"].iloc[0]["source"] == "static_archive"
    assert rows.attrs["source_counts"] == {"manual_csv": 1, "static_archive": 1}


def test_deals_history_falls_back_to_dynamic_when_manual_and_static_empty(tmp_path):
    def fake_dynamic(deal_type: str, **kwargs):
        if deal_type != "bulk":
            return None
        return _deal_frame("RELIANCE", "dynamic_api")

    rows = NB.deals_history(
        ["RELIANCE"],
        start=date(2026, 6, 1),
        end=date(2026, 6, 3),
        manual_dir=tmp_path / "missing",
        cache_dir=tmp_path / "cache",
        fetch_static=lambda *args, **kwargs: None,
        fetch_range=fake_dynamic,
    )

    assert rows is not None
    assert rows.iloc[0]["source"] == "dynamic_api"
    assert rows.attrs["source_counts"] == {"dynamic_api": 1}
