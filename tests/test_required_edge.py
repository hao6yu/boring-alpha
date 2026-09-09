"""Round 51: the required-edge arithmetic, and the benchmark's own sample written down.

The bisection is legal only because terminal wealth is monotone in the rate, so that is the first thing pinned —
before any of the numbers, because a non-monotone recurrence would make every printed "required" meaningless rather
than merely wrong.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import required_edge as re_                              # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


class TheArithmetic(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_terminal_wealth_is_strictly_increasing_in_the_rate(self):
        w = [re_.terminal_wealth(20_000.0, r, 500.0, 500.0, 120) for r in (-0.20, 0.0, 0.10, 0.30)]
        for a, b in zip(w, w[1:]):
            self.assertLess(a, b, f"the recurrence went flat or backwards: {w}")

    def test_the_root_round_trips_at_every_corner_of_the_grid(self):
        for c0 in (20_000.0, 100_000.0):
            for m in (0.0, 500.0, 1_000.0):
                need = re_.required_cagr(c0, m, 500.0, 10, 1.0)
                self.assertIsNotNone(need, f"no rate clears c0={c0} m={m}")
                end = re_.terminal_wealth(c0, need / 100.0, m, 500.0, 120)
                self.assertAlmostEqual(end, c0, delta=c0 * 1e-6,
                                       msg=f"{c0}/{m}: {end:,.2f} != {c0:,.2f}")

    def test_the_bisection_reproduces_the_closed_form_at_every_probe(self):
        """With no contributions and a principal-preservation floor the recurrence has an exact fixed point: if
        r/12 equals the monthly withdrawal rate, the balance returns to `c0` every month, so the required return is
        12 x target / capital and is **identical at every horizon**. That is algebra, not a property of the solver,
        and it is the cheapest available proof that 80 bisection steps are answering the right question.

        The horizon-blindness is worth stating out loud, because it is the trap in every plan spreadsheet: a
        required return is a *mean* statistic, so length costs it nothing. The horizon is charged for by the
        guarantee, a path minimum (round 50: $592.97 at 10 years down to $364.45 at 20). The gap between the two
        framings is not a disagreement about arithmetic, it is sequence risk wearing two hats.
        """

        for c0, target in ((50_000.0, 500.0), (1_000_000.0, 500.0), (50_000.0, 1_000.0), (120_000.0, 400.0)):
            want = 12.0 * target / c0 * 100.0
            for years in (5, 10, 20, 30):
                got = re_.required_cagr(c0, 0.0, target, years, 1.0)
                self.assertAlmostEqual(got, want, places=6,
                                       msg=f"c0={c0} t={target} y={years}: {got} vs {want}")

    def test_the_requirement_rises_with_the_target_and_falls_with_contributions(self):
        base = re_.required_cagr(50_000.0, 0.0, 500.0, 10, 1.0)
        self.assertGreater(re_.required_cagr(50_000.0, 0.0, 1_000.0, 10, 1.0), base)
        self.assertLess(re_.required_cagr(100_000.0, 0.0, 500.0, 10, 1.0), base)
        self.assertLess(re_.required_cagr(50_000.0, 500.0, 500.0, 10, 1.0), base,
                        "contributions are the cheapest lever on the table and this test is why")
        self.assertGreater(re_.required_cagr(50_000.0, 0.0, 500.0, 10, 2.0), base)

    def test_the_mean_framing_and_the_guarantee_framing_disagree_by_triple_the_capital(self):
        """$500/mo on VOO's own median 10-year return needs $44,910 of capital. The worst 20-year start in the same
        archive needs $137,215. Same objective, same archive, 3x apart, and the difference is the price of
        insisting the plan survive a path rather than an average."""

        voo = re_.rolling_cagr(self.data, "VOO", 10)
        mean_capital = 500.0 * 12.0 / (voo["median"] / 100.0)
        from income_accounting import guarantee
        g = guarantee("SPY", 1.00, 100_000.0, 20, self.data, 1)["cheque"]
        guaranteed_capital = 500.0 * 12.0 / (g / 100_000.0)
        self.assertGreater(guaranteed_capital / mean_capital, 2.5,
                           f"the framings now agree within {guaranteed_capital / mean_capital:.2f}x")
        self.assertGreater(guaranteed_capital, 130_000.0)
        self.assertLess(mean_capital, 50_000.0)


    def test_matching_contributions_make_the_required_return_exactly_zero(self):
        """An identity, not a curiosity: in $500 and out $500 means the balance never moves, so the plan clears at
        any non-negative rate and the required figure must be zero. If this ever prints 3%, the recurrence has a
        timing bug in the contribution."""

        self.assertAlmostEqual(re_.required_cagr(20_000.0, 500.0, 500.0, 10, 1.0), 0.0, places=4)

    def test_an_impossible_plan_says_none_rather_than_a_big_number(self):
        self.assertIsNone(re_.required_cagr(20_000.0, 0.0, 200_000.0, 10, 1.0))

    def test_a_floor_below_one_is_easier_and_above_one_is_harder(self):
        mid = re_.required_cagr(50_000.0, 0.0, 500.0, 10, 1.0)
        self.assertLess(re_.required_cagr(50_000.0, 0.0, 500.0, 10, 0.5), mid)
        self.assertGreater(re_.required_cagr(50_000.0, 0.0, 500.0, 10, 2.0), mid)


class TheBenchmarkIsNotWhatItLooksLike(unittest.TestCase):
    """The round's finding: the ticker the objective names as its bar has the shortest and friendliest record in
    the archive, so the bar must be quoted with its window count and its worst case, not as a median."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.voo = re_.rolling_cagr(cls.data, "VOO", 10)
        cls.spy = re_.rolling_cagr(cls.data, "SPY", 10)

    def test_the_window_count_travels_with_the_distribution(self):
        self.assertGreater(self.voo["n"], 40)
        self.assertGreater(self.spy["n"], self.voo["n"],
                           "VOO's advantage is its history length; if that stops showing, the archive changed")

    def test_voo_has_no_negative_decade_in_this_archive_and_spy_has_many(self):
        self.assertGreater(self.voo["min"], 0.10,
                           "VOO's record gained a lost decade; re-read every comparison built on its median")
        self.assertLess(self.spy["min"], 0.0)
        self.assertGreater(self.spy["min"], -20.0)

    def test_the_medians_are_not_close_enough_to_be_interchangeable(self):
        self.assertGreater(self.voo["median"] - self.spy["median"], 3.0,
                           f"the benchmark gap narrowed to {self.voo['median'] - self.spy['median']:.2f}pp")

    def test_a_20_year_window_in_the_short_recorded_sleeve_asks_for_the_impossible(self):
        """The honest shape of a short record: enough windows at 10 years, too few to be a distribution at 20."""

        voo20 = re_.rolling_cagr(self.data, "VOO", 20)
        self.assertLess(voo20["n"], 40, "VOO now has enough 20-year windows; the warning above needs rewriting")


class TheVerdictIsNotRigged(unittest.TestCase):
    """A tool that always answers "no" is as useless as one that always answers "yes", so the negative verdict is
    pinned next to a case that clears."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.spy = re_.rolling_cagr(cls.data, "SPY", 10)

    def test_the_smallest_capital_no_contribution_case_is_beyond_any_measured_edge(self):
        need = re_.required_cagr(20_000.0, 0.0, 500.0, 10, 1.0)
        self.assertGreater(need, 25.0)
        self.assertIn("NO measured edge", re_.feasibility(need, self.spy))

    def test_a_case_that_clears_is_reported_as_clearing(self):
        """The exact figure is 0.60%: $6,000 a year out of $1m, which the closed form above predicts. The point of
        the test is the verdict, not the number — a tool that answers "impossible" to everything would pass every
        other test in this file."""

        need = re_.required_cagr(1_000_000.0, 0.0, 500.0, 10, 1.0)
        self.assertAlmostEqual(need, 0.60, places=6)
        verdict = re_.feasibility(need, self.spy)
        self.assertNotIn("NO measured edge", verdict, verdict)

    def test_the_measured_edges_are_their_stated_arithmetic_and_not_typeds(self):
        self.assertAlmostEqual(re_.BEST_ANY_EDGE_PP, (12.00 - 4.90) * 0.25, places=10)
        self.assertAlmostEqual(re_.BEST_MEASURED_EDGE_PP, 1.63, places=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
