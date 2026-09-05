"""A real synthetic cost difference must reach the corresponding tax gate.

The benchmark histories below come from the production sweep. Strategy return
inputs are then deliberately calibrated *only for a criterion wiring probe*:
the 20-bps strategy lies between the two actual benchmark maxima. Using the
wrong account therefore changes the verdict instead of leaving a green test.
These manipulated metrics are never published as a research artifact.
"""

from copy import deepcopy
from decimal import Decimal
import math

import pytest

from boring_alpha.config import load_config
from boring_alpha.criteria_ba002 import evaluate_period
from boring_alpha.data import load_market_data
from boring_alpha.demo import prepare_ba002_demo
from boring_alpha.period_evidence import AccountEvidence, build_period_evidence
from boring_alpha.sweep import run_sweep


@pytest.fixture(scope="module")
def changing_price_sweep(tmp_path_factory):
    root = tmp_path_factory.mktemp("paired-benchmark-probe")
    paths = prepare_ba002_demo(root)
    config = load_config(paths["development"])
    data = load_market_data(config)
    assert len({data.bar(day, "SPY").close for day in data.dates}) > 100
    return run_sweep(config, data)


def _best(sweep, account):
    return max(
        Decimal(str(scenario["metrics"]["after_tax_cagr"]))
        for scenario in sweep.tax["runs"][account].values()
    )


def _assert_cost_matched_gate(sweep):
    raw_tax = deepcopy(sweep.tax)
    variants = deepcopy(sweep.variants)
    best_ten = _best(sweep, "benchmark")
    best_twenty = _best(sweep, "benchmark:double_cost")
    assert best_ten > best_twenty
    midpoint = (best_ten + best_twenty) / 2
    for row, accounts in sweep.account_map.items():
        benchmark_best = _best(sweep, accounts["benchmark"])
        cagr = midpoint if row == "double_cost" else benchmark_best + Decimal("0.006")
        for scenario in raw_tax["runs"][accounts["strategy"]].values():
            scenario["metrics"]["after_tax_cagr"] = float(cagr)
        # The fixture isolates the after-tax pairing gate: no risk failure can
        # accidentally provide an alternative reason for a failed verdict.
        variants[row]["strategy"]["max_drawdown"] = 0.0
    original = sweep.evidence
    evidence = build_period_evidence(
        variants=variants, tax=raw_tax, account_map=sweep.account_map,
        row_definitions=sweep.row_definitions, verification=sweep.verification,
        identities=original.identity, contract=sweep.research_contract,
        period=original.period, start=original.start, end=original.end,
        evidence_status=original.evidence_status,
    )
    outcome = evaluate_period(evidence)
    gate = next(item for item in outcome.criteria if item.name == "double_cost:return")
    assert gate.passed, "the 20-bps return must use its own 20-bps benchmark"
    assert outcome.passed


def test_paired_benchmark_costs_change_actual_histories_and_feed_correct_gate(changing_price_sweep):
    sweep = changing_price_sweep
    ten, twenty = sweep.runs["base"][1], sweep.runs["double_cost"][1]
    assert ten.fills and twenty.fills
    for result, rate in ((ten, 0.001), (twenty, 0.002)):
        assert any(fill.notional > 0 for fill in result.fills)
        for fill in result.fills:
            assert math.isclose(fill.cost, fill.notional * rate, rel_tol=1e-12, abs_tol=1e-12)
    assert ten.equity_curve[-1].equity > twenty.equity_curve[-1].equity
    assert _best(sweep, "benchmark") > _best(sweep, "benchmark:double_cost")
    _assert_cost_matched_gate(sweep)


def test_base_benchmark_substitution_is_killed_by_the_pairing_fixture(changing_price_sweep, monkeypatch):
    sweep = changing_price_sweep
    original_best = AccountEvidence.best_cagr.fget
    base_best = _best(sweep, "benchmark")

    def wrong_benchmark(account):
        if account.account_id == "benchmark:double_cost":
            return base_best
        return original_best(account)

    monkeypatch.setattr(AccountEvidence, "best_cagr", property(wrong_benchmark))
    with pytest.raises(AssertionError, match="20-bps return"):
        _assert_cost_matched_gate(sweep)
