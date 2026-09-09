"""The forward books have never sealed a real month-end, so a month-end is manufactured and the seal is made to pass.

`tools/rehearse_forward.py` copies the sealed corpus to a scratch directory, appends synthetic month-ends for dates after the
archive's tail, and drives the same CLI a person will run on 2026-09-30. These tests assert what that rehearsal must conclude,
and one thing it must never do: touch the real corpus. The rehearsal exists because `tests/test_paper*.py` can only ever
exercise the engine on history — a month-end that is already in the file — and because round 84 changed two conventions on
the seal path (`_deposits_due` accrues per calendar month, `days_to_invest` records the wait) under the cover of unit tests
that could call the helper but never the command.

Round 87 found two real things by running this: the engine refuses to seal a date the bill curve does not cover (correct, and
the reason the fetcher writes prices and cash atomically), and a band-triggered rebalance could size a buy one cent past the
cash that existed, which the ledger resolved by booking a loan on a plan whose sealed `plan` field says it never borrows.
"""

from __future__ import annotations

import hashlib
import io
import contextlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import rehearse_forward as rf                                    # noqa: E402


def _corpus_hash() -> dict:
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (rf.REAL_MARKET, rf.REAL_CASH)}


class RehearsalRuns(unittest.TestCase):
    """Every scenario is run once, in the class fixture, because each copy of the corpus costs a few seconds."""

    @classmethod
    def setUpClass(cls):
        cls.before = _corpus_hash()
        cls.results = {name: rf.run(name, 5_000.0, 500.0) for name in rf.SCENARIOS}

    def checks(self, scenario, needle):
        return [c for c in self.results[scenario] if needle in c[0]]

    def test_the_real_corpus_is_untouched_by_rehearsing_on_a_copy_of_it(self):
        """The one check that is not about the engine. Round 87's first version of this tool bound a path before repathing
        the module that used it and appended a synthetic row to the live bill curve; it was restored byte-exact against a
        snapshot copy, which the destroyed engine file of round 84 had no equivalent of."""

        self.assertEqual(_corpus_hash(), self.before, "a rehearsal wrote to the sealed archive")

    def test_every_scenario_passes_every_check(self):
        failed = [(name, c[0], c[2]) for name, checks in self.results.items() for c in checks if not c[1]]
        self.assertEqual(failed, [], f"failing checks: {failed}")

    def test_the_scenarios_are_four_and_each_seals_at_least_two_intervals(self):
        self.assertEqual(len(rf.SCENARIOS), 4)
        for name, checks in self.results.items():
            self.assertGreaterEqual(len([c for c in checks if " sealed" in c[0]]), 2, name)

    def test_a_flat_tape_never_produces_a_sell_however_many_deposits_arrive(self):
        """Round 84's defect, in integration: a banded book whose prices never moved must not trade because money arrived."""

        for check in self.checks("flat", " sold "):
            self.assertIn("sold 0 sleeve", check[0], check[2])
            self.assertTrue(check[1], check[2])

    def test_a_twelve_point_divergence_breaches_a_five_point_band_and_sells_the_runner(self):
        breached = self.checks("divergent", "sold 1 sleeve")
        self.assertTrue(breached, "the band never fired on a 12-point divergence, so it is decoration")
        self.assertIn("SPY", breached[0][2], breached[0][2])

    def test_a_missed_seal_arrives_with_every_transfer_it_skipped_and_says_how_late_they_were(self):
        """The two round-84 conventions, tested through the command rather than on the helper: October pays one deposit,
        December pays two, and the older one is recorded as thirty days idle — which is also the first time the ledger's own
        idle-cash finding has any chance of firing."""

        # The scenario seals September and November: October has no bar at all, which is the missed seal being modelled — a
        # month the operator did not run the tool, not a month the tool ran and declined.
        november = self.checks("skipped", "2026-11-30 accrued")[0]
        self.assertIn("sealed $1,000.00, expected $1,000.00", november[2],
                      "two calendar months passed, so two transfers were owed whatever the sealing schedule managed")
        wait = self.checks("skipped", "2026-11-30 reports the wait")[0]
        self.assertIn("days_to_invest 30, expected 30", wait[2])
        december = self.checks("skipped", "2026-12-31 accrued")[0]
        self.assertIn("sealed $500.00, expected $500.00", december[2], "one month since the last seal pays one transfer")

    def test_the_anchors_own_month_is_not_paid_out_twice(self):
        first = self.checks("flat", "2026-09-30 accrued")[0]
        self.assertIn("sealed $0.00, expected $0.00", first[2],
                      "the anchor already funded September; a second transfer on the first seal would double the opening")

    def test_a_book_that_sells_in_a_crash_does_not_borrow_or_flag_itself(self):
        for check in self.checks("crash", "took no loan"):
            self.assertTrue(check[1], check[2])
            self.assertIn("no borrowing in the note", check[2])

    def test_no_interval_ever_ends_a_no_borrow_plan_owing_a_cent(self):
        """Round 87's real find: the ledger would silently book a one-cent loan on a plan whose sealed `plan` string says
        it never borrows. The buy is trimmed to the cash that exists instead, and this check is what keeps it that way."""

        for name, checks in self.results.items():
            for check in [c for c in checks if "took no loan" in c[0]]:
                self.assertTrue(check[1], f"{name}: {check[2]}")

    def test_every_sealed_entry_still_verifies_after_the_last_one_lands(self):
        for name, checks in self.results.items():
            for check in [c for c in checks if "both chains verify" in c[0]]:
                self.assertTrue(check[1], f"{name}: {check[2]}")


class TheCommandLineContract(unittest.TestCase):
    def test_main_exits_zero_when_the_rehearsal_passes_and_names_the_corpus_it_protected(self):
        saved, sys.argv = sys.argv, ["rehearse_forward.py", "--scenario", "flat"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = rf.main()
        finally:
            sys.argv = saved
        self.assertEqual(code, 0)
        self.assertIn("byte-identical", out.getvalue())
        self.assertIn("all checks passed", out.getvalue())

    def test_the_json_form_carries_every_check_as_a_record(self):
        saved, sys.argv = sys.argv, ["rehearse_forward.py", "--scenario", "crash", "--json"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = rf.main()
        finally:
            sys.argv = saved
        import json
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["failed"], 0)
        self.assertEqual(len(payload["results"]), 1)
        self.assertIn("passed", str(payload["results"][0]["checks"][0]))


if __name__ == "__main__":
    unittest.main()
