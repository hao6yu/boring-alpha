"""Independent dollar examples for BA-009B, plus data-integrity boundaries."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import us_futures_spread as spread

TIME = "2026-09-09T23:30:00+00:00"


def policy():
    out = json.loads(spread.POLICY_FILE.read_text())
    # Isolate percentage fees for $100 synthetic contracts, without a floor.
    for case in out["fee_cases"]:
        case["perp_min_usd"] = case["dated_min_usd"] = 0
    return out


def pair(root="BTC"):
    common = {"product_type": "FUTURE", "product_venue": "FCM", "quote_currency_id": "USD",
              "fcm_trading_session_details": {"is_session_open": True},
              **{key: False for key in ("is_disabled", "trading_disabled", "cancel_only", "view_only", "post_only", "auction_mode")}}
    result = {}
    for leg in ("perp", "dated"):
        result[leg] = {**deepcopy(common), "product_id": root + "-" + leg,
                       "future_product_details": {"contract_root_unit": root, "contract_size": "1",
                           "contract_expiry": "2030-12-20T16:00:00Z" if leg == "perp" else "2026-09-25T15:00:00Z",
                           "funding_interval": "3600s" if leg == "perp" else None,
                           "funding_rate": "0.00001" if leg == "perp" else "", "funding_time": TIME,
                           "overnight_margin_rate": {"long_margin_rate": "0.2", "short_margin_rate": "0.3"}}}
    return result


def books(bid=100, ask=100):
    return {leg: {"bids": [(bid, 1000)], "asks": [(ask, 1000)]} for leg in ("perp", "dated")}


def row(result, **criteria):
    criteria = {"holding_days": 14, "fee_case": "base_assumed", "funding_case": "annual_0.1",
                "terminal_gap_case": "zero_gap", "cash_rate": 0.04, "exit_spread_multiplier": 1, **criteria}
    return next(r for r in result["scenarios"] if all(r[k] == v for k, v in criteria.items()))


def test_hand_calculated_fixed_quantity_profit_and_funding_sign():
    # Long 10 @100 ->110 earns100; short10 @102 ->111 loses90.
    assert spread.spread_pnl(10, 100, 102, 110, 111, 2, 3) == 5
    assert spread.spread_pnl(10, 100, 102, 110, 111, -2, 3) == 9


def test_four_fills_full_capital_cash_and_signed_funding_hurdle():
    result = spread.screen_pair("BTC", pair(), books(), policy(), TIME)
    r = row(result)
    assert result["contracts_each_leg"] == 25
    assert result["initial_gross_notional_usd"] == 5000
    assert r["round_trip_fees_usd"] == pytest.approx(5)  # 4 x $2500 x .0005
    assert r["funding_paid_usd"] == pytest.approx(2500 * 0.1 * 14 / 365)
    assert r["cash_benchmark_usd"] == pytest.approx(5000 * 0.04 * 14 / 365)
    assert r["excess_over_cash_usd"] == pytest.approx(-22.26027397260274)
    assert r["return_on_full_capital"] == pytest.approx(r["net_pnl_usd"] / 5000)
    assert r["required_mid_gap_narrowing_at_scenario_fees_usd_per_unit"] == pytest.approx(22.26027397260274 / 25)
    assert row(result, funding_case="annual_-0.1")["funding_paid_usd"] < 0


def test_spread_paid_once_and_double_exit_width_adds_half_roundtrip_cost():
    p = policy()
    for case in p["fee_cases"]:
        case["perp_bps"] = case["dated_bps"] = 0
    result = spread.screen_pair("BTC", pair(), books(99, 101), p, TIME)
    r = row(result, funding_case="annual_0", terminal_gap_case="unchanged")
    assert result["contracts_each_leg"] == 24
    assert r["round_trip_spread_usd"] == 96  # 24 x ($2 + $2)
    assert r["net_pnl_usd"] == -96
    doubled = row(result, funding_case="annual_0", terminal_gap_case="unchanged", exit_spread_multiplier=2)
    assert doubled["net_pnl_usd"] == -144


def test_dated_fee_is_independent_from_perp_fee():
    p = policy()
    result = spread.screen_pair("BTC", pair(), books(), p, TIME)
    p["fee_cases"][1]["dated_bps"] = 10
    changed = spread.screen_pair("BTC", pair(), books(), p, TIME)
    assert row(changed)["round_trip_fees_usd"] - row(result)["round_trip_fees_usd"] == pytest.approx(2.5)


def test_reserve_counts_immediate_spread_mark_loss():
    p = policy()
    p["reserve_usd"] = 3500
    for case in p["fee_cases"]:
        case["perp_bps"] = case["dated_bps"] = 0
    result = spread.screen_pair("BTC", pair(), books(90, 110), p, TIME)
    assert result["contracts_each_leg"] == 20  # 22 would pass cash-only reserve but fail marked equity
    assert result["initial_equity_beyond_margin_usd"] == pytest.approx(3500)


def test_common_market_move_nets_gains_without_assuming_margin_credit():
    result = spread.screen_pair("BTC", pair(), books(), policy(), TIME)
    assert result["initial_margin_no_offset_usd"] == pytest.approx(1250)
    # Equity is $4997.50 after entry fees; margin at 1.5x prices and 1.5x rates = $2812.50.
    assert result["stress"]["common_rise_and_margin_increase_headroom_usd"] == pytest.approx(2185)


def test_expiry_buffer_omits_unsupported_holding_periods():
    products = pair()
    products["dated"]["future_product_details"]["contract_expiry"] = "2026-09-18T23:30:00Z"
    result = spread.screen_pair("BTC", products, books(), policy(), TIME)
    assert result["excluded_holding_days"] == [14]
    assert {r["holding_days"] for r in result["scenarios"]} == {1, 7}


def test_unequal_multipliers_and_insufficient_capital_cannot_round_into_a_hedge():
    products = pair()
    products["dated"]["future_product_details"]["contract_size"] = "0.1"
    with pytest.raises(ValueError, match="multipliers"):
        spread.screen_pair("BTC", products, books(), policy(), TIME)
    for product in products.values():
        product["future_product_details"]["contract_size"] = "100"
    assert spread.screen_pair("BTC", products, books(), policy(), TIME)["status"] == "NO_SIZE_WITHIN_BUDGET_AND_DEPTH"


def test_view_only_and_closed_markets_are_excluded():
    btc, eth = pair(), pair("ETH")
    far = deepcopy(btc["dated"])
    far["product_id"], far["view_only"] = "BTC-far", True
    pairs, excluded = spread.select_pairs([*btc.values(), *eth.values(), far], TIME, 48)
    assert pairs["BTC"]["dated"]["product_id"] == "BTC-dated"
    assert excluded[0]["product_id"] == "BTC-far"
    btc["dated"]["fcm_trading_session_details"]["is_session_open"] = False
    with pytest.raises(ValueError, match="BTC"):
        spread.select_pairs([*btc.values(), *eth.values()], TIME, 48)


def snapshot(path):
    products = [p for root in ("BTC", "ETH") for p in pair(root).values()]
    payloads = {"products.json": {"products": products}, "policy.json": policy()}
    for root in ("BTC", "ETH"):
        for leg in ("perp", "dated"):
            payloads[f"{root}-{leg}-book.json"] = {"pricebook": {"product_id": root + "-" + leg, "time": TIME,
                "bids": [{"price": "99", "size": "1000"}], "asks": [{"price": "101", "size": "1000"}]}}
    sources = {}
    for name, payload in payloads.items():
        data = json.dumps(payload).encode()
        (path / name).write_bytes(data)
        sources[name] = {"sha256": hashlib.sha256(data).hexdigest(), "received_at": TIME}
    manifest = {"schema": spread.SCHEMA, "sources": sources, "started_at": TIME, "finished_at": TIME}
    (path / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_offline_replay_and_input_tampering(tmp_path):
    snapshot(tmp_path)
    a = spread.analyze(tmp_path)
    assert a == spread.analyze(tmp_path)
    assert a["profitability_verdict"] == "NOT_ESTABLISHED"
    (tmp_path / "policy.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        spread.analyze(tmp_path)


def test_pair_clock_skew_is_rejected_even_when_each_book_is_fresh(tmp_path):
    manifest = snapshot(tmp_path)
    path = tmp_path / "BTC-perp-book.json"
    payload = json.loads(path.read_text())
    payload["pricebook"]["time"] = "2026-09-09T23:29:57+00:00"
    data = json.dumps(payload).encode()
    path.write_bytes(data)
    manifest["sources"][path.name]["sha256"] = hashlib.sha256(data).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="skew"):
        spread.analyze(tmp_path)
