#!/usr/bin/env python3
"""Reproduce BA-012's static bounds without reading prices or making requests.

Writes research/ba012-stage-a/static-constraint-bounds.json. Use --check to
verify the existing artifact without changing it. This is fixed arithmetic,
not a signal, volatility estimator, trading engine, or return backtest.
"""
from __future__ import annotations

import argparse
from decimal import Decimal as D
import hashlib
from itertools import product
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/ba012-stage-a/static-constraint-bounds.json"
PROTOCOL_SHA256 = "095fa832c82645a6f570668813b59b08afa4a21c93466980703ff78c46eec67f"
SYMBOLS = ["NES", "MTN", "M6E", "1OZ", "MZC"]
GROUPS = ["equities", "rates", "fx", "commodities", "commodities"]
SHOCK = list(map(D, ["200", "200", "250", "200", "200"]))
EXECUTION = list(map(D, ["1.11", "3.685", "2.90", "1.16", "5.76"]))
INITIAL_LONG = list(map(D, ["324.1225", "710.681", "329.442", "459.689", "206.92"]))
INITIAL_SHORT = list(map(D, ["298.78", "751.28", "334.442", "464.189", "234.42"]))


def verified_protocol_hash() -> str:
    actual = hashlib.sha256((ROOT / "docs/strategies/BA-012.md").read_bytes()).hexdigest()
    freeze = json.loads((ROOT / "research/ba012-protocol-v1-freeze.json").read_text())
    if actual != PROTOCOL_SHA256 or freeze["canonical_protocol"]["sha256"] != actual:
        raise SystemExit("Frozen BA-012 version 1 checksum mismatch; no output written")
    return actual


def dot(quantity, values):
    return sum(n * value for n, value in zip(quantity, values))


def build_diagnostic(protocol_hash: str) -> dict:
    low = [min(a, b) for a, b in zip(INITIAL_LONG, INITIAL_SHORT)]
    high = [max(a, b) for a, b in zip(INITIAL_LONG, INITIAL_SHORT)]
    charges = [shock + 2 * cost for shock, cost in zip(SHOCK, EXECUTION)]
    capital_bounds = []
    for capital in map(D, [5000, 25000, 100000]):
        budget, tau = capital * D(".2"), capital * D(".08")
        capital_bounds.append({
            "capital_usd": str(capital),
            "stage_a_simulated_loss_budget_usd": str(budget),
            "annual_dollar_vol_cap_usd": str(tau),
            "frozen_diagonal_sum_rejection_threshold": str(2 * tau * tau),
            "stress_only_total_contract_upper_bound": int(budget / min(charges)),
            "stress_only_per_market_quantity_upper_bounds": [int(budget / x) for x in charges],
        })

    # Four total contracts at most, and at least three markets: each quantity
    # is at most two. Enumerate only that small, proven superset for the pilot.
    patterns = []
    for quantity in product(range(3), repeat=5):
        if not 3 <= sum(quantity) <= 4:
            continue
        if len({group for group, n in zip(GROUPS, quantity) if n}) < 3:
            continue
        charge = dot(quantity, charges)
        if charge > D(1000):
            continue
        low_capital = charge + 2 * dot(quantity, low) + D(100)
        high_capital = charge + 2 * dot(quantity, high) + D(100)
        status = ("passes_all_signs" if high_capital <= 5000 else
                  "sign_dependent" if low_capital <= 5000 else "fails_all_signs")
        patterns.append({
            "absolute_quantities": list(quantity),
            "stress_entry_exit_charge_usd": str(charge),
            "required_capital_best_initial_sides_usd": str(low_capital),
            "required_capital_worst_initial_sides_usd": str(high_capital),
            "margin_status": status,
        })
    counts = {label: sum(p["margin_status"] == label for p in patterns)
              for label in ("passes_all_signs", "sign_dependent", "fails_all_signs")}
    witness = [1, 0, 1, 0, 1]
    charge = dot(witness, charges)
    return {
        "diagnostic_type": "static_constraint_arithmetic_only_not_stage_a_price_test",
        "protocol_sha256": protocol_hash,
        "freeze_sha256_verified": True,
        "historical_data_read": False,
        "strategy_returns_calculated": False,
        "volatility_estimated": False,
        "scope": "Fresh cash entries only; 20% simulated loss budgets for larger virtual capitals as frozen; static counts omit measured volatility, target tracking, nonzero monthly signals, and volatility concentration. Static margin costs monotone in partial fills, so full-entry pass covers partial states for margin/stress only.",
        "symbols": SYMBOLS,
        "entry_plus_stress_plus_exit_per_contract_usd": [str(x) for x in charges],
        "capital_bounds": capital_bounds,
        "pilot_pattern_counts": {"stress_and_three_group_patterns": len(patterns), **counts},
        "pilot_patterns": patterns,
        "static_witness": {
            "absolute_quantities": witness,
            "groups": ["equities", "fx", "commodities"],
            "stress_price_loss_usd": "650",
            "entry_plus_exit_cost_usd": str(charge - D(650)),
            "total_loss_budget_charge_usd": str(charge),
            "worst_side_initial_margin_usd": str(dot(witness, high)),
            "required_capital_worst_sides_including_2x_initial_stress_costs_and_100_reserve_usd": str(charge + 2 * dot(witness, high) + 100),
            "required_capital_best_sides_usd": str(charge + 2 * dot(witness, low) + 100),
            "statement": "This proves no contradiction among fixed cost/stress/group-count/margin rules. It does not establish measured volatility/concentration or target tracking feasibility.",
        },
        "necessary_tests": [
            "At least three asset groups must contain eligible, nonzero-signal instruments.",
            "Every selected sleeve must satisfy abs(q_i)*v_i <= tau because that sleeve alone is a possible partial-fill state from cash.",
            "If fewer than three groups contain an instrument with v_i <= tau, all nonzero entries are impossible.",
            "For the cheapest-in-volatility representative of each eligible group, sum the three smallest squared annual dollar volatilities. If the sum exceeds 2*tau^2, the frozen shrinkage lower bound proves infeasibility.",
            "Final concentration requires max(abs(q_i)*v_i) <= sum(abs(q_i)*v_i)/2. For three one-unit markets this is the triangle inequality on their v_i.",
            "Every subset of a from-cash integer basket is a possible fill state; test its full covariance risk, not merely the completed portfolio. For a positive semidefinite covariance, maximum variance over the quantity box occurs at a vertex, so all 2^k sleeve-empty/full vertices suffice for the volatility check at fixed E and covariance. Costs/equity re-marking need their own stated treatment.",
            "From-cash quantities have cheap bounds from stress, single-sleeve margin, and partial-fill volatility; passing any bound is not a Stage A pass.",
        ],
        "exact_blockers": [
            "A five-market one-contract-each entry costs 1079.230 USD of stipulated stress plus entry and exit reserve, exceeding the pilot 1000 USD budget regardless of signs or covariance.",
            "Pilot total quantity is at most four contracts; with at least three active markets, no market can exceed two contracts.",
            "Fixed constraints alone do not prove the pilot infeasible; measured 252-session dollar risk remains required.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check the saved artifact without writing")
    args = parser.parse_args()
    report = build_diagnostic(verified_protocol_hash())
    rendered = json.dumps(report, indent=2) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != rendered:
            raise SystemExit("Static diagnostic differs or is missing; no output written")
        action = "verified_exact_output"
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(rendered)
        action = "wrote_output"
    print(json.dumps({"status": action, "path": str(OUTPUT),
                      "pilot_pattern_counts": report["pilot_pattern_counts"]}))


if __name__ == "__main__":
    main()
