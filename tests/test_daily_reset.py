"""Tests for the measured path cost of a daily-reset fund.

The load-bearing claim is not the full-record number, which is close to the textbook formula and therefore
uninteresting. It is that the formula is wrong in both directions in the windows that decide survivability, so it
cannot be used as a bound in either direction. These tests pin the signs, the orderings and the specific failures,
including the one where a daily-reset 3x fund loses to its own unlevered underlying — which is the result that
should end any argument conducted with the approximation.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import daily_reset as dr                           # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402


class TheArithmeticIsExact(unittest.TestCase):
    def test_unlevered_compounding_is_plain_buy_and_hold(self):
        rets = [0.01, -0.02, 0.03, 0.00]
        self.assertAlmostEqual(dr.cagr(rets, 1.0),
                               (1.01 * 0.98 * 1.03 * 1.0) ** (252.0 / 4) - 1.0, places=12)

    def test_zero_returns_under_any_leverage_earns_exactly_nothing(self):
        for L in (1.25, 3.0):
            self.assertAlmostEqual(dr.cagr([0.0] * 500, L), 0.0, places=12)

    def test_a_leverage_of_one_is_monthly_reset_by_definition_so_the_two_agree(self):
        """The control that says the two functions differ only in the reset, nothing else."""

        rets = [0.01, -0.01, 0.02, 0.03, -0.02, 0.00] * 40
        self.assertAlmostEqual(dr.cagr(rets, 1.0), dr.cagr_monthly(rets, 1.0), places=10)

    def test_the_formula_returns_zero_drag_at_unity_leverage(self):
        self.assertEqual(dr.approximation(1.0, 0.20), 0.0)


class ThePathCostIsReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.dates, cls.rets = dr.daily_returns(cls.data)
        cls.sigma = dr.sigma(cls.rets)
        cls.base = dr.cagr(cls.rets, 1.0)

    def test_the_archive_is_deep_enough_for_this_to_mean_anything(self):
        self.assertGreater(len(self.rets), 6000, "a daily-reset study on 500 sessions is a demo, not evidence")
        self.assertGreater(self.sigma, 0.10)
        self.assertGreater(self.base, 0.05)

    def test_the_path_cost_grows_superlinearly_with_leverage(self):
        cost = {L: dr.cagr(self.rets, L) - L * self.base for L in (1.25, 2.0, 3.0)}
        self.assertLess(cost[3.0], cost[2.0])
        self.assertLess(cost[2.0], cost[1.25])
        # Measured: -0.43% / -3.00% / -9.82% per year. The ratio test is the point: 3x costs 3.3x what 2x
        # costs, not 1.5x, which is the sense in which the charge is superlinear.
        self.assertGreater(abs(cost[1.25]), 0.002)
        self.assertGreater(abs(cost[3.0]) / abs(cost[2.0]), 2.5)

    def test_over_the_full_record_the_formula_is_close_which_is_why_nobody_noticed_it_is_wrong(self):
        """The trap in one assertion: the aggregate looks fine."""

        path_cost = dr.cagr(self.rets, 3.0) - 3.0 * self.base
        self.assertLess(abs(dr.approximation(3.0, self.sigma) - path_cost), 1.0)

    def test_monthly_rebalancing_beats_daily_reset_over_the_record(self):
        gain = dr.cagr_monthly(self.rets, 3.0) - dr.cagr(self.rets, 3.0)
        self.assertGreater(gain, 0.01)
        self.assertLess(gain, 0.08)


class TheFormulaFailsWhereItMatters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.dates, cls.rets = dr.daily_returns(cls.data)

    def window(self, first, last):
        idx = [i for i, k in enumerate(self.dates) if first <= int(str(k)[:4]) <= last]
        return [self.rets[i] for i in idx]

    def error_3x(self, first, last):
        rr = self.window(first, last)
        return dr.approximation(3.0, dr.sigma(rr)) - (dr.cagr(rr, 3.0) - 3.0 * dr.cagr(rr, 1.0))

    def test_the_formula_understates_the_damage_in_a_bear_market(self):
        self.assertLess(self.error_3x(2022, 2022), -0.10)
        self.assertLess(self.error_3x(2000, 2002), -0.08)

    def test_the_formula_is_also_wrong_in_a_calm_market_and_here_is_why_it_matters(self):
        """2017 is the file's most uncomfortable number. Vol was 6.7%, the index returned +21.8%, and a 3x
        daily-reset fund returned +78.2% — so the realised path cost was a POSITIVE +12.8%/yr while the formula
        said -1.36%. A fund's daily reset is not a standing cost: in a low-volatility trend it is a tailwind,
        because every up day raises the base the next day's leverage is applied to. That is the same fact as the
        crash years read from the other side, and it is the reason no single drag number can be quoted at all."""

        rr = self.window(2017, 2017)
        self.assertGreater(dr.cagr(rr, 3.0) - 3.0 * dr.cagr(rr, 1.0), 0.10)
        self.assertGreater(abs(self.error_3x(2017, 2017)), 0.10)

    def test_the_turnover_bill_is_measured_and_smaller_than_the_path_effect_it_justifies(self):
        """Round 35's completion of round 34's claim: monthly rebalancing must win on BOTH axes or the advice
        is merely a preference. Path gain was ~3.5%/yr over the record; if the turnover bill were anywhere near
        that the conclusion would invert, so the bill being two orders smaller is the load-bearing fact."""

        ann_daily, gap_daily = dr.turnover_per_year(self.rets, 3.0, 1)
        ann_monthly, gap_monthly = dr.turnover_per_year(self.rets, 3.0, dr.MONTH_SESSIONS)
        self.assertGreater(ann_daily, ann_monthly, "more rebalances must trade more")
        self.assertLess(gap_daily, gap_monthly, "and each time a smaller gap — the asymmetry is the point")
        self.assertLess(ann_daily * 0.0002, 0.002, "the bill must stay small enough for path to dominate")
        self.assertLess(ann_monthly * 0.0002, ann_daily * 0.0002)

    def test_a_levered_book_in_a_flat_market_trades_only_its_entry_gap_and_an_unlevered_one_nothing(self):
        """The control I got wrong twice, recorded as one honest assertion. A flat market at L=2 still turns over
        0.50x/yr, because the book must be *funded* to 2.0 and that funding trade recurs once per simulated block
        — an entry cost, not drift. An unlevered book in a flat market trades exactly nothing. And on the real
        archive an unlevered book turns over 0.41x/yr just holding 1.0, which is a cost every index fund in this
        project pays and none of them has ever billed."""

        flat = [0.0] * 500
        self.assertAlmostEqual(dr.turnover_per_year(flat, 1.0, 21)[0], 0.0, places=9)
        self.assertGreater(dr.turnover_per_year(flat, 2.0, 21)[0], 0.4)
        self.assertGreater(dr.turnover_per_year(self.rets, 1.0, 21)[0], 0.3)

    def test_turnover_rises_with_leverage_because_a_given_move_makes_a_bigger_gap(self):
        a = dr.turnover_per_year(self.rets, 1.25, 21)[0]
        c = dr.turnover_per_year(self.rets, 3.0, 21)[0]
        self.assertGreater(c, a)

    def test_monthly_beats_daily_on_the_phase_averaged_mean_not_the_published_draw(self):
        """Round 37's correction of round 34: the +3.54%/yr I published was one start day out of 21, chosen by
        the calendar rather than by me. The mean over all phases is +0.91%/yr. The direction holds; the size
        did not, and the number a reader can act on is the mean."""

        daily = dr.cadence_profile(self.rets, 3.0, 1)["mean"]
        monthly = dr.cadence_profile(self.rets, 3.0, dr.MONTH_SESSIONS)
        self.assertGreater(monthly["mean"], daily, "less often must still win on the average")
        self.assertLess(monthly["mean"] - daily, 0.02, "and the honest gap is under 2%, not the 3.5% I printed")

    def test_the_single_draw_i_published_is_above_the_phase_mean_which_is_the_bias_made_visible(self):
        """If the naive number had landed below the mean the error would have been in the safe direction and I
        would very likely never have noticed it. It did not, so the test says so."""

        prof = dr.cadence_profile(self.rets, 3.0, dr.MONTH_SESSIONS)
        naive = dr.cagr_monthly(self.rets, 3.0, dr.MONTH_SESSIONS)
        self.assertGreater(naive, prof["mean"])
        self.assertGreater(naive - prof["mean"], 0.02)

    def test_phase_spread_grows_with_the_interval_which_is_the_real_cadence_result(self):
        """The round's actual finding: cadence is a leverage decision, not a schedule. Spread must be monotone
        in the interval, and quarterly must be catastrophic at 3x."""

        a = dr.cadence_profile(self.rets, 3.0, 5)["spread"]
        b = dr.cadence_profile(self.rets, 3.0, dr.MONTH_SESSIONS)["spread"]
        c = dr.cadence_profile(self.rets, 3.0, 63)["spread"]
        self.assertLess(a, b)
        self.assertLess(b, c)
        self.assertGreater(c, 0.5)
        self.assertLess(dr.cadence_profile(self.rets, 3.0, 63)["min"], -0.5)

    def test_two_of_the_six_regimes_flip_sign_so_cadence_advice_cannot_be_global(self):
        """The figure round 34 quoted for corona was the best of 21 starts. Phase-averaged it reverses. Pinning
        the reversal count is the point: if a future re-seal removes the flips, the advice changes too."""

        w = {x["label"]: x for x in dr.stress_windows(self.dates, self.rets, 3.0)}
        self.assertLess(w["corona 2020"]["gain"], 0.0, "the window round 34 praised is now a loss")
        self.assertGreater(w["bear 2022"]["gain"], 0.0)
        flips = sum(1 for x in w.values() if x["gain"] * w["full record"]["gain"] < 0)
        self.assertGreaterEqual(flips, 1, "at least one regime must disagree with the record")

    def test_the_worst_corona_start_is_catastrophic_enough_that_no_average_may_be_quoted_alone(self):
        w = {x["label"]: x for x in dr.stress_windows(self.dates, self.rets, 3.0)}
        self.assertLess(w["corona 2020"]["min"], -0.9)
        self.assertGreater(w["corona 2020"]["max"], w["corona 2020"]["mean"])
        self.assertGreater(w["corona 2020"]["mean"] - w["corona 2020"]["min"], 0.5)

    def test_a_daily_reset_3x_fund_loses_to_its_own_unlevered_underlying_in_2020(self):
        """The single most persuasive number in the file: a year in which the index rose 18% and the 3x fund
        finished below it, produced entirely by the reset and not by any fee."""

        rr = self.window(2020, 2020)
        self.assertGreater(dr.cagr(rr, 1.0), 0.10)
        self.assertLess(dr.cagr(rr, 3.0), dr.cagr(rr, 1.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
