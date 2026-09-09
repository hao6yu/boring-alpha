"""Round 60: what a model is worth while you are still contributing, and the checks that keep that figure honest.

The statistics here are new to the repository — median multiple of contributions, and P(terminal < total contributed)
— so they are tested against hand-built series as well as against the archive.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import contribution_race as cr                           # noqa: E402
import monthly_income_race as mir                        # noqa: E402
import plan_survival as ps                               # noqa: E402
import rates_gate as rg                                  # noqa: E402
import rotation_edge as re_                              # noqa: E402
import trend_cost_test as tc                             # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


class Shared(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        ordered, rets, bills, expense = re_.panel(cls.data)
        cls.ordered = ordered
        pos = {d: i for i, d in enumerate(tc.days_of(cls.data, "SPY"))}
        cl = tc.closes_of(cls.data, "SPY")
        closes = {"SPY": [cl[pos[d]] for d in ordered]}
        cls.marks = {}
        for leg in mir.LEGS:
            w = mir.leg_weights(leg, ordered, rets, bills, expense, closes, re_.UNKNOWN_ER)
            cls.marks[leg] = mir.month_marks(ordered, mir.wealth_path(ordered, rets, bills, expense, w))[1]
        cls.long = cr.long_record(cls.data, 1_000.0, 10, 5)


class TheStatisticsAreWhatTheySay(Shared):

    def test_a_flat_series_returns_exactly_what_was_put_in(self):
        """No withdrawal, no return: the terminal balance is the arithmetic sum. Everything else in this file is
        built on the sim being exact about the cash flows."""

        out = cr.run_windows([0.0] * 120, 10_000.0, 250.0, 10)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]["terminal"], 10_000.0 + 250.0 * 120, places=6)
        s = cr.summary(out, 10_000.0, 250.0, 10)
        self.assertAlmostEqual(s["mult"], 1.0, places=9)
        self.assertEqual(s["p_under"], 0.0)

    def test_a_series_that_falls_every_month_always_returns_less_than_contributed(self):
        out = cr.run_windows([-0.02] * 120, 10_000.0, 250.0, 10)
        s = cr.summary(out, 10_000.0, 250.0, 10)
        self.assertEqual(s["p_under"], 1.0, "P(terminal < contributed) missed a certain failure")
        self.assertLess(s["median"], s["total"])

    def test_an_untested_sample_is_none_and_not_zero(self):
        s = cr.summary([], 100_000.0, 1_000.0, 10)
        self.assertEqual(s["n"], 0)
        for k in ("median", "p_under", "mult", "min"):
            self.assertIsNone(s[k], f"{k} read as a number on an empty sample")

    def test_every_starting_month_of_the_plan_is_counted_once(self):
        out = cr.run_windows(self.marks["SPY hold"], 0.0, 1_000.0, 10)
        self.assertEqual(len(out), len(self.marks["SPY hold"]) - 120 + 1)


class TheArithmeticScalesWithCapitalNotCleverness(Shared):

    def test_the_advantage_is_linear_in_starting_capital(self):
        """With no withdrawal and no contribution, terminal wealth is linear in the balance. If the advantage were
        not, the tool would be computing something other than what it claims."""

        def adv(c0):
            a = cr.summary(cr.run_windows(self.marks["MA200 monthly"], c0, 0.0, 10), c0, 0.0, 10)["median"]
            b = cr.summary(cr.run_windows(self.marks["SPY hold"], c0, 0.0, 10), c0, 0.0, 10)["median"]
            return a - b

        self.assertAlmostEqual(adv(200_000.0) / adv(100_000.0), 2.0, delta=0.001)
        self.assertAlmostEqual(adv(250_000.0) / adv(50_000.0), 5.0, delta=0.001)
        self.assertLess(adv(100_000.0), 0.0, "the trend rule now beats the index on the panel with a lump sum")

    def test_contributions_dilute_the_model_as_a_share_of_the_outcome(self):
        def share(c0, contrib):
            a = cr.summary(cr.run_windows(self.marks["MA200 monthly"], c0, contrib, 10), c0, contrib, 10)
            b = cr.summary(cr.run_windows(self.marks["SPY hold"], c0, contrib, 10), c0, contrib, 10)
            return abs(a["median"] - b["median"]) / a["median"]

        # Measured: 0.3228 of terminal wealth with no contributions, 0.2585 at $2,000 a month. The claim is that the
        # model becomes a smaller part of the answer as the savings rate becomes a bigger part of it, so the bound is
        # a shrinkage, not a particular size of one.
        small, large = share(100_000.0, 0.0), share(100_000.0, 2_000.0)
        self.assertLess(large, small * 0.95,
                        f"the model's share of the outcome did not shrink as contributions grew ({small:.4f} vs"
                        f" {large:.4f})")


class TheFindingsHold(Shared):

    def test_every_alternative_leg_ends_the_plan_smaller_than_the_index_on_the_panel(self):
        base = cr.summary(cr.run_windows(self.marks["SPY hold"], 20_000.0, 1_000.0, 10), 20_000.0, 1_000.0, 10)
        for leg in mir.LEGS[1:]:
            s = cr.summary(cr.run_windows(self.marks[leg], 20_000.0, 1_000.0, 10), 20_000.0, 1_000.0, 10)
            self.assertLess(s["median"], base["median"],
                            f"{leg} now beats the index in a contribution plan; the panel finding has flipped")

    def test_the_index_can_leave_a_contributor_with_less_than_they_saved_and_the_rule_cannot(self):
        idx = self.long["whole"]["SPY hold"]
        rule = self.long["whole"]["MA200 monthly"]
        self.assertGreater(idx["p_under"], 0.02,
                           f"on the long record the index failed to return contributions in only {idx['p_under']:.1%}"
                           " of windows; the insurance claim needs re-explaining")
        self.assertEqual(rule["p_under"], 0.0, "the trend rule now has a window where a contributor ended under water")
        self.assertLess(rule["median"], idx["median"], "the rule no longer costs growth, which contradicts r58/r60")

    def test_the_trend_rule_is_ahead_only_in_the_oldest_era_at_either_plan_length(self):
        """A 10-year plan cannot score the newest era — there are not enough windows — so the newest era is checked
        at 5 years, where the tool says it can be. Asking the long plan for that cell would be asking for a number
        the sample does not contain."""

        for plan, eras in ((10, ("2005-2015",)), (5, ("2005-2015", "2016-now"))):
            lh = cr.long_record(self.data, 1_000.0, plan, plan)
            for era in eras:
                e, b = lh["eras"][era]["MA200 monthly"], lh["eras"][era]["SPY hold"]
                self.assertIsNotNone(e["median"], f"{era} at a {plan}y plan is untested and must not be quoted")
                self.assertGreater(b["n"], 30)
                self.assertLess(e["median"], b["median"], f"MA200 beat the index in {era} at {plan}y")
            e, b = lh["eras"]["1993-2004"]["MA200 monthly"], lh["eras"]["1993-2004"]["SPY hold"]
            self.assertGreater(e["median"], b["median"],
                               f"the oldest era no longer favours the rule at {plan}y; re-read the note")
        thin = cr.long_record(self.data, 1_000.0, 10, 10)
        self.assertIsNone(thin["eras"]["2016-now"]["MA200 monthly"]["median"],
                          "a 10-year plan in the newest era is reporting a figure it does not have")

    def test_the_long_record_starts_where_it_says_and_the_panel_starts_in_2006(self):
        """Both sample boundaries, asserted rather than assumed: half of this round's message is that the two
        boundaries disagree, and that claim is worth nothing if the boundaries are not the ones named."""

        keys = rg.series(self.data, 10, 100_000.0, 0.05)[1]
        self.assertEqual(keys[0].year, 1993)
        self.assertLess(self.ordered[0].year, keys[0].year + 20, "the panel is not a subset of the long record")
        self.assertEqual(self.ordered[0].year, 2006)
        self.assertGreater(self.long["eras"]["1993-2004"]["SPY hold"]["n"], 100)

    def test_the_cross_engine_pair_agree_on_who_wins(self):
        """This file prices the long record on the monthly convention and the panel on the daily one. Whichever
        convention a number came from, the ordering it produced has to be the same one."""

        panel = cr.summary(cr.run_windows(self.marks["MA200 monthly"], 100_000.0, 0.0, 10), 100_000.0, 0.0, 10)["median"]
        idx = cr.summary(cr.run_windows(self.marks["SPY hold"], 100_000.0, 0.0, 10), 100_000.0, 0.0, 10)["median"]
        self.assertLess(panel, idx)
        self.assertLess(self.long["whole"]["MA200 monthly"]["median"],
                        self.long["whole"]["SPY hold"]["median"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
