"""Verified integer transitions under BA-012's unchanged risk/cost policies.

No prices, P&L, orders, or implicit liquidation. The caller supplies current
equity/high water, fixed account loss budget, covariance and existing holdings.
Optional transitions include their starting state. If it already violates a
hard limit, mandatory protection belongs to the caller, not this optimizer.

Money uses Decimal(str(input)) and exact frozen per-unit costs. Risk uses the
old solver's normalized float64 tolerance and outward objective-bound padding.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from itertools import product
import math

import numpy as np

try:
    import ba012_sizing as base
except ModuleNotFoundError:
    from tools import ba012_sizing as base

SCALE = Decimal(base.MONEY_SCALE)
COST = tuple(Decimal(x) / SCALE for x in base.EXECUTION)
SHOCK = tuple(Decimal(x) / SCALE for x in base.SHOCK)


def _money(value, name, *, positive=False):
    try:
        if isinstance(value, (bool, np.bool_)):
            raise ValueError
        result = Decimal(str(value))
        if not result.is_finite() or (result <= 0 if positive else result < 0):
            raise ValueError
        if not math.isfinite(float(result)):
            raise ValueError
        return result
    except (ValueError, InvalidOperation, OverflowError) as exc:
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}") from exc


def _integers(values, name, *, nonnegative=False):
    try:
        raw = tuple(values)
        if len(raw) != 5 or any(isinstance(x, (bool, np.bool_)) for x in raw):
            raise ValueError
        decimal = tuple(Decimal(str(x)) for x in raw)
        if any(not x.is_finite() or x != x.to_integral_value() or (nonnegative and x < 0) for x in decimal):
            raise ValueError
        return tuple(int(x) for x in decimal)
    except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
        raise ValueError(f"{name} must contain five {'nonnegative ' if nonnegative else ''}integers") from exc


def _sign(value):
    return (value > 0) - (value < 0)


class _Context:
    def __init__(self, sigma, signs, equity, high_water, loss_budget, holdings,
                 roll_mask, component_upper_bound, component_lower_bound, reduction_only):
        self.sigma = np.asarray(sigma, dtype=float)
        if (self.sigma.shape != (5, 5) or not np.isfinite(self.sigma).all()
                or np.any(np.diag(self.sigma) <= 0)
                or not np.allclose(self.sigma, self.sigma.T, rtol=0, atol=1e-12)):
            raise ValueError("A finite symmetric positive-variance five-market covariance is required")
        self.vol = np.sqrt(np.diag(self.sigma))
        self.correlation = self.sigma / np.outer(self.vol, self.vol)
        if np.linalg.eigvalsh(self.correlation).min() < .5 - 1e-12:
            raise ValueError("Covariance violates the frozen 50% diagonal-shrink lower bound")
        self.signs = base._validated_signs(signs)
        self.equity = _money(equity, "equity", positive=True)
        self.high_water = _money(high_water, "high_water")
        self.budget = _money(loss_budget, "loss_budget", positive=True)
        self.drawdown = max(Decimal(0), self.high_water - self.equity)
        self.p = _integers(holdings, "holdings")
        self.roll = tuple(False for _ in range(5)) if roll_mask is None else tuple(roll_mask)
        if len(self.roll) != 5 or any(not isinstance(x, (bool, np.bool_)) for x in self.roll):
            raise ValueError("roll_mask must contain five booleans")
        self.upper = None if component_upper_bound is None else _integers(component_upper_bound, "component_upper_bound", nonnegative=True)
        self.lower = (0, 0, 0, 0, 0) if component_lower_bound is None else _integers(component_lower_bound, "component_lower_bound", nonnegative=True)
        if not isinstance(reduction_only, (bool, np.bool_)):
            raise ValueError("reduction_only must be boolean")
        self.reduction_only = bool(reduction_only)
        self.tau = .08 * float(self.equity)
        if not math.isfinite(self.tau) or self.tau <= 0:
            raise ValueError("Equity cannot be normalized safely")
        self.unit_vol = self.vol / self.tau
        self.q_star = np.zeros(5)
        if any(self.signs):
            u = np.asarray(self.signs) / self.vol
            self.q_star = self.tau * u / np.sqrt(u @ self.sigma @ u)
        if not np.isfinite(self.q_star).all() or not np.isfinite(self.unit_vol).all():
            raise ValueError("Target/risk normalization is nonfinite")
        self.start_norm = self.norm(self.p)

    def norm(self, quantity):
        z = np.asarray(quantity, dtype=float) * self.unit_vol
        return math.sqrt(max(0.0, float(z @ self.correlation @ z)))

    def bridge(self, q):
        return tuple(0 if roll or old * new < 0 else _sign(old) * min(abs(old), abs(new))
                     for old, new, roll in zip(self.p, q, self.roll))


def _cost_units(left, right):
    return sum(abs(a - b) * cost for a, b, cost in zip(left, right, base.EXECUTION))


def _state(context, quantity, paid_units, phase, initial_required):
    """Hard limits only. Diversification/directions belong to terminal q."""
    paid = Decimal(paid_units) / SCALE
    loss = sum(abs(n) * value for n, value in zip(quantity, SHOCK))
    reserve = sum(abs(n) * value for n, value in zip(quantity, COST))
    maintenance = Decimal(sum(abs(n) * (long if n >= 0 else short)
                              for n, long, short in zip(quantity, base.MAINTENANCE_LONG, base.MAINTENANCE_SHORT))) / SCALE
    initial = Decimal(sum(abs(n) * (long if n >= 0 else short)
                          for n, long, short in zip(quantity, base.INITIAL_LONG, base.INITIAL_SHORT))) / SCALE
    loss_headroom = context.budget - context.drawdown - paid - loss - reserve
    remaining = context.equity - paid - loss - reserve - 100
    maintenance_headroom = remaining - 2 * maintenance
    initial_headroom = remaining - 2 * initial
    norm = context.norm(quantity)
    adjusted_norm = norm + float(paid / context.equity)
    violations = []
    if adjusted_norm > 1 + base.FEASIBILITY_ATOL:
        violations.append("volatility_cap")
    if loss_headroom < 0:
        violations.append("loss_budget")
    if maintenance_headroom < 0:
        violations.append("maintenance_funding")
    if initial_required and initial_headroom < 0:
        violations.append("initial_funding")
    return {"phase": phase, "quantities": list(quantity), "incurred_stressed_cost_usd": float(paid),
            "equity_after_cost_usd": float(context.equity - paid),
            "forecast_volatility_usd": norm * context.tau,
            "forecast_volatility_cap_usd": .08 * float(context.equity - paid),
            "normalized_volatility_plus_cost_fraction": adjusted_norm,
            "stress_price_loss_usd": float(loss), "exit_reserve_usd": float(reserve),
            "maintenance_margin_usd": float(maintenance), "initial_margin_usd": float(initial),
            "loss_budget_headroom_usd": float(loss_headroom),
            "maintenance_funding_headroom_usd": float(maintenance_headroom),
            "initial_funding_headroom_usd": float(initial_headroom),
            "initial_margin_required": bool(initial_required), "violations": violations}


def _phase_vertices(start, end):
    varying = [i for i, (a, b) in enumerate(zip(start, end)) if a != b]
    for flags in product((False, True), repeat=len(varying)):
        q = list(start)
        for i, filled in zip(varying, flags):
            if filled:
                q[i] = end[i]
        yield tuple(q)


def _audit(context, q, *, include_states, early_stop=False):
    bridge = context.bridge(q)
    exit_cost = _cost_units(context.p, bridge)
    entry_cost = _cost_units(bridge, q)
    total_cost = exit_cost + entry_cost
    terminal_violations = []
    if any(n and _sign(n) != s for n, s in zip(q, context.signs)):
        terminal_violations.append("direction_constraint")
    if context.upper is not None and any(abs(n) > upper for n, upper in zip(q, context.upper)):
        terminal_violations.append("component_upper_bound")
    if any(abs(n) < lower for n, lower in zip(q, context.lower)):
        terminal_violations.append("component_lower_bound")
    if context.reduction_only:
        if any(abs(n) > abs(p) or n * p < 0 for n, p in zip(q, context.p)):
            terminal_violations.append("reduction_only_constraint")
        if context.norm(q) > context.start_norm + base.FEASIBILITY_ATOL:
            terminal_violations.append("reduction_increases_terminal_risk")
    if any(q):
        if sum(bool(n) for n in q) < 3 or len({g for n, g in zip(q, base.GROUPS) if n}) < 3:
            terminal_violations.append("terminal_diversification")
        standalone = np.abs(np.asarray(q)) * context.unit_vol
        if 2 * float(standalone.max()) > float(standalone.sum()) + base.FEASIBILITY_ATOL:
            terminal_violations.append("terminal_concentration")
    terminal = _state(context, q, total_cost, "terminal", bool(entry_cost))
    terminal_violations.extend(terminal["violations"])
    terminal["violations"] = sorted(set(terminal_violations))
    violations = set(terminal_violations)
    states = []
    if not (early_stop and violations):
        for phase, start, end, prior_cost in (("exits", context.p, bridge, 0), ("entries", bridge, q, exit_cost)):
            for state in _phase_vertices(start, end):
                phase_cost = _cost_units(start, state)
                check = _state(context, state, prior_cost + phase_cost, phase,
                               phase == "entries" and bool(phase_cost))
                states.append(check)
                violations.update(check["violations"])
                if early_stop and violations:
                    break
            if early_stop and violations:
                break
    start = _state(context, context.p, 0, "starting", False)
    violations.update(start["violations"])
    result = {"feasible": not violations, "violations": sorted(violations),
              "terminal_feasible": not terminal_violations, "terminal": terminal,
              "starting_state_feasible": not start["violations"], "starting_state": start,
              "bridge_quantities": list(bridge), "exit_quantities": [p - x for p, x in zip(context.p, bridge)],
              "entry_quantities": [n - x for n, x in zip(q, bridge)],
              "stressed_exit_cost_usd": float(Decimal(exit_cost) / SCALE),
              "stressed_entry_cost_usd": float(Decimal(entry_cost) / SCALE),
              "stressed_transition_cost_usd": float(Decimal(total_cost) / SCALE),
              "initial_drawdown_usd": float(context.drawdown),
              "phase_vertex_count_evaluated": len(states),
              "partial_state_failures": [state for state in states if state["violations"]]}
    if include_states:
        result["phase_vertices"] = states
    return result


def audit_transition(sigma, signs, equity, high_water, loss_budget, holdings, quantities, *,
                     roll_mask=None, component_upper_bound=None, component_lower_bound=None,
                     reduction_only=False, include_states=True):
    """Audit optional p→x→q at fixed prices/Sigma and cumulative stressed costs.

    At most 32 vertices per phase suffice: each coordinate stays in one sign
    within a phase, cost is affine, and norm plus cost is convex. The money
    functions are convex too. Terminal group/concentration rules do not apply
    to a first fill. Initial margin is needed once an entry/replacement fills.
    """
    context = _Context(sigma, signs, equity, high_water, loss_budget, holdings,
                       roll_mask, component_upper_bound, component_lower_bound, reduction_only)
    return _audit(context, _integers(quantities, "quantities"), include_states=include_states)


def audit_holdings(sigma, equity, high_water, loss_budget, holdings, *, include_states=False):
    """Current hold audit, independent of a new month's direction or roll plan."""
    holdings = _integers(holdings, "holdings")
    return audit_transition(sigma, [_sign(n) for n in holdings], equity, high_water,
                            loss_budget, holdings, holdings, include_states=include_states)


def _near_integers(upper, ideal):
    """Nearest-first deterministic traversal without allocating a huge range."""
    if ideal <= 0:
        yield from range(upper + 1)
        return
    if ideal >= upper:
        yield from range(upper, -1, -1)
        return
    left = int(math.floor(ideal))
    right = left + 1
    while left >= 0 or right <= upper:
        if right > upper or (left >= 0 and ideal - left <= right - ideal):
            yield left
            left -= 1
        else:
            yield right
            right += 1


def optimize_transition(sigma, signs, equity, high_water, loss_budget, holdings, *,
                        roll_mask=None, component_upper_bound=None, component_lower_bound=None, reduction_only=False,
                        max_nodes=2_000_000):
    """Global integer optimum or explicit infeasibility/unresolved search.

    Bounds omit future C conservatively, use maintenance rather than initial
    for existing holdings, and use sqrt(2)*tau/v from diagonal shrinkage.
    The stronger from-cash singleton bound is NOT valid for held hedges.
    """
    base.verify_frozen_protocol()
    context = _Context(sigma, signs, equity, high_water, loss_budget, holdings,
                       roll_mask, component_upper_bound, component_lower_bound, reduction_only)
    if isinstance(max_nodes, bool) or not isinstance(max_nodes, int) or max_nodes < 1:
        raise ValueError("max_nodes must be a positive integer")
    counts = {"nodes": 0, "objective_prunes": 0, "money_prunes": 0, "group_prunes": 0,
              "terminal_evaluations": 0, "feasible_candidates": 0, "max_nodes": max_nodes}
    starting = _state(context, context.p, 0, "starting", False)
    best = None
    best_rank = None
    best_objective = None
    best_audit = None
    limit_hit = False
    bounds = [0] * 5
    loss_weights = [Decimal(b + c) / SCALE for b, c in zip(base.SHOCK, base.EXECUTION)]
    maintenance_side = [long if s >= 0 else short for s, long, short in zip(context.signs, base.MAINTENANCE_LONG, base.MAINTENANCE_SHORT)]
    funding_weights = [loss + Decimal(2 * m) / SCALE for loss, m in zip(loss_weights, maintenance_side)]
    loss_room = context.budget - context.drawdown
    funding_room = context.equity - 100
    if not starting["violations"]:
        for i, sign in enumerate(context.signs):
            if not sign or (context.reduction_only and (context.p[i] == 0 or _sign(context.p[i]) != sign)):
                continue
            bounds[i] = max(0, min(int(math.floor(math.sqrt(2) / context.unit_vol[i] * (1 + 2 * base.FEASIBILITY_ATOL))),
                                   int(loss_room // loss_weights[i]), int(funding_room // funding_weights[i])))
            if context.upper is not None:
                bounds[i] = min(bounds[i], context.upper[i])
            if context.reduction_only:
                bounds[i] = min(bounds[i], abs(context.p[i]))

        def consider(q):
            nonlocal best, best_rank, best_objective, best_audit
            counts["terminal_evaluations"] += 1
            audit = _audit(context, q, include_states=False, early_stop=True)
            if not audit["feasible"]:
                return
            counts["feasible_candidates"] += 1
            delta = (np.asarray(q) - context.q_star) * context.unit_vol
            objective = float(delta @ context.correlation @ delta)
            bridge = context.bridge(q)
            cost = _cost_units(context.p, bridge) + _cost_units(bridge, q)
            stress = sum(abs(n) * b for n, b in zip(q, base.SHOCK))
            magnitude = tuple(abs(n) for n in q)
            rank = (round(objective, 12), cost, stress, magnitude)
            if best_rank is None or rank < best_rank:
                best, best_rank, best_objective, best_audit = q, rank, objective, audit

        zero = (0, 0, 0, 0, 0)
        seeds = [zero, context.p]
        for rounding in (math.floor, round):
            seeds.append(tuple(s * min(upper, max(0, int(rounding(abs(target)))))
                               for s, upper, target in zip(context.signs, bounds, context.q_star)))
        for seed in dict.fromkeys(seeds):
            if all(lower <= abs(n) <= upper for n, lower, upper in zip(seed, context.lower, bounds)):
                consider(seed)

        active = [i for i, upper in enumerate(bounds) if upper]
        if active and all(lower <= upper for lower, upper in zip(context.lower, bounds)):
            indices = np.asarray(active)
            direction = np.where(np.asarray(context.signs) == 0, 1, context.signs)
            signed_correlation = context.correlation * np.outer(direction, direction)
            corr = signed_correlation[np.ix_(indices, indices)]
            full_target = np.abs(context.q_star) * context.unit_vol
            target = full_target[indices]
            fixed = [i for i in range(5) if i not in active]
            fixed_delta = -full_target[fixed]
            cross_fixed = signed_correlation[np.ix_(indices, fixed)] @ fixed_delta
            shift = np.linalg.solve(corr, cross_fixed)
            objective_target = target - shift
            constant = float(fixed_delta @ signed_correlation[np.ix_(fixed, fixed)] @ fixed_delta
                             - cross_fixed @ shift)
            dimension = len(active)
            schur = [np.empty((0, 0))]
            for depth in range(1, dimension + 1):
                block = corr[:depth, :depth]
                if depth < dimension:
                    cross = corr[:depth, depth:]
                    block = block - cross @ np.linalg.solve(corr[depth:, depth:], cross.T)
                schur.append(block)
            magnitude = [0] * dimension

            def visit(depth, used_loss, used_funding):
                nonlocal limit_hit
                if counts["nodes"] >= max_nodes:
                    limit_hit = True
                    return
                counts["nodes"] += 1
                if depth:
                    delta = np.asarray(magnitude[:depth]) * context.unit_vol[indices[:depth]] - objective_target[:depth]
                    lower = float(delta @ schur[depth] @ delta + constant)
                    if best_rank is not None and lower > best_rank[0] + .5e-12 + base.BOUND_PAD:
                        counts["objective_prunes"] += 1
                        return
                possible_groups = {base.GROUPS[active[j]] for j in range(depth) if magnitude[j]} | {base.GROUPS[i] for i in active[depth:]}
                if len(possible_groups) < 3:
                    # Cash was audited independently before search.
                    counts["group_prunes"] += 1
                    return
                if depth == dimension:
                    q = [0] * 5
                    for i, n in zip(active, magnitude):
                        q[i] = context.signs[i] * n
                    consider(tuple(q))
                    return
                i = active[depth]
                upper = min(bounds[i], int((loss_room - used_loss) // loss_weights[i]),
                            int((funding_room - used_funding) // funding_weights[i]))
                counts["money_prunes"] += bounds[i] - upper
                lower_quantity = context.lower[i]
                if upper < lower_quantity:
                    counts["money_prunes"] += 1
                    return
                ideal = objective_target[depth] / context.unit_vol[i]
                for offset in _near_integers(upper - lower_quantity, ideal - lower_quantity):
                    n = lower_quantity + offset
                    magnitude[depth] = n
                    visit(depth + 1, used_loss + n * loss_weights[i], used_funding + n * funding_weights[i])
                    if limit_hit:
                        return

            visit(0, Decimal(0), Decimal(0))

    status = "SEARCH_LIMIT" if limit_hit else "OPTIMAL" if best is not None else "NO_FEASIBLE_TRANSITION"
    return {"status": status, "quantities": list(best) if status == "OPTIMAL" else None,
            "objective": best_objective if status == "OPTIMAL" else None,
            "objective_rounded_12": best_rank[0] if status == "OPTIMAL" else None,
            "optimum_verified": status == "OPTIMAL", "infeasibility_verified": status == "NO_FEASIBLE_TRANSITION",
            "incumbent_quantities": list(best) if best is not None else None,
            "incumbent_objective": best_objective, "audit": best_audit if best_audit is not None else {
                "feasible": False, "terminal_feasible": False,
                "violations": starting["violations"] or ["no_feasible_optional_transition"], "starting_state": starting},
            "continuous_target_quantities": context.q_star.tolist(), "per_market_quantity_upper_bounds": bounds,
            "per_market_quantity_lower_bounds": list(context.lower),
            "search": counts | {"complete": not limit_hit, "method": "finite branch-and-bound with normalized Schur lower bounds",
                                 "objective_bound_padding": base.BOUND_PAD, "risk_roundoff_allowance": base.FEASIBILITY_ATOL},
            "protocol_sha256": base.PROTOCOL_SHA256,
            "scope": "Optional transitions only; caller handles mandatory protective liquidation and actual fills"}
