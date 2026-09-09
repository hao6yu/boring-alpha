"""Tests for `tools/monthly_ticket.py` — the artifact that turns a measured result into an order.

The mechanism was graded in rounds 4, 11 and 12. This file does not re-litigate whether leverage is a good
idea. It checks the four things that would make the *ticket* wrong while the underlying research stayed
right: that it refuses when it should, that the price it prints as protective is the price the engine acts
at, that the dollar figure it hands the user belongs to the user's account and not to the archive's, and
that the arithmetic it shows is the arithmetic it used.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import financing_break_even as fbe                 # noqa: E402
import monthly_ticket as mt                        # noqa: E402
from boring_alpha.data.csv_loader import (         # noqa: E402
    load_csv_market_data,
)

TOOL = ROOT / "tools" / "monthly_ticket.py"


class TheTicketRefusesBeforeItInstructs(unittest.TestCase):
    """A tool that can only say "here is your order" is a sales leaflet with argparse in it."""

    @classmethod
    def setUpClass(cls):
        cls.cheap = mt.issue("SPY", 1.25, "Public", 20_000.0, "full")
        cls.dear = mt.issue("SPY", 1.25, "Fidelity", 20_000.0, "full")

    def test_the_cheap_desk_gets_a_ticket(self):
        self.assertTrue(self.cheap.issued, "the cheapest posted desk was refused; nothing else here means anything")
        self.assertIn("Public", self.cheap.clears)

    def test_the_dear_desk_is_refused_and_says_which_number_refused_it(self):
        self.assertFalse(self.dear.issued)
        text = mt.render(self.dear, "full")
        self.assertIn("REFUSED", text)
        self.assertNotIn("target exposure", text, "a refused ticket still printed an order")
        self.assertIn(f"{self.dear.worst_break_even:.2%}", text,
                      "the refusal did not name the binding break-even")

    def test_the_same_book_is_refused_at_one_desk_and_issued_at_another(self):
        """The difference between the two tickets is a broker's pricing page and nothing else."""

        self.assertNotEqual(self.cheap.issued, self.dear.issued)
        self.assertEqual(self.cheap.target, self.dear.target)
        self.assertGreater(self.dear.carry_month, self.cheap.carry_month)

    def test_the_menu_decides_the_verdict_not_the_tools_opinion_of_leverage(self):
        for name, rate in fbe.MENU:
            t = mt.issue("SPY", 1.25, name, 20_000.0, "full")
            self.assertEqual(t.issued, rate <= self.cheap.worst_break_even,
                             f"{name} at {rate:.2%} was graded against the wrong threshold")

    def test_an_unlevered_ticket_is_refused_with_a_different_exit_code(self):
        """1 means "this desk is too dear"; 2 means "there is no loan to write a ticket about"."""

        for lever, expected in ((1.0, 2), (0.8, 2)):
            r = subprocess.run([sys.executable, str(TOOL), "--lever", str(lever)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, expected, r.stdout[-300:])
            self.assertIn("borrows nothing", r.stdout)
        self.assertEqual(subprocess.run([sys.executable, str(TOOL), "--desk", "Fidelity"],
                                        capture_output=True, text=True).returncode, 1)
        self.assertEqual(subprocess.run([sys.executable, str(TOOL)], capture_output=True,
                                        text=True).returncode, 0)


class TheProtectivePriceIsThePriceTheEngineActsOn(unittest.TestCase):
    """The delever trigger is the one number on the ticket that exists to protect the account."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(mt.SNAPSHOT, mt.CASH_FILE)
        cls.tickets = {L: mt.issue("SPY", L, "Public", 20_000.0, "full") for L in (1.25, 1.5, 2.0, 3.0)}

    def test_the_trigger_price_is_where_the_ratio_actually_breaches(self):
        """Equity over position at the printed price must be the maintenance ratio, to the cent."""

        for lever, t in self.tickets.items():
            fall, m = t.trigger_fall, mt.MAINTENANCE
            position = lever * (1.0 - fall)                    # per dollar of NAV, loan fixed at lever-1
            equity = position - (lever - 1.0)
            self.assertAlmostEqual(equity / position, m, places=9,
                                   msg=f"at {lever}x the printed trigger breaches at {equity / position:.4f}")

    def test_the_naive_formula_flips_from_conservative_to_dangerous(self):
        """The regression this file exists to prevent, and it is not the one I expected.

        The first version of the trigger line printed `1 - L m`. Set against the exact breach point, that
        approximation gives the user *more* room than the account has above 1/(1 - m) — 1.43x at a 30%
        ratio — and less room below it. Below the crossover it is a rounding error in the safe direction,
        which is the kind of error that survives review. Above it, the ticket would have told an operator
        to watch a price the broker had already breached. The operating point this repo recommends,
        1.25x, is on the safe side by nine points of price; 2x is not, and neither is anything a leveraged
        ETF sleeve would want.
        """

        crossover = 1.0 / (1.0 - mt.MAINTENANCE)      # 1.4286x at a 30% ratio
        for lever, t in self.tickets.items():
            naive = 1.0 - lever * mt.MAINTENANCE
            if lever < crossover:
                self.assertGreater(t.trigger_fall, naive,
                                   f"at {lever}x the exact trigger should sit further away than the naive one")
            else:
                self.assertLess(t.trigger_fall, naive,
                                f"at {lever}x the naive form was supposed to be the dangerous one")
        near = mt.issue("SPY", crossover, "Public", 20_000.0, "full")
        self.assertAlmostEqual(near.trigger_fall, 1.0 - crossover * mt.MAINTENANCE, places=9,
                               msg="the crossover moved off 1/(1-m); re-derive it before trusting the "
                                   "sign of the error")

    def test_the_trigger_moves_the_wrong_way_for_the_naive_reader(self):
        """More leverage means a *closer* trigger and a *higher* trigger price, not a lower one."""

        falls = [self.tickets[L].trigger_fall for L in (1.25, 1.5, 2.0, 3.0)]
        self.assertEqual(falls, sorted(falls, reverse=True))
        prices = [self.tickets[L].trigger_price for L in (1.25, 1.5, 2.0, 3.0)]
        self.assertEqual(prices, sorted(prices),
                         "a levered book's protective price got further away as the leverage rose")

    def test_the_archive_explains_the_margin_calls_it_prints(self):
        """0 calls is only meaningful next to the worst fall the sleeve actually took.

        A book that rebalances to target delevers as it falls and so never reaches its own trigger; a book
        whose loan just sits there does. The ticket prints both facts because they disagree, and the reader
        needs to know which book they are signing up for.
        """

        closes = [row["SPY"].close for row in self.data.by_date.values() if "SPY" in row]
        peak, worst = 0.0, 0.0
        for c in closes:
            peak = max(peak, c)
            worst = min(worst, c / peak - 1.0)
        # The 2008 collapse, to the point: peak 110.87 into the trough of 2009-03-09. Pinned because every
        # leverage conclusion in this repo is measured against this one drawdown, and a loader that quietly
        # clipped it would change the answer without changing any test's sign.
        self.assertAlmostEqual(worst, -0.552, places=3, msg=f"SPY's worst archive fall is {worst:.1%}")
        self.assertGreater(self.tickets[1.25].trigger_fall, -worst,
                           "the 1.25x trigger is inside the archive's worst fall, yet the engine took no "
                           "calls — the printed evidence and the printed price would disagree")
        self.assertLess(self.tickets[2.0].trigger_fall, -worst,
                        "at 2x the static-loan trigger should be reachable in this archive")
        self.assertEqual(self.tickets[1.25].margin_calls, 0)

    def test_the_engine_can_actually_fire_the_rule_this_ticket_promises(self):
        """A guard that cannot fire is decoration. At 3.00x the same engine does take calls."""

        self.assertGreater(self.tickets[3.0].margin_calls, 0,
                           "the maintenance rule never fires at any leverage; the forced-sale assumption "
                           "in every leverage note in this repo is untested")


class TheDollarFigureBelongsToTheAccountNotTheArchive(unittest.TestCase):
    """The research ends in millions on a 33-year path. The user has one account, this month."""

    @classmethod
    def setUpClass(cls):
        cls.tiny = mt.issue("SPY", 1.25, "Public", 5_000.0, "full")
        cls.big = mt.issue("SPY", 1.25, "Public", 50_000.0, "full")

    def test_the_money_line_scales_with_the_account_and_the_bps_do_not(self):
        self.assertAlmostEqual(self.big.per_month_at_size / self.tiny.per_month_at_size, 10.0, places=9)
        self.assertAlmostEqual(self.big.excess_measured, self.tiny.excess_measured, places=9)

    def test_the_archive_figure_is_not_presentation_for_this_size(self):
        """Both numbers must be present and they must differ, or one of them is decoration."""

        self.assertGreater(self.tiny.archive_per_month, 10 * self.tiny.per_month_at_size,
                           "the archive's $/mo and the account's $/mo are suspiciously close")
        text = mt.render(self.tiny, "full")
        self.assertIn("not a forecast", text)

    def test_the_identity_shown_is_the_identity_used(self):
        t = self.tiny
        self.assertAlmostEqual(t.per_month_at_size,
                               t.value * t.excess_measured / 1e4 / 12.0, places=6)
        self.assertAlmostEqual(t.carry_month, t.borrow * t.rate / 12.0, places=9)
        self.assertAlmostEqual(t.units * t.price, t.target, places=6)
        self.assertAlmostEqual(t.target, t.value * t.lever, places=9)

    def test_a_bigger_bet_bills_more_and_promises_more_in_the_same_ratio(self):
        t1 = mt.issue("SPY", 1.25, "Public", 20_000.0, "full")
        t2 = mt.issue("SPY", 1.50, "Public", 20_000.0, "full")
        self.assertGreater(t2.carry_month, t1.carry_month)
        self.assertGreater(t2.excess_measured, t1.excess_measured)
        self.assertGreater(t1.worst_break_even, t2.worst_break_even,
                           "more debt did not tighten the break-even")

    def test_a_sleeve_that_outruns_the_loan_clears_higher(self):
        qqq = mt.issue("QQQ", 1.25, "Public", 20_000.0, "since 2010")
        spy = mt.issue("SPY", 1.25, "Public", 20_000.0, "since 2010")
        self.assertGreater(qqq.sleeve_irr, spy.sleeve_irr)
        self.assertGreater(qqq.break_even_allin["since 2010"], spy.break_even_allin["since 2010"])


class TheRefusalPathIsNotAFileMissing(unittest.TestCase):
    """Every rejected branch has to be a decision, not an accident of parsing."""

    def test_every_menu_desk_and_every_sleeve_produces_a_ticket_or_a_refusal(self):
        for name, _rate in fbe.MENU:
            for sleeve in fbe.SLEEVES:
                t = mt.issue(sleeve, 1.25, name, 20_000.0, "full")
                self.assertGreater(t.price, 0.0, f"{sleeve} priced at zero at {name}")
                self.assertLessEqual(t.trigger_fall, 1.0 / t.lever + 1e-12)
                self.assertLessEqual(t.trigger_price, t.price)

    def test_the_binding_window_is_the_minimum_not_the_mean(self):
        t = mt.issue("SPY", 1.25, "Public", 20_000.0, "full")
        self.assertEqual(t.worst_break_even, min(t.break_even_allin.values()))
        self.assertLess(t.worst_break_even, sum(t.break_even_allin.values()) / 3)

    def test_the_json_is_the_ticket_not_a_rendition_of_it(self):
        import json
        from datetime import date

        r = subprocess.run([sys.executable, str(TOOL), "--json"], capture_output=True, text=True)
        blob = json.loads(r.stdout)
        for key in ("issued", "per_month_at_size", "worst_break_even", "margin_calls", "asof"):
            self.assertIn(key, blob)
        self.assertTrue(blob["issued"])
        data = load_csv_market_data(mt.SNAPSHOT, mt.CASH_FILE)
        self.assertEqual(date.fromisoformat(blob["asof"]),
                         max(d for d in data.by_date if "SPY" in data.by_date[d]),
                         "the ticket was priced on a date that is not the archive's latest for this sleeve")


if __name__ == "__main__":
    unittest.main(verbosity=2)
