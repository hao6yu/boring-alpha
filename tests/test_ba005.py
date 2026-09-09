"""Tests for BA-005's runner: the fee arithmetic, the spec's own locked numbers, and the verdict the fee cannot change.

The rule under test is not interesting to these tests — what is tested is that the *locked* numbers are the numbers used, that a fee is
charged exactly once per switch and nowhere else, and that a gate which fails at a fee of zero is reported as a failure rather than
postponed behind the missing fee record.
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
from boring_alpha.data.csv_loader import load_csv_market_data                   # noqa: E402
import withdrawal_capacity as wc                                               # noqa: E402


class TheLockedNumbers(unittest.TestCase):
    """Every constant the runner prices with is parsed out of the locked spec, so a re-lock cannot silently move it."""

    def test_the_window_the_average_and_the_instrument_come_from_the_spec(self):
        self.assertEqual(ba005.WINDOW_START, date(2016, 5, 18))
        self.assertEqual(ba005.SMA_DAYS, 200)
        self.assertEqual(ba005.PAIR, "BTC-USD")
        self.assertEqual(ba005.DD_LIMIT, 1.25)

    def test_the_window_is_the_one_the_spec_text_states(self):
        text = ba005.SPEC.read_text()
        self.assertIn("**Window**: 2016-05-18", text, "the spec no longer states the window the runner parses")

    def test_the_runner_owns_no_fee_of_its_own(self):
        """The grid is a set of hypotheticals. Nothing in the file may be *the* fee: that lives in the venue record or nowhere."""

        source = (ROOT / "tools" / "ba005.py").read_text()
        offenders = re.findall(r"(?m)^[A-Z][A-Z_0-9]*FEE[A-Z_0-9]*\s*=\s*[\d.]+", source)
        self.assertEqual(offenders, [], f"a fee constant crept into the runner: {offenders}")


class AFeeThatIsChargedOnce(unittest.TestCase):
    """A hand-built path where the arithmetic is checkable by hand: 12 months, one asset that rises 10% a month, cash at zero."""

    def setUp(self):
        self.months = [date(2020, m, 29) for m in range(1, 13)]
        # A sawtooth: up for four months, down for four, up for four — a 200-day mean is impossible here, so the signal is driven
        # directly by `above_sma` with a short span.
        self.btc = {}
        price = 100.0
        for i, month in enumerate(self.months):
            price *= 1.10 if (i // 4) % 2 == 0 else 0.90
            self.btc[month] = price
        self.cash = [0.0] * len(self.months)

    def signal_of(self, span):
        return [ba005.above_sma(self.btc, m, span) for m in self.months]

    def test_a_short_record_is_silence_not_a_sell_signal(self):
        self.assertFalse(ba005.above_sma(self.btc, self.months[0], span=200), "not enough history is not a bearish reading")

    def test_each_switch_costs_exactly_one_fee_on_the_sleeve(self):
        """Two switches at 1% must leave (1-0.01)^2 of the fee-free terminal — not (1-0.02)^2, and not one fee for the round trip."""

        gross = ba005.run(self.months[1:], self.btc, self.cash[1:], 0.0, [0.0] * 11, span=3)
        net = ba005.run(self.months[1:], self.btc, self.cash[1:], 100.0, [0.0] * 11, span=3)
        self.assertEqual(gross["switches"], net["switches"])
        self.assertGreater(gross["switches"], 0, "the fixture never switches, so it cannot test the fee")
        expected = gross["terminal"] * (1.0 - 0.01) ** gross["switches"]
        self.assertAlmostEqual(net["terminal"], expected, places=6)

    def test_the_fee_paid_is_reported_and_it_is_not_the_whole_cost_story(self):
        net = ba005.run(self.months[1:], self.btc, self.cash[1:], 100.0, [0.0] * 11, span=3)
        self.assertAlmostEqual(net["fees_paid"] / ba005.CAPITAL, 1.0 - (1.0 - 0.01) ** net["switches"], places=8)

    def test_the_break_even_fee_reproduces_the_bar_when_it_is_charged(self):
        gross = ba005.run(self.months[1:], self.btc, self.cash[1:], 0.0, [0.0] * 11, span=3)
        bar = gross["terminal"] * 0.5
        bps = ba005.breakeven_fee(gross["terminal"], bar, gross["switches"])
        self.assertIsNotNone(bps)
        net = ba005.run(self.months[1:], self.btc, self.cash[1:], bps, [0.0] * 11, span=3)
        self.assertAlmostEqual(net["terminal"], bar, places=2)

    def test_a_rule_behind_the_bar_has_no_break_even_fee_to_dream_about(self):
        self.assertIsNone(ba005.breakeven_fee(100.0, 200.0, 10))
        self.assertIsNone(ba005.breakeven_fee(300.0, 200.0, 0), "a rule that never trades has no fee sensitivity either")


class TheLiveRun(unittest.TestCase):
    """The archived corpus, priced once. Slow, but this is the number the note publishes."""

    @classmethod
    def setUpClass(cls):
        cls.md = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def lines(self, fee=None, record=None, quiet=True):
        """`report_lines` returns its output instead of printing it, precisely so this test needs no terminal capture."""

        lines, code = ba005.report_lines(self.md, fee, record, quiet=quiet)
        return code, lines

    def test_the_locked_window_produces_a_monthly_grid_and_no_warm_up_silence(self):
        months, returns, rates = ba005.grid(self.md, ba005.WINDOW_START)
        self.assertGreater(len(months), 100)
        self.assertEqual(len(months), len(returns))
        self.assertEqual(len(returns), len(rates))
        self.assertGreaterEqual(months[0], ba005.WINDOW_START)

    def test_without_a_fee_record_the_run_refuses_a_verdict_unless_the_fee_cannot_decide_it(self):
        code, text = self.lines(fee=None, record=None)
        joined = "\n".join(text)
        self.assertIn(code, (1, 3), "an undecidable fee exits 3; a gate the fee cannot move exits 1")
        if code == 3:
            self.assertIn("NO VERDICT", joined)
        else:
            self.assertIn("no fee record can change it", joined)

    def test_the_drawdown_gate_fails_and_the_failure_is_stated_without_a_fee(self):
        """This is the round's finding, so it is pinned: BTC's 200-day rule stays ahead of QQQ at any fee the venue could charge, and
        still fails the spec, because the gate was locked to drawdown rather than to the terminal."""

        code, text = self.lines(fee=None, record=None)
        joined = "\n".join(text)
        self.assertEqual(code, 1, "the drawdown gate fails at a fee of zero, so no fee record can rescue it")
        self.assertRegex(joined, r"FAIL, and no fee record can change it")
        self.assertIn("the ruin promise", joined, "the refusal has to say why the terminal is not the point")

    def test_the_grid_is_monotone_in_the_fee_because_a_fee_only_ever_takes_money_out(self):
        _, text = self.lines(fee=None, record=None, quiet=False)
        terminals = [float(l.split("$")[1].split()[0].replace(",", "")) for l in text if re.match(r"^\s+\d+\s+\$", l)]
        self.assertGreaterEqual(len(terminals), 5)
        self.assertEqual(terminals, sorted(terminals, reverse=True), "a higher taker fee may not raise the terminal")

    def test_the_fee_on_record_is_annotated_in_the_grid(self):
        _, text = self.lines(fee=60.0, record={"product": "advanced-trade", "as_of": "2026-09-08", "taker_bps": 60.0},
                             quiet=False)
        self.assertIn("the fee on record", "\n".join(text))

    def test_holding_the_asset_is_reported_next_to_timing_it(self):
        """The timing is only interesting against just holding the thing. If that line ever disappears, the +2.9% is invisible."""

        _, text = self.lines(fee=None, record=None)
        self.assertRegex("\n".join(text), r"simply holding the asset, no signal at all: \$[\d,]+")


class TheRuinPromise(unittest.TestCase):
    """Step 3's machinery: the bill is the archive's own, and the gate needs more than one window's worth of evidence."""

    @classmethod
    def setUpClass(cls):
        cls.md = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def setUp(self):
        self.months = [date(2015 + i // 12, i % 12 + 1, 28) for i in range(132)]
        self.bar = [0.006] * 131

    def _sections(self, ours_returns):
        months = self.months[1:]
        ours = {"returns": ours_returns}
        held = {"returns": ours_returns}
        return ba005.ruin_section(months, self.bar, ours, held, None, None)

    def test_a_rock_steady_series_can_afford_more_than_a_crashing_one(self):
        calm = self._sections([0.006] * 131)
        crashy = self._sections([0.006 if i % 24 != 23 else -0.45 for i in range(131)])
        self.assertGreater(calm["ours"]["median_mult"], crashy["ours"]["median_mult"])

    def test_the_gate_needs_the_pair_not_one_window_of_noise(self):
        """`ours_worse` fires only when the rule fails more often *and* is more often halved. A one-window difference in P(fail)
        on 64 windows is an artefact of resolution, and the tool says so out loud."""

        calm_against_calm = self._sections([0.006] * 131)
        self.assertFalse(calm_against_calm["ours_worse"], "identical paths cannot be a worse plan")
        crash = self._sections([-0.60 if i % 30 == 29 else 0.004 for i in range(131)])
        self.assertTrue(crash["ours_worse"], "a series that is halved every 30 months must not tie the bar on ruin")

    def test_the_ruin_gate_reports_itself_in_the_output_with_its_resolution(self):
        _, text = TheLiveRun_lines(self.md)
        joined = "\n".join(text)
        self.assertIn("ends whole", joined)
        self.assertIn("never reach zero", joined)
        self.assertRegex(joined, r"one window is [\d.]+ points")

    def test_the_bill_charged_is_the_archive_sown_not_a_copy_of_it(self):
        """The tool must price the ruin test at the number `monthly_income_race` produces for the same bar, computed here afresh."""

        import monthly_income_race as mir
        months, qqq_returns, _ = ba005.grid(self.md, ba005.WINDOW_START)
        expected = mir.safe_amount(qqq_returns, ba005.CAPITAL, ba005.RUIN_YEARS, ba005.P_FAIL_MAX, floor=1.0)
        _, text = TheLiveRun_lines(self.md)
        joined = "\n".join(text)
        self.assertIn(f"${expected:,.0f}/mo", joined, "the printed bill is not the archive's own affordable amount")


def TheLiveRun_lines(md):
    import ba005 as _b
    lines, code = _b.report_lines(md, None, None)
    return code, lines


if __name__ == "__main__":
    unittest.main()
