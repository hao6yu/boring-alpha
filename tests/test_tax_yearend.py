"""Character, netting and carryovers follow the rules the spec states (§4.5, §4.7)."""

from datetime import date
from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import load_tax_policy
from boring_alpha.tax.yearend import Amounts, is_long_term, net_and_tax, qualifies

POLICY = """
[tax]
distributions_path = "distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.5
[tax.qualified_fraction]
A = 1.0
[tax.gains_class]
A = "standard"
"""


def _policy():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "policy.toml"
        path.write_text(POLICY, encoding="utf-8")
        return load_tax_policy(path, ("A",))


class HoldingPeriodTests(unittest.TestCase):
    def test_more_than_365_days_is_long_term(self) -> None:
        opened = date(2023, 3, 1)
        self.assertFalse(is_long_term(opened, date(2024, 2, 29)))   # 365 days
        self.assertTrue(is_long_term(opened, date(2024, 3, 1)))     # 366 days

    def test_qualified_needs_more_than_sixty_days_inside_the_window(self) -> None:
        ex_date = date(2024, 6, 14)
        opened = date(2024, 5, 15)
        self.assertTrue(qualifies(opened, date(2024, 7, 15), ex_date))    # 61 days held in window
        self.assertFalse(qualifies(opened, date(2024, 7, 14), ex_date))   # 60 days

    def test_days_outside_the_window_do_not_count(self) -> None:
        ex_date = date(2024, 6, 14)
        # April 15 through June 14 inclusive is 61 days; June 13 is only 60.
        self.assertTrue(qualifies(date(2020, 1, 1), date(2024, 6, 14), ex_date))
        self.assertFalse(qualifies(date(2020, 1, 1), date(2024, 6, 13), ex_date))

    def test_acquisition_on_the_window_start_excludes_that_day(self) -> None:
        ex_date = date(2024, 6, 14)
        # The window starts April 15. Buying that day leaves April 16 through
        # June 14 (60 days); buying April 14 includes all 61 window days.
        self.assertFalse(qualifies(date(2024, 4, 15), date(2024, 6, 14), ex_date))
        self.assertTrue(qualifies(date(2024, 4, 14), date(2024, 6, 14), ex_date))

    def test_the_window_end_is_inclusive_and_later_days_cannot_help(self) -> None:
        ex_date = date(2024, 6, 14)
        # June 14 through August 13 inclusive is 61 days. June 15 through
        # August 13 is 60, even if the lot remains open beyond August 13.
        self.assertTrue(qualifies(date(2024, 6, 13), date(2024, 8, 13), ex_date))
        self.assertFalse(qualifies(date(2024, 6, 14), date(2024, 8, 13), ex_date))
        self.assertFalse(qualifies(date(2024, 6, 14), date(2024, 9, 1), ex_date))

    def test_the_window_may_cross_a_year_end(self) -> None:
        ex_date = date(2024, 12, 20)
        self.assertTrue(qualifies(date(2024, 11, 1), date(2025, 2, 28), ex_date))
        self.assertFalse(qualifies(date(2024, 12, 1), date(2025, 1, 15), ex_date))


class AmountsTests(unittest.TestCase):
    def test_scaled_multiplies_every_field(self) -> None:
        amounts = Amounts(qualified_income=10.0, short_gains=20.0, marks_long=6.0, wash_disallowed=1.0)
        scaled = amounts.scaled(2.0)
        self.assertAlmostEqual(scaled.qualified_income, 20.0)
        self.assertAlmostEqual(scaled.short_gains, 40.0)
        self.assertAlmostEqual(scaled.marks_long, 12.0)
        self.assertAlmostEqual(scaled.wash_disallowed, 2.0)
        self.assertAlmostEqual(amounts.short_gains, 20.0)   # the original is untouched

    def test_gains_route_by_term_and_class(self) -> None:
        amounts = Amounts()
        amounts.add_gain(100.0, long_term=False, gains_class="standard", mark_to_market=False)
        amounts.add_gain(-30.0, long_term=False, gains_class="collectibles", mark_to_market=False)
        amounts.add_gain(50.0, long_term=True, gains_class="standard", mark_to_market=False)
        amounts.add_gain(-20.0, long_term=True, gains_class="standard", mark_to_market=False)
        amounts.add_gain(70.0, long_term=True, gains_class="collectibles", mark_to_market=False)
        amounts.add_gain(-10.0, long_term=True, gains_class="collectibles", mark_to_market=False)
        self.assertEqual((amounts.short_gains, amounts.short_losses), (100.0, 30.0))
        self.assertEqual((amounts.long_gains, amounts.long_losses), (50.0, 20.0))
        self.assertEqual((amounts.collectibles_gains, amounts.collectibles_losses), (70.0, 10.0))

    def test_mark_to_market_splits_sixty_forty_regardless_of_term(self) -> None:
        amounts = Amounts()
        amounts.add_gain(100.0, long_term=False, gains_class="commodity_pool", mark_to_market=True)
        amounts.add_gain(-50.0, long_term=True, gains_class="commodity_pool", mark_to_market=True)
        self.assertAlmostEqual(amounts.marks_long, 30.0)
        self.assertAlmostEqual(amounts.marks_short, 20.0)
        self.assertEqual(amounts.short_gains, 0.0)

    def test_as_dict_lists_every_field(self) -> None:
        record = Amounts(cash_interest=3.0).as_dict()
        self.assertEqual(record["cash_interest"], 3.0)
        self.assertEqual(len(record), 13)


class NettingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tax = _policy()

    def test_a_short_gain_is_taxed_at_the_ordinary_rate(self) -> None:
        year = net_and_tax(Amounts(short_gains=100.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 35.0)
        self.assertAlmostEqual(year.short_carry_out, 0.0)

    def test_a_short_loss_offsets_a_long_gain_and_the_rest_carries_as_short(self) -> None:
        year = net_and_tax(Amounts(short_losses=100.0, long_gains=50.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 0.0)
        self.assertAlmostEqual(year.long_net, 0.0)
        self.assertAlmostEqual(year.short_carry_out, 50.0)
        self.assertAlmostEqual(year.long_carry_out, 0.0)

    def test_a_short_carryover_reduces_a_short_gain(self) -> None:
        year = net_and_tax(Amounts(short_gains=100.0), 30.0, 0.0, self.tax)
        self.assertAlmostEqual(year.short_carry_used, 30.0)
        self.assertAlmostEqual(year.tax, 70.0 * 0.35)
        self.assertAlmostEqual(year.short_carry_out, 0.0)

    def test_a_long_carryover_offsets_collectibles_first(self) -> None:
        year = net_and_tax(Amounts(collectibles_gains=30.0, long_gains=50.0), 0.0, 40.0, self.tax)
        self.assertAlmostEqual(year.collectibles_net, 0.0)
        self.assertAlmostEqual(year.long_net, 40.0)
        self.assertAlmostEqual(year.long_carry_used, 40.0)
        self.assertAlmostEqual(year.tax, 40.0 * 0.20)

    def test_a_long_loss_offsets_a_short_gain(self) -> None:
        year = net_and_tax(Amounts(short_gains=100.0, long_losses=30.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 70.0 * 0.35)
        self.assertAlmostEqual(year.long_carry_out, 0.0)

    def test_long_losses_net_against_collectibles_gains_before_anything_else(self) -> None:
        year = net_and_tax(Amounts(collectibles_gains=100.0, long_losses=40.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.collectibles_net, 60.0)
        self.assertAlmostEqual(year.tax, 60.0 * 0.28)

    def test_an_unused_long_loss_carries_with_its_character(self) -> None:
        year = net_and_tax(Amounts(long_losses=100.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 0.0)
        self.assertAlmostEqual(year.long_carry_out, 100.0)
        self.assertAlmostEqual(year.short_carry_out, 0.0)

    def test_carryovers_not_needed_this_year_survive(self) -> None:
        year = net_and_tax(Amounts(), 25.0, 15.0, self.tax)
        self.assertAlmostEqual(year.short_carry_used, 0.0)
        self.assertAlmostEqual(year.long_carry_used, 0.0)
        self.assertAlmostEqual(year.short_carry_out, 25.0)
        self.assertAlmostEqual(year.long_carry_out, 15.0)

    def test_short_carry_offsets_long_gain_and_keeps_unused_short_character(self) -> None:
        year = net_and_tax(Amounts(long_gains=100.0), 150.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 0.0)
        self.assertAlmostEqual(year.short_net, -50.0)
        self.assertAlmostEqual(year.long_net, 0.0)
        self.assertAlmostEqual(year.short_carry_used, 100.0)
        self.assertAlmostEqual(year.short_carry_out, 50.0)
        self.assertAlmostEqual(year.long_carry_out, 0.0)

    def test_long_carry_offsets_short_gain_and_keeps_unused_long_character(self) -> None:
        year = net_and_tax(Amounts(short_gains=100.0), 0.0, 150.0, self.tax)
        self.assertAlmostEqual(year.tax, 0.0)
        self.assertAlmostEqual(year.short_net, 0.0)
        self.assertAlmostEqual(year.long_net, -50.0)
        self.assertAlmostEqual(year.long_carry_used, 100.0)
        self.assertAlmostEqual(year.long_carry_out, 50.0)
        self.assertAlmostEqual(year.short_carry_out, 0.0)

    def test_gain_above_opposite_character_carry_keeps_its_tax_rate(self) -> None:
        short_gain = net_and_tax(Amounts(short_gains=100.0), 0.0, 30.0, self.tax)
        self.assertAlmostEqual(short_gain.short_net, 70.0)
        self.assertAlmostEqual(short_gain.tax, 24.5)
        self.assertAlmostEqual(short_gain.long_carry_used, 30.0)
        self.assertAlmostEqual(short_gain.long_carry_out, 0.0)

        long_gain = net_and_tax(Amounts(long_gains=100.0), 30.0, 0.0, self.tax)
        self.assertAlmostEqual(long_gain.long_net, 70.0)
        self.assertAlmostEqual(long_gain.tax, 14.0)
        self.assertAlmostEqual(long_gain.short_carry_used, 30.0)
        self.assertAlmostEqual(long_gain.short_carry_out, 0.0)

    def test_short_carry_offsets_collectibles_before_other_long_gains(self) -> None:
        year = net_and_tax(
            Amounts(collectibles_gains=80.0, long_gains=100.0), 110.0, 0.0, self.tax
        )
        self.assertAlmostEqual(year.collectibles_net, 0.0)
        self.assertAlmostEqual(year.long_net, 70.0)
        self.assertAlmostEqual(year.short_carry_used, 110.0)
        self.assertAlmostEqual(year.short_carry_out, 0.0)
        self.assertAlmostEqual(year.tax, 14.0)

    def test_current_short_losses_and_carry_net_across_both_long_buckets(self) -> None:
        # Current short net is -60; with the prior 50 it is -110. Collectibles
        # absorb 30 and ordinary long gains 60, leaving 20 of short loss.
        year = net_and_tax(
            Amounts(short_gains=20.0, short_losses=80.0,
                    collectibles_gains=30.0, long_gains=60.0),
            50.0, 0.0, self.tax,
        )
        self.assertAlmostEqual(year.tax, 0.0)
        self.assertAlmostEqual(year.short_net, -20.0)
        self.assertAlmostEqual(year.long_net, 0.0)
        self.assertAlmostEqual(year.collectibles_net, 0.0)
        self.assertAlmostEqual(year.short_carry_used, 30.0)
        self.assertAlmostEqual(year.short_carry_out, 20.0)

    def test_current_long_losses_and_carry_net_against_short_gains(self) -> None:
        # 70 of ordinary long loss first nets against 20 of collectibles gain.
        # Adding 40 carried long loss gives -90; 60 short gain leaves -30.
        year = net_and_tax(
            Amounts(short_gains=60.0, long_gains=10.0, long_losses=80.0,
                    collectibles_gains=20.0),
            0.0, 40.0, self.tax,
        )
        self.assertAlmostEqual(year.tax, 0.0)
        self.assertAlmostEqual(year.short_net, 0.0)
        self.assertAlmostEqual(year.long_net, -30.0)
        self.assertAlmostEqual(year.collectibles_net, 0.0)
        self.assertAlmostEqual(year.long_carry_used, 10.0)
        self.assertAlmostEqual(year.long_carry_out, 30.0)

    def test_each_carry_nets_in_its_own_pool_before_cross_character_offset(self) -> None:
        # 100 short gain uses 50 short carry, then 50 of the 100 long carry.
        # The surviving 50 remains long; it must not become short carry.
        year = net_and_tax(Amounts(short_gains=100.0), 50.0, 100.0, self.tax)
        self.assertAlmostEqual(year.tax, 0.0)
        self.assertAlmostEqual(year.short_carry_used, 50.0)
        self.assertAlmostEqual(year.long_carry_used, 50.0)
        self.assertAlmostEqual(year.short_carry_out, 0.0)
        self.assertAlmostEqual(year.long_carry_out, 50.0)

    def test_new_losses_do_not_make_unneeded_carryovers_look_used(self) -> None:
        year = net_and_tax(
            Amounts(short_losses=70.0, long_gains=20.0, collectibles_losses=30.0),
            40.0, 50.0, self.tax,
        )
        self.assertAlmostEqual(year.tax, 0.0)
        self.assertAlmostEqual(year.short_carry_used, 0.0)
        self.assertAlmostEqual(year.long_carry_used, 0.0)
        self.assertAlmostEqual(year.short_carry_out, 110.0)
        self.assertAlmostEqual(year.long_carry_out, 60.0)

    def test_income_is_taxed_by_character_and_interest_as_ordinary(self) -> None:
        amounts = Amounts(qualified_income=100.0, ordinary_income=50.0, cash_interest=20.0)
        year = net_and_tax(amounts, 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.income_tax, 100.0 * 0.20 + 70.0 * 0.35)
        self.assertAlmostEqual(year.gains_tax, 0.0)
        self.assertAlmostEqual(year.tax, year.income_tax)

    def test_marks_enter_their_pools(self) -> None:
        year = net_and_tax(Amounts(marks_long=60.0, marks_short=40.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 60.0 * 0.20 + 40.0 * 0.35)

    def test_income_is_never_offset_by_capital_losses(self) -> None:
        year = net_and_tax(Amounts(ordinary_income=100.0, short_losses=500.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 35.0)
        self.assertAlmostEqual(year.short_carry_out, 500.0)


if __name__ == "__main__":
    unittest.main()
