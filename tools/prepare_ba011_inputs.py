#!/usr/bin/env python3
"""Prepare only an authorized BA-011 stage from the existing MES archive.

Integrity audit only: no signal returns or trade outcomes are computed here.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
import gzip
from importlib.metadata import version
import hashlib
import json
from pathlib import Path

import exchange_calendars as xcals

try:
    from tools import audit_mes_history as audit
except ModuleNotFoundError:
    import audit_mes_history as audit

ROOT = Path(__file__).resolve().parents[1]
YEARS = {"development": (2021, 2022, 2023), "oos": (2024, 2025)}


def calendar_rows():
    cal = xcals.get_calendar("XNYS", start="2020-12-01", end="2025-12-31")
    rows = []
    for day, record in cal.schedule.iterrows():
        opening, closing = record["open"].to_pydatetime(), record["close"].to_pydatetime()
        lo, lc = opening.astimezone(audit.NY), closing.astimezone(audit.NY)
        rows.append({"date": str(day.date()), "open_utc": opening.isoformat(),
                     "close_utc": closing.isoformat(),
                     "full_session": (lo.hour, lo.minute, lc.hour, lc.minute) == (9, 30, 16, 0)})
    return rows


def _boundary(day, schedule, sessions):
    row = sessions.get(day)
    close = None
    if row is not None:
        close = next((b[4] for b in row["bars"] if b[0] == 959), None)
    return {"date": day, "full_session": schedule[day]["full_session"],
            "symbol": row["symbol"] if row else None,
            "instrument_id": row["instrument_id"] if row else None,
            "close_ticks": close}


def prepare(source_manifest, output_root, *, stage="development",
            development_report=None, development_manifest=None):
    if stage not in YEARS:
        raise audit.AuditError("Unknown BA-011 stage")
    prior = None
    if stage == "oos":
        if development_report is None or development_manifest is None:
            raise audit.AuditError("OOS preparation requires passed development report and manifest")
        try:
            from tools import ba011
        except ModuleNotFoundError:
            import ba011
        # This executes BEFORE any source price archive is opened.
        prior = ba011.validate_development(development_report, development_manifest)
    source_manifest = Path(source_manifest).resolve()
    manifest = json.loads(source_manifest.read_text())
    audit.validate_manifest(manifest)
    source_hash = audit.sha256(source_manifest)
    rows = calendar_rows()
    if not rows or [r["date"] for r in rows] != sorted({r["date"] for r in rows}):
        raise audit.AuditError("Invalid calendar ordering")
    schedule = {r["date"]: r for r in rows}
    predecessors = {r["date"]: rows[i - 1]["date"] if i else None for i, r in enumerate(rows)}
    calendar_bytes = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    calendar = {"name": "XNYS", "timezone": "America/New_York", "schedule_file": "calendar.json",
                "sha256": hashlib.sha256(calendar_bytes).hexdigest(),
                "exchange_calendars_version": version("exchange-calendars"),
                "tzdata_version": version("tzdata")}
    metadata = {"schema": "ba011-inputs-v1", "stage": stage,
                "source_manifest": str(source_manifest), "source_manifest_sha256": source_hash,
                "source_quote_usd": manifest["quote_attempted_total_usd"], "calendar": calendar}
    warmup = None
    if stage == "oos":
        # Freeze includes source archive, calendar and all executable dependencies.
        expected = ba011.freeze_record(Path(output_root) / "manifest.json", metadata)
        ba011.validate_development(development_report, development_manifest, expected_freeze=expected)
        dev = json.loads(Path(development_manifest).read_text())
        warmup = dev["boundary_reference"]
        expected_boundary = max(d for d in schedule if d.startswith("2023-"))
        if warmup["date"] != expected_boundary or warmup["full_session"] != schedule[expected_boundary]["full_session"]:
            raise audit.AuditError("Development boundary does not match the actual final 2023 session")
        metadata["development_input"] = {"file": str(Path(development_manifest).resolve()),
                                         "sha256": audit.sha256(development_manifest)}

    years = YEARS[stage]
    intervals = manifest["symbology"]["resolved_contract_intervals"]
    starts = [audit.timestamp_ns(r["d0"]) for r in intervals]
    sessions = {}
    for day, row in schedule.items():
        if int(day[:4]) not in years or not row["full_session"]:
            continue
        opening = int(datetime.fromisoformat(row["open_utc"]).timestamp()) * 10**9
        index = bisect_right(starts, opening) - 1
        if index < 0 or opening >= audit.timestamp_ns(intervals[index]["d1"]):
            raise audit.AuditError("Missing dated contract mapping")
        mapping = intervals[index]
        sessions[day] = {"date": day, "symbol": mapping["raw_symbol"],
                         "instrument_id": mapping["instrument_id"], "bars": []}

    audits = []
    excluded = Counter()
    for part in sorted(manifest["partitions"], key=lambda p: p["year"]):
        if part["year"] not in years:
            continue  # Never stat, hash, or open the other stage's price files.
        file = source_manifest.parent / part["file"]
        if file.resolve().parent != source_manifest.parent or part["status"] != "complete" or audit.sha256(file) != part["gzip_sha256"]:
            raise audit.AuditError("Archive file/hash mismatch")
        digest, count, previous, retained = hashlib.sha256(), 0, -1, 0
        lower, upper = audit.timestamp_ns(part["query"]["start"]), audit.timestamp_ns(part["query"]["end"])
        with gzip.open(file, "rb") as stream:
            for raw in stream:
                digest.update(raw)
                stamp, day, inst, symbol, bar = audit.decode_bar(raw, intervals, starts, previous)
                if not lower <= stamp < upper:
                    raise audit.AuditError("Bar outside annual source partition")
                previous, count = stamp, count + 1
                if day in sessions and 570 <= bar[0] <= 960:
                    row = sessions[day]
                    if inst != row["instrument_id"] or symbol != row["symbol"]:
                        raise audit.AuditError("Contract changes within retained session")
                    row["bars"].append(bar)
                    retained += 1
                else:
                    excluded["outside_selected_full_session_window"] += 1
        if count != part["expected_records"] or count != part["downloaded_records"] or digest.hexdigest() != part["raw_sha256"]:
            raise audit.AuditError("Raw archive count/hash mismatch")
        audits.append({"year": part["year"], "source_records": count, "retained_bars": retained})
        print(json.dumps(audits[-1]), flush=True)

    # Populate references only after source integrity checks, preserving causal
    # missing-reference abstentions instead of selecting complete future paths.
    for day, row in sessions.items():
        prev_day = predecessors[day]
        prev_full = schedule[prev_day]["full_session"] if prev_day else False
        ref = (_boundary(prev_day, schedule, sessions) if prev_day else None)
        if warmup is not None and prev_day == warmup["date"]:
            ref = warmup
        row.update({"previous_session_date": prev_day, "previous_session_full": prev_full,
                    "previous_close_ticks": ref["close_ticks"] if ref else None,
                    "previous_symbol": ref["symbol"] if ref else None,
                    "previous_instrument_id": ref["instrument_id"] if ref else None})
        minutes = [b[0] for b in row["bars"]]
        if minutes != sorted(set(minutes)):
            raise audit.AuditError("Duplicate or unordered session minutes")

    final_day = max(d for d in schedule if int(d[:4]) in years)
    metadata["boundary_reference"] = _boundary(final_day, schedule, sessions)
    metadata["audit"] = {"reconciled": True, "source_partitions": audits,
                         "excluded_source_bars": dict(excluded), "missing_minutes_are_retained": True}
    metadata["years"] = {}
    metadata["created_at"] = datetime.now(timezone.utc).isoformat()
    folder = Path(output_root) / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "calendar.json").write_bytes(calendar_bytes)
    for year in years:
        selected = [sessions[d] for d in sorted(sessions) if d.startswith(f"{year}-")]
        if not selected:
            raise audit.AuditError(f"No scheduled full sessions for {year}")
        missing = []
        target = folder / f"sessions-{year}.jsonl.gz"
        with target.open("xb") as out, gzip.GzipFile(filename="", fileobj=out, mode="wb", mtime=0) as zipped:
            for row in selected:
                absent = sorted(set(range(570, 961)) - {b[0] for b in row["bars"]})
                if absent:
                    missing.append({"date": row["date"], "minutes": absent})
                zipped.write((json.dumps(row, separators=(",", ":")) + "\n").encode())
        metadata["years"][str(year)] = {"file": target.name, "sha256": audit.sha256(target),
            "full_sessions": len(selected), "complete_sessions": len(selected) - len(missing),
            "missing_minutes": sum(len(m["minutes"]) for m in missing), "missing_by_session": missing}
    result = folder / "manifest.json"
    result.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    for file in folder.iterdir():
        file.chmod(0o444)
    print(json.dumps({"input_manifest": str(result), "stage": stage, "years": {
        year: {k: v for k, v in data.items() if k != "missing_by_session"}
        for year, data in metadata["years"].items()}}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("--stage", choices=tuple(YEARS), default="development")
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/futures/ba011-inputs")
    parser.add_argument("--development-report", type=Path)
    parser.add_argument("--development-manifest", type=Path)
    args = parser.parse_args()
    prepare(args.source_manifest, args.output_root, stage=args.stage,
            development_report=args.development_report, development_manifest=args.development_manifest)
