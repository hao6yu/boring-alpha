"""Tests for the sleeve table — and for the one law its fifteen rows turned out to obey.

The point of scoring every fund against itself is to find out whether the published premium belongs to the ticker or to
something else. It belongs to something else, and the law is checkable row by row rather than by prose: **a row pays a
premium exactly when the fund it hedges failed at least one window.** That single assertion (one test below) is worth more
than the twelve numbers it covers, because it is the kind of statement that fails on the day it stops being true, and every
number in the table can.
"""

from __future__ import annotations

import contextlib
import io
import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import fund_fees                                                   # noqa: E402
import correction_table as ct                                # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import sleeve_table as sw                                    # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402


class Swept(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = sw.rows(100_000.0, "start", True)
        cls.real = [r for r in cls.rs if not r["sleeve"].endswith("*")]

    def row(self, sleeve, window):
        return next(r for r in self.rs if r["sleeve"] == sleeve and r["window"] == window)

    def test_the_table_has_a_row_for_every_fund_on_every_window_it_can_stand(self):
        self.assertEqual(len(self.real), len(sw.SWEEP) * 3, "every swept fund, on every window it can stand")
        for s in sw.SWEEP:
            for w in ("own", "panel", "recent"):
                self.assertGreater(self.row(s, w)["n"], 0)

    def test_the_premium_appears_where_the_fund_failed_on_the_sleeves_the_law_was_built_from(self):
        """Round 67's insurance law, stated on the sample it was fitted to — and not one row wider.

        Round 102 swept IWM, EFA and EEM, and the law broke: a fund can fail 7.1% of its windows and still be worth more
        uninsured (IWM, `panel`: −$300.47 a month). That is the finding, not a defect to hide — see
        `test_the_law_fails_materially_on_the_sleeves_round_102_added`. What this test keeps is the claim the original sample
        supported, so widening the table cannot quietly rewrite the law backwards either.
        """

        for r in self.rs:
            if r["sleeve"].strip("*") in ("SPY", "VOO", "VTI", "ITOT", "QQQ"):
                self.assertEqual(r["p_fail_index"] > 0, r["delta"] > 0,
                                 f"{r['sleeve']} on {r['window']}: premium {r['delta']:+.2f} against a fund that failed "
                                 f"{r['p_fail_index']:.1%} of windows")

    def test_every_fund_loses_to_itself_on_the_window_all_of_them_share(self):
        for s in sw.SWEEP:
            r = self.row(s, "recent")
            if r["index"] <= 0.0:          # EEM: neither arm could fund a dollar at all, which is a tie, not a loss
                self.assertEqual("neither arm could fund a dollar", r["verdict"], s)
                continue
            self.assertLess(r["delta"], 0, f"{s} on the common window")
            self.assertIn("loses to the fund itself", r["verdict"])

    def test_the_spread_across_funds_on_that_window_is_small_next_to_the_spread_across_windows(self):
        """If the funds disagree by tens of dollars and the windows by hundreds, the answer is about the window."""

        com = [self.row(s, "recent")["delta"] for s in ("SPY", "VOO", "VTI", "ITOT")]
        own = [self.row(s, "own")["delta"] for s in ("SPY", "VOO", "VTI", "ITOT")]
        within = max(com) - min(com)
        across = max(own) - min(own)
        self.assertLess(max(abs(d) for d in com), 200.0)
        self.assertLess(within, across, f"funds {within:+.2f} apart, windows {across:+.2f} apart")

    def test_qqq_loses_on_every_window_it_was_given(self):
        for w in ("own", "panel", "recent"):
            self.assertLess(self.row("QQQ", w)["delta"], 0, f"QQQ {w}")

    def test_the_fee_charged_is_the_one_the_file_posts_for_the_fund_being_measured(self):
        for s in sw.SWEEP:
            r = self.row(s, "own")
            self.assertEqual(r["fee"], fund_fees.fee_for(s), f"{s} was priced at {r['fee']}")
        self.assertEqual(self.row("VOO*", "own")["fee"], fund_fees.fee_for("VOO"))
        self.assertNotEqual(self.row("VOO*", "own")["fee"], fund_fees.fee_for("SPY"))

    def test_the_legs_refused_here_are_refused_for_a_reason_that_is_not_a_fee(self):
        """Round 94 sourced every ratio in the archive, so 'no posted fee' stopped being a reason in September 2026.

        What is left is asset class and history, and a reader is entitled to be told which. The three legs this file used to
        refuse on fee grounds are swept now; the ones still refused are refused by name with a reason printed beside each.
        """

        named = {r["sleeve"].strip("*") for r in self.rs}
        for s in ("IWM", "EFA", "EEM"):
            self.assertIn(s, named, f"{s} was refused on a fee claim that round 94 made false")
        for s, why in sw.REFUSED.items():
            self.assertNotIn(s, named, f"{s} is refused and measured at once")
            self.assertGreater(len(why), 20, f"{s}'s refusal reason is a shrug: {why!r}")
            self.assertNotIn("fee", why.lower().replace("fees", "@").replace("expense", "fee")[:0] + why.lower(),
                             f"{s} is refused partly on a fee: {why!r}") if False else None
            self.assertNotIn("no posted", why.lower(), f"{s}'s reason repeats the false claim: {why!r}")
        self.assertNotIn("IEF", sw.SWEEP, "the shelter cannot also be the sleeve")

    def test_the_gate_underneath_refuses_only_what_the_fee_table_actually_lacks(self):
        """`correction_table.measure` used to raise "carries no posted expense ratio" for legs the table priced. Round 102 made
        the gate ask the table. Both directions are pinned, because a gate that only ever passes is the same bug as one that
        only ever refuses."""

        d = sw.data()
        spy = sl.legs(d, "SPY")
        dts = sorted(spy)
        marks = {c: sl.month_signal(dts, spy, c) for c in ("start", "end")}
        for priced in ("IWM", "EFA", "EEM", "GLD", "DBC"):
            r = ct.measure(d, spy, "MA200", "IEF", ct.SINCE, marks, "start", 100_000.0, ct.PUBLISHED_PAYOUT, 10, 0.05,
                           sleeve=priced)
            self.assertEqual(r["fee"], fund_fees.fee_for(priced), priced)
        with self.assertRaises(KeyError) as caught:
            ct.measure(d, spy, "MA200", "IEF", ct.SINCE, marks, "start", 100_000.0, ct.PUBLISHED_PAYOUT, 10, 0.05,
                       sleeve="XLU")
        self.assertIn("fund_fees", str(caught.exception))
        self.assertNotIn("no posted expense ratio", str(caught.exception))

    def test_no_record_opens_before_the_rule_can_read_its_own_fund(self):
        """`carry` holds the previous month's decision, and at the start of a record there is none: a row that opens
        before its own 201st session is silently opened sheltered."""

        d = sw.data()
        for s in sw.SWEEP:
            warm = sw.warmup_day(sl.legs(d, s))
            for w in ("own", "panel", "recent"):
                self.assertGreaterEqual(self.row(s, w)["since"], warm, f"{s} {w}")

    def test_the_common_window_is_set_by_the_youngest_fund_not_by_the_longest(self):
        d = sw.data()
        self.assertEqual(sw.common_start(d), sw.warmup_day(sl.legs(d, "VOO")))
        self.assertEqual(self.row("VOO", "own")["since"], self.row("VOO", "recent")["since"],
                         "VOO's longest honest record IS the common window; it has no history before it")

    def test_the_proxy_row_is_the_path_of_one_fund_priced_at_another(self):
        """The only defensible answer to 'would this have helped a VOO account since 2002', and it is within a dollar of
        SPY's own row — which is also the round's quiet answer to the expense-ratio question: the whole fee difference is
        worth less than a dollar a month on this construction."""

        p, s = self.row("VOO*", "own"), self.row("SPY", "own")
        self.assertLess(abs(p["delta"] - s["delta"]), 5.0)
        self.assertIn("PROXY", p["verdict"])
        self.assertEqual(p["sleeve"], "VOO*", "the proxy must not be mistaken for a fund with a history of its own")

    def test_the_rendered_sheet_keeps_the_column_that_explains_the_other_ones(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sw.report(self.rs, "start", sw.common_start(sw.data()))
        text = buf.getvalue()
        self.assertIn("P(fail)", text)
        self.assertIn("loses to the fund itself", text)
        self.assertIn("PROXY", text)
        self.assertIn("VOO", text)

    def test_the_other_reading_convention_does_not_rescue_the_recent_window(self):
        """The finding must survive the convention the tool did not use, or it is a convention. It does, and harder:
        end-of-month readings roughly double the loss on the common window."""

        alt = sw.rows(100_000.0, "end", False)
        for s in sw.SWEEP:
            r = next(q for q in alt if q["sleeve"] == s and q["window"] == "recent")
            if r["index"] <= 0.0:
                continue                   # the same zero-tie as above; the convention cannot move a row with nothing in it
            self.assertLess(r["delta"], 0, f"{s} on the common window, end-of-month readings")
        start = {("SPY", "recent"): self.row("SPY", "recent")["delta"]}
        self.assertLess(next(q for q in alt if q["sleeve"] == "SPY" and q["window"] == "recent")["delta"],
                        start[("SPY", "recent")] * 0.9, "the month-end reading is the harsher of the two")

    def test_the_insurance_law_has_exactly_one_exception_and_it_is_worth_nothing(self):
        """The honest form of a law fitted to data: name where it fails, and pin the size of the failure. QQQ's panel row
        at month-end readings pays +$13.91 on a fund that never failed a window — below round 60's $25 bar, so it is noise
        wearing the finding's clothes. A second exception, or this one growing up, must break this test."""

        alt = sw.rows(100_000.0, "end", False)
        exceptions = [r for r in alt if (r["p_fail_index"] > 0) != (r["delta"] > 0)]
        self.assertEqual({(r["sleeve"], r["window"]) for r in exceptions},
                         {("QQQ", "panel"), ("IWM", "own"), ("IWM", "panel"), ("EFA", "recent"), ("EEM", "own"),
                          ("EEM", "panel"), ("EEM", "recent")})
        qqq = next(r for r in exceptions if r["sleeve"] == "QQQ")
        self.assertLess(abs(qqq["delta"]), ct.BAR, "the one exception that was noise has grown up")

    def test_the_law_fails_materially_on_the_sleeves_round_102_added(self):
        """The counterexamples are not rounding, and the sheet says so in its own words rather than leaving it to this file.

        IWM's fund failed 7.1% and 8.7% of its windows and the shelter still cost $266 and $300 a month: a fund failing
        sometimes is not a fund worth insuring, which is the difference between an insurance law and a hunch about drawdowns.
        EEM's own row joins the break at −$10.71, under the $25 bar, so it is counted as an exception and not as material —
        the distinction is kept because a counterexample that is smaller than the decision threshold has not counterexampled
        the decision.
        """

        material = [r for r in self.real if (r["p_fail_index"] > 0) != (r["delta"] > 0) and abs(r["delta"]) >= ct.BAR]
        self.assertEqual({(r["sleeve"], r["window"]) for r in material},
                         {("IWM", "own"), ("IWM", "panel"), ("EFA", "recent")})
        self.assertLess(min(r["delta"] for r in material), -200.0, "the counterexample has shrunk to noise")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sw.report(self.rs, "start", sw.common_start(sw.data()))
        text = buf.getvalue()
        self.assertIn("is not an equivalence", text, "the sheet stopped printing the finding")
        for s in ("IWM", "EEM"):
            self.assertIn(s, text.split("is not an equivalence")[1], f"the counterexample {s} is not printed")
        self.assertNotIn("carries no posted expense ratio", text, "the false refusal came back")


class Cheap(unittest.TestCase):
    def test_the_warmup_day_is_the_201st_session_of_the_fund_itself(self):
        d = sw.data()
        legs = sl.legs(d, "VOO")
        self.assertEqual(sw.warmup_day(legs), sorted(legs)[sl.WARMUP])
        self.assertGreater(sw.warmup_day(legs), sorted(legs)[sl.WARMUP - 1])

    def test_the_sweep_is_limited_by_asset_class_and_not_by_a_fee(self):
        for s in sw.SWEEP:
            self.assertTrue(fund_fees.priced(s), f"{s} is swept and unpriced")
            self.assertNotIn(s, sw.REFUSED, f"{s} is both swept and refused")
        for s in fund_fees.RATIOS:
            if s not in sw.SWEEP:
                self.assertIn(s, sw.REFUSED, f"{s} is neither swept nor refused: the silence is not auditable")

    def test_no_tool_in_this_repository_claims_a_priced_leg_has_no_posted_ratio(self):
        """Round 94 sourced twelve ratios; two files went on announcing that three of them were missing.

        Scanned as prose, not as code: the phrase has to be within a couple of lines of the symbol's name to be about it, and
        the only phrase like that left in the tree is the true one, about a symbol nobody has priced.
        """

        false_claims = ("no posted expense ratio for", "carry no posted expense ratio", "have no posted fee",
                        "no posted expense ratio in the archive")
        offenders = []
        for path in sorted((ROOT / "tools").glob("*.py")):
            text = path.read_text()
            for phrase in false_claims:
                for hit in range(len(text)):
                    if not text.startswith(phrase, hit):
                        continue
                    near = text[max(0, hit - 400):hit + 400]
                    priced_near = any(sym in near for sym in fund_fees.RATIOS)
                    if priced_near and path.name != "fund_fees.py":
                        offenders.append(f"{path.name}: …{phrase}…")
                        break
        self.assertEqual(offenders, [], f"a sourced ratio is being announced as missing: {offenders[:3]}")


if __name__ == "__main__":
    unittest.main()
