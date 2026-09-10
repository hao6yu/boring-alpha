#!/usr/bin/env python3
"""Prepare pinned BA-012 covered-window inputs offline; never calculate P&L.

The morning risk matrix ends on the previous joint session. Same-day
settlements and month-end signs are available only after 16:30 Chicago.
Missing marks are explicit nulls, never fabricated prices or flat positions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, time, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import gzip
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_ba012_inputs as reference
import prepare_ba012_settlements as settlement
import ba012_sizing as sizing
import fetch_ba012_execution as execution

ROOT = reference.ROOT
STAGE = reference.STAGE
OUT = ROOT / "research/ba012-profitability/traded-inputs-v1.json"
SOURCE = STAGE / "settlement-inputs-v2-continuation.json"
SOURCE_SHA = "2b309c135d3b8982450a186e4e05f0d400bd02ec71f8ba6c98044cb77c3986cf"
MAPPING = STAGE / "symbology/20260910T130820097627Z/mapping.json"
MAPPING_SHA = "f933f9ca008c4f75ea5abd76224dc9a20a9bc48247f07f769c44be08bce7b117"
SIZING_SHA = "5b51ffe91ed845be846801c0d695897801a1c0430c910852310ac9ca4c397726"
EXECUTION_PLAN = ROOT / "research/ba012-profitability/execution-query-plan-v1.json"
EXECUTION_PLAN_SHA = "962e8489034bfa10bee94066e14f15110d5995cdbdf4cb88e509f7f5202b21d0"
SEED, START, END = "2022-06-30", "2022-07-01", "2024-01-01"
CHICAGO = ZoneInfo("America/Chicago")
MINUTES = tuple(f"10:{minute:02d}" for minute in range(6))


class BundleError(Exception):
    pass


def check(condition, message):
    if not condition:
        raise BundleError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned(path, expected):
    raw = Path(path).read_bytes()
    check(hashlib.sha256(raw).hexdigest() == expected, "pinned_input_checksum_mismatch")
    return reference.archive.load_json(raw)


def price_string(raw):
    return str(Decimal(raw) / Decimal(10**9))


def previous_month(month):
    year, number = map(int, month.split("-"))
    return f"{year - (number == 1):04d}-{(number - 2) % 12 + 1:02d}"


def ns_at(day, hour, minute):
    value = datetime.combine(datetime.fromisoformat(day).date(), time(hour, minute), CHICAGO)
    return int(value.timestamp()) * 10**9


def build_base(reference_root=reference.archive.OUTPUT_ROOT):
    source = pinned(SOURCE, SOURCE_SHA)
    check(source["schema"] == settlement.SCHEMA, "wrong_settlement_input_schema")
    check(digest(ROOT / "tools/ba012_sizing.py") == SIZING_SHA, "sizing_helper_changed")
    old = reference.load_design()
    new = reference.load_design(STAGE / "rolls-v2.json")
    amendment, amendment_sha = reference.frozen_json(STAGE / "settlement-amendment-v2.json")
    check(amendment_sha == settlement.AMENDMENT_SHA256 == source["amendment_sha256"], "amendment_mismatch")
    check(source["rolls_v2_sha256"] == new["rolls_sha256"] and source["base_rolls_sha256"] == old["rolls_sha256"], "rolls_mismatch")
    check(source["calendar_sha256"] == new["calendar_sha256"] and source["base_protocol_sha256"] == sizing.PROTOCOL_SHA256, "design_mismatch")
    check(source["market_order"] == list(reference.MARKETS), "market_order_mismatch")
    mapping = pinned(MAPPING, MAPPING_SHA)
    check(source["mapping_sha256"] == MAPPING_SHA, "mapping_checksum_mismatch")
    forward, reverse = settlement.original_mapping_for_v2(mapping, old, new)
    for item in source["archive_manifests"]:
        check(digest(item["path"]) == item["sha256"], "settlement_archive_manifest_changed")

    calendar = new["calendar"]["joint_sessions"]
    indices = {day: index for index, day in enumerate(calendar)}
    rows = new["rolls"]["rows"]
    needed_days = [day for day in calendar if SEED <= day < END]
    check(needed_days[0] == SEED and len(needed_days) == 378, "covered_calendar_mismatch")
    earliest = indices[SEED] - 252
    history = set(calendar[earliest:indices[needed_days[-1]] + 1])
    selected, selected_meta = {}, {}
    for item in source["selection_audit"]["selected_references"]:
        day, symbol = item["date_chicago"], item["symbol"]
        if day not in history:
            continue
        key = (day, symbol)
        check(key not in selected, "duplicate_selected_settlement")
        identity = reference.resolve_identity(symbol, day, forward, reverse)
        check(identity == item["instrument_id"], "settlement_identity_mismatch")
        value = reference.archive.strict_integer(item["price"])
        flags = reference.archive.strict_integer(item["stat_flags"])
        check(0 < value < 2**63 - 1 and 0 <= flags <= 15 and flags & 2 and not flags & 8, "invalid_selected_settlement")
        check(item["availability_basis"] == "capture_receive_time" and 0 < item["ts_event_ns"] <= item["ts_recv_ns"] == item["availability_ns"] <= settlement.cutoff_ns(day), "noncausal_selected_settlement")
        selected[key], selected_meta[key] = value, item

    supplied_intervals = {r["date_chicago"]: r for r in source["interval_provenance"]}
    intervals = {}
    for index in range(earliest + 1, indices[needed_days[-1]] + 1):
        row, prev = rows[index], rows[index - 1]
        day, before_day = row["date_chicago"], prev["date_chicago"]
        values, ratios, contracts, missing = [], [], [], []
        # Preserve the original full reference-date requirement, including
        # both old and active contracts at a roll, before constructing ratios.
        for endpoint in (prev, row):
            for market in endpoint["markets"]:
                for symbol in market["required_parent_raw_symbols"]:
                    if (endpoint["date_chicago"], symbol) not in selected:
                        missing.append((endpoint["date_chicago"], symbol))
        if not missing:
            for column, market in enumerate(row["markets"]):
                symbol = market["interval_parent_raw_symbol"]
                before, after = selected[(before_day, symbol)], selected[(day, symbol)]
                values.append(str(Decimal(after - before) * reference.SENSITIVITIES[column] / Decimal(10**9)))
                ratios.append(Fraction(after, before))
                contracts.append(symbol)
        status = "DATA_INCOMPLETE" if missing else "READY"
        check(supplied_intervals[day]["status"] == status, "reconstructed_interval_status_mismatch")
        if not missing:
            check(supplied_intervals[day]["contracts"] == contracts, "interval_contract_mismatch")
        intervals[day] = {"status": status, "dollar_movements": values, "ratios": ratios,
                          "previous_joint_date_chicago": before_day, "missing": missing}

    monthly = {r["decision_date_chicago"]: r for r in source["monthly_cases"]}
    month_ends = {day[:7]: day for day in calendar}
    risks = {}
    for day in needed_days:
        index = indices[day]
        window_days = calendar[index - 251:index + 1]
        window = [intervals[d] for d in window_days]
        check(len(window) == 252 and all(r["status"] == "READY" for r in window), "incomplete_covered_risk_window")
        movements = [r["dollar_movements"] for r in window]
        covariance = sizing.estimate_covariance(movements).tolist()
        signs = []
        for column in range(5):
            total = Fraction(1)
            for r in window:
                total *= r["ratios"][column]
            signs.append((total > 1) - (total < 1))
        if day in monthly:
            case = monthly[day]
            check(case["status"] == "READY" and case["signs"] == signs and case["interval_dates"] == window_days, "monthly_signal_mismatch")
            check(all(Decimal(a) == Decimal(b) for x, y in zip(movements, case["dollar_movements"]) for a, b in zip(x, y)), "monthly_movement_mismatch")
        risks[day] = {"annual_covariance": covariance, "signs": signs,
                      "window_first_endpoint": calendar[index - 252], "window_last_endpoint": day,
                      "available_after_utc_ns": settlement.cutoff_ns(day)}

    # A validated calendar subset limits decompression to seed/account dates.
    subset = dict(new, calendar=dict(new["calendar"], joint_sessions=needed_days))
    bars, manifests = reference.read_archives(reference_root, subset)
    missing_inputs, output_rows = [], []
    for day in needed_days:
        index, original_row = indices[day], rows[indices[day]]
        is_seed = day == SEED
        previous = calendar[index - 1]
        symbols = sorted({symbol for m in original_row["markets"] for symbol in m["required_parent_raw_symbols"]})
        prices, reference_prices, identities, provenance, absent = {}, {}, {}, {}, []
        for symbol in symbols:
            identity = reference.resolve_identity(symbol, day, forward, reverse)
            check(identity is not None, "required_dated_identity_missing")
            identities[symbol] = identity
            raw = selected.get((day, symbol))
            prices[symbol] = None if raw is None else price_string(raw)
            provenance[symbol] = selected_meta.get((day, symbol))
            mark = bars.get(day, {}).get(identity)
            reference_prices[symbol] = None if mark is None else price_string(mark)
            if mark is None:
                absent.append({"date_chicago": day, "symbol": symbol, "field": "reference_1000", "reason": "MISSING_EXACT_0959_BAR"})
            if raw is None:
                absent.append({"date_chicago": day, "symbol": symbol, "field": "settlement_1630", "reason": "MISSING_SELECTED_SETTLEMENT"})
        signal_day = SEED if is_seed else month_ends[previous_month(day[:7])]
        check(signal_day <= day and (is_seed or signal_day < day), "noncausal_monthly_signal")
        check(monthly[signal_day]["status"] == "READY", "missing_monthly_signal")
        first = not is_seed and previous[:7] != day[:7]
        last = month_ends[day[:7]] == day
        item = {"date_chicago": day, "previous_joint_date_chicago": previous,
                "first_joint_of_month": first, "last_joint_of_month": last,
                "monthly_signal_date": signal_day, "signs": monthly[signal_day]["signs"],
                "monthly_after_1630_signs": risks[day]["signs"] if last else None,
                "sigma_before_1000": None if is_seed else risks[previous]["annual_covariance"],
                "sigma_before_1000_asof": None if is_seed else previous,
                "sigma_after_1630": risks[day]["annual_covariance"],
                "risk_window_first_endpoint": risks[day]["window_first_endpoint"],
                "settlement_cutoff_utc_ns": settlement.cutoff_ns(day),
                "reference_bar_start_utc_ns": ns_at(day, 9, 59),
                "markets": original_row["markets"], "instrument_ids": identities,
                "settlement_1630": prices, "settlement_provenance": provenance,
                "reference_1000": reference_prices, "execution_bars": {}, "missing_inputs": absent}
        missing_inputs.extend(absent)
        output_rows.append(item)
    return {"schema": "ba012-traded-inputs-v1", "status": "EXECUTION_PANEL_PENDING",
            "source": {"path": str(SOURCE), "sha256": SOURCE_SHA, "schema": source["schema"]},
            "base_protocol_sha256": sizing.PROTOCOL_SHA256, "amendment_sha256": amendment_sha,
            "calendar_sha256": new["calendar_sha256"], "rolls_v2_sha256": new["rolls_sha256"],
            "mapping_sha256": MAPPING_SHA, "sizing_helper_sha256": SIZING_SHA,
            "settlement_archive_manifests": source["archive_manifests"], "reference_archive_manifests": manifests,
            "market_order": list(reference.MARKETS), "child_dollar_sensitivities": list(map(str, reference.SENSITIVITIES)),
            "price_format": "exact normalized decimal strings; no fill price has been selected",
            "start_inclusive": START, "end_exclusive": END, "seed": output_rows[0], "days": output_rows[1:],
            "missing_inputs": missing_inputs, "strategy_pnl_calculated": False,
            "limitations": ["Parent exposure inputs; historical child execution is not established.",
                            "Settlement marks are product-specific and asynchronous.",
                            "Missing marks remain null; account holdings determine whether they block a performance conclusion."]}


def decode_execution_file(path, partition, identities):
    """Verify one complete archive, preserving missing exact minute bars."""
    query = partition["query"]
    start, end = reference.archive.stamp_ns(query["start"]), reference.archive.stamp_ns(query["end"])
    check(end - start == 6 * 60 * 10**9, "execution_window_length_mismatch")
    ids = {number: symbol for symbol, number in identities.items()}
    check(len(ids) == len(identities), "ambiguous_execution_identity")
    bars = {symbol: {minute: None for minute in MINUTES} for symbol in identities}
    count, raw_bytes, checksum, seen, invalid = 0, 0, hashlib.sha256(), {}, []
    with gzip.open(path, "rb") as stream:
        while line := stream.readline(execution.MAX_LINE + 1):
            check(len(line) <= execution.MAX_LINE and count < 60_000, "execution_record_bound_exceeded")
            item = reference.archive.load_json(line)
            stamp = reference.archive.strict_integer(item["hd"]["ts_event"])
            check(start <= stamp < end and stamp % (60 * 10**9) == 0, "execution_bar_outside_exact_window")
            minute_start = datetime.fromtimestamp(stamp // 10**9, CHICAGO)
            one_minute = query | {"start": minute_start.isoformat(),
                                  "end": datetime.fromtimestamp(stamp // 10**9 + 60, CHICAGO).isoformat()}
            reference.archive.validate_bar(line, one_minute, seen.setdefault(stamp, set()))
            raw_bytes += len(line)
            checksum.update(line)
            count += 1
            instrument = reference.archive.strict_integer(item["hd"]["instrument_id"])
            if instrument not in ids:
                continue
            symbol, minute = ids[instrument], minute_start.strftime("%H:%M")
            check(minute in MINUTES, "execution_local_minute_mismatch")
            prices = {field: reference.archive.price_integer(item[field]) for field in ("open", "high", "low", "close")}
            volume = reference.archive.strict_integer(item["volume"])
            if any(value <= 0 for value in prices.values()) or volume <= 0:
                invalid.append({"symbol": symbol, "minute": minute, "reason": "NONPOSITIVE_EXACT_OUTRIGHT_BAR"})
                continue
            check(bars[symbol][minute] is None, "duplicate_selected_execution_bar")
            bars[symbol][minute] = {**{field: price_string(value) for field, value in prices.items()},
                                    "volume": volume, "instrument_id": instrument,
                                    "ts_event_ns": stamp, "bar_end_utc_ns": stamp + 60 * 10**9}
    check(count == partition["records"] and raw_bytes == partition["raw_bytes"]
          and checksum.hexdigest() == partition["raw_sha256"], "execution_raw_integrity_mismatch")
    return bars, invalid


def merge_execution(bundle, execution_root=execution.OUTPUT_ROOT):
    """Read each completed six-minute archive once; do not choose any fills."""
    plan = pinned(EXECUTION_PLAN, EXECUTION_PLAN_SHA)
    check(plan["schema"] == "ba012-execution-plan-v1" and plan["rolls_sha256"] == bundle["rolls_v2_sha256"]
          and plan["calendar_sha256"] == bundle["calendar_sha256"] and plan["amendment_sha256"] == bundle["amendment_sha256"]
          and plan["mapping"]["sha256"] == bundle["mapping_sha256"], "execution_plan_design_mismatch")
    check(len(plan["queries"]) == len(plan["required_contracts"]) == len(bundle["days"]) == 377, "execution_plan_count_mismatch")
    daily = {row["date_chicago"]: row for row in bundle["days"]}
    queries = {}
    for required, query in zip(plan["required_contracts"], plan["queries"]):
        day = required["date_chicago"]
        check(day in daily and {r["raw_symbol"]: r["instrument_id"] for r in required["contracts"]} == daily[day]["instrument_ids"], "execution_required_symbols_mismatch")
        check(query["dataset"] == "GLBX.MDP3" and query["schema"] == "ohlcv-1m" and query["stype_in"] == "parent"
              and query["symbols"] == "ES.FUT,TN.FUT,6E.FUT,GC.FUT,ZC.FUT"
              and reference.archive.stamp_ns(query["start"]) == ns_at(day, 10, 0)
              and reference.archive.stamp_ns(query["end"]) == ns_at(day, 10, 6), "execution_fixed_query_mismatch")
        identity = execution.query_id(query)
        check(identity not in queries, "duplicate_execution_plan_query")
        queries[identity] = (day, query)
    execution_root = Path(execution_root)
    check(execution_root.is_dir() and not (execution_root / ".download.lock").exists(), "execution_acquisition_incomplete_or_active")
    reserved, complete = execution.execution_prior(execution_root)
    check(complete == set(queries), "execution_acquisition_incomplete")
    manifests, archive_records, archive_bytes, partitions_read = [], 0, 0, set()
    for folder in sorted(execution_root.iterdir()):
        path = folder / "manifest.json"
        raw = path.read_bytes()
        report = reference.archive.load_json(raw)
        check(report["schema"] == execution.SCHEMA, "wrong_execution_archive_schema")
        check(digest(folder / "query-plan.json") == report["plan_sha256"] == EXECUTION_PLAN_SHA, "execution_archive_plan_mismatch")
        manifests.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
        for partition in report["partitions"]:
            if partition["status"] != "complete":
                continue
            identity = execution.query_id(partition["query"])
            check(identity in queries and identity not in partitions_read, "unexpected_or_duplicate_execution_archive")
            day, query = queries[identity]
            check(partition["query"] == query, "execution_archive_query_mismatch")
            row = daily[day]
            row["execution_bars"], invalid = decode_execution_file(folder / partition["file"], partition, row["instrument_ids"])
            row["execution_archive"] = {"manifest_path": str(path), "file": partition["file"],
                                        "raw_sha256": partition["raw_sha256"], "gzip_sha256": partition["gzip_sha256"]}
            invalid_keys = {(r["symbol"], r["minute"]): r["reason"] for r in invalid}
            for symbol, minutes in row["execution_bars"].items():
                for minute, bar in minutes.items():
                    if bar is None:
                        missing = {"date_chicago": day, "symbol": symbol, "field": "execution_bars", "minute": minute,
                                   "reason": invalid_keys.get((symbol, minute), "MISSING_EXACT_EXECUTION_BAR")}
                        row["missing_inputs"].append(missing)
                        bundle["missing_inputs"].append(missing)
            archive_records += partition["records"]
            archive_bytes += partition["raw_bytes"]
            partitions_read.add(identity)
    check(partitions_read == set(queries), "missing_completed_execution_partition")
    bundle.update(status="VERIFIED_INPUTS_WITH_MISSING_MARKS" if bundle["missing_inputs"] else "VERIFIED_INPUTS_COMPLETE",
                  execution_plan={"path": str(EXECUTION_PLAN), "sha256": EXECUTION_PLAN_SHA},
                  execution_archive_manifests=manifests, execution_reserved_estimate_usd=str(reserved),
                  execution_archive_records=archive_records, execution_archive_raw_bytes=archive_bytes,
                  execution_schema="Raw OHLCV bars by exact symbol and Chicago minute; opens are hypothetical fill inputs only, closes usable after bar_end_utc_ns.",
                  missing_counts_by_field=dict(Counter(r["field"] for r in bundle["missing_inputs"])))
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--reference-root", type=Path, default=reference.archive.OUTPUT_ROOT)
    parser.add_argument("--execution-root", type=Path, default=execution.OUTPUT_ROOT)
    args = parser.parse_args()
    result = merge_execution(build_base(args.reference_root), args.execution_root)
    result["generator_sha256"] = digest(Path(__file__))
    result["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["runtime"] = {"python": sys.version, "numpy": sizing.np.__version__}
    raw = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(raw)
    sidecar = args.output.with_suffix(args.output.suffix + ".sha256")
    with sidecar.open("x") as stream:
        stream.write(hashlib.sha256(raw).hexdigest() + "  " + args.output.name + "\n")
    args.output.chmod(0o444)
    sidecar.chmod(0o444)
    print(json.dumps({"status": result["status"], "days": len(result["days"]),
                      "missing": len(result["missing_inputs"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
