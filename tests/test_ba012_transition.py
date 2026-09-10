"""Independent small-box enumeration of signed, costed partial transitions."""
from decimal import Decimal as D
from itertools import product
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ba012_transition as transition

FEE = tuple(map(D, ("1.11", "3.685", "2.90", "1.16", "5.76")))
SHOCK = tuple(map(D, ("200", "200", "250", "200", "200")))
INITIAL_LONG = tuple(map(D, ("324.1225", "710.681", "329.442", "459.689", "206.92")))
INITIAL_SHORT = tuple(map(D, ("298.78", "751.28", "334.442", "464.189", "234.42")))
MAINT_LONG = tuple(map(D, ("259.81", "616.95", "286.471", "399.73", "179.931")))
MAINT_SHORT = tuple(map(D, ("259.808", "616.95", "286.471", "399.73", "179.931")))
GROUP = (0, 1, 2, 3, 3)


def _sign(n):
    return int(n > 0) - int(n < 0)


def independently_feasible(sigma, signs, equity, high_water, budget, p, q, roll, reduction=False):
    """Visit EVERY integer partial quantity, not just the solver's vertices."""
    equity, high_water, budget = D(str(equity)), D(str(high_water)), D(str(budget))
    tau = float(equity) * .08
    drawdown = max(D(0), high_water - equity)
    vol = np.sqrt(np.diag(sigma))
    if any(n and _sign(n) != sign for n, sign in zip(q, signs)):
        return False
    if reduction and (any(abs(n) > abs(old) or n * old < 0 for n, old in zip(q, p))
                      or np.sqrt(np.array(q) @ sigma @ q) > np.sqrt(np.array(p) @ sigma @ p) + tau * 1e-12):
        return False
    if any(q):
        contributions = np.abs(q) * vol
        if len({g for n, g in zip(q, GROUP) if n}) < 3 or 2 * max(contributions) > sum(contributions) + tau * 1e-12:
            return False
    bridge = tuple(0 if rolling or old * new < 0 else _sign(old) * min(abs(old), abs(new))
                   for old, new, rolling in zip(p, q, roll))
    exit_cost = sum(abs(old - retained) * fee for old, retained, fee in zip(p, bridge, FEE))
    for phase, start, end, previous_cost in ((0, p, bridge, D(0)), (1, bridge, q, exit_cost)):
        for state in product(*(range(min(left, right), max(left, right) + 1) for left, right in zip(start, end))):
            new_cost = sum(abs(n - old) * fee for n, old, fee in zip(state, start, FEE))
            cost = previous_cost + new_cost
            price_loss = sum(abs(n) * shock for n, shock in zip(state, SHOCK))
            reserve = sum(abs(n) * fee for n, fee in zip(state, FEE))
            maintenance = sum(abs(n) * (long if n >= 0 else short) for n, long, short in zip(state, MAINT_LONG, MAINT_SHORT))
            initial = sum(abs(n) * (long if n >= 0 else short) for n, long, short in zip(state, INITIAL_LONG, INITIAL_SHORT))
            if drawdown + cost + price_loss + reserve > budget:
                return False
            remainder = equity - cost - price_loss - reserve - 100
            if remainder < 2 * maintenance or (phase == 1 and new_cost > 0 and remainder < 2 * initial):
                return False
            if np.sqrt(np.array(state) @ sigma @ state) > .08 * float(equity - cost) + tau * 1e-12:
                return False
    return True


def brute_force(sigma, signs, equity, high_water, budget, p, roll, lower=(0, 0, 0, 0, 0),
                upper=(2, 2, 2, 2, 2), reduction=False):
    vol = np.sqrt(np.diag(sigma))
    tau = .08 * equity
    u = np.array(signs) / vol
    target = tau * u / np.sqrt(u @ sigma @ u) if any(signs) else np.zeros(5)
    best = None
    for magnitude in product(*(range(lo, hi + 1) for lo, hi in zip(lower, upper))):
        if any(n and not sign for n, sign in zip(magnitude, signs)):
            continue
        q = tuple(n * sign for n, sign in zip(magnitude, signs))
        if not independently_feasible(sigma, signs, equity, high_water, budget, p, q, roll, reduction):
            continue
        delta = np.array(q) - target
        j = float(delta @ sigma @ delta / tau**2)
        bridge = tuple(0 if rolling or old * new < 0 else _sign(old) * min(abs(old), abs(new))
                       for old, new, rolling in zip(p, q, roll))
        cost = sum((abs(old - retained) + abs(new - retained)) * fee for old, retained, new, fee in zip(p, bridge, q, FEE))
        stress = sum(abs(n) * shock for n, shock in zip(q, SHOCK))
        rank = (round(j, 12), cost, stress, magnitude)
        if best is None or rank < best[0]:
            best = (rank, list(q))
    return best


def test_hold_has_no_entry_cost_and_requires_maintenance_not_initial_margin():
    sigma = np.eye(5) * 100**2
    p = (1, 1, 0, 1, 0)
    audit = transition.audit_holdings(sigma, 3400, 3400, 680, p, include_states=True)
    assert audit["feasible"] and audit["terminal_feasible"]
    assert audit["stressed_transition_cost_usd"] == 0
    assert audit["terminal"]["initial_funding_headroom_usd"] < 0
    assert audit["terminal"]["maintenance_funding_headroom_usd"] > 0
    assert not any(state["initial_margin_required"] for state in audit["phase_vertices"])


def test_transition_cost_tie_prefers_existing_feasible_hold():
    p = (1, 1, 1, 0, 0)
    result = transition.optimize_transition(np.eye(5) * 200**2, [1] * 5, 5000, 5000, 1000, p)
    assert result["status"] == "OPTIMAL" and result["quantities"] == list(p)
    assert result["audit"]["stressed_transition_cost_usd"] == 0


def test_sign_reversal_pays_both_legs_and_bridges_through_zero():
    p, q = (1, 1, 1, 0, 0), (-1, 1, 1, 0, 0)
    audit = transition.audit_transition(np.eye(5) * 10000, (-1, 1, 1, 0, 0), 5000, 5000, 1000, p, q)
    assert audit["feasible"]
    assert audit["bridge_quantities"] == [0, 1, 1, 0, 0]
    assert audit["stressed_exit_cost_usd"] == pytest.approx(1.11)
    assert audit["stressed_entry_cost_usd"] == pytest.approx(1.11)
    assert audit["stressed_transition_cost_usd"] == pytest.approx(2.22)


def test_same_quantity_roll_pays_close_and_replacement():
    p = (1, 1, 1, 0, 0)
    audit = transition.audit_transition(np.eye(5) * 10000, (1, 1, 1, 0, 0), 5000, 5000, 1000, p, p,
                                        roll_mask=(False, False, True, False, False), reduction_only=True)
    assert audit["feasible"] and audit["bridge_quantities"] == [1, 1, 0, 0, 0]
    assert audit["stressed_transition_cost_usd"] == pytest.approx(5.80)
    assert audit["terminal"]["initial_margin_required"]


def test_existing_drawdown_consumes_fixed_budget_without_reset():
    q = (1, 1, 1, 0, 0)
    good = transition.audit_transition(np.eye(5) * 10000, q, 4800, 5000, 1000, (0,) * 5, q)
    bad = transition.audit_transition(np.eye(5) * 10000, q, 4500, 5000, 1000, (0,) * 5, q)
    assert good["feasible"] and good["initial_drawdown_usd"] == 200
    assert not bad["feasible"] and "loss_budget" in bad["violations"]


def test_arbitrary_reduced_equity_reduces_post_cost_risk_cap():
    sigma = np.diag(np.array([220, 220, 220, 100, 100])**2)
    q = (1, 1, 1, 0, 0)
    assert transition.audit_transition(sigma, q, 5000, 5000, 1000, (0,) * 5, q)["feasible"]
    bad = transition.audit_transition(sigma, q, "4700.12345", 5000, 1000, (0,) * 5, q)
    assert not bad["feasible"] and "volatility_cap" in bad["violations"]
    assert bad["terminal"]["equity_after_cost_usd"] == pytest.approx(4700.12345 - 7.695)


def hedge_example():
    correlation = np.eye(5)
    correlation[:3, :3] = .5 * np.eye(3) + .5 * np.ones((3, 3))
    vol = np.array([450, 225, 225, 100, 100])
    return correlation * np.outer(vol, vol), (1, -1, -1, 0, 0)


def test_held_hedge_can_exceed_fresh_singleton_bound_but_hold_is_feasible():
    sigma, p = hedge_example()
    assert np.sqrt(sigma[0, 0]) > 400
    assert transition.audit_holdings(sigma, 5000, 5000, 1000, p)["feasible"]
    result = transition.optimize_transition(sigma, p, 5000, 5000, 1000, p)
    assert result["status"] == "OPTIMAL" and result["quantities"] == list(p)
    assert result["per_market_quantity_upper_bounds"][0] >= 1


def test_optional_flatten_checks_hedge_removal_vertices_not_just_cash_terminal():
    sigma, p = hedge_example()
    audit = transition.audit_transition(sigma, p, 5000, 5000, 1000, p, (0,) * 5)
    assert audit["terminal_feasible"] and audit["starting_state_feasible"]
    assert not audit["feasible"] and "volatility_cap" in audit["violations"]
    assert any(state["quantities"] == [1, 0, 0, 0, 0] for state in audit["partial_state_failures"])


def test_initial_hard_violation_blocks_optional_optimizer_even_if_terminal_cash_passes():
    p = (1, 1, 1, 0, 0)
    result = transition.optimize_transition(np.eye(5) * 300**2, p, 5000, 5000, 1000, p)
    assert result["status"] == "NO_FEASIBLE_TRANSITION" and result["quantities"] is None
    assert result["infeasibility_verified"] and result["search"]["nodes"] == 0
    assert "volatility_cap" in result["audit"]["violations"]


def test_reduction_only_cannot_increase_terminal_risk_even_below_account_cap():
    correlation = np.eye(5)
    correlation[0, 1] = correlation[1, 0] = .5
    vol = np.array([180, 100, 100, 100, 100])
    sigma = correlation * np.outer(vol, vol)
    p, q = (1, -1, 1, 1, 0), (1, 0, 1, 1, 0)
    assert transition.audit_transition(sigma, p, 5000, 5000, 1000, p, q)["feasible"]
    audit = transition.audit_transition(sigma, p, 5000, 5000, 1000, p, q, reduction_only=True)
    assert not audit["feasible"] and "reduction_increases_terminal_risk" in audit["violations"]


def test_concentration_only_breach_allows_verified_daily_reduction_before_flattening():
    sigma = np.diag(np.array([150, 100, 100, 100, 100])**2)
    p = (2, 1, 1, 0, 0)
    held = transition.audit_holdings(sigma, 5000, 5000, 1000, p)
    assert held["starting_state_feasible"]
    assert not held["terminal_feasible"] and held["violations"] == ["terminal_concentration"]
    result = transition.optimize_transition(sigma, (1, 1, 1, 0, 0), 5000, 5000, 1000, p,
                                            component_upper_bound=p, reduction_only=True)
    assert result["status"] == "OPTIMAL" and result["quantities"] == [1, 1, 1, 0, 0]
    assert result["audit"]["feasible"]
    assert result["audit"]["terminal"]["forecast_volatility_usd"] < held["starting_state"]["forecast_volatility_usd"]


def test_retained_lower_bound_prevents_cash_or_reduction_during_entry_recheck():
    p = (1, 1, 0, 0, 0)
    result = transition.optimize_transition(np.eye(5) * 10000, (1, 1, 1, 0, 0), 5000, 5000, 1000, p,
                                           component_lower_bound=p, component_upper_bound=(1, 1, 0, 0, 0))
    assert result["status"] == "NO_FEASIBLE_TRANSITION" and result["quantities"] is None
    result = transition.optimize_transition(np.eye(5) * 10000, (1, 1, 1, 0, 0), 5000, 5000, 1000, p,
                                           component_lower_bound=p, component_upper_bound=(1, 1, 1, 0, 0))
    assert result["status"] == "OPTIMAL" and result["quantities"] == [1, 1, 1, 0, 0]


def test_hold_audit_ignores_new_month_direction_before_reversal_decision():
    p = (1, 1, 1, 0, 0)
    assert transition.audit_holdings(np.eye(5) * 10000, 5000, 5000, 1000, p)["feasible"]
    bad = transition.audit_transition(np.eye(5) * 10000, (-1, 1, 1, 0, 0), 5000, 5000, 1000, p, p)
    assert "direction_constraint" in bad["violations"]


@pytest.mark.parametrize("seed", range(16))
def test_optimum_matches_independent_all_integer_partial_state_brute_force(seed):
    rng = np.random.default_rng(seed)
    matrix = rng.normal(size=(5, 5))
    sample = matrix @ matrix.T
    correlation = .5 * sample / np.sqrt(np.outer(np.diag(sample), np.diag(sample))) + .5 * np.eye(5)
    vol = rng.uniform(60, 180, size=5)
    sigma = correlation * np.outer(vol, vol)
    p = (1, -1, 1, 0, 0) if seed % 3 else (0, 0, 0, 0, 0)
    signs = tuple(int(x) for x in rng.choice([-1, 0, 1], size=5, p=[.45, .1, .45]))
    roll = tuple(bool(x) for x in rng.choice([False, True], size=5, p=[.8, .2]))
    equity, high_water, budget = 4800.125, 4900.875, 1000
    expected = brute_force(sigma, signs, equity, high_water, budget, p, roll)
    actual = transition.optimize_transition(sigma, signs, equity, high_water, budget, p,
                                            roll_mask=roll, component_upper_bound=(2,) * 5)
    if expected is None:
        assert actual["status"] == "NO_FEASIBLE_TRANSITION"
    else:
        assert actual["status"] == "OPTIMAL"
        assert actual["quantities"] == expected[1]
        assert actual["objective_rounded_12"] == expected[0][0]


def test_lower_and_upper_bounds_match_independent_brute_force():
    sigma = np.eye(5) * 150**2
    p, signs, roll = (1, 1, 0, 0, 0), (1, 1, 1, 1, 1), (False,) * 5
    lower, upper = (1, 1, 0, 0, 0), (2, 2, 1, 1, 1)
    expected = brute_force(sigma, signs, 5000, 5000, 1000, p, roll, lower, upper)
    actual = transition.optimize_transition(sigma, signs, 5000, 5000, 1000, p,
                                            component_lower_bound=lower, component_upper_bound=upper)
    assert actual["status"] == "OPTIMAL" and actual["quantities"] == expected[1]


def test_search_limit_never_publishes_seed_or_cash_as_verified_result():
    result = transition.optimize_transition(np.eye(5) * 10000, [1] * 5, 5000, 5000, 1000, [0] * 5, max_nodes=1)
    assert result["status"] == "SEARCH_LIMIT"
    assert result["quantities"] is None and result["objective"] is None
    assert not result["optimum_verified"] and not result["infeasibility_verified"]


@pytest.mark.parametrize("kwargs", [{"equity": 0}, {"high_water": -1}, {"loss_budget": float("nan")},
                                    {"holdings": [True, 0, 0, 0, 0]}, {"component_lower_bound": [-1, 0, 0, 0, 0]}])
def test_invalid_inputs_fail_closed(kwargs):
    args = dict(sigma=np.eye(5), signs=[1] * 5, equity=5000, high_water=5000, loss_budget=1000, holdings=[0] * 5)
    args.update(kwargs)
    with pytest.raises(ValueError):
        transition.optimize_transition(**args)
