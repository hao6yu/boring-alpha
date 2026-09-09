"""Tests for the file that bills the archive's free-rebalancing idealisation.

The claims being tested are narrow and mechanical: a one-fund account must be identical under every rebalancing regime
because there is nothing to rebalance; a band may never sell more often than a monthly rebalance; the sell counter must be
non-zero for a book that demonstrably sells (it was silently zero for one run, counted after the trades had settled the
account); and a band wide enough to never trigger must reproduce two independent dollar-cost averages, summed — an oracle
computed a different way rather than the same function called twice.

The economic findings are in the note, not here. Nothing in this file asserts what the tape did, because the tape is the
thing under test.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                                 # noqa: E402
import power_horizon as ph                                   # noqa: E402
import rebalance_cost as rc                                  # noqa: E402

FLAT = [(dt.date(2021 + m // 12, m % 12 + 1, 28), {"SPY": 100.0, "QQQ": 100.0, "VOO": 100.0}) for m in range(25)]
DIVERGING = [(dt.date(2021 + m // 12, m % 12 + 1, 28),
              {"SPY": 100.0, "QQQ": 100.0 * (1.05 ** m), "VOO": 100.0}) for m in range(25)]


def row(rows, window, construction, regime):
    return rc.by(rows, window=window, construction=construction, regime=regime)[0]


class Grids(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.closes = ph.month_closes(None)
        cls.rows = rc.grid(cls.closes, "the record", len(cls.closes))

    def test_the_row_being_priced_is_the_book_running_live(self):
        """The construction this file exists to cost-check must be the one the journal is holding, not a near relation."""

        want = next(c for c in rc.CONSTRUCTIONS if c[0] == "50% QQQ")
        self.assertEqual(want[1], paper.tilt_weights())
        self.assertEqual(want[2], "the live income book")

    def test_a_single_fund_book_is_the_same_account_under_every_charged_regime(self):
        """There is nothing to rebalance in a one-sleeve book, so any difference between charged regimes is a bug in the band.

        The no-trading-cost column is excluded on purpose: it waives the spread on *purchases* too, so a book that never
        rebalances still ends up ahead of itself there. Pretending otherwise is how a comparison quietly changes two things at
        once, which round 81's fee ordering and round 69's differential both exist to prevent.
        """

        for construction in ("plain VOO", "plain SPY", "100% QQQ"):
            values = {r["regime"]: r["value"] for r in rc.by(self.rows, window="the record", construction=construction)
                      if r["regime"] in rc.CHARGED}
            self.assertEqual(len(values), len(rc.CHARGED), construction)
            self.assertEqual(len(set(round(v, 2) for v in values.values())), 1, f"{construction}: {values}")

    def test_the_same_policy_charged_a_spread_is_never_worth_more_than_that_policy_charged_none(self):
        """Monotonicity holds only between accounts running the *same* policy. `deposit only` beats the zero-cost column by
        more than a fee on this record — letting a winner run was worth far more than the spread — and an assertion that
        ignored that would be a claim about costs smuggling in a claim about the tape."""

        for construction, _, _ in rc.CONSTRUCTIONS:
            free = row(self.rows, "the record", construction, rc.FREE)["value"]
            monthly = row(self.rows, "the record", construction, rc.MONTHLY)["value"]
            self.assertLessEqual(monthly, free + 0.01, f"{construction} gained from being charged for the same trades")

    def test_a_wider_band_never_sold_more_than_the_monthly_rebalance(self):
        for construction, _, _ in rc.CONSTRUCTIONS:
            monthly = row(self.rows, "the record", construction, rc.MONTHLY)
            band5 = row(self.rows, "the record", construction, "band 5 pts")
            band10 = row(self.rows, "the record", construction, "band 10 pts")
            self.assertLessEqual(band5["sell_months"], monthly["sell_months"], construction)
            self.assertLessEqual(band10["sell_months"], band5["sell_months"], construction)

    def test_the_book_under_test_actually_sold_the_counter_says_it_did(self):
        """The first version of this tally read the account after its orders had settled, so every month looked like no trade
        at all and the file reported a rebalancing book that had never rebalanced."""

        mixed = row(self.rows, "the record", "50% QQQ", rc.MONTHLY)
        self.assertGreater(mixed["sell_months"], 0)
        self.assertGreater(mixed["sell_months"], mixed["months"] * 0.25,
                           f"on a record where one sleeve out-returned the other, {mixed['sell_months']} sales is too few")
        single = row(self.rows, "the record", "plain VOO", rc.MONTHLY)
        self.assertEqual(single["sell_months"], 0)

    def test_tickets_are_one_per_sleeve_per_month_and_do_not_depend_on_the_band(self):
        """A book that adds money every month buys every sleeve every month whatever its band: the band stops sales, not
        contributions. This is why the answer to ticket drag is the fund count, not the policy."""

        for construction, _, _ in rc.CONSTRUCTIONS:
            monthly = row(self.rows, "the record", construction, rc.MONTHLY)
            band5 = row(self.rows, "the record", construction, "band 5 pts")
            weights = {c[0]: c[1] for c in rc.CONSTRUCTIONS}[construction]
            expected = 12.0 * sum(1 for w in weights.values() if w > 0.0)
            self.assertAlmostEqual(monthly["per_year"], expected, delta=0.5, msg=construction)
            self.assertGreaterEqual(band5["tickets"], monthly["tickets"] - 12.0, construction)

    def test_the_cost_and_the_drift_effect_are_kept_apart_and_each_recomputes(self):
        """The whole point of the file: a spread bill is a cost, an end-value gap is a cost plus a path."""

        tax = rc.idealisation_tax(self.rows, "the record", "50% QQQ")
        monthly = row(self.rows, "the record", "50% QQQ", rc.MONTHLY)
        plain = row(self.rows, "the record", "50% QQQ", rc.PLAIN)
        self.assertAlmostEqual(tax["spread_cost"], monthly["spread_paid"] - plain["spread_paid"], delta=0.01)
        self.assertAlmostEqual(tax["value_gap"], monthly["value"] - plain["value"], delta=0.01)
        self.assertGreater(tax["spread_cost"], 0.0, "a book that trades pays more spread than one that does not")
        voo = row(self.rows, "the record", "plain VOO", rc.PLAIN)["value"]
        self.assertAlmostEqual(tax["monthly_vs_voo"], monthly["value"] - voo, delta=0.01)
        self.assertGreater(abs(tax["value_gap"]), tax["spread_cost"],
                           "if the drift did not dominate the bill, this file's title would be the wrong title")

    def test_the_rows_are_serialisable_and_carry_every_figure_the_report_prints(self):
        json.dumps(self.rows)
        for r in self.rows:
            for key in ("value", "paid_in", "tickets", "sell_months", "per_year", "why"):
                self.assertIn(key, r)
            self.assertGreater(r["value"], 0.0)
            self.assertLess(r["value"], r["paid_in"] * 40.0, "a sanity bound, not a claim")


class BandMechanics(unittest.TestCase):
    def test_a_band_wide_enough_to_never_trigger_is_two_independent_dollar_cost_averages(self):
        """An oracle computed a different way: never rebalancing a 50/50 book is the same account as two single-fund accounts
        holding half the money each, and that is checkable without this file's arithmetic."""

        never = ph.simulate(DIVERGING, 100_000.0, 10_000.0, {"SPY": 0.5, "QQQ": 0.5}, 3.0, 0.0, rc.fees(), band=100.0)
        halves = [0.0, 0.0]
        for i, weights in enumerate(({"SPY": 1.0}, {"QQQ": 1.0})):
            halves[i] = ph.simulate(DIVERGING, 50_000.0, 5_000.0, weights, 3.0, 0.0, rc.fees())[-1]
        self.assertAlmostEqual(never[-1], sum(halves), delta=1.0,
                               msg=f"banded {never[-1]:,.2f} against summed halves {sum(halves):,.2f}")

    def test_a_book_that_never_rebalances_never_sells(self):
        stats: dict = {}
        ph.simulate(DIVERGING, 100_000.0, 10_000.0, {"SPY": 0.5, "QQQ": 0.5}, 3.0, 9.95, rc.fees(), band=100.0,
                    stats=stats)
        self.assertEqual(stats["sells"], 0)
        self.assertEqual(stats["tickets"], 2 * (len(DIVERGING) - 1))

    def test_a_lump_sum_book_rebalances_every_month_of_a_diverging_pair(self):
        stats: dict = {}
        ph.simulate(DIVERGING, 100_000.0, 0.0, {"SPY": 0.5, "QQQ": 0.5}, 3.0, 0.0, rc.fees(), stats=stats)
        self.assertGreater(stats["sells"], len(DIVERGING) // 2, f"only {stats['sells']} selling months")

    def test_a_heavily_funded_book_rebalancing_monthly_buys_rather_than_sells(self):
        """Found while writing the test above: while the monthly deposit is large relative to the book, arriving money can
        restore the weights by buying both sleeves, so nothing is sold at all. The 16-year record crosses over at month ~90,
        which is why it shows 100 selling months out of 193. Rebalancing is a cost of *mature* accounts, not of accumulating
        ones — and the live book, at $500 a month on $5,000, is in the buying phase."""

        stats: dict = {}
        ph.simulate(DIVERGING, 10_000.0, 10_000.0, {"SPY": 0.5, "QQQ": 0.5}, 3.0, 0.0, rc.fees(), stats=stats)
        self.assertEqual(stats["sells"], 0, f"a book whose deposit is its whole month sold {stats['sells']} times")

    def test_a_flat_tape_produces_no_sells_and_no_turnover(self):
        stats: dict = {}
        ph.simulate(FLAT, 100_000.0, 10_000.0, {"SPY": 0.5, "QQQ": 0.5}, 3.0, 0.0, rc.fees(), stats=stats)
        self.assertEqual(stats["sells"], 0, "nothing moved, so nothing had drifted")
        self.assertGreater(stats["tickets"], 0, "the deposit was still bought")

    def test_an_annual_decision_sells_in_a_twelfth_of_the_months_a_monthly_one_does(self):
        monthly, annual = {}, {}
        ph.simulate(DIVERGING, 100_000.0, 10_000.0, {"SPY": 0.5, "QQQ": 0.5}, 3.0, 0.0, rc.fees(), stats=monthly)
        ph.simulate(DIVERGING, 100_000.0, 10_000.0, {"SPY": 0.5, "QQQ": 0.5}, 3.0, 0.0, rc.fees(), every=12,
                    stats=annual)
        self.assertLess(annual["sells"], monthly["sells"])
        self.assertLessEqual(annual["months"], monthly["months"])


class TheReport(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        argv = sys.argv
        sys.argv = ["rebalance_cost.py"]
        try:
            with redirect_stdout(self.out):
                rc.main()
        finally:
            sys.argv = argv
        self.text = self.out.getvalue()

    def test_the_claim_is_scored_on_every_window_rather_than_asserted_once(self):
        self.assertIn("ranking survives being charged:", self.text)
        self.assertEqual(self.text.count("ranking survives being charged"), 2, "both windows must be scored, not one")
        self.assertIn("NOT one-signed", self.text, "the drift effect changes sign between windows and must not be averaged")

    def test_the_deferral_is_printed_rather_than_left_out_quietly(self):
        """The brake constructions are excluded because their flat months park cash and this file does not model a bill curve.
        An omission a reader cannot find is a bias with the name left off."""

        self.assertIn("deferred on purpose", self.text)
        for name in ("brake", "bill curve"):
            self.assertIn(name, self.text)

    def test_the_json_carries_the_taxes_and_the_ticket_rows_the_report_sums(self):
        out = io.StringIO()
        argv = sys.argv
        sys.argv = ["rebalance_cost.py", "--json"]
        try:
            with redirect_stdout(out):
                rc.main()
        finally:
            sys.argv = argv
        got = json.loads(out.getvalue())
        self.assertEqual(len(got["taxes"]), 2)
        self.assertEqual(len(got["tickets"]), 8, "two sizes by four fund-count and band combinations")
        for t in got["tickets"]:
            self.assertIn("share_of_deposit", t)

    def test_a_two_fund_book_pays_twice_the_ticket_drag_of_a_one_fund_book_at_the_same_size(self):
        pairs = {(t["scale"], t["regime"]): t for t in rc.tickets()}
        for scale in rc.TICKET_SCALES:
            two = pairs[(scale, "two funds, monthly")]
            one = pairs[(scale, "one fund, monthly")]
            self.assertAlmostEqual(two["tickets"] / one["tickets"], 2.0, places=3)
            self.assertGreater(two["sell_months"], one["sell_months"])


class Windows(unittest.TestCase):
    def test_the_recent_window_is_stated_relative_to_the_archive_not_to_a_typed_year(self):
        since = ph.last_date() - dt.timedelta(days=int(365.25 * 5))
        got = ph.month_closes(since)
        self.assertGreater(len(got), 55)
        self.assertLessEqual(len(got), 65)
        self.assertLessEqual(len(got), len(ph.month_closes(None)))


class ThePublishedTable(unittest.TestCase):
    """Round 83 published a table; round 84 changed an accounting convention underneath it and two cells moved by $35k.

    A note is evidence only if the artefact can tell when it has been invalidated, so the headline cells of that table are
    pinned here at the cent. This is not a claim that these numbers are right forever: it is a claim that they cannot move
    again without a test failing and a correction being written, which is the difference between a published figure and a
    number that happens to be on screen.
    """

    @classmethod
    def setUpClass(cls):
        cls.closes = ph.month_closes(None)
        cls.rows = rc.grid(cls.closes, "the record", len(cls.closes))
        cls.recent = ph.month_closes(ph.last_date() - dt.timedelta(days=int(365.25 * 5)))
        cls.rows += rc.grid(cls.recent, "last five years", len(cls.recent))

    def published(self, window, construction, regime):
        return rc.by(self.rows, window=window, construction=construction, regime=regime)[0]["value"]

    def test_the_record_column_that_survived_the_convention_fix(self):
        for construction, expected in (("plain VOO", 7853675.0), ("plain SPY", 7760092.0), ("100% QQQ", 12216556.0)):
            self.assertAlmostEqual(self.published("the record", construction, rc.MONTHLY), expected, delta=1.0,
                                   msg=construction)

    def test_the_two_cells_round_eighty_five_had_to_correct(self):
        self.assertAlmostEqual(self.published("the record", "25% QQQ", "band 5 pts"), 8792165.0, delta=1.0)
        self.assertAlmostEqual(self.published("the record", "75% QQQ", "band 5 pts"), 11008766.0, delta=1.0)
        self.assertAlmostEqual(self.published("the record", "50% QQQ", "band 5 pts"), 9812538.0, delta=1.0)

    def test_the_headline_claims_of_the_note_recompute_from_the_rows(self):
        """The note's four sentences that make a claim, restated as arithmetic on the published table."""

        tax = rc.idealisation_tax(self.rows, "the record", "50% QQQ")
        self.assertAlmostEqual(tax["spread_cost"], 1091.0, delta=2.0)
        self.assertAlmostEqual(tax["value_gap"], -210122.0, delta=2.0)
        self.assertAlmostEqual(tax["monthly_vs_voo"], 1924527.0, delta=2.0)
        self.assertEqual((tax["sell_months"], tax["sell_months_band5"]), (100, 2))
        recent = rc.idealisation_tax(self.rows, "last five years", "50% QQQ")
        self.assertGreater(recent["value_gap"], 0.0, "the five-year sign is the one that flips; if it stops flipping,"
                                                    " this file's central finding needs rewriting, not re-running")
        self.assertAlmostEqual(recent["value_gap"], 1319.0, delta=2.0)

    def test_a_band_that_never_triggers_is_the_same_book_as_one_that_never_rebalances(self):
        """Over the last five years the 5-point band never fired, so the banded and drifted books must be identical to the
        dollar. Anything else would mean the band does something even when it decides to do nothing."""

        for construction in ("25% QQQ", "50% QQQ", "75% QQQ"):
            self.assertAlmostEqual(self.published("last five years", construction, "band 5 pts"),
                                   self.published("last five years", construction, rc.PLAIN), delta=0.01,
                                   msg=construction)


if __name__ == "__main__":
    unittest.main()
