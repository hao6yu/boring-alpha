#!/usr/bin/env python3
"""Read-only Coinbase US spot/futures feasibility screen (BA-009).

Collect public product metadata and order books, or reproduce a saved snapshot.
No credentials, private endpoints, order entry, or scheduled execution.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from fetch_market_data import _CONTEXT  # noqa: E402  verified OS CA fallback

API = "https://api.coinbase.com/api/v3/brokerage/market/"
SCHEMA = "us-crypto-carry-feasibility-v1"
FEE_FILE = ROOT / "research/us-crypto-fees-2026-09-09.json"
POLICY = {"capital_usd": 5000.0, "reserve_usd": 1000.0,
          "max_leg_fraction": 0.5, "margin_price_rise": 0.5,
          "holding_days": [7, 30, 90], "cash_rates": [0.04, 0.06],
          "max_book_age_seconds": 60, "idle_cash_yield": 0.0}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return parsed


def number(value, label: str, *, positive: bool = True) -> float:
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"invalid {label}")
    return result


def fetch(path: str) -> tuple[bytes, dict]:
    url = API + path
    started = utcnow()
    request = urllib.request.Request(url, headers={"User-Agent": "BoringAlpha-Research/0.1",
                                                   "Accept": "application/json"})
    with urllib.request.urlopen(request, context=_CONTEXT, timeout=15) as response:
        body = response.read()
        server_date = response.headers.get("Date")
    # Parse before publishing; an HTML response cannot masquerade as data.
    json.loads(body)
    return body, {"url": url, "started_at": started, "received_at": utcnow(),
                  "http_date": server_date, "bytes": len(body),
                  "sha256": hashlib.sha256(body).hexdigest()}


def select_contracts(products: list[dict]) -> dict[str, dict]:
    selected = {}
    for root in ("BTC", "ETH"):
        matches = []
        for product in products:
            details = product.get("future_product_details") or {}
            if (product.get("product_type") == "FUTURE" and product.get("product_venue") == "FCM"
                    and details.get("contract_root_unit") == root
                    and details.get("funding_interval") == "3600s"
                    and not product.get("trading_disabled") and not product.get("is_disabled")):
                matches.append(product)
        if len(matches) != 1:
            raise ValueError(f"expected exactly one active hourly-funded FCM {root} contract; got {len(matches)}")
        selected[root] = matches[0]
    return selected


def read_book(payload: dict, expected_id: str, received_at: str, max_age: float) -> dict:
    book = payload["pricebook"]
    if book["product_id"] != expected_id:
        raise ValueError("order-book product mismatch")
    age = (timestamp(received_at) - timestamp(book["time"])).total_seconds()
    if age < -5 or age > max_age:
        raise ValueError(f"stale or future order book for {expected_id}: {age:.1f}s")
    out = {"time": book["time"], "age_seconds": age}
    for side in ("bids", "asks"):
        levels = [(number(row["price"], "book price"), number(row["size"], "book size"))
                  for row in book[side]]
        if not levels:
            raise ValueError(f"empty {side} for {expected_id}")
        out[side] = sorted(levels, reverse=side == "bids")
    if out["bids"][0][0] >= out["asks"][0][0]:
        raise ValueError(f"locked/crossed book for {expected_id}")
    return out


def vwap(levels: list[tuple[float, float]], quantity: float) -> float:
    number(quantity, "requested quantity")
    remaining, total = quantity, 0.0
    for price, size in levels:
        take = min(remaining, size)
        total += take * price
        remaining -= take
        if remaining <= quantity * 1e-12:
            return total / quantity
    raise ValueError("insufficient displayed depth; cannot assume best-price fills")


def futures_fee(contracts: int, multiplier: float, price: float, bps: float, minimum: float) -> float:
    return contracts * max(multiplier * price * bps / 10000, minimum)


def screen_pair(root: str, product: dict, spot_book: dict, future_book: dict,
                fees: dict, policy: dict) -> dict:
    capital = number(policy["capital_usd"], "capital")
    details = product["future_product_details"]
    multiplier = number(details["contract_size"], "contract size")
    margin_rate = number(details["overnight_margin_rate"]["short_margin_rate"], "short overnight margin")
    rate = number(details["funding_rate"], "hourly funding", positive=False)
    # Empty nested perpetual_details.funding_rate is not the FCM funding field.
    funding_time = details["funding_time"]
    timestamp(funding_time)
    spot_fee = fees["coinbase_advanced_spot"]["base_scenario_bps"]
    future_fee = fees["coinbase_us_futures"]["base_scenario_bps"]
    minimum = fees["coinbase_us_futures"]["published_minimum_per_contract_usd"]
    max_contracts = math.floor(capital * policy["max_leg_fraction"] /
                               (multiplier * max(spot_book["asks"][0][0], future_book["asks"][0][0])))
    quote = None
    for count in range(max_contracts, 0, -1):
        quantity = count * multiplier
        try:
            sa = vwap(spot_book["asks"], quantity)
            sb = vwap(spot_book["bids"], quantity)
            fb = vwap(future_book["bids"], count)  # futures sizes are contracts
            fa = vwap(future_book["asks"], count)
        except ValueError:
            continue
        if quantity * max(sa, fa) > capital * policy["max_leg_fraction"]:
            continue
        entry_fee = quantity * sa * spot_fee / 10000 + futures_fee(count, multiplier, fb, future_fee, minimum)
        initial_margin = quantity * fa * margin_rate
        residual = capital - quantity * sa - entry_fee - initial_margin
        if residual >= policy["reserve_usd"]:
            quote = count, quantity, sa, sb, fb, fa, entry_fee, initial_margin, residual
            break
    if quote is None:
        return {"asset": root, "product_id": product["product_id"],
                "status": "NO_SIZE_WITHIN_BUDGET_AND_DISPLAYED_DEPTH"}
    count, quantity, sa, sb, fb, fa, entry_fee, initial_margin, residual = quote
    mid = (future_book["asks"][0][0] + future_book["bids"][0][0]) / 2
    notional = quantity * mid
    spread_cost = quantity * ((sa - sb) + (fa - fb))
    # No spot gains are assumed transferable into the futures account.
    rise = policy["margin_price_rise"]
    stressed_margin = quantity * fa * (1 + rise) * margin_rate
    variation_loss = notional * rise
    futures_cash = capital - quantity * sa - entry_fee
    stress_headroom = futures_cash - variation_loss - stressed_margin
    rows = []
    for spot_bps in fees["coinbase_advanced_spot"]["research_taker_bps"]:
        for future_bps in fees["coinbase_us_futures"]["research_bps"]:
            total_fees = quantity * (sa + sb) * spot_bps / 10000
            total_fees += futures_fee(count, multiplier, fb, future_bps, minimum)
            total_fees += futures_fee(count, multiplier, fa, future_bps, minimum)
            for days in policy["holding_days"]:
                funding = notional * rate * days * 24
                for cash_rate in policy["cash_rates"]:
                    cash_return = capital * cash_rate * days / 365
                    cost = total_fees + spread_cost
                    hurdle = (cost + cash_return) / (notional * days * 24)
                    rows.append({"spot_fee_bps": spot_bps, "futures_fee_bps": future_bps,
                                 "holding_days": days, "cash_rate": cash_rate,
                                 "round_trip_fees_usd": total_fees,
                                 "round_trip_spread_usd": spread_cost,
                                 "funding_if_current_rate_persists_usd": funding,
                                 "cash_benchmark_usd": cash_return,
                                 "net_if_rate_and_basis_unchanged_usd": funding - cost,
                                 "excess_over_cash_usd": funding - cost - cash_return,
                                 "required_hourly_funding_rate": hurdle,
                                 "required_simple_annual_funding_on_notional": hurdle * 24 * 365})
    return {"asset": root, "product_id": product["product_id"], "status": "SCENARIO_ONLY",
            "contracts": count, "underlying_quantity": quantity, "notional_per_leg_usd": notional,
            "spot_buy_vwap": sa, "spot_sell_vwap": sb, "futures_sell_vwap": fb, "futures_buy_vwap": fa,
            "funding_rate_reported": rate, "funding_time_reported": funding_time,
            "simple_annualized_snapshot_rate_on_notional": rate * 24 * 365,
            "overnight_short_margin_rate": margin_rate, "initial_margin_usd": initial_margin,
            "cash_beyond_initial_margin_usd": residual,
            "headroom_after_50pct_rise_at_current_margin_rate_usd": stress_headroom,
            "basis_widens_one_percent_loss_usd": notional * 0.01,
            "scenarios": rows}


def analyze(snapshot: Path) -> dict:
    manifest = json.loads((snapshot / "manifest.json").read_text())
    if manifest["schema"] != SCHEMA:
        raise ValueError("unrecognized snapshot schema")
    payloads = {}
    for name, source in manifest["sources"].items():
        if Path(name).name != name:
            raise ValueError("invalid snapshot filename")
        body = (snapshot / name).read_bytes()
        if hashlib.sha256(body).hexdigest() != source["sha256"]:
            raise ValueError(f"snapshot checksum mismatch: {name}")
        payloads[name] = json.loads(body)
    fees, policy = payloads["fees.json"], payloads["policy.json"]
    contracts = select_contracts(payloads["products.json"]["products"])
    out = []
    for root, product in contracts.items():
        books = {}
        for label, pid in (("spot", f"{root}-USD"), ("future", product["product_id"])):
            name = f"{root}-{label}-book.json"
            books[label] = read_book(payloads[name], pid, manifest["sources"][name]["received_at"],
                                     policy["max_book_age_seconds"])
        skew = abs((timestamp(books["spot"]["time"]) - timestamp(books["future"]["time"])).total_seconds())
        if skew > policy["max_book_age_seconds"]:
            raise ValueError(f"spot/futures books too far apart for {root}")
        details = product["future_product_details"]
        funding_age = (timestamp(manifest["sources"]["products.json"]["received_at"]) -
                       timestamp(details["funding_time"])).total_seconds()
        if not -3600 <= funding_age <= 7200:
            raise ValueError(f"stale or future funding metadata for {root}")
        if timestamp(details["contract_expiry"]) <= timestamp(manifest["started_at"]):
            raise ValueError(f"expired contract for {root}")
        row = screen_pair(root, product, books["spot"], books["future"], fees, policy)
        row["book_timestamp_skew_seconds"] = skew
        out.append(row)
    return {"schema": SCHEMA, "snapshot": str(snapshot.resolve()), "observed_at": manifest["finished_at"],
            "profitability_verdict": "NOT_ESTABLISHED", "policy": policy, "assets": out,
            "limitations": ["funding is one reported snapshot, not realized history or a forecast",
                            "fees include explicitly unverified sensitivity assumptions",
                            "entry and hypothetical exit use current depth; future fills and basis will differ",
                            "account eligibility unverified; margin rates can change",
                            "idle collateral yield is zero; taxes and operating overhead excluded",
                            "the 20% loss tolerance is not guaranteed by a hedge or margin scenario"]}


def collect(output: Path) -> Path:
    target = output / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target.mkdir(parents=True, exist_ok=False)
    sources = {}
    started = utcnow()

    def save(name, path):
        body, source = fetch(path)
        (target / name).write_bytes(body)
        sources[name] = source
        return json.loads(body)

    try:
        listing = save("products.json", "products?product_type=FUTURE&limit=100")
        selected = select_contracts(listing["products"])
        for root, product in selected.items():
            for label, pid in (("spot", f"{root}-USD"), ("future", product["product_id"])):
                query = urllib.parse.urlencode({"product_id": pid, "limit": 50})
                save(f"{root}-{label}-book.json", f"product_book?{query}")
        for name, body in (("fees.json", FEE_FILE.read_bytes()),
                           ("policy.json", json.dumps(POLICY, sort_keys=True).encode())):
            (target / name).write_bytes(body)
            sources[name] = {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
        manifest = {"schema": SCHEMA, "started_at": started, "finished_at": utcnow(),
                    "sources": sources, "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "listing_scope": "returned first page; exact BTC/ETH pair required, not a full-market census"}
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    except Exception as exc:
        (target / "failure.json").write_text(json.dumps({"error": str(exc), "sources": sources,
                                                        "failed_at": utcnow()}, indent=2) + "\n")
        raise
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="recompute a saved snapshot offline")
    parser.add_argument("--out", type=Path, default=ROOT / "data/us_crypto/snapshots")
    args = parser.parse_args()
    try:
        snapshot = args.snapshot or collect(args.out)
        report = analyze(snapshot)
        if args.snapshot is None:
            (snapshot / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
        print(f"BA-009: {report['profitability_verdict']} — snapshot scenarios, not a backtest")
        for asset in report["assets"]:
            if asset["status"] != "SCENARIO_ONLY":
                print(f"{asset['asset']}: {asset['status']}")
                continue
            base = next(row for row in asset["scenarios"] if row["spot_fee_bps"] == 120
                        and row["futures_fee_bps"] == 5 and row["holding_days"] == 30 and row["cash_rate"] == 0.04)
            print(f"{asset['asset']}: {asset['contracts']} contracts; ${asset['notional_per_leg_usd']:.2f}/leg; "
                  f"30-day excess vs 4% cash if current funding/basis persist: ${base['excess_over_cash_usd']:.2f}; "
                  f"funding hurdle {base['required_simple_annual_funding_on_notional']:.1%}/yr on notional")
        print(f"Snapshot: {snapshot.resolve()}")
        print("No account access or orders. Fee assumptions and all sensitivity rows are in report.json.")
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(f"FEASIBILITY DATA ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
