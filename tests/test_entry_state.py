"""Round 62: the 2x2 entry-state table — where a rule's protection lands, not how much it averages to.

The synthetic cases come first because they define the cells. If the table cannot put a hand-built leg in the right
box, the archive's striking table means nothing.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import entry_state as es                                 # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


def synth(rows_by_leg):
    """Contingency straight off hand-built rows, bypassing the archive."""

    return es.contingency({leg: rows for leg, rows in rows_by_leg.items()})


def rows(dates, failed, multiple=1.0):
    return [{"date": d, "failed": f, "terminal": 100_000.0 * multiple, "multiple": multiple}
            for d, f in zip(dates, failed)]


DATES = [("20%02d-01-01" % (10 + i)) for i in range(10)]


class TheCellsAreDefinedRight(unittest.TestCase):

    def test_the_cells_are_exhaustive_and_partition_the_starts(self):
        c = synth({es.BENCH: rows(DATES, [False, True, False, True, False, False, False, False, False, False]),
                   "x": rows(DATES, [False, False, True, True, False, False, False, False, False, False])})["x"]
        self.assertEqual(c["insurance"], 1, "the leg survived where the index failed and that is not insurance?")
        self.assertEqual(c["redundant"], 1)
        self.assertEqual(c["cost"], 1)
        self.assertEqual(c["fine"], 7)
        self.assertEqual(c["n"], 10)
        self.assertEqual(sum(c[k] for k in es.CELLS), c["n"])

    def test_a_clone_of_the_index_is_all_redundant_and_costs_nothing(self):
        b = [False, True, False, True, False, False, False, False, False, False]
        c = synth({es.BENCH: rows(DATES, b), "clone": rows(DATES, list(b))})["clone"]
        self.assertEqual((c["insurance"], c["redundant"], c["cost"]), (0, 2, 0))
        self.assertEqual(c["fine"], 8)

    def test_a_rule_that_always_survives_is_pure_insurance(self):
        b = [False, True, True, True, False, False, False, False, False, False]
        c = synth({es.BENCH: rows(DATES, b), "cash": rows(DATES, [False] * 10)})["cash"]
        self.assertEqual((c["insurance"], c["redundant"], c["cost"]), (3, 0, 0))
        self.assertEqual(c["concordance"], 0.0)

    def test_a_rule_that_always_fails_pays_the_cost_cell(self):
        b = [False, True, True, True, False, False, False, False, False, False]
        c = synth({es.BENCH: rows(DATES, b), "junk": rows(DATES, [True] * 10)})["junk"]
        self.assertEqual((c["insurance"], c["redundant"], c["cost"]), (0, 3, 7))
        self.assertEqual(c["concordance"], 1.0)
        self.assertAlmostEqual(c["p_fail_self"], 1.0)

    def test_concordance_is_undefined_when_the_benchmark_never_fails(self):
        c = synth({es.BENCH: rows(DATES, [False] * 10), "x": rows(DATES, [True] * 10)})["x"]
        self.assertIsNone(c["concordance"])
        self.assertEqual(c["cost"], 10)

    def test_the_benchmark_row_cannot_insure_or_cost_itself(self):
        b = [False, True, False, True, False, False, False, False, False, False]
        c = synth({es.BENCH: rows(DATES, b)})[es.BENCH]
        self.assertEqual((c["insurance"], c["cost"]), (0, 0))
        self.assertEqual(c["concordance"], 1.0)


class ArchiveTable(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.wanted = ("SPY hold", "MA200 monthly", "static 60/40")
        all_series = es.legs_from_long_record(cls.data, 10)
        cls.series = {k: v for k, v in all_series.items() if k in cls.wanted}
        cls.starts = es.starts(cls.series, 10)
        cls.withdraw = es.score(cls.series, cls.starts, 10, 435.47, 0.0, 100_000.0)
        cls.cells = es.contingency(cls.withdraw)

    def test_every_scored_start_has_the_full_plan_ahead_of_it_in_every_leg(self):
        self.assertGreater(len(self.starts), 250)
        for d0, s in self.starts:
            self.assertEqual(self.series[es.BENCH][0][s], d0)
            for leg, (dates, m) in self.series.items():
                i = dates.index(d0)
                self.assertGreaterEqual(i + 120, 120)
                self.assertLessEqual(i + 120, len(m), f"{leg} has no 10-year window from {d0}")
                self.assertEqual(dates[i:i + 120], self.series[es.BENCH][0][s:s + 120])

    def test_the_cells_partition_the_start_set_for_every_leg(self):
        for leg, c in self.cells.items():
            self.assertEqual(sum(c[k] for k in es.CELLS), len(self.starts), leg)
            self.assertEqual(c["n"], len(self.starts))
            self.assertAlmostEqual(c["p_fail_self"], (c["redundant"] + c["cost"]) / c["n"], places=12)

    def test_the_index_fails_in_fifty_six_entries_and_the_rule_in_none_at_all(self):
        """"Perfect" is a strong word and this table earns it: 56 of 283 entries break the index at $435.47/mo and the
        trend rule breaks in none of them, nor in any entry the index survived. If the record is ever extended and
        that 0 moves, this test is where the claim changes rather than quietly decays."""

        ma = self.cells["MA200 monthly"]
        self.assertEqual(self.cells[es.BENCH]["redundant"], 56)
        self.assertEqual((ma["insurance"], ma["redundant"], ma["cost"]), (56, 0, 0))
        self.assertEqual(ma["p_fail_self"], 0.0)
        self.assertEqual(ma["concordance"], 0.0)

    def test_the_zero_is_a_measurement_and_not_a_stuck_boolean(self):
        """A leg that never fails at one payout might just not be scored. Raise the payout and the count has to move."""

        moved = []
        for payout in (600.0, 800.0, 1100.0):
            sc = es.score(self.series, self.starts, 10, payout, 0.0, 100_000.0)
            moved.append(sum(1 for r in sc["MA200 monthly"] if r["failed"]))
        # Measured: 0 failures at the table's $435.47, 33 at $600, 134 at $800, 262 at $1,100. The monotone ladder is
        # the point — the zero in the table is one rung below where failures start, not an untested leg.
        self.assertEqual(moved, sorted(moved))
        self.assertGreater(moved[0], 0, "the leg never fails at any payout, which means it is not being scored")
        self.assertGreater(moved[2], moved[0])

    def test_the_protection_comes_from_one_contiguous_episode(self):
        """The caveat that keeps the perfect table from being read as a general property of the rule."""

        fails = [r["date"] for r in self.withdraw[es.BENCH] if r["failed"]]
        self.assertGreaterEqual(min(fails).year, 1998)
        self.assertLessEqual(max(fails).year, 2007)
        self.assertGreaterEqual(sum(1 for d in fails if d.year <= 2002) / len(fails), 0.9)

    def test_the_bond_allocation_is_cost_without_insurance_on_a_payout(self):
        c = self.cells["static 60/40"]
        self.assertEqual(c["insurance"], 0, "the 60/40 now saves an entry the index could not survive")
        self.assertEqual(c["redundant"], self.cells[es.BENCH]["redundant"])
        self.assertGreater(c["cost"], 30, f"the cost cell has fallen to {c['cost']}: re-read the note")
        self.assertEqual(c["concordance"], 1.0)

    def test_the_contribution_frame_reproduces_round_60s_rate_exactly(self):
        """Two independent implementations of the same plan — this file's own simulation loop and round 60's
        window walker — have to agree on the one number both rounds publish."""

        sc = es.score(self.series, self.starts, 10, 0.0, 1_000.0, 0.0)
        f = sum(1 for r in sc[es.BENCH] if r["failed"])
        self.assertEqual(f, 12)
        self.assertAlmostEqual(f / len(self.starts), 0.042, places=3)
        c = es.contingency(sc)["MA200 monthly"]
        self.assertEqual((c["insurance"], c["redundant"], c["cost"]), (12, 0, 0))
        bond = es.contingency(sc)["static 60/40"]
        self.assertLess(bond["concordance"], 1.0,
                        "the bond leg now shares every index failure; r62's partial-insurance reading is stale")

    def test_the_worst_entries_for_a_payout_are_the_dot_com_years(self):
        worst = sorted(self.withdraw[es.BENCH], key=lambda r: r["multiple"])[:3]
        self.assertEqual({w["date"].year for w in worst}, {2000},
                         f"the three worst entries are now {[str(w['date']) for w in worst]}")
        for w in worst:
            self.assertLess(w["multiple"], 0.40, "the index's worst 10-year payout entry is no longer a rout")
        contrib = es.score(self.series, self.starts, 10, 0.0, 1_000.0, 0.0)
        worst2 = sorted(contrib[es.BENCH], key=lambda r: r["multiple"])[:3]
        for w in worst2:
            self.assertTrue(1998 <= w["date"].year <= 2009,
                            f"a contribution plan now fails hardest entering {w['date']}")


class TheCliRefusesNonsense(unittest.TestCase):

    def test_the_reference_leg_cannot_be_dropped_from_the_table(self):
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "entry_state.py"), "--legs", "MA200 monthly"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SPY hold", r.stdout + r.stderr)

    def test_an_unknown_leg_is_listed_not_silently_ignored(self):
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "entry_state.py"), "--legs", "SPY hold,fibonacci"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("fibonacci", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
