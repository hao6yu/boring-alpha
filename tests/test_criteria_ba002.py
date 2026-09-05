"""Adversarial, hand-numbered BA-002 economic and evidence tests."""

from copy import deepcopy
from decimal import Decimal

import pytest

from boring_alpha.criteria_ba002 import ResearchEligibility, classify, evaluate_period
from boring_alpha.period_evidence import build_period_evidence
from boring_alpha.research_contract import (
    build_contract, code_fingerprint, contract_sha256, evaluator_fingerprint,
    expected_account_map, expected_row_definitions,
)
from boring_alpha.tax.policy import OVERLAY_VERSION, SCENARIOS


def evidence_inputs(period="development"):
    """Expected numbers are chosen directly, never computed from gate helpers."""
    contract = build_contract(
        synthetic=True,
        periods={
            "development": {"start": "2010-01-01", "end": "2011-12-31", "status": "seen"},
            "validation": {"start": "2012-01-01", "end": "2013-12-31", "status": "seen"},
        },
        data_methodology="synthetic-v1",
        tax_policy_sha256="a" * 64,
        calendar_sha256="b" * 64,
        calendar_authority_sha256="c" * 64,
    )
    identity = {
        "strategy_spec_sha256": "d" * 64,
        "code_sha256": code_fingerprint(),
        "tax_policy_sha256": "a" * 64,
        "distributions_sha256": "e" * 64,
        "data_sha256": "f" * 64,
        "contract_sha256": contract_sha256(contract),
        "evaluator_sha256": evaluator_fingerprint(),
        "calendar_sha256": "b" * 64,
        "calendar_authority_sha256": "c" * 64,
    }
    account_map = expected_account_map()
    runs = {}
    for accounts in account_map.values():
        for role, account in accounts.items():
            runs[account] = {
                scenario.key: {
                    "scenario": scenario.as_dict(),
                    "policy": {
                        "tax_policy_sha256": identity["tax_policy_sha256"],
                        "code_sha256": identity["code_sha256"],
                        "distributions_sha256": identity["distributions_sha256"],
                        "overlay_version": OVERLAY_VERSION,
                    },
                    "metrics": {"after_tax_cagr": 0.045 if role == "strategy" else 0.04},
                    "identity_checks": {
                        "share_identity_passed": True,
                        "income_plus_gain_passed": True,
                        "implied_price_check_passed": True,
                    },
                }
                for scenario in SCENARIOS
            }
    return {
        "variants": {
            row: {
                "strategy": {"max_drawdown": -0.2, "sharpe_vs_cash": 100},
                "static": {"max_drawdown": -0.2, "sharpe_vs_cash": 0},
            }
            for row in account_map
        },
        "tax": {
            "tax_policy_sha256": identity["tax_policy_sha256"],
            "distributions_sha256": identity["distributions_sha256"],
            "overlay_version": OVERLAY_VERSION,
            "runs": runs,
        },
        "account_map": account_map,
        "row_definitions": expected_row_definitions(),
        "verification": {"account_reconciliation": {account: True for account in runs}, "calendar_complete": True},
        "identities": identity,
        "contract": contract,
        "period": period,
        "start": contract["periods"][period]["start"],
        "end": contract["periods"][period]["end"],
        "evidence_status": "synthetic",
    }


def set_cagr(raw, account, value):
    for scenario in raw["tax"]["runs"][account].values():
        scenario["metrics"]["after_tax_cagr"] = value


def test_exact_50_bps_passes_without_float_subtraction_roundoff():
    outcome = evaluate_period(build_period_evidence(**evidence_inputs()))
    assert outcome.passed
    assert len(outcome.criteria) == 15
    assert "50" in outcome.criteria[0].detail


def test_499999_bps_fails_despite_excellent_pre_tax_sharpe():
    raw = evidence_inputs()
    set_cagr(raw, "strategy", 0.04499999)
    assert not evaluate_period(build_period_evidence(**raw)).passed


@pytest.mark.parametrize("row", ["double_cost", "without_9", "without_12", "without_15"])
def test_one_zero_margin_stress_fails(row):
    raw = evidence_inputs()
    set_cagr(raw, f"variant:{row}", 0.04)
    assert not evaluate_period(build_period_evidence(**raw)).passed


@pytest.mark.parametrize("strategy_dd,benchmark_dd", [(-0.21, -0.3), (-0.19, -0.18)])
def test_drawdown_absolute_and_relative_gates_are_separate(strategy_dd, benchmark_dd):
    raw = evidence_inputs()
    raw["variants"]["base"]["strategy"]["max_drawdown"] = strategy_dd
    raw["variants"]["base"]["static"]["max_drawdown"] = benchmark_dd
    assert not evaluate_period(build_period_evidence(**raw)).passed


def test_independent_extrema_fail_although_every_matched_pair_beats_50_bps():
    raw = evidence_inputs()
    # Every matched pair is +60 bps, but worst S=.046 vs best B=.05 is negative.
    for index, scenario in enumerate(SCENARIOS):
        raw["tax"]["runs"]["strategy"][scenario.key]["metrics"]["after_tax_cagr"] = 0.046 if index == 0 else 0.056
        raw["tax"]["runs"]["benchmark"][scenario.key]["metrics"]["after_tax_cagr"] = 0.04 if index == 0 else 0.05
    assert not evaluate_period(build_period_evidence(**raw)).passed


def test_two_periods_are_not_pooled():
    first, second = evidence_inputs(), evidence_inputs("validation")
    set_cagr(first, "strategy", 0.5)
    set_cagr(second, "variant:without_15", 0.039)
    assert classify(build_period_evidence(**first), build_period_evidence(**second)) is ResearchEligibility.NOT_ELIGIBLE


def test_all_rows_in_both_periods_pass():
    assert classify(build_period_evidence(**evidence_inputs()), build_period_evidence(**evidence_inputs("validation"))) is ResearchEligibility.ELIGIBLE


def test_data_and_truncated_distributions_may_differ_between_periods():
    first, second = evidence_inputs(), evidence_inputs("validation")
    second["identities"]["data_sha256"] = "1" * 64
    second["identities"]["distributions_sha256"] = "2" * 64
    second["tax"]["distributions_sha256"] = "2" * 64
    for scenarios in second["tax"]["runs"].values():
        for scenario in scenarios.values():
            scenario["policy"]["distributions_sha256"] = "2" * 64
    assert classify(build_period_evidence(**first), build_period_evidence(**second)) is ResearchEligibility.ELIGIBLE


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), float("-inf"), True, False, "0.1"])
@pytest.mark.parametrize("field", ["drawdown", "cagr"])
def test_invalid_numeric_evidence_is_not_an_economic_failure(value, field):
    raw = evidence_inputs()
    if field == "drawdown":
        raw["variants"]["base"]["strategy"]["max_drawdown"] = value
    else:
        raw["tax"]["runs"]["benchmark"][SCENARIOS[-1].key]["metrics"]["after_tax_cagr"] = value
    with pytest.raises(ValueError):
        build_period_evidence(**raw)


@pytest.mark.parametrize("change", ["missing_row", "extra_row", "missing_scenario", "extra_scenario", "missing_benchmark", "missing_mapping", "wrong_benchmark", "wrong_cost", "false_identity", "truthy_identity", "wrong_policy", "wrong_scenario", "missing_reconciliation", "false_reconciliation", "false_calendar", "old_schema", "changed_evaluator", "old_code", "changed_window"])
def test_incomplete_or_incompatible_evidence_refuses(change):
    raw = evidence_inputs()
    scenarios = raw["tax"]["runs"]["benchmark:double_cost"]
    one = scenarios[SCENARIOS[0].key]
    if change == "missing_row": raw["variants"].pop("without_15")
    elif change == "extra_row": raw["variants"]["reference_12"] = deepcopy(raw["variants"]["base"])
    elif change == "missing_scenario": scenarios.pop(SCENARIOS[-1].key)
    elif change == "extra_scenario": scenarios["optimistic"] = deepcopy(one)
    elif change == "missing_benchmark": raw["tax"]["runs"].pop("benchmark:double_cost")
    elif change == "missing_mapping": raw["account_map"].pop("without_9")
    elif change == "wrong_benchmark": raw["row_definitions"]["double_cost"]["benchmark"]["exposure"] = 1.0
    elif change == "wrong_cost": raw["row_definitions"]["double_cost"]["benchmark"]["cost_bps"] = 10
    elif change == "false_identity": one["identity_checks"]["income_plus_gain_passed"] = False
    elif change == "truthy_identity": one["identity_checks"]["income_plus_gain_passed"] = 1
    elif change == "wrong_policy": one["policy"]["tax_policy_sha256"] = "1" * 64
    elif change == "wrong_scenario": one["scenario"]["lot_method"] = "fifo"
    elif change == "missing_reconciliation": raw["verification"]["account_reconciliation"].pop("benchmark:double_cost")
    elif change == "false_reconciliation": raw["verification"]["account_reconciliation"]["benchmark:double_cost"] = False
    elif change == "false_calendar": raw["verification"]["calendar_complete"] = False
    elif change == "old_schema": raw["artifact_schema"] = 6
    elif change == "changed_evaluator": raw["identities"]["evaluator_sha256"] = "1" * 64
    elif change == "old_code": raw["identities"]["code_sha256"] = "1" * 64
    elif change == "changed_window": raw["end"] = "2010-12-31"
    with pytest.raises(ValueError):
        build_period_evidence(**raw)


def test_matching_old_evaluator_hashes_do_not_authorize_new_evaluator():
    raw = evidence_inputs()
    raw["identities"]["evaluator_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="evaluator"):
        build_period_evidence(**raw)


def test_same_period_cannot_be_passed_twice():
    one = build_period_evidence(**evidence_inputs())
    with pytest.raises(ValueError, match="development.*validation"):
        classify(one, one)


def test_mutating_source_payload_cannot_change_accepted_evidence():
    raw = evidence_inputs()
    accepted = build_period_evidence(**raw)
    set_cagr(raw, "strategy", -0.5)
    assert evaluate_period(accepted).passed


def test_cross_period_strategy_identity_changes_refuse():
    first, second = evidence_inputs(), evidence_inputs("validation")
    second["identities"]["strategy_spec_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="strategy_spec"):
        classify(build_period_evidence(**first), build_period_evidence(**second))


def test_extrema_regression_is_killed_by_discriminating_fixture(monkeypatch):
    from boring_alpha.period_evidence import RowEvidence

    # A plausible bug: the worst matched difference, instead of independent
    # extrema. Demonstrate that the earlier fixture actually rejects this code.
    monkeypatch.setattr(RowEvidence, "margin", property(lambda row: min(value for _, value in row.paired_margins)))
    with pytest.raises(AssertionError):
        test_independent_extrema_fail_although_every_matched_pair_beats_50_bps()


def test_primary_threshold_regression_is_killed_by_boundary_fixture(monkeypatch):
    import boring_alpha.criteria_ba002 as criteria

    monkeypatch.setattr(criteria, "PRIMARY_MARGIN", Decimal("0.004"))
    with pytest.raises(AssertionError):
        test_499999_bps_fails_despite_excellent_pre_tax_sharpe()


def test_full_tax_policy_contents_are_checked_not_only_repeated_hashes():
    from test_research_contract import historical_contract

    raw = evidence_inputs()
    policy = historical_contract()["tax_policy"]
    from boring_alpha.research_contract import canonical_sha256
    digest = canonical_sha256(policy)
    raw["contract"]["tax_policy"] = policy
    raw["contract"]["tax_policy_sha256"] = digest
    raw["identities"]["tax_policy_sha256"] = digest
    raw["identities"]["contract_sha256"] = contract_sha256(raw["contract"])
    raw["tax"]["tax_policy_sha256"] = digest
    for scenarios in raw["tax"]["runs"].values():
        for scenario in scenarios.values():
            scenario["policy"].update(deepcopy(policy))
            scenario["policy"]["tax_policy_sha256"] = digest
    assert evaluate_period(build_period_evidence(**raw)).passed
    raw["tax"]["runs"]["benchmark:without_12"][SCENARIOS[-1].key]["policy"]["ordinary_rate"] = 0.1
    with pytest.raises(ValueError, match="ordinary_rate"):
        build_period_evidence(**raw)


def test_nonfinite_tax_identity_measure_cannot_hide_behind_true_flag():
    raw = evidence_inputs()
    raw["tax"]["runs"]["strategy"][SCENARIOS[-1].key]["identity_checks"]["share_identity_max_relative_deviation"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        build_period_evidence(**raw)
