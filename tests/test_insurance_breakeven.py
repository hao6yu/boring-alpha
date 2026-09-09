"""Round 63: the payout curve — where the rule's insurance is worth something, and where it stops being.

The invariants come first. A curve whose endpoints are wrong in the wiring (a payout of zero that can still fail, or a
median that rises as you take more out) would produce a confident, meaningless breakeven.
"""

import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import insurance_breakeven as ib                          # noqa: E402
import withdrawal_capacity as wc                          # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402


def fake_series(n_months=400, bench=0.006, rule=0.006, bond=0.004):
    dates = [dt.date(1993, 1, 1) + dt.timedelta(days=30 * i) for i in range(n_months)]
    return {ib.BENCH: (dates, [bench] * n_months),
            "MA200 monthly": (dates, [rule] * n_months),
            "static 60/40": (dates, [bond] * n_months)}


class InvariantsBeforeFindings(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.series = {k: v for k, v in ib.es.legs_from_long_record(cls.data, 10).items() if k in ib.LEGS}
        cls.wins = ib.windows(cls.series, 1993, 2100, 10)

    def test_the_windows_are_aligned_across_legs_and_the_right_length(self):
        n = len(self.wins[ib.BENCH])
        self.assertGreater(n, 250)
        for leg, rows in self.wins.items():
            self.assertEqual(len(rows), n, leg)
            self.assertEqual([d for d, _w in rows], [d for d, _w in self.wins[ib.BENCH]], leg)
            for d0, w in rows:
                self.assertEqual(len(w), 120, f"{leg} window at {d0} is not ten years")

    def test_the_year_range_is_honoured(self):
        early = ib.windows(self.series, 1993, 2005, 10)
        self.assertTrue(all(1993 <= d.year <= 2005 for d, _w in early[ib.BENCH]))
        self.assertLess(len(early[ib.BENCH]), len(self.wins[ib.BENCH]))
        recent = ib.windows(self.series, 2016, 2100, 10)
        self.assertLess(len(recent[ib.BENCH]), 12,
                        "a ten-year plan can now be started and finished inside 2016-onward; the sample boundary moved")

    def test_zero_withdrawal_fails_only_by_ending_below_where_it_started(self):
        """The promise is "ends whole", so a plan that takes nothing out can still fail — the 2000s do. Recomputed
        here from the simulation directly, and the index's figure is round 58's published 8%: the same promise read
        by two tools, twelve rounds apart."""

        c = ib.curve(self.series, self.wins, 0.0, 100_000.0, 10)
        for leg in ib.LEGS:
            want = []
            for _d0, w in self.wins[leg]:
                r = ib.ps.simulate(w, 100_000.0, 0.0, 0.0, 0.0)
                want.append(0 if r["survived"] else 1)
            self.assertAlmostEqual(c[leg]["p_fail"], sum(want) / len(want), places=12, msg=leg)
            self.assertGreater(c[leg]["median"], 1.0, leg)
        self.assertAlmostEqual(c[ib.BENCH]["p_fail"], 0.0848, places=3,
                               msg="the no-withdrawal failure rate moved off round 58's 8%")

    def test_a_bigger_withdrawal_never_leaves_more_behind(self):
        prev = {}
        for payout in (0.0, 200.0, 435.47, 600.0, 800.0, 1_000.0):
            c = ib.curve(self.series, self.wins, payout, 100_000.0, 10)
            for leg in ib.LEGS:
                if leg in prev:
                    self.assertLessEqual(c[leg]["median"], prev[leg] + 1e-12,
                                        f"{leg} ends richer at ${payout}/mo than at a smaller payout")
                prev[leg] = c[leg]["median"]

    def test_failure_risk_grows_with_the_withdrawal(self):
        prev = {l: -1.0 for l in ib.LEGS}
        for payout in (0.0, 200.0, 435.47, 600.0, 800.0, 1_000.0, 1_200.0):
            c = ib.curve(self.series, self.wins, payout, 100_000.0, 10)
            for leg in ib.LEGS:
                self.assertGreaterEqual(c[leg]["p_fail"], prev[leg] - 1e-12, leg)
                prev[leg] = c[leg]["p_fail"]

    def test_the_whole_thing_scales_with_the_money_and_not_otherwise(self):
        """Doubling the starting balance must leave every multiple alone and double the payout that breaks the
        protection — otherwise the per-$100,000 figures in the note cannot be scaled to a reader's balance."""

        a = ib.curve(self.series, self.wins, 435.47, 100_000.0, 10)
        b = ib.curve(self.series, self.wins, 870.94, 200_000.0, 10)
        for leg in ib.LEGS:
            self.assertAlmostEqual(a[leg]["median"], b[leg]["median"], places=9)
            self.assertAlmostEqual(a[leg]["p_fail"], b[leg]["p_fail"], places=9)
        x = ib.risk_crossover(self.wins, self.series, 100_000.0, 10, "MA200 monthly", 1_500.0, 25.0)
        y = ib.risk_crossover(self.wins, self.series, 200_000.0, 10, "MA200 monthly", 3_000.0, 50.0)
        self.assertIsNotNone(x)
        self.assertIsNotNone(y)
        self.assertAlmostEqual(y, 2 * x, delta=50.0)


class TheScansBehaveOnFabricatedSeries(unittest.TestCase):

    def test_a_leg_identical_to_the_index_is_never_called_better(self):
        s = fake_series(rule=0.006)
        w = ib.windows(s, 1993, 2100, 10)
        be, _d = ib.breakeven(w, s, 100_000.0, 10, "MA200 monthly", 1_200.0, 50.0)
        self.assertIsNone(be, "a clone of the index came out ahead of the index")
        self.assertIsNone(ib.risk_crossover(w, s, 100_000.0, 10, "MA200 monthly", 1_200.0, 50.0))

    def test_a_leg_that_earns_more_every_month_is_ahead_at_once(self):
        s = fake_series(rule=0.007)
        w = ib.windows(s, 1993, 2100, 10)
        be, d = ib.breakeven(w, s, 100_000.0, 10, "MA200 monthly", 1_200.0, 50.0)
        self.assertEqual(be, 0.0)
        self.assertGreater(d, 0.0)

    def test_a_leg_that_earns_less_never_clears_the_bar_and_fails_first(self):
        s = fake_series(rule=0.003)
        w = ib.windows(s, 1993, 2100, 10)
        be, _d = ib.breakeven(w, s, 100_000.0, 10, "MA200 monthly", 1_200.0, 50.0)
        self.assertIsNone(be)
        self.assertIsNotNone(ib.risk_crossover(w, s, 100_000.0, 10, "MA200 monthly", 1_200.0, 50.0),
                            "a leg earning 0.3%/mo never fails before the index? check the scan")

    def test_the_units_of_the_difference_are_dollars_a_month(self):
        s = fake_series(rule=0.007)
        w = ib.windows(s, 1993, 2100, 10)
        d = ib.difference(w, s, 300.0, 100_000.0, 10, "MA200 monthly")
        c = ib.curve(s, w, 300.0, 100_000.0, 10)
        self.assertAlmostEqual(d, (c["MA200 monthly"]["median"] - c[ib.BENCH]["median"]) * 100_000.0 / 120, places=9)


class TheArchiveCurve(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.series = {k: v for k, v in ib.es.legs_from_long_record(cls.data, 10).items() if k in ib.LEGS}
        cls.slices = {label: ib.windows(cls.series, y0, y1, 10)
                      for label, y0, y1 in (("whole", 1993, 2100), ("2006", 2006, 2100), ("pre06", 1993, 2005))}

    def test_the_return_verdict_flips_with_the_sample_and_not_with_the_payout(self):
        """Whole record: the rule is ahead of the index at every payout, even zero. Since 2006: behind at every
        payout. Same rule, same costs, one crossing that is set by which years you include — the round's actual
        finding, and the reason neither round 58 nor round 60 was wrong."""

        full, _ = ib.breakeven(self.slices["whole"], self.series, 100_000.0, 10, "MA200 monthly", 1_500.0, 25.0)
        recent, _ = ib.breakeven(self.slices["2006"], self.series, 100_000.0, 10, "MA200 monthly", 1_500.0, 25.0)
        self.assertEqual(full, 0.0)
        self.assertIsNone(recent)

    def test_the_protection_has_a_capacity_and_the_bond_leg_holds_a_third_of_it(self):
        rule = ib.risk_crossover(self.slices["whole"], self.series, 100_000.0, 10, "MA200 monthly", 1_500.0, 25.0)
        bond = ib.risk_crossover(self.slices["whole"], self.series, 100_000.0, 10, "static 60/40", 1_500.0, 25.0)
        self.assertIsNotNone(rule)
        self.assertGreaterEqual(rule, 750.0)
        self.assertLessEqual(rule, 950.0)
        self.assertIsNotNone(bond)
        self.assertGreater(rule, 2 * bond, f"the rule insures ${rule}/mo and the 60/40 ${bond}/mo: the 2x gap closed")

    def test_the_pre_2006_sample_never_turns_the_rule_into_the_riskier_leg(self):
        x = ib.risk_crossover(self.slices["pre06"], self.series, 100_000.0, 10, "MA200 monthly", 1_500.0, 25.0)
        self.assertIsNone(x, "the trend rule is now the riskier leg inside 1993-2005; the insurance band has shrunk")


if __name__ == "__main__":
    unittest.main(verbosity=2)
