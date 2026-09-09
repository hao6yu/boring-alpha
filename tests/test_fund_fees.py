"""The expense table is one file, its numbers have sources, and no other tool is allowed a copy of them.

`tools/fund_fees.py` exists because round 94 found four files in this repository stating the same eight facts four ways: the
engine charged seven legs a flat 0.35%, the comparator battery had four of eight legs wrong, the cross-sectional scanner was three
basis points off on one fund after being right about the rest, and `withdrawal_capacity.py` posted five and refused the others. A
wrong fee is not a rounding matter here: round 83 measured the whole 50/50 book's rebalancing bill at 0.054% of paid in over
sixteen years, and the battery's TLT line alone was 33 bps a year wrong. These tests are the reason the copies cannot come back.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import fund_fees as ff                                   # noqa: E402
import paper                                             # noqa: E402

TOOLS = sorted((ROOT / "tools").glob("*.py"))
TICKERS = "|".join(sorted(ff.RATIOS))


class TheTableItself(unittest.TestCase):
    def test_every_leg_the_archive_quotes_has_a_ratio_with_a_source_and_a_date(self):
        self.assertEqual(set(ff.RATIOS), set(ff.POSTED_FIVE) | set(ff.FORMERLY_GUESSED))
        self.assertRegex(ff.RETRIEVED, r"^\d{4}-\d{2}-\d{2}$")
        for symbol, (ratio, issuer, note) in ff.RATIOS.items():
            self.assertGreater(ratio, 0.0, symbol)
            self.assertLess(ratio, 0.01, f"{symbol} is not an expense ratio")
            self.assertTrue(issuer, symbol)
            self.assertTrue(note, symbol)
            self.assertIn("{ticker}", ff.SOURCE)

    def test_the_five_ratios_sealed_chains_are_priced_with_have_not_moved(self):
        """The immutability constraint, stated as a test: a book's history is comparable with itself only if its fund's fee
        never changed under it."""

        sealed_before = {"SPY": 0.000945, "VOO": 0.0003, "VTI": 0.0003, "ITOT": 0.0003, "QQQ": 0.0020}
        for symbol, ratio in sealed_before.items():
            self.assertAlmostEqual(ff.fee_for(symbol), ratio, delta=1e-12, msg=symbol)

    def test_the_guess_was_pessimistic_on_some_legs_and_optimistic_on_others_and_says_so(self):
        """Not a nicety: the guess's own comment claimed it was 'deliberately the pessimistic direction', and three of seven
        legs were cheaper than published, which is the direction that flatters a holding."""

        harsher = [s for s in ff.FORMERLY_GUESSED if ff.correction(s) > 0]
        kinder = [s for s in ff.FORMERLY_GUESSED if ff.correction(s) < 0]
        self.assertTrue(harsher and kinder, "a uniform guess in one direction would at least have been honest")
        self.assertIn("IEF", harsher)
        self.assertIn("DBC", kinder)
        self.assertLess(ff.correction("DBC"), -0.004, "DBC was undercharged by nearly fifty basis points")

    def test_the_cheapest_and_dearest_legs_are_what_the_benchmarks_are_chosen_for(self):
        cheapest = min(ff.FEES.values())
        self.assertEqual(ff.fee_for("VOO"), cheapest)
        self.assertEqual(ff.fee_for("DBC"), max(ff.FEES.values()))
        self.assertGreater(ff.fee_for("DBC") / cheapest, 25.0,
                           "the spread across this universe is the reason an equal-weight basket is not free")

    def test_a_symbol_with_no_source_falls_back_to_the_guess_rather_than_to_zero(self):
        self.assertEqual(ff.fee_for("XLU"), ff.GUESS)
        self.assertFalse(ff.priced("XLU"))


class NobodyMayKeepACopy(unittest.TestCase):
    """The regression this file exists to prevent: four files, four answers, one fact."""

    def test_the_engine_charges_the_table_not_its_own_numbers(self):
        for symbol, ratio in ff.FEES.items():
            self.assertAlmostEqual(paper.fee_for(symbol), ratio, places=12, msg=symbol)
        self.assertEqual(set(paper.POSTED), set(ff.RATIOS), "every sourced ratio may witness")

    def test_the_research_consumers_import_the_table_and_do_not_retype_it(self):
        import cross_section as cs
        import run_comparator_battery as rb
        import withdrawal_capacity as wc
        for symbol, ratio in ff.FEES.items():
            self.assertAlmostEqual(cs.EXPENSE[symbol], ratio, places=12, msg=symbol)
        for symbol, ratio in rb.EXPENSE.items():
            self.assertAlmostEqual(ratio, ff.fee_for(symbol), places=12, msg=symbol)
        for symbol, ratio in wc.EXPENSE.items():
            self.assertAlmostEqual(ratio, ff.fee_for(symbol), places=12, msg=symbol)
        self.assertEqual(set(wc.EXPENSE), set(ff.POSTED_FIVE),
                         "withdrawal_capacity's short list is a decision about what it grades, not a missing fee")

    def test_no_tool_outside_this_table_maps_a_ticker_to_a_fee(self):
        """Weight maps may name tickers — `{"SPY": 0.5, "QQQ": 0.5}` is an allocation, not a cost — so the scan keys on the
        shape of the number as well as the key: a fee in this repository is a positive ratio below two percent."""

        pattern = re.compile(rf"['\"]({TICKERS})['\"]\s*:\s*(0\.\d+)")   # a fee here is a positive ratio under 2%; weights are 0.0/0.5/1.0 and are not costs
        offenders = []
        for path in TOOLS:
            if path.name == "fund_fees.py":
                continue
            for line in path.read_text().splitlines():
                for match in pattern.finditer(line):
                    if 0.0 < float(match[2]) < 0.02 and "fund_fees" not in line:
                        offenders.append(f"{path.name}: {line.strip()[:70]}")
                        break
        self.assertEqual(offenders, [], f"a hand-copied fee came back: {offenders[:4]}")

    def test_the_battery_no_longer_understates_the_two_legs_it_used_to_flatter(self):
        """The battery's comment said an error here only hurts if it is too low — and it understated EEM and DBC."""

        self.assertGreater(ff.fee_for("EEM"), 0.0032)
        self.assertGreater(ff.fee_for("DBC"), 0.0065)
        self.assertLess(ff.fee_for("TLT"), 0.0048)
        self.assertLess(ff.fee_for("IEF"), 0.0038)


class TheScreenAgreesWithTheTable(unittest.TestCase):
    def run_screen(self, argv):
        import contextlib
        import io
        saved, sys.argv = sys.argv, argv
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = ff.main()
        finally:
            sys.argv = saved
        return code, out.getvalue()

    def test_it_prints_both_directions_of_the_correction(self):
        code, text = self.run_screen(["fund_fees.py"])
        self.assertEqual(code, 0)
        self.assertIn("undercharged", text)
        self.assertIn("overcharged", text)
        self.assertIn("false of three", text)

    def test_the_json_carries_the_ratios_and_the_date(self):
        _code, text = self.run_screen(["fund_fees.py", "--json"])
        payload = json.loads(text)
        self.assertEqual(payload["retrieved"], ff.RETRIEVED)
        self.assertEqual(payload["fees"]["DBC"], 0.0084)
        self.assertAlmostEqual(payload["correction"]["IEF"], 0.0020, delta=1e-12)


ASSIGNMENT = re.compile(r"\b([A-Z]{2,6})_ER\b[^=]*=\s*(0\.\d{3,})")
#: Round 104 widened the net: `run_voltarget_scan.py` had been holding `EXPENSE = 0.000945`, which is SPY's ratio under a
#: different name and matches no `_ER` pattern. Any upper-case constant whose name mentions a fee, holding a bare ratio, is a
#: candidate copy — the name is the claim, and the claim is that this file knows what a fund costs.
FEE_LITERAL = re.compile(r"^([A-Z][A-Z_0-9]*(?:EXPENSE|FEE|RATIO|TICKET)[A-Z_0-9]*)\s*=\s*(0\.\d{3,})\s*(?:#.*)?$")


def assignment_offenders(text: str, filename: str) -> list:
    """A ratio written as a bare constant is the same fact this file owns, wearing a different syntax.

    The round-94 scan looked for dict literals, which is where fees usually hide; `SGOV_ER, BIL_ER = 0.0009, 0.0014` in
    `cash_yield_gap.py` slipped past it for four rounds. This scan keys on an uppercase name ending in `_ER` holding a
    ratio-shaped number, which is how a fee hides when it is not in a table.
    """

    out = []
    for line in text.splitlines():
        for match in ASSIGNMENT.finditer(line):
            if match.group(1) in ff.CASH_FUNDS or match.group(1) in ff.RATIOS:
                if "fund_fees" not in line:
                    out.append(f"{filename}: {line.strip()[:70]}")
    return out


class TheCashLegs(unittest.TestCase):
    """Round 99 added the two funds a cash sleeve would use, and the distinction between priced and tradeable."""

    def test_a_bill_fund_is_priced_rather_than_guessed(self):
        self.assertAlmostEqual(ff.fee_for("SGOV"), 0.0009, places=12)
        self.assertAlmostEqual(ff.fee_for("BIL"), 0.0014, places=12)
        self.assertNotEqual(ff.fee_for("SGOV"), ff.GUESS, "the 0.35% guess would have misstated the bill leg by 26 bps")

    def test_a_bill_fund_is_not_a_sleeve_and_says_which_it_is(self):
        for symbol in ff.CASH_FUNDS:
            self.assertNotIn(symbol, ff.RATIOS, f"{symbol} would become scoreable if it joined RATIOS")
            self.assertNotIn(symbol, ff.FEES)
            self.assertTrue(ff.priced(symbol))
            with self.assertRaises(SystemExit) as caught:
                paper.posted_fee(symbol)
            self.assertIn("not a traded leg", str(caught.exception))

    def test_an_unpriced_symbol_still_gets_the_old_refusal(self):
        with self.assertRaises(SystemExit) as caught:
            paper.posted_fee("XLU")
        self.assertIn("no posted expense ratio", str(caught.exception))

    def test_the_sweep_ratios_are_imported_where_they_were_once_written(self):
        import cash_yield_gap as cy
        self.assertAlmostEqual(cy.SGOV_ER, ff.fee_for("SGOV"), places=12)
        self.assertAlmostEqual(cy.BIL_ER, ff.fee_for("BIL"), places=12)

    def test_a_fee_named_constant_holds_a_sourced_ratio_or_declares_itself_an_assumption(self):
        """Round 104's widening of the same rule: `run_voltarget_scan.py` carried `EXPENSE = 0.000945`, which is SPY's posted
        ratio under a name no `_ER` pattern would ever catch, and `leverage_sizing.py` and `withdrawal_capacity.py` each typed
        0.90% for a leveraged fund's expense ratio — the same assumption, twice.

        A constant whose *name* claims to know what a fund charges may hold the table's value or a single declared assumption.
        Anything else is a copy, and the allow-list is where an assumption has to state itself to survive.
        """

        allowed = {"withdrawal_capacity.py": "the leveraged-fund expense ratio, an assumption stated once and labelled"}
        offenders = []
        for path in sorted((ROOT / "tools").glob("*.py")):
            if path.name == "fund_fees.py":
                continue
            for no, line in enumerate(path.read_text().splitlines(), 1):
                m = FEE_LITERAL.match(line)
                if m and path.name not in allowed:
                    offenders.append(f"{path.name}:{no} {m.group(1)} = {m.group(2)}")
        self.assertEqual(offenders, [], f"fee-named literals with no table under them: {offenders}")
        self.assertIn("WRAPPER_EXPENSE", (ROOT / "tools" / "withdrawal_capacity.py").read_text())

    def test_no_tool_restates_a_ratio_as_a_bare_constant(self):
        offenders = []
        for path in TOOLS:
            if path.name == "fund_fees.py":
                continue
            offenders += assignment_offenders(path.read_text(), path.name)
        self.assertEqual(offenders, [], f"a fee is written down twice: {offenders[:4]}")

    def test_the_scan_fires_on_the_copy_it_exists_to_catch(self):
        """r93: a check needs a negative test. This is the line that hid for four rounds."""

        caught = assignment_offenders("SGOV_ER, BIL_ER = 0.0009, 0.0014\n", "some_tool.py")
        self.assertEqual(len(caught), 1, "the scan is not looking at what it claims to look at")
        self.assertIn("some_tool.py", caught[0])


class EveryAccessorAgrees(unittest.TestCase):
    """Round 103's generalisation of round 94: a fact sourced once is only sourced once if every accessor returns it.

    Five files had their own answer to "what does this fund charge" — a literal dict, a graded-universe comprehension, a gate, a
    refusal list, and a `else FLAT_FEE` fallback keyed on the *scope list of a different tool* (r103). Scanning for copies of the
    numbers was not enough, because the copy that survives is the copy of the *universe*. This test checks behaviour through each
    accessor instead, and checks that a fallback is unreachable where one remains.
    """

    def test_every_fee_accessor_returns_the_table_s_ratio_for_every_leg_it_can_name(self):
        import cross_section as cx                                      # noqa: PLC0415
        import rotation_search as rse                                   # noqa: PLC0415
        import withdrawal_capacity as wc                                # noqa: E402
        seen = set()
        for sym, val in paper.FEES.items():
            self.assertEqual(val, ff.fee_for(sym), f"paper.FEES still holds its own answer for {sym}")
            seen.add(sym)
        for sym, val in cx.EXPENSE.items():
            self.assertEqual(val, ff.fee_for(sym), f"cross_section.EXPENSE still holds its own answer for {sym}")
            seen.add(sym)
        for sym, val in wc.EXPENSE.items():
            self.assertEqual(val, ff.fee_for(sym), f"withdrawal_capacity.EXPENSE disagrees for {sym}")
            seen.add(sym)
        for sym in rse.RISK + (rse.SHELTER,):
            self.assertEqual(rse.fee(sym), ff.fee_for(sym), f"rotation_search charged {sym} something else")
            seen.add(sym)
        self.assertEqual(seen, set(ff.RATIOS), "a priced leg was never checked by any accessor")

    def test_where_a_guess_default_remains_it_cannot_be_reached_by_the_universe_being_scored(self):
        """`power_horizon.simulate` charges `paper.UNPOSTED_FEE` for a symbol missing from its fee map. That is only honest while
        the map always covers the book it scores — and 'while' is a claim, so it is pinned instead of trusted."""

        import combined_account as ca                                   # noqa: PLC0415
        import power_horizon as ph                                      # noqa: PLC0415
        import withdrawal_capacity as wc                                # noqa: E402
        for sym in tuple(ph.BOOK) + (ph.WITNESS,):
            self.assertTrue(ff.priced(sym), f"{sym} is in the scored book and would be charged the guess")
        self.assertIn(ca.SYMBOL, wc.EXPENSE, f"{ca.SYMBOL} is subscripted out of a five-fund table")


if __name__ == "__main__":
    unittest.main()
