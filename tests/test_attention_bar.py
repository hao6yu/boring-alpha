"""Tests for the attention feed and its bar.

Two files are under test. `attention_feed.py` captures a non-price series in a form this repository is
willing to believe, and `attention_bar.py` prices it. The tests are offline: they read the sealed panel and
construct their own series, so a network outage cannot turn a green suite red, and nothing here can be
influenced by what Wikipedia is serving today.

What is pinned, in order of how much it matters:

  * point-in-time   truncating the history cannot change a past z-score; the schedule for a month cannot
                    depend on a signal that month or any month after it.
  * the cash leg    sitting out is cash, not "keep holding", which is what an empty weight row means.
  * the guard       a series that begins after the sample begins is rejected, whatever its name claims.
  * the integrity   a tampered blob refuses to build a panel, rather than building a quiet one.
  * the grader      it can pass, it can refuse, and its control clause runs first.
  * the result      on the sealed record, no direction of this feed clears its pre-registered bar, and the
                    control basket is why.
"""

from __future__ import annotations

import copy
import importlib
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import attention_bar as ab                       # noqa: E402
import attention_feed as af                      # noqa: E402


def series(start: date, days: int, value: int = 100) -> dict:
    return {start + timedelta(days=i): value for i in range(days)}


class TheSignalCannotSeeTomorrow(unittest.TestCase):
    def test_truncating_the_history_cannot_rewrite_a_past_zscore(self):
        """The point-in-time property, tested rather than asserted.

        A z-score computed on data through day t must be identical whether or not the code can see day
        t+1. Anything built on a whole-sample mean passes every visual review and fails exactly this test.
        """

        values = [10.0 + (i % 37) * 0.1 + (5.0 if i in (300, 400, 500) else 0.0) for i in range(700)]
        whole = ab.rolling_z(values)
        for cut in (320, 455, 601):
            part = ab.rolling_z(values[:cut])
            self.assertEqual(part, whole[:cut], f"the z-score at {cut} days was computed with the future")

    def test_no_zscore_exists_before_its_own_window_does(self):
        z = ab.rolling_z([1.0] * (ab.MIN_HISTORY - 1))
        self.assertTrue(all(v is None for v in z))
        self.assertIsNotNone(ab.rolling_z([1.0] * ab.MIN_HISTORY)[-1])

    def test_a_flat_series_scores_zero_rather_than_nothing(self):
        self.assertEqual(ab.rolling_z([7.0] * (ab.MIN_HISTORY + 10))[-1], 0.0)

    def test_the_schedule_for_a_month_uses_the_previous_month_and_stops_there(self):
        months = [date(2016, m, 1) for m in range(1, 13)]
        base = {m: 0.0 for m in months}
        before = ab.schedule(self.panel, base, 0.5, True)
        for bumped, factor in ((6, 99.0), (9, 99.0), (11, 99.0)):
            hostile = dict(base)
            hostile[months[bumped]] = factor
            after = ab.schedule(self.panel, hostile, 0.5, True)
            self.assertEqual(before[:bumped + 1], after[:bumped + 1],
                             f"the signal at {months[bumped]} moved a month before it existed")

    @classmethod
    def setUpClass(cls):
        cls.panel = ab.__dict__["_tiny_panel"] if "_tiny_panel" in ab.__dict__ else None
        import cross_section as xs
        cls.panel = xs.build_panel(ab.Sleeves, lookback_months=1, start=date(2016, 1, 1),
                                   end=date(2017, 1, 1), warmup=15, reference=ab.SLEEVE)


class TheCashLegIsCash(unittest.TestCase):
    """`run_book` reads an empty weight row as "keep holding". A timing rule that inherits that default is a
    buy-and-hold rule wearing a timing costume, and it will print the most convincing wrong number in the
    file."""

    def test_an_all_zero_schedule_earns_cash_and_not_the_equity_premium(self):
        import cross_section as xs
        panel = self.panel
        n = len(panel.months)
        zero = xs.run_book(panel, [{s: 0.0 for s in ab.Sleeves}] * n, 2.0, first=panel.first)
        held = xs.run_book(panel, [{s: (1.0 if s == ab.SLEEVE else 0.0) for s in ab.Sleeves}] * n, 2.0,
                           first=panel.first)
        self.assertLess(zero["ending"], held["ending"],
                        "a book that holds nothing finished ahead of one that holds the index; the zero "
                        "row is being read as 'keep holding'")
        self.assertLess(zero["fees"], 1.0, "a never-trading book paid fees")

    def test_a_sit_out_row_is_not_an_empty_row(self):
        months = [date(2016, m, 1) for m in range(1, 13)]
        hot = {m: 99.0 for m in months}
        exits = ab.schedule(self.panel, hot, 0.5, False)     # panic exits, and panic is always on
        buys = ab.schedule(self.panel, hot, 0.5, True)       # panic buys, and panic is always on
        # Months before the signal exists are cash by assumption, so the assertion is about every month
        # that has a signal behind it: it is an explicit zero, never an empty row.
        scored = [i for i in range(len(self.panel.months))
                  if self.panel.months[max(i - 1, 0)].replace(day=1) in hot
                  and i >= 1 and self.panel.months[i] <= months[-1]]
        self.assertGreater(len(scored), 6, "the panel is too short for this test to mean anything")
        self.assertTrue(all(row for row in exits), "a rule that sat out produced empty rows, not zeros")
        self.assertTrue(all(sum(exits[i].values()) == 0.0 for i in scored),
                        "panic said exit and the book was still holding")
        self.assertTrue(all(sum(buys[i].values()) == 1.0 for i in scored))
        self.assertTrue(all(set(buys[i]) == set(ab.Sleeves) for i in scored),
                        "a row omitted a sleeve instead of zeroing it")

    @classmethod
    def setUpClass(cls):
        import cross_section as xs
        cls.panel = xs.build_panel(ab.Sleeves, lookback_months=1, start=date(2015, 7, 1),
                                   end=date(2026, 9, 4), warmup=15, reference=ab.SLEEVE)


class TheGuardAgainstAnArticleThatPostdatesItsOwnEvent(unittest.TestCase):
    """The capture trap that decides whether a page-view series is evidence or hindsight."""

    def test_a_series_that_begins_mid_sample_is_rejected(self):
        start, end = af.SAMPLE_START, af.SAMPLE_START + timedelta(days=3000)
        late = af.Series(article="2020_stock_market_crash", role="financial",
                         views=series(start + timedelta(days=1700), 1300), requested="x", resolved="x")
        cov, starts_ok = af.completeness(late, start, end)
        self.assertFalse(starts_ok, "an article created four years into the sample was allowed in")
        self.assertLess(cov, 0.5)

    def test_a_full_sample_series_is_accepted(self):
        end = af.SAMPLE_START + timedelta(days=3000)
        ok = af.Series(article="Recession", role="financial",
                       views=series(af.SAMPLE_START, 3001), requested="x", resolved="x")
        cov, starts_ok = af.completeness(ok, af.SAMPLE_START, end)
        self.assertTrue(starts_ok)
        self.assertGreaterEqual(cov, 1.0 - af.GAP_ALLOWANCE)

    def test_the_board_is_split_between_a_signal_and_a_control_that_cannot_pass(self):
        roles = dict(af.BOARD)
        self.assertGreaterEqual(sum(1 for r in roles.values() if r == "control"), 5)
        self.assertEqual(len(roles), len(af.BOARD), "an article appears twice on the board")
        self.assertTrue(set(af.CONTROL).isdisjoint(set(af.FINANCIAL)))

    def test_the_sample_start_is_the_endpoints_own_limit(self):
        self.assertEqual(af.SAMPLE_START, date(2015, 7, 1),
                         "the sample start moved; the endpoint's depth limit is a fact about the world")


class TheSealHolds(unittest.TestCase):
    """A panel assembled from blobs that no longer hash is a panel assembled from a different feed."""

    def test_a_tampered_blob_refuses_to_build_a_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "raw").mkdir()
            shutil.copy(af.INDEX, tmp / "index.json")
            for blob in af.RAW_DIR.glob("*.json"):
                shutil.copy(blob, tmp / "raw" / blob.name)
            victim = next(p for p in (tmp / "raw").glob("Recession-*.json"))
            victim.write_bytes(victim.read_bytes() + b" ")
            moved = importlib.reload(af)
            moved.RAW_DIR, moved.INDEX = tmp / "raw", tmp / "index.json"
            try:
                with self.assertRaises(SystemExit) as got:
                    moved.load_sealed()
                self.assertIn("reproduce", str(got.exception))
            finally:
                moved.RAW_DIR, moved.INDEX = af.RAW_DIR, af.INDEX
                importlib.reload(af)

    def test_the_sealed_record_covers_the_whole_sample_for_every_accepted_article(self):
        index = json.loads(af.INDEX.read_text())
        accepted = [r for r in index["fetched"] if r["accepted"]]
        self.assertEqual(len(accepted), len(af.BOARD),
                         f"only {len(accepted)} of {len(af.BOARD)} articles were accepted; the grid needs "
                         f"both baskets whole")
        for rec in accepted:
            self.assertEqual(rec["first"], index["sample_start"])
            self.assertGreaterEqual(rec["coverage"], 1.0 - af.GAP_ALLOWANCE)
            self.assertGreater(rec["days"], 3000)


class TheGraderCanRefuse(unittest.TestCase):
    """A pass rule that can only print one answer is decoration."""

    def cells(self, fin_gap: float, ctl_gap: float, rev_scale: float = 0.5) -> list:
        """A whole grid, in the shape the grader expects, with the reversal set relative to the signal.

        Only one of two mirror-image directions can beat its own reversal, so "the reversal loses" is a
        property of a cell and not of a grid: `rev_scale` below 1 lets the panic-buying direction win its
        pair, above 1 makes it lose. A grid built from equal numbers ties everywhere, and a tie is not
        strictly anything — which is how a grader gets blamed for refusing a cell it was never offered.
        """

        rows = []
        for basket, gap in (("financial", fin_gap), ("control", ctl_gap)):
            for threshold in ab.THRESHOLDS:
                for panic_buys in (True, False):
                    g = gap if basket == "control" or panic_buys else gap * rev_scale
                    for window, _lo, _hi in ab.WINDOWS:
                        rows.append({"basket": basket, "z": threshold, "panic_buys": panic_buys,
                                      "window": window, "gap": g, "$/mo": g / 40.0})
        return rows

    def test_a_cell_the_control_cannot_match_and_the_reversal_loses_is_a_pass(self):
        graded = ab.grade(self.cells(5_000.0, 100.0, rev_scale=0.5))
        self.assertTrue(any(v.startswith("CLEARS") for v in graded.values()),
                        f"the grader cannot say yes: {graded}")

    def test_a_cell_the_control_matches_is_refuted_before_anything_else_is_checked(self):
        graded = ab.grade(self.cells(5_000.0, 5_000.0))
        mine = [v for k, v in graded.items() if k[0] == "financial"]
        self.assertTrue(all(v.startswith("REFUTED") for v in mine),
                        f"the control clause did not run first: {mine}")
        self.assertNotIn("CLEARS", str(mine))

    def test_the_control_basket_can_never_pass_by_construction(self):
        graded = ab.grade(self.cells(100.0, 5_000.0))
        mine = [v for k, v in graded.items() if k[0] == "control"]
        self.assertTrue(all("control" in v for v in mine))
        self.assertNotIn("CLEARS", str(mine))

    def test_a_reversal_that_beats_the_signal_fails_the_rule(self):
        """One of the pair must lose to its own reversal, and the grader has to name that clause."""

        graded = ab.grade(self.cells(5_000.0, 100.0, rev_scale=1.8))
        mine = [v for k, v in graded.items() if k[0] == "financial"]
        self.assertTrue(any("reversal" in v for v in mine), f"the reversal clause never ran: {mine}")
        self.assertTrue(any(v.startswith("CLEARS") for v in mine),
                        f"the direction that did beat its reversal was not allowed to pass: {mine}")


class TheSealedResultIsPinned(unittest.TestCase):
    """The round's own finding, pinned so a future re-run has to disagree with it on purpose."""

    @classmethod
    def setUpClass(cls):
        cls.rows, cls.meta = ab.scan(2.0)

    def test_no_direction_of_the_financial_basket_clears_the_bar(self):
        mine = [v for v in ab.grade(self.rows).values()]
        self.assertNotIn("CLEARS", str(mine),
                         "the attention feed cleared its bar; re-read the note before believing this")

    def test_every_direction_is_refuted_by_the_control_basket(self):
        graded = ab.grade(self.rows)
        refuted = [k for k, v in graded.items() if k[0] == "financial" and v.startswith("REFUTED")]
        self.assertEqual(len(refuted), len(ab.THRESHOLDS) * 2,
                         f"{len(refuted)} of {len(ab.THRESHOLDS) * 2} directions refuted; the refutation "
                         f"is the finding and it should not get weaker quietly")

    def test_neither_direction_makes_money_and_the_whole_grid_is_negative(self):
        """The corrected finding, pinned so a future edit has to argue with it.

        The first pass at this grid showed "panic exits" earning +$507 a month, which was true of a book
        holding two index funds at once: the schedule put a full weight in every sleeve, so every "on" month
        was 2x. Corrected, both directions lose, and the exit rule only loses more slowly than the buy rule
        — which is what a variable that is a noisy restatement of the price path is supposed to do.
        """

        for threshold in ab.THRESHOLDS:
            for panic_buys in (True, False):
                cell = [r for r in self.rows if r["basket"] == "financial" and r["z"] == threshold
                        and r["panic_buys"] is panic_buys and r["window"] == ab.WINDOWS[0][0]][0]
                self.assertLess(cell["$/mo"], ab.NOISE_FLOOR + 1e-9,
                                f"z>={threshold} panic {'buys' if panic_buys else 'exits'} made money")
        buys = [r for r in self.rows if r["basket"] == "financial" and r["panic_buys"]
                and r["window"] == ab.WINDOWS[0][0]]
        exits = [r for r in self.rows if r["basket"] == "financial" and not r["panic_buys"]
                 and r["window"] == ab.WINDOWS[0][0]]
        self.assertGreater(min(r["$/mo"] for r in exits), min(r["$/mo"] for r in buys))

    def test_a_schedule_that_asks_for_leverage_is_refused_not_priced(self):
        """The bug this class exists to keep dead: 1.0 in every sleeve is 2x, not fully invested."""

        import cross_section as xs
        from datetime import date as d

        panel = xs.build_panel(ab.Sleeves, lookback_months=1, start=d(2015, 7, 1), end=d(2026, 9, 4),
                               warmup=15, reference=ab.SLEEVE)
        two = [{s: 1.0 for s in ab.Sleeves}] * len(panel.months)
        with self.assertRaises(ValueError) as got:
            ab.price(panel, two, 2.0)
        self.assertIn("leverage", str(got.exception))

    def test_a_held_month_holds_one_sleeve_and_not_the_benchmark_too(self):
        import cross_section as xs
        from datetime import date as d

        panel = xs.build_panel(ab.Sleeves, lookback_months=1, start=d(2015, 7, 1), end=d(2026, 9, 4),
                               warmup=15, reference=ab.SLEEVE)
        hot = {m.replace(day=1): 99.0 for m in panel.months}
        sched = ab.schedule(panel, hot, 0.5, True)
        held = [row for row in sched if sum(row.values()) > 0]
        self.assertTrue(held, "a permanently hot signal never got the book into the market")
        for row in held:
            self.assertAlmostEqual(sum(row.values()), 1.0, places=12)
            self.assertEqual(row[ab.BENCH], 0.0, "the comparator fund is being held, so the book is levered")

    def test_the_signal_is_persistent_enough_that_its_months_are_not_its_bets(self):
        ac1, n_eff, live = self.meta["financial"]
        self.assertGreater(ac1, 0.3, "attention turned out non-persistent; the effective-count claim needs "
                                     "revisiting")
        self.assertLess(n_eff, live / 2, f"{n_eff:.0f} effective bets in {live} months is not the discount "
                                         f"this file reports")

    def test_the_grid_is_complete(self):
        self.assertEqual(len(self.rows),
                         2 * len(ab.THRESHOLDS) * 2 * len(ab.WINDOWS),
                         "a cell is missing from the grid; a sweep with a hole in it hides losers")


if __name__ == "__main__":
    unittest.main(verbosity=2)
