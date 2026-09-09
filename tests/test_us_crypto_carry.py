"""Cash-budget, fee-unit, depth, and snapshot-integrity checks for BA-009."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import us_crypto_carry as carry

TIME = "2026-09-09T23:30:00+00:00"


def product(root="BTC"):
    return {"product_id": root + "-US-PERP", "product_type": "FUTURE", "product_venue": "FCM",
            "future_product_details": {"contract_root_unit": root, "contract_size": "1",
                                       "contract_expiry_type": "EXPIRING", "funding_interval": "3600s",
                                       "funding_rate": "0.00001", "funding_time": TIME,
                                       "contract_expiry": "2030-12-20T16:00:00Z",
                                       "overnight_margin_rate": {"short_margin_rate": "0.3"}}}


def fees():
    return json.loads(carry.FEE_FILE.read_text())


def book(pid, bid=99, ask=101):
    return {"pricebook": {"product_id": pid, "time": TIME,
                          "bids": [{"price": str(bid), "size": "10000"}],
                          "asks": [{"price": str(ask), "size": "10000"}]}}


def test_fcm_perpetual_style_is_selected_despite_expiring_enum():
    foreign = deepcopy(product())
    foreign["product_venue"] = "INTX"
    assert set(carry.select_contracts([foreign, product(), product("ETH")])) == {"BTC", "ETH"}


def test_ambiguous_contracts_fail_instead_of_selecting_best_funding():
    with pytest.raises(ValueError, match="exactly one"):
        carry.select_contracts([product(), product(), product("ETH")])


def test_depth_walk_uses_contract_quantities_and_refuses_insufficient_depth():
    assert carry.vwap([(105, 2), (100, 3)], 5) == 102
    with pytest.raises(ValueError, match="insufficient"):
        carry.vwap([(105, 2), (100, 3)], 6)


def test_futures_fee_floor_is_a_maximum_not_an_added_fee():
    assert carry.futures_fee(1, 0.01, 100000, 2, 0.15) == pytest.approx(0.2)
    assert carry.futures_fee(1, 0.01, 10000, 2, 0.15) == 0.15
    assert carry.futures_fee(3, 0.01, 10000, 2, 0.15) == pytest.approx(0.45)


def test_flat_price_cash_hurdle_includes_both_legs_both_directions_and_full_capital():
    # Isolate fees with flat prices: 25 contracts of 1 unit at $100.
    flat = {"bids": [(100, 10000)], "asks": [(100, 10000)]}
    result = carry.screen_pair("BTC", product(), flat, flat, fees(), carry.POLICY)
    assert result["contracts"] == 25
    row = next(r for r in result["scenarios"] if r["spot_fee_bps"] == 120
               and r["futures_fee_bps"] == 5 and r["holding_days"] == 30 and r["cash_rate"] == 0.04)
    # Spot: 2 * $2500 * 1.2% = $60. Futures: 2 * 25 * $0.15 = $7.50.
    assert row["round_trip_fees_usd"] == pytest.approx(67.5)
    assert row["funding_if_current_rate_persists_usd"] == pytest.approx(18)
    assert row["cash_benchmark_usd"] == pytest.approx(5000 * 0.04 * 30 / 365)
    assert row["net_if_rate_and_basis_unchanged_usd"] == pytest.approx(-49.5)
    assert result["headroom_after_50pct_rise_at_current_margin_rate_usd"] == pytest.approx(91.25)


def test_negative_funding_is_a_cost_not_income_to_the_short_hedge():
    p = product()
    p["future_product_details"]["funding_rate"] = "-0.00001"
    flat = {"bids": [(100, 10000)], "asks": [(100, 10000)]}
    result = carry.screen_pair("BTC", p, flat, flat, fees(), carry.POLICY)
    assert all(row["funding_if_current_rate_persists_usd"] < 0 for row in result["scenarios"])


def test_insufficient_budget_cannot_round_up_to_one_contract():
    p = product()
    p["future_product_details"]["contract_size"] = "100"
    flat = {"bids": [(100, 10000)], "asks": [(100, 10000)]}
    result = carry.screen_pair("BTC", p, flat, flat, fees(), carry.POLICY)
    assert result["status"] == "NO_SIZE_WITHIN_BUDGET_AND_DISPLAYED_DEPTH"


def test_stale_crossed_or_wrong_product_books_fail():
    with pytest.raises(ValueError, match="stale"):
        carry.read_book(book("BTC-USD"), "BTC-USD", "2026-09-09T23:32:00Z", 60)
    with pytest.raises(ValueError, match="crossed"):
        carry.read_book(book("BTC-USD", 102, 101), "BTC-USD", TIME, 60)
    with pytest.raises(ValueError, match="mismatch"):
        carry.read_book(book("BTC-USD"), "ETH-USD", TIME, 60)


def write_snapshot(path):
    sources = {}
    payloads = {"products.json": {"products": [product(), product("ETH")]},
                "fees.json": fees(), "policy.json": carry.POLICY}
    for root in ("BTC", "ETH"):
        payloads[f"{root}-spot-book.json"] = book(root + "-USD")
        payloads[f"{root}-future-book.json"] = book(root + "-US-PERP")
    for name, payload in payloads.items():
        data = json.dumps(payload).encode()
        (path / name).write_bytes(data)
        sources[name] = {"sha256": hashlib.sha256(data).hexdigest(), "received_at": TIME}
    (path / "manifest.json").write_text(json.dumps({"schema": carry.SCHEMA, "sources": sources,
                                                   "started_at": TIME, "finished_at": TIME}))


def test_offline_snapshot_reproduces_and_tampering_fails(tmp_path):
    write_snapshot(tmp_path)
    report = carry.analyze(tmp_path)
    assert report == carry.analyze(tmp_path)
    assert report["profitability_verdict"] == "NOT_ESTABLISHED"
    assert len(report["assets"]) == 2
    (tmp_path / "fees.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        carry.analyze(tmp_path)
