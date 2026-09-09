"""Tests for `tools/partial_tilt.py`.

A tool whose whole output is a straight line through the origin needs a different kind of test than a
simulation does: the checks here are mostly *shapes* — proportionality in the tilt size, scale-freedom in
the Sharpe, monotonicity in the cost — because those are the properties that would break first if the
tilt leg were being double-counted, mis-signed, or charged to the wrong book.
"""

from __future__ import annotations

from datetime import date
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import cross_section as xs        # noqa: E402
import partial_tilt as pt         # noqa: E402


class TheTiltIsAWeightNotAnAlchemy(unittest.TestCase):
    """Sizing a tilt must move the money and nothing else."""

    @classmethod
    def setUpClass(cls):
        cls.panel = xs.build_panel(start=date(2007, 3, 1), end=date(2026, 9, 4), warmup=15)
        cls.rows = {r["tilt"]: r for r in pt.scan_window(cls.panel, 2.0)
                    if r["k"] == 1 and not r["reverse"]}
        cls.base = [xs.bench_weights(cls.panel, i) for i in range(len(cls.panel.months))]
        cls.plain = xs.run_book(cls.panel, cls.base, 2.0)

    def test_a_zero_tilt_is_the_index_book_to_the_cent(self):
        w = [pt.tilt_weights(self.panel, i, 1, 0.0) for i in range(len(self.panel.months))]
        self.assertEqual(w, self.base)
        book = xs.run_book(self.panel, w, 2.0)
        self.assertAlmostEqual(book["ending"], self.plain["ending"], places=9)

    def test_the_spread_series_is_exactly_proportional_to_the_tilt(self):
        """The tilt moves money it does not create, so double the size is double the monthly P&L.

        This is the invariant the whole table rests on. It was false in one month out of 235 while the
        cost term was an absolute instead of an increment, because the benchmark's own fund splice in
        September 2010 billed the tilt for a trade the comparator was making anyway.
        """

        small = pt.spread(self.panel, [pt.tilt_weights(self.panel, i, 1, 0.05)
                                       for i in range(len(self.panel.months))], self.base, 2.0,
                          self.panel.first)
        big = pt.spread(self.panel, [pt.tilt_weights(self.panel, i, 1, 0.50)
                                     for i in range(len(self.panel.months))], self.base, 2.0,
                        self.panel.first)
        self.assertEqual(len(small), len(big))
        for i, (x, y) in enumerate(zip(small, big)):
            self.assertAlmostEqual(y, 10.0 * x, places=9, msg=f"month {i} is not proportional")

    def test_the_ending_gap_grows_faster_than_the_tilt(self):
        """Super-linear at 50%, and the reason is a cost that scales with nothing on this table.

        A tilt that loses linearly in arithmetic terms still loses the geometric race: the extra variance
        drags the compounded balance below the sum of its parts, so halving the tilt does not halve the
        damage. The direction is pinned because "size it down and it is fine" is the wrong inference.
        """

        small, mid, big = self.rows[0.05], self.rows[0.20], self.rows[0.50]
        self.assertLess(abs(mid["gap"] / small["gap"] - 4.0), 0.35)
        self.assertGreater(big["gap"] / small["gap"], 10.4,
                           "no variance drag at 50% of the account; check the spread attribution")

    def test_the_sharpe_does_not_move_with_the_size_of_the_bet(self):
        """Scale-free by construction, and any deviation means the spread series is mis-scaled."""

        rates = [self.rows[t]["sharpe"] for t in pt.TILTS]
        self.assertTrue(all(r is not None for r in rates))
        self.assertAlmostEqual(max(rates) - min(rates), 0.0, places=9)

    def test_a_dearer_toll_never_helps_a_forward_tilt(self):
        for tilt in pt.TILTS:
            w = [pt.tilt_weights(self.panel, i, 1, tilt) for i in range(len(self.panel.months))]
            ends = [xs.run_book(self.panel, w, c)["ending"] for c in (0.3, 2.0, 5.0, 20.0)]
            self.assertEqual(ends, sorted(ends, reverse=True), f"tilt {tilt} gained from a higher fee")

    def test_the_ranking_helps_even_where_the_tilt_loses(self):
        """Not a claim that momentum pays — a claim that the sign of the ranking is doing work."""

        rev = {r["tilt"]: r for r in pt.scan_window(self.panel, 2.0)
               if r["k"] == 1 and r["reverse"]}
        for tilt in pt.TILTS:
            self.assertGreater(self.rows[tilt]["gap"], rev[tilt]["gap"])
        self.assertLess(self.rows[0.20]["gap"], 0, "the full-record loss is the published result")


class TheHonestyMetricsAreHonest(unittest.TestCase):
    """`n_eff`, `deploy` and the pass rule all exist to make the table read worse. Check that they do."""

    def test_autocorrelation_may_discount_the_count_and_never_inflate_it(self):
        up = [0.01 if i % 2 == 0 else 0.011 for i in range(60)]           # strong positive persistence
        down = [0.01 * (1 if i % 2 else -1) for i in range(60)]           # alternating, ac1 near -1
        for series in (up, down, [0.001] * 40, [(-1) ** i * 0.02 for i in range(40)]):
            _sr, _ac, eff = pt.sharpe(series)
            if eff is not None:
                self.assertLessEqual(eff, len(series) + 1e-9)

    def test_a_short_series_refuses_a_sharpe_instead_of_inventing_one(self):
        self.assertEqual(pt.sharpe([0.01] * 12), (None, None, 12))

    def test_deploy_is_zero_when_the_rule_picks_the_fund_the_account_already_holds(self):
        """A tilt that keeps landing back on the index fund is not a 20% tilt, and must not read as one."""

        panel = xs.build_panel(start=date(2012, 1, 1), end=date(2013, 12, 31), warmup=15)
        base = [xs.bench_weights(panel, i) for i in range(len(panel.months))]
        same = [dict(b) for b in base]
        self.assertAlmostEqual(pt.deployed(panel, same, base, panel.first), 0.0, places=12)
        moved = [{**b, "GLD": 0.2} for b in base]
        self.assertAlmostEqual(pt.deployed(panel, moved, base, panel.first), 0.2, places=12)

    def test_deploy_matches_the_label_only_because_the_rule_never_picks_the_benchmark(self):
        """The one assumption behind the `deploy` column, pinned where it can be falsified."""

        panel = xs.build_panel(start=date(2007, 3, 1), end=date(2026, 9, 4), warmup=15)
        base = [xs.bench_weights(panel, i) for i in range(len(panel.months))]
        rows = [r for r in pt.scan_window(panel, 2.0) if r["k"] == 1 and not r["reverse"]]
        for r in rows:
            self.assertAlmostEqual(r["deployed"], r["tilt"], places=2,
                                   msg="top-1 landed on the index fund; deploy is no longer the label")

    def test_the_pass_rule_can_pass(self):
        """A verdict that always prints NO is decoration. Feed it a winner and it must say so."""

        def grid(fwd_gap, fwd_sharpe, rev_gap):
            return {w: [{"k": k, "tilt": t, "reverse": rev, "gap": fwd_gap if not rev else rev_gap,
                         "sharpe": fwd_sharpe if not rev else -0.4,
                         "$/mo": fwd_gap / 40.0 if not rev else rev_gap / 40.0}
                        for k in pt.TOP_K for t in pt.TILTS for rev in (False, True)]
                    for w in pt.WINDOWS_KEYS}

        text = pt.verdict(grid(5_000.0, 0.9, -3_000.0))
        self.assertNotIn("NO", text, f"a clean sweep still failed the rule:\n{text}")
        self.assertIn("pass", text)

        one_bad = grid(5_000.0, 0.9, -3_000.0)
        second = list(one_bad)[1]
        one_bad[second] = [{**r, "gap": -500.0, "$/mo": -12.5} for r in one_bad[second]
                           if not r["reverse"]] + [r for r in one_bad[second] if r["reverse"]]
        self.assertIn("NO", pt.verdict(one_bad), "a losing window did not fail the rule")
        self.assertRaises(ValueError, pt.verdict, {"shared 2007-03..2026-08": []})


class ThePredictionInTheDocstringIsCheckable(unittest.TestCase):
    """Round 16 promised, before running, that the tilt would land near zero and positive recently."""

    def test_the_full_record_is_negative_and_the_recent_window_positive(self):
        full = xs.build_panel(start=date(2007, 3, 1), end=date(2026, 9, 4), warmup=15)
        recent = xs.build_panel(start=date(2022, 1, 1), end=date(2026, 9, 4), warmup=15)
        for panel, sign in ((full, -1), (recent, +1)):
            for r in pt.scan_window(panel, 2.0):
                if r["k"] == 1 and not r["reverse"]:
                    self.assertEqual(math.copysign(1, r["gap"]), sign,
                                     f"{r['tilt']:.0%} tilt broke the predicted sign")

    def test_the_spread_is_discounted_to_the_months_that_independent_evidence_exists_for(self):
        """The recent window is 57 months of +0.46 persistence, and the table has to say ~21."""

        recent = xs.build_panel(start=date(2022, 1, 1), end=date(2026, 9, 4), warmup=15)
        rows = [r for r in pt.scan_window(recent, 2.0) if r["k"] == 1 and not r["reverse"]]
        self.assertTrue(all(r["n_eff"] is not None and r["n_eff"] < 40 for r in rows),
                        "n_eff should be far below the 57 months on the calendar")
        self.assertTrue(all(r["sharpe"] is not None and r["sharpe"] < pt.SHARPE_BAR for r in rows),
                        "some cell cleared the pre-registered Sharpe bar")


if __name__ == "__main__":
    unittest.main()
