#!/usr/bin/env python3
"""BA-009B: public U.S. dated/perpetual futures spread feasibility.

Read-only quotes and explicit scenarios, not a trading strategy or forecast.
The long leg is always the perp and the short leg always the dated future.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import urllib.parse

from us_crypto_carry import ROOT, fetch, futures_fee, number, read_book, timestamp, utcnow, vwap

SCHEMA = "us-dated-perpetual-feasibility-v1"
POLICY_FILE = ROOT / "research/ba009b-feasibility-policy.json"


def executable(product: dict) -> bool:
    flags = ("is_disabled", "trading_disabled", "cancel_only", "view_only", "post_only", "auction_mode")
    return (product.get("product_type") == "FUTURE" and product.get("product_venue") == "FCM"
            and product.get("quote_currency_id") == "USD"
            and all(product.get(key) is False for key in flags)
            and product.get("fcm_trading_session_details", {}).get("is_session_open") is True)


def select_pairs(products: list[dict], asof: str, min_hours: float) -> tuple[dict, list]:
    out, rejected = {}, []
    for root in ("BTC", "ETH"):
        perp, dated = [], []
        for product in products:
            details = product.get("future_product_details") or {}
            if details.get("contract_root_unit") != root or product.get("product_venue") != "FCM":
                continue
            if not executable(product):
                rejected.append({"product_id": product["product_id"], "reason": "public flags do not support immediate execution"})
                continue
            hours = (timestamp(details["contract_expiry"]) - timestamp(asof)).total_seconds() / 3600
            if hours < min_hours:
                rejected.append({"product_id": product["product_id"], "reason": "too near expiry or expired"})
                continue
            if details.get("funding_interval") == "3600s":
                perp.append(product)
            elif details.get("funding_interval") in (None, "") and details.get("funding_rate") in (None, ""):
                dated.append(product)
        if len(perp) != 1 or not dated:
            raise ValueError(f"{root}: require one hourly-funded perp and at least one executable dated contract")
        dated.sort(key=lambda p: (timestamp(p["future_product_details"]["contract_expiry"]), p["product_id"]))
        # Closest eligible expiry in the observed listing, never best historical return.
        out[root] = {"perp": perp[0], "dated": dated[0]}
    return out, rejected


def trade_fees(count: int, size: float, prices: dict, case: dict, legs=("perp", "dated")) -> float:
    return sum(futures_fee(count, size, prices[leg], case[f"{leg}_bps"], case[f"{leg}_min_usd"])
               for leg in legs)


def spread_pnl(quantity: float, perp_entry: float, dated_entry: float,
               perp_exit: float, dated_exit: float, funding_cash: float, fees_cash: float) -> float:
    """Signed fills already include spreads; a long perp pays positive funding."""
    return quantity * ((dated_entry - perp_entry) - (dated_exit - perp_exit)) - funding_cash - fees_cash


def screen_pair(root: str, pair: dict, books: dict, policy: dict, asof: str) -> dict:
    capital = number(policy["capital_usd"], "capital")
    details = {leg: p["future_product_details"] for leg, p in pair.items()}
    size = number(details["perp"]["contract_size"], "perp contract size")
    if size != number(details["dated"]["contract_size"], "dated contract size"):
        raise ValueError("unequal contract multipliers require separate integer hedge sizing")
    margin = {"perp": number(details["perp"]["overnight_margin_rate"]["long_margin_rate"], "perp margin"),
              "dated": number(details["dated"]["overnight_margin_rate"]["short_margin_rate"], "dated margin")}
    rate = number(details["perp"]["funding_rate"], "hourly funding", positive=False)
    hours_left = (timestamp(details["dated"]["contract_expiry"]) - timestamp(asof)).total_seconds() / 3600
    if hours_left < policy["min_hours_to_expiry"]:
        raise ValueError("dated contract too close to expiry")
    base = next(c for c in policy["fee_cases"] if c["name"] == "base_assumed")
    max_price = max(books[leg]["asks"][0][0] for leg in pair)
    limit = math.floor(capital * policy["max_leg_fraction"] / (size * max_price))
    quote = None
    for count in range(limit, 0, -1):
        try:
            fills = {leg: {side: vwap(books[leg][side], count) for side in ("bids", "asks")} for leg in pair}
        except ValueError:
            continue
        quantity = count * size
        if max(fills[leg]["asks"] for leg in pair) * quantity > capital * policy["max_leg_fraction"]:
            continue
        entry_prices = {"perp": fills["perp"]["asks"], "dated": fills["dated"]["bids"]}
        entry_fees = trade_fees(count, size, entry_prices, base)
        initial_margin = quantity * sum(fills[leg]["asks"] * margin[leg] for leg in pair)
        entry_mark_loss = quantity * sum((fills[leg]["asks"] - fills[leg]["bids"]) / 2 for leg in pair)
        if capital - entry_fees - entry_mark_loss - initial_margin >= policy["reserve_usd"]:
            quote = count, quantity, fills, entry_fees, initial_margin
            break
    if quote is None:
        return {"asset": root, "status": "NO_SIZE_WITHIN_BUDGET_AND_DEPTH"}
    count, quantity, fills, entry_fees, initial_margin = quote
    pa, pb = fills["perp"]["asks"], fills["perp"]["bids"]
    da, db = fills["dated"]["asks"], fills["dated"]["bids"]
    pmid, dmid = (pa + pb) / 2, (da + db) / 2
    gap = dmid - pmid
    round_trip_spread = quantity * (pa - pb + da - db)
    mid_pnl_at_entry = quantity * ((pmid - pa) + (db - dmid))
    entry_equity = capital - entry_fees + mid_pnl_at_entry
    # Fixed dollar gap while the common underlying moves; both marks are positive.
    common_marks = {leg: (pmid if leg == "perp" else dmid) + pmid * policy["common_price_stress_fraction"]
                    for leg in pair}
    common_pnl = quantity * ((common_marks["perp"] - pa) + (db - common_marks["dated"]))
    stressed_margin = quantity * sum(common_marks[leg] * margin[leg] for leg in pair) * policy["margin_rate_stress_multiplier"]
    common_headroom = capital - entry_fees + common_pnl - stressed_margin
    widening_loss = quantity * pmid * 0.01
    single_leg_move = quantity * max(pa, da) * policy["leg_failure_move_fraction"]
    cases = {"unchanged": gap, "half_current_gap": gap / 2, "zero_gap": 0.0,
             "widens_one_percent_of_perp": gap + pmid * 0.01}
    rates = [(f"annual_{annual:g}", annual / 8760) for annual in policy["funding_simple_annual_scenarios"]]
    if policy["include_current_hourly_funding_scenario"]:
        rates.append(("current_hour_persists", rate))
    scenarios = []
    excluded_days = []
    for days in policy["holding_days"]:
        if days * 24 > hours_left - policy["exit_buffer_hours"]:
            excluded_days.append(days)
            continue
        for case in policy["fee_cases"]:
            entry_fee = trade_fees(count, size, {"perp": pa, "dated": db}, case)
            entry_feasible = capital + mid_pnl_at_entry - initial_margin - entry_fee >= policy["reserve_usd"]
            for label, funding_rate in rates:
                funding = quantity * pmid * funding_rate * days * 24
                for gap_case in policy["terminal_gap_cases"]:
                    for exit_spread_multiplier in policy["exit_spread_multipliers"]:
                        terminal_gap = cases[gap_case]
                        # Same common perp price and observed size-specific spread at exit.
                        exit_prices = {"perp": pmid - (pa - pb) / 2 * exit_spread_multiplier,
                                       "dated": pmid + terminal_gap + (da - db) / 2 * exit_spread_multiplier}
                        if min(exit_prices.values()) <= 0:
                            raise ValueError("scenario has nonpositive exit price")
                        fees = entry_fee + trade_fees(count, size, exit_prices, case)
                        net = spread_pnl(quantity, pa, db, exit_prices["perp"], exit_prices["dated"], funding, fees)
                        scenario_spread = round_trip_spread * (1 + exit_spread_multiplier) / 2
                        for cash_rate in policy["cash_rates"]:
                            cash = capital * cash_rate * days / 365
                            needed = (fees + funding + scenario_spread + cash) / quantity
                            scenarios.append({"holding_days": days, "fee_case": case["name"],
                                "funding_case": label, "hourly_funding_rate": funding_rate,
                                "exit_spread_multiplier": exit_spread_multiplier,
                                "terminal_gap_case": gap_case, "terminal_mid_gap_usd_per_unit": terminal_gap,
                                "entry_feasible_under_fee_case": entry_feasible,
                                "round_trip_fees_usd": fees, "round_trip_spread_usd": scenario_spread,
                                "funding_paid_usd": funding, "net_pnl_usd": net,
                                "return_on_full_capital": net / capital, "cash_rate": cash_rate,
                                "cash_benchmark_usd": cash, "excess_over_cash_usd": net - cash,
                                "required_mid_gap_narrowing_at_scenario_fees_usd_per_unit": needed,
                                "max_terminal_executable_gap_at_scenario_fees_usd_per_unit": db - pa - (fees + funding + cash) / quantity})
    return {"asset": root, "status": "SCENARIOS_ONLY", "products": {l: p["product_id"] for l, p in pair.items()},
            "contracts_each_leg": count, "underlying_quantity": quantity, "contract_size": size,
            "hours_to_dated_expiry": hours_left, "excluded_holding_days": excluded_days,
            "fills": fills, "initial_mid_gap_usd_per_unit": gap,
            "executable_entry_gap_usd_per_unit": db - pa,
            "notional_each_leg_usd": {"perp": quantity * pmid, "dated": quantity * dmid},
            "initial_gross_notional_usd": quantity * (pmid + dmid),
            "funding_rate_reported": rate, "funding_time_reported": details["perp"]["funding_time"],
            "initial_margin_no_offset_usd": initial_margin,
            "initial_cash_beyond_margin_and_entry_fees_usd": capital - initial_margin - entry_fees,
            "initial_equity_beyond_margin_usd": entry_equity - initial_margin,
            "entry_equity_at_mid_after_fees_usd": entry_equity,
            "stress": {"common_price_rise_fraction": policy["common_price_stress_fraction"],
                "margin_rate_multiplier": policy["margin_rate_stress_multiplier"],
                "common_rise_and_margin_increase_headroom_usd": common_headroom,
                "one_percent_additional_gap_widening_loss_usd": widening_loss,
                "isolated_leg_20pct_adverse_move_price_loss_usd": single_leg_move,
                "note": "scenarios exclude accrued future funding and emergency liquidation costs; not guaranteed loss limits"},
            "scenarios": scenarios}


def analyze(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["schema"] != SCHEMA:
        raise ValueError("wrong snapshot schema")
    payloads = {}
    for name, source in manifest["sources"].items():
        if Path(name).name != name:
            raise ValueError("unsafe snapshot filename")
        body = (directory / name).read_bytes()
        if hashlib.sha256(body).hexdigest() != source["sha256"]:
            raise ValueError(f"checksum mismatch: {name}")
        payloads[name] = json.loads(body)
    policy = payloads["policy.json"]
    asof = manifest["finished_at"]
    pairs, rejected = select_pairs(payloads["products.json"]["products"], asof, policy["min_hours_to_expiry"])
    assets = []
    for root, pair in pairs.items():
        books = {}
        for leg, product in pair.items():
            name = f"{root}-{leg}-book.json"
            # Validate at completion, not just receipt, so an early book cannot age unnoticed.
            books[leg] = read_book(payloads[name], product["product_id"], asof, policy["max_book_age_seconds"])
        skew = abs((timestamp(books["perp"]["time"]) - timestamp(books["dated"]["time"])).total_seconds())
        if skew > policy["max_pair_skew_seconds"]:
            raise ValueError(f"{root}: asynchronous quotes exceed pair skew limit")
        funding_age = (timestamp(asof) - timestamp(pair["perp"]["future_product_details"]["funding_time"])).total_seconds()
        if not -3600 <= funding_age <= 7200:
            raise ValueError("stale or future funding metadata")
        result = screen_pair(root, pair, books, policy, asof)
        result["quote_skew_seconds"] = skew
        assets.append(result)
    return {"schema": SCHEMA, "observed_at": asof, "profitability_verdict": "NOT_ESTABLISHED",
            "policy": policy, "assets": assets, "excluded_products": rejected,
            "limitations": ["quotes are indicative and not atomic two-leg fills",
                "dated/perp all-in fees remain separately assumed, not account verified",
                "terminal gaps and funding are scenarios, not forecasts; zero gap is not guaranteed",
                "no historical order book, funding settlement marks, or margin path in this snapshot",
                "full-capital cash comparison; no collateral yield, taxes, or operating overhead",
                "public tradability flags do not establish account approval"]}


def collect(output: Path) -> Path:
    directory = output / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, exist_ok=False)
    started, sources = utcnow(), {}

    def save(name, body, source):
        (directory / name).write_bytes(body)
        sources[name] = source

    try:
        body, source = fetch("products?product_type=FUTURE&limit=100")
        save("products.json", body, source)
        policy_body = POLICY_FILE.read_bytes()
        policy = json.loads(policy_body)
        pairs, _ = select_pairs(json.loads(body)["products"], utcnow(), policy["min_hours_to_expiry"])
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(fetch, "product_book?" + urllib.parse.urlencode({"product_id": p["product_id"], "limit": 50})):
                    f"{root}-{leg}-book.json" for root, pair in pairs.items() for leg, p in pair.items()}
            for job in as_completed(jobs):
                body, source = job.result()
                save(jobs[job], body, source)
        save("policy.json", policy_body, {"sha256": hashlib.sha256(policy_body).hexdigest()})
        files = [Path(__file__), ROOT / "tools/us_crypto_carry.py", ROOT / "tools/fetch_market_data.py"]
        manifest = {"schema": SCHEMA, "started_at": started, "finished_at": utcnow(), "sources": sources,
                    "code_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                    "listing_scope": "first 100 public futures; closest executable dated expiry within observed listing"}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    except Exception as exc:
        (directory / "failure.json").write_text(json.dumps({"error": str(exc), "sources": sources,
                                                           "failed_at": utcnow()}, indent=2) + "\n")
        raise
    return directory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="offline replay without modifying the snapshot")
    parser.add_argument("--out", type=Path, default=ROOT / "data/us_crypto/spread-snapshots")
    args = parser.parse_args()
    try:
        directory = args.snapshot or collect(args.out)
        report = analyze(directory)
        if args.snapshot is None:
            (directory / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
        print(f"BA-009B: {report['profitability_verdict']} (hypothetical spread/funding scenarios)")
        for asset in report["assets"]:
            print(asset["asset"], asset["status"])
            if asset["status"] == "SCENARIOS_ONLY":
                print(f"  {asset['contracts_each_leg']} contracts/leg; entry gap ${asset['executable_entry_gap_usd_per_unit']:.4f}/unit; margin ${asset['initial_margin_no_offset_usd']:.2f}")
                for row in asset["scenarios"]:
                    if (row["fee_case"] == "base_assumed" and row["funding_case"] == "current_hour_persists"
                            and row["terminal_gap_case"] == "zero_gap" and row["cash_rate"] == 0.04
                            and row["exit_spread_multiplier"] == 1):
                        print(f"  {row['holding_days']}d ZERO-GAP SCENARIO: net ${row['net_pnl_usd']:.2f}; excess vs cash ${row['excess_over_cash_usd']:.2f}")
        print(f"Snapshot: {directory.resolve()}")
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(f"SPREAD FEASIBILITY DATA ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
