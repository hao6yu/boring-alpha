"""P0 as an executable rule, and the arithmetic it must never get wrong.

Round 89's runbook opens its stopping conditions with "the tilt must beat plain index investing net of every fee and every
ticket", and for a round that sentence had no command behind it: `report` scores a book against its own zero-commission twin, and
`journal.verdict`'s comparator is deliberately generous to the book. `tools/forward_p0.py` closes the gap by rebuilding the index
side from the same sealed quotes and charging each side what that side would have paid. That is a small amount of arithmetic in
the one place where arithmetic decides whether the whole programme continues, so it gets tests with known answers: chains built
so that the expected result is derivable by hand, and a tampered ledger that must be refused rather than judged.

The flat-price chains below are not a market. They are the accounting made visible: when nothing moves, the only thing that can
separate the two sides is cost, so every assertion here is an assertion about cost.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import re
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import forward_p0 as fp                                    # noqa: E402
import paper                                               # noqa: E402
import skill_null as sn                                    # noqa: E402
from boring_alpha import journal                           # noqa: E402

RUNBOOK = (ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
FLAT = (journal.Quote("SPY", 100.0), journal.Quote("QQQ", 100.0), journal.Quote("VOO", 100.0))
START = dt.date(2026, 9, 4)


def entry(index: int, month: int, arrived: float, holdings: tuple, closing: float, fee: float = 0.0) -> journal.Entry:
    asof = START + dt.timedelta(days=30 * month)
    return journal.Entry(index=index, asof=asof, prior_hash="0" * 64, plan="p0 fixture", plan_posted_on=START,
                         opening_value=paper.OPENING if index == 0 else 0.0, cash_arrived=arrived,
                         invested=arrived, days_to_invest=0, fee_paid=fee, closing_value=closing,
                         quotes=FLAT, holdings=tuple(journal.Holding(s, u) for s, u in holdings),
                         violations=(), note="fixture")


def flat_chain(sells_at: int | None = None, closing: float = 5994.0) -> tuple:
    """Three intervals, every price 100 the whole way. Deposits on the second and third."""

    open_book = (("SPY", 1.0), ("QQQ", 1.0))
    if sells_at == 2:
        after = (("SPY", 1.05),)                       # QQQ sold, proceeds into SPY: one sell, one buy
    else:
        after = open_book
    return (entry(0, 0, 0.0, (), 5000.0),
            entry(1, 1, 500.0, open_book, 5497.0, 3.0),
            entry(2, 2, 500.0, after, closing, 2.0))


class TicketsComeFromTheRecord(unittest.TestCase):
    def test_a_month_that_only_invests_the_deposit_is_two_buys_and_no_sells(self):
        t = fp.count_tickets(flat_chain())
        self.assertEqual((t["buys"], t["sells"], t["tickets"]), (2, 0, 2))

    def test_a_rebalancing_month_is_counted_as_one_sell_and_one_buy(self):
        t = fp.count_tickets(flat_chain(sells_at=2))
        self.assertEqual((t["buys"], t["sells"], t["tickets"]), (3, 1, 4),
                         f"per interval: {t['per_interval']}")
        self.assertEqual(t["per_interval"][2]["sells"], ["QQQ"])

    def test_the_index_pays_one_order_in_every_month_money_arrived(self):
        self.assertEqual(fp.plain_index_tickets(flat_chain()), 2)
        self.assertEqual(fp.plain_index_tickets(flat_chain()[:1]), 0, "the anchor month funds nothing, so it buys nothing")


class TheArithmeticIsCheckable(unittest.TestCase):
    def test_equal_ticket_counts_make_the_commission_cancel_out_of_the_gap(self):
        """Two orders each side, flat prices: the venue can only cost both of them the same money."""

        a, b = fp.evaluate(flat_chain(), 0.0), fp.evaluate(flat_chain(), 9.95)
        self.assertAlmostEqual(a["gap"], b["gap"], delta=0.005)
        self.assertAlmostEqual(b["ticket_cost_book"], 2 * 9.95, delta=0.005)
        self.assertAlmostEqual(b["ticket_cost_index"], 2 * 9.95, delta=0.005)

    def test_an_extra_order_costs_exactly_one_ticket_and_not_a_rounding_of_anything(self):
        still = fp.evaluate(flat_chain(), 9.95)["gap"]
        trading = fp.evaluate(flat_chain(sells_at=2), 9.95)["gap"]
        self.assertAlmostEqual(trading - still, -2 * 9.95, delta=0.005,
                               msg="the rebalancing month adds one sell and one buy: two tickets, at the printed price")

    def test_on_flat_prices_the_book_lags_the_index_by_the_fees_the_engine_actually_charged(self):
        """Nothing moved, so the gap must be the sealed fee line against VOO's expense — and the sealed fee line is $5, which is
        larger, so the book loses on a flat tape. This is the number the first month will print in miniature."""

        out = fp.evaluate(flat_chain(), 0.0)
        self.assertLess(out["gap"], 0.0)
        self.assertGreater(out["gap"], -80.0, f"the gap is {out['gap']:,.2f}; on flat prices nothing else may explain it")
        self.assertGreater(out["index_value"], out["book_value"],
                           "a fee-charged book cannot beat a flat index account, which is the whole point of P0")

    def test_it_refuses_to_score_a_book_it_cannot_verify(self):
        scratch = Path(tempfile.mkdtemp(prefix="p0-tamper-"))
        try:
            book = scratch / "books" / "tampered"
            book.mkdir(parents=True)
            source = paper.PAPER_DIR / "books" / "tilt" / "ledger.jsonl"
            line = source.read_text().replace('"closing_value": 5000', '"closing_value": 5001', 1)
            self.assertNotEqual(line, source.read_text(), "the fixture did not actually tamper with anything")
            (book / "ledger.jsonl").write_text(line)
            saved_dir, saved_argv = paper.PAPER_DIR, sys.argv
            paper.PAPER_DIR = scratch
            sys.argv = ["forward_p0.py", "--book", "tampered"]
            try:
                with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
                    fp.main()
            finally:
                paper.PAPER_DIR, sys.argv = saved_dir, saved_argv
            self.assertIn("does not verify", str(caught.exception))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_a_negative_commission_is_refused_rather_than_treated_as_a_rebate(self):
        with self.assertRaises(SystemExit):
            fp.evaluate(flat_chain(), -1.0)


class TheThresholdIsTheProtocolsOwn(unittest.TestCase):
    def test_below_the_floor_it_reports_a_cost_sheet_and_no_verdict(self):
        out = fp.evaluate(flat_chain(), 0.0)
        self.assertIn("not decidable", out["verdict"])
        self.assertIn(str(journal.MIN_ENTRIES_FOR_SKILL_VERDICT - 3), out["verdict"])

    def test_the_margin_table_is_what_skill_null_still_prints(self):
        """The published margins are the only numbers in this tool that came from somewhere else, so they are re-derived."""

        argv, saved = sys.argv, sys.argv[:]
        sys.argv = ["skill_null.py", "--paths", "600", "--horizons", "24", "--json"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                sn.main()
        finally:
            sys.argv = saved
        rows = json.loads(out.getvalue())["rows"]
        row = next(r for r in rows if r["mode"] == "hurdle-as-pinned")
        self.assertAlmostEqual(fp.MARGINS[24], row["margin_bps_p95"], delta=2.0)

    def test_the_runbook_names_the_command_that_can_actually_enforce_its_first_rule(self):
        self.assertIn("forward_p0.py", RUNBOOK)


class TheBandAgainstItsTwin(unittest.TestCase):
    """Stopping rule 2, on fixtures where the expected answer is arithmetic."""

    def test_two_extra_orders_between_two_policies_is_exactly_two_tickets_at_the_printed_price(self):
        out = fp.evaluate_pair(flat_chain(sells_at=2), flat_chain(), 9.95)
        self.assertEqual((out["tickets_book"], out["tickets_twin"]), (4, 2))
        self.assertAlmostEqual(out["gap"], -2 * 9.95, delta=0.005)

    def test_the_measured_bill_is_a_share_of_paid_in_and_a_shortfall_past_it_is_named(self):
        twin = flat_chain(closing=5998.0)           # the unbanded book four dollars ahead, with no tickets to separate them
        out = fp.evaluate_pair(flat_chain(), twin, 0.0)
        self.assertAlmostEqual(out["bill_cap"], fp.BAND_BILL_SHARE * out["paid_in"], delta=0.01,
                              msg="the cap must scale with what was paid in, not sit as a dollar figure")
        self.assertAlmostEqual(out["gap"], -4.0, delta=0.01)
        self.assertGreater(-out["gap"], out["bill_cap"], "the fixture no longer breaches the cap it is meant to test")
        self.assertIn("BAND FAILS", out["verdict"],
                      f"a shortfall past the measured bill must be called what it is: {out['verdict']}")

    def test_a_shortfall_inside_the_bill_gets_no_verdict_rather_than_a_convenient_one(self):
        # The band trades twice and the twin trades four times, so the venue, not the market, decides this one.
        out = fp.evaluate_pair(flat_chain(), flat_chain(sells_at=2), 9.95)
        self.assertGreater(out["gap"], 0.0)
        self.assertIn("ahead of its own twin", out["verdict"])

    def test_two_identical_policies_are_reported_as_buying_nothing(self):
        out = fp.evaluate_pair(flat_chain(), flat_chain(), 9.95)
        self.assertAlmostEqual(out["gap"], 0.0, delta=0.005)
        self.assertIn("bought nothing", out["verdict"])

    def test_books_that_sealed_different_intervals_are_refused_rather_than_compared(self):
        with self.assertRaises(SystemExit) as caught:
            fp.evaluate_pair(flat_chain()[:2], flat_chain(), 0.0)
        self.assertIn("same intervals", str(caught.exception))

    def test_the_default_bill_cap_is_the_one_the_runbook_quotes(self):
        self.assertIn("0.054% of paid in", RUNBOOK, "the runbook no longer states the bill the tool defaults to")
        self.assertAlmostEqual(fp.BAND_BILL_SHARE, 0.00054, delta=1e-9)


class TheOneCommandScreen(unittest.TestCase):
    """`--status` is the monthly screen: four conditions, each with the command that owns it."""

    def run_status(self, argv_extra=()):
        saved, sys.argv = sys.argv, ["forward_p0.py", "--status", *argv_extra]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = fp.main()
        finally:
            sys.argv = saved
        self.assertEqual(code, 0)
        return out.getvalue()

    def test_it_lists_every_stopping_condition_by_name(self):
        text = self.run_status()
        for rule in ("P0", "band", "Skill", "Integrity"):
            self.assertIn(rule, text)

    def test_it_names_the_command_that_owns_each_condition_rather_than_answering_for_itself(self):
        text = self.run_status()
        self.assertIn("owner: tools/", text)
        self.assertIn("tools/paper.py report", text)

    def test_it_says_not_decidable_when_the_archive_has_not_earned_an_answer(self):
        text = self.run_status()
        self.assertIn("nothing to compare yet", text)
        self.assertIn("underpowered", text)
        self.assertIn("all chains verify", text)

    def test_the_json_carries_the_four_conditions_and_the_integrity_flag(self):
        saved, sys.argv = sys.argv, ["forward_p0.py", "--status", "--json"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                fp.main()
        finally:
            sys.argv = saved
        payload = json.loads(out.getvalue())
        self.assertEqual(len(payload["conditions"]), 4)
        self.assertTrue(payload["integrity_all_intact"])
        for condition in payload["conditions"]:
            self.assertTrue(all(k in condition for k in ("rule", "command", "answer")))

    def test_a_status_screen_that_only_admits_ignorance_still_exits_cleanly(self):
        self.assertIn("`not decidable`", self.run_status())

    def test_the_runbook_points_the_operator_at_the_screen(self):
        self.assertIn("--status", RUNBOOK)


class TheSecondQuestion(unittest.TestCase):
    """The objective names two indexes, so the command can be pointed at both — and must not be able to move the goal.

    P0 is 100% VOO: the plainest thing that would have done the job, pre-registered before the evidence. QQQ is the free version of
    the same bet, and the archive's own replay says the tilt loses to it (round 82: 12.3M against 9.8M), so the honest thing is a flag
    that asks the question and wording that refuses to let the answer become P0.
    """

    def test_the_witness_is_charged_its_own_sourced_fee_not_the_book_s(self):
        voo = fp.evaluate(flat_chain(), 0.0, witness="VOO")
        qqq = fp.evaluate(flat_chain(), 0.0, witness="QQQ")
        self.assertAlmostEqual(voo["witness_fee"], 0.0003, delta=1e-12)
        self.assertAlmostEqual(qqq["witness_fee"], 0.0020, delta=1e-12)
        self.assertGreater(qqq["gap"], voo["gap"],
                           "QQQ costs six times what VOO costs, so on flat prices the QQQ bar must be the easier one")

    def test_the_ticket_count_does_not_depend_on_which_index_is_named(self):
        """The index side buys once per deposit month whoever it buys, so a change of witness may not change the cost sheet."""

        a = fp.evaluate(flat_chain(sells_at=2), 9.95, witness="VOO")
        b = fp.evaluate(flat_chain(sells_at=2), 9.95, witness="QQQ")
        self.assertEqual(a["index_tickets"], b["index_tickets"])
        self.assertEqual(a["tickets"]["tickets"], b["tickets"]["tickets"])

    def test_a_secondary_bar_is_worded_as_a_secondary_bar(self):
        """A 24-entry fixture, because below the protocol's floor every verdict line is the same sentence about being undecided."""

        losing = fp.evaluate(long_flat_chain(), 9.95, witness="VOO")
        secondary = fp.evaluate(long_flat_chain(), 9.95, witness="QQQ")
        self.assertIn("FAILS P0", losing["verdict"])
        self.assertIn("FAILS the secondary bar at QQQ", secondary["verdict"])
        self.assertIn("cannot redefine P0", secondary["verdict"])
        self.assertNotIn("ahead", secondary["verdict"], "a losing book may not be dressed as a tie by a generous margin")

    def test_the_witness_being_a_sleeve_of_the_book_is_reported_rather_than_hidden(self):
        self.assertFalse(fp.evaluate(flat_chain(), 0.0, witness="VOO")["witness_is_a_sleeve"])
        self.assertTrue(fp.evaluate(flat_chain(), 0.0, witness="QQQ")["witness_is_a_sleeve"])

    def test_a_witness_with_no_sourced_fee_is_refused_before_anything_is_priced(self):
        with self.assertRaises(SystemExit):
            fp.evaluate(flat_chain(), 0.0, witness="XLU")

    def test_a_witness_the_chain_never_sealed_a_price_for_is_named_not_traced(self):
        """A posted fee is not the same thing as a sealed quote, and the difference has to be legible on screen."""

        with self.assertRaises(SystemExit) as caught:
            fp.evaluate(flat_chain(), 0.0, witness="IWM")
        message = str(caught.exception)
        self.assertIn("IWM cannot be the bar", message)
        self.assertIn("no sealed quote", message)

    def test_a_symbol_with_a_fee_but_no_price_cannot_be_a_bar_and_says_so(self):
        """Round 99 put bill funds in the fee table, which made this reachable: a sourced ratio is not a traded leg."""

        with self.assertRaises(SystemExit) as caught:
            fp.evaluate(flat_chain(), 0.0, witness="SGOV")
        self.assertIn("not a traded leg", str(caught.exception))

    def test_the_runbook_keeps_voo_as_the_standing_rule_and_says_a_second_bar_cannot_move_it(self):
        text = RUNBOOK
        self.assertIn("--witness", text)
        self.assertIn("secondary", text.lower())
        self.assertIn("VOO", text)

    def test_the_status_screen_still_asks_only_the_standing_question(self):
        saved, sys.argv = sys.argv, ["forward_p0.py", "--status"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                fp.main()
        finally:
            sys.argv = saved
        text = out.getvalue()
        self.assertIn("P0 — beat plain VOO net of everything", text)
        self.assertNotIn("QQQ", text, "the monthly screen may not quietly widen the standing rule")

    def test_the_json_separates_the_primary_from_the_secondary(self):
        import subprocess
        payload = json.loads(subprocess.run([sys.executable, str(ROOT / "tools" / "forward_p0.py"), "--book", "tilt",
                                            "--witness", "VOO,QQQ", "--json"], capture_output=True, text=True,
                                           check=True).stdout)
        self.assertEqual(list(payload), ["primary", "secondary"])
        self.assertEqual(payload["primary"]["witness"], "VOO")
        self.assertEqual([w["witness"] for w in payload["secondary"]], ["QQQ"])


def long_flat_chain(entries=24, closing=5994.0):
    """A chain past the protocol's 24-entry floor on flat prices, so verdict wording is reachable at all.

    Flat prices plus a charged fee put the book behind both bars by its own costs, which is the case the wording has to get
    right: round 90's no-skill margin is a false-*positive* threshold and must never dress a negative gap as a tie.
    """

    held = (("SPY", 1.0), ("QQQ", 1.0))
    return tuple(entry(i, i, 0.0 if i == 0 else 500.0, () if i == 0 else held,
                       paper.OPENING if i == 0 else closing, fee=2.0) for i in range(entries))


class TheCommandRuns(unittest.TestCase):
    def test_the_live_books_answer_honestly_about_having_only_an_anchor(self):
        argv, saved = sys.argv, sys.argv[:]
        for book in ("tilt_band", "tilt", None):
            sys.argv = ["forward_p0.py"] + (["--book", book] if book else []) + ["--commission", "9.95"]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = fp.main()
            self.assertEqual(code, 0)
            self.assertIn("nothing to compare yet", out.getvalue())
        sys.argv = saved

    def test_json_carries_the_ticket_ledger(self):
        sys.argv, saved = ["forward_p0.py", "--book", "tilt", "--json"], sys.argv[:]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                fp.main()
        finally:
            sys.argv = saved
        payload = json.loads(out.getvalue())["primary"]      # the shape gained a "secondary" list in round 96
        for key in ("entries", "paid_in", "tickets", "index_tickets", "verdict"):
            self.assertIn(key, payload)
        self.assertEqual(payload["tickets"]["tickets"], 0, "the anchored books hold no positions, so no order has been paid for")


if __name__ == "__main__":
    unittest.main()
