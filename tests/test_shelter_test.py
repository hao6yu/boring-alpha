"""Round 64: the shelter substitution. The first test is that the cash row still says what round 58 published.

Everything else in the file compares shelters against each other, so if the cash row had drifted, the deltas would be
measuring the test. The pin comes first for that reason.
"""

import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import monthly_income_race as mir                            # noqa: E402
import rotation_edge as re_                                  # noqa: E402
import shelter_test as st                                    # noqa: E402
import trend_cost_test as tc                                 # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data       # noqa: E402


def run_shelter(shelter: str, er: float):
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    ordered, rets, bills, base = re_.panel(data, re_.UNKNOWN_ER)
    pos = {d: i for i, d in enumerate(tc.days_of(data, "SPY"))}
    cl = tc.closes_of(data, "SPY")
    closes = {"SPY": [cl[pos[d]] for d in ordered]}
    sig = mir.leg_weights("MA200 monthly", ordered, rets, bills, base, closes, re_.UNKNOWN_ER)
    exp = st.shelter_expense(base, shelter, er)
    path = mir.wealth_path(ordered, rets, bills, exp, st.shelter_weights(sig, shelter))
    keys, monthly = mir.month_marks(ordered, path)
    return {"safe1": mir.safe_amount(monthly, 100_000.0, 10, 0.05, floor=1.0),
            "safe0": mir.safe_amount(monthly, 100_000.0, 10, 0.05, floor=0.0),
            "months": len(monthly), "keys": keys, "path": path, "ordered": ordered}


class TheCashRowIsRoundFiftysEight(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cash = run_shelter(st.CASH, 0.0)

    def test_the_cash_shelter_still_prints_round_58s_number(self):
        """$593.13 is round 58's published withdrawal capacity for MA200 monthly on this panel. A cent off means the
        shelter comparison is measuring the harness, not the shelter."""

        self.assertAlmostEqual(self.cash["safe1"], 593.13, delta=0.01,
                               msg=f"the cash shelter now supports {self.cash['safe1']:.2f}, not round 58's 593.13")

    def test_the_looser_promise_always_supports_at_least_as_much(self):
        self.assertGreater(self.cash["safe0"], self.cash["safe1"])

    def test_the_panel_is_the_one_round_58_scored(self):
        self.assertEqual(self.cash["ordered"][0], dt.date(2006, 2, 7))
        self.assertEqual(self.cash["months"], 246, "the complete-month count moved; every figure in this file is"
                                                  " comparable to round 58 only while this is 246")

    def test_the_sample_is_the_same_for_every_shelter(self):
        n = self.cash["months"]
        for shelter in st.SHELTERS:
            self.assertEqual(run_shelter(shelter, 0.0035)["months"], n, shelter)


class TheWeightsAreWhatTheySay(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.ordered, cls.rets, cls.bills, cls.base = re_.panel(cls.data, re_.UNKNOWN_ER)
        pos = {d: i for i, d in enumerate(tc.days_of(cls.data, "SPY"))}
        cl = tc.closes_of(cls.data, "SPY")
        cls.closes = {"SPY": [cl[pos[d]] for d in cls.ordered]}
        cls.sig = mir.leg_weights("MA200 monthly", cls.ordered, cls.rets, cls.bills, cls.base,
                                  cls.closes, re_.UNKNOWN_ER)

    def test_a_cash_shelter_is_the_signal_untouched(self):
        self.assertEqual([tuple(w) for w in st.shelter_weights(self.sig, st.CASH)],
                         [tuple(w) for w in self.sig])

    def test_an_etf_shelter_holds_the_remainder_and_nothing_else(self):
        i_spy = re_.UNIVERSE.index("SPY")
        i_tlt = re_.UNIVERSE.index("TLT")
        for a, b in zip(self.sig, st.shelter_weights(self.sig, "TLT")):
            self.assertAlmostEqual(float(a[i_spy]), float(b[i_spy]), places=12, msg="the equity leg changed")
            self.assertAlmostEqual(sum(b), 1.0, places=12, msg="the account went partly into cash by accident")
            self.assertAlmostEqual(float(b[i_tlt]), 1.0 - float(a[i_spy]), places=12)
            self.assertEqual(sum(float(x) for k, x in enumerate(b) if k not in (i_spy, i_tlt)), 0.0)

    def test_a_composite_shelter_splits_the_remainder(self):
        w = st.shelter_weights(self.sig, "IEF+TLT")
        i_ief, i_tlt = re_.UNIVERSE.index("IEF"), re_.UNIVERSE.index("TLT")
        for row in w:
            self.assertAlmostEqual(row[i_ief], row[i_tlt], places=12)
            self.assertAlmostEqual(row[i_ief] + row[i_tlt], 1.0 - row[re_.UNIVERSE.index("SPY")], places=12)

    def test_an_overweight_equity_leg_is_refused_not_absorbed(self):
        fat = [tuple([1.5 if k == re_.UNIVERSE.index("SPY") else 0.0 for k in range(len(re_.UNIVERSE))])
               for _ in self.sig]
        with self.assertRaises(ValueError):
            st.shelter_weights(fat, "TLT")

    def test_the_fee_is_carried_by_the_shelter_and_not_by_the_equity(self):
        cheap = st.shelter_expense(self.base, "TLT", 0.0020)
        dear = st.shelter_expense(self.base, "TLT", 0.0060)
        self.assertEqual(cheap["SPY"], dear["SPY"], "the equity leg's fee moved")
        self.assertAlmostEqual(dear["TLT"] - cheap["TLT"], 0.0040, places=12)
        self.assertEqual(st.shelter_expense(self.base, st.CASH, 0.0060), dict(self.base),
                         "a cash shelter was given an expense ratio; bills are not a fund")

    def test_a_dearer_shelter_cannot_support_more_income(self):
        lo = run_shelter("TLT", 0.0020)["safe1"]
        hi = run_shelter("TLT", 0.0060)["safe1"]
        self.assertLess(hi, lo, f"a 60bp shelter supports {hi:.2f} against a 20bp one at {lo:.2f}")


class TheSheltersThemselves(unittest.TestCase):

    def test_a_drawdown_of_a_hand_built_path(self):
        self.assertAlmostEqual(st.max_drawdown([1.0, 1.2, 0.6, 0.9]), 0.5, places=12)
        self.assertEqual(st.max_drawdown([1.0, 1.1, 1.2, 1.3]), 0.0)
        self.assertAlmostEqual(st.max_drawdown([1.0, 0.5]), 0.5, places=12)

    def test_the_composite_shelter_is_the_weighted_average_of_its_halves(self):
        r = st.composite_rets(self.rets_of(), "IEF+TLT")
        a, b = self.rets_of()["IEF"], self.rets_of()["TLT"]
        self.assertEqual(len(r), len(a))
        for i in (0, len(r) // 2, len(r) - 1):
            self.assertAlmostEqual(r[i], 0.5 * a[i] + 0.5 * b[i], places=15)

    def setUp(self):
        self.rets_of = lambda: {"IEF": [0.001] * 30, "TLT": [-0.001] * 30,
                                "SPY": [0.002] * 30, "GLD": [0.0] * 30, "DBC": [0.003] * 30}

    def test_the_composites_drawdown_sits_between_its_halves(self):
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        _o, rets, _b, _e = re_.panel(data, re_.UNKNOWN_ER)
        ief = st.panel_stats(rets, "IEF")
        tlt = st.panel_stats(rets, "TLT")
        both = st.panel_stats(rets, "IEF+TLT")
        self.assertTrue(min(ief[1], tlt[1]) <= both[1] <= max(ief[1], tlt[1]),
                        f"a 50/50 bond shelter drew down {both[1]:.1%}, outside {ief[1]:.1%} and {tlt[1]:.1%}")

    def test_cagr_of_a_constant_series_compounds_over_the_right_horizon(self):
        r = {"X": [0.01] * int(tc.DAYS)}
        cagr, mdd = st.panel_stats(r, "X")
        self.assertAlmostEqual(cagr, 1.01 ** tc.DAYS - 1.0, places=9)
        self.assertEqual(mdd, 0.0)


class TheVerdict(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rows = {(s, er): run_shelter(s, er) for s in ("IEF", "TLT", "GLD", "DBC", "IEF+TLT")
                    for er in st.ER_GRID}
        cls.cash = run_shelter(st.CASH, 0.0)["safe1"]

    def test_the_bond_and_gold_shelters_clear_the_bar_even_at_the_pessimal_fee(self):
        for s in ("IEF", "TLT", "GLD", "IEF+TLT"):
            gain = self.rows[(s, max(st.ER_GRID))]["safe1"] - self.cash
            self.assertGreater(gain, st.MATERIAL, f"{s} as a shelter is worth {gain:+.2f}/mo at its worst fee")

    def test_the_sign_never_depends_on_the_unposted_fee(self):
        for s in ("IEF", "TLT", "GLD", "DBC", "IEF+TLT"):
            signs = {(self.rows[(s, er)]["safe1"] - self.cash) > st.MATERIAL for er in st.ER_GRID}
            self.assertEqual(len(signs), 1, f"{s}: the verdict turns on an expense ratio this repository does not post")

    def test_the_metric_can_say_no(self):
        """DBC is not a slightly worse shelter, it is the one that breaks the plan. If it comes back clean, the
        scoring has gone soft rather than the commodities having improved."""

        d = self.rows[("DBC", 0.0035)]
        self.assertLess(d["safe1"], self.cash)
        self.assertLess(d["safe1"], 400.0, f"DBC as a shelter now supports {d['safe1']:.2f}/mo")

    def test_income_follows_what_the_shelter_pays_while_held_not_over_its_whole_history(self):
        """The finding, pinned. Ranking by unconditional return gets IEF and TLT the wrong way round; ranking by the
        return the shelter earns during the episodes the signal chooses to hold it in gets every pair right. The
        shelter's usefulness is a property of the signal's timing, not of the asset class."""

        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        _o, rets, _b, _e = re_.panel(data, re_.UNKNOWN_ER)
        pos = {d: i for i, d in enumerate(tc.days_of(data, "SPY"))}
        cl = tc.closes_of(data, "SPY")
        closes = {"SPY": [cl[pos[d]] for d in _o]}
        sig = mir.leg_weights("MA200 monthly", _o, rets, _b, _e, closes, re_.UNKNOWN_ER)
        held = [1.0 - float(w[re_.UNIVERSE.index("SPY")]) > 1e-9 for w in sig]
        legs = ("DBC", "IEF", "IEF+TLT", "TLT", "GLD")
        by_income = sorted(legs, key=lambda s: self.rows[(s, 0.0035)]["safe1"])
        by_held = sorted(legs, key=lambda s: st.held_stats(rets, s, held)[0])
        self.assertEqual(by_income, by_held,
                         f"income orders {by_income}, held returns order {by_held}: the mechanism has changed")
        self.assertEqual(by_income[-1], "GLD")
        self.assertEqual(by_income[0], "DBC")
        singles = ("IEF", "TLT", "GLD", "DBC")
        uncond = {s: st.panel_stats(rets, s)[0] for s in singles}
        held_r = {s: st.held_stats(rets, s, held)[0] for s in singles}
        self.assertGreater(uncond["IEF"], uncond["TLT"], "the unconditional returns no longer invert; check the panel")
        self.assertLess(held_r["IEF"], held_r["TLT"],
                        "the held-episode returns no longer invert the unconditional pair; the finding is stale")
        for s in ("IEF", "TLT", "GLD"):
            self.assertGreater(held_r[s], uncond[s], f"{s} no longer pays more while held than over its history")
        self.assertLess(held_r["DBC"], uncond["DBC"], "commodities now pay while held; why did the plan stop failing?")


class TheCapacityScan(unittest.TestCase):
    """Round 65: round 63's ceiling, re-measured under the better shelter."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.ordered, cls.rets, cls.bills, cls.base = re_.panel(cls.data, re_.UNKNOWN_ER)
        pos = {d: i for i, d in enumerate(tc.days_of(cls.data, "SPY"))}
        cl = tc.closes_of(cls.data, "SPY")
        cls.closes = {"SPY": [cl[pos[d]] for d in cls.ordered]}
        cls.sig = mir.leg_weights("MA200 monthly", cls.ordered, cls.rets, cls.bills, cls.base,
                                  cls.closes, re_.UNKNOWN_ER)
        cls.bench = mir.month_marks(cls.ordered, mir.wealth_path(cls.ordered, cls.rets, cls.bills, cls.base,
                                                                 mir.leg_weights("SPY hold", cls.ordered, cls.rets,
                                                                                 cls.bills, cls.base, cls.closes,
                                                                                 re_.UNKNOWN_ER)))[1]
        cls.m = {s: mir.month_marks(cls.ordered, mir.wealth_path(cls.ordered, cls.rets, cls.bills,
                                                                st.shelter_expense(cls.base, s, 0.0035),
                                                                st.shelter_weights(cls.sig, s)))[1]
                 for s in st.SHELTERS}
        cls.cap = {s: st.capacity(cls.m[s], cls.bench, 100_000.0, 10) for s in st.SHELTERS}

    def test_a_plan_cannot_be_riskier_than_itself(self):
        cap, info = st.capacity(self.bench, self.bench, 100_000.0, 10)
        self.assertIsNone(cap)
        self.assertEqual(info["flips"], 0)

    def test_a_better_shelter_lifts_the_ceiling_and_a_worse_one_drops_it(self):
        """"Round 63's whole finding, re-measured with the shelter substituted: the bond shelter buys about two more
        months of grid, gold buys about seven, commodities give away twenty."""

        cash = self.cap[st.CASH][0]
        self.assertIsNotNone(cash)
        self.assertEqual(int(cash) % 25, 0, "the capacity must land on a grid rung")
        self.assertLessEqual(cash, max(st.CAP_GRID))
        self.assertGreater(self.cap["IEF"][0], cash, "IEF as a shelter did not lift the ceiling")
        self.assertGreater(self.cap["GLD"][0], self.cap["IEF"][0])
        self.assertLess(self.cap["DBC"][0], cash, "DBC as a shelter did not cut the ceiling")

    def test_an_oscillating_ordering_is_reported_rather_than_smoothed(self):
        """The failure rates are step functions over 127 windows, so two steep curves can step over each other more
        than once. The first crossing is quoted and the count of crossings travels with it."""

        self.assertEqual(self.cap[st.CASH][1]["flips"], 1)
        self.assertGreater(self.cap["TLT"][1]["flips"], 1,
                           "TLT's ordering stopped oscillating; the (3 flips) annotation is now a lie")
        for _s, (_cap, info) in self.cap.items():
            self.assertGreaterEqual(info["rungs"], 40, "the sweep stopped early; the capacity is being read off a"
                                                      " truncated grid")

    def test_a_plan_that_is_never_riskier_than_the_benchmark_reports_no_ceiling(self):
        """`None` has to mean "no rung in the grid", not "the sweep went wrong", so it is exercised against a
        benchmark built to lose everywhere without dying outright."""

        worse = [r - 0.004 for r in self.bench]
        cap, info = st.capacity(self.m[st.CASH], worse, 100_000.0, 10)
        self.assertIsNone(cap)
        self.assertGreater(info["rungs"], 40, "no crossing was found because the sweep never ran")

    def test_a_dead_benchmark_stops_the_sweep_instead_of_inventing_a_ceiling(self):
        dead = [-0.5] * 246
        cap, info = st.capacity(self.m[st.CASH], dead, 100_000.0, 10)
        self.assertIsNone(cap)
        self.assertEqual(info["rungs"], 0)
        self.assertIsNone(info["bench_at_end"])

    def test_the_capacity_is_measured_where_the_failure_rates_still_mean_something(self):
        """Quoting a ceiling is only useful while the benchmark can still be beaten, so the sweep must stop once the
        benchmark fails in every window."""

        cap, info = st.capacity(self.m[st.CASH], self.bench, 100_000.0, 10)
        self.assertLess(info["bench_at_end"], 1.0)
        st_c = mir.plan_stats(self.m[st.CASH], 100_000.0, cap, 10, 0.0, 1.0)
        self.assertGreater(st_c["p_fail"], 0.10, "the capacity moved into a region where the plan is comfortably"
                                                 " safe; re-read what the ceiling is describing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
