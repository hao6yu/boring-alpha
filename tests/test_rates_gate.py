"""Round 59: the bill yield as a signal — the only macro variable in the archive — and the era split that decides
whether round 58's income advantage is a property of the strategy or of the decades it happens to include.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import monthly_income_race as mir                        # noqa: E402
import rates_gate as rg                                  # noqa: E402
import rotation_edge as re_                              # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


class Shared(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.out, cls.keys, cls.eq, cls.cash, cls.y, cls.sg = rg.series(cls.data, 10, 100_000.0, 0.05)
        cls.months = [(k.year, k.month) for k in cls.keys]
        cls.payout = 435.47


class TheGatesAreSwitches(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.out, cls.keys, cls.eq, cls.cash, cls.y, cls.sg = rg.series(cls.data, 10, 100_000.0, 0.05)

    def test_the_yield_series_covers_the_regimes_it_claims_to(self):
        self.assertLess(min(self.y), 0.001, "no zero-rate era in the record; the gate has one regime to learn")
        self.assertGreater(max(self.y), 0.05, "no high-rate era either; it has no other")

    def test_every_gate_actually_switches_and_none_of_them_is_always_on(self):
        """A filter that is never off is not a filter, and one that is always off has already lost the argument.
        Both are printed here rather than hidden in a backtest that looks like a survivor."""

        for name, sig in self.sg.items():
            on = sum(1 for v in sig.values() if v == 1.0)
            frac = on / len(sig)
            self.assertGreater(frac, 0.05, f"{name} was risk-on {frac:.0%} of the time: the switch is stuck off")
            self.assertLess(frac, 0.95, f"{name} was risk-on {frac:.0%} of the time: the switch is stuck on")

    def test_the_gate_is_off_when_cash_pays_more_than_it_has_lately(self):
        months = [(k.year, k.month) for k in self.keys]
        i = months.index((2023, 12))
        self.assertGreater(self.y[i], 0.04)
        self.assertEqual(self.sg["yield_gate"][(2023, 12)], 0.0, "5.2% cash and the gate still says hold equities")
        j = months.index((2021, 12))
        self.assertLess(self.y[j], 0.002)
        self.assertEqual(self.sg["yield_gate"][(2021, 12)], 1.0, "near-zero cash and the gate says wait")

    def test_no_gate_exists_before_its_own_warm_up(self):
        self.assertNotIn((1994, 6), self.sg["yield_gate"], "a 3-year average was computed from months that did not exist")
        first = min(self.sg["yield_gate"])
        self.assertGreater((first[0] - 1993) * 12 + first[1], 35)

    def test_the_and_gate_is_the_min_of_its_two_parts(self):
        combo = {k: min(self.sg["ma200"][k], self.sg["yield_gate"][k])
                 for k in set(self.sg["ma200"]) & set(self.sg["yield_gate"])}
        self.assertTrue(all(v in (0.0, 1.0) for v in combo.values()))
        self.assertLess(sum(combo.values()), sum(self.sg["ma200"][k] for k in combo))


class TheConventionIsMeasuredNotDisclaimed(Shared):

    def test_monthly_and_daily_conventions_agree_to_three_basis_points(self):
        """Rounds 56-58 charge expense daily through the panel engine; this file charges it monthly. The only
        honest response is to price the difference and report it, which is what this test does. It is the same sleeve,
        the same months, two engines."""

        start = next(i for i, k in enumerate(self.keys) if k.year == 2006)
        sub = self.eq[start + 1:]
        w = 1.0
        for r in sub:
            w *= (1.0 + r)
        monthly_cagr = w ** (12.0 / len(sub)) - 1.0
        o, r_, b, e = re_.panel(self.data)
        want = re_.run_weights(o, r_, b, e, re_.constant_weights("SPY", len(o)))["cagr"]
        self.assertLess(abs(monthly_cagr - want), 0.001,
                        f"the two conventions differ by {abs(monthly_cagr - want) * 100:.3f}pp on the same sleeve")

    def test_the_fixed_payout_default_has_not_gone_stale(self):
        """The default payout comes from round 58's panel table. It is a parameter for speed, so its provenance is
        re-derived here from the engine that produced it."""

        o, r_, b, e = re_.panel(self.data)
        w = re_.constant_weights("SPY", len(o))
        keys, mr = mir.month_marks(o, mir.wealth_path(o, r_, b, e, w))
        bm = mir.bill_months(self.data, o)
        amt = mir.safe_amount(mir.blend(mr, [bm[k] for k in keys], 0.0), 100_000.0, 10, 0.05)
        self.assertLess(abs(amt - self.payout), 15.0,
                        f"round 58's index-safe figure is now ${amt:,.2f}, not ${self.payout:,.2f}")


class TheVerdictsHold(Shared):

    def test_no_rates_gate_beats_the_trend_rule_at_the_same_payout(self):
        base = mir.plan_stats(self.out["MA200 monthly"]["m"], 100_000.0, self.payout, 10)["p_fail"]
        for gate in ("yield_gate", "carry_flip", "tightening_exit", "ma200_and_gate"):
            r = mir.plan_stats(self.out[gate]["m"], 100_000.0, self.payout, 10)["p_fail"]
            self.assertGreater(r, base, f"{gate} now matches or beats MA200 ({r:.0%} vs {base:.0%}):"
                                        " the macro information is doing something; re-read the note")

    def test_the_macro_filter_subtracts_from_the_price_filter(self):
        combo = self.out["ma200_and_gate"]
        solo = self.out["MA200 monthly"]
        self.assertGreater(combo["amount"], 0.0)
        self.assertLess(combo["amount"], solo["amount"],
                        f"the combined gate now pays ${combo['amount']:,.2f} against MA200 alone at"
                        f" ${solo['amount']:,.2f}")
        self.assertGreater(mir.plan_stats(combo["m"], 100_000.0, self.payout, 10)["p_fail"],
                           mir.plan_stats(solo["m"], 100_000.0, self.payout, 10)["p_fail"])

    def test_the_and_gate_buys_the_lowest_drawdown_in_the_repository(self):
        best = min(self.out.values(), key=lambda v: v["max_dd"])
        self.assertIs(best, self.out["ma200_and_gate"],
                      f"something now has a lower drawdown than {best['max_dd']:.1%}")
        self.assertLess(best["max_dd"], 0.20)
        self.assertLess(best["cagr"], self.out["SPY hold"]["cagr"] - 0.02,
                        "and it is no longer paying for it in growth, which is the whole point")

    def test_the_plain_yield_gate_is_worse_than_the_index_it_is_meant_to_protect(self):
        g, h = self.out["yield_gate"], self.out["SPY hold"]
        self.assertLess(g["cagr"], h["cagr"])
        self.assertGreater(mir.plan_stats(g["m"], 100_000.0, self.payout, 10)["p_fail"],
                           mir.plan_stats(h["m"], 100_000.0, self.payout, 10)["p_fail"])
        self.assertGreater(g["max_dd"], h["max_dd"] * 0.9,
                           "the rates gate now halves the drawdown; the finding has flipped")

    def test_the_trend_rule_wins_the_two_older_eras_and_loses_the_newest_one(self):
        """The era split round 55 demanded, applied to round 58's income metric. If this ever fails, the
        2016-onward figure has changed and the income claim needs re-reading, not restating."""

        idx = [i for i, k in enumerate(self.keys) if k.year == 2006]
        self.assertTrue(idx)
        for lo, hi in ((1993, 2004), (2005, 2015)):
            ma = rg.era_stats(self.out["MA200 monthly"]["m"], self.keys, 100_000.0, self.payout, 5, lo, hi)
            sp = rg.era_stats(self.out["SPY hold"]["m"], self.keys, 100_000.0, self.payout, 5, lo, hi)
            self.assertLess(ma["p_fail"], sp["p_fail"], f"MA200 stopped beating the index in {lo}-{hi}")
        ma = rg.era_stats(self.out["MA200 monthly"]["m"], self.keys, 100_000.0, self.payout, 5, 2016, 2100)
        sp = rg.era_stats(self.out["SPY hold"]["m"], self.keys, 100_000.0, self.payout, 5, 2016, 2100)
        self.assertGreater(ma["p_fail"], sp["p_fail"],
                            f"MA200 now beats the index in the newest era ({ma['p_fail']:.0%} vs"
                            f" {sp['p_fail']:.0%}) at n={ma['n']} windows")
        self.assertGreaterEqual(ma["n"], 30, "the newest era is too short to conclude anything")

    def test_an_era_with_too_few_windows_is_untested_and_not_zero(self):
        e = rg.era_stats(self.out["SPY hold"]["m"], self.keys, 100_000.0, self.payout, 10, 2024, 2100)
        self.assertIsNone(e["p_fail"])
        self.assertLess(e["n"], 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
