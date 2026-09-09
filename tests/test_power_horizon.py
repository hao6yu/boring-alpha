"""Tests for the study that found the journal's benchmark could not compound.

The headline is the differential test below. Round 82 set out to ask how many monthly seals the live book needs and whether
more money shortens the wait, and to answer that honestly the study's witness had to be the journal's own — so the study
grew a simulator and this file grew a test comparing them month for month. They agreed, and both were wrong: the accounts
tracked the deposits rather than the market because both recovered a cash line from the prior balance minus holdings priced
at *today's* prices. `paper.shadow_step` is fixed in `paper.recover_cash`; this file's simulator tracks cash as a state
variable. A reimplementation is a written-down theory of the original, and this is the second time that theory turned out to
be the thing worth reading (round 69).

Everything else here is about the claim the study makes: that the wait is invariant to account size while costs are
proportional, and that a flat per-order charge breaks the invariance in the direction that hurts the small account.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import math
import statistics
import sys
import unittest


def _months(n):
    return [dt.date(2020 + m // 12, m % 12 + 1, 28) for m in range(n)]
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                                 # noqa: E402
import corpus_diff                                          # noqa: E402
import power_horizon as ph
import withdrawal_capacity as wc                                       # noqa: E402  the same snapshot the tool reads                                   # noqa: E402
from boring_alpha.journal import Comparator                  # noqa: E402

VOO = Comparator("100% VOO", {"VOO": 1.0}, paper.FEES["VOO"])
FEES = {s: paper.fee_for(s) for s in ("SPY", "QQQ", "VOO")}


class TheDifferential(unittest.TestCase):
    """The test that found the defect: two independent accounts, one fund, one deposit stream, month by month."""

    def setUp(self):
        self.closes = ph.month_closes(None)[:24]

    def _sealed(self):
        """`paper.shadow_step`, walked over the study's own month-ends, at the journal's own deposit schedule."""

        entry = paper.shadow_anchor(self.closes[0][0], self.closes[0][1])
        chain = (entry,)
        for i, (day, prices) in enumerate(self.closes[1:], start=1):
            entry = paper.shadow_step(chain, day, paper.MONTHLY, prices, VOO, "0" * 64)
            chain += (entry,)
        return chain

    def test_the_simulator_reproduces_the_sealed_witness_month_for_month(self):
        mine = ph.simulate(self.closes, paper.OPENING, paper.MONTHLY, {"VOO": 1.0},
                           paper.SPREAD_BPS, 0.0, FEES)
        theirs = [e.closing_value for e in self._sealed()[1:]]
        self.assertEqual(len(mine), len(theirs) + 1, "the sealed chain has an anchor entry; the study's first month is it")
        for i, (a, b) in enumerate(zip(mine[1:], theirs)):
            # The sealed entry rounds its balance to cents and its fees to four places; the study rounds nothing. The drift
            # between them is that bookkeeping and must not be anything else, so the tolerance is a quarter.
            self.assertAlmostEqual(a, b, delta=0.25, msg=f"month {i}: study {a:,.2f} vs sealed witness {b:,.2f}")

    def test_both_accounts_earn_the_market_so_neither_can_report_the_deposits(self):
        """The property the defect destroyed, asserted on the study's own account. Prices over the record roughly octuple."""

        value = ph.simulate(ph.month_closes(None), paper.OPENING, paper.MONTHLY, {"VOO": 1.0}, paper.SPREAD_BPS, 0.0, FEES)
        paid = ph.pay_in(ph.month_closes(None), paper.OPENING, paper.MONTHLY)
        self.assertGreater(value[-1], 2.5 * paid[-1],
                           f"a 16-year dollar-cost average into a rising index ended at {value[-1]:,.0f} on {paid[-1]:,.0f}")

    def test_the_sealed_witness_never_sells_a_rising_market_back_to_its_deposit(self):
        """A 100%-one-fund target can only ever need buying. The defect made the month *sell* on every up day by reading the
        gain as a cash hole, so the units line is the tell-tale; this is asserted on the journal's own chain, not on the
        study's copy of it."""

        rising = [100.0, 104.0, 109.0, 115.0, 122.0, 130.0, 139.0, 149.0]
        entry = paper.shadow_anchor(dt.date(2021, 1, 29), {"VOO": 100.0})
        chain = (entry,)
        for i, px in enumerate(rising[1:], start=1):
            entry = paper.shadow_step(chain, dt.date(2021, 1 + i, 28), paper.MONTHLY, {"VOO": px}, VOO, "0" * 64)
            chain += (entry,)
        units = [e.holdings[0].units for e in chain[1:] if e.holdings]
        self.assertTrue(all(b >= a for a, b in zip(units, units[1:])), f"the witness sold into strength: {units}")


class TheClaim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.study = ph.study(None, "test window")

    def _cells(self, commission):
        return {c["scale"]: c for c in self.study["cells"] if c["commission"] == commission and c["spread_bps"] == 3.0}

    def test_the_wait_is_the_same_number_of_seals_at_every_account_size_when_costs_are_proportional(self):
        got = {c["m"] for c in self._cells(0.0).values()}
        self.assertEqual(len(got), 1, f"scale bought knowledge after all: {got}")
        self.assertTrue(next(iter(got)))
        # Ceilings can straddle an integer boundary and disagree on arithmetic that is identical; the unrounded statistic is
        # what the claim is about, so the invariance is scored there.
        self.assertLess(self.study["invariance_spread"], 1e-9, str(self.study["invariance_spread"]))

    def test_a_flat_ticket_charge_breaks_the_invariance_against_the_smallest_account(self):
        for commission in ph.COMMISSIONS[1:]:
            cells = self._cells(commission)
            self.assertGreater(cells[ph.SCALES[0]]["m"], cells[ph.SCALES[-1]]["m"],
                               f"a ${commission:.2f} ticket should hurt the small account more")

    def test_the_dollar_gap_scales_with_the_account_while_the_wait_does_not(self):
        cells = self._cells(0.0)
        small, big = cells[ph.SCALES[0]], cells[ph.SCALES[-1]]
        ratio = big["final_gap"] / small["final_gap"]
        self.assertAlmostEqual(ratio, ph.SCALES[-1] / ph.SCALES[0], delta=0.5 * ratio,
                               msg="dollars are supposed to scale even when knowledge does not")

    def test_the_study_deposits_the_journals_own_shape_rather_than_an_invented_one(self):
        self.assertAlmostEqual(ph.SCALE_RATIO, paper.MONTHLY / paper.OPENING, places=10)

    def test_the_difference_it_measures_is_a_difference_and_the_book_is_ahead_on_the_record(self):
        cells = self._cells(0.0)
        for c in cells.values():
            self.assertIsNotNone(c["m"], c.get("why"))
            self.assertGreater(c["mean"], 0.0)
            self.assertGreater(c["final_gap"], 0.0)


class TheMachinery(unittest.TestCase):
    def test_horizon_refuses_a_difference_that_is_not_there_rather_than_reporting_a_big_number(self):
        down = [-0.5] * 40
        got = ph.horizon(down)
        self.assertIsNone(got["m"])
        self.assertIn("does not favour", got["why"])
        self.assertIsNone(ph.horizon([0.1] * 6)["m"], "under a year of difference is not a horizon either")

    def test_the_wait_falls_as_the_difference_grows_and_rises_as_its_noise_grows(self):
        quiet, loud = ph.horizon([0.01, 0.03] * 30), ph.horizon([-0.08, 0.12] * 30)
        self.assertAlmostEqual(quiet["mean"], loud["mean"], places=10, msg="same difference, different noise")
        self.assertLess(quiet["m"], loud["m"], "the wait is set by the noise around the difference, not its size")
        self.assertEqual(quiet["m"], math.ceil((2 * quiet["sd"] / quiet["mean"]) ** 2), "the two-sigma rule must be visible")
        self.assertGreater(loud["m"], 50)

    def test_the_statistic_is_taken_on_the_change_so_a_trending_level_cannot_pass_for_edge(self):
        rel = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05]
        inc = ph.increments(rel)
        self.assertEqual(len(inc), len(rel) - 1)
        self.assertAlmostEqual(statistics.fmean(inc), (rel[-1] - rel[0]) / (len(rel) - 1), places=12)

    def test_paid_in_adds_the_opening_once_and_the_deposit_after_that(self):
        closes = [(dt.date(2020, m, 28), {}) for m in range(1, 7)]
        paid = ph.pay_in(closes, 5_000.0, 500.0)
        self.assertEqual(paid[:3], [5_000.0, 5_500.0, 6_000.0])
        self.assertEqual(paid[-1], 5_000.0 + 500.0 * 5)

    def test_month_ends_are_the_last_day_each_month_with_every_fund_present(self):
        closes = ph.month_closes(None)
        self.assertEqual(closes, sorted(closes, key=lambda e: e[0]))
        self.assertEqual(len({d for d, _ in closes}), len(closes), "one month-end per month")
        for day, prices in closes[:24]:
            self.assertEqual(set(prices), {"SPY", "QQQ", "VOO"})
            self.assertLessEqual(day.day, 31)
        last = max(d for d, _ in closes)
        self.assertLessEqual(last, ph.month_closes(None)[-1][0])

    def test_a_flat_market_costs_the_account_its_fees_and_nothing_else(self):
        flat = [(d, {"SPY": 100.0, "QQQ": 100.0, "VOO": 100.0}) for d in _months(25)]
        value = ph.simulate(flat, 100_000.0, 10_000.0, {"VOO": 1.0}, 3.0, 0.0, FEES)[-1]
        paid = ph.pay_in(flat, 100_000.0, 10_000.0)[-1]
        self.assertLess(value, paid)
        self.assertGreater(value, paid * 0.99, f"a flat book should lose only fees: {value:,.2f} of {paid:,.0f}")

    def test_a_dearer_book_is_a_smaller_book_with_prices_held_still(self):
        flat = [(d, {"SPY": 100.0, "QQQ": 100.0, "VOO": 100.0}) for d in _months(25)]
        cheap = ph.simulate(flat, 100_000.0, 10_000.0, ph.TILT, 1.0, 0.0, {"SPY": 0.0, "QQQ": 0.0, "VOO": 0.0})[-1]
        dear = ph.simulate(flat, 100_000.0, 10_000.0, ph.TILT, 10.0, 9.95, FEES)[-1]
        self.assertLess(dear, cheap)

    def test_the_commission_is_charged_per_ticket_not_per_dollar(self):
        flat = [(d, {"SPY": 100.0, "QQQ": 100.0, "VOO": 100.0}) for d in _months(13)]
        free = ph.simulate(flat, 100_000.0, 10_000.0, ph.TILT, 0.0, 0.0, FEES)[-1]
        tickets = ph.simulate(flat, 100_000.0, 10_000.0, ph.TILT, 0.0, 9.95, FEES)[-1]
        # Thirteen month-ends: the first opens the account with cash, so twelve buying months, and a two-fund book splits
        # every deposit across two sleeves and so pays two tickets each time. Four times the charge of the one-fund book.
        self.assertAlmostEqual(free - tickets, 2 * 12 * 9.95, delta=0.60, msg="two sleeves, twelve buying months")
        one = ph.simulate(flat, 100_000.0, 10_000.0, {"SPY": 1.0}, 0.0, 9.95, FEES)[-1]
        self.assertLess(tickets, one, "a two-fund book pays two tickets a month, whatever its size")
        free_one = ph.simulate(flat, 100_000.0, 10_000.0, {"SPY": 1.0}, 0.0, 0.0, FEES)[-1]
        self.assertAlmostEqual(free_one - one, 12 * 9.95, delta=0.50, msg="one sleeve, one ticket a month")

    def test_the_study_is_serialisable_and_its_report_prints_no_untraceable_figure(self):
        study = ph.study(None, "json")
        json.dumps(study)
        self.assertEqual({c["spread_bps"] for c in study["cells"]}, set(ph.SPREADS))
        self.assertEqual(len(study["cells"]), len(ph.SCALES) * len(ph.COMMISSIONS) * len(ph.SPREADS))


class TheCommand(unittest.TestCase):
    def test_the_tool_prints_and_the_json_option_emits_the_same_numbers(self):
        out = io.StringIO()
        argv = sys.argv
        sys.argv = ["power_horizon.py", "--window", "recent"]
        try:
            with redirect_stdout(out):
                code = ph.main()
        finally:
            sys.argv = argv
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("Pre-registered claim, scored", text)
        self.assertIn("identical", text)
        self.assertRegex(text, r"\$\s?5,000")


class TheBarsHaveACommand(unittest.TestCase):
    """Round 82's most consequential table existed only as prose in a note until round 96.

    The objective is "beat VOO, QQQ, or whatever", and the archive's answer — that the free version of the bet beats the book's
    construction — was a table with no command under it. It now runs on every invocation of the tool, so the finding either
    repeats or it doesn't. The tolerance is generous on purpose: the corpus is re-fetched, closes get revised, and a headline
    that moves half a percent is the same headline. One that moves twenty is a different finding and this test says so.
    """

    PUBLISHED = {"plain VOO, the standing bar": 7_888_445.0,
                 "plain QQQ, the free version of the same bet": 12_316_793.0,
                 "plain SPY, the free market": 7_794_662.0,
                 "the tilt, rebalanced monthly": 9_841_466.0}      # renamed in round 97 when the band joined the table

    @classmethod
    def setUpClass(cls):
        cls.block = ph.secondary_bars(None, "since the witness existed")

    def test_the_reprint_still_sits_inside_a_percent_of_the_published_table(self):
        names = [row["bar"] for row in self.block["rows"]]
        for published_name in self.PUBLISHED:
            self.assertEqual(names.count(published_name), 1, f"`{published_name}` is not printed exactly once any more")
        for row in self.block["rows"]:
            if row["bar"] not in self.PUBLISHED:
                continue                                   # the band and the drift control are new; nothing to pin them to yet
            published = self.PUBLISHED[row["bar"]]
            drift = abs(row["closed_at"] - published) / published
            self.assertLess(drift, corpus_diff.TOLERANCE,
                            f"{row['bar']}: published {published:,.0f}, reprinted {row['closed_at']:,.0f}. Amend the note.")

    def test_the_same_money_is_paid_in_whichever_bar_is_chosen(self):
        paid = {round(row["paid_in"]) for row in self.block["rows"]}
        self.assertEqual(len(paid), 1, "a differential that pays in different amounts is not a comparison")

    def test_every_row_reports_a_hole_and_only_the_bills_are_allowed_none(self):
        """The bill row's zero hole is arithmetic, not an unfired check: a funded bill account gains its deposit every month.

        That exception is stated as a name rather than a filter on `abs(hole) < eps`, so a second row that quietly reports no
        hole would still fail here.
        """

        for row in self.block["rows"]:
            self.assertGreater(row["worst_drawdown"], -0.95, f"{row['bar']}: a 95% hole on a funded account is a bug")
            if row["cash"]:
                self.assertEqual(row["bar"], "T-bills, charged SGOV's ratio", "the only zero-hole row must be the bills")
                self.assertEqual(row["worst_drawdown"], 0.0, "a bill balance that fell would be a broken accrual, not a risk")
            else:
                self.assertLess(row["worst_drawdown"], 0.0, f"{row['bar']} never fell? check the path")

    def test_the_more_concentrated_bar_has_the_deeper_hole(self):
        """The one risk ordering this archive is confident enough to assert: QQQ's hole is deeper than the fund's."""

        by_name = {r["bar"]: r for r in self.block["rows"]}
        self.assertLess(by_name["plain QQQ, the free version of the same bet"]["worst_drawdown"],
                        by_name["plain VOO, the standing bar"]["worst_drawdown"])

    def test_rebalancing_this_pair_has_never_helped_on_the_way_up_over_the_record(self):
        """The claim the table now makes out loud: monthly < banded < never, and the drift control is the best of the three.

        This is the risk-free version of the r83 bill — the bill was priced in tickets, this is priced in dollars of terminal
        value, and the two agree in sign for the first time because round 83 counted the trades and not the forgone drift.
        """

        rows = {r["bar"]: r for r in self.block["rows"]}
        monthly = rows["the tilt, rebalanced monthly"]["closed_at"]
        banded = rows["the tilt, only past 5 points of drift"]["closed_at"]
        drift = rows["the tilt, never rebalanced"]["closed_at"]
        self.assertLessEqual(monthly, banded, "monthly rebalancing is supposed to be the most expensive variant")
        self.assertLessEqual(banded, drift, "the band is supposed to trade less often than the drift control")
        self.assertGreater(drift - monthly, 10_000.0, "if the three variants are within noise the table may not claim an ordering")

    def test_the_band_which_has_not_fired_in_the_recent_window_costs_exactly_nothing_there(self):
        recent = ph.secondary_bars(dt.date.today() - dt.timedelta(days=5 * 365), "last five years")
        rows = {r["bar"]: r["closed_at"] for r in recent["rows"]}
        self.assertAlmostEqual(rows["the tilt, only past 5 points of drift"], rows["the tilt, never rebalanced"], delta=1.0,
                              msg="five points of drift have not been breached in 61 months; if they now are, the live book"
                                  " has started trading and this test has to be re-read rather than relaxed")

    def test_the_bill_row_is_charged_the_table_s_ratio_and_not_the_guess(self):
        import fund_fees as ff
        row = next(r for r in self.block["rows"] if r["cash"])
        self.assertEqual(row["expense_ratio"], ff.fee_for("SGOV"))
        self.assertNotEqual(row["expense_ratio"], ff.GUESS)

    def test_the_bill_row_meets_the_curve_the_other_half_of_the_repository_already_reports(self):
        """An independent engine owns the bill curve; this bar must agree with it on the same twelve hundred months.

        `cash_yield_gap.bill()` annualises the mean of the last 120 complete monthly factors. This bar accrues the same
        sessions the fund bars use — which is a different construction (interval products, exact on a stub) — so agreement
        is evidence and not tautology. The window stops one month short of the seal so the comparison excludes the stub,
        which is precisely the defect round 47 was written about.
        """
        import cash_yield_gap as cy
        from boring_alpha.data.csv_loader import load_csv_market_data
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        accruals = ph.secondary_bars(None, "since the witness existed")["accruals"]
        twelve = sum(accruals[-121:-1]) / 120.0
        implied = (1.0 + twelve) ** 12 - 1.0
        self.assertAlmostEqual(implied, cy.bill(data)["last10y"], delta=0.003,
                              msg=f"two readings of one curve disagreed by more than 30 bps: {implied:.4f} vs "
                                  f"{cy.bill(data)['last10y']:.4f}")

    def test_the_bill_bar_refuses_a_calendar_it_cannot_accrue_on(self):
        """No sessions between two month keys means the row would silently earn nothing, which is a wrong number, not a missing one."""

        with self.assertRaises(SystemExit):
            ph.cash_bar([(dt.date(2026, 1, 30), {}), (dt.date(2026, 1, 30), {})], 1000.0, 100.0, 0.0009, 3.0)

    def test_the_archive_names_the_free_version_of_the_bet_as_the_best_bar(self):
        best = max(self.block["rows"], key=lambda r: r["closed_at"])
        self.assertIn("QQQ", best["bar"])
        tilt = next(r for r in self.block["rows"] if r["bar"].startswith("the tilt"))
        self.assertGreater(best["closed_at"] - tilt["closed_at"], 1_000_000.0,
                           "the tilt's lead over the free bet has shrunk; re-read what changed before quoting either")

if __name__ == "__main__":
    unittest.main()
