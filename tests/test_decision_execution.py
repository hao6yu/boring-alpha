"""Tests for the sheet's execution section, and for the dominance scan underneath it.

Everything else in this repository prices proportions, and a proportion cannot see a flat ticket. These tests exist because
the answer changed when it was finally priced: at $2,500 with a $9.95 ticket, the two-sleeve book that every table in this
archive says dominates plain VOO ends *behind* it over two years. That is not a rounding curiosity, it is the P0 rule failing
in the corner of parameter space a real small account occupies — so the corner gets pinned, along with the invariance that
makes the corner meaningful (with no commission, size changes nothing at all).

No threshold is asserted here. Where the sign turns over is reported; that it turns over is claimed.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import decision_sheet as ds                                  # noqa: E402
import power_horizon as ph                                   # noqa: E402
import rebalance_cost as rc                                  # noqa: E402

TWO_YEARS = ph.month_closes(ph.last_date() - dt.timedelta(days=int(365.25 * 2)))


class DominanceScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cells = [rc.dominance(TWO_YEARS, cap, 9.95) for cap in rc.CAPITAL_LADDER]

    def test_the_paid_in_line_follows_the_journals_own_deposit_rule(self):
        cell = rc.dominance(TWO_YEARS, 10_000.0, 0.0)
        self.assertAlmostEqual(cell["paid_in"], 10_000.0 + 1_000.0 * (len(TWO_YEARS) - 1), delta=0.01)
        self.assertEqual(cell["months"], len(TWO_YEARS))

    def test_a_commission_free_comparison_is_invariant_to_size_to_the_last_digit(self):
        shares = {round(rc.dominance(TWO_YEARS, cap, 0.0)["gap"] / rc.dominance(TWO_YEARS, cap, 0.0)["paid_in"], 9)
                  for cap in rc.CAPITAL_LADDER}
        self.assertEqual(len(shares), 1, f"commission-free, size moved the comparison: {shares}")

    def test_the_witness_pays_exactly_one_ticket_for_every_two_the_book_pays(self):
        """The whole asymmetry of a two-sleeve book at a per-ticket broker, in one line, checked at every size."""

        for cell in self.cells:
            self.assertEqual(cell["tilt_tickets"], 2 * cell["witness_tickets"], f"at {cell['capital']:,.0f}")

    def test_the_bigger_account_keeps_at_least_as_much_of_the_edge(self):
        shares = [c["gap"] / c["paid_in"] for c in self.cells]
        for earlier, later in zip(shares, shares[1:]):
            self.assertLessEqual(earlier, later + 1e-9, "a smaller account should not be rewarded for being small")

    def test_the_sign_turns_over_somewhere_on_the_ladder_rather_than_being_asserted(self):
        """The claim is that a flip exists in the priced range, not where it happens. A threshold written into a test would
        be a threshold invented by the test."""

        failing = [c for c in self.cells if not c["dominates"]]
        winning = [c for c in self.cells if c["dominates"]]
        self.assertTrue(failing and winning, f"no flip at $9.95: {[c['dominates'] for c in self.cells]}")
        self.assertLess(max(c["capital"] for c in failing), min(c["capital"] for c in winning),
                        "the failing sizes must all be smaller than the winning ones")

    def test_a_free_broker_flips_nothing_at_any_horizon(self):
        for cell in rc.scan(1_000.0, 0.0):
            self.assertTrue(cell["dominates"], f"{cell['horizon']} fails commission-free, which cannot be a cost story")

    def test_the_scan_answers_at_every_horizon_it_names_and_orders_them_shortest_first(self):
        cells = rc.scan(10_000.0, 9.95)
        self.assertEqual([c["horizon"] for c in cells], [label for label, _ in rc.HORIZONS])
        self.assertGreater(cells[-1]["gap"] / cells[-1]["paid_in"], cells[0]["gap"] / cells[0]["paid_in"])

    def test_the_cells_are_serialisable_and_carry_the_ticket_count_the_sheet_prints(self):
        for cell in rc.scan(5_000.0, 4.95):
            json.dumps(cell)
            for key in ("tilt_tickets", "witness_tickets", "tilt_ticket_share", "gap", "paid_in", "dominates"):
                self.assertIn(key, cell)

    def test_the_crossover_report_brackets_rather_than_invents_a_number(self):
        cross = rc.crossover(9.95, closes=TWO_YEARS)
        self.assertFalse(cross["dominates_at_every_size"], "two years at $9.95 must produce at least one failing size")
        self.assertIsNotNone(cross["first_capital_dominating"])
        self.assertLess(cross["last_capital_failing"], cross["first_capital_dominating"])


class TheSheetSeesItsSize(unittest.TestCase):
    def render(self, **kw):
        kw.setdefault("position", "income")
        kw.setdefault("horizon", "recent")
        kw.setdefault("ask", None)
        commission = kw.pop("commission", None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            print(ds.render(ds.sheet(kw["capital"], None, kw["position"], kw["horizon"], None, commission)))
        return out.getvalue()

    def test_the_sheet_names_the_policy_and_the_tool_that_measured_it(self):
        text = self.render(capital=100_000.0)
        self.assertIn("HOW TO EXECUTE IT", text)
        self.assertIn("rebalance_cost.py", text)
        self.assertIn(f"{ds.paper.TILT_BAND_POINTS:g} points", text)

    def test_it_refuses_to_invent_a_broker(self):
        text = self.render(capital=100_000.0)
        self.assertIn("the sheet was not told yours", text)
        self.assertIn("does not depend on size at all", text, "the invariance is the reason a broker matters at all")

    def test_a_small_account_on_a_paid_broker_is_told_to_hold_one_thing(self):
        text = self.render(capital=2_500.0, commission=9.95)
        self.assertIn("REFUSED at this size on this broker", text)
        self.assertIn("one fund", text)
        self.assertIn("FAILS against", text)

    def test_the_same_broker_refuses_nobody_at_a_large_size(self):
        text = self.render(capital=1_000_000.0, commission=9.95)
        self.assertNotIn("REFUSED at this size", text)
        self.assertIn("dominates", text)

    def test_a_broker_tier_is_priced_as_a_share_of_the_edge_rather_than_as_a_dollar_figure(self):
        text = self.render(capital=100_000.0, commission=9.95)
        self.assertIn("keeps", text)
        self.assertIn("of its commission-free two-year edge", text)

    def test_a_negative_commission_is_refused_before_anything_is_computed(self):
        with self.assertRaises(ds.Refused) as got:
            ds.sheet(100_000.0, None, "income", "recent", None, -1.0)
        self.assertIn("negative", str(got.exception))

    def test_the_regenerate_line_carries_the_broker_it_was_told(self):
        """The reproduce line is printed by the CLI rather than the renderer, so the CLI is what gets tested. A sheet that
        reproduces the positions but silently drops the broker assumption would reprint the same table and quietly change the
        verdict on it."""

        def cli(argv):
            out, code = io.StringIO(), None
            saved, sys.argv = sys.argv, ["decision_sheet.py"] + argv
            try:
                with contextlib.redirect_stdout(out):
                    code = ds.main()
            finally:
                sys.argv = saved
            self.assertEqual(code, 0)
            return out.getvalue()

        def repro(argv):
            return [line for line in cli(argv).splitlines() if "regenerate with" in line][0]

        self.assertIn("--commission 9.95", repro(["--capital", "250000", "--commission", "9.95"]))
        self.assertNotIn("--commission", repro(["--capital", "250000"]),
                         "a reproduce line that omits the flag reproduces a different sheet: the same positions, the opposite "
                         "verdict on how to execute them")

    def test_every_percentage_the_sheet_prints_comes_from_the_tool(self):
        cell = next(c for c in rc.scan(10_000.0, 9.95) if c["horizon"] == "two years")
        expected = f"{100 * abs(cell['gap']) / cell['paid_in']:.1f}%"
        self.assertIn(expected, self.render(capital=10_000.0, commission=9.95))


class EveryDollarLineScales(unittest.TestCase):
    """Round 86 found a sheet line wearing a dollar sign that was actually a figure per $100,000.

    `rotation_search` reports capacity per $100,000 of book, and the sheet scales every line built from it except the one
    comparing the best rule against plain SPY, so a $25,000 account and a $400,000 one were told the same monthly number. The
    sign of that comparison is scale-free and the verdict never moved, which is exactly why the defect survived thirty rounds
    of reading this sheet: it only misreported a magnitude. Any future line has to scale or say it is a percentage.
    """

    def numbers(self, capital):
        o = ds.sheet(capital, None, "income", "recent", None)
        return (o["best_rule"]["vs_spy_recent"], o["best_rule"]["vs_control_recent"],
                o["must_beat"]["control"]["recent"])

    def test_the_rule_lines_move_with_the_capital_they_are_quoted_at(self):
        small, mid = self.numbers(25_000.0), self.numbers(100_000.0)
        for got, base in zip(small, mid):
            self.assertAlmostEqual(got, base * 0.25, delta=1e-6,
                                   msg="a monthly dollar figure that does not scale is a percentage in disguise")

    def test_the_scaling_is_linear_over_a_big_range_rather_than_fitted_at_two_points(self):
        base = self.numbers(100_000.0)
        for factor in (0.01, 2.5, 10.0):
            for got, expect in zip(self.numbers(100_000.0 * factor), base):
                self.assertAlmostEqual(got, expect * factor, delta=1e-4 * abs(expect) + 1e-9)


if __name__ == "__main__":
    unittest.main()
