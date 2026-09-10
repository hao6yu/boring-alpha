#!/usr/bin/env python3
"""Apply frozen BA-012 v2 gold calendar amendment using metadata only."""
from bisect import bisect_left
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import build_ba012_rolls as base

EXPECTED_AMENDMENT = "a556ee73b7d2d54a054b88afebf3c8f9d736680b17657af71af4c3a0fae397a3"


def build():
    amendment_path = base.DIR / "settlement-amendment-v2.json"
    assert base.digest(amendment_path) == EXPECTED_AMENDMENT
    amendment = json.loads(amendment_path.read_bytes())
    for key in ("base_protocol", "calendar", "base_rolls"):
        assert base.digest(base.ROOT / amendment[key]["path"]) == amendment[key]["sha256"]
    original = json.loads((base.ROOT / amendment["base_rolls"]["path"]).read_bytes())
    result = deepcopy(original)
    result["contract_metadata"] = [c for c in result["contract_metadata"]
                                   if c["child_root"] != "1OZ" or c["contract_month"] != 10]
    calendar = json.loads(base.CALENDAR.read_bytes())
    joint = [date.fromisoformat(d) for d in calendar["joint_sessions"]]
    # Gold replacement at the final study date is February2024; its LTD/exit
    # are January2024. Extend dates only with the already-reviewed base rules.
    cursor = date(2024, 1, 1)
    while cursor < date(2024, 4, 1):
        if base.is_business_day(cursor):
            joint.append(cursor)
        cursor += base.timedelta(days=1)
    gold = {}
    for contract in result["contract_metadata"]:
        if contract["child_root"] != "1OZ":
            continue
        ltd = base.last_trade("1OZ", contract["contract_year"], contract["contract_month"])
        exit_day = joint[bisect_left(joint, ltd) - 5]
        assert sum(exit_day <= day < ltd for day in joint) == 5
        contract.update(exchange_last_trade_date=ltd.isoformat(),
                        effective_deadline_date=ltd.isoformat(), exit_date_chicago=exit_day.isoformat())
        gold[contract["parent_raw_symbol"]] = contract
    previous = None
    changed_active_dates = 0
    for before, row in zip(original["rows"], result["rows"]):
        old = before["markets"][3]
        current = row["markets"][3]
        assert old["child_root"] == current["child_root"] == "1OZ"
        year, month = map(int, old["active_maturity"].split("-"))
        month = 12 if month == 10 else month
        symbol = f"GC{base.MONTH_CODES[month - 1]}{year % 10}"
        selected = gold[symbol]
        nearest = next(c for c in gold.values() if c["exit_date_chicago"] > row["date_chicago"])
        assert selected == nearest
        changed_active_dates += symbol != old["active_parent_raw_symbol"]
        current.update(active_parent_raw_symbol=symbol, interval_parent_raw_symbol=previous,
                       is_roll=previous is not None and previous != symbol,
                       required_parent_raw_symbols=[symbol] if previous in (None, symbol) else [previous, symbol],
                       active_maturity=selected["maturity"],
                       active_exchange_last_trade_date=selected["exchange_last_trade_date"],
                       active_exit_date_chicago=selected["exit_date_chicago"])
        if current["is_roll"]:
            assert gold[previous]["exit_date_chicago"] == row["date_chicago"]
        for index in (0, 1, 2, 4):
            assert row["markets"][index] == before["markets"][index]
        previous = symbol
    counts = Counter(m["child_root"] for row in result["rows"] for m in row["markets"] if m["is_roll"])
    assert dict(counts) == {"1OZ": 40, "MZC": 40, "MTN": 32, "M6E": 32, "NES": 32}
    result.pop("frozen_before_archive_price_reads_by_generator", None)
    result.update(manifest_version=2, registered_utc=datetime.now(timezone.utc).isoformat(),
                  amendment_sha256=EXPECTED_AMENDMENT, base_rolls_sha256=amendment["base_rolls"]["sha256"],
                  frozen_before_settlement_price_reads=True, v1_coverage_already_seen=True,
                  generator_path="tools/build_ba012_rolls_v2.py", generator_sha256=base.digest(Path(__file__)),
                  base_generator_sha256=base.digest(Path(base.__file__)),
                  roll_counts=dict(sorted(counts.items())), gold_changed_active_reference_dates=changed_active_dates)
    result["rules"]["selection"] = "Frozen v2: nearest eligible child maturity, with October gold mapped to December of the same full year"
    result["rules"]["reference_source"] = "Official CME settlement messages selected under settlement-amendment-v2.json; not executable or simultaneous marks"
    result["rules"]["1OZ_allowed_months"] = [2, 4, 6, 8, 12]
    result["rules"]["account_execution"] = "No account execution or P&L in this v2 sizing-only amendment"
    return result


if __name__ == "__main__":
    report = build()
    target = base.DIR / "rolls-v2.json"
    raw = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    with target.open("xb") as stream:
        stream.write(raw)
    digest = hashlib.sha256(raw).hexdigest()
    with Path(str(target) + ".sha256").open("x") as stream:
        stream.write(digest + "  " + target.name + "\n")
    print(json.dumps({"path": str(target), "sha256": digest, "rows": len(report["rows"]),
                      "roll_counts": report["roll_counts"],
                      "gold_changed_active_reference_dates": report["gold_changed_active_reference_dates"]}))
