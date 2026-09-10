"""Offline MES audit regressions, using generated rows and temporary archives."""
import copy
from datetime import datetime
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import socket

import pytest


pytest.importorskip("exchange_calendars")
SPEC = importlib.util.spec_from_file_location(
    "audit_mes_history", Path(__file__).parents[1] / "tools/audit_mes_history.py"
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

MINUTE_NS = 60 * 10**9
FIRST_DAYS = {2021: "2021-01-04", 2022: "2022-01-03", 2023: "2023-01-03",
              2024: "2024-01-02", 2025: "2025-01-02"}
BASE_QUERY = {"dataset": "GLBX.MDP3", "symbols": "MES.v.0",
              "stype_in": "continuous", "schema": "ohlcv-1m"}


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("MES audit tests must never access the network")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def ns(value):
    return int(datetime.fromisoformat(value).timestamp()) * 10**9


def bar(value="2021-01-04T14:30:00+00:00", instrument_id=12345):
    return {"hd": {"ts_event": str(ns(value)), "rtype": 33,
                   "publisher_id": 1, "instrument_id": instrument_id},
            "open": "6000250000000", "high": "6001000000000",
            "low": "6000000000000", "close": "6000750000000", "volume": "7"}


def interval(d0="2021-01-01", d1="2026-01-01", instrument_id=12345,
             raw_symbol="MESH1"):
    return {"d0": d0, "d1": d1, "instrument_id": instrument_id,
            "raw_symbol": raw_symbol}


def decode(item, *, mappings=None, previous=-1):
    mappings = [interval()] if mappings is None else mappings
    starts = [m.timestamp_ns(row["d0"]) for row in mappings]
    return m.decode_bar(json.dumps(item).encode() + b"\n", mappings, starts, previous)


def scheduled(day, *, early=False):
    return {"date": day, "open_utc": f"{day}T14:30:00+00:00",
            "close_utc": f"{day}T{'18' if early else '21'}:00:00+00:00",
            "full_session": not early}


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """Only five sparse synthetic sessions; production data is never opened."""
    schedule = {day: scheduled(day) for day in FIRST_DAYS.values()}
    schedule["2021-11-26"] = scheduled("2021-11-26", early=True)
    monkeypatch.setattr(m, "calendar_rows", lambda: copy.deepcopy(schedule))
    folder = tmp_path / "source"
    folder.mkdir()
    manifest = {"schema": "databento-mes-history-archive-v1", "status": "complete",
                "dataset": "GLBX.MDP3", "symbol": "MES.v.0", "bar_schema": "ohlcv-1m",
                "start": "2021-01-01", "end": "2026-01-01",
                "quote_attempted_total_usd": "5",
                "symbology": {"resolved_contract_intervals": [interval()]},
                "partitions": []}
    rows = {}
    for year, day in FIRST_DAYS.items():
        rows[year] = [bar(f"{day}T14:30:00+00:00"), bar(f"{day}T14:32:00+00:00")]
        manifest["partitions"].append({
            "year": year, "file": f"mes-v0-{year}-ohlcv-1m.jsonl.gz", "status": "complete",
            "query": BASE_QUERY | {"start": f"{year}-01-01", "end": f"{year+1}-01-01"},
        })

    def write():
        for part in manifest["partitions"]:
            raw = b"".join(json.dumps(row).encode() + b"\n" for row in rows[part["year"]])
            compressed = gzip.compress(raw, mtime=0)
            (folder / part["file"]).write_bytes(compressed)
            part.update(expected_records=len(rows[part["year"]]),
                        downloaded_records=len(rows[part["year"]]),
                        raw_sha256=hashlib.sha256(raw).hexdigest(),
                        gzip_sha256=hashlib.sha256(compressed).hexdigest())
        source = folder / "manifest.json"
        source.write_text(json.dumps(manifest))
        return source

    return manifest, rows, write, tmp_path / "audited", schedule


def run(archive):
    _, _, write, output, _ = archive
    return m.audit(write(), output)


def test_historical_calendar_obeys_dst_early_closes_and_exceptional_closure():
    rows = m.calendar_rows()
    assert rows["2021-03-12"]["open_utc"] == "2021-03-12T14:30:00+00:00"
    assert rows["2021-03-15"]["open_utc"] == "2021-03-15T13:30:00+00:00"
    assert rows["2021-11-05"]["open_utc"] == "2021-11-05T13:30:00+00:00"
    assert rows["2021-11-08"]["open_utc"] == "2021-11-08T14:30:00+00:00"
    assert rows["2021-06-18"]["full_session"]  # Juneteenth closure began in 2022.
    assert rows["2021-12-31"]["full_session"]  # Saturday New Year's exception.
    assert "2022-06-20" not in rows
    assert "2025-01-09" not in rows  # Carter funeral, not an ordinary holiday.
    assert "2025-04-18" not in rows  # Good Friday.
    for day in ("2021-11-26", "2023-07-03", "2024-12-24", "2025-11-28"):
        assert not rows[day]["full_session"]
        close = datetime.fromisoformat(rows[day]["close_utc"]).astimezone(m.NY)
        assert (close.hour, close.minute) == (13, 0)
    assert all("2021-01-01" <= day < "2026-01-01" for day in rows)


@pytest.mark.parametrize("value", [True, False, 1.0, None, [], {}, "1.0", "1e3", "-1",
                                   "+1", " 1", "1 ", "", "9" * 21])
def test_market_integer_rejects_nonintegral_or_ambiguous_encoding(value):
    with pytest.raises(m.AuditError):
        m.integer(value)


def test_decode_converts_fixed_prices_to_exact_integer_ticks_and_local_minute():
    stamp, day, inst, symbol, values = decode(bar())
    assert stamp == ns("2021-01-04T14:30:00+00:00")
    assert (day, inst, symbol) == ("2021-01-04", 12345, "MESH1")
    assert values == [570, 24001, 24004, 24000, 24003, 7]
    summer = bar("2021-06-18T13:30:00+00:00")
    assert decode(summer)[-1][0] == 570
    assert m.integer("18446744073709551615") == 2**64 - 1


def test_sha256_covers_all_chunks_and_empty_files(tmp_path):
    path = tmp_path / "generated-bytes.bin"
    for content in (b"", b"synthetic" * 150_000 + b"final bytes"):
        path.write_bytes(content)
        assert m.sha256(path) == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize("field,value", [
    ("open", "6000250000001"), ("close", 0), ("high", 2**63),
    ("low", -m.TICK_SCALE), ("high", "6000000000000"),
    ("low", "6000500000000"), ("close", "6001250000000"),
    ("volume", 0), ("volume", 2**64), ("volume", True), ("open", 6000250000000.0),
])
def test_decode_rejects_off_tick_impossible_ohlc_and_invalid_volume(field, value):
    item = bar()
    item[field] = value
    with pytest.raises(m.AuditError):
        decode(item)


@pytest.mark.parametrize("field,value", [("rtype", 32), ("instrument_id", 0),
                                         ("instrument_id", 99), ("ts_event", True)])
def test_decode_rejects_bad_header_and_instrument_mapping(field, value):
    item = bar()
    item["hd"][field] = value
    with pytest.raises(m.AuditError):
        decode(item)


def test_decode_rejects_duplicate_unordered_and_partial_minute_timestamps():
    item = bar()
    stamp = int(item["hd"]["ts_event"])
    for previous in (stamp, stamp + MINUTE_NS):
        with pytest.raises(m.AuditError):
            decode(item, previous=previous)
    item["hd"]["ts_event"] = str(stamp + 1)
    with pytest.raises(m.AuditError):
        decode(item)


def test_dated_mapping_is_start_inclusive_end_exclusive_and_changes_at_boundary():
    mappings = [interval(d1="2021-03-15"),
                interval(d0="2021-03-15", instrument_id=54321, raw_symbol="MESM1")]
    assert decode(bar("2021-03-14T23:59:00+00:00"), mappings=mappings)[3] == "MESH1"
    assert decode(bar("2021-03-15T00:00:00+00:00", 54321), mappings=mappings)[3] == "MESM1"
    with pytest.raises(m.AuditError):
        decode(bar("2021-03-15T00:00:00+00:00"), mappings=mappings)
    for value in ("2020-12-31T23:59:00+00:00", "2026-01-01T00:00:00+00:00"):
        with pytest.raises(m.AuditError):
            decode(bar(value), mappings=mappings)


def test_audit_preserves_missing_minutes_empty_sessions_hashes_counts_and_exclusions(archive):
    manifest, rows, _, _, schedule = archive
    schedule["2021-01-05"] = scheduled("2021-01-05")  # An entirely absent session remains.
    rows[2021].insert(0, bar("2021-01-04T14:29:00+00:00"))
    rows[2021].extend([bar("2021-01-04T21:00:00+00:00"),
                       bar("2021-11-26T14:30:00+00:00")])
    rows[2025].append(bar("2025-01-09T14:30:00+00:00"))
    result_path = run(archive)
    result = json.loads(result_path.read_text())
    assert result["source_manifest_sha256"] == hashlib.sha256(
        Path(result["source_manifest"]).read_bytes()).hexdigest()
    assert result["calendar"]["sha256"] == hashlib.sha256(
        (result_path.parent / "calendar.json").read_bytes()).hexdigest()
    assert result["audit"]["reconciled"] is True
    assert result["audit"]["all_held_positions_resolved"] == "not_yet_evaluated"
    assert result["audit"]["missing_minutes_are_retained"] is True
    assert result["audit"]["excluded_source_bars"] == {
        "bars_outside_cash_window": 2, "bars_on_scheduled_early_close": 1,
        "bars_on_non_nyse_session": 1,
    }
    for part, reported in zip(manifest["partitions"], result["audit"]["source_partitions"]):
        assert reported["source_records"] == part["expected_records"] == part["downloaded_records"]
        assert reported["full_session_bars"] == 2
    for year, record in result["years"].items():
        target = result_path.parent / record["file"]
        assert hashlib.sha256(target.read_bytes()).hexdigest() == record["sha256"]
        sessions = [json.loads(line) for line in gzip.decompress(target.read_bytes()).splitlines()]
        assert sessions[0]["bars"] == [[570, 24001, 24004, 24000, 24003, 7],
                                        [572, 24001, 24004, 24000, 24003, 7]]
        assert 571 in record["missing_by_session"][0]["minutes"]
        assert 570 not in record["missing_by_session"][0]["minutes"]
        assert record["complete_sessions"] == 0
        if year == "2021":
            assert record["full_sessions"] == 2
            assert record["missing_minutes"] == 388 + 390
            assert sessions[1] == {"date": "2021-01-05", "instrument_id": 12345,
                                   "symbol": "MESH1", "bars": []}
            assert record["early_closes"] == ["2021-11-26"]
        else:
            assert record["full_sessions"] == 1
            assert record["missing_minutes"] == 388
        assert target.stat().st_mode & 0o222 == 0
    assert result_path.stat().st_mode & 0o222 == 0


def test_complete_session_contains_exactly_the_390_observed_minutes(archive):
    _, rows, _, _, _ = archive
    prototype = rows[2023][0]
    opening = int(prototype["hd"]["ts_event"])
    rows[2023] = []
    for minute in range(390):
        item = copy.deepcopy(prototype)
        item["hd"]["ts_event"] = str(opening + minute * MINUTE_NS)
        rows[2023].append(item)
    result_path = run(archive)
    result = json.loads(result_path.read_text())
    year = result["years"]["2023"]
    assert year["full_sessions"] == year["complete_sessions"] == 1
    assert year["missing_minutes"] == 0
    assert year["missing_by_session"] == []
    raw = gzip.decompress((result_path.parent / year["file"]).read_bytes())
    assert [item[0] for item in json.loads(raw)["bars"]] == list(range(570, 960))


@pytest.mark.parametrize("field,value", [("gzip_sha256", "0" * 64), ("raw_sha256", "0" * 64),
                                         ("expected_records", 3), ("downloaded_records", 1),
                                         ("expected_records", True), ("downloaded_records", 0),
                                         ("expected_records", 2.0),
                                         ("status", "attempting")])
def test_archive_hash_count_or_completion_mismatch_blocks_publication(archive, field, value):
    manifest, _, write, output, _ = archive
    source = write()
    manifest["partitions"][0][field] = value
    source.write_text(json.dumps(manifest))
    with pytest.raises(m.AuditError):
        m.audit(source, output)
    assert not list(output.glob("*/manifest.json"))


@pytest.mark.parametrize("value", ["2020-12-31T23:59:00+00:00", "2022-01-01T00:00:00+00:00"])
def test_bar_outside_annual_half_open_bounds_is_rejected(archive, value):
    _, rows, _, _, _ = archive
    rows[2021] = [bar(value)]
    with pytest.raises(m.AuditError):
        run(archive)


@pytest.mark.parametrize("field,value", [("start", "2020-01-01"), ("end", "2023-01-01"),
                                         ("symbols", "ES.v.0"), ("schema", "ohlcv-1s"),
                                         ("dataset", "OTHER.DATA"), ("stype_in", "raw_symbol")])
def test_annual_query_must_match_partition_year_and_frozen_data_scope(archive, field, value):
    manifest, _, _, _, _ = archive
    manifest["partitions"][0]["query"][field] = value
    with pytest.raises(m.AuditError):
        run(archive)


@pytest.mark.parametrize("field,value", [("schema", "other-archive"), ("status", "attempting"),
                                         ("dataset", "OTHER.DATA"), ("symbol", "ES.v.0"),
                                         ("start", "2020-01-01"), ("end", "2027-01-01")])
def test_top_level_archive_scope_is_bound(archive, field, value):
    manifest, _, _, _, _ = archive
    manifest[field] = value
    with pytest.raises(m.AuditError):
        run(archive)


def test_duplicate_annual_partition_cannot_hide_a_missing_year(archive):
    manifest, _, _, _, _ = archive
    source = archive[2]()
    manifest["partitions"][1] = copy.deepcopy(manifest["partitions"][0])
    source.write_text(json.dumps(manifest))
    with pytest.raises(m.AuditError):
        m.audit(source, archive[3])


@pytest.mark.parametrize("mappings", [
    [interval(d1="2021-01-03"), interval(d0="2021-01-02")],  # overlap
    [interval(d1="2021-01-02"), interval(d0="2021-01-03")],  # weekend gap
    [interval(d0="2020-12-31")], [interval(d1="2026-01-02")],
    [interval(d0="2021-01-01T00:00:00+00:00")],
    [interval(d1="2021-01-02", raw_symbol="ESH1"), interval(d0="2021-01-02")],
    [interval(d1="2021-01-02", instrument_id=True), interval(d0="2021-01-02")],
    [interval(d1="2021-01-02", instrument_id=2**32), interval(d0="2021-01-02")],
])
def test_mapping_integrity_is_checked_even_where_no_bar_or_session_exists(archive, mappings):
    manifest, _, _, _, _ = archive
    manifest["symbology"]["resolved_contract_intervals"] = mappings
    with pytest.raises(m.AuditError):
        run(archive)


def test_missing_mapping_for_a_full_session_blocks_publication(archive):
    manifest, _, _, _, _ = archive
    manifest["symbology"]["resolved_contract_intervals"] = [interval(d1="2025-01-01")]
    with pytest.raises(m.AuditError):
        run(archive)
