#!/usr/bin/env python3
"""Audit an immutable MES archive and emit full-NYSE-session inputs, no returns."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

ROOT = Path(__file__).resolve().parents[1]
NY = ZoneInfo("America/New_York")
TICK_SCALE = 250_000_000


class AuditError(ValueError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def integer(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,20}", value):
        return int(value)
    raise AuditError("Nonintegral market-data field")


def timestamp_ns(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise AuditError("Expected a canonical UTC date boundary")
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()) * 10**9


def validate_manifest(manifest):
    expected = {"schema": "databento-mes-history-archive-v1", "status": "complete",
                "dataset": "GLBX.MDP3", "symbol": "MES.v.0", "bar_schema": "ohlcv-1m",
                "start": "2021-01-01", "end": "2026-01-01"}
    if any(manifest.get(k) != v for k,v in expected.items()):
        raise AuditError("Require the complete fixed MES archive")
    partitions = manifest["partitions"]
    if any(type(p["year"]) is not int for p in partitions) or sorted(p["year"] for p in partitions) != list(range(2021, 2026)):
        raise AuditError("Expected exactly five annual partitions")
    for part in partitions:
        year = part["year"]
        query = {"dataset": "GLBX.MDP3", "symbols": "MES.v.0", "stype_in": "continuous", "schema": "ohlcv-1m",
                 "start": f"{year}-01-01", "end": f"{year+1}-01-01"}
        if part["query"] != query or part["file"] != f"mes-v0-{year}-ohlcv-1m.jsonl.gz":
            raise AuditError("Partition differs from fixed annual request")
        for key in ("expected_records", "downloaded_records"):
            if type(part[key]) is not int or not 0 < part[key] <= 366 * 1440:
                raise AuditError("Invalid annual record count")
    intervals = manifest["symbology"]["resolved_contract_intervals"]
    cursor = "2021-01-01"
    if not isinstance(intervals, list) or not intervals:
        raise AuditError("Missing contract intervals")
    for row in intervals:
        timestamp_ns(row["d0"])
        timestamp_ns(row["d1"])
        if row["d0"] != cursor or not row["d0"] < row["d1"] <= "2026-01-01":
            raise AuditError("Gap, overlap, or invalid contract interval")
        if type(row["instrument_id"]) is not int or not 0 < row["instrument_id"] < 2**32:
            raise AuditError("Invalid mapped identifier")
        if not isinstance(row["raw_symbol"], str) or not re.fullmatch(r"MES[HMUZ][0-9]{1,2}", row["raw_symbol"]):
            raise AuditError("Unexpected mapped contract")
        cursor = row["d1"]
    if cursor != "2026-01-01":
        raise AuditError("Incomplete mapping coverage")


def calendar_rows():
    calendar = xcals.get_calendar("XNYS", start="2021-01-01", end="2025-12-31")
    rows = {}
    for day, record in calendar.schedule.iterrows():
        opening, closing = record["open"].to_pydatetime(), record["close"].to_pydatetime()
        local_open, local_close = opening.astimezone(NY), closing.astimezone(NY)
        full = (local_open.hour, local_open.minute, local_close.hour, local_close.minute) == (9, 30, 16, 0)
        rows[str(day.date())] = {"date": str(day.date()), "open_utc": opening.isoformat(),
            "close_utc": closing.isoformat(), "full_session": full}
    return rows


def decode_bar(raw, intervals, starts, previous):
    item = json.loads(raw)
    hd = item["hd"]
    stamp = integer(hd["ts_event"])
    inst = integer(hd["instrument_id"])
    if integer(hd["rtype"]) != 33 or inst <= 0 or stamp <= previous or stamp % (60 * 10**9):
        raise AuditError("Bad record type, timestamp ordering, or identifier")
    location = bisect_right(starts, stamp) - 1
    if location < 0:
        raise AuditError("Missing contract mapping")
    mapping = intervals[location]
    if stamp >= timestamp_ns(mapping["d1"]) or inst != mapping["instrument_id"]:
        raise AuditError("Bar differs from dated contract mapping")
    if not re.fullmatch(r"MES[HMUZ][0-9]{1,2}", mapping["raw_symbol"]):
        raise AuditError("Unexpected mapped contract")
    values = [integer(item[k]) for k in ("open", "high", "low", "close")]
    if any(v <= 0 or v >= 2**63 or v % TICK_SCALE for v in values):
        raise AuditError("Off-tick or invalid price")
    o, h, l, c = (v // TICK_SCALE for v in values)
    volume = integer(item["volume"])
    if not l <= min(o, c) <= max(o, c) <= h or not 0 < volume < 2**64:
        raise AuditError("Impossible OHLC or volume")
    local = datetime.fromtimestamp(stamp // 10**9, timezone.utc).astimezone(NY)
    minute = local.hour * 60 + local.minute
    return stamp, str(local.date()), inst, mapping["raw_symbol"], [minute, o, h, l, c, volume]


def audit(source_manifest, output_root):
    source_manifest = Path(source_manifest).resolve()
    manifest = json.loads(source_manifest.read_bytes())
    validate_manifest(manifest)
    partitions = manifest["partitions"]
    intervals = manifest["symbology"]["resolved_contract_intervals"]
    starts = [timestamp_ns(row["d0"]) for row in intervals]
    if starts != sorted(set(starts)):
        raise AuditError("Invalid mapping order")
    schedule = calendar_rows()
    sessions = {}
    for day, row in schedule.items():
        if not row["full_session"]:
            continue
        opening = int(datetime.fromisoformat(row["open_utc"]).timestamp()) * 10**9
        index = bisect_right(starts, opening) - 1
        if index < 0 or opening >= timestamp_ns(intervals[index]["d1"]):
            raise AuditError("Missing full-session contract mapping")
        mapping = intervals[index]
        sessions[day] = {"date": day, "symbol": mapping["raw_symbol"],
                         "instrument_id": mapping["instrument_id"], "bars": []}
    audit_rows = []
    excluded = Counter()
    for part in sorted(partitions, key=lambda p: p["year"]):
        file = source_manifest.parent / part["file"]
        if file.parent != source_manifest.parent or part["status"] != "complete" or sha256(file) != part["gzip_sha256"]:
            raise AuditError("Archive file/hash mismatch")
        digest, count, previous, full_count = hashlib.sha256(), 0, -1, 0
        lower, upper = timestamp_ns(part["query"]["start"]), timestamp_ns(part["query"]["end"])
        with gzip.open(file, "rb") as stream:
            for raw in stream:
                digest.update(raw)
                stamp, day, inst, symbol, bar = decode_bar(raw, intervals, starts, previous)
                if not lower <= stamp < upper:
                    raise AuditError("Bar outside annual request")
                previous, count = stamp, count + 1
                if day in sessions and 570 <= bar[0] < 960:
                    session = sessions[day]
                    if inst != session["instrument_id"] or symbol != session["symbol"]:
                        raise AuditError("Contract changes within cash session")
                    session["bars"].append(bar)
                    full_count += 1
                elif day in schedule and not schedule[day]["full_session"] and 570 <= bar[0] < 960:
                    excluded["bars_on_scheduled_early_close"] += 1
                elif day not in schedule and 570 <= bar[0] < 960:
                    excluded["bars_on_non_nyse_session"] += 1
                else:
                    excluded["bars_outside_cash_window"] += 1
        if count != part["expected_records"] or count != part["downloaded_records"] or digest.hexdigest() != part["raw_sha256"]:
            raise AuditError("Raw archive count/hash mismatch")
        audit_rows.append({"year": part["year"], "source_records": count, "full_session_bars": full_count})
        print(json.dumps(audit_rows[-1]), flush=True)
    folder = Path(output_root) / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True, exist_ok=False)
    calendar_file = folder / "calendar.json"
    calendar_file.write_text(json.dumps(list(schedule.values()), indent=2, sort_keys=True) + "\n")
    result = {"schema": "ba010-inputs-v1", "created_at": datetime.now(timezone.utc).isoformat(),
              "source_manifest": str(source_manifest), "source_manifest_sha256": sha256(source_manifest),
              "source_quote_usd": manifest["quote_attempted_total_usd"],
              "calendar": {"name": "XNYS", "timezone": "America/New_York", "schedule_file": "calendar.json",
                  "sha256": sha256(calendar_file), "exchange_calendars_version": version("exchange-calendars"),
                  "tzdata_version": version("tzdata")}, "years": {},
              "audit": {"reconciled": True, "source_partitions": audit_rows, "excluded_source_bars": dict(excluded),
                  "missing_minutes_are_retained": True, "all_held_positions_resolved": "not_yet_evaluated"}}
    for year in range(2021, 2026):
        rows = [sessions[d] for d in sorted(sessions) if d.startswith(str(year))]
        missing = []
        target = folder / f"sessions-{year}.jsonl.gz"
        with target.open("xb") as output, gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as zipped:
            for row in rows:
                minutes = [b[0] for b in row["bars"]]
                if minutes != sorted(set(minutes)):
                    raise AuditError("Duplicate or unsorted session minutes")
                absent = sorted(set(range(570, 960)) - set(minutes))
                if absent:
                    missing.append({"date": row["date"], "minutes": absent})
                zipped.write((json.dumps(row, separators=(",", ":")) + "\n").encode())
        result["years"][str(year)] = {"file": target.name, "sha256": sha256(target), "full_sessions": len(rows),
            "complete_sessions": len(rows) - len(missing), "missing_minutes": sum(len(m["minutes"]) for m in missing),
            "missing_by_session": missing, "early_closes": [d for d,r in schedule.items() if d.startswith(str(year)) and not r["full_session"]]}
    (folder / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for file in folder.iterdir():
        file.chmod(0o444)
    print(json.dumps({"input_manifest": str(folder / "manifest.json"), "years": {
        year: {k:v for k,v in row.items() if k not in ("missing_by_session", "early_closes")}
        for year,row in result["years"].items()}}, indent=2))
    return folder / "manifest.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/futures/ba010-inputs")
    args = parser.parse_args()
    audit(args.source_manifest, args.output_root)


if __name__ == "__main__":
    main()
