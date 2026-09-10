"""Minute-audit checks protect against false synchronization and interpolation."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("minute_audit", Path(__file__).parents[1] / "tools/us_futures_minute_audit.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def row(stamp, close=100, volume=1):
    return {"start": stamp, "open": close, "close": close, "high": close, "low": close, "volume": volume}


def test_sample_and_page_budget_fixed_in_advance():
    pages = m.windows(m.START, m.END)
    assert m.hourly.iso(m.START) == "2026-09-08T00:00:00+00:00"
    assert m.hourly.iso(m.END) == "2026-09-10T00:00:00+00:00"
    assert len(pages) == 10
    assert 4 * (1 + len(pages)) == 44
    assert sum((b - a) // 60 for a, b in pages) == 2880
    assert all(b - a <= 300 * 60 for a, b in pages)
    assert all(a[1] == b[0] for a, b in zip(pages, pages[1:]))
    with pytest.raises(ValueError):
        m.windows(0, 49 * 3600)


def test_latest_common_minute_differs_from_final_trade_minute():
    # Perp moved after the dated leg's last trade. Exact common-minute gap is 5,
    # versus the asynchronous hourly gap of -5, despite matching hourly closes.
    p = [row(55 * 60, 100), row(59 * 60, 110)]
    d = [row(55 * 60, 105)]
    result = m.audit_pair(p, d, [row(0, 110)], [row(0, 105)], 0, 3600)
    r = result["hours"][0]
    assert r["perp_last_trade_minute_lag_from_hour_end"] == 0
    assert r["dated_last_trade_minute_lag_from_hour_end"] == 4
    assert r["last_trade_minute_separation"] == 4
    assert r["last_common_minute_gap_usd_per_underlying"] == 5
    assert r["hourly_gap_usd_per_underlying"] == -5
    assert r["hourly_gap_minus_common_minute_gap_usd"] == -10
    assert r["timing_comparison_valid"] is True
    assert result["matched_hours_sign_changes"] == 1


def test_no_common_minute_never_carries_prices_or_crosses_hour():
    result = m.audit_pair([row(0), row(3600)], [row(60), row(3540)],
                          [row(0), row(3600)], [row(0)], 0, 7200)
    assert result["hours_with_common_active_minute"] == 0
    assert result["matched_hours_common_minute_gap_usd"] is None
    assert result["hours"][1]["dated_last_trade_minute"] is None


def test_zero_volume_candle_is_not_a_trade_match():
    result = m.audit_pair([row(3540)], [row(3540, volume=0)], [row(0)], [row(0)], 0, 3600)
    assert result["hours_with_common_active_minute"] == 0
    assert result["hours"][0]["dated_active_minutes"] == 0


def test_revised_or_inconsistent_hourly_close_excluded_from_timing_aggregate():
    result = m.audit_pair([row(3540)], [row(3540, 105)], [row(0, 101)], [row(0, 105)], 0, 3600)
    assert result["hours_with_common_active_minute"] == 1
    assert result["perp_hourly_close_mismatches"] == 1
    assert result["hours_with_reconciled_closes_and_common_minute"] == 0
    assert result["matched_hours_absolute_gap_difference_usd"] is None
    assert result["hours"][0]["hourly_gap_minus_common_minute_gap_usd"] == -1


@pytest.mark.parametrize("change", [{"start": 1}, {"start": 60}, {"close": float("nan")},
                                     {"low": 101}, {"volume": -1}])
def test_invalid_minute_data_rejected(change):
    with pytest.raises(ValueError):
        m.normalize_minutes({"candles": [row(0) | change]}, 0, 60)


def test_missing_duplicates_and_oversized_pages():
    assert m.normalize_minutes({"candles": [row(120), row(0)]}, 0, 180) == [row(0), row(120)]
    with pytest.raises(ValueError, match="duplicate"):
        m.normalize_minutes({"candles": [row(0), row(0)]}, 0, 60)
    with pytest.raises(ValueError, match="oversized"):
        m.normalize_minutes({"candles": [row(0)] * 301}, 0, 18060)


def test_checksum_and_unsafe_reference_path(tmp_path):
    p = tmp_path / "raw.json"
    raw = b'{"candles":[]}'
    p.write_bytes(raw)
    source = {"sha256": m.hashlib.sha256(raw).hexdigest()}
    assert m.checked_bytes(tmp_path, p.name, source) == raw
    p.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="checksum"):
        m.checked_bytes(tmp_path, p.name, source)
    with pytest.raises(ValueError, match="unsafe"):
        m.checked_bytes(tmp_path, "../raw.json", source)


def test_extrema_sort_by_absolute_hourly_gap_with_stable_time_tie():
    p = [row(i * 3600 + 3540, 100) for i in range(6)]
    d = [row(i * 3600 + 3540, 100 + gap) for i, gap in enumerate((1, -8, 3, 8, -9, 4))]
    ph, dh = [[r | {"start": r["start"] - 3540} for r in series] for series in (p, d)]
    result = m.audit_pair(p, d, ph, dh, 0, 6 * 3600)
    assert [r["hourly_gap_usd_per_underlying"] for r in result["five_largest_absolute_hourly_gaps"]] == [-9, -8, 8, 4, 3]


def test_reference_window_selection_is_fixed_to_existing_hourly_manifest():
    manifest = {"schema": m.hourly.SCHEMA, "pairs": {k: list(v) for k, v in m.PAIRS.items()},
                "start": m.hourly.parse_time("2026-06-12T00:00:00Z"), "end_exclusive": m.END}
    selected = m.reference_sources(manifest, m.START, m.END)
    assert len(selected) == 4
    assert all(len(pages) == 1 for pages in selected.values())
    with pytest.raises(ValueError, match="does not cover"):
        m.reference_sources(manifest, m.START, m.END + 3600)


def test_complete_archive_replays_without_original_directory_or_network(tmp_path, monkeypatch):
    reference = tmp_path / "reference"
    reference.mkdir()
    manifest = {"schema": m.hourly.SCHEMA, "pairs": m.PAIRS,
                "start": m.START, "end_exclusive": m.END, "sources": {}}

    def product(pid):
        root = next(root for root, pair in m.PAIRS.items() if pid in pair)
        return {"product_id": pid, "product_venue": "FCM", "product_type": "FUTURE",
                "future_product_details": {"contract_root_unit": root}}

    def archive(name, path, payload):
        raw = json.dumps(payload).encode()
        (reference / name).write_bytes(raw)
        manifest["sources"][name] = {"url": m.hourly.API + path,
                                      "sha256": m.hashlib.sha256(raw).hexdigest()}

    for pair in m.PAIRS.values():
        for pid in pair:
            archive(f"{pid}-product.json", f"products/{pid}", product(pid))
            query = m.urllib.parse.urlencode({"start": m.START, "end": m.END - 1,
                                              "granularity": "ONE_HOUR", "limit": 350})
            archive(f"{pid}-{m.START}-{m.END}.json", f"products/{pid}/candles?{query}",
                    {"candles": [row(t) for t in range(m.START, m.END, 3600)]})
    (reference / "manifest.json").write_text(json.dumps(manifest))

    requests = []

    def fake_fetch(path):
        requests.append(path)
        pid = path.split("/")[1]
        if "/candles?" in path:
            params = m.urllib.parse.parse_qs(m.urllib.parse.urlparse(path).query)
            payload = {"candles": [row(int(params["start"][0]))]}
        else:
            payload = product(pid)
        raw = json.dumps(payload).encode()
        return raw, {"url": m.hourly.API + path, "sha256": m.hashlib.sha256(raw).hexdigest()}

    monkeypatch.setattr(m.hourly, "fetch", fake_fetch)
    folder = m.collect(tmp_path / "audits", reference)
    assert len(requests) == 44
    assert m.analyze(folder) == json.loads((folder / "report.json").read_text())
    reference.rename(tmp_path / "moved-reference")

    def no_network(path):
        raise AssertionError("offline replay tried to use network")

    monkeypatch.setattr(m.hourly, "fetch", no_network)
    assert m.analyze(folder)["network_requests"] == 44
    saved = json.loads((folder / "manifest.json").read_text())
    name = next(name for name in saved["sources"] if "product" not in name)
    saved["sources"][name]["url"] += "wrong"
    (folder / "manifest.json").write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="URL"):
        m.load_snapshot(folder)
