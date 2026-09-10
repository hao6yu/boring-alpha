#!/usr/bin/env python3
"""One exploratory past-only conditional spread screen; no strategy backtest."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

from us_futures_history import HOUR, PAIRS, ROOT, load_snapshot, paired_rows
from us_futures_spread import analyze as analyze_quotes, trade_fees

POLICY_FILE = ROOT / "research/ba009b-conditional-screen-policy.json"


def percentile(values: list[float], quantile: float) -> float:
    if not values or not 0 < quantile <= 1:
        raise ValueError("quantile requires observations and probability in (0,1]")
    return sorted(values)[math.ceil(quantile * len(values)) - 1]


def distribution(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"count": len(values), "mean": statistics.fmean(values), "median": statistics.median(values),
            "p10": percentile(values, 0.1), "p90": percentile(values, 0.9),
            "min": min(values), "max": max(values)}


def classify(rows: list[dict], policy: dict) -> list[dict]:
    """Uses only current/past pairs; scheduled nonoverlap ignores future availability."""
    rows = sorted(rows, key=lambda r: r["start"])
    if len({r["start"] for r in rows}) != len(rows):
        raise ValueError("duplicate paired times")
    signals, past = [], []
    next_slot = -math.inf
    for row in rows:
        stamp = row["start"]
        past = [r for r in past if r["start"] >= stamp - policy["lookback_hours"] * HOUR]
        if row["both_have_reported_volume"] and len(past) >= policy["minimum_past_paired_bars"]:
            values = [r["gap_bps_of_perp"] for r in past]
            threshold = percentile(values, policy["high_quantile"])
            high = row["gap_bps_of_perp"] > threshold and row["gap_bps_of_perp"] > 0
            selected = stamp >= next_slot
            if selected:
                next_slot = stamp + policy["nonoverlap_spacing_hours"] * HOUR
            signals.append({"signal_start": stamp, "signal_available_at": stamp + HOUR,
                            "signal_gap_bps": row["gap_bps_of_perp"],
                            "past_observations": len(past), "past_p90_bps": threshold,
                            "group": "high" if high else "ordinary", "nonoverlap_slot": selected,
                            "signal_gap_usd_per_unit": row["gap_usd_per_underlying"]})
        if row["both_have_reported_volume"]:
            past.append(row)
    return signals


def attach_outcomes(signals: list[dict], rows: list[dict], end_exclusive: int, policy: dict) -> list[dict]:
    by_time = {row["start"]: row for row in rows if row["both_have_reported_volume"]}
    results = []
    for signal in signals:
        row = dict(signal)
        entry_time = row["signal_start"] + policy["entry_delay_hours"] * HOUR
        exit_time = entry_time + policy["holding_hours"] * HOUR
        row.update({"entry_start": entry_time, "exit_start": exit_time,
                    "missing_entry": entry_time not in by_time,
                    "right_censored": exit_time >= end_exclusive,
                    "missing_exit": exit_time < end_exclusive and exit_time not in by_time})
        row["missing_path_bars"] = sum(t not in by_time for t in range(entry_time, min(exit_time + HOUR, end_exclusive), HOUR))
        if not row["missing_entry"]:
            entry = by_time[entry_time]
            row["signal_to_entry_narrowing_bps"] = (row["signal_gap_usd_per_unit"] - entry["gap_usd_per_underlying"]) / entry["perp_close"] * 10000
            row["entry_perp_close"] = entry["perp_close"]
            row["entry_dated_close"] = entry["dated_close"]
            row["entry_proxy_gap_bps"] = entry["gap_bps_of_perp"]
        if row["right_censored"]:
            row["outcome_state"] = "RIGHT_CENSORED"
        elif row["missing_entry"] or row["missing_exit"]:
            row["outcome_state"] = "MISSING_ENDPOINT"
        else:
            row["outcome_state"] = "OBSERVED_ENDPOINTS"
            entry, leave = by_time[entry_time], by_time[exit_time]
            denominator = entry["perp_close"]
            # Fixed-quantity pair: dollar gap change, normalized by ENTRY perp only.
            row["delayed_narrowing_bps"] = (entry["gap_usd_per_underlying"] - leave["gap_usd_per_underlying"]) / denominator * 10000
        results.append(row)
    return results


def cost_reference(row: dict, quote: dict, quote_policy: dict, size: float, policy: dict) -> list[dict]:
    """Cost hurdles use current assumptions; no hypothetical returns are booked."""
    p, d = row["entry_perp_close"], row["entry_dated_close"]
    contracts = math.floor(policy["capital_usd"] * policy["max_leg_fraction"] / (size * max(p, d)))
    if contracts < 1:
        return []
    notional = contracts * size * p
    qfills = quote["fills"]
    reference_pmid = (qfills["perp"]["asks"] + qfills["perp"]["bids"]) / 2
    quoted_spread_bps = sum(qfills[leg]["asks"] - qfills[leg]["bids"] for leg in ("perp", "dated")) / reference_pmid * 10000
    funding_bps = policy["reference_funding_simple_annual"] * policy["holding_hours"] / 8760 * 10000
    cash_bps = policy["capital_usd"] * policy["reference_cash_rate"] * policy["holding_hours"] / 8760 / notional * 10000
    result = []
    for case in quote_policy["fee_cases"]:
        if case["name"] not in policy["reference_fee_cases"]:
            continue
        # Round trip at unchanged reference prices, not the unknown historical fills.
        fees_bps = 2 * trade_fees(contracts, size, {"perp": p, "dated": d}, case) / notional * 10000
        for multiplier in policy["reference_spread_multipliers"]:
            cost = fees_bps + funding_bps + cash_bps + quoted_spread_bps * multiplier
            result.append({"case": case["name"], "spread_multiplier": multiplier,
                           "contracts_each_leg": contracts, "reference_hurdle_bps": cost,
                           "price_change_exceeds_reference_hurdle": row["delayed_narrowing_bps"] > cost})
    return result


def describe(rows: list[dict]) -> dict:
    observed = [r for r in rows if r["outcome_state"] == "OBSERVED_ENDPOINTS"]
    costs = defaultdict(list)
    hits = defaultdict(list)
    for r in observed:
        for c in r.get("cost_references", []):
            key = c["case"] + f"_spread{c['spread_multiplier']}"
            costs[key].append(c["reference_hurdle_bps"])
            hits[key].append(c["price_change_exceeds_reference_hurdle"])
    return {"signals": len(rows), "distinct_signal_dates": len({r["signal_start"] // (24 * HOUR) for r in rows}),
            "outcome_counts": dict(Counter(r["outcome_state"] for r in rows)),
            "missing_entry": sum(r["missing_entry"] for r in rows),
            "missing_exit": sum(r["missing_exit"] for r in rows),
            "observed_endpoints_with_interior_gaps": sum(r["missing_path_bars"] > 0 for r in observed),
            "delayed_narrowing_bps": distribution([r["delayed_narrowing_bps"] for r in observed]),
            "signal_to_entry_narrowing_bps": distribution([r["signal_to_entry_narrowing_bps"] for r in rows if "signal_to_entry_narrowing_bps" in r]),
            "reference_cost_hurdles_bps": {k: distribution(v) for k, v in costs.items()},
            "price_changes_exceeding_reference_cost": {k: {"count": sum(v), "observations": len(v)} for k, v in hits.items()}}


def evaluate(rows: list[dict], end_exclusive: int, policy: dict, quote: dict, quote_policy: dict, size: float) -> dict:
    signals = classify(rows, policy)
    observations = attach_outcomes(signals, rows, end_exclusive, policy)
    for row in observations:
        if row["outcome_state"] == "OBSERVED_ENDPOINTS":
            row["cost_references"] = cost_reference(row, quote, quote_policy, size, policy)
    by_week = defaultdict(list)
    for row in observations:
        iso = datetime.fromtimestamp(row["signal_start"], timezone.utc).isocalendar()
        by_week[f"{iso.year}-W{iso.week:02}"].append(row)
    positive = sum(r["both_have_reported_volume"] for r in rows)
    return {"eligibility": {"paired_rows": len(rows), "positive_volume_paired_rows": positive,
                             "excluded_for_inadequate_past": positive - len(signals), "eligible_signals": len(signals)},
            "groups": {group: describe([r for r in observations if r["group"] == group]) for group in ("high", "ordinary")},
            "nonoverlap_groups": {group: describe([r for r in observations if r["group"] == group and r["nonoverlap_slot"]]) for group in ("high", "ordinary")},
            "by_week": {week: {group: describe([r for r in rr if r["group"] == group]) for group in ("high", "ordinary")} for week, rr in sorted(by_week.items())},
            "observations": observations}


def run(policy: dict) -> dict:
    history = ROOT / policy["history_snapshot"]
    quotes = ROOT / policy["quote_snapshot"]
    manifest, candles, products = load_snapshot(history)
    quote_report = analyze_quotes(quotes)
    assets = {}
    for root, (perp, dated) in PAIRS.items():
        quote = next(a for a in quote_report["assets"] if a["asset"] == root)
        if quote["products"] != {"perp": perp, "dated": dated}:
            raise ValueError("quote/history exact product mismatch")
        size = float(products[perp]["future_product_details"]["contract_size"])
        if size != float(products[dated]["future_product_details"]["contract_size"]):
            raise ValueError("unequal contract multipliers")
        assets[root] = evaluate(paired_rows(candles[perp], candles[dated]), manifest["end_exclusive"], policy,
                                quote, quote_report["policy"], size)
    return {"status": "EXPLORATORY_PRICE_PROXY_ONLY", "candidate": "BA-009B", "policy": policy,
            "input_manifest_hashes": {name: hashlib.sha256((p / "manifest.json").read_bytes()).hexdigest()
                                       for name, p in (("history", history), ("quotes", quotes))},
            "assets": assets,
            "limitations": ["No executable strategy P&L or expected return has been estimated.",
                "Historical last trades may be asynchronous, including within a common hour.",
                "Conditional observations overlap; nonoverlap slots were chosen before outcomes and can remain missing.",
                "High/ordinary differences can reflect calendar, contract lifecycle, missingness, and stale prices.",
                "Cost reference uses assumed 10% annual funding and current spreads/fees, not historical realized costs.",
                "Spread references use the snapshot's original contract size/depth, not quantity-matched historical fills.",
                "Observed endpoints do not establish marks, margin compliance or survival between them."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY_FILE)
    parser.add_argument("--snapshot", type=Path, help="offline replay and comparison with a saved result")
    parser.add_argument("--out", type=Path, default=ROOT / "data/us_crypto/conditional-screens")
    args = parser.parse_args()
    policy_path = args.snapshot / "policy.json" if args.snapshot else args.policy
    policy_bytes = policy_path.read_bytes()
    policy = json.loads(policy_bytes)
    result = run(policy)
    if args.snapshot:
        target = args.snapshot
        saved = json.loads((target / "report.json").read_text())
        saved.pop("analysis_code_sha256", None)
        if result != saved:
            raise ValueError("saved result does not reproduce; archive was not modified")
        print("Offline replay matches saved result (analysis source hash excluded).")
    else:
        target = args.out / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target.mkdir(parents=True, exist_ok=False)
        (target / "policy.json").write_bytes(policy_bytes)
        result["analysis_code_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (target / "report.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    for root, asset in result["assets"].items():
        for group, summary in asset["groups"].items():
            print(root, group, json.dumps({k: summary[k] for k in
                ("signals", "outcome_counts", "delayed_narrowing_bps")}, sort_keys=True))
    print(f"Report: {target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
