"""Independent exhaustive small cases and hand checks for frozen Stage A."""
from decimal import Decimal as D
import importlib.util
from itertools import product
from pathlib import Path

import numpy as np
import pytest


SPEC = importlib.util.spec_from_file_location("ba012_sizing", Path(__file__).resolve().parents[1] / "tools/ba012_sizing.py")
sizing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sizing)

FEE = tuple(map(D, ("1.11", "3.685", "2.90", "1.16", "5.76")))
LOSS = tuple(map(D, ("200", "200", "250", "200", "200")))
LONG = tuple(map(D, ("324.1225", "710.681", "329.442", "459.689", "206.92")))
SHORT = tuple(map(D, ("298.78", "751.28", "334.442", "464.189", "234.42")))
GROUP = (0, 1, 2, 3, 3)


def brute_force(sigma, signs, equity=5000, upper=2):
    """No solver bounds/pruning; test EVERY integer partial fill, not vertices."""
    vol = np.sqrt(np.diag(sigma))
    tau = equity * .08
    u = np.array(signs) / vol
    target = tau * u / np.sqrt(u @ sigma @ u) if any(signs) else np.zeros(5)
    cash = (0, 0, 0, 0, 0)
    best_rank = (round(float(target @ sigma @ target / tau**2), 12), D(0), D(0), cash)
    best = cash
    feasible = []
    for n in product(range(upper + 1), repeat=5):
        if any(q and not s for q, s in zip(n, signs)):
            continue
        if len({g for g, q in zip(GROUP, n) if q}) < 3:
            continue
        contributions = np.array(n) * vol
        if contributions.max() > contributions.sum() / 2 + 1e-10:
            continue
        valid = True
        for state in product(*(range(q + 1) for q in n)):
            cost = sum(q * c for q, c in zip(state, FEE))
            stress = sum(q * b for q, b in zip(state, LOSS))
            initial = sum(q * (long if sign >= 0 else short)
                          for q, sign, long, short in zip(state, signs, LONG, SHORT))
            if 2 * cost + stress > D(equity) / 5 or D(equity) - 2 * cost - stress < 2 * initial + 100:
                valid = False
                break
            q = np.array(state) * signs
            if np.sqrt(q @ sigma @ q) > .08 * (equity - float(cost)) + tau * 1e-12:
                valid = False
                break
        if not valid:
            continue
        feasible.append(n)
        q = np.array(n) * signs
        delta = q - target
        rank = (round(float(delta @ sigma @ delta / tau**2), 12),
                sum(q * c for q, c in zip(n, FEE)), sum(q * b for q, b in zip(n, LOSS)), n)
        if rank < best_rank:
            best, best_rank = n, rank
    return [int(q * s) for q, s in zip(best, signs)], best_rank, feasible


def movements_with_sample_covariance(sample):
    # Five orthogonal sinusoidal columns, zero means, and squared norms 251.
    t = np.arange(252)
    orthogonal = np.column_stack([np.sin(2 * np.pi * k * t / 252) for k in range(1, 6)])
    orthogonal *= np.sqrt(251 / 126)
    return orthogonal @ np.linalg.cholesky(sample).T


def test_covariance_demeans_uses_251_and_shrinks_before_annualizing():
    sample = np.diag([1., 4., 9., 16., 25.])
    sample[0, 1] = sample[1, 0] = 1.0
    rows = movements_with_sample_covariance(sample) + np.arange(5) * 123.0
    expected = 252 * (.5 * sample + .5 * np.diag(np.diag(sample)))
    np.testing.assert_allclose(sizing.estimate_covariance(rows), expected, atol=1e-9)


def test_public_boundary_accepts_decimal_strings_and_checks_freeze():
    rows = movements_with_sample_covariance(np.eye(5) * 10000 / 252)
    result = sizing.size_stage_a([[str(x) for x in row] for row in rows], ["1"] * 5)
    assert result["quantities"] == [1, 1, 1, 1, 0]
    assert result["protocol_sha256"] == sizing.verify_frozen_protocol()


@pytest.mark.parametrize("rows", [np.ones((251, 5)), np.ones((252, 4)),
                                  np.full((252, 5), np.nan), np.zeros((252, 5)),
                                  np.full((252, 5), .1)])
def test_bad_risk_windows_block_sizing(rows):
    with pytest.raises(ValueError):
        sizing.size_stage_a(rows, [1] * 5)


@pytest.mark.parametrize("signs", [[1] * 4, [True, 1, 1, 1, 1], [1, 1, .5, 1, 1], [1, 1, "NaN", 1, 1]])
def test_bad_signs_rejected(signs):
    with pytest.raises(ValueError):
        sizing._size_from_covariance(np.eye(5), signs)


@pytest.mark.parametrize("equity", [4999, 10000, True])
def test_unregistered_capital_rejected(equity):
    with pytest.raises(ValueError):
        sizing._size_from_covariance(np.eye(5), [1] * 5, equity)


def test_cash_signal_and_group_rules_do_not_force_participation():
    for signs in ([0] * 5, [1, 0, 0, 1, 1]):
        result = sizing._size_from_covariance(np.eye(5) * 10000, signs)
        assert result["quantities"] == [0] * 5
        assert result["nonzero_feasibility"] == "PROVED_INFEASIBLE"


def test_cost_adjusted_partial_equity_rejects_exact_pre_entry_cap():
    sigma = np.eye(5) * (400 / np.sqrt(3))**2
    result = sizing._size_from_covariance(sigma, [1, 1, 1, 0, 0])
    assert np.sqrt(np.ones(3) @ sigma[:3, :3] @ np.ones(3)) == pytest.approx(400)
    assert result["quantities"] == [0] * 5
    assert result["search"]["partial_risk_prunes"] > 0


def test_terminal_hedge_is_insufficient_when_a_two_sleeve_fill_exceeds_cap():
    sigma = (np.eye(5) * .5 + np.ones((5, 5)) * .5) * 240**2
    q = np.array([1, 1, -1, 0, 0])
    assert np.sqrt(q @ sigma @ q) < 399
    partial = np.array([1, 1, 0, 0, 0])
    assert np.sqrt(partial @ sigma @ partial) > 400
    result = sizing._size_from_covariance(sigma, q)
    assert result["quantities"] == [0] * 5
    assert result["nonzero_feasibility"] == "PROVED_INFEASIBLE"


def test_concentration_can_reject_an_otherwise_fundable_three_group_basket():
    sigma = np.diag(np.array([50., 50., 300., 900., 900.])**2)
    result = sizing._size_from_covariance(sigma, [1, 1, 1, 0, 0])
    assert result["quantities"] == [0] * 5
    assert result["search"]["concentration_rejections"] > 0


def test_upward_rounding_and_cost_tie_break_choose_a_nonzero_basket():
    result = sizing._size_from_covariance(np.eye(5) * 200**2, [1] * 5)
    assert all(x < 1 for x in result["continuous_target_quantities"])
    assert result["quantities"] == [1, 0, 1, 1, 0]
    assert result["incumbent_entry_cost_usd"] == pytest.approx(5.17)
    assert result["incumbent_loss_budget_charge_usd"] == pytest.approx(660.34)
    assert result["incumbent_post_entry_equity_usd"] == pytest.approx(4994.83)


def test_objective_rounding_precedes_lower_cost_and_stress():
    assert sizing._rank(.5 + 1e-13, (1, 0, 0, 0, 0)) < sizing._rank(.5, (0, 0, 0, 1, 0))
    # Same entry cost: 116 NES or 111 gold; gold has less stipulated stress.
    assert sizing._rank(.5, (0, 0, 0, 111, 0)) < sizing._rank(.5, (116, 0, 0, 0, 0))


def test_three_group_singleton_and_shrinkage_bounds_are_exact_rejections():
    result = sizing._size_from_covariance(np.diag(np.array([100, 500, 500, 100, 100])**2), [1] * 5)
    assert "fewer_than_three_groups" in result["necessary_failures"][0]
    result = sizing._size_from_covariance(np.eye(5) * 350**2, [1] * 5)
    assert "three_group_shrinkage_lower_bound_exceeds_risk_cap" in result["necessary_failures"]
    assert result["search"]["nodes"] == 0


@pytest.mark.parametrize("seed", range(16))
def test_pilot_optimum_matches_independent_brute_force_with_all_partial_quantities(seed):
    rng = np.random.default_rng(seed)
    raw = rng.normal(size=(5, 5))
    raw = raw @ raw.T
    corr = raw / np.sqrt(np.outer(np.diag(raw), np.diag(raw)))
    corr = .5 * corr + .5 * np.eye(5)
    vol = rng.uniform(55, 390, size=5)
    sigma = corr * np.outer(vol, vol)
    signs = rng.choice([-1, 0, 1], size=5, p=[.45, .1, .45])
    expected, expected_rank, feasible = brute_force(sigma, signs)
    actual = sizing._size_from_covariance(sigma, signs)
    assert actual["optimum_verified"]
    assert actual["quantities"] == expected
    assert actual["incumbent_tracking_objective_rounded_12"] == expected_rank[0]
    if actual["nonzero_feasibility"] == "PROVED_INFEASIBLE":
        assert not feasible


@pytest.mark.parametrize("equity", [25000, 100000])
def test_larger_virtual_capital_matches_brute_force_without_increasing_risk_policy(equity):
    # One-sleeve cost-adjusted risk bounds prove at most two units per market.
    scale = equity / 5000
    sigma = np.diag((np.array([145., 180., 200., 250., 175.]) * scale)**2)
    signs = [1, -1, 1, -1, 1]
    actual = sizing._size_from_covariance(sigma, signs, equity)
    expected, rank, _ = brute_force(sigma, signs, equity)
    assert actual["quantities"] == expected
    assert actual["incumbent_tracking_objective_rounded_12"] == rank[0]
    assert actual["simulated_loss_budget_usd"] == equity / 5
    assert actual["pre_entry_annual_dollar_vol_target_usd"] == equity * .08


def test_search_limit_is_never_reported_as_an_optimum_or_cash_verdict():
    result = sizing._size_from_covariance(np.eye(5) * 100**2, [1] * 5, max_nodes=1)
    assert result["status"] == "SEARCH_LIMIT"
    assert not result["optimum_verified"]
    assert result["decision"] == "UNRESOLVED"
    assert result["quantities"] is None


def test_fixed_zero_bound_signal_sleeve_is_retained_in_objective():
    sigma = (.5 * np.eye(5) + .5 * np.ones((5, 5))) * np.outer([100, 100, 100, 800, 100], [100, 100, 100, 800, 100])
    signs = [1, -1, 1, 1, -1]
    actual = sizing._size_from_covariance(sigma, signs)
    expected, rank, _ = brute_force(sigma, signs)
    assert actual["quantities"] == expected
    assert actual["incumbent_tracking_objective_rounded_12"] == rank[0]
