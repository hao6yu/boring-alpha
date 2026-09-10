"""Data-integrity regressions for the public U.S. paired-candle importer."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("us_futures_history", Path(__file__).parents[1] / "tools/us_futures_history.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def candle(stamp=0, close=100, volume=2):
    return {"start": str(stamp), "open": "100", "high": str(max(100, close)),
            "low": str(min(100, close)), "close": str(close), "volume": str(volume)}


def test_90_day_pagination_never_truncates_or_overlaps():
    pages = m.windows(0, 90 * 24 * m.HOUR)
    assert len(pages) == 8
    assert pages[0] == (0, 300 * m.HOUR)
    assert all((b - a) // m.HOUR <= 300 for a, b in pages)
    assert sum((b - a) // m.HOUR for a, b in pages) == 2160
    assert all(left[1] == right[0] for left, right in zip(pages, pages[1:]))
    with pytest.raises(ValueError):
        m.windows(0, 91 * 24 * m.HOUR)


def test_missing_candles_are_not_filled():
    rows = m.normalize_candles({"candles": [candle(7200), candle(0)]}, 0, 10800)
    assert [row["start"] for row in rows] == [0, 7200]
    report = m.describe_pair(rows, rows, 0, 10800)
    assert report["paired_buckets"] == 2
    assert report["missing_paired_ranges"][0]["hours"] == 1
    assert report["gap_changes_usd_per_underlying_contiguous_positive_volume_hours"]["1"] is None


@pytest.mark.parametrize("change", [{"start": "1"}, {"start": "3600"}, {"close": "nan"},
                                     {"low": "101"}, {"volume": "-1"}, {"close": "0"}])
def test_rejects_bad_or_out_of_window_bars(change):
    with pytest.raises(ValueError):
        m.normalize_candles({"candles": [candle() | change]}, 0, 3600)


def test_rejects_duplicates_and_oversized_response():
    with pytest.raises(ValueError, match="duplicate"):
        m.normalize_candles({"candles": [candle(), candle()]}, 0, 3600)
    with pytest.raises(ValueError, match="350"):
        m.normalize_candles({"candles": [candle()] * 351}, 0, 3600)


def test_pair_exact_join_and_narrowing_sign_excludes_zero_volume():
    perp = m.normalize_candles({"candles": [candle(0), candle(3600), candle(7200, volume=0)]}, 0, 10800)
    dated = m.normalize_candles({"candles": [candle(0, 110), candle(3600, 104), candle(7200, 90)]}, 0, 10800)
    report = m.describe_pair(perp, dated, 0, 10800)
    assert report["both_have_reported_volume_buckets"] == 2
    assert report["gap_usd_per_underlying_on_positive_volume_buckets"]["min"] == 4
    assert report["gap_changes_usd_per_underlying_contiguous_positive_volume_hours"]["1"]["min"] == -6


def test_archive_replays_validates_urls_and_detects_tampering(tmp_path, monkeypatch):
    def fake_fetch(path):
        pid = path.split("/")[1]
        if "/candles?" in path:
            payload = {"candles": [candle()]}
        else:
            root = next(root for root, pair in m.PAIRS.items() if pid in pair)
            payload = {"product_id": pid, "product_venue": "FCM", "product_type": "FUTURE",
                       "future_product_details": {"contract_root_unit": root}}
        raw = json.dumps(payload).encode()
        return raw, {"url": m.API + path, "sha256": m.hashlib.sha256(raw).hexdigest()}
    monkeypatch.setattr(m, "fetch", fake_fetch)
    folder = m.collect(0, 3600, tmp_path)
    assert m.analyze(folder) == json.loads((folder / "report.json").read_text())
    manifest = json.loads((folder / "manifest.json").read_text())
    name = next(iter(manifest["sources"]))
    manifest["sources"][name]["url"] += "wrong-product"
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="URL"):
        m.load_snapshot(folder)
    manifest["sources"][name]["url"] = manifest["sources"][name]["url"].removesuffix("wrong-product")
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with (folder / name).open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="checksum"):
        m.analyze(folder)


def test_refuses_overwriting_archive_file(tmp_path):
    target = tmp_path / "manifest.json"
    m.write_new(target, {"one": 1})
    with pytest.raises(FileExistsError):
        m.write_new(target, {"two": 2})
