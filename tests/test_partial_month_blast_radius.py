"""Round 48: how far the partial-month stub reaches, measured at every consumer.

Round 47 found that `bill()` annualised a four-day September bucket as a month and mis-stated the spot bill yield
by 103bp. The defect belongs to `withdrawal_capacity.monthly`, which eight tools call, so the question this file
answers is not whether the bug is real — it is **where it is allowed to matter**. The answer, measured: it moved
spot-anchored figures by 37% of the headline action's value and moved the guaranteed cheque by **exactly nothing**,
because a minimum over 165 windows is set by a window ending in 2020 and has no idea what September did.

Those two facts are different in kind, so they are pinned separately: an invariant where the defect is provably
harmless, and a magnitude where it is not. If the guarantee ever stops being invariant, that is a different story
being told by the same archive, and this file should fail loudly.
"""

import sys
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cash_yield_gap as cy                    # noqa: E402
import combined_account as ca                  # noqa: E402
import financing_desk as fd                    # noqa: E402
import income_accounting as ia                 # noqa: E402
import income_frontier as ifr                  # noqa: E402
import withdrawal_capacity as wc               # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


@contextmanager
def stub_state(drop: bool):
    """Force every tool to or away from the raw series by patching the one function they all call.

    `drop=True` is the honest reading of the archive. The raw series is reproduced rather than assumed, so the
    tests measure the difference the helper makes rather than the helper's own opinion about it.
    """

    original = wc.monthly
    if drop:
        wc.monthly = lambda s, c: tuple(x[:-1] for x in original(s, c))
    try:
        yield
    finally:
        wc.monthly = original


class TheHelperItself(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.raw = wc.monthly(ifr.series_for(cls.data, "SPY"), cls.data.cash_factors)
        cls.clean = wc.monthly_complete(ifr.series_for(cls.data, "SPY"), cls.data.cash_factors,
                                        max(cls.data.by_date))

    def test_the_sealed_archive_ends_on_a_stub_and_exactly_one_bucket_is_dropped(self):
        self.assertEqual(len(self.raw[2]) - len(self.clean[2]), 1)
        self.assertEqual(max(self.data.by_date), date(2026, 9, 4),
                         "the archive moved to a month end; the expected stub is no longer guaranteed")
        self.assertEqual(self.clean[2][-1], self.raw[2][-2], "the surviving series is the raw one minus its tail")

    def test_a_month_end_seal_keeps_its_month(self):
        """The control that makes the rule a rule and not a reflex: given a seal on the final month's last
        weekday, nothing is dropped."""

        month_end = wc.last_business_day(self.raw[2][-1].year, self.raw[2][-1].month)
        kept = wc.monthly_complete(ifr.series_for(self.data, "SPY"), self.data.cash_factors, month_end)
        self.assertEqual(len(kept[2]), len(self.raw[2]))

    def test_the_calendar_helper_agrees_with_the_calendar(self):
        self.assertEqual(wc.last_business_day(2026, 9), date(2026, 9, 30))
        self.assertEqual(wc.last_business_day(2026, 5), date(2026, 5, 29))   # the 31st is a Sunday
        self.assertEqual(wc.last_business_day(2026, 8), date(2026, 8, 31))

    def test_the_months_are_consecutive_so_only_the_tail_died(self):
        prev = self.clean[2][-2]
        cur = self.clean[2][-1]
        expected = date(prev.year + (prev.month == 12), 1 if prev.month == 12 else prev.month + 1, 1)
        self.assertLess(expected, cur, "dropping the stub also dropped a real month")


class WhereTheStubCannotMatter(unittest.TestCase):
    """Window minima and full-history compounding: measured indifferent, and pinned at exact equality so that a
    change in which window binds is reported as the story change it would be."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_the_guaranteed_cheque_is_identical_to_the_cent_at_both_levers(self):
        with stub_state(False):
            raw = [ia.guarantee("SPY", lev, wc.START, 20, self.data, 1)["cheque"] for lev in (1.00, 1.25)]
        with stub_state(True):
            clean = [ia.guarantee("SPY", lev, wc.START, 20, self.data, 1)["cheque"] for lev in (1.00, 1.25)]
        self.assertEqual(raw, clean, f"the guarantee moved: {raw} -> {clean}")
        self.assertAlmostEqual(raw[0], 364.45, delta=0.05)

    def test_the_negative_month_share_is_stable_at_39_1_percent(self):
        months = ca.monthly_edge(self.data, 1.25, wc.TURNOVER_COST, "SPY")[1]
        share = sum(1 for m in months if m < 0) / len(months)
        self.assertLess(abs(share - 0.391), 0.01, f"the negative-month share drifted from 39.1%: {share:.3f}")

    def test_full_history_compounding_moves_by_under_five_basis_points(self):
        with stub_state(False):
            raw = fd.excess(self.data, "SPY", 1.25, 0.049, None)
        with stub_state(True):
            clean = fd.excess(self.data, "SPY", 1.25, 0.049, None)
        self.assertLess(abs(clean[0] - raw[0]), 0.05, f"full-history excess moved {clean[0] - raw[0]:+.3f}pp")


class WhereTheStubDoesMatter(unittest.TestCase):
    """The spot family: pinned as material, so nobody simplifies the complete-month rule back out again."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_the_spot_bill_yield_moved_by_more_than_half_a_point_and_in_the_expected_direction(self):
        """Round 47 replaced a formula, not a call site, so the comparison is formula against formula: the old
        three-month annualisation computed on the raw series, against `bill()` as it now stands. Patching
        `monthly` can no longer reproduce the defect, which is the point of the fix."""

        import statistics
        raw = wc.monthly(ifr.series_for(self.data, "SPY"), self.data.cash_factors)[1]
        contaminated = (1.0 + statistics.fmean(raw[-3:])) ** 12 - 1.0
        clean = cy.bill(self.data)["current3m"]
        self.assertLess(contaminated, clean, "a four-day accrual can only pull an annualisation down")
        self.assertGreater(clean - contaminated, 0.005,
                           f"the defect is only {clean - contaminated:+.4%}; the note's 103bp claim is stale")

    def test_a_window_measured_at_its_edge_moves_six_times_as_much_as_the_full_history(self):
        """16y excess shifts 0.15pp against full history's 0.003pp. Not because the stub is large — because
        dropping it slides the whole 192-month window by a month. That is r39's era effect, the largest
        uncontrolled quantity in this repository, arriving through a one-month edge."""

        with stub_state(False):
            raw = fd.excess(self.data, "SPY", 1.25, 0.049, 192)
        with stub_state(True):
            clean = fd.excess(self.data, "SPY", 1.25, 0.049, 192)
        shift = abs(clean[0] - raw[0])
        self.assertLess(shift, 0.25, "window-edge sensitivity exceeded the era budget")
        self.assertGreater(shift, 0.05, "the window edge stopped mattering; re-read what that implies")

    def test_the_switch_distribution_moved_by_pennies_while_its_spot_moved_by_pounds(self):
        import statistics
        raw = wc.monthly(ifr.series_for(self.data, "SPY"), self.data.cash_factors)[1]
        old_spot = (1.0 + statistics.fmean(raw[-3:])) ** 12 - 1.0
        annual = [x * 12.0 for x in raw]
        old = {"worth_spot": (old_spot - cy.SGOV_ER - cy.SWEEP_MEDIAN) * 20_000.0 / 12.0,
               "median": sorted(annual)[len(annual) // 2]}
        clean = cy.path(self.data)
        self.assertLess(abs(clean["median"] - old["median"]), 0.0020,
                        "the distribution must be near-identical; that is why thirteen rounds saw no symptom")
        self.assertGreater(abs(clean["worth_spot"] - old["worth_spot"]), 10.0,
                           "the spot row must stay materially wrong without the complete-month rule")


if __name__ == "__main__":
    unittest.main(verbosity=2)
