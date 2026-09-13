"""Offline fixed-span PTN source qualification. No network or strategy returns."""
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xc

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
NY = ZoneInfo("America/New_York")
START, END = "2022-07-01", "2023-11-01"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def event(row):
    return int(row["hd"]["ts_event"])


def day_of(row):
    return dt.datetime.fromtimestamp(event(row) // 10**9, dt.timezone.utc).astimezone(NY).date().isoformat()


def key(row):
    return int(row["hd"]["publisher_id"]), int(row["hd"]["instrument_id"]), event(row)


def order(row):
    return event(row), int(row["sequence"]), int(row["ts_recv"])


def load_json(path):
    data = path.read_bytes()
    return json.loads(data), digest(data)


def verify_action_sources(value, checked):
    if isinstance(value, dict):
        for file_key, hash_key in (("file", "sha256"), ("primary_file", "primary_sha256")):
            if file_key in value and hash_key in value:
                path = ROOT / value[file_key]
                assert digest(path.read_bytes()) == value[hash_key], f"action source mismatch: {path}"
                checked[str(path.relative_to(ROOT))] = value[hash_key]
        for child in value.values():
            verify_action_sources(child, checked)
    elif isinstance(value, list):
        for child in value:
            verify_action_sources(child, checked)


def build_day(day, opening_ns, closing_ns, trades, statistics, definitions):
    """Canonicalize current immutable records; return a failure instead of a fill."""
    failures, warnings = [], []
    if len(definitions) != 1:
        failures.append("MISSING_OR_MULTIPLE_DAILY_DEFINITIONS")
    for definition in definitions:
        if (definition.get("raw_symbol"), definition.get("exchange"), definition.get("security_type"),
                definition.get("instrument_class"), definition["hd"]["instrument_id"], definition["hd"]["publisher_id"]) != ("PTN", "XASE", "C", "K", 13132, 11):
            failures.append("HISTORICAL_IDENTITY_MISMATCH")
    if len({packed(r) for r in trades}) != len(trades):
        failures.append("EXACT_DUPLICATE_TRADE_RECORDS")
    for row in trades + statistics:
        if (int(row["hd"]["instrument_id"]), int(row["hd"]["publisher_id"])) != (13132, 11):
            failures.append("ROW_IDENTITY_MISMATCH")
        if not 0 < int(row["price"]) < 2**63-1 or int(row["ts_recv"]) < event(row):
            failures.append("INVALID_PRICE_OR_TIMESTAMP")
    for row in trades:
        if row["action"] != "T" or not 0 < int(row["size"]) < 2**32:
            failures.append("INVALID_TRADE_QUANTITY_ACTION")
    if any(int(s["stat_type"]) not in (1, 11, 16) or int(s["update_action"]) != 1 for s in statistics):
        failures.append("UNRESOLVED_STATISTIC_TYPE_DELETE_OR_REVISION")
    if len({(key(s), int(s["stat_type"])) for s in statistics}) != len(statistics):
        failures.append("AMBIGUOUS_STATISTIC_REVISION")
    opens = [s for s in statistics if int(s["stat_type"]) == 1]
    closes = [s for s in statistics if int(s["stat_type"]) == 11]
    if len(opens) > 1 or len(closes) > 1:
        failures.append("MULTIPLE_OPEN_OR_CLOSE_STATISTICS")
    core = [r for r in trades if opening_ns <= event(r) < closing_ns]
    if not core:
        failures.append("NO_CORE_SESSION_TRADE")
    auctions = [s for s in statistics if int(s["stat_type"]) in (1, 11) or opening_ns <= event(s) < closing_ns]
    removed, replacements, auction_audit = set(), [], []
    for stat in auctions:
        same = [t for t in trades if key(t) == key(stat)]
        if not all(int(t["price"]) == int(stat["price"]) for t in same):
            failures.append("AUCTION_TIMESTAMP_PRICE_COLLISION")
        bulk = [t for t in same if int(t["sequence"]) == int(stat["sequence"]) and int(t["size"]) == int(stat["quantity"])]
        if len(bulk) != 1 or not 0 < int(stat["quantity"]) < 2**63-1:
            failures.append("AUCTION_BULK_BINDING_OR_QUANTITY_UNRESOLVED")
        removed.add(key(stat))
        replacements.append({"event_ns": event(stat), "sequence": int(stat["sequence"]),
                             "price": int(stat["price"]), "size": int(stat["quantity"]), "ts_recv": int(stat["ts_recv"])})
        auction_audit.append({"stat_type": int(stat["stat_type"]), "event_ns": event(stat),
                              "quantity": int(stat["quantity"]), "same_event_trade_count": len(same),
                              "same_event_trade_shares": sum(int(t["size"]) for t in same),
                              "individual_fill_shares_removed": sum(int(t["size"]) for t in same) - int(stat["quantity"])})
    if failures:
        return {"date": day, "status": "SOURCE_UNRESOLVED", "failures": sorted(set(failures))}
    points = [{"event_ns": event(t), "sequence": int(t["sequence"]), "price": int(t["price"]),
               "size": int(t["size"]), "ts_recv": int(t["ts_recv"])} for t in core if key(t) not in removed] + replacements
    first = opens[0] if opens else min(core, key=order)
    last = closes[0] if closes else max(core, key=order)
    if not opens:
        warnings.append("OPEN_USES_FIRST_CORE_TRADE")
    if not closes:
        warnings.append("CLOSE_USES_LAST_CORE_TRADE")
    result = {"date": day, "status": "QUALIFIED_RAW_PRIMARY_VENUE_PROXY", "failures": [], "warnings": warnings,
              "open": int(first["price"]) / 1e9, "high": max(p["price"] for p in points) / 1e9,
              "low": min(p["price"] for p in points) / 1e9, "close": int(last["price"]) / 1e9,
              "volume": sum(p["size"] for p in points), "open_basis": "CORE_OPENING_AUCTION" if opens else "FIRST_CORE_TRADE",
              "close_basis": "CORE_CLOSING_AUCTION" if closes else "LAST_CORE_TRADE",
              "open_event_ns": event(first), "close_event_ns": event(last),
              "close_age_before_scheduled_close_seconds": max(0, closing_ns-event(last)) / 1e9,
              "close_event_offset_from_scheduled_close_seconds": (event(last)-closing_ns) / 1e9,
              "open_event_offset_from_scheduled_open_seconds": (event(first)-opening_ns) / 1e9,
              "source_cutoff_used_ns": max(p["ts_recv"] for p in points),
              "scheduled_open_ns": opening_ns, "scheduled_close_ns": closing_ns,
              "source_trade_rows": len(trades), "source_core_trade_rows": len(core),
              "excluded_noncore_nonauction_trade_rows": sum(not opening_ns <= event(t) < closing_ns and key(t) not in removed for t in trades),
              "source_stat_rows": len(statistics), "canonical_auction_groups": auction_audit}
    assert result["low"] <= min(result["open"], result["close"]) <= max(result["open"], result["close"]) <= result["high"]
    assert result["volume"] > 0
    return result


def main():
    manifest, manifest_sha = load_json(HERE / "ptn-download-manifest.json")
    actions, actions_sha = load_json(HERE / "ptn-actions.json")
    review, review_sha = load_json(HERE / "databento-source-review.json")
    action_sources = {}
    verify_action_sources(actions, action_sources)
    assert actions["cash_dividends"]["through_target_end_verified"]
    assert not actions["additional_common_split_found_in_target_span"]
    assert len(actions["common_share_adjustment_actions"]) == 1
    split = actions["common_share_adjustment_actions"][0]
    assert (split["first_split_adjusted_regular_session"], split["old_shares"], split["new_shares"]) == ("2022-08-31", 25, 1)
    groups, files = {}, []
    for f in manifest["downloads"]:
        if f["params"]["start"] != START or f["params"]["end"] != END:
            continue
        assert f["params"]["dataset"] == "XASE.PILLAR" and f["params"]["symbols"] == "PTN"
        content = (ROOT / f["path"]).read_bytes()
        assert digest(content) == f["sha256"] and len(content) == f["bytes"]
        rows = [json.loads(line) for line in content.splitlines() if line]
        assert len(rows) == f["rows"] < f["params"]["limit"]
        schema = f["params"]["schema"]
        assert schema not in groups
        groups[schema] = rows
        files.append({k: f[k] for k in ("path", "sha256", "bytes", "rows")})
    assert set(groups) == {"trades", "statistics", "definition"}
    by_day = {schema: collections.defaultdict(list) for schema in groups}
    for schema, rows in groups.items():
        for row in rows:
            by_day[schema][day_of(row)].append(row)
    calendar = xc.get_calendar("XNYS", start=START, end="2023-10-31")
    schedule = [{"date": str(day.date()), "open_ns": row.open.value, "close_ns": row.close.value}
                for day, row in calendar.schedule.iterrows()]
    assert len(schedule) == 336
    dates = {s["date"] for s in schedule}
    assert all(set(source) <= dates for source in by_day.values()), "non-session source rows require investigation"
    rows = [build_day(s["date"], s["open_ns"], s["close_ns"], by_day["trades"][s["date"]],
                      by_day["statistics"][s["date"]], by_day["definition"][s["date"]]) for s in schedule]
    windows = []
    for window in review["required_windows"]:
        selected = [r for r in rows if window["start"] <= r["date"] <= window["end_inclusive"]]
        assert len(selected) == window["sessions"] == 81
        failures = [r["date"] for r in selected if r["status"] != "QUALIFIED_RAW_PRIMARY_VENUE_PROXY"]
        windows.append({**window, "observed_sessions": len(selected), "unresolved_dates": failures,
                        "source_gate_pass": not failures, "fallback_close_dates": [r["date"] for r in selected if r.get("close_basis") == "LAST_CORE_TRADE"],
                        "actions_pass": True, "price_and_volume_basis": "Raw event-time prices and shares; NYSE American partial venue; auction duplication canonicalized."})
    qualified = sum(r["status"] == "QUALIFIED_RAW_PRIMARY_VENUE_PROXY" for r in rows)
    basis = "NYSE American provider-normalized core-session trades, replacing complete same-event auction groups with one official auction statistic. Official close where present; otherwise last core trade with explicit age. Raw contemporary share and price units."
    provenance = {"manifest_sha256": manifest_sha, "actions_sha256": actions_sha, "source_review_sha256": review_sha,
                  "script_sha256": digest(Path(__file__).read_bytes()), "raw_files": files,
                  "exchange_calendars_version": xc.__version__, "calendar": "XNYS", "schedule_sha256": digest(packed(schedule)),
                  "early_close_dates": [str(d.date()) for d in calendar.early_closes]}
    daily = {"schema": "PTN-raw-canonical-daily-v1", "provenance": provenance, "price_volume_basis": basis,
             "split_adjusted": False, "dividend_adjusted": False, "consolidated": False, "schedule": schedule, "rows": rows}
    daily_path = ROOT / "data/snapshots/equity-event-test-2026-09-10/ptn-xase/rawcanonicaldaily.json"
    daily_path.write_text(json.dumps(daily, indent=2, sort_keys=True) + "\n")
    audit = {"schema": "PTN-full-source-audit-v1", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
             "status": "FULL_SOURCE_GATE_MET" if qualified == 336 else "SOURCE_UNRESOLVED", "provenance": provenance,
             "rawcanonicaldaily_path": str(daily_path.relative_to(ROOT)), "rawcanonicaldaily_sha256": digest(daily_path.read_bytes()),
             "expected_sessions": 336, "qualified_sessions": qualified, "required_windows": windows,
             "qualified_windows": sum(w["source_gate_pass"] for w in windows),
             "raw_counts": {k: len(v) for k, v in groups.items()},
             "statistics_types": dict(collections.Counter(r["stat_type"] for r in groups["statistics"])),
             "statistics_update_actions": dict(collections.Counter(r["update_action"] for r in groups["statistics"])),
             "fallback_close_days": [{k: r[k] for k in ("date", "close", "close_basis", "close_age_before_scheduled_close_seconds", "source_core_trade_rows")} for r in rows if r.get("close_basis") == "LAST_CORE_TRADE"],
             "fallback_open_days": [r["date"] for r in rows if r.get("open_basis") == "FIRST_CORE_TRADE"],
             "failures": [r for r in rows if r["status"] == "SOURCE_UNRESOLVED"],
             "action_source_hashes_verified": action_sources,
             "auction_groups_canonicalized": sum(len(r.get("canonical_auction_groups", [])) for r in rows),
             "auction_extra_print_shares_removed": sum(a["individual_fill_shares_removed"] for r in rows for a in r.get("canonical_auction_groups", [])),
             "anchor_june16_2023": {"expected_close": 2.19, "observed_close": next(r["close"] for r in rows if r["date"] == "2023-06-16")},
             "basis": basis,
             "limitations": ["Source qualification is not a profitability result or claim of executable daily auction fills.",
                             "Primary-venue volume excludes other venues; provider cancellation/printability methodology remains disclosed. No perfect-tape or consolidated-volume gate was added.",
                             "Historical issuer2024 dividend statement is used solely to verify actions ex post; it is not a2022-2023 predictor.",
                             "Original four event entries occur after the2022 reverse split. Feature windows crossing it need separately declared action normalization; raw data is never automatically back-adjusted.",
                             "Five missing closing auctions use regular-session last trades; their age is preserved. Missing records do not imply zero returns or hypothetical execution."],
             "no_network": True, "strategy_returns_calculated": False}
    assert audit["anchor_june16_2023"]["observed_close"] == 2.19
    path = HERE / "ptn-full-audit.json"
    path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"path": str(path.relative_to(ROOT)), "sha256": digest(path.read_bytes()), "daily_sha256": audit["rawcanonicaldaily_sha256"],
                      "status": audit["status"], "sessions": qualified, "windows": audit["qualified_windows"], "fallback_closes": len(audit["fallback_close_days"])}))


if __name__ == "__main__":
    main()
