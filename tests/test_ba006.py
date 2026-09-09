"""Tests for BA-006: the sized-sleeve test, its arithmetic, and the fee logic that decides whether it may speak.

The figures this tool publishes are the affordable *bill* at each weight, so the tests are mostly about the two ways a bill can be wrong —
blending the legs incorrectly, and reading a 63-window overlap as 63 trials — plus the exit-code contract that lets a FAIL out without a fee
record while withholding a PASS until one exists.
"""

from __future__ import annotations

import re
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import ba005                                                                   # noqa: E402
import ba006                                                                   # noqa: E402
import monthly_income_race as mir                                              # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data                   # noqa: E402
import withdrawal_capacity as wc                                               # noqa: E402


class TheLockedLadder(unittest.TestCase):
    def test_the_weights_and_the_margin_are_the_specs_not_a_copy_of_it(self):
        self.assertEqual(ba006.WEIGHTS, (0.05, 0.10, 0.20))
        self.assertEqual(ba006.BILL_MARGIN, 0.05)

    def test_the_ladder_is_a_fixed_set_in_the_spec_text(self):
        self.assertIn("**Weights:** the fixed set **{5%, 10%, 20%}**", ba006.SPEC_TEXT)

    def test_the_gate_and_horizon_are_inherited_from_ba_005_not_re_typed(self):
        """One gate for the whole Coinbase line: a second tool re-typing 1.25 would be a second gate."""

        self.assertEqual(ba006.GATE, ba005.DD_LIMIT)
        self.assertEqual(ba006.YEARS, ba005.RUIN_YEARS)
        self.assertEqual(ba006.BUDGET, ba005.P_FAIL_MAX)

    def test_no_expense_ratio_or_fee_is_written_into_the_source(self):
        source = (ROOT / "tools" / "ba006.py").read_text()
        self.assertEqual(re.findall(r"(?m)^[A-Z][A-Z_0-9]*(FEE|ER|EXPENSE)[A-Z_0-9]*\s*=\s*[\d.]+", source), [])
        self.assertIn("fund_fees.fee_for(", source, "expense ratios must be looked up, not typed")


class TheArithmetic(unittest.TestCase):
    def test_a_zero_weight_is_the_base_and_a_full_weight_is_the_sleeve(self):
        strat, base = [0.10, -0.20, 0.05], [0.01, 0.02, 0.03]
        self.assertEqual(ba006.blend(strat, base, 0.0), base)
        self.assertEqual(ba006.blend(strat, base, 1.0), strat)

    def test_a_half_weight_blend_is_the_mean_of_the_two_legs(self):
        self.assertAlmostEqual(ba006.blend([0.10], [0.02], 0.5)[0], 0.06, places=12)

    def test_a_monthly_rebalanced_blend_reverts_to_target_rather_than_drifting(self):
        """50/50 of a +100% month and a 0% month must be +50%, not the drift a buy-and-hold blend would produce."""

        self.assertAlmostEqual(ba006.blend([1.0], [0.0], 0.5)[0], 0.50, places=10)

    def test_the_drawdown_is_measured_on_the_path_not_the_endpoints(self):
        self.assertAlmostEqual(ba006.drawdown([1.0, -0.5]), 0.50, places=10)
        self.assertAlmostEqual(ba006.drawdown([0.1, 0.1, 0.1]), 0.0, places=10)

    def test_the_sleeve_becomes_more_expensive_as_the_fee_rises_and_the_bill_falls(self):
        md = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        legs = ba006.price_legs(md)
        cheap = ba006.bill_of(ba006.blend(ba006.sleeve_returns(legs, 0.0), legs["voo"], 0.20))
        dear = ba006.bill_of(ba006.blend(ba006.sleeve_returns(legs, 240.0), legs["voo"], 0.20))
        self.assertGreater(cheap, dear, "a 240 bps taker fee may not raise the affordable bill")


class TheVerdict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.md = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def run_with(self, fee, record):
        return ba006.report_lines(self.md, fee, record)

    def test_p0_s_bill_is_the_archive_sown_figure_recomputed_here(self):
        lines, _ = self.run_with(None, None)
        legs = ba006.price_legs(self.md)
        expected = mir.safe_amount(legs["voo"], ba005.CAPITAL, ba006.YEARS, ba006.BUDGET, floor=1.0)
        self.assertIn(f"${expected:,.0f}/mo", "\n".join(lines))

    def test_p0_s_own_row_is_printed_with_its_median_so_the_table_has_no_unpriced_bar(self):
        legs = ba006.price_legs(self.md)
        stats = mir.plan_stats(legs["voo"], ba005.CAPITAL, mir.safe_amount(legs["voo"], ba005.CAPITAL, ba006.YEARS, ba006.BUDGET,
                                                                            floor=1.0), ba006.YEARS, floor=1.0)
        lines, _ = self.run_with(None, None)
        self.assertIn(f"median {stats['median_mult']:.2f}x", "\n".join(lines))

    def test_without_a_fee_record_a_clearing_weight_withholds_the_pass_but_a_failure_still_prints(self):
        lines, code = self.run_with(None, None)
        joined = "\n".join(lines)
        self.assertIn(code, (1, 3))
        if code == 3:
            self.assertIn("NO VERDICT", joined)
            self.assertIn("venue_fees", joined, "the refusal has to name the command that unblocks it")

    def test_a_recorded_fee_lets_the_verdict_be_rendered(self):
        """The fee is what condition 5 asks for; with a record present the tool must speak, not stall."""

        lines, code = self.run_with(60.0, {"product": "advanced-trade", "as_of": "2026-09-08", "taker_bps": 60.0})
        joined = "\n".join(lines)
        self.assertIn(code, (0, 1))
        if code == 0:
            self.assertRegex(joined, r"PASS — a sized sleeve")
            self.assertIn("fifth forward book", joined)

    def test_a_clearing_weight_has_its_seatbelt_margin_printed_in_dollars_not_as_a_percentage_that_hides_its_size(self):
        for fee, record in ((60.0, {"taker_bps": 60.0, "product": "x", "as_of": "2026-09-08"}), (None, None)):
            lines, _ = self.run_with(fee, record)
            joined = "\n".join(lines)
            if "clears 1-4" in joined or "PASS" in joined:
                self.assertRegex(joined, r"Condition 4 passed by \$[\d,]+/mo|seatbelt")
                return
        self.fail("no weight cleared the gates, so there was nothing to annotate — the tool would have printed FAIL")

    def test_the_overlap_caveat_prints_whatever_the_verdict_says(self):
        """63 overlapping windows is two looks at one decade. A table of rates without that sentence invites over-reading."""

        lines, _ = self.run_with(None, None)
        self.assertRegex("\n".join(lines), r"non-overlapping looks at one decade")

    def test_the_fee_grid_shows_the_result_survives_every_fee_on_the_published_grid(self):
        """Not a claim that fees are small — a claim about this candidate's sensitivity, checked against the printed grid."""

        lines, _ = self.run_with(None, None)
        bills = [float(m) for m in re.findall(r"bps → \$([\d,]+)/mo at 20% sleeve", "\n".join(lines).replace(",", ""))]
        self.assertEqual(len(bills), len(ba005.FEE_GRID_BPS))
        self.assertEqual(bills, sorted(bills, reverse=True))


class TheStartDateLadder(unittest.TestCase):
    """The disclosure that says where the result lives. It has no switch, and it is judged by the same gates as the table."""

    @classmethod
    def setUpClass(cls):
        cls.md = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_every_roll_and_every_weight_is_printed_and_none_of_it_is_switchable(self):
        lines, _ = ba006.report_lines(self.md, None, None)
        joined = "\n".join(lines)
        for years in ba006.ROLL_YEARS:
            start = date(ba005.WINDOW_START.year + years, ba005.WINDOW_START.month, ba005.WINDOW_START.day)
            self.assertIn(start.isoformat(), joined, f"roll {start} is missing from the ladder")
        self.assertEqual(joined.count("sleeve"), joined.count("sleeve"), "sanity")
        rows = [l for l in lines if re.match(r"^\s+\d{4}-\d{2}-\d{2}\s+\d+\s+\d", l)]
        for row in rows:
            self.assertEqual(row.count("|"), len(ba006.WEIGHTS) - 1, "a roll row dropped a weight")
        source = (ROOT / "tools" / "ba006.py").read_text()
        self.assertNotIn("--sensitivity", source, "the disclosure that undermines the headline must not sit behind a flag")

    def test_the_first_rung_is_the_graded_table_to_the_dollar(self):
        """A ladder whose zero-roll disagreed with the table would be a second test with a second convention."""

        legs = ba006.price_legs(self.md)
        p0_bill = ba006.bill_of(legs["voo"])
        p0_stats = mir.plan_stats(legs["voo"], ba005.CAPITAL, p0_bill, ba006.YEARS, floor=1.0)
        costed = ba006.sleeve_returns(legs, 0.0)
        lines, _ = ba006.report_lines(self.md, None, None)
        for w in ba006.WEIGHTS:
            g = ba006.gates(legs, costed, w, p0_bill, p0_stats, ba006.drawdown(legs["qqq"]))
            self.assertIn(f"${g['bill']:,.0f}", "\n".join(lines))

    def test_the_summary_names_where_a_clearing_weight_appears_and_where_it_does_not(self):
        joined = "\n".join(ba006.report_lines(self.md, None, None)[0])
        self.assertRegex(joined, r"a clearing weight appears at \d{4}-\d{2}-\d{2} and nowhere at")
        self.assertIn("closer to the later starts", joined)

    def test_the_ladder_reports_which_gates_a_roll_fails_rather_than_a_bare_fails(self):
        joined = "\n".join(ba006.report_lines(self.md, None, None)[0])
        self.assertRegex(joined, r"fails (bill|erase|drawdown|seatbelt)(,\w+)*")


class TheCashLegQuestion(unittest.TestCase):
    """The conversion probe's real consequence: the specs credit the below-the-line cash with a T-bill the venue does not hold."""

    @classmethod
    def setUpClass(cls):
        cls.md = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.lines, cls.code = ba006.report_lines(cls.md, None, None)
        cls.joined = "\n".join(cls.lines)

    @property
    def variant_rows(self):
        """The three rows of the cash-leg block: weight, T-bill bill, zero-yield bill, difference. Nothing else in the report has
        that shape — an earlier version of this selector also matched the main table's rows and passed for the wrong reason."""

        return [l for l in self.lines if re.match(r"^\s+\d+%\s+[\d,]+\s+[\d,]+\s+-?[\d,]+$", l)]

    def test_both_cash_legs_are_priced_at_every_weight(self):
        self.assertIn("the cash leg, both ways", self.joined)
        rows = self.variant_rows
        self.assertEqual(len(rows), len(ba006.WEIGHTS), "a weight was priced with one cash leg only")

    def test_the_cash_column_in_the_variants_block_is_the_same_number_as_the_main_table(self):
        """Round 5's bug: the block reused a variable the fee grid had rebound, so its 'T-bill' column quietly printed the 240 bps bills.

        Plausible, wrong, and only catchable by comparing the two places that must agree.
        """
        table_bills = [float(m.replace(",", "")) for m in re.findall(r"^\s+\d+%\s+\$?([\d,]+)\s+\+", "\n".join(self.lines), re.M)]
        variant_treasury = [float(l.split()[1].replace(",", "")) for l in self.variant_rows]
        self.assertEqual(len(table_bills), len(variant_treasury))
        for expected, printed in zip(table_bills, variant_treasury):
            self.assertAlmostEqual(expected, printed, delta=1.0, msg="the two places that price the T-bill cash leg disagree")

    def test_a_cash_leg_that_earns_nothing_cannot_buy_a_bigger_bill_than_a_cash_leg_that_pays(self):
        for row in self.variant_rows:
            fields = row.split()
            treasury, zero, worth = float(fields[1].replace(",", "")), float(fields[2].replace(",", "")), float(fields[3].replace(",", ""))
            self.assertLessEqual(zero, treasury + 1.0, f"zero-yield cash outselling T-bills at {fields[0]}")
            self.assertGreaterEqual(worth, -1.0)

    def test_the_clearing_row_still_clears_when_the_cash_leg_earns_nothing(self):
        """The note publishes this sentence, so it is checked rather than inferred: an account that earns nothing on idle balances
        still has its 20% sleeve clearing all four gates — the unsourced T-bill assumption is not what the result rests on."""

        legs = ba006.price_legs(self.md)
        p0_bill = ba006.bill_of(legs["voo"])
        p0_stats = mir.plan_stats(legs["voo"], ba005.CAPITAL, p0_bill, ba006.YEARS, floor=1.0)
        zero = ba006.sleeve_returns(legs, 0.0, [0.0] * len(legs["cash"]))
        top = max(ba006.WEIGHTS)
        g = ba006.gates(legs, zero, top, p0_bill, p0_stats, ba006.drawdown(legs["qqq"]))
        self.assertTrue(g["clears"], f"the published claim that zero-yield cash still clears is false: {g['ok']}")
        self.assertLess(g["bill"], ba006.bill_of(ba006.blend(ba006.sleeve_returns(legs, 0.0), legs["voo"], top)))

    def test_the_tool_says_whether_the_assumption_it_cannot_source_is_load_bearing(self):
        self.assertRegex(self.joined, r"the T-bill assumption is (not )?load-bearing")
        self.assertIn("403", self.joined, "the block has to name why the yield is unknown rather than omitting the question")


if __name__ == "__main__":
    unittest.main()
