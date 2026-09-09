"""Tests for the unlevered anatomy: an accounting identity, two controls, and one ordering claim.

The decomposition is the kind of claim that can only be right in one way — the three month-type contributions
must sum to the headline, to the month, because every month is in exactly one bucket. If they do not, a month
was counted twice or lost, and the whole table above it is fiction. The rest of the file guards the two controls
that make the table mean anything: the cap must actually forbid leverage, and the static control must match the
capped rule's *average* exposure, because a comparison at the wrong average weight is a comparison of sizes
rather than of timing.
"""

from __future__ import annotations

import statistics
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import income_frontier as ifr                      # noqa: E402
import unlevered_timing as ut                      # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402


class TheDecompositionIsAnIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.capped = ut.run(cls.data, cap=1.0)
        cls.a = cls.capped["anatomy"]

    def test_the_three_month_types_sum_to_the_headline_because_every_month_is_in_exactly_one(self):
        total = self.a["crash"] + self.a["rally"] + self.a["flat"]
        self.assertAlmostEqual(total, self.a["total"], places=9,
                               msg="a month is double-counted or dropped; the anatomy is not a partition")
        self.assertAlmostEqual(self.a["total"], self.capped["total"] * 1200.0, places=9)

    def test_the_counts_are_the_record_and_add_up(self):
        self.assertEqual(self.a["n_crash"] + self.a["n_rally"] + (self.a["months"] - self.a["n_crash"]
                                                                 - self.a["n_rally"]), self.a["months"])
        self.assertEqual(self.a["months"], len(self.capped["strat"]))
        self.assertGreater(self.a["n_crash"], 20, "with too few crash months the first column is a story "
                                                 "about three events, and the tool would have to say so")

    def test_the_two_tallies_have_the_signs_the_device_claims(self):
        """Saved in falls, paid away in rises. If the first number ever goes negative the rule is not a
        drawdown device at all and the note has to be rewritten, not the threshold nudged."""

        self.assertGreater(self.a["crash"], 0.0)
        self.assertLess(self.a["rally"], 0.0)
        self.assertGreater(abs(self.a["rally"]), self.a["crash"],
                           "the premium turned positive: the device now pays for itself, which is a different "
                           "note")

    def test_the_crash_and_rally_thresholds_separate_the_two_buckets(self):
        """Four months, one per bucket plus one extra fall, with a rule that held only 20% through the falls
        and the full position through the rise: the falls must read positive and the rise negative, and the
        buckets must be counted where the thresholds say they belong."""

        a = ut.anatomy([0.02, 0.00, 0.06, -0.02], [0.00, -0.06, 0.06, -0.06], ["w", "x", "y", "z"], 0.05)
        self.assertEqual((a["n_crash"], a["n_rally"]), (2, 1))
        self.assertGreater(a["crash"], 0.0, "holding 20% through a −6% month must read as a saving")
        self.assertEqual(a["rally"], 0.0, "a full position through a +6% month is the benchmark, not a gain")


class TheControlsControlWhatTheySay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.capped = ut.run(cls.data, cap=1.0)
        cls.book = ut.run(cls.data)
        cls.ctrl = ut.run(cls.data, static=cls.capped["mean_w"])

    def test_the_cap_forbids_borrowing_rather_than_reducing_it(self):
        self.assertLessEqual(max(self.capped["weights"]), 1.0 + 1e-12)
        self.assertGreater(max(self.book["weights"]), 1.0, "the book's rule no longer levers, so the cap "
                                                           "controls nothing")
        self.assertLess(self.capped["mean_w"], self.book["mean_w"])

    def test_the_static_control_matches_the_capped_rules_average_exposure_not_its_shape(self):
        self.assertAlmostEqual(self.ctrl["mean_w"], self.capped["mean_w"], places=12)
        self.assertLess(self.capped["mean_w"], 1.0, "a rule that never holds less than the index needs no "
                                                    "equal-exposure control; the comparison would be trivial")

    def test_the_capped_rule_has_the_shallowest_drawdown_of_the_three(self):
        """The device's entire purpose, as an ordering rather than a dollar figure — the one claim in this
        table that does not need statistical power to be worth acting on."""

        self.assertGreater(self.capped["dd"], self.ctrl["dd"])
        self.assertGreater(self.capped["dd"], self.book["dd"])
        self.assertLess(abs(self.capped["dd"]), 0.40)
        self.assertGreater(abs(self.ctrl["dd"]), abs(self.capped["dd"]) * 1.4)


class TheComparatorPaysItsOwnExpense(unittest.TestCase):
    """The bug that found this round: a static-100% row whose "excess vs the index" was exactly the fund's
    expense ratio, because the strategy leg was charged a fee the benchmark leg was not. The pinned comparator
    in `data/paper/model.json` is net of that fee, so both legs must pay it and the excess of holding exactly
    the comparator must be zero."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.index = ut.run(cls.data, static=1.0)
        cls.book = ut.run(cls.data)

    def test_a_static_full_position_in_the_comparator_earns_exactly_the_comparator(self):
        self.assertAlmostEqual(self.index["total"], 0.0, places=12,
                               msg=f"the benchmark is off by {self.index['total']*1200:.4f}%/yr — one "
                                   f"expense ratio again")

    def test_the_record_carries_the_expense_that_the_fix_removed(self):
        self.assertAlmostEqual(float(wc.EXPENSE["SPY"]), 0.000945, places=9)
        self.assertGreater(self.book["mean_w"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
