"""The forward journal's guarantees, and the lies it must make impossible.

Three groups. The chain must refuse silent edits, or the whole premise of a
journal is a story with timestamps. The comparator must reproduce an answer
computable by hand, or the benchmark it prints is decoration. And the skill
verdict must be unreachable early, or the tool manufactures the confidence it
exists to test.
"""

from dataclasses import replace
from datetime import date, timedelta
import json
import tempfile
import unittest
from pathlib import Path

from boring_alpha.journal import (
    GENESIS,
    MIN_ENTRIES_FOR_SKILL_VERDICT,
    Comparator,
    Entry,
    Holding,
    Quote,
    account_return,
    append,
    comparator_flows,
    comparator_path,
    comparator_return,
    create_ledger,
    entry_hash,
    measure,
    read,
    verdict,
    verify,
)

SPY = "SPY"
COMPARATOR = Comparator("100% SPY", {SPY: 1.0}, 0.0)
THIRTY = timedelta(days=30)


def make_entry(index, asof, prior, close, opening, arrived, closing, *, fees=0.0,
               days=0, violations=(), plan=None):
    return Entry(
        index=index,
        asof=asof,
        prior_hash=prior,
        plan=plan or f"buy ${arrived:,.0f} of SPY on the declared day",
        plan_posted_on=asof - THIRTY,
        opening_value=opening,
        cash_arrived=arrived,
        invested=arrived,
        days_to_invest=days,
        fee_paid=fees,
        closing_value=closing,
        quotes=(Quote(SPY, close),),
        holdings=(Holding(SPY, closing / close),),
        violations=tuple(violations),
        note="",
    )


def month_series(months, growth=0.01, contribution=500.0, opening=5_000.0,
                 price0=100.0, fee=0.0, days=0, start=date(2027, 1, 31)):
    """A path growing by exactly `growth` per interval, on exact 30-day intervals.

    Follows the journal's own convention: the first entry carries the opening
    value and no growth, and each later entry applies one interval's return to the
    balance *after* that interval's deposit. Exact 30-day spacing is deliberate, so
    the money-weighted solver has one unambiguous answer and the assertions are
    analytic rather than calibrated.
    """

    entries, price, value, prior = [], price0, opening, GENESIS
    for index in range(months):
        arrived = 0.0 if index == 0 else contribution
        opening_here = value
        if index:
            price *= 1.0 + growth
            value = (opening_here + arrived - fee) * (1.0 + growth)
        entries.append(
            make_entry(index, start + index * THIRTY, prior, round(price, 8),
                       opening_here, arrived, value, fees=fee, days=days)
        )
        prior = entry_hash(entries[-1])
    return tuple(entries)


def closed_form(months, growth, contribution, opening, fee=0.0):
    """open*(1+g)^(n-1) + sum of (c-f)*(1+g)^k for k in 1..n-1, by unrolling."""

    net = contribution - fee
    total = opening * (1.0 + growth) ** (months - 1)
    factor = 1.0 + growth
    for k in range(1, months):
        total += net * factor ** k
    return total


class LedgerChain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_first_entry_must_be_genesis(self):
        with self.assertRaises(ValueError):
            create_ledger(self.path, month_series(2)[1])

    def test_a_written_ledger_is_never_overwritten(self):
        create_ledger(self.path, month_series(1)[0])
        with self.assertRaises(ValueError):
            create_ledger(self.path, month_series(1)[0])

    def test_an_edited_plan_breaks_the_chain_from_that_entry_onward(self):
        entries = month_series(4)
        create_ledger(self.path, entries[0])
        for entry in entries[1:]:
            append(self.path, entry)
        self.assertTrue(verify(self.path))

        lines = self.path.read_text().splitlines()
        row = json.loads(lines[1])
        row["plan"] = "I always intended to hold the cash"
        lines[1] = json.dumps(row, sort_keys=True)
        self.path.write_text("\n".join(lines) + "\n")

        report = verify(self.path)
        self.assertFalse(report)
        self.assertIsNotNone(report.broken_at)
        self.assertIn("hash", report.reason.lower())

    def test_a_replayed_old_entry_is_refused(self):
        entries = month_series(3)
        create_ledger(self.path, entries[0])
        append(self.path, entries[1])
        append(self.path, entries[2])
        with self.assertRaises(ValueError):
            append(self.path, entries[1])

    def test_an_entry_with_a_forged_link_is_refused(self):
        entries = month_series(2)
        create_ledger(self.path, entries[0])
        forged = replace(entries[1], prior_hash="f" * 64)
        with self.assertRaises(ValueError):
            append(self.path, forged)
        self.assertEqual(len(read(self.path)), 1)

    def test_time_cannot_run_backwards(self):
        entries = month_series(2)
        create_ledger(self.path, entries[0])
        backwards = replace(entries[1], asof=entries[0].asof)
        with self.assertRaises(ValueError):
            append(self.path, backwards)

    def test_a_plan_cannot_be_dated_after_the_interval_it_plans(self):
        base = month_series(1)[0]
        with self.assertRaises(ValueError):
            replace(base, plan_posted_on=base.asof + timedelta(days=5))

    def test_hash_is_independent_of_quote_ordering(self):
        base = month_series(1)[0]
        first = replace(base, quotes=(Quote("QQQ", 200.0), Quote("SPY", 100.0)))
        second = replace(base, quotes=(Quote("SPY", 100.0), Quote("QQQ", 200.0)))
        self.assertEqual(entry_hash(first), entry_hash(second))

    def test_an_entry_owing_more_than_it_holds_is_refused(self):
        base = month_series(1)[0]
        with self.assertRaises(ValueError):
            replace(base, invested=base.opening_value + base.cash_arrived + 1.0)


class ComparatorArithmetic(unittest.TestCase):
    def test_weights_must_be_a_single_full_portfolio(self):
        with self.assertRaises(ValueError):
            Comparator("half of nothing", {SPY: 0.5}, 0.0)

    def test_the_path_matches_the_unrolled_recurrence(self):
        """The benchmark has to equal arithmetic, to the cent, on a hand-built path."""

        entries = month_series(13, growth=0.01, contribution=500.0, opening=5_000.0)
        self.assertAlmostEqual(
            comparator_path(entries, COMPARATOR),
            closed_form(13, 0.01, 500.0, 5_000.0),
            places=6,
        )

    def test_a_flat_path_grows_by_contributions_alone(self):
        entries = month_series(13, growth=0.0, contribution=500.0, opening=5_000.0)
        self.assertAlmostEqual(comparator_path(entries, COMPARATOR), 5_000.0 + 12 * 500.0, places=6)
        irr = comparator_return(entries, COMPARATOR, entries[0].opening_value, entries[-1].asof)
        self.assertAlmostEqual(irr, 0.0, places=9)

    def test_a_steady_one_percent_month_has_an_exact_annualised_answer(self):
        """1% per 30 days is 1.01**(365.2425/30) - 1. No calibration, no tolerance fudge."""

        entries = month_series(14, growth=0.01, fee=0.0)
        expected = 1.01 ** (365.2425 / 30) - 1.0
        irr = comparator_return(entries, COMPARATOR, entries[0].opening_value, entries[-1].asof)
        self.assertLess(abs(irr - expected), 1e-9, (irr, expected))

    def test_the_expense_ratio_is_the_only_gap_when_nothing_else_leaks(self):
        cheap = Comparator("cheap", {SPY: 1.0}, 0.0003)
        rich = Comparator("rich", {SPY: 1.0}, 0.0043)
        entries = month_series(14, growth=0.01)
        end = entries[-1].asof
        gap = (
            comparator_return(entries, cheap, entries[0].opening_value, end)
            - comparator_return(entries, rich, entries[0].opening_value, end)
        ) * 10_000.0
        # The gap is larger than the 40 bps of nominal fee difference, and that is
        # arithmetic rather than accident: a level gap that compounds over fourteen
        # intervals annualises to more than the nominal. Same reason a 42 bps fund
        # is not 42 bps of shortfall. Bound it, and do not pretend it is 40.
        self.assertGreater(gap, 40.0, gap)
        self.assertLess(gap, 46.0, gap)

    def test_a_comparator_that_the_journal_does_not_price_is_an_error(self):
        entries = month_series(3)
        gold = Comparator("unpriced", {"XAU": 1.0}, 0.0)
        with self.assertRaises(ValueError):
            comparator_path(entries, gold)

    def test_the_account_and_the_comparator_share_one_convention(self):
        """Identical closing values must give identical returns, exactly."""

        entries = month_series(14, growth=0.01)
        end = entries[-1].asof
        mine = account_return(entries, end)
        theirs = comparator_return(entries, COMPARATOR, entries[0].opening_value, end)
        self.assertAlmostEqual(mine, theirs, places=10)

    def test_deposits_are_dated_at_the_interval_open_not_the_report_close(self):
        entries = month_series(4)
        flows = comparator_flows(entries)
        self.assertEqual(len(flows), 3)
        self.assertEqual(flows[0].date, entries[0].asof)
        self.assertEqual(flows[1].date, entries[1].asof)


class LayerOneIsAlwaysDecisive(unittest.TestCase):
    def test_a_ten_dollar_monthly_fee_is_flagged_as_material(self):
        """The BA-004 lesson, encoded: fixed-dollar fees dwarf every bps budget."""

        entries = month_series(12, growth=0.005, fee=10.0)
        fees = [f for f in measure(entries) if f.kind == "fees"]
        self.assertEqual(len(fees), 1)
        self.assertGreater(fees[0].magnitude_bps, 100.0, fees[0])

    def test_a_clean_interval_produces_no_findings(self):
        self.assertEqual(measure(month_series(3)), ())

    def test_a_declared_violation_is_carried_with_its_entry(self):
        entries = month_series(2)
        flagged = replace(entries[1], violations=("sold during the decline",))
        found = [f for f in measure((entries[0], flagged)) if f.kind == "violation"]
        self.assertEqual(len(found), 1)
        self.assertIn("sold during the decline", found[0].detail)

    def test_idle_cash_is_reported_whether_or_not_it_cost_anything(self):
        entries = month_series(6, growth=0.0, days=20)
        kinds = {f.kind for f in measure(entries)}
        self.assertIn("idle cash", kinds)


class SkillVerdictIsGated(unittest.TestCase):
    def test_fewer_than_the_minimum_entries_cannot_produce_a_number(self):
        report = verdict(month_series(6, growth=0.02), COMPARATOR, date(2027, 6, 8))
        self.assertIsNone(report.shortfall_bps)
        self.assertIn("underpowered", report.skill)
        self.assertIn("more monthly entries", report.skill)

    def test_enough_months_but_too_little_money_still_withholds(self):
        entries = month_series(26, growth=0.02)
        paid_in = entries[0].opening_value + sum(e.cash_arrived for e in entries)
        report = verdict(entries, COMPARATOR, entries[-1].asof, min_paid_in=paid_in + 1.0)
        self.assertIsNone(report.shortfall_bps)
        self.assertIn("more paid in", report.skill)

    def test_once_gated_it_reports_a_signed_shortfall(self):
        entries = month_series(26, growth=0.02, contribution=900.0, opening=9_000.0)
        rich = Comparator("rich", {SPY: 1.0}, 0.0100)
        report = verdict(entries, rich, entries[-1].asof, min_paid_in=0.0)
        self.assertIsNotNone(report.shortfall_bps)
        self.assertGreater(report.shortfall_bps, 0.0)
        self.assertIn("beat", report.skill)

    def test_the_default_gate_is_two_years(self):
        self.assertEqual(MIN_ENTRIES_FOR_SKILL_VERDICT, 24)

    def test_fees_are_totalled_regardless_of_the_skill_gate(self):
        report = verdict(month_series(4, fee=9.99), COMPARATOR, date(2027, 3, 31))
        self.assertAlmostEqual(report.total_fees, 4 * 9.99)  # every entry reports its own
        self.assertIsNone(report.shortfall_bps)

    def test_verdict_on_an_empty_ledger_is_an_error_not_a_zero(self):
        with self.assertRaises(ValueError):
            verdict((), COMPARATOR, date(2027, 1, 31))


if __name__ == "__main__":
    unittest.main()
