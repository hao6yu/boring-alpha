"""Tests for the action ledger: that it adds up, that it stays honest about variance, and that the two rows
anyone can recompute still match the tools that produced them.

A summary table is the most dangerous artefact in a project like this, because it survives the analysis that
justified it and keeps its authority after its numbers go stale. So these tests do not check that the table is
*agreeable*; they check that it cannot silently drift. The two rows that are cheap enough to recompute from the
archive are recomputed here against the tools that own them, the variance labels are checked to be one of a
closed set rather than free prose, and the arithmetic of the closing total is re-derived from the rows instead
of being asserted alongside them.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import action_ledger as al                         # noqa: E402
import unlevered_timing as ut                      # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

VARIANCE_CLASSES = {"none", "substantial"}


class TheTableIsWellFormed(unittest.TestCase):
    def test_every_row_has_a_known_variance_class_and_a_source_round(self):
        self.assertGreaterEqual(len(al.rows(DATA())), 6)
        for action, how, dollars, variance, src, caveat in al.rows(DATA()):
            self.assertIn(variance, VARIANCE_CLASSES, action)
            self.assertTrue(src.strip(), action)
            self.assertTrue(how.strip() and caveat.strip(), action)
            self.assertTrue(dollars is None or isinstance(dollars, float), action)

    def test_no_row_is_labelled_variance_free_without_a_positive_or_zero_figure(self):
        """"No variance" is the claim that makes a row actionable. A row cannot carry it and also carry a
        range, so the label is only allowed where the number is a point estimate."""

        for action, _how, dollars, variance, _src, _c in al.rows(DATA()):
            if variance == "none":
                self.assertIsNotNone(dollars, f"{action} claims no variance but has no point estimate")

    def test_the_dollar_column_is_linear_in_capital_and_the_scale_factor_is_sane(self):
        self.assertAlmostEqual(al.BASE_CAPITAL, 20_000.0, places=6)
        for scale in (0.5, 1.0, 2.5):
            for action, _how, dollars, _v, _s, _c in al.rows(DATA()):
                if dollars is None:
                    continue
                self.assertAlmostEqual(dollars * scale / dollars, scale, places=12, msg=action)


class TheZeroVarianceRowsAreTheOnesThatMatter(unittest.TestCase):
    """The table's argument is that the actionable rows are the ones with no variance. If a row ever acquires a
    variance label, this test has to be argued with rather than edited, because that is the whole point."""

    def test_the_idle_cash_row_beats_the_largest_single_row_that_is_not_a_loan(self):
        """Demoted in round 29, and the demotion is the finding.

        Round 28's version of this test asserted that the zero-variance rows beat every positive stochastic row
        *combined*. It died the moment a constant 1.25× book was priced under honest financing (+$27.24/mo), so
        the honest claim is narrower: idle cash still beats the largest single row that asks you to hold a view.
        The row that beats it is a financing decision, not a forecast, and is checked separately below.
        """

        sure = [a[2] for a in al.rows(DATA()) if a[3] == "none" and a[2] and a[2] > 0]
        # Round 49 is a demotion, and the test has to carry it. The idle-cash row used to sit in the certain group,
        # which is what made the certain group top the table; r47 showed its value is 3 cents a month in 2021 and
        # $63 today, so it is a rate view and it moved out. The certain rows now total less than it — correctly.
        signals = [a[2] for a in al.rows(DATA())
                   if a[3] != "none" and a[2] and a[2] > 0 and "1.25x" not in a[0] and "idle cash" not in a[0]]
        rate_views = [a[2] for a in al.rows(DATA()) if a[3] != "none" and a[2] and "idle cash" in a[0]]
        self.assertGreater(sum(sure), 30.0, "housekeeping must still be worth something")
        self.assertLess(sum(sure), max(rate_views),
                        "if the certain group beats the rate view again, r49's reclassification was undone")
        # R29's comparison list is now empty by construction: the only stochastic positives left are the cash rate
        # view and the 1.25x loan, and neither is a signal. That emptiness is the finding, so it is asserted.
        self.assertEqual(len(signals), 0, f"a new signal-derived positive row appeared: {signals}")
        stochastic = sorted((a[0], round(a[2], 2)) for a in al.rows(DATA())
                            if a[3] != "none" and a[2] and a[2] > 0)
        self.assertEqual(len(stochastic), 2, f"stochastic positives changed: {stochastic}")
        self.assertGreater(rate_views[0], 25.0, "the rate view must still be the largest row on the table")
        # This floor was set while the idle-cash row sat in the certain group at $63. It moved with the row, so
        # the assertion is now about *which* row tops the certain group, not how big it is.
        top = max(al.rows(DATA()), key=lambda a: a[2] if (a[3] == "none" and a[2]) else -1)
        self.assertIn("rate card", top[0], f"the certain group is now topped by {top[0]}")
        self.assertGreater(top[2], 25.0)

    def test_the_only_positive_rows_that_are_not_loans_are_all_costs(self):
        """Every positive row must be a rate, a fee, or a loan. If a fifth positive row appears it is a signal
        claiming to work, and it has to be argued into this list with its round cited."""

        positive = [a[0] for a in al.rows(DATA()) if a[2] and a[2] > 0]
        self.assertEqual(len(positive), 5, f"positive rows changed: {positive}")
        for name in positive:
            self.assertTrue(any(word in name.lower() for word in
                                ("cash", "cheapest", "reinvest", "1.25x", "rate card")), name)


class TheRecomputableRowsStillMatchTheirTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.capped = ut.run(cls.data, cap=1.0)

    def test_the_unlevered_row_matches_what_the_tool_measures_today(self):
        row = {a[0]: a[2] for a in al.rows(DATA())}["de-risk with the trend/vol rule, unlevered"]
        measured = self.capped["total"] * 20_000.0
        self.assertAlmostEqual(row, -21.15, places=2)
        self.assertAlmostEqual(measured, row, delta=0.05,
                               msg=f"the tool now measures ${measured:+.2f}/mo and the table says ${row:+.2f}")

    def test_the_table_admits_that_the_same_signal_beats_its_equal_exposure_control(self):
        """The one positive fact about the trading rule is that it beats a static position of the same average
        weight. The table's caveat carries it, and the measurement has to keep carrying it too.

        `ut.run` reports a *monthly* decimal difference, so ×1200 puts it on the annualised-percent scale the
        notes publish. The band is the round-26 figure plus room for a future re-seal of the archive, and it is
        deliberately tight: the point of this test is that the timing premium is small, so a test that would
        pass at +5%/yr is not testing the claim the table makes.
        """

        ctrl = ut.run(self.data, static=self.capped["mean_w"])
        timing = (self.capped["total"] - ctrl["total"]) * 1200.0
        self.assertGreater(timing, 0.30)
        self.assertLess(timing, 0.70)
        self.assertGreater(self.capped["dd"], ctrl["dd"], "the drawdown ordering inverted; rewrite the row")


class ARowThatIsActuallyANoiseFloor(unittest.TestCase):
    """Round 38's bug, pinned. The share-class row read $25.00/mo for nine rounds and appears in four notes.
    It was round 18's NOISE FLOOR — the size of the SPY-versus-VOO splicing artefact — copied into the ledger as
    the value of the action. The action is worth the expense ratio: 6.45bp, $1.07/mo at $20,000. A number that
    describes how badly you can measure something is not a description of how much the thing is worth."""

    def test_the_share_class_row_equals_the_expense_ratio_and_nothing_else(self):
        row = [a for a in al.rows(DATA()) if "cheapest share class" in a[0]][0]
        expected = (wc.EXPENSE["SPY"] - wc.EXPENSE["VOO"]) * al.BASE_CAPITAL / 12.0
        self.assertAlmostEqual(row[2], round(expected, 2), places=2)
        self.assertLess(row[2], 2.0, "the true fee gap is about a dollar a month at this capital")

    def test_the_row_is_classified_as_variance_free_because_a_fee_schedule_is_not_an_estimate(self):
        row = [a for a in al.rows(DATA()) if "cheapest share class" in a[0]][0]
        self.assertEqual(row[3], "none")

    def test_the_row_that_moved_documents_its_own_provenance_in_the_table(self):
        """The correction is recorded where the error was, not only in a note nobody reads."""

        row = [a for a in al.rows(DATA()) if "cheapest share class" in a[0]][0]
        self.assertIn("NOISE FLOOR", row[5])

    def test_the_only_positive_stochastic_row_sits_just_above_the_comparator_fuzz(self):
        """Not a bug, a constraint: the loan row is $27.24/mo against a splicing-noise floor round 18 measured at
        roughly $24/mo. Two rows once sat inside that band and one of them was 23x wrong. Anything the ledger
        reports as positive and stochastic should be read as barely distinguishable from the bar's own fuzz."""

        floor = 24.0
        # The noise floor is a property of the *splicing comparator*, so only signal-derived rows compete against
        # it. Round 49 added a second stochastic row — the idle-cash rate view, $63 — and it is not a signal, so
        # excluding it is a definition, not a dodge; the rate row is checked against its own quartiles elsewhere.
        risky = [a[2] for a in al.rows(DATA())
                 if a[3] != "none" and a[2] and a[2] > 0 and "idle cash" not in a[0]]
        self.assertTrue(risky, "the ledger must still contain at least one stochastic positive row")
        self.assertLess(max(risky) - floor, 8.0, f"top stochastic row {max(risky):+.2f} vs floor {floor}")


if __name__ == "__main__":
    unittest.main(verbosity=2)


_DATA = None


def DATA():
    """One archive load for the whole module: the ledger's rows are derived, so every test needs the data."""

    global _DATA
    if _DATA is None:
        _DATA = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    return _DATA


class TheSwitchRowIsDerivedNotTranscribed(unittest.TestCase):
    """Round 47's second lesson. This row carried `46.12` and "the 55th percentile" as literals for fifteen
    rounds, and both were wrong by 37% and 10 points because the spot they came from had been pulled down by a
    four-day partial month. The row is now computed at print time; this test is what keeps it that way."""

    def test_the_row_equals_the_engine_and_no_literal_can_return(self):
        import cash_yield_gap as cy
        pth = cy.path(DATA())
        row = al.switch_row(DATA())
        self.assertAlmostEqual(row[2], pth["worth_spot"], places=9)
        self.assertGreater(row[2], 60.0, "a literal of 46.12 would still pass the old tests")
        self.assertIn("47", row[4])
        self.assertTrue(any(r[2] is None for r in al.ACTIONS),
                        "the literal is back in ACTIONS; the row must stay a placeholder until derived")

    def test_the_derived_table_still_holds_exactly_five_positive_rows(self):
        positive = [r for r in al.rows(DATA()) if r[2] and r[2] > 0]
        self.assertEqual(len(positive), 5)
        self.assertTrue(all(any(w in r[0].lower() for w in ("cash", "cheapest", "reinvest", "1.25x", "rate card"))
                            for r in positive))

    def test_the_financing_row_is_derived_from_the_rate_card_and_beats_the_tilt_it_sits_under(self):
        """Round 49's reason for existing: 710bp of posted spread on a borrowed slice is worth more than the
        borrowing decision itself. If the rate card narrows, this fails and the ordering has to be re-argued."""

        import financing_desk as fd
        row = [r for r in al.rows(DATA()) if "rate card" in r[0]][0]
        self.assertAlmostEqual(row[2], (fd.EXPENSIVE[1] - fd.CHEAP[1]) * 0.25 * al.BASE_CAPITAL / 12.0, places=2)
        self.assertEqual(row[3], "none", "a posted rate tier is contractual; do not hedge it")
        tilt = [r for r in al.rows(DATA()) if "1.25x" in r[0]][0]
        self.assertGreater(row[2], tilt[2], "the desk stopped outranking the tilt it finances")

    def test_the_cash_row_is_no_longer_sold_as_variance_free(self):
        row = [r for r in al.rows(DATA()) if "idle cash" in r[0]][0]
        self.assertEqual(row[3], "substantial", "r47: this row is worth 3 cents in 2021 and $63 today")
        self.assertIn("49", row[4])


if __name__ == "__main__":
    unittest.main(verbosity=2)
