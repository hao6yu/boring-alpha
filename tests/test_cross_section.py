"""Tests for `tools/cross_section.py` — the rotation bar, and the four ways it could lie.

Two of these files' failure modes are visible only as a *number that reads fine*, which is the class of
bug this repository has been burned by four times. So the tests aim at the arithmetic's shape rather
than its output: the engine must reproduce a hand-computed account, the ranking must be unable to see
the month it trades on, the bar must be able to refuse, and a sleeve that does not exist yet must be
impossible to hold.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import cross_section as xs  # noqa: E402

COST = 2.0


def month_ends(n, year=2015):
    """`n` month-end dates walking forward a calendar month at a time, wrapping the year for real."""

    out, y, m = [], year, 1
    for _ in range(n):
        out.append(date(y, m, 1))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def synthetic(months, series, first=1):
    """A hand-built panel. Returns are supplied as exact numbers so the arithmetic can be checked."""

    panel = xs.Panel(months=months, first=first, cash=[0.0] * len(months),
                     expense={s: 0.0 for s in series})
    panel.ret = {s: list(v) for s, v in series.items()}
    panel.avail = {s: [True] * len(months) for s in series}
    panel.age = {s: [i + 1 for i in range(len(months))] for s in series}
    for missing in set(xs.UNIVERSE) - set(series):
        panel.ret[missing] = [0.0] * len(months)
        panel.avail[missing] = [False] * len(months)
        panel.age[missing] = [0] * len(months)
    return panel


class TheEngineIsAnAccount(unittest.TestCase):
    """The simulator has to be an account before anything it prints means anything."""

    def test_a_flat_market_returns_the_deposits_exactly(self):
        """Zero returns, zero costs: the ending is the money paid in, to the cent, not a hair off."""

        months = [date(2020, m, 1) for m in range(1, 13)]
        panel = synthetic(months, {s: [0.0] * 12 for s in xs.UNIVERSE})
        book = xs.run_book(panel, [{s: 1.0 / 9 for s in xs.UNIVERSE} for _ in months], 0.0)
        self.assertAlmostEqual(book["ending"], xs.OPENING + xs.MONTHLY * (len(months) - 1), places=6)
        self.assertAlmostEqual(book["fees"], 0.0, places=9)
        self.assertEqual(book["paid"], xs.OPENING + xs.MONTHLY * (len(months) - 1))

    def test_a_single_sleeve_book_is_a_hand_computed_account(self):
        """One sleeve, one expense ratio, one cost: the arithmetic is checked against arithmetic."""

        months = month_ends(5, 2021)
        panel = synthetic(months, {s: [0.0] * 5 for s in xs.UNIVERSE})
        panel.ret["SPY"] = [0.0, 0.01, 0.01, 0.01, 0.01]
        panel.expense["SPY"] = 0.012           # 1% a year, charged on the fund leg monthly
        book = xs.run_book(panel, [{"SPY": 1.0} for _ in months], 0.0, first=1)
        value = xs.OPENING
        for i in range(1, 5):
            r = panel.ret["SPY"][i]
            value *= 1.0 + (r - (1.0 + r) * 0.012 / 12.0)
            value += xs.MONTHLY
        self.assertAlmostEqual(book["ending"], value, places=6)
        panel.expense["SPY"] = 0.0
        free = xs.run_book(panel, [{"SPY": 1.0} for _ in months], 0.0, first=1)
        self.assertGreater(free["ending"], book["ending"], "the expense ratio charged nothing")
        self.assertLess(free["ending"] - book["ending"], free["ending"] * 0.02,
                        "a 1.2% fee cannot plausibly cost a sixth of the account")

    def test_turnover_is_charged_to_the_book_that_switches(self):
        """An unchanged schedule pays nothing; a switching one pays, and the difference is the toll."""

        months = [date(2022, m + 1, 1) for m in range(6)]
        flat = synthetic(months, {s: [0.0] * 6 for s in xs.UNIVERSE})
        a = xs.run_book(flat, [{"SPY": 1.0} for _ in months], COST)
        b = xs.run_book(flat, [{"SPY" if i % 2 else "GLD": 1.0} for i, _ in enumerate(months)], COST)
        self.assertGreater(a["ending"], b["ending"])
        # A book that never switches still buys what it holds once: exactly one leg, at the opening size.
        self.assertAlmostEqual(a["fees"], COST / 1e4 * xs.OPENING, places=6)
        self.assertGreater(b["fees"], 8 * a["fees"], "switching every month must cost many times a buy")


class TheRankingCannotSeeTomorrow(unittest.TestCase):
    """The weights that trade in month m must be a function of months strictly before m."""

    @classmethod
    def setUpClass(cls):
        cls.panel = xs.build_panel(start=date(2015, 1, 1), end=date(2024, 12, 31), warmup=15)

    def test_truncating_the_archive_leaves_earlier_weights_untouched(self):
        full = [xs.weights_for(self.panel, i, 2, 12, 1)
                for i in range(self.panel.first, len(self.panel.months))]
        cut = self.panel.first + 40
        short = xs.build_panel(start=self.panel.months[self.panel.first],
                               end=self.panel.months[cut - 1], warmup=15)
        again = [xs.weights_for(short, i, 2, 12, 1) for i in range(short.first, len(short.months))]
        self.assertGreater(len(again), 24, f"only {len(again)} scored months to compare")
        self.assertEqual(short.months, self.panel.months[:len(short.months)],
                         "the truncated panel must share the full panel's calendar, index for index")
        for offset in range(len(again) - 1):
            self.assertEqual(full[offset], again[offset],
                             f"the ranking changed at month {offset} when only later months moved")

    def test_a_ranking_never_holds_a_sleeve_that_has_not_listed(self):
        """Availability is enforced by a refusal, not by a convention someone can forget."""

        months = [date(2005, m, 1) for m in range(1, 13)]
        panel = synthetic(months, {s: [0.005] * 12 for s in xs.UNIVERSE}, first=1)
        panel.avail["GLD"] = [False] * 12                       # not listed until the following year
        with self.assertRaises(ValueError) as ctx:
            xs.run_book(panel, [{"GLD": 1.0} for _ in months], COST, first=1)
        self.assertIn("before it listed", str(ctx.exception))

    def test_the_guard_refuses_a_window_with_no_history_behind_it(self):
        """A rotation solved on a warm-up it does not have must fail loudly, not print a number."""

        with self.assertRaises(ValueError):
            xs.build_panel(start=date(2006, 3, 1), end=date(2026, 9, 4), warmup=1)


class TheBarCanRefuse(unittest.TestCase):
    """r10: a guard that cannot say no is decoration. The same applies to a bar."""

    def setUp(self):
        self.months = month_ends(30, 2015)
        series = {s: [0.0] * 30 for s in xs.UNIVERSE}
        for i in range(1, 30):
            series["SPY"][i] = 0.02                              # the benchmark only goes up
            series["GLD"][i] = -0.01                             # everything else only goes down
        self.panel = synthetic(self.months, series, first=13)
        self.fallback = [{s: 1.0 / 9 for s in xs.UNIVERSE} for _ in self.months]

    def test_no_accuracy_reaches_a_target_the_pick_cannot_reach(self):
        """`None` rather than a clamped 0.0%: the clamped reading is what a cleared bar looks like."""

        pick = [{"GLD": 1.0} for _ in self.months]
        target = xs.run_book(self.panel, [{"SPY": 1.0} for _ in self.months], COST)["ending"]
        self.assertIsNone(xs.solve_blend(self.panel, pick, self.fallback, target, COST))

    def test_a_pick_better_than_its_fallback_is_not_reported_as_a_cleared_bar(self):
        """A blend fraction below zero means more ranking moves you away. Printing 0.0% would be a win."""

        worse = [{"GLD": 1.0} for _ in self.months]
        better_fallback = [{"SPY": 1.0} for _ in self.months]
        target = 1e9
        self.assertIsNone(xs.solve_blend(self.panel, worse, better_fallback, target, COST))

    def test_the_blend_is_linear_in_p_because_the_months_are_independent(self):
        """The solve is exact, not simulated, and this is the property that makes it exact."""

        pick = [{"TLT": 1.0} for _ in self.months]
        lo = xs.blend_ending(self.panel, pick, self.fallback, 0.0, COST)
        mid = xs.blend_ending(self.panel, pick, self.fallback, 0.5, COST)
        hi = xs.blend_ending(self.panel, pick, self.fallback, 1.0, COST)
        self.assertAlmostEqual(mid, (lo + hi) / 2.0, places=4)

    def test_the_warm_up_is_not_invested_and_the_cash_leg_eargs_its_own_rate(self):
        """Round 15's own bug: a short window parked in the benchmark before the rules could run.

        The account with no weights is all T-bill, so its ending must be reproducible from the panel's
        cash factor alone — which checks the money-market leg against arithmetic at the same time as it
        checks that nothing is invested during warm-up.
        """

        panel = xs.build_panel(start=date(2012, 1, 1), end=date(2013, 12, 31), warmup=15)
        self.assertGreaterEqual(panel.first, 13)
        book = xs.run_book(panel, [{} for _ in panel.months], COST)
        self.assertEqual(book["months"], len(panel.months) - panel.first)
        value = xs.OPENING
        for i in range(panel.first, len(panel.months)):
            value *= 1.0 + panel.cash[i]
            value += xs.MONTHLY
        self.assertAlmostEqual(book["ending"], value, places=6)
        self.assertGreater(book["ending"], xs.OPENING + xs.MONTHLY * book["months"],
                           "idle cash earning nothing is a bug, not a conservative default")


class TheControlsBehaveAsWritten(unittest.TestCase):
    """Reversal must reverse, equal weight must be equal, and correlation must count the truth."""

    def test_reversing_changes_which_sleeves_are_held_and_what_they_earn(self):
        """A run-index style off-by-one would leave this pair identical (r5: negative-control everything)."""

        panel = xs.build_panel(start=date(2007, 3, 1), end=date(2026, 9, 4), warmup=15)
        blank = [{} for _ in range(panel.first)]
        forward = blank + [xs.weights_for(panel, i, 2, 12, 1)
                           for i in range(panel.first, len(panel.months))]
        back = blank + [xs.weights_for(panel, i, 2, 12, 1, True)
                        for i in range(panel.first, len(panel.months))]
        differ = sum(1 for a, b in zip(forward, back) if a != b and a and b)
        self.assertGreater(differ, panel.first + 6, "a reversed ranking that matches the forward one")
        fa = xs.run_book(panel, forward, COST)["ending"]
        ba = xs.run_book(panel, back, COST)["ending"]
        self.assertNotAlmostEqual(fa, ba, places=0)

    def test_a_schedule_the_wrong_length_is_refused_not_truncated(self):
        """An IndexError from inside the simulator would be a wrong answer shaped like a crash."""

        months = month_ends(8, 2018)
        panel = synthetic(months, {s: [0.0] * 8 for s in xs.UNIVERSE}, first=1)
        with self.assertRaises(ValueError):
            xs.run_book(panel, [{"SPY": 1.0}] * 4, COST)

    def test_equal_weight_holds_every_eligible_sleeve_and_nothing_else(self):
        panel = xs.build_panel(start=date(2015, 1, 1), end=date(2016, 12, 31), warmup=15)
        w = xs.equal_weights(panel, panel.first + 12)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=12)
        self.assertTrue(all(abs(v - 1.0 / len(w)) < 1e-12 for v in w.values()))
        self.assertTrue(set(w) <= set(xs.UNIVERSE))
        self.assertTrue(all(panel.avail[s][panel.first + 12] for s in w), "an unlisted sleeve in EW")

    def test_the_correlation_table_is_not_empty_and_points_the_right_way(self):
        """A helper that returns a safe default when it finds nothing would make this file's honesty moot."""

        panel = xs.build_panel(start=date(2007, 3, 1), end=date(2026, 9, 4), warmup=15)
        rho, n_eff, hi, lo = xs.effective_n(panel, panel.first)
        self.assertEqual(len(hi) + len(lo), 5, "the helper returned fewer pairs than it was given")
        self.assertGreater(rho, 0.15, f"average pairwise correlation {rho} is implausibly low for nine ETFs")
        self.assertGreater(hi[0][0], 0.85, "TLT and IEF are the same bet at two durations; rho must see it")

    def test_the_archive_counts_as_few_independent_sleeves_as_it_really_has(self):
        """Ten names across four asset classes is not ten bets, and the report has to say so."""

        panel = xs.build_panel(start=date(2007, 3, 1), end=date(2026, 9, 4), warmup=15)
        rho, n_eff, hi, lo = xs.effective_n(panel, panel.first)
        self.assertLess(n_eff, len(xs.UNIVERSE) * 0.6,
                        f"n_eff {n_eff:.1f} of 9 is too close to 9 to be an honest independence count")
        self.assertLess(hi[0][0], 0.99, "SPY and VOO were the same fund; the ranked set must not contain both")


if __name__ == "__main__":
    unittest.main()


class TheResultIsPinned(unittest.TestCase):
    """The finding itself, pinned, so a later edit that quietly improves it has to argue.

    Recorded 2026-09-06 at 2 bps one-way, twelve months' lookback skipping one month, nine ranked
    sleeves. Four claims, each of which is contradicted by a change someone will be tempted to make.
    """

    @classmethod
    def setUpClass(cls):
        cls.panel = xs.build_panel(start=date(2007, 3, 1), end=date(2026, 9, 4), warmup=15)
        cls.rows = {r["rule"]: r for r in xs.scan(cls.panel, 2.0, 12, 1)}

    def rotation(self):
        return [r for r in self.rows.values() if "momentum" in r["rule"]]

    def test_no_rotation_beats_just_buying_the_fund_on_the_full_record(self):
        """The P0 verdict: everything here loses to DCA into the same sleeve, net, over nineteen years."""

        for r in self.rotation():
            self.assertLess(r["vs_bench"], 0,
                            f"{r['rule']} beat the index DCA, which contradicts the published verdict")

    def test_every_rotation_beats_the_naive_version_of_itself(self):
        """The signal is real in the only sense that survives a dominance test: it beats equal weight."""

        for r in self.rotation():
            self.assertGreater(r["vs_ew"], 0, f"{r['rule']} could not beat buying all nine sleeves")

    def test_the_forward_ranking_out_earns_the_reversed_one(self):
        """Not an assertion that momentum works — an assertion that the ranking carries the money."""

        back = self.rows["top-2 reversed"]
        fwd = self.rows["top-2 momentum"]
        self.assertGreater(fwd["vs_ew"], back["vs_ew"], "the reversal out-earned the rule; see r13")
        self.assertGreater(fwd["ending"] - back["ending"], 100_000.0,
                           "forward minus reversed is the whole measurable signal; it must be large")

    def test_the_short_window_clearance_does_not_survive_its_own_neighbourhood(self):
        """The one cell that clears both comparators is a 12-month lookback, not a momentum effect.

        At three months the same rule loses to the reversal, which is what pinning this against a
        parameter sweep looks like: the win sits at the a-priori window and vanishes one notch away.
        """

        panel = xs.build_panel(start=date(2022, 1, 1), end=date(2026, 9, 4), warmup=15)
        rows = {r["rule"]: r for r in xs.scan(panel, 2.0, 3, 1)}
        for r in (rows["top-1 momentum"], rows["top-2 momentum"], rows["top-3 momentum"]):
            self.assertLess(r["vs_bench"], 0, f"{r['rule']} cleared the bar at a 3-month lookback")
        self.assertGreater(rows["top-2 reversed"]["vs_bench"], 0,
                           "at a 3-month lookback the reversal should win; the sign must flip, not fade")
