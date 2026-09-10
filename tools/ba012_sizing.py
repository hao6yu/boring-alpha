#!/usr/bin/env python3
"""Frozen BA-012 Stage A sizing only: no prices, returns, or order interface.

``size_stage_a`` accepts exactly 252 aligned one-child dollar-movement rows in
NES, MTN, M6E, 1OZ, MZC order and five already-frozen direction signs. Each
decision starts in cash at fixed capital, without a strategy equity path.

Money comparisons use integer ten-thousandths of a dollar. Covariance and
optimization use float64 in volatility-normalized coordinates; feasibility
has a disclosed 1e-12 normalized roundoff allowance. Objective lower bounds
are padded outward by 1e-10, much more than floating roundoff in the small,
well-conditioned shrunk correlation matrices. A node-limit result is NEVER
an optimum or a Stage A verdict.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
from itertools import product
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_SHA256 = "095fa832c82645a6f570668813b59b08afa4a21c93466980703ff78c46eec67f"
SYMBOLS = ("NES", "MTN", "M6E", "1OZ", "MZC")
GROUPS = ("equities", "rates", "fx", "commodities", "commodities")
MONEY_SCALE = 10_000
EXECUTION = (11100, 36850, 29000, 11600, 57600)
SHOCK = (2000000, 2000000, 2500000, 2000000, 2000000)
CHARGE = tuple(b + 2 * c for b, c in zip(SHOCK, EXECUTION))
INITIAL_LONG = (3241225, 7106810, 3294420, 4596890, 2069200)
INITIAL_SHORT = (2987800, 7512800, 3344420, 4641890, 2344200)
MAINTENANCE_LONG = (2598100, 6169500, 2864710, 3997300, 1799310)
MAINTENANCE_SHORT = (2598080, 6169500, 2864710, 3997300, 1799310)
FEASIBILITY_ATOL = 1e-12
BOUND_PAD = 1e-10


def verify_frozen_protocol() -> str:
    """Fail closed if either the protocol or its registration has changed."""
    actual = hashlib.sha256((ROOT / "docs/strategies/BA-012.md").read_bytes()).hexdigest()
    freeze = json.loads((ROOT / "research/ba012-protocol-v1-freeze.json").read_text())
    if actual != PROTOCOL_SHA256 or freeze["canonical_protocol"]["sha256"] != actual:
        raise ValueError("Frozen BA-012 version 1 checksum mismatch")
    return actual


def estimate_covariance(dollar_movements) -> np.ndarray:
    """Demeaned 251-denominator covariance, 50% diagonal shrink, annualize 252."""
    try:
        rows = np.asarray(dollar_movements, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Dollar movements must be a numeric 252-by-5 array") from exc
    if rows.shape != (252, 5) or not np.isfinite(rows).all():
        raise ValueError("Exactly 252 complete finite five-market rows are required")
    if np.any(np.all(rows == rows[0], axis=0)):
        # A repeated nonbinary float can leave a tiny identical residual
        # after mean rounding; that residual is not measured variance.
        raise ValueError("A constant movement column has zero variance and blocks sizing")
    centered = rows - rows.mean(axis=0)
    sample = centered.T @ centered / 251.0
    sigma = 252.0 * (0.5 * sample + 0.5 * np.diag(np.diag(sample)))
    if not np.isfinite(sigma).all() or np.any(np.diag(sigma) <= 0):
        raise ValueError("Nonfinite or zero-variance risk estimate blocks sizing")
    return sigma


def _validated_signs(signs) -> tuple[int, ...]:
    try:
        values = tuple(signs)
        if len(values) != 5 or any(isinstance(x, (bool, np.bool_)) for x in values):
            raise ValueError
        decimal_values = tuple(Decimal(str(x)) for x in values)
        if any(x not in (Decimal(-1), Decimal(0), Decimal(1)) for x in decimal_values):
            raise ValueError
        return tuple(int(x) for x in decimal_values)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError("Five signs, each exactly -1, 0, or 1, are required") from exc


def _rank(j: float, magnitude: tuple[int, ...]) -> tuple:
    return (round(float(j), 12),
            sum(n * c for n, c in zip(magnitude, EXECUTION)),
            sum(n * b for n, b in zip(magnitude, SHOCK)), magnitude)


def size_stage_a(dollar_movements, signs, equity=5000, *, max_nodes=2_000_000) -> dict:
    """Return a verified global integer optimum, or explicit SEARCH_LIMIT.

    Numeric decimal strings are accepted at the input boundary. Capital is
    restricted to the frozen 5k/25k/100k Stage A scenarios, with 20% simulated
    loss budgets. Inputs must already have passed the caller's provenance,
    causality, calendar and completeness audit. This function cannot audit
    their timestamps or prove that the supplied signs were computed causally.
    """
    verify_frozen_protocol()
    return _size_from_covariance(estimate_covariance(dollar_movements), signs,
                                 equity, max_nodes=max_nodes)


def _size_from_covariance(sigma, signs, equity=5000, *, max_nodes=2_000_000) -> dict:
    """Internal numerical seam for tests; production uses size_stage_a."""
    signs = _validated_signs(signs)
    if isinstance(equity, bool) or Decimal(str(equity)) not in map(Decimal, (5000, 25000, 100000)):
        raise ValueError("Stage A capital must be 5000, 25000, or 100000")
    equity = int(Decimal(str(equity)))
    if isinstance(max_nodes, bool) or not isinstance(max_nodes, int) or max_nodes < 1:
        raise ValueError("max_nodes must be a positive integer")
    sigma = np.asarray(sigma, dtype=float)
    if sigma.shape != (5, 5) or not np.isfinite(sigma).all() or np.any(np.diag(sigma) <= 0):
        raise ValueError("A finite positive-variance five-market covariance is required")
    if not np.allclose(sigma, sigma.T, rtol=0, atol=1e-12):
        raise ValueError("Covariance is not symmetric")
    vol = np.sqrt(np.diag(sigma))
    correlation = sigma / np.outer(vol, vol)
    # Both the shrinkage lower bound and stable Schur bounds rely on this.
    if np.linalg.eigvalsh(correlation).min() < 0.5 - 1e-12:
        raise ValueError("Covariance violates the frozen 50% diagonal-shrink lower bound")
    tau = 0.08 * equity
    budget_units = equity * MONEY_SCALE // 5
    funding_units = (equity - 100) * MONEY_SCALE
    initial = tuple(a if s >= 0 else b for s, a, b in zip(signs, INITIAL_LONG, INITIAL_SHORT))
    maintenance = tuple(a if s >= 0 else b for s, a, b in zip(signs, MAINTENANCE_LONG, MAINTENANCE_SHORT))
    funding_charge = tuple(w + 2 * m for w, m in zip(CHARGE, initial))
    active = [i for i, s in enumerate(signs) if s]
    q_star = np.zeros(5)
    if active:
        u = np.asarray(signs, dtype=float) / vol
        q_star = tau * u / np.sqrt(u @ sigma @ u)
    zero = (0, 0, 0, 0, 0)
    best = zero
    best_j = float(q_star @ sigma @ q_star / tau**2)
    best_rank = _rank(best_j, best)
    counters = {name: 0 for name in ("nodes", "objective_prunes", "money_prunes",
                                    "group_prunes", "partial_risk_prunes", "concentration_rejections",
                                    "terminal_candidates_evaluated", "feasible_nonzero_evaluated")}
    necessary_failures = []
    bounds = [0] * 5
    for i in active:
        # A one-sleeve fill incurs costs before its equity-based risk check.
        risk_bound = tau * (1 + FEASIBILITY_ATOL) / (vol[i] + 0.08 * EXECUTION[i] / MONEY_SCALE)
        bounds[i] = min(int(np.floor(risk_bound)), budget_units // CHARGE[i],
                        funding_units // funding_charge[i])
    eligible = [i for i in active if bounds[i] >= 1]
    eligible_groups = {GROUPS[i] for i in eligible}
    if len({GROUPS[i] for i in active}) < 3:
        necessary_failures.append("fewer_than_three_nonzero_signal_groups")
    elif len(eligible_groups) < 3:
        necessary_failures.append("fewer_than_three_groups_with_one_contract_within_singleton_risk_and_money_caps")
    group_min = [min(vol[i]**2 for i in eligible if GROUPS[i] == group)
                 for group in sorted(eligible_groups)]
    minimum_three_group_sum = sum(sorted(group_min)[:3]) if len(group_min) >= 3 else None
    if minimum_three_group_sum is not None and minimum_three_group_sum > 2 * tau**2 * (1 + FEASIBILITY_ATOL)**2:
        necessary_failures.append("three_group_shrinkage_lower_bound_exceeds_risk_cap")

    peak_for_best = 0.0
    limit_hit = False
    if active and not necessary_failures:
        # Volatility normalization keeps eigenvalues in [0.5, 3], avoiding
        # ill-conditioned raw-dollar Schur complements. Prefix minima allow
        # arbitrary real remaining quantities: a valid optimistic lower bound.
        active = eligible
        indices = np.asarray(active)
        directions = np.asarray(signs)[indices]
        corr = correlation[np.ix_(indices, indices)] * np.outer(directions, directions)
        unit_vol = vol[indices] / tau
        target = np.abs(q_star[indices]) * unit_vol
        dimension = len(active)
        schur = [np.empty((0, 0))]
        for depth in range(1, dimension + 1):
            block = corr[:depth, :depth]
            if depth < dimension:
                cross = corr[:depth, depth:]
                block = block - cross @ np.linalg.solve(corr[depth:, depth:], cross.T)
            schur.append(block)
        masks = [np.asarray(list(product((0.0, 1.0), repeat=d))) for d in range(1, dimension + 1)]
        magnitude = [0] * dimension
        # Excluded zero-bound signal sleeves still have nonzero target. They
        # cannot be dropped from J. Keep all five coordinates for its lower
        # bound by conditioning the original target on those fixed zeros.
        fixed = [i for i in range(5) if i not in active]
        signed_correlation = correlation * np.outer(np.where(np.asarray(signs) == 0, 1, signs),
                                                    np.where(np.asarray(signs) == 0, 1, signs))
        full_target = np.abs(q_star) * vol / tau
        fixed_delta = -full_target[fixed]
        cross_fixed = signed_correlation[np.ix_(indices, fixed)] @ fixed_delta
        shift = np.linalg.solve(corr, cross_fixed)
        objective_target = target - shift
        objective_constant = float(fixed_delta @ signed_correlation[np.ix_(fixed, fixed)] @ fixed_delta
                                   - cross_fixed @ np.linalg.solve(corr, cross_fixed))
        def visit(depth, used_loss, used_funding):
            nonlocal best, best_j, best_rank, peak_for_best, limit_hit
            if counters["nodes"] >= max_nodes:
                limit_hit = True
                return
            counters["nodes"] += 1
            if depth:
                prefix = np.asarray(magnitude[:depth])
                delta = prefix * unit_vol[:depth] - objective_target[:depth]
                lower = float(delta @ schur[depth] @ delta + objective_constant)
                if lower > best_rank[0] + 0.5e-12 + BOUND_PAD:
                    counters["objective_prunes"] += 1
                    return
                fill_coordinates = masks[depth - 1] * (prefix * unit_vol[:depth])
                variances = np.einsum("ij,jk,ik->i", fill_coordinates, corr[:depth, :depth], fill_coordinates)
                costs_fraction = masks[depth - 1] @ (prefix * np.asarray([EXECUTION[i] for i in active[:depth]]) / (MONEY_SCALE * equity))
                partial_peak = float(np.max(np.sqrt(np.maximum(variances, 0)) + costs_fraction))
                if partial_peak > 1 + FEASIBILITY_ATOL:
                    counters["partial_risk_prunes"] += 1
                    return
            else:
                partial_peak = 0.0
            present_groups = {GROUPS[active[j]] for j in range(depth) if magnitude[j]}
            possible_groups = present_groups | {GROUPS[i] for i in active[depth:]}
            if len(possible_groups) < 3:
                counters["group_prunes"] += 1
                return
            if depth == dimension:
                if len(present_groups) < 3:
                    counters["group_prunes"] += 1
                    return
                counters["terminal_candidates_evaluated"] += 1
                standalone = np.asarray(magnitude) * unit_vol
                if 2 * float(standalone.max()) > float(standalone.sum()) + FEASIBILITY_ATOL:
                    counters["concentration_rejections"] += 1
                    return
                counters["feasible_nonzero_evaluated"] += 1
                candidate = [0] * 5
                for i, n in zip(active, magnitude):
                    candidate[i] = n
                candidate = tuple(candidate)
                delta_full = np.asarray(candidate) * vol / tau - full_target
                j = float(delta_full @ signed_correlation @ delta_full)
                rank = _rank(j, candidate)
                if rank < best_rank:
                    best, best_j, best_rank, peak_for_best = candidate, j, rank, partial_peak
                return
            i = active[depth]
            upper = min(bounds[i], (budget_units - used_loss) // CHARGE[i],
                        (funding_units - used_funding) // funding_charge[i])
            counters["money_prunes"] += bounds[i] - upper
            ideal = objective_target[depth] / unit_vol[depth]
            for n in sorted(range(upper + 1), key=lambda n: (abs(n - ideal), n)):
                magnitude[depth] = n
                visit(depth + 1, used_loss + n * CHARGE[i], used_funding + n * funding_charge[i])
                if limit_hit:
                    return

        visit(0, 0, 0)

    def dollars(values):
        return sum(n * x for n, x in zip(best, values)) / MONEY_SCALE

    entry_cost = dollars(EXECUTION)
    price_stress = dollars(SHOCK)
    initial_margin, maintenance_margin = dollars(initial), dollars(maintenance)
    signed_best = [s * n for s, n in zip(signs, best)]
    variance = float(np.asarray(signed_best) @ sigma @ np.asarray(signed_best))
    verified = not limit_hit
    nonzero_witness = counters["feasible_nonzero_evaluated"] > 0
    infeasibility_proved = bool(necessary_failures) or not active or (
        verified and not nonzero_witness and counters["objective_prunes"] == 0)
    return {
        "status": "OPTIMAL" if verified else "SEARCH_LIMIT",
        "optimum_verified": verified,
        "decision": ("NONZERO" if any(best) else "CASH") if verified else "UNRESOLVED",
        "quantities": signed_best if verified else None,
        "incumbent_quantities": signed_best,
        "protocol_sha256": PROTOCOL_SHA256,
        "scope": "Stage A independent from-cash sizing; hypothetical parent exposures; no strategy returns",
        "symbols": list(SYMBOLS), "signs": list(signs), "equity_usd": equity,
        "simulated_loss_budget_usd": equity / 5,
        "pre_entry_annual_dollar_vol_target_usd": tau,
        "annual_covariance": sigma.tolist(), "annual_standalone_vol_usd": vol.tolist(),
        "continuous_target_quantities": q_star.tolist(),
        "incumbent_tracking_objective": best_j,
        "incumbent_tracking_objective_rounded_12": best_rank[0],
        "incumbent_entry_cost_usd": entry_cost,
        "incumbent_exit_reserve_usd": entry_cost,
        "incumbent_stress_price_loss_usd": price_stress,
        "incumbent_loss_budget_charge_usd": 2 * entry_cost + price_stress,
        "incumbent_initial_margin_usd": initial_margin,
        "incumbent_maintenance_margin_usd": maintenance_margin,
        "incumbent_funding_headroom_usd": equity - 2 * entry_cost - price_stress - 2 * initial_margin - 100,
        "incumbent_post_entry_equity_usd": equity - entry_cost,
        "incumbent_post_entry_annual_dollar_vol_cap_usd": 0.08 * (equity - entry_cost),
        "incumbent_terminal_annual_dollar_vol_usd": float(np.sqrt(max(0, variance))),
        "incumbent_max_partial_risk_norm_plus_cost_fraction": peak_for_best,
        "nonzero_feasibility": ("WITNESS_FOUND" if nonzero_witness else
                                "PROVED_INFEASIBLE" if infeasibility_proved else "NOT_RESOLVED"),
        "necessary_failures": necessary_failures, "per_market_quantity_upper_bounds": bounds,
        "minimum_three_group_squared_standalone_vol": minimum_three_group_sum,
        "search": {**counters, "max_nodes": max_nodes,
                   "objective_pruning_pad": BOUND_PAD, "normalized_feasibility_allowance": FEASIBILITY_ATOL,
                   "method": "finite integer branch-and-bound with unconstrained Schur lower bounds"},
        "partial_fill_treatment": "All empty/full sleeve vertices cover the from-cash quantity box: norm(q)+0.08*C(q) is convex. State E=initial E minus incurred entry costs; D=incurred costs. Positive additive stress/funding charges attain their maximum at the completed basket. No entry cost is deducted twice.",
    }
