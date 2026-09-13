"""Offline arithmetic for one public quote packet; no network or trading."""
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from us_crypto_carry import read_book, timestamp, vwap, futures_fee


def main():
    policy = json.loads((HERE / "policy.json").read_text())
    manifest = json.loads((HERE / "manifest.json").read_text())
    selection = json.loads((HERE / "selection.json").read_text())
    rawdir = ROOT / "data/us_crypto/dated-screen-2026-09-10"
    assert hashlib.sha256((HERE / "policy.json").read_bytes()).hexdigest() == manifest["policy_sha256"]
    payloads = {}
    for name, meta in manifest["sources"].items():
        raw = (rawdir / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == meta["sha256"], name
        payloads[name] = json.loads(raw)
    assets, rows = [], []
    cases = list(zip(policy["cost_scenarios_paired_not_grid"], policy["spot_fee_bps_per_side"],
                     policy["dated_future_fee_bps_per_side"], policy["dated_future_fee_min_usd_per_contract"]))
    for asset, product in selection["selected"].items():
        d = product["future_product_details"]
        assert product in payloads["products.json"]["products"]
        assert d.get("funding_interval") in (None, "") and d.get("funding_rate") in (None, "")
        spotmeta = payloads[asset + "-spot-product.json"]
        assert spotmeta["product_id"] == asset + "-USD"
        for flag in ("is_disabled", "trading_disabled", "view_only", "post_only", "limit_only", "cancel_only", "auction_mode"):
            assert spotmeta[flag] is False, (asset, flag)
        books = {}
        for leg, pid in (("spot", asset + "-USD"), ("future", product["product_id"])):
            name = asset + "-" + leg + "-book.json"
            books[leg] = read_book(payloads[name], pid, manifest["sources"][name]["received_at"],
                                   policy["max_book_age_seconds"])
        skew = abs((timestamp(books["spot"]["time"]) - timestamp(books["future"]["time"])).total_seconds())
        assert skew <= policy["max_pair_skew_seconds"]
        asof = max(timestamp(manifest["sources"][asset + "-" + leg + "-book.json"]["received_at"])
                   for leg in ("spot", "future"))
        days = (timestamp(d["contract_expiry"]) - asof).total_seconds() / 86400
        assert days >= policy["min_hours_to_expiry"] / 24
        size, margin = float(d["contract_size"]), float(d["overnight_margin_rate"]["short_margin_rate"])
        sa0, fb0, fa0 = books["spot"]["asks"][0][0], books["future"]["bids"][0][0], books["future"]["asks"][0][0]
        assets.append({"asset": asset, "future": product["product_id"], "expiry": d["contract_expiry"],
                       "observed_at": asof.isoformat(), "days_to_expiry": days, "contract_size": size,
                       "short_overnight_margin_rate": margin, "spot_best_ask": books["spot"]["asks"][0],
                       "future_best_bid": books["future"]["bids"][0], "future_best_ask": books["future"]["asks"][0],
                       "book_skew_seconds": skew, "book_age_seconds": {k: v["age_seconds"] for k,v in books.items()},
                       "fee_free_best_level_simple_annual_basis_on_spot": (fb0-sa0)/sa0*365/days,
                       "auxiliary_fee_free_no_reserve_fractional_margin_only_annual_return":
                           (fb0-sa0)/(sa0+margin*fa0)*365/days})
        for capital in policy["capital_usd"]:
            chosen = None
            upper = math.floor(capital*policy["max_leg_fraction"]/(size*max(sa0, fb0)))
            for n in range(upper, 0, -1):
                q = n*size
                try:
                    sa, fb, fa = vwap(books["spot"]["asks"], q), vwap(books["future"]["bids"], n), vwap(books["future"]["asks"], n)
                except ValueError:
                    continue
                spot, future = q*sa, q*fb
                entry_fee = spot*cases[-1][1]/10000 + futures_fee(n,size,fb,cases[-1][2],cases[-1][3])
                initial_margin = q*fa*margin
                free = capital-spot-entry_fee-initial_margin
                if max(spot,future) <= capital*policy["max_leg_fraction"] and free >= capital*policy["min_initial_free_cash_fraction"]:
                    chosen = n,q,sa,fb,fa,spot,entry_fee,initial_margin,free
                    break
            if chosen is None:
                rows.append({"asset":asset,"capital_usd":capital,"status":"NO_FEASIBLE_SIZE"})
                continue
            n,q,sa,fb,fa,spot,entry_fee,initial_margin,free = chosen
            gross = q*(fb-sa)
            liquidity = []
            for name, rise, basis, mult in (("price_rise_current_margin",.5,0,1),
                                           ("price_rise_double_margin",.5,0,2),
                                           ("price_rise_double_margin_extra_basis",.5,.05,2)):
                fs = fb+(rise+basis)*sa
                vm = q*(fs-fb)
                stressed_margin = q*fs*margin*mult
                liquidity.append({"name":name,"stressed_future_price":fs,"variation_margin_outflow":vm,
                                  "required_margin":stressed_margin,"cash_headroom":capital-spot-entry_fee-vm-stressed_margin,
                                  "spot_gain_not_available_for_margin":spot*rise,
                                  "hedge_mark_loss_from_added_basis":spot*basis})
            fee_rows = []
            for name,sbps,fbps,fmin in cases:
                sf = 2*spot*sbps/10000
                ff = 2*futures_fee(n,size,fb,fbps,fmin)
                mismatches = [{"bps":bps,"allowance_usd":spot*bps/10000,
                               "net_usd":gross-sf-ff-spot*bps/10000} for bps in policy["adverse_exit_mismatch_bps"]]
                fee_rows.append({"case":name,"spot_fee_bps_each_side":sbps,"future_fee_bps_each_side":fbps,
                                 "future_min_per_contract_each_side":fmin,"spot_round_trip_fee":sf,
                                 "future_entry_plus_exit_fee_budget":ff,"net_perfect_match":gross-sf-ff,
                                 "mismatch_scenarios":mismatches})
            cash = {str(rate):capital*rate*days/365 for rate in policy["cash_rates"]}
            rows.append({"asset":asset,"capital_usd":capital,"contracts":n,"quantity":q,
                         "spot_buy_vwap":sa,"future_sell_vwap":fb,"future_buyback_mark_vwap":fa,
                         "spot_cost":spot,"entry_fee_stress":entry_fee,"initial_margin":initial_margin,
                         "free_cash_after_initial_margin_and_stress_entry_fee":free,
                         "zero_fee_perfect_match_capture":gross,"zero_fee_simple_annual_return_on_all_capital":gross/capital*365/days,
                         "cash_hurdles":cash,"total_cost_budget_to_beat_cash":{k:gross-v for k,v in cash.items()},
                         "fees":fee_rows,"liquidity_scenarios":liquidity,
                         "status":"REJECT_SAMPLED_ENTRY" if gross < cash["0.06"] else "REQUIRES_COST_AND_RISK_REVIEW"})
    out={"schema":"dated-cash-carry-single-packet-v1","policy_sha256":manifest["policy_sha256"],
         "analysis_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"assets":assets,"rows":rows,
         "cash_stress_convention":"F_stress=F_entry+(price_rise+additional_basis_fraction)*S_entry; stress entry fees already paid; unsold spot gains unavailable",
         "fee_scenarios":"unchanged entry prices used only for fee budget; future closing/expiry budget counted once; actual fees and terminal spot price unknown",
         "interpretation":"One synchronized displayed-book packet, not fills, a backtest or expected annual return. Perfect settlement match is a reference, not an absolute bound when mismatch is nonzero.",
         "account_eligibility":"unverified","paid_data_cost_usd":0}
    (HERE/"result.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps({"assets":assets,"rows":[{k:v for k,v in r.items() if k not in ('fees','liquidity_scenarios')} for r in rows]},indent=2))


if __name__ == "__main__":
    main()
