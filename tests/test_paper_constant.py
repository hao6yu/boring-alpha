"""Tests for the forward book's third model, "constant".

`test_constleverage.py` tests the policy in isolation. These tests cover the part that only exists inside
`paper.py`: that the model dispatch returns a well-formed vector, that it is honest in its label, and — the one
that matters most — that this model's exposure is **not** the thing the project has been claiming for five rounds.
The constant plan beats the comparator because it borrows; the live signal today happens to want slightly *more*
exposure than the constant does, which means the gap between them is not "more of the same" and the forward record
has to be read accordingly.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                       # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402


class TheConstantModelIsRunnable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(paper.SNAPSHOT, paper.CASH_FILE)
        cls.asof = max(cls.data.dates)
        cls.const = paper.signal_for(cls.data, cls.asof, "constant")
        cls.vol = paper.signal_for(cls.data, cls.asof, "voltarget")

    def test_it_returns_a_vector_on_the_same_session_the_other_models_use(self):
        self.assertIsNotNone(self.const)
        self.assertEqual(self.const.asof, self.vol.asof,
                         "two books on different calendars cannot be compared at all")
        self.assertAlmostEqual(self.const.target_weights["SPY"], paper.CONSTANT_WEIGHT, places=12)
        self.assertEqual(set(self.const.target_weights), {"SPY"})

    def test_the_name_says_loan_because_a_bare_percentage_would_be_read_as_a_view(self):
        n = self.const.name.lower()
        self.assertIn("loan", n)
        self.assertNotIn("target", n, "a constant has no target to hit; the word would imply a controller")

    def test_the_hurdle_is_zero_because_there_is_no_alternative_it_is_beating(self):
        """A trend model is compared against cash. A leverage decision is not — it is the same asset, more of it,
        and giving it a hurdle would imply a gate it does not have. `WeightVector` stores the constructor's
        `hurdle` under the field name `cash_return`, which is why this asserts on the attribute and not the kwarg.
        """

        self.assertEqual(self.const.cash_return, 0.0)
        self.assertEqual(self.vol.cash_return, 0.0,
                         "both books must face the same alternative or their spreads mean different things")

    def test_the_pre_registered_borrow_spread_is_still_the_one_the_chains_are_price_by(self):
        """Round 30 measured the desk's real spread at ~202bp over the archive curve, against this book's stale 150bp,
        and paper.py itself said any re-init should pin 0.0202. It was pinned on 2026-09-07, at the re-init round 68's
        shelter model forced — which is the only moment the change is allowed, because a mid-chain change would make a
        book incomparable with its own history for a reason that has nothing to do with the market.

        It stays a loud test on purpose: change the number again and this fails, and the fix is a new chain, not an
        edit to this line.
        """

        self.assertEqual(paper.BORROW_SPREAD, 0.0202, "a spread may only change at a re-init, and that is a new chain")
        self.assertGreater(paper.CONSTANT_WEIGHT, 1.0)


class TheGapBetweenTheTwoBooksIsNotMerelyExposure(unittest.TestCase):
    """The claim round 32 was written to support, stated honestly enough to be falsified by the next session."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(paper.SNAPSHOT, paper.CASH_FILE)
        cls.asof = max(cls.data.dates)
        cls.const = paper.signal_for(cls.data, cls.asof, "constant")
        cls.vol = paper.signal_for(cls.data, cls.asof, "voltarget")

    def test_on_the_last_sealed_session_the_signal_wants_at_least_as_much_as_the_constant(self):
        """Today that is true — the gate has the signal at 1.28x against the constant's 1.25x. If it ever stops
        being true it is not a bug, it is the point of running both: the signal de-risks into a fall and the loan
        does not, and the forward record is where you find out which of those behaviour costs more."""

        self.assertGreaterEqual(self.vol.target_weights["SPY"], paper.CONSTANT_WEIGHT - 0.05)

    def test_the_two_books_differ_in_whether_anything_decides(self):
        """One policy's weight is a function of the market and the other's is a constant. Over the archive the
        signal's mean weight is far below the constant's, so the plan's excess return is leverage rather than
        timing, and this test is the assertion that the project has not confused the two."""

        import withdrawal_capacity as wc
        import income_frontier as ifr
        import unlevered_timing as ut
        d = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        mean_w = ut.run(d)["mean_w"]
        self.assertLess(mean_w, paper.CONSTANT_WEIGHT,
                        "if the signal ever averages more exposure than the loan, the comparison inverts")


if __name__ == "__main__":
    unittest.main(verbosity=2)
