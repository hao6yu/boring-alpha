"""Tests for the drift band, the one execution policy this repository has ever measured rather than assumed.

Round 83 priced five rebalancing regimes on the archive and found that the policy, not the fee, is where the money moves:
rebalancing monthly instead of letting the weights drift cost $210,122 on the record and *won* $1,319 on the last five years.
A backtest could not settle that — the sign is the tape's — so the difference was written into a book and anchored, where it
will be settled by month-ends nobody has seen. These tests hold the book to exactly one difference from `tilt`: the band.

Nothing here asserts which policy wins. That is what the ledger is for.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                        # noqa: E402
import rebalance_cost                               # noqa: E402

TARGETS = {"SPY": 0.5, "QQQ": 0.5}


def book(drift_spy_points: float, cash: float = 0.0, equity: float = 10_000.0, prices=None):
    """A book holding `equity` across two sleeves, one of which is `drift_spy_points` overweight."""

    prices = prices or {"SPY": 100.0, "QQQ": 100.0}
    spy_value = equity * (0.5 + drift_spy_points / 100.0)
    units = {"SPY": spy_value / prices["SPY"], "QQQ": (equity - spy_value) / prices["QQQ"]}
    return paper.orders_within_band(TARGETS, units, prices, equity + cash, cash, paper.TILT_BAND_POINTS)


class TheNumber(unittest.TestCase):
    def test_the_band_is_pinned_to_the_measurement_that_chose_it(self):
        """Same rule as the tilt weight and the comparator's fee: a live parameter must name the table that produced it."""

        self.assertEqual(paper.TILT_BAND_POINTS, 5.0)
        priced = {name: band for name, band, _every, _spread, _comm, _why in rebalance_cost.REGIMES}
        self.assertEqual(paper.TILT_BAND_POINTS, priced["band 5 pts"])

    def test_a_caller_may_not_choose_it(self):
        argv = sys.argv
        sys.argv = ["paper.py", "init", "--book", "scratch", "--model", "tilt_band", "--band", "0"]
        try:
            with self.assertRaises(SystemExit) as got, redirect_stdout(io.StringIO()):
                paper.main()
        finally:
            sys.argv = argv
        self.assertIn("TILT_BAND_POINTS", str(got.exception))

    def test_the_band_is_carried_by_the_signal_not_by_the_stepping_code(self):
        """Read from a constant at the call site, a second rebalancing rule would live in `command_step` where the model that
        asked for it cannot be seen, and the next model would silently inherit it."""

        data = paper.load_data()
        banded = paper.signal_for(data, dt.date(2026, 9, 4), "tilt_band")
        plain = paper.signal_for(data, dt.date(2026, 9, 4), "tilt")
        self.assertEqual(banded.band, paper.TILT_BAND_POINTS)
        self.assertEqual(plain.band, 0.0)
        self.assertEqual(banded.target_weights, plain.target_weights)


class InsideTheBand(unittest.TestCase):
    def test_a_book_inside_its_band_raises_not_a_single_sell(self):
        orders, drift = book(3.0, cash=500.0)
        self.assertLessEqual(drift, paper.TILT_BAND_POINTS, f"the fixture drifted {drift:.1f} points")
        self.assertNotIn("SELL", {o.side for o in orders}, f"{[(o.symbol, o.side) for o in orders]}")

    def test_the_deposit_is_still_invested(self):
        """Round 83's most expensive bug: the band suppressed the first rebalance and the opening sat in cash for sixteen
        years, so a low-turnover policy was measured as a cash-drag policy. A band may stop sales; it may not stop investing.
        """

        orders, _ = book(3.0, cash=500.0)
        bought = sum(o.notional for o in orders if o.side == "BUY")
        self.assertAlmostEqual(bought, 500.0, delta=1.0, msg=f"{[(o.symbol, round(o.notional, 2)) for o in orders]}")
        self.assertEqual({o.side for o in orders}, {"BUY"})

    def test_arriving_cash_is_split_by_the_target_weights_not_by_the_current_ones(self):
        orders, _ = book(3.0, cash=1_000.0)
        by_symbol = {o.symbol: o.notional for o in orders}
        self.assertAlmostEqual(by_symbol["SPY"] / by_symbol["QQQ"], 1.0, delta=0.02,
                               msg=f"the underweight sleeve should get the same deposit: {by_symbol}")

    def test_a_book_inside_its_band_with_nothing_to_add_does_nothing(self):
        orders, _ = book(3.0, cash=0.0)
        self.assertEqual(orders, [])

    def test_the_first_month_of_a_new_book_invests_through_the_band(self):
        """At inception every sleeve is 50 points adrift, so the band cannot hold the opening back — but the reason is worth
        pinning, because a band implemented as 'never sell' rather than 'not yet' would strand the anchor cash."""

        orders, drift = book(0.0, cash=5_000.0, equity=0.0)
        self.assertGreater(drift, paper.TILT_BAND_POINTS)
        self.assertEqual(len(orders), 2)
        self.assertAlmostEqual(sum(o.notional for o in orders), 5_000.0, delta=1.0)


class OutsideTheBand(unittest.TestCase):
    def test_a_drift_past_the_band_sells_the_runner(self):
        orders, drift = book(8.0, cash=500.0)
        self.assertGreater(drift, paper.TILT_BAND_POINTS)
        self.assertIn(("SPY", "SELL"), [(o.symbol, o.side) for o in orders])

    def test_a_breach_rebalances_to_the_targets_the_untouched_model_would_have_used(self):
        """The band decides *when* to trade. It must not change where the book is going: two policies, one destination."""

        units = {"SPY": 58.0, "QQQ": 47.0}
        prices = {"SPY": 100.0, "QQQ": 100.0}
        equity = 10_500.0
        orders, _ = paper.orders_within_band(TARGETS, units, prices, equity, 0.0, paper.TILT_BAND_POINTS)
        self.assertEqual(orders, paper.orders_for(TARGETS, units, prices, equity))

    def test_the_drift_is_measured_in_points_of_weight_not_in_dollars(self):
        """Otherwise a book that compounds would drift out of its band merely by growing, and the band would quietly mean
        'rebalance for the first few years'."""

        small, _ = book(4.0, cash=0.0, equity=10_000.0)
        large, big_drift = book(4.0, cash=0.0, equity=1_000_000.0)
        self.assertAlmostEqual(big_drift, 4.0, delta=0.01)
        self.assertEqual(small, large)


class TheBookItself(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "data/paper/books/tilt_band/model.json").read_text())

    def test_the_two_books_differ_in_the_policy_and_in_nothing_else(self):
        """Round 70's rule: one construction per book. The forward comparison is only meaningful if the weight, the sleeves,
        the fees and the witness are the same and the difference is declared, single, and narrow."""

        self.assertEqual(paper.book_sleeves("tilt_band"), paper.book_sleeves("tilt"))
        self.assertEqual(paper.book_fees("tilt_band"), paper.book_fees("tilt"))
        tilt = json.loads((ROOT / "data/paper/books/tilt/model.json").read_text())
        self.assertEqual(self.config["comparator"], tilt["comparator"], "the witness must be the same fund, at the same fee")
        self.assertEqual(list(self.config["comparator"]["weights"]), ["VOO"])
        self.assertEqual(self.config["rebalance_band_points"], paper.TILT_BAND_POINTS)

    def test_the_band_was_never_retrofitted_onto_a_book_that_was_anchored_without_it(self):
        raw = (ROOT / "data/paper/books/tilt/model.json").read_text()
        tilt = json.loads(raw)
        self.assertIsNone(tilt.get("rebalance_band_points"))
        self.assertNotIn("band", raw.lower(), "the band must not be retrofitted onto a book anchored without one")

    def test_the_banded_policy_is_written_into_the_name_a_forward_reader_will_see(self):
        name = paper.signal_for(paper.load_data(), dt.date(2026, 9, 4), "tilt_band").name
        self.assertIn("rebalanced only past 5 points", name)
        self.assertIn("0.200%", name, "the fee disclosure must survive the policy change")

    def test_every_anchored_book_still_reports_an_intact_chain(self):
        out = subprocess.run([sys.executable, str(ROOT / "tools/paper.py"), "compare"], capture_output=True, text=True,
                             check=True, cwd=ROOT).stdout
        self.assertIn("tilt_band", out)
        self.assertNotIn("broken", out)


if __name__ == "__main__":
    unittest.main()
