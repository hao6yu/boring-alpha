#!/usr/bin/env python3
"""Small offline v2 settlement adapter; frozen v1 sizing risk is unchanged.

No network and no P&L. Selection uses only settlement messages available by
the frozen session cutoff, never a hindsight final-settlement substitution.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, time, timezone
from decimal import Decimal
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_ba012_inputs as original
import ba012_sizing as sizing

SCHEMA = "ba012-stage-a-settlement-inputs-v2"
CHICAGO = ZoneInfo("America/Chicago")
UNDEFINED_TIMESTAMP = 2**64 - 1
LEGACY_END = "2017-05-21"
CAPTURE_START_NS = int(datetime(2017, 5, 21, tzinfo=timezone.utc).timestamp()) * 10**9
AMENDMENT_SHA256 = "a556ee73b7d2d54a054b88afebf3c8f9d736680b17657af71af4c3a0fae397a3"


class SettlementError(Exception):
    pass


def integer(value):
    return original.archive.strict_integer(value)


def timestamp(value):
    if value is None:
        return None
    number = integer(value)
    return number if 0 < number < UNDEFINED_TIMESTAMP else None


def cutoff_ns(day):
    value = datetime.combine(datetime.fromisoformat(day).date(), time(16, 30), CHICAGO)
    return int(value.timestamp()) * 10**9


def original_mapping_for_v2(mapping, old_design, new_design):
    """Validate original identity metadata without rewriting its v1 hashes."""
    forward, reverse = original.mapping_index(mapping, old_design)
    if not set(new_design["symbols"]) <= set(old_design["symbols"]):
        raise SettlementError("v2_symbol_outside_original_validated_mapping")
    return forward, reverse


def select_settlements(records, design, forward, reverse):
    """Choose actual nonintraday settlements, respecting updates and deletes.

    ts_ref's UTC date is the literal session date. Genuine receive time is
    mandatory from 2017-05-21 onward; earlier history is labeled event proxy.
    Sequence is comparable only within one publisher/channel identity.
    """
    required = {}
    for row in design["rolls"]["rows"]:
        day = row["date_chicago"]
        for market in row["markets"]:
            for symbol in market["required_parent_raw_symbols"]:
                instrument = original.resolve_identity(symbol, day, forward, reverse)
                if instrument is not None:
                    required[(day, instrument)] = symbol
    candidates = defaultdict(list)
    invalid = defaultdict(set)
    counts = Counter()
    for item in records:
        counts["raw_records"] += 1
        try:
            if integer(item["stat_type"]) != 3:
                continue
            if integer(item["hd"]["rtype"]) != 24:
                raise SettlementError("settlement_record_type_mismatch")
            reference = timestamp(item["ts_ref"])
            if reference is None or reference % (86400 * 10**9):
                raise SettlementError("settlement_reference_date_unavailable")
            day = datetime.fromtimestamp(reference // 10**9, timezone.utc).date().isoformat()
            instrument = integer(item["hd"]["instrument_id"])
            key = (day, instrument)
            if key not in required:
                continue
            event = timestamp(item["hd"]["ts_event"])
            if event is None:
                invalid[key].add("MISSING_EVENT_TIME")
                continue
            cutoff = cutoff_ns(day)
            if event > cutoff:
                counts["after_event_cutoff"] += 1
                continue
            action = integer(item["update_action"])
            flags = integer(item["stat_flags"])
            legacy = event < CAPTURE_START_NS
            receive = timestamp(item.get("ts_recv"))
            if not legacy and (receive is None or receive < event):
                invalid[key].add("MISSING_GENUINE_RECEIVE_TIME")
                continue
            if not legacy and receive > cutoff:
                counts["after_receive_cutoff"] += 1
                continue
            availability = event if legacy else receive
            if action == 2:
                invalid[key].add("PRE_CUTOFF_SETTLEMENT_DELETE")
                continue
            if action != 1:
                invalid[key].add("UNSUPPORTED_SETTLEMENT_ACTION")
                continue
            if not 0 <= flags <= 15:
                invalid[key].add("INVALID_SETTLEMENT_FLAGS")
                continue
            if not flags & 2 or flags & 8:
                counts["ineligible_settlement_flags"] += 1
                continue
            price = integer(item["price"])
            if not 0 < price < 2**63 - 1:
                invalid[key].add("NONPOSITIVE_OR_UNDEFINED_SETTLEMENT")
                continue
            candidate = {"price": price, "stat_flags": flags, "final_flag": bool(flags & 1),
                         "availability_ns": availability, "ts_event_ns": event,
                         "ts_recv_ns": receive, "availability_basis": "event_time_proxy" if legacy else "capture_receive_time",
                         "publisher_id": integer(item["hd"]["publisher_id"]),
                         "channel_id": integer(item["channel_id"]), "sequence": integer(item["sequence"])}
            if not (0 <= candidate["publisher_id"] < 2**16 and 0 <= candidate["channel_id"] < 2**16
                    and 0 <= candidate["sequence"] < 2**32):
                invalid[key].add("INVALID_CHANNEL_OR_SEQUENCE")
                continue
            candidates[key].append(candidate)
        except (KeyError, TypeError, ValueError, OverflowError, original.archive.ArchiveError):
            raise SettlementError("malformed_settlement_record") from None
    selected, provenance = {}, []
    for key in sorted(required):
        rows = candidates.get(key, ())
        if not invalid[key] and rows:
            latest = max((row["availability_ns"], row["ts_event_ns"]) for row in rows)
            tied = [row for row in rows if (row["availability_ns"], row["ts_event_ns"]) == latest]
            if len({(r["publisher_id"], r["channel_id"]) for r in tied}) > 1:
                invalid[key].add("AMBIGUOUS_CROSS_CHANNEL_ORDER")
            else:
                sequence = max(r["sequence"] for r in tied)
                tied = [r for r in tied if r["sequence"] == sequence]
                # The separately frozen pre-price clarification applies only
                # at the final ordering tie, never across event chronology.
                clearing = [r for r in tied if not r["stat_flags"] & 4]
                if clearing:
                    tied = clearing
                if len({(r["price"], r["stat_flags"]) for r in tied}) > 1:
                    invalid[key].add("CONFLICTING_SAME_ORDER_SETTLEMENTS")
                else:
                    chosen = tied[0]
                    day, instrument = key
                    selected.setdefault(day, {})[instrument] = chosen["price"]
                    provenance.append({"date_chicago": day, "instrument_id": instrument,
                                       "symbol": required[key], **chosen})
        if not rows:
            invalid[key].add("NO_ELIGIBLE_PRE_CUTOFF_SETTLEMENT")
    issues = [{"date_chicago": day, "instrument_id": instrument, "symbol": required[(day, instrument)],
               "reasons": sorted(reasons)} for (day, instrument), reasons in sorted(invalid.items()) if reasons]
    return selected, {"counts": dict(counts), "selected_references": provenance, "reference_issues": issues}


def build_monthly_cases(design, selected, forward, reverse):
    """Same 252 scheduled within-contract interval arithmetic as v1."""
    rows = design["rolls"]["rows"]
    prices, missing = {}, {}
    for row in rows:
        day, values, absent = row["date_chicago"], {}, []
        for market in row["markets"]:
            for symbol in market["required_parent_raw_symbols"]:
                instrument = original.resolve_identity(symbol, day, forward, reverse)
                value = selected.get(day, {}).get(instrument)
                if value is None or value <= 0:
                    absent.append(symbol)
                else:
                    values[symbol] = value
        prices[day], missing[day] = values, sorted(set(absent))
    intervals = []
    for index, row in enumerate(rows[1:], 1):
        day, previous = row["date_chicago"], rows[index - 1]["date_chicago"]
        record = {"date_chicago": day, "previous_joint_date_chicago": previous, "status": "DATA_INCOMPLETE"}
        if not missing[day] and not missing[previous]:
            changes, ratios, contracts = [], [], []
            for column, market in enumerate(row["markets"]):
                symbol = market["interval_parent_raw_symbol"]
                before, after = prices[previous][symbol], prices[day][symbol]
                changes.append(str(Decimal(after - before) * original.SENSITIVITIES[column] / Decimal(10**9)))
                ratios.append(Fraction(after, before))
                contracts.append(symbol)
            record.update(status="READY", dollar_movements=changes, ratios=ratios, contracts=contracts)
        intervals.append(record)
    cases = []
    for index, row in enumerate(rows):
        day = row["date_chicago"]
        if day < "2018-01-01" or (index + 1 < len(rows) and rows[index + 1]["date_chicago"][:7] == day[:7]):
            continue
        window = intervals[index - 252:index] if index >= 252 else []
        case = {"decision_date_chicago": day, "status": "DATA_INCOMPLETE", "required_intervals": 252,
                "valid_intervals": sum(r["status"] == "READY" for r in window)}
        if len(window) == 252 and all(r["status"] == "READY" for r in window):
            signs = []
            for column in range(5):
                product = Fraction(1)
                for record in window:
                    product *= record["ratios"][column]
                signs.append((product > 1) - (product < 1))
            case.update(status="READY", window_first_endpoint=window[0]["previous_joint_date_chicago"],
                        interval_dates=[r["date_chicago"] for r in window], signs=signs,
                        dollar_movements=[r["dollar_movements"] for r in window])
        else:
            case["missing_interval_dates"] = [r["date_chicago"] for r in window if r["status"] != "READY"]
        cases.append(case)
    return cases, [{"date_chicago": day, "missing_symbols": values} for day, values in missing.items() if values], [
        {k: v for k, v in row.items() if k not in ("ratios", "dollar_movements")} for row in intervals]


def size_pilot_cases(cases):
    """Only READY 5k cases; no P&L and no conversion of missing data to cash."""
    results = []
    for case in cases:
        if case["status"] != "READY":
            result = {"status": "DATA_INCOMPLETE", "decision": "UNRESOLVED", "quantities": None, "optimum_verified": False}
        else:
            try:
                result = sizing.size_stage_a(case["dollar_movements"], case["signs"], 5000)
            except ValueError:
                result = {"status": "INVALID_RISK_INPUT", "decision": "UNRESOLVED", "quantities": None, "optimum_verified": False}
        results.append({"decision_date_chicago": case["decision_date_chicago"], "sizing": result})
    verified = [r["sizing"] for r in results if r["sizing"]["optimum_verified"]]
    nonzero = sum(r["decision"] == "NONZERO" for r in verified)
    cash = sum(r["decision"] == "CASH" for r in verified)
    verdict = ("ALL_CASH_REJECT_CAPITAL_SPECIFICATION" if len(cases) == len(verified) == cash == 72 else
               "COMPLETE_SIZING_PARTICIPATION_EVIDENCE" if len(cases) == len(verified) == 72 else
               "INCOMPLETE_STUDY_WITH_PARTICIPATION_EVIDENCE" if nonzero else "INCOMPLETE_STUDY_NO_CAPITAL_VERDICT")
    return {"equity_usd": 5000, "verdict": verdict, "verified_cases": len(verified), "nonzero_cases": nonzero,
            "cash_cases": cash, "unresolved_cases": len(cases) - len(verified), "per_date": results,
            "strategy_pnl_calculated": False}


def verified_design(amendment_path, rolls_path):
    raw = Path(amendment_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != AMENDMENT_SHA256:
        raise SettlementError("amendment_checksum_mismatch")
    amendment = original.archive.load_json(raw)
    old = original.load_design()
    new = original.load_design(rolls_path)
    if (amendment["base_protocol"]["sha256"] != sizing.PROTOCOL_SHA256
            or amendment["base_rolls"]["sha256"] != old["rolls_sha256"]
            or amendment["calendar"]["sha256"] != new["calendar_sha256"]
            or new["rolls"]["amendment_sha256"] != AMENDMENT_SHA256
            or new["rolls"]["base_rolls_sha256"] != old["rolls_sha256"]):
        raise SettlementError("amended_design_provenance_mismatch")
    return old, new


def manifest_records(manifest_paths, provenance):
    """Read complete hashed raw statistics partitions; no requests or retries."""
    from run_ba012_stage_a import sha256_file
    seen_files = set()
    for manifest_path in manifest_paths:
        path = Path(manifest_path)
        raw = path.read_bytes()
        manifest = original.archive.load_json(raw)
        provenance.append({"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest()})
        for partition in manifest["partitions"]:
            if partition["status"] != "complete":
                continue
            query = partition["query"]
            if query["schema"] != "statistics" or query["dataset"] != "GLBX.MDP3":
                raise SettlementError("wrong_statistics_dataset_or_schema")
            name = partition["file"]
            if Path(name).name != name:
                raise SettlementError("unsafe_archive_filename")
            target = (path.parent / name).resolve()
            if target in seen_files:
                raise SettlementError("duplicate_statistics_archive")
            seen_files.add(target)
            if sha256_file(target) != partition["gzip_sha256"]:
                raise SettlementError("statistics_gzip_checksum_mismatch")
            digest, count = hashlib.sha256(), 0
            with gzip.open(target, "rb") as stream:
                while line := stream.readline(original.archive.MAX_LINE_BYTES + 1):
                    if len(line) > original.archive.MAX_LINE_BYTES:
                        raise SettlementError("statistics_record_too_large")
                    digest.update(line)
                    count += 1
                    yield original.archive.load_json(line)
            if count != partition["records"] or digest.hexdigest() != partition["raw_sha256"]:
                raise SettlementError("statistics_raw_checksum_or_count_mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amendment", type=Path, default=original.STAGE / "settlement-amendment-v2.json")
    parser.add_argument("--rolls", type=Path, default=original.STAGE / "rolls-v2.json")
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size-pilot", action="store_true")
    args = parser.parse_args()
    try:
        old, new = verified_design(args.amendment, args.rolls)
        mapping_raw = args.mapping.read_bytes()
        forward, reverse = original_mapping_for_v2(original.archive.load_json(mapping_raw), old, new)
        manifests = []
        selected, audit = select_settlements(manifest_records(args.manifest, manifests), new, forward, reverse)
        cases, missing, interval_provenance = build_monthly_cases(new, selected, forward, reverse)
        report = {"schema": SCHEMA, "amendment_sha256": AMENDMENT_SHA256,
                  "base_protocol_sha256": sizing.PROTOCOL_SHA256,
                  "base_rolls_sha256": old["rolls_sha256"], "rolls_v2_sha256": new["rolls_sha256"],
                  "calendar_sha256": new["calendar_sha256"],
                  "mapping_sha256": hashlib.sha256(mapping_raw).hexdigest(), "mapping_source_design": "validated_original_v1_symbol_subset",
                  "archive_manifests": manifests, "market_order": list(original.MARKETS),
                  "status": "READY" if len(cases) == 72 and all(c["status"] == "READY" for c in cases) else "DATA_INCOMPLETE",
                  "monthly_cases": cases, "selection_audit": audit, "missing_references": missing,
                  "interval_provenance": interval_provenance, "strategy_pnl_calculated": False,
                  "study_label": "Amended v2 causal settlements; hypothetical child exposures on parent history; development feasibility, not a holdout or historical child execution"}
        if args.size_pilot:
            report["pilot_sizing"] = size_pilot_cases(cases)
        from run_ba012_stage_a import runtime_provenance, sha256_file
        report["runtime"] = runtime_provenance()
        report["runtime"]["adapter"] = {"path": str(Path(__file__).resolve()), "sha256": sha256_file(__file__)}
        with args.output.open("x") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        print(json.dumps({"status": report["status"], "ready_monthly_cases": sum(c["status"] == "READY" for c in cases),
                          "output": str(args.output), "sha256": sha256_file(args.output),
                          "pilot_verdict": report.get("pilot_sizing", {}).get("verdict")}))
        return 0 if report["status"] == "READY" else 2
    except SettlementError as exc:
        print(json.dumps({"status": "DATA_INCOMPLETE", "failure": str(exc), "capital_verdict": "UNRESOLVED"}), file=sys.stderr)
        return 2
    except (original.InputError, original.archive.ArchiveError, OSError, KeyError, ValueError):
        print(json.dumps({"status": "DATA_INCOMPLETE", "failure": "Settlement adapter validation failed; no capital verdict"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
