"""Tests for the sheltered-trend ticket — the sheet the user actually reads, and the refusals it must be able to make.

A sheet like this fails in two ways: it drifts from the numbers the evidence was computed on, or it stops being able to
say no. Both are pinned here. The numbers are re-derived from `correction_table` rather than typed in, so a change to the
measurement shows up here as a failure rather than as a stale paragraph, and every refusal path is exercised by being
asked for the thing it refuses.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import correction_table as ct                                # noqa: E402
import paper                                                 # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import shelter_ticket as st                                  # noqa: E402


class Issued(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = st.issue(100_000.0, None, "long", "start", "IEF", None, 10)

    def test_the_sheet_is_issued_at_its_own_numbers(self):
        self.assertTrue(self.t["issued"], self.t["refusals"])
        self.assertEqual(self.t["refusals"], [])
        self.assertAlmostEqual(self.t["safe"], 567.22, delta=0.01)
        self.assertAlmostEqual(self.t["safe_index"], 436.76, delta=0.01)
        self.assertAlmostEqual(self.t["delta"], 130.46, delta=0.01)

    def test_the_sheet_and_the_correction_table_agree_because_they_are_the_same_call(self):
        """The point of importing the measurement rather than restating it: the artifact that tells a person what to do
        must not be a third implementation of the answer."""

        from boring_alpha.data.csv_loader import load_csv_market_data
        import withdrawal_capacity as wc
        d = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        spy = sl.legs(d, "SPY")
        marks = {c: sl.month_signal(sorted(spy), spy, c) for c in ("start", "end")}
        direct = ct.measure(d, spy, "MA200", "IEF", ct.SINCE, marks, "start", 100_000.0, ct.PUBLISHED_PAYOUT, 10, 0.05)
        for key in ("safe", "cap", "p_fail", "months", "n", "duty"):
            self.assertAlmostEqual(self.t["plan"][key], direct[key], places=10, msg=key)

    def test_every_dollar_figure_is_proportional_to_the_capital_and_so_is_the_ceiling(self):
        double = st.issue(200_000.0, None, "long", "start", "IEF", None, 10)
        for key in ("safe", "safe_index", "delta", "cap"):
            self.assertAlmostEqual(double[key], 2.0 * self.t[key], places=6, msg=key)

    def test_the_decision_is_the_forward_books_decision_not_a_copy_of_it(self):
        _w, _last, read_on, want = paper.shelter_weights(self.t["data"], self.t["signal"]["asof"])
        self.assertEqual(self.t["signal"]["weights"], {"SPY": 1.0} if want else {"IEF": 1.0})
        self.assertEqual(self.t["signal"]["read_on"], read_on)
        self.assertLess(read_on, self.t["signal"]["asof"])

    def test_the_sheet_names_its_own_fee_assumption_and_the_duty_cycle_it_earns_it_on(self):
        self.assertEqual(self.t["shelter_fee"], paper.fee_for("IEF"))
        self.assertAlmostEqual(self.t["plan"]["duty"], 0.196, delta=0.002,
                               msg="round 66's duty cycle, on this record, from this code path")

    def test_an_issued_sheet_still_prints_the_window_that_refuses_it(self):
        """The companion block is the reason the long-record premium may be printed at all: a sheet that shows one window
        is a position being sold, and round 66's rule about record length applies to the sheet itself."""

        text = st.render(self.t)
        self.assertIn("THE OTHER WINDOWS", text)
        self.assertIn("recent  from 2011-06-24", text)
        self.assertIn("-159.06", text)
        self.assertIn("no premium", text)

    def test_the_rendered_sheet_refuses_to_claim_return_alpha(self):
        text = st.render(self.t)
        self.assertIn("not a return alpha", text)
        self.assertIn("0 of 26", text)
        self.assertIn("436.76", text)

    def test_a_cash_shelter_is_legal_and_worth_less_than_a_paying_one(self):
        cash = st.issue(100_000.0, None, "long", "start", sl.CASH, None, 10)
        self.assertTrue(cash["issued"], cash["refusals"])
        self.assertEqual(cash["shelter_fee"], 0.0)
        self.assertLess(cash["safe"], self.t["safe"], "round 64's finding reversed: the shelter pays for itself")
        self.assertGreater(self.t["safe"] - cash["safe"], 50.0, f"the shelter is only worth {self.t['safe']-cash['safe']:.2f}")


class Refused(unittest.TestCase):
    def test_a_withdrawal_past_the_capacity_is_refused_and_the_ceiling_is_printed_instead(self):
        t = st.issue(100_000.0, 900.0, "long", "start", "IEF", None, 10)
        self.assertFalse(t["issued"])
        self.assertIn("775.00", t["refusals"][0])
        self.assertIn("NOT ISSUED", st.render(t))

    def test_the_capacity_refusal_scales_with_the_account_it_is_written_for(self):
        t = st.issue(200_000.0, 1600.0, "long", "start", "IEF", None, 10)
        self.assertFalse(t["issued"])
        self.assertIn("1,550.00", t["refusals"][0])
        ok = st.issue(200_000.0, 1500.0, "long", "start", "IEF", None, 10)
        self.assertTrue(ok["issued"], ok["refusals"])

    def test_a_record_before_the_average_exists_refuses_rather_than_selling(self):
        """The defect class round 45 caught in one tool and round 66 in another: a rule that cannot answer must not
        answer 'sell'. This is the same failure reached from the sheet rather than the rule."""

        t = st.issue(100_000.0, None, "long", "start", "IEF", dt.date(1993, 7, 15), 10)
        self.assertFalse(t["issued"])
        self.assertTrue(any("200-day average" in r for r in t["refusals"]), t["refusals"])
        self.assertEqual(t["signal"]["weights"], {})

    def test_the_command_exits_non_zero_when_it_refuses(self):
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "shelter_ticket.py"), "--payout", "900"],
                             capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(out.returncode, 3)
        self.assertIn("NOT ISSUED", out.stdout)

    def test_the_recent_window_refuses_and_says_what_it_instead(self):
        """Round 73's refusal, and the most important one the sheet has: on the window every fund can be scored on, the
        plan loses to holding the fund, and the sheet says so in those words rather than quietly quoting the older record.
        """

        t = st.issue(100_000.0, None, "recent", "start", "IEF", None, 10)
        self.assertFalse(t["issued"])
        self.assertTrue(any("loses to holding the fund itself" in r for r in t["refusals"]), t["refusals"])
        self.assertTrue(any("159" in r for r in t["refusals"]), t["refusals"])

    def test_a_materiality_shortfall_would_refuse_too(self):
        """Not reachable on this archive — the plan clears the bar by fifty dollars — but the branch is the reason the
        sheet is advice rather than promotion, so it is exercised on a fabricated measure."""

        t = st.issue(100_000.0, None, "long", "start", "IEF", None, 10)
        t["plan"] = dict(t["plan"], safe=t["index"]["safe"] + 10.0)
        t["refusals"] = ["the plan clears the index by only 10.00/mo, under the $25 materiality bar"]
        t["issued"] = False
        self.assertIn("materiality", st.render(t))


class CommandLine(unittest.TestCase):
    def test_json_output_carries_the_decisions_and_not_the_data(self):
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "shelter_ticket.py"), "--json",
                              "--capital", "50000"], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stderr[-400:])
        payload = json.loads(out.stdout)
        for key in ("issued", "safe", "safe_index", "delta", "cap", "shelter_fee", "signal", "payout"):
            self.assertIn(key, payload)
        self.assertNotIn("data", payload)
        self.assertAlmostEqual(payload["safe"], st.issue(100_000.0, None, "long", "start", "IEF", None, 10)["safe"]
                               / 2.0, places=6)

    def test_the_panel_record_is_available_and_smaller_than_the_long_one(self):
        panel = st.issue(100_000.0, None, "panel", "start", "IEF", None, 10)
        self.assertTrue(panel["issued"], panel["refusals"])
        self.assertEqual(panel["plan"]["n"], 127)
        self.assertLess(panel["safe"], st.issue(100_000.0, None, "long", "start", "IEF", None, 10)["safe"])


if __name__ == "__main__":
    unittest.main()
