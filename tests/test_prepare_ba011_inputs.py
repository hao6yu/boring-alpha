"""Offline BA-011 adapter regressions; every price is generated in tmp_path."""
from __future__ import annotations

import copy
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import socket
import sys

import pytest

pytest.importorskip("exchange_calendars")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import ba011
from tools import prepare_ba011_inputs as m

BASE_QUERY = {"dataset": "GLBX.MDP3", "symbols": "MES.v.0",
              "stype_in": "continuous", "schema": "ohlcv-1m"}


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("BA-011 adapter tests must never access the network")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def scheduled(day, *, early=False):
    return {"date": day, "open_utc": f"{day}T14:30:00+00:00",
            "close_utc": f"{day}T{'18' if early else '21'}:00:00+00:00",
            "full_session": not early}


def bar(day, minute, *, instrument_id=12345, close_ticks=24003):
    local = datetime.fromisoformat(day).replace(
        hour=minute // 60, minute=minute % 60, tzinfo=m.audit.NY)
    return {"hd": {"ts_event": str(int(local.timestamp()) * 10**9),
                   "rtype": 33, "publisher_id": 1, "instrument_id": instrument_id},
            "open": str(24001 * m.audit.TICK_SCALE),
            "high": str(max(24004, close_ticks) * m.audit.TICK_SCALE),
            "low": str(24000 * m.audit.TICK_SCALE),
            "close": str(close_ticks * m.audit.TICK_SCALE), "volume": "7"}


@pytest.fixture
def archive(tmp_path, monkeypatch):
    days = ["2020-12-31", "2021-01-04", "2021-01-05", "2021-11-26",
            "2021-11-29", "2021-12-31", "2022-01-03", "2023-01-03",
            "2023-12-29", "2024-01-02", "2024-12-31", "2025-01-02"]
    calendar = [scheduled(day, early=day == "2021-11-26") for day in days]
    monkeypatch.setattr(m, "calendar_rows", lambda: copy.deepcopy(calendar))
    folder = tmp_path / "source"
    folder.mkdir()
    manifest = {"schema": "databento-mes-history-archive-v1", "status": "complete",
                "dataset": "GLBX.MDP3", "symbol": "MES.v.0", "bar_schema": "ohlcv-1m",
                "start": "2021-01-01", "end": "2026-01-01",
                "quote_attempted_total_usd": "5", "partitions": [],
                "symbology": {"resolved_contract_intervals": [{
                    "d0": "2021-01-01", "d1": "2026-01-01",
                    "instrument_id": 12345, "raw_symbol": "MESH1"}]}}
    rows = {year: [] for year in range(2021, 2026)}
    for day in days:
        year = int(day[:4])
        if year < 2021 or day == "2021-01-05":
            continue
        rows[year].extend(bar(day, minute, close_ticks=24013 if day == "2023-12-29" else 24003)
                          for minute in (570, 929, 930, 959, 960))
    for year in rows:
        manifest["partitions"].append({
            "year": year, "file": f"mes-v0-{year}-ohlcv-1m.jsonl.gz", "status": "complete",
            "query": BASE_QUERY | {"start": f"{year}-01-01", "end": f"{year + 1}-01-01"}})

    def write(*, include_oos=False):
        for part in manifest["partitions"]:
            raw = b"".join(json.dumps(row).encode() + b"\n" for row in rows[part["year"]])
            compressed = gzip.compress(raw, mtime=0)
            # Holdout metadata is present; its files do not exist by default.
            if part["year"] <= 2023 or include_oos:
                (folder / part["file"]).write_bytes(compressed)
            part.update(expected_records=len(rows[part["year"]]),
                        downloaded_records=len(rows[part["year"]]),
                        raw_sha256=hashlib.sha256(raw).hexdigest(),
                        gzip_sha256=hashlib.sha256(compressed).hexdigest())
        source = folder / "manifest.json"
        source.write_text(json.dumps(manifest))
        return source

    return manifest, rows, write, tmp_path / "prepared", calendar


def prepared(archive):
    path = m.prepare(archive[2](), archive[3])
    manifest = json.loads(path.read_text())
    sessions = {}
    for entry in manifest["years"].values():
        for line in gzip.decompress((path.parent / entry["file"]).read_bytes()).splitlines():
            row = json.loads(line)
            sessions[row["date"]] = row
    return path, manifest, sessions


def block_price_files(monkeypatch, *, years):
    names = {f"mes-v0-{year}-ohlcv-1m.jsonl.gz" for year in years}
    for method in ("open", "stat"):
        original = getattr(Path, method)
        def guard(self, *args, _original=original, **kwargs):
            if self.name in names:
                pytest.fail(f"Unauthorized raw price access: {self.name}")
            return _original(self, *args, **kwargs)
        monkeypatch.setattr(Path, method, guard)


def passed_report(path, tmp_path):
    """Generate gate metadata, without running a strategy or calculating returns."""
    manifest = json.loads(path.read_text())
    report = {"schema": "ba011-results-v1", "stage": "development",
              "years": [2021, 2022, 2023], "status": "DEVELOPMENT_PASS",
              "development_passed": True, "data_reconciled": True,
              "held_positions_resolved": True,
              "models": {"base_pilot": {"net_cents": 1, "halt": None}},
              "input_manifest_sha256": ba011.sha256(path),
              "boundary_reference": manifest["boundary_reference"],
              "freeze": ba011.freeze_record(path, manifest)}
    target = tmp_path / "synthetic-development-report.json"
    target.write_text(json.dumps(report))
    return target


def test_development_never_opens_or_stats_holdout_prices_and_publishes_hashes(archive, monkeypatch):
    archive[2]()
    block_price_files(monkeypatch, years=(2024, 2025))
    path, manifest, _ = prepared(archive)
    assert manifest["stage"] == "development"
    assert set(manifest["years"]) == {"2021", "2022", "2023"}
    assert [part["year"] for part in manifest["audit"]["source_partitions"]] == [2021, 2022, 2023]
    assert manifest["source_manifest_sha256"] == m.audit.sha256(Path(manifest["source_manifest"]))
    assert manifest["calendar"]["sha256"] == m.audit.sha256(path.parent / "calendar.json")
    for entry in manifest["years"].values():
        target = path.parent / entry["file"]
        assert entry["sha256"] == m.audit.sha256(target)
        assert target.stat().st_mode & 0o222 == 0
    assert path.stat().st_mode & 0o222 == 0


def test_inclusive_exit_minute_missing_intervals_and_empty_sessions_are_preserved(archive):
    path, manifest, sessions = prepared(archive)
    assert [b[0] for b in sessions["2021-01-04"]["bars"]] == [570, 929, 930, 959, 960]
    assert sessions["2021-01-05"]["bars"] == []
    missing = {r["date"]: r["minutes"] for r in manifest["years"]["2021"]["missing_by_session"]}
    assert len(missing["2021-01-04"]) == 386
    assert 931 in missing["2021-01-04"] and 960 not in missing["2021-01-04"]
    assert missing["2021-01-05"] == list(range(570, 961))
    assert "2021-11-26" not in sessions
    assert manifest["audit"]["missing_minutes_are_retained"] is True
    assert manifest["audit"]["excluded_source_bars"] == {"outside_selected_full_session_window": 5}
    # The strategy reader accepts the adapter's metadata without opening prices from another stage.
    assert len(ba011.read_sessions(path, manifest, (2021, 2022, 2023))) == len(sessions)


def test_exact_predecessors_include_early_closes_missing_history_and_year_boundary(archive):
    _, _, sessions = prepared(archive)
    first = sessions["2021-01-04"]
    assert first["previous_session_date"] == "2020-12-31"
    assert first["previous_session_full"] is True and first["previous_close_ticks"] is None
    following_early = sessions["2021-11-29"]
    assert following_early["previous_session_date"] == "2021-11-26"
    assert following_early["previous_session_full"] is False
    assert following_early["previous_close_ticks"] is None
    january = sessions["2022-01-03"]
    assert january["previous_session_date"] == "2021-12-31"
    assert january["previous_close_ticks"] == 24003
    assert january["previous_instrument_id"] == 12345


def test_reference_preserves_contract_identity_across_a_roll(archive):
    manifest, rows, _, _, _ = archive
    manifest["symbology"]["resolved_contract_intervals"] = [
        {"d0": "2021-01-01", "d1": "2022-01-01", "instrument_id": 12345, "raw_symbol": "MESH1"},
        {"d0": "2022-01-01", "d1": "2026-01-01", "instrument_id": 54321, "raw_symbol": "MESH2"}]
    for year in (2022, 2023, 2024, 2025):
        for row in rows[year]:
            row["hd"]["instrument_id"] = 54321
    _, _, sessions = prepared(archive)
    january = sessions["2022-01-03"]
    assert (january["symbol"], january["instrument_id"]) == ("MESH2", 54321)
    assert (january["previous_symbol"], january["previous_instrument_id"]) == ("MESH1", 12345)
    assert ba011.candidate_order(january)[0] is None


def test_full_391_minute_session_is_complete(archive):
    archive[1][2022] = [bar("2022-01-03", minute) for minute in range(570, 961)]
    _, manifest, sessions = prepared(archive)
    assert manifest["years"]["2022"]["complete_sessions"] == 1
    assert manifest["years"]["2022"]["missing_minutes"] == 0
    assert len(sessions["2022-01-03"]["bars"]) == 391


@pytest.mark.parametrize("field,value", [("gzip_sha256", "0" * 64),
    ("raw_sha256", "0" * 64), ("expected_records", 1), ("status", "attempting")])
def test_selected_archive_must_reconcile_before_manifest_publication(archive, field, value):
    manifest, _, write, output, _ = archive
    source = write()
    manifest["partitions"][0][field] = value
    source.write_text(json.dumps(manifest))
    with pytest.raises(m.audit.AuditError):
        m.prepare(source, output)
    assert not list(output.glob("*/manifest.json"))


@pytest.mark.parametrize("gate", ["missing", "failed", "changed_source", "changed_calendar", "changed_boundary"])
def test_oos_refuses_unpassed_or_changed_development_before_price_access(archive, monkeypatch, tmp_path, gate):
    path, _, _ = prepared(archive)
    report_path = passed_report(path, tmp_path)
    source = Path(json.loads(path.read_text())["source_manifest"])
    kwargs = {"development_report": report_path, "development_manifest": path}
    if gate == "missing":
        kwargs = {}
    elif gate == "failed":
        report = json.loads(report_path.read_text())
        report["development_passed"] = False
        report_path.write_text(json.dumps(report))
    elif gate == "changed_source":
        source.write_text(source.read_text() + "\n")
    elif gate == "changed_calendar":
        archive[4].append(scheduled("2025-12-31"))
    else:
        manifest = json.loads(path.read_text())
        manifest["boundary_reference"]["close_ticks"] += 1
        path.chmod(0o644)
        path.write_text(json.dumps(manifest))
    block_price_files(monkeypatch, years=range(2021, 2026))
    with pytest.raises((m.audit.AuditError, ba011.Refusal)):
        m.prepare(source, archive[3] / "oos", stage="oos", **kwargs)


def test_passed_oos_uses_hashed_boundary_without_reopening_development_prices(archive, monkeypatch, tmp_path):
    source = archive[2](include_oos=True)
    path = m.prepare(source, archive[3])
    dev = json.loads(path.read_text())
    assert dev["boundary_reference"] == {"date": "2023-12-29", "full_session": True,
        "symbol": "MESH1", "instrument_id": 12345, "close_ticks": 24013}
    report_path = passed_report(path, tmp_path)
    block_price_files(monkeypatch, years=(2021, 2022, 2023))
    oos_path = m.prepare(source, archive[3] / "oos", stage="oos",
                         development_report=report_path, development_manifest=path)
    oos = json.loads(oos_path.read_text())
    assert set(oos["years"]) == {"2024", "2025"}
    first = json.loads(gzip.decompress(
        (oos_path.parent / oos["years"]["2024"]["file"]).read_bytes()).splitlines()[0])
    assert first["previous_session_date"] == "2023-12-29"
    assert first["previous_close_ticks"] == 24013
    assert oos["development_input"]["sha256"] == m.audit.sha256(path)


def test_metadata_calendar_covers_initial_predecessor_dst_and_actual_closures():
    rows = {r["date"]: r for r in m.calendar_rows()}
    assert rows["2020-12-31"]["full_session"] is True
    assert rows["2021-03-12"]["open_utc"].endswith("14:30:00+00:00")
    assert rows["2021-03-15"]["open_utc"].endswith("13:30:00+00:00")
    assert rows["2021-11-26"]["full_session"] is False
    assert "2025-01-09" not in rows
