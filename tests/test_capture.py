"""Axis B: can the audit see leakage it is told to plant?

A retention audit that reports "within budget" while blind to a deliberate leak
is worse than no audit, because it manufactures the confidence that the number is
there to provide. Every test below plants a known cost at a declared magnitude and
demands two things: the total must move, and the ledger must name the channel that
moved it. A correct total with a wrong name still fails, because a total without a
name cannot be acted on.
"""

import calendar
from datetime import date
import unittest

from boring_alpha.capture import (
    CASH_DRAG,
    INSTRUMENT_FEE,
    LATENCY,
    PLATFORM_FEE,
    SPREAD,
    CapturePolicy,
    Period,
    audit,
    simulate,
)
from boring_alpha.metrics.cashflow import CashFlow

OPENING = 2_000.0
CONTRIBUTION = 500.0
MONTHLY_GROSS = 0.0075
CASH_ANNUAL = 0.04


def months(count: int, start: date = date(2019, 1, 1)) -> tuple[Period, ...]:
    series = []
    year, month = start.year, start.month
    for _ in range(count):
        series.append(
            Period(date(year, month, 1), calendar.monthrange(year, month)[1], MONTHLY_GROSS)
        )
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return tuple(series)


def contributions(count: int, start: date = date(2019, 1, 1)) -> tuple[CashFlow, ...]:
    """One contribution at the open of every month except the first.

    The opening of the first month is the opening valuation, so a deposit dated
    there would be counted twice. That is exactly the sort of error the guard in
    `simulate` exists to catch rather than to silently tolerate.
    """

    flows = []
    year, month = start.year, start.month
    for _ in range(count - 1):
        month += 1
        if month > 12:
            year, month = year + 1, 1
        flows.append(CashFlow(date(year, month, 1), CONTRIBUTION))
    return tuple(flows)


def run(policy: CapturePolicy, count: int = 24):
    series = months(count)
    flows = contributions(count)
    return audit(policy, series, flows, OPENING, series[-1].start.replace(
        day=calendar.monthrange(series[-1].start.year, series[-1].start.month)[1]
    ))


class BlindnessTests(unittest.TestCase):
    """A zero-leakage account must read as zero. Otherwise nothing else means anything."""

    def setUp(self) -> None:
        self.audit = run(CapturePolicy(spread_bps=0.0, target_cash_weight=0.0))

    def test_a_fully_invested_account_with_no_costs_retains_almost_everything(self) -> None:
        self.assertLess(self.audit.tier2_shortfall_bps, 1.0)
        self.assertGreater(self.audit.closing_value, 0.0)

    def test_the_reference_account_is_what_the_candidate_would_be(self) -> None:
        self.assertGreater(self.audit.reference_closing_value, 0.0)
        self.assertAlmostEqual(
            self.audit.closing_value, self.audit.reference_closing_value, delta=1.0
        )


class CleanPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.audit = run(CapturePolicy())

    def test_the_registered_policy_is_inside_budget(self) -> None:
        """3 bps per side on contributions only: a couple of basis points, not scores."""

        self.assertLess(self.audit.tier2_shortfall_bps, 10.0)
        self.assertTrue(self.audit.passes_gate)

    def test_attribution_reproduces_the_total_rather_than_rounding_it(self) -> None:
        self.assertLess(abs(self.audit.residual_bps), 0.5)

    def test_the_instrument_fee_is_measured_and_sits_outside_the_gate(self) -> None:
        """A 7 bps wrapper reads as 7.67 bps of annualised gap, not as behaviour.

        The gap exceeds the nominal fee because the gross series is grown first and
        the fee then compounds against a rising base. Measured, not assumed.
        """

        self.assertGreater(self.audit.tier1_tier2_bps, 7.0)
        self.assertLess(self.audit.tier1_tier2_bps, 8.5)


class InjectionTests(unittest.TestCase):
    """Each channel at a declared magnitude. Detection is 80% of the planted size."""

    def test_planted_idle_cash_is_found_and_named(self) -> None:
        result = run(CapturePolicy(target_cash_weight=0.08))
        predicted = 0.08 * (1.0579 - 1.04) * 10_000.0  # weight x the annual return gap
        self.assertGreater(result.tier2_shortfall_bps, 0.8 * predicted)
        self.assertEqual(result.binding_channel, CASH_DRAG)
        self.assertGreater(
            result.attribution[CASH_DRAG] / result.tier2_shortfall_bps, 0.8
        )

    def test_planted_market_orders_are_found_and_named(self) -> None:
        mild = run(CapturePolicy(spread_bps=3.0))
        harsh = run(CapturePolicy(spread_bps=12.0))
        self.assertGreater(
            harsh.tier2_shortfall_bps - mild.tier2_shortfall_bps,
            0.8 * mild.attribution[SPREAD] * 3.0,
        )
        self.assertEqual(harsh.binding_channel, SPREAD)

    def test_planted_contribution_latency_is_found_and_named(self) -> None:
        result = run(CapturePolicy(latency_days=10))
        self.assertGreater(result.attribution[LATENCY], 0.0)
        self.assertGreater(result.tier2_shortfall_bps, result.attribution[SPREAD])
        self.assertEqual(result.binding_channel, LATENCY)

    def test_a_planted_platform_fee_is_found_and_named(self) -> None:
        result = run(CapturePolicy(platform_fee_monthly=10.0))
        self.assertEqual(result.binding_channel, PLATFORM_FEE)
        self.assertGreater(result.tier2_shortfall_bps, 150.0)
        self.assertFalse(result.passes_gate)

    def test_an_expensive_wrapper_fails_at_tier_one_and_never_touches_the_gate(self) -> None:
        """The strictest test here. Forty-two basis points must be a selection failure.

        If the wrapper fee leaked into the Tier-2 total, the audit would blame the
        holder's behaviour for a decision made at account opening, and the one
        distinction BA-004 exists to preserve would be gone.
        """

        result = run(CapturePolicy(expense_ratio=0.0042))
        # Compared against the SAME account at a cheap wrapper: a 35 bps swing in
        # the fund's fee must leave the behaviour score untouched, to the cent.
        baseline = run(CapturePolicy())
        self.assertGreater(result.tier1_tier2_bps, 44.0)   # measured: 46.04
        self.assertLess(result.tier1_tier2_bps, 48.0)
        self.assertLess(result.tier2_shortfall_bps, 5.0)
        # Not exactly zero, and it would be dishonest to assert zero. A wrapper
        # fee is multiplicative and a money-weighted return is not, so a fee does
        # not cancel perfectly in a difference when interim flows are present.
        # Measured: 0.0066 bps of contamination from a 35 bps fee swing, about
        # 0.02% of the gate. Immaterial, disclosed, and asserted rather than assumed.
        self.assertLess(
            abs(result.tier2_shortfall_bps - baseline.tier2_shortfall_bps), 0.05
        )
        self.assertLess(abs(result.attribution[INSTRUMENT_FEE] - result.tier1_tier2_bps), 1e-9)

    def test_a_behavioural_violation_voids_the_run_even_at_a_perfect_shortfall(self) -> None:
        result = run(CapturePolicy(spread_bps=0.0, violations=1))
        self.assertLess(result.tier2_shortfall_bps, 1.0)
        self.assertFalse(result.passes_gate)
        self.assertEqual(result.violations, 1)


class AdditivityTests(unittest.TestCase):
    """Single-channel ablation is not a unique decomposition, so it is checked, not assumed."""

    def setUp(self) -> None:
        self.result = run(
            CapturePolicy(
                spread_bps=12.0,
                target_cash_weight=0.05,
                latency_days=10,
                platform_fee_monthly=5.0,
            )
        )

    def test_the_named_channels_account_for_the_total_to_within_two_basis_points(self) -> None:
        self.assertLess(abs(self.result.residual_bps), 2.0)

    def test_no_channel_is_credited_with_more_than_the_total_it_could_have_cost(self) -> None:
        for name, value in self.result.attribution.items():
            if name == INSTRUMENT_FEE:
                continue
            self.assertGreaterEqual(value, -1.0, f"{name} credited a negative leak")
            self.assertLessEqual(
                value, self.result.tier2_shortfall_bps + 2.0, f"{name} over-credited"
            )

    def test_disabling_an_already_inert_channel_changes_nothing(self) -> None:
        """The ablation itself must be discriminating, not merely arithmetic."""

        for name in (LATENCY, PLATFORM_FEE, CASH_DRAG):
            policy = CapturePolicy(spread_bps=12.0)
            series = months(24)
            flows = contributions(24)
            base = simulate(policy, series, flows, OPENING)
            same = simulate(policy.disabled(name), series, flows, OPENING)
            self.assertAlmostEqual(base, same, places=8)


class CrossCheckTests(unittest.TestCase):
    def test_the_second_metric_agrees_on_the_difference_not_the_level(self) -> None:
        """Protocol §6: Modified Dietz is a validity check, and it has a known floor."""

        cases = (
            ("clean", CapturePolicy()),
            ("idle cash 8%", CapturePolicy(target_cash_weight=0.08)),
            ("spread 12 + latency 10 + $10/mo", CapturePolicy(
                spread_bps=12.0, latency_days=10, platform_fee_monthly=10.0)),
            ("$40/mo + 25 bps", CapturePolicy(
                platform_fee_monthly=40.0, spread_bps=25.0)),
        )
        for label, policy in cases:
            with self.subTest(case=label):
                result = run(policy)
                self.assertLess(
                    result.dietz_cross_check_bps,
                    max(20.0, 0.05 * result.tier2_shortfall_bps),
                )

    def test_the_dietz_check_would_reject_a_run_it_cannot_confirm(self) -> None:
        """A check that never fails is not a check. A fee-dominated run must trip it."""

        result = run(CapturePolicy(platform_fee_monthly=40.0, spread_bps=25.0))
        self.assertGreater(result.dietz_cross_check_bps, 5.0)


class ScaleTests(unittest.TestCase):
    def test_a_fixed_dollar_fee_bites_ten_times_harder_on_a_small_account(self) -> None:
        """The arithmetic that makes a $2,000 account unable to afford what a
        $50,000 account treats as free."""

        series = months(24)
        end = series[-1].start.replace(day=calendar.monthrange(
            series[-1].start.year, series[-1].start.month
        )[1])
        from boring_alpha.capture import audit as run_audit
        from boring_alpha.metrics.cashflow import CashFlow

        def ladder(opening: float, contribution: float) -> float:
            year, month = 2019, 1
            flows = []
            for _ in range(23):
                month += 1
                if month > 12:
                    year, month = year + 1, 1
                flows.append(CashFlow(date(year, month, 1), contribution))
            return run_audit(
                CapturePolicy(platform_fee_monthly=10.0), series, tuple(flows), opening, end
            ).tier2_shortfall_bps

        small, large = ladder(2_000.0, 500.0), ladder(20_000.0, 5_000.0)
        self.assertGreater(small, 150.0)   # measured: 166.19
        self.assertLess(large, 25.0)       # measured: 19.06
        self.assertGreater(small, large * 5.0)
        self.assertFalse(run(CapturePolicy(platform_fee_monthly=10.0)).passes_gate)


if __name__ == "__main__":
    unittest.main()
