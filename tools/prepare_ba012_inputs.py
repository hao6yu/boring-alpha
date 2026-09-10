#!/usr/bin/env python3
"""Build BA-012 Stage A inputs offline from frozen identities and reference bars.

No network, strategy P&L, sizing optimization or filling of missing bars. Price
archives are opened only after calendar and roll-map checksums are verified.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_ba012_references as archive

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "research/ba012-stage-a"
MARKETS = ("NES", "MTN", "M6E", "1OZ", "MZC")
PARENTS = ("ES", "TN", "6E", "GC", "ZC")
# Databento normalized prices: index points, decimal bond points, USD/EUR,
# USD/ounce, cents/bushel. Do not reinterpret Treasury points as display fractions.
SENSITIVITIES = tuple(map(Decimal, ("0.5", "100", "12500", "1", "5")))
START, END = "2016-01-11", "2024-01-01"
SCHEMA = "ba012-stage-a-inputs-v1"


class InputError(Exception):
    """Fixed non-sensitive diagnostic code, never an arbitrary provider body."""


def frozen_json(path):
    try:
        path = Path(path)
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        pinned = path.with_suffix(path.suffix + ".sha256").read_text().split()[0]
        if not re.fullmatch(r"[0-9a-f]{64}", pinned) or pinned != digest:
            raise ValueError
        return archive.load_json(raw), digest
    except (OSError, ValueError, IndexError, TypeError):
        raise InputError("missing_or_changed_frozen_artifact") from None


def load_design(rolls_path=STAGE / "rolls-v1.json", calendar_path=STAGE / "calendar-v1.json"):
    """Validate design and causal roll continuity before any price file access."""
    archive.checked_protocol()
    calendar, calendar_sha = frozen_json(calendar_path)
    rolls, rolls_sha = frozen_json(rolls_path)
    try:
        sessions = calendar["joint_sessions"]
        if (calendar["strategy_id"] != "BA-012" or calendar["stage"] != "A"
                or calendar["range_start_inclusive"] != START or calendar["range_end_exclusive"] != END
                or sessions != sorted(set(sessions)) or not sessions or sessions[0] != START
                or rolls["calendar_sha256"] != calendar_sha):
            raise ValueError
        rows = rolls["rows"]
        if [row["date_chicago"] for row in rows] != sessions:
            raise ValueError
        all_symbols = set()
        for index, row in enumerate(rows):
            day = row["date_chicago"]
            if date.fromisoformat(day).isoformat() != day or not START <= day < END:
                raise ValueError
            previous = None if index == 0 else sessions[index - 1]
            if row["previous_joint_date_chicago"] != previous or len(row["markets"]) != 5:
                raise ValueError
            for column, market in enumerate(row["markets"]):
                if market["child_root"] != MARKETS[column] or market["parent_root"] != PARENTS[column]:
                    raise ValueError
                active, interval = market["active_parent_raw_symbol"], market["interval_parent_raw_symbol"]
                expected_interval = None if index == 0 else rows[index - 1]["markets"][column]["active_parent_raw_symbol"]
                if interval != expected_interval:
                    raise ValueError
                required = sorted({active, *(() if interval is None else (interval,))})
                if sorted(market["required_parent_raw_symbols"]) != required:
                    raise ValueError
                if market["is_roll"] is not (interval is not None and active != interval):
                    raise ValueError
                for symbol in required:
                    if not re.fullmatch(re.escape(PARENTS[column]) + r"[FGHJKMNQUVXZ][0-9]{1,2}", symbol):
                        raise ValueError
                all_symbols.update(required)
        return {"calendar": calendar, "rolls": rolls, "calendar_sha256": calendar_sha,
                "rolls_sha256": rolls_sha, "symbols": tuple(sorted(all_symbols))}
    except (ValueError, TypeError, KeyError):
        raise InputError("invalid_frozen_calendar_or_rolls") from None


def mapping_index(report, design):
    """Keep forward and reverse dated intervals; never assume an ID is permanent."""
    try:
        if (report["schema"] != "ba012-dated-symbology-v1" or report["status"] != "complete"
                or report["rolls_sha256"] != design["rolls_sha256"]
                or report["calendar_sha256"] != design["calendar_sha256"]
                or report["protocol_sha256"] != archive.PROTOCOL_SHA256
                or report["data_downloads"] != 0):
            raise ValueError
        forward, reverse = {}, {}
        for direction, output in (("forward", forward), ("reverse", reverse)):
            for partition in report[direction]:
                query = partition["query"]
                if query["dataset"] != "GLBX.MDP3" or query["start_date"] != START or query["end_date"] != END:
                    raise ValueError
                expected_types = ("raw_symbol", "instrument_id") if direction == "forward" else ("instrument_id", "raw_symbol")
                if (query["stype_in"], query["stype_out"]) != expected_types:
                    raise ValueError
                for symbol, intervals in partition["mapping"]["result"].items():
                    if symbol in output or symbol not in query["symbols"].split(","):
                        raise ValueError
                    previous_end = START
                    for interval in intervals:
                        if not START <= interval["d0"] < interval["d1"] <= END or interval["d0"] < previous_end:
                            raise ValueError
                        previous_end = interval["d1"]
                    output[symbol] = intervals
        if set(forward) != set(design["symbols"]):
            raise ValueError
        return forward, reverse
    except (ValueError, TypeError, KeyError):
        raise InputError("invalid_or_incomplete_dated_symbology") from None


def resolve_identity(symbol, day, forward, reverse):
    ids = [row["s"] for row in forward.get(symbol, ()) if row["d0"] <= day < row["d1"]]
    if len(ids) != 1:
        return None
    instrument = ids[0]
    names = [row["s"] for row in reverse.get(str(instrument), ()) if row["d0"] <= day < row["d1"]]
    if names != [symbol]:
        return None
    try:
        number = archive.strict_integer(instrument)
        return number if 0 < number < 2**32 else None
    except archive.ArchiveError:
        return None


def read_archives(output_root, design):
    """Only completed, ledger-reconciled archives may supply reference values."""
    output_root = Path(output_root)
    if (output_root / ".download.lock").exists():
        raise InputError("reference_acquisition_still_active")
    try:
        archive.prior_state(output_root)
        by_date, manifests = {}, []
        if not output_root.exists():
            return by_date, manifests
        sessions = set(design["calendar"]["joint_sessions"])
        for folder in sorted(output_root.iterdir()):
            raw_manifest = (folder / "manifest.json").read_bytes()
            report = archive.load_json(raw_manifest)
            manifests.append({"path": str(folder / "manifest.json"), "sha256": hashlib.sha256(raw_manifest).hexdigest()})
            for partition in report["partitions"]:
                if partition["status"] != "complete":
                    continue
                query = partition["query"]
                day = query["start"][:10]
                if day not in sessions:
                    continue
                if day in by_date:
                    raise ValueError
                seen, records, digest = set(), {}, hashlib.sha256()
                with gzip.open(folder / partition["file"], "rb") as stream:
                    while line := stream.readline(archive.MAX_LINE_BYTES + 1):
                        if len(line) > archive.MAX_LINE_BYTES or len(records) >= archive.MAX_RECORDS:
                            raise ValueError
                        archive.validate_bar(line, query, seen)
                        item = archive.load_json(line)
                        instrument = archive.strict_integer(item["hd"]["instrument_id"])
                        records[instrument] = archive.price_integer(item["close"])
                        digest.update(line)
                if len(records) != partition["records"] or digest.hexdigest() != partition["raw_sha256"]:
                    raise ValueError
                by_date[day] = records
        return by_date, manifests
    except (OSError, ValueError, KeyError, TypeError, archive.ArchiveError):
        raise InputError("unverifiable_reference_archives") from None


def build_cases(design, mapping, bars):
    """No gap compression and no cross-contract price subtraction at a roll."""
    forward, reverse = mapping_index(mapping, design)
    rows = design["rolls"]["rows"]
    prices, identities, issues = {}, {}, {}
    for row in rows:
        day = row["date_chicago"]
        daily, ids, missing = {}, {}, []
        for market in row["markets"]:
            for symbol in market["required_parent_raw_symbols"]:
                instrument = resolve_identity(symbol, day, forward, reverse)
                reason = None
                if instrument is None:
                    reason = "MISSING_OR_AMBIGUOUS_DATED_IDENTITY"
                elif day not in bars:
                    reason = "MISSING_REFERENCE_ARCHIVE"
                elif instrument not in bars[day]:
                    reason = "MISSING_EXACT_OUTRIGHT_REFERENCE_BAR"
                elif bars[day][instrument] <= 0:
                    reason = "NONPOSITIVE_SELECTED_OUTRIGHT_PRICE"
                if reason:
                    missing.append({"market": market["child_root"], "symbol": symbol, "reason": reason})
                else:
                    daily[symbol] = bars[day][instrument]
                    ids[symbol] = instrument
        prices[day], identities[day], issues[day] = daily, ids, missing
    intervals = []
    for index, row in enumerate(rows[1:], 1):
        day, previous = row["date_chicago"], rows[index - 1]["date_chicago"]
        record = {"date_chicago": day, "previous_joint_date_chicago": previous, "status": "DATA_INCOMPLETE"}
        if not issues[day] and not issues[previous]:
            dollars, ratios, contracts = [], [], []
            for column, market in enumerate(row["markets"]):
                symbol = market["interval_parent_raw_symbol"]
                before, after = prices[previous][symbol], prices[day][symbol]
                dollars.append(str(Decimal(after - before) * SENSITIVITIES[column] / Decimal(10**9)))
                ratios.append(Fraction(after, before))
                contracts.append({"symbol": symbol, "previous_instrument_id": identities[previous][symbol],
                                  "current_instrument_id": identities[day][symbol]})
            record.update(status="READY", dollar_movements=dollars, ratios=ratios, contracts=contracts)
        intervals.append(record)
    monthly_indices = [index for index, row in enumerate(rows) if row["date_chicago"] >= "2018-01-01"
                       and (index == len(rows) - 1 or rows[index + 1]["date_chicago"][:7] != row["date_chicago"][:7])]
    cases = []
    for index in monthly_indices:
        decision = rows[index]["date_chicago"]
        window = intervals[index - 252:index] if index >= 252 else []
        case = {"decision_date_chicago": decision, "status": "DATA_INCOMPLETE", "required_intervals": 252,
                "valid_intervals": sum(row["status"] == "READY" for row in window)}
        if len(window) == 252 and all(row["status"] == "READY" for row in window):
            signs = []
            for column in range(5):
                product = Fraction(1)
                for record in window:
                    product *= record["ratios"][column]
                signs.append((product > 1) - (product < 1))
            case.update(status="READY", interval_dates=[r["date_chicago"] for r in window],
                window_first_endpoint=window[0]["previous_joint_date_chicago"], signs=signs,
                dollar_movements=[r["dollar_movements"] for r in window])
        else:
            case["missing_interval_dates"] = [r["date_chicago"] for r in window if r["status"] != "READY"]
        cases.append(case)
    return {"schema": SCHEMA, "status": "READY" if len(cases) == 72 and all(c["status"] == "READY" for c in cases) else "DATA_INCOMPLETE",
        "market_order": list(MARKETS), "protocol_sha256": archive.PROTOCOL_SHA256,
        "calendar_sha256": design["calendar_sha256"], "rolls_sha256": design["rolls_sha256"],
        "study_label": "Hypothetical child exposure applied to parent history; not historical child execution",
        "price_conventions": {"raw_fixed_point_scale": "1e-9", "parent_units": ["index_points", "decimal_bond_points", "USD_per_EUR", "USD_per_ounce", "cents_per_bushel"],
            "child_dollar_sensitivities": list(map(str, SENSITIVITIES)),
            "source": "https://databento.com/docs/examples/instrument-definitions/contract-notional"},
        "sign_method": "Exact rational product of 252 same-contract price ratios, compared with one; zero is flat",
        "strategy_pnl_calculated": False, "sizing_calculated": False,
        "monthly_cases": cases, "reference_issues": [{"date_chicago": day, "issues": value} for day, value in issues.items() if value],
        "interval_provenance": [{key: value for key, value in row.items() if key not in ("ratios", "dollar_movements")} for row in intervals],
        "limitations": ["DATA_INCOMPLETE is not a capital-failure verdict.", "No missing date, bar or roll endpoint is filled or compressed.",
            "Positive-volume bar closes are bounded-asynchronous trades, not simultaneous midpoints.",
            "Calendar, contract and broker-deadline limitations in the frozen roll map remain applicable."]}


def main():
    parser = archive.SafeParser(description=__doc__)
    parser.add_argument("--rolls", type=Path, default=STAGE / "rolls-v1.json")
    parser.add_argument("--calendar", type=Path, default=STAGE / "calendar-v1.json")
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, default=archive.OUTPUT_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        design = load_design(args.rolls, args.calendar)
        mapping_raw = args.mapping.read_bytes()
        mapping = archive.load_json(mapping_raw)
        mapping_index(mapping, design)  # Also gate archive access on identities.
        bars, manifests = read_archives(args.archive_root, design)
        report = build_cases(design, mapping, bars)
        report["mapping_sha256"] = hashlib.sha256(mapping_raw).hexdigest()
        report["archive_manifests"] = manifests
        with args.output.open("x") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print(json.dumps({"status": report["status"], "monthly_cases": len(report["monthly_cases"]),
            "ready_cases": sum(case["status"] == "READY" for case in report["monthly_cases"]), "output": str(args.output)}))
        return 0 if report["status"] == "READY" else 2
    except (InputError, archive.ArchiveError) as exc:
        print(json.dumps({"status": "DATA_INCOMPLETE", "failure": str(exc)}), file=sys.stderr)
        return 2
    except Exception:
        print(json.dumps({"status": "DATA_INCOMPLETE", "failure": "input_preparation_failed"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
