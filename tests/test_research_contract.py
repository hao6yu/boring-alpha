"""Frozen behavior identity is neither mutable prose nor authorization."""

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from boring_alpha.criteria_ba002 import evaluate_period
from boring_alpha.period_evidence import build_period_evidence
from boring_alpha.research_contract import (
    SYMBOLS, canonical_sha256, contract_sha256, load_contract,
    require_approved_contract, validate_contract,
)
from test_criteria_ba002 import evidence_inputs


def historical_contract():
    contract = evidence_inputs()["contract"]
    contract["synthetic"] = False
    contract["data_methodology"] = "yahoo-adjusted-v2+dgs3mo-v1"
    contract["periods"]["sealed"] = {"start": "2014-01-01", "end": "2015-12-31", "status": "unopened"}
    contract["tax_policy"] = {
        "ordinary_rate": 0.35, "long_term_rate": 0.2, "collectibles_rate": 0.28,
        "qualified_fraction_low": 0.5,
        "qualified_fraction": {symbol: 0.0 for symbol in SYMBOLS},
        "gains_class": {symbol: "collectibles" if symbol == "GLD" else "commodity_pool" if symbol == "DBC" else "standard" for symbol in SYMBOLS},
    }
    contract["tax_policy_sha256"] = canonical_sha256(contract["tax_policy"])
    return contract


def test_contract_key_order_and_formatting_are_not_identity(tmp_path):
    original = evidence_inputs()["contract"]
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(dict(reversed(list(original.items()))), indent=4))
    assert contract_sha256(load_contract(path)) == contract_sha256(original)


def test_validator_detaches_source_data():
    original = evidence_inputs()["contract"]
    selected = validate_contract(original)
    original["grid"]["base"]["cost_bps"] = 0
    assert selected["grid"]["base"]["cost_bps"] == 10


@pytest.mark.parametrize("change", ["symbol", "weight", "grid", "warmup", "cost", "benchmark_cost", "benchmark", "capital", "threshold", "scenario", "period_status", "overlap", "dataset_end", "family", "boolean_number", "unknown_field", "missing_hash"])
def test_behavior_changes_require_a_different_reviewed_design(change):
    contract = evidence_inputs()["contract"]
    if change == "symbol": contract["symbols"][0] = "QQQ"
    elif change == "weight": contract["rule"]["sleeve_weight"] = 0.2
    elif change == "grid": contract["grid"].pop("without_9")
    elif change == "warmup": contract["grid"]["without_15"]["warmup_months"] = 12
    elif change == "cost": contract["grid"]["base"]["cost_bps"] = 0
    elif change == "benchmark_cost": contract["grid"]["double_cost"]["benchmark"]["cost_bps"] = 10
    elif change == "benchmark": contract["benchmark"]["rebalance"] = "monthly"
    elif change == "capital": contract["initial_cash"] = 5000
    elif change == "threshold": contract["criteria"]["primary_margin_min"] = 0.004
    elif change == "scenario": contract["scenarios"].pop()
    elif change == "period_status": contract["periods"]["validation"]["status"] = "unseen"
    elif change == "overlap": contract["periods"]["validation"]["start"] = "2011-01-01"
    elif change == "dataset_end": contract["periods"]["validation"]["end"] = "dataset"
    elif change == "family": contract["family_id"] = "FRESH-HOLDOUT"
    elif change == "boolean_number": contract["criteria"]["stress_margin_exclusive_min"] = False
    elif change == "unknown_field": contract["git_commit"] = "docs-changing-hash"
    elif change == "missing_hash": contract.pop("calendar_authority_sha256")
    with pytest.raises(ValueError):
        validate_contract(contract)


def test_synthetic_contract_cannot_authorize_history_even_if_both_copies_match():
    contract = evidence_inputs()["contract"]
    with pytest.raises(ValueError, match="synthetic"):
        require_approved_contract(contract, deepcopy(contract))


def test_historical_contract_needs_independent_freeze():
    with pytest.raises(ValueError, match="independently approved"):
        require_approved_contract(historical_contract(), None)


def test_matching_historical_contract_is_a_pure_comparison_not_a_record_write():
    contract = historical_contract()
    assert require_approved_contract(contract, deepcopy(contract)) is None


def test_changed_historical_period_cannot_match_approved_freeze():
    approved = historical_contract()
    changed = deepcopy(approved)
    changed["periods"]["development"]["start"] = "2010-02-01"
    with pytest.raises(ValueError, match="freeze"):
        require_approved_contract(changed, approved)


def test_full_historical_tax_policy_is_required():
    contract = historical_contract()
    contract.pop("tax_policy")
    with pytest.raises(ValueError, match="complete tax_policy"):
        validate_contract(contract)


def test_policy_contents_must_match_its_hash():
    contract = historical_contract()
    contract["tax_policy"]["ordinary_rate"] = 0.37
    with pytest.raises(ValueError, match="tax policy contents"):
        validate_contract(contract)


@pytest.mark.parametrize("change", ["missing_rate", "infinite_rate", "boolean_rate", "missing_symbol", "wrong_class", "excess_collectibles"])
def test_even_self_consistent_policy_hash_does_not_validate_invalid_policy(change):
    contract = historical_contract()
    policy = contract["tax_policy"]
    if change == "missing_rate": policy.pop("ordinary_rate")
    elif change == "infinite_rate": policy["ordinary_rate"] = float("inf")
    elif change == "boolean_rate": policy["ordinary_rate"] = True
    elif change == "missing_symbol": policy["qualified_fraction"].pop("GLD")
    elif change == "wrong_class": policy["gains_class"]["GLD"] = "standard"
    elif change == "excess_collectibles": policy["collectibles_rate"] = 0.5
    with pytest.raises(ValueError):
        contract["tax_policy_sha256"] = canonical_sha256(policy)
        validate_contract(contract)


@pytest.mark.parametrize("change", ["start", "status", "contract"])
def test_manually_changed_typed_period_cannot_bypass_contract(change):
    evidence = build_period_evidence(**evidence_inputs())
    if change == "start": evidence = replace(evidence, start="2010-02-01")
    elif change == "status": evidence = replace(evidence, evidence_status="seen")
    elif change == "contract": evidence = replace(evidence, contract_json="{}")
    with pytest.raises(ValueError):
        evaluate_period(evidence)
