"""Tests for money-weighted return: the identity checks, not the happy path."""

from datetime import date, timedelta
import math
import unittest

from boring_alpha.metrics.cashflow import (
    AmbiguousCashFlows,
    CashFlow,
    modified_dietz,
    money_weighted_return,
    net_present_value,
    shortfall_bps,
)

JAN_1 = date(2020, 1, 1)


def monthly(start: date, months: int, amount: float) -> tuple[CashFlow, ...]:
    """A contribution on the same day each month, first one excluded."""

    flows = []
    year, month = start.year, start.month
    for index in range(1, months + 1):
        month += 1
        if month > 12:
            year, month = year + 1, 1
        flows.append(CashFlow(date(year, month, start.day), amount))
    return tuple(flows)


class RoundTripTests(unittest.TestCase):
    """The solver must recover a rate that generated the data, to machine noise."""

    def test_recovers_a_known_rate_from_generated_values(self) -> None:
        rate, deposit, opening = 0.07, 500.0, 2_000.0
        months, day = 60, 27
        flows = monthly(JAN_1, months, deposit)
        closing_date = date(2025, 1, 27)
        horizon = (closing_date - JAN_1).days / 365.2425
        closing = opening * (1.0 + rate) ** horizon + sum(
            flow.amount * (1.0 + rate) ** ((closing_date - flow.date).days / 365.2425)
            for flow in flows
        )
        recovered = money_weighted_return(
            JAN_1, opening, closing_date, closing, flows
        )
        self.assertAlmostEqual(rate, recovered, places=10)

    def test_no_external_flows_reduces_to_the_time_weighted_cagr(self) -> None:
        closing_date = date(2023, 1, 1)
        closing = 10_000.0
        # Day-count convention, pinned here so it is a decision and not an accident:
        # this module discounts on day *differences*, so a period counts its days
        # exclusively. performance.py counts inclusively, which is one day longer.
        elapsed = (closing_date - JAN_1).days
        expected = (closing / 8_000.0) ** (365.2425 / elapsed) - 1.0
        self.assertAlmostEqual(
            expected,
            money_weighted_return(JAN_1, 8_000.0, closing_date, closing),
            places=12,
        )

    def test_the_day_count_difference_from_the_inclusive_convention_is_immaterial(self) -> None:
        """The one-day convention gap must be far below any reported basis point."""

        closing_date = date(2023, 1, 1)
        elapsed = (closing_date - JAN_1).days
        exclusive = (10_000.0 / 8_000.0) ** (365.2425 / elapsed) - 1.0
        inclusive = (10_000.0 / 8_000.0) ** (365.2425 / (elapsed + 1)) - 1.0
        self.assertLess(abs(shortfall_bps(exclusive, inclusive)), 1.0)

    def test_a_flat_account_returns_zero_whatever_the_deposit_timing(self) -> None:
        """Principal in, principal out: zero is the only answer, any timing."""

        flows = (
            CashFlow(JAN_1, 1_000.0),
            CashFlow(date(2020, 6, 1), 1_000.0),
            CashFlow(date(2020, 11, 2), 1_000.0),
        )
        self.assertAlmostEqual(
            0.0,
            money_weighted_return(JAN_1, 1_000.0, date(2021, 1, 1), 4_000.0, flows),
            places=10,
        )


class DivergenceTests(unittest.TestCase):
    """Money-weighted and time-weighted must disagree, or this module is pointless."""

    def test_a_crash_before_a_contribution_makes_cagr_lie(self) -> None:
        """The core reason BA-004 may not report CAGR.

        The fund falls 10% while only the opening $1,000 is invested, then $18,000
        arrives afterwards and nothing more moves. Time-weighted, the account lost
        10%. The owner put in $19,000 and holds $18,900: money-weighted, it lost
        about 0.1%. Any report that led with the time-weighted figure would be
        describing a fund, not this account.
        """

        flows = (CashFlow(date(2020, 9, 1), 18_000.0),)
        closing = money_weighted_return(
            JAN_1, 1_000.0, date(2021, 1, 1), 18_900.0, flows
        )
        time_weighted = -0.10
        self.assertGreater(abs(shortfall_bps(closing, time_weighted)), 800.0)
        self.assertGreater(closing, -0.02)

    def test_money_weighted_return_is_untouched_by_size_of_a_single_lump(self) -> None:
        """No flows at all: doubling opening and closing leaves the rate alone."""

        small = money_weighted_return(JAN_1, 1_000.0, date(2022, 1, 1), 1_400.0)
        large = money_weighted_return(JAN_1, 50_000.0, date(2022, 1, 1), 70_000.0)
        self.assertAlmostEqual(small, large, places=12)


class CrossCheckTests(unittest.TestCase):
    def test_the_two_methods_may_disagree_on_level_but_agree_on_shortfall(self) -> None:
        """The audit's quantity of interest is a difference, so that is what agrees.

        Modified Dietz is linear where the internal rate of return is
        multiplicative, so on twelve monthly flows in a rising year the two levels
        legitimately differ by tens of basis points. A flat tolerance on level
        agreement was a naive pin and this test replaces it: candidate and
        reference carry identical flows, so the approximation error is common-mode
        and cancels in the difference. The gap being measured survives; the gap in
        the measuring convention does not.
        """

        flows = monthly(JAN_1, 11, 500.0)
        closing_date = date(2021, 1, 1)
        reference, candidate = 8_830.0, 8_800.0

        def both(closing: float) -> tuple[float, float]:
            return (
                money_weighted_return(JAN_1, 2_000.0, closing_date, closing, flows),
                modified_dietz(JAN_1, 2_000.0, closing_date, closing, flows),
            )

        candidate_irr, candidate_dietz = both(candidate)
        reference_irr, reference_dietz = both(reference)

        # Predicted: the two metrics disagree about the level by far more than
        # any reporting tolerance would forgive.
        self.assertGreater(abs(shortfall_bps(candidate_dietz, candidate_irr)), 15.0)
        # Required: on the difference being audited, they agree tightly, because
        # both accounts carry identical flows and the error cancels.
        irr_gap = shortfall_bps(candidate_irr, reference_irr)
        dietz_gap = shortfall_bps(candidate_dietz, reference_dietz)
        # Measured on this fixture: the cross-check error is 3.24 bps, roughly a
        # twentieth of the level disagreement and about 10% of the 30 bps gate.
        # The pinned bound is 5 bps; the measurement floor it implies is recorded
        # in the protocol as a limitation, not smoothed into a pass.
        self.assertLess(abs(dietz_gap - irr_gap), 5.0)
        self.assertGreater(abs(dietz_gap - irr_gap), 0.01)

    def test_dietz_diverges_from_irr_when_a_late_lump_arrives(self) -> None:
        """Divergence is diagnostic. A harness that always agrees is not two tests."""

        flows = (CashFlow(date(2020, 12, 20), 50_000.0),)
        closing = 61_000.0
        irr = money_weighted_return(JAN_1, 2_000.0, date(2021, 1, 1), closing, flows)
        dietz = modified_dietz(JAN_1, 2_000.0, date(2021, 1, 1), closing, flows)
        self.assertGreater(abs(shortfall_bps(dietz, irr)), 100.0)


class GuardTests(unittest.TestCase):
    """Every refusal below is a wrong answer prevented."""

    def test_intermediate_withdrawal_is_refused_as_ambiguous(self) -> None:
        flows = (
            CashFlow(date(2020, 6, 1), 5_000.0),
            CashFlow(date(2020, 9, 1), -3_000.0),
        )
        with self.assertRaises(AmbiguousCashFlows):
            money_weighted_return(JAN_1, 2_000.0, date(2021, 1, 1), 4_500.0, flows)

    def test_withdrawal_still_works_for_dietz_which_has_no_root_problem(self) -> None:
        flows = (
            CashFlow(date(2020, 6, 1), 5_000.0),
            CashFlow(date(2020, 9, 1), -3_000.0),
        )
        self.assertTrue(
            math.isfinite(
                modified_dietz(
                    JAN_1, 2_000.0, date(2021, 1, 1), 4_500.0, flows
                )
            )
        )

    def test_deposit_after_the_closing_date_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            money_weighted_return(
                JAN_1, 1_000.0, date(2021, 1, 1), 1_100.0, (CashFlow(date(2021, 6, 1), 500.0),)
            )

    def test_a_wiped_out_account_is_refused_rather_than_reported_as_minus_one_hundred(self) -> None:
        with self.assertRaises(ValueError):
            money_weighted_return(
                JAN_1, 1_000.0, date(2021, 1, 1), 0.0, (CashFlow(date(2020, 5, 1), 500.0),)
            )

    def test_opening_value_must_be_positive(self) -> None:
        for bad in (0.0, -100.0):
            with self.assertRaises(ValueError):
                money_weighted_return(JAN_1, bad, date(2021, 1, 1), 1_000.0)

    def test_zero_length_period_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            money_weighted_return(JAN_1, 1_000.0, JAN_1, 1_000.0)

    def test_flows_before_the_period_start_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            money_weighted_return(
                date(2020, 6, 1),
                1_000.0,
                date(2021, 1, 1),
                1_100.0,
                (CashFlow(date(2020, 1, 1), 500.0),),
            )


class SolverTests(unittest.TestCase):
    def test_present_value_falls_monotonically_as_the_rate_rises(self) -> None:
        flows = monthly(JAN_1, 11, 500.0)
        values = [
            net_present_value(JAN_1, 2_000.0, date(2021, 1, 1), 8_800.0, flows, rate)
            for rate in (0.0, 0.05, 0.2, 1.0)
        ]
        self.assertTrue(all(later < earlier for earlier, later in zip(values, values[1:])))

    def test_a_double_over_a_leap_year_is_not_exactly_one_hundred_percent(self) -> None:
        """The point of the test is that the answer is not 1.000000.

        Assuming 365 days would report exactly 100%. 2020 has 366, and the rate
        is 0.997133. Getting this wrong is immaterial here and fatal over a
        decade of monthly flows, so the day count is asserted rather than trusted.
        """

        rate = money_weighted_return(JAN_1, 1_000.0, date(2021, 1, 1), 2_000.0)
        self.assertLess(rate, 1.0)
        self.assertAlmostEqual(0.997133, rate, places=6)

    def test_shortfall_is_reported_in_basis_points_by_subtraction(self) -> None:
        self.assertAlmostEqual(30.0, shortfall_bps(0.0700, 0.0730), places=9)
        self.assertAlmostEqual(-100.0, shortfall_bps(0.08, 0.07), places=9)

    def test_an_inflated_metric_is_caught_by_bisection_over_the_whole_range(self) -> None:
        """A 10x account in ten years must solve, not wander out of the bracket."""

        flows = monthly(JAN_1, 119, 500.0)
        closing = money_weighted_return(
            JAN_1, 2_000.0, date(2030, 1, 1), 200_000.0, flows
        )
        self.assertTrue(0.0 < closing < 1.0)


if __name__ == "__main__":
    unittest.main()
