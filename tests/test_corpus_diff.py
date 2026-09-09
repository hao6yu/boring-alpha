"""Tests for `tools/corpus_diff.py` — the corpus half of rule 4, and a check that is allowed to say "not yet".

Every snapshot here is fabricated: two directories, a manifest, and three CSVs. The real snapshots are only ever asked to *run*, never
asserted to be within tolerance — a suite that fails because a vendor revised a close is r95's failure rehearsed as policy.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import corpus_diff as cd                                    # noqa: E402

STAMP_OLD, STAMP_NEW = "20260101T000000Z", "20260201T000000Z"


def snapshot(dirs: Path, stamp: str, prices: dict, cash: dict, dividends: dict, columns=None):
    """Write one snapshot directory. `prices` maps (date, symbol) -> close; the rest are keyed the same way."""

    d = dirs / stamp
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"fetched": stamp}))
    with (d / "market_daily.csv").open("w", encoding="utf-8") as handle:
        handle.write("date,symbol,tr_open,tr_close\n")
        for (date, symbol), close in sorted(prices.items()):
            handle.write(f"{date},{symbol},{close},{close}\n")
    with (d / "cash_daily.csv").open("w", encoding="utf-8") as handle:
        handle.write("date,cash_factor\n")
        for date, factor in sorted(cash.items()):
            handle.write(f"{date},{factor}\n")
    fields = columns or ("date", "symbol", "close", "dividend")
    with (d / "distributions_daily.csv").open("w", encoding="utf-8") as handle:
        handle.write(",".join(fields) + "\n")
        for (date, symbol), amount in sorted(dividends.items()):
            handle.write(f"{date},{symbol},10.0,{amount}\n")
    return d


class Scratch(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="corpus-diff-"))
        self.saved = cd.SNAPSHOTS
        cd.SNAPSHOTS = self.dir
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.addCleanup(setattr, cd, "SNAPSHOTS", self.saved)

    def make(self, old_prices, new_prices, old_cash=None, new_cash=None, old_div=None, new_div=None, columns=None):
        base = {"2026-01-02": {"SPY": 100.0, "QQQ": 200.0}, "2026-01-05": {"SPY": 101.0, "QQQ": 201.0}}
        expand = lambda rows: {(d, s): v for d, by in rows.items() for s, v in by.items()}
        snapshot(self.dir, STAMP_OLD, expand(old_prices or base), old_cash or {"2026-01-02": 1.0001},
                 old_div or {("2026-01-02", "SPY"): 0.0}, columns=columns)
        snapshot(self.dir, STAMP_NEW, expand(new_prices or base), new_cash or {"2026-01-02": 1.0001},
                 new_div or {("2026-01-02", "SPY"): 0.0}, columns=columns)

    def run_tool(self, argv=()):
        argv, saved = ["corpus_diff.py", *argv], sys.argv
        sys.argv = argv
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = cd.main()
        finally:
            sys.argv = saved
        return code, out.getvalue()


class AFetchThatOnlyAddsHistory(Scratch):
    def test_a_new_session_is_reported_and_the_month_continues(self):
        self.make(None, {"2026-01-02": {"SPY": 100.0, "QQQ": 200.0}, "2026-01-05": {"SPY": 101.0, "QQQ": 201.0},
                         "2026-01-06": {"SPY": 102.0, "QQQ": 202.0}})
        code, text = self.run_tool()
        self.assertEqual(code, 0)
        self.assertIn("added 2026-01-06", text)
        self.assertIn("within the 1.5%", text)
        # Round 105 narrowed this pin. The tool used to print "Nothing has to be re-read" on every within-tolerance diff, and on
        # the real corpus that sentence contradicted the line above it: 11 of 12 symbols' old closes had moved, by 0.0002%, and
        # one of them moved a dollar in the runbook.
        self.assertIn("No old close moved at all", text)

    def test_a_revision_small_enough_to_be_noise_still_names_the_document_it_moved(self):
        """Round 105's real fetch moved `12,216,556 → 12,216,557` in the obeyed document — a 0.0001% revision, and the class under
        the figure caught it. The diff tool may call that immaterial; it may not call it nothing.

        """

        self.make(None, {"2026-01-02": {"SPY": 100.0001, "QQQ": 200.0}, "2026-01-05": {"SPY": 101.0, "QQQ": 201.0}})
        code, text = self.run_tool()
        self.assertEqual(code, 0, "an immaterial revision must not stop the month")
        self.assertIn("within the 1.5%", text)
        self.assertIn("old closes moved", text)
        self.assertIn("docs/RUNBOOK.md", text, "the verdict stops short of the document the move can actually reach")
        self.assertIn("never by hand", text)
        self.assertNotIn("Nothing has to be re-read", text, "the tool is again calling a revision nothing")

    def test_a_revision_too_small_to_matter_is_still_printed(self):
        """Reporting and stopping are different acts. Everything that moved is printed; only a big move stops the month."""

        self.make(None, {"2026-01-02": {"SPY": 100.0, "QQQ": 200.0}, "2026-01-05": {"SPY": 101.1, "QQQ": 201.0}})
        code, text = self.run_tool()
        self.assertEqual(code, 0, "a 0.1% revision must not stop a month")
        self.assertIn("0.0990%", text)   # 101.0 → 101.1 is 0.0990%, and the tool prints what it measured


class AnEmptyFetchHasToSayWhy(Scratch):
    """A fetch that adds no sessions is the most common confusing outcome of the month, and the tool used to print "history added".

    Round 106's fetch added nothing; the archive's edge was right and the missing day was a US market holiday, which is a fact the
    repository owns only in `data/calendars/`, whose coverage stops at 2026-08-31. So the tool now states which of four things is true
    — nothing to add, the days were closures, the source fell short, or the calendar cannot say — and the fourth is the live case.
    """

    def calendar(self, coverage_end: str, open_days=()):
        path = self.dir / "calendar.json"
        path.write_text(json.dumps({"closures": [], "half_days": [], "sessions": list(open_days),
                                    "coverage_start": "2006-01-01", "coverage_end": coverage_end}))
        saved = cd.CALENDAR
        cd.CALENDAR = path
        self.addCleanup(setattr, cd, "CALENDAR", saved)

    def test_a_calendar_that_cannot_reach_the_gap_says_so_and_names_the_rebuild(self):
        self.make(None, {"2026-01-02": {"SPY": 100.0, "QQQ": 200.0}, "2026-01-05": {"SPY": 101.0, "QQQ": 201.0}})
        self.calendar("2026-01-10", open_days=["2026-01-02", "2026-01-05"])
        code, text = self.run_tool()
        self.assertEqual(code, 0)
        self.assertIn("no new sessions", text)
        self.assertIn("coverage ends 2026-01-10", text)
        self.assertIn("build_nyse_calendar.py", text, "the refusal has to point at the thing that would lift it")

    def test_an_uncovered_gap_inside_the_reviewed_window_is_still_answered_from_the_rules(self):
        """The artifact vouches for dates; the rule set vouches for the reviewed window. Round 108 made the tool say which it used.

        The scratch calendar here stops a month into the gap, so the artifact cannot answer — but 2026 is inside the window the
        transcription was reviewed for, and the rules say most of those January weekdays were trading days. The tool must admit the
        coverage first and then answer, never quietly switch sources.
        """

        self.make(None, {"2026-01-02": {"SPY": 100.0, "QQQ": 200.0}, "2026-01-05": {"SPY": 101.0, "QQQ": 201.0}})
        self.calendar("2026-01-10", open_days=["2026-01-02", "2026-01-05"])          # coverage irrelevant now: the rules answer
        code, text = self.run_tool()
        self.assertEqual(code, 0)
        self.assertIn("coverage ends 2026-01-10", text, "the admission has to stay in the sentence")
        self.assertIn("re-derived in `tests/test_nyse_rules_independently.py`", text)
        self.assertIn("were trading days", text)

    def test_the_rule_source_refuses_the_years_it_was_never_reviewed_for(self):
        """The transcription was reviewed for 2006-2026 and says so; the tool must not extrapolate the rules past that.

        Tested at the seam rather than through a fabricated stamp, because the fetch date is what places a gap in a year, and a
        fixture that disagreed with its own calendar directory would be testing the fixture.
        """

        self.assertIsNotNone(cd.rule_closures(2026), "the reviewed window has to reach the year the forward test is being run in")
        self.assertIsNone(cd.rule_closures(2031), "2031 is outside the reviewed rule window and must not be guessed at")
        self.assertIsNone(cd.rule_closures(1999), "neither is the pre-transcription past")
        self.assertIn("2026-09-07", cd.rule_closures(2026), "Labor Day is the fact the live month needs, and the rules carry it")

    def test_days_the_calendar_says_were_closures_are_reported_as_current_not_stalled(self):
        self.make(None, {"2026-01-02": {"SPY": 100.0, "QQQ": 200.0}, "2026-01-05": {"SPY": 101.0, "QQQ": 201.0}})
        self.calendar("2026-02-01", open_days=["2026-01-02", "2026-01-05"])       # no gap weekday is open
        code, text = self.run_tool()
        self.assertEqual(code, 0)
        self.assertIn("were exchange closures", text)
        self.assertIn("not stalled", text)

    def test_an_open_day_the_source_skipped_is_called_short_and_the_day_is_named(self):
        self.make(None, {"2026-01-02": {"SPY": 100.0, "QQQ": 200.0}, "2026-01-05": {"SPY": 101.0, "QQQ": 201.0}})
        self.calendar("2026-02-01", open_days=["2026-01-02", "2026-01-05", "2026-01-12"])
        code, text = self.run_tool()
        self.assertEqual(code, 0, "a short source is loud but does not stop the month; the next fetch fills it")
        self.assertIn("the source fell short", text)
        self.assertIn("2026-01-12", text, "the refusal must name the day it missed")

    def test_no_calendar_on_disk_is_a_named_absence_rather_than_a_shrug(self):
        self.make(None, {"2026-01-02": {"SPY": 100.0, "QQQ": 200.0}, "2026-01-05": {"SPY": 101.0, "QQQ": 201.0}})
        saved = cd.CALENDAR
        cd.CALENDAR = self.dir / "not-here.json"
        self.addCleanup(setattr, cd, "CALENDAR", saved)
        code, text = self.run_tool()
        self.assertEqual(code, 0)
        self.assertIn("no exchange calendar on disk", text)
        self.assertIn("cannot tell a holiday from a stalled fetch", text)


class ARevisionThatHasToBeRead(Scratch):
    def test_a_close_revised_past_the_tolerance_stops_the_run_and_names_the_worst_cell(self):
        self.make(None, {"2026-01-02": {"SPY": 103.0, "QQQ": 200.0}, "2026-01-05": {"SPY": 101.0, "QQQ": 201.0}})
        code, text = self.run_tool()
        self.assertEqual(code, 1)
        self.assertIn("OUTSIDE tolerance", text)
        self.assertIn("SPY", text)
        self.assertIn("2026-01-02", text)
        self.assertIn("3.0000%", text)

    def test_history_that_disappeared_is_a_failure_even_if_no_price_moved(self):
        """The most dangerous kind of revision is a deletion: it makes every 'record through' sentence in the notes a lie."""

        self.make(None, {"2026-01-05": {"SPY": 101.0, "QQQ": 201.0}})
        code, text = self.run_tool()
        self.assertEqual(code, 1)
        self.assertIn("REMOVED 2026-01-02", text)

    def test_a_symbol_that_left_the_archive_is_named_as_lost(self):
        self.make(None, {"2026-01-02": {"SPY": 100.0}, "2026-01-05": {"SPY": 101.0}})
        code, text = self.run_tool()
        self.assertEqual(code, 1)
        self.assertIn("LOST QQQ", text)

    def test_a_dividend_restated_by_more_than_half_a_cent_is_its_own_failure(self):
        self.make(None, None, old_div={("2026-01-02", "SPY"): 0.50}, new_div={("2026-01-02", "SPY"): 0.52})
        code, text = self.run_tool()
        self.assertEqual(code, 1, "0.02 of a restated dividend moves every adjusted close downstream of it")
        self.assertIn("$0.0200", text)

    def test_the_json_carries_the_same_facts_the_screen_does(self):
        self.make(None, {"2026-01-02": {"SPY": 100.0, "QQQ": 200.0}, "2026-01-05": {"SPY": 110.0, "QQQ": 201.0}})
        code, text = self.run_tool(["--json"])
        payload = json.loads(text)
        self.assertEqual(code, 1)
        self.assertFalse(payload["within_tolerance"])
        self.assertEqual(payload["newer"], STAMP_NEW)
        self.assertGreater(payload["per_symbol"]["SPY"]["max_revision"], 0.08)


class ACheckAllowedToAdmitIgnorance(Scratch):
    def test_a_first_snapshot_reports_nothing_to_compare_and_exits_cleanly(self):
        snapshot(self.dir, STAMP_NEW, {}, {}, {})
        code, text = self.run_tool()
        self.assertEqual(code, 0, "one snapshot is a fact about the calendar, not a failure")
        self.assertIn("nothing to compare yet", text)

    def test_the_tool_refuses_to_diff_a_snapshot_against_itself(self):
        self.make(None, None)
        code = None
        with self.assertRaises(SystemExit) as caught:
            self.run_tool(["--against", STAMP_NEW])
        self.assertIn("lie", str(caught.exception))

    def test_an_unknown_stamp_is_refused_with_the_names_that_do_exist(self):
        self.make(None, None)
        with self.assertRaises(SystemExit) as caught:
            self.run_tool(["--against", "19990101T000000Z"])
        self.assertIn(STAMP_OLD, str(caught.exception))


class AnEmptyDiffIsNeverQuiet(Scratch):
    def test_a_cash_file_with_no_known_column_is_named_rather_than_reported_as_unchanged(self):
        """r92: a check that cannot find its input must not print the number that lets the month continue."""

        snapshot(self.dir, STAMP_OLD, {}, {"2026-01-02": 1.0}, {})
        snapshot(self.dir, STAMP_NEW, {}, {}, {})
        (self.dir / STAMP_OLD / "cash_daily.csv").write_text("date,whatever\n2026-01-02,1.0\n")
        (self.dir / STAMP_NEW / "cash_daily.csv").write_text("date,whatever\n2026-01-02,1.0\n")
        with self.assertRaises(SystemExit) as caught:
            self.run_tool()
        self.assertIn("no cash column", str(caught.exception))
        self.assertIn("whatever", str(caught.exception))

    def test_a_distributions_file_with_no_dividend_column_is_named_too(self):
        self.make(None, None, columns=("date", "symbol", "close"))
        with self.assertRaises(SystemExit) as caught:
            self.run_tool()
        self.assertIn("no dividend column", str(caught.exception))


class TheToleranceExistsOnce(unittest.TestCase):
    def test_the_number_is_not_written_in_the_test_that_uses_it(self):
        text = (ROOT / "tests" / "test_power_horizon.py").read_text()
        self.assertNotIn("0.015", text, "the pin re-states the tolerance instead of importing it (r94)")
        self.assertIn("corpus_diff.TOLERANCE", text)

    def test_the_runbook_quotes_the_same_number_the_tool_uses(self):
        self.assertIn(f"{cd.TOLERANCE:.1%}", (ROOT / "docs" / "RUNBOOK.md").read_text())

    def test_the_monthly_block_runs_the_diff_right_after_the_fetch(self):
        block = (ROOT / "docs" / "RUNBOOK.md").read_text().split("```sh")[1].split("```")[0]
        lines = [l for l in block.splitlines() if l.strip() and not l.strip().startswith("#")]
        fetch = next(i for i, l in enumerate(lines) if "fetch_market_data" in l)
        diff = next(i for i, l in enumerate(lines) if "corpus_diff" in l)
        self.assertEqual(diff, fetch + 1, "the diff belongs immediately after the fetch, or it describes a stale pointer")


class TheRealSnapshotsMustOnlyRun(unittest.TestCase):
    """The archive's own snapshots are never asserted to be within tolerance: that is the vendor's behaviour, not this repository's."""

    def test_comparing_the_two_newest_real_snapshots_produces_a_full_structure(self):
        found = cd.snapshots()
        if len(found) < 2:
            self.skipTest("one snapshot on this machine")
        diff = cd.compare(found[-1], found[-2])
        self.assertEqual(diff["newer"], found[-1].name)
        self.assertEqual(diff["older"], found[-2].name)
        self.assertGreater(diff["sessions"]["new"], 8000)
        for symbol, row in diff["per_symbol"].items():
            self.assertGreaterEqual(row["max_revision"], 0.0)
            self.assertGreater(row["sessions"], 1000, f"{symbol} is barely present in the archive")
        self.assertGreater(len(cd.cash(found[-1] / cd.CASH)), 5000, "the cash reader parsed almost nothing")
        self.assertGreater(len(cd.distributions(found[-1] / cd.DISTRIBUTIONS)), 1000, "the dividend reader parsed almost nothing")

    def test_the_shipped_calendar_cannot_reach_the_gap_the_live_fetch_left(self):
        """The calendar is an input, and it ages: its published coverage stops before the archive's newest session, so on the live
        corpus the tool must admit it cannot say whether the missing weekdays were closures. Round 106's fetch landed exactly there
        (2026-09-07, US Labor Day, two days after the calendar stops). Pinning the *admission* keeps the honesty from rotting into
        a guess the next time the dates line up differently.
        """

        found = cd.snapshots()
        if len(found) < 2:
            self.skipTest("one snapshot on this machine")
        coverage = json.loads(cd.CALENDAR.read_text())["coverage_end"]
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "corpus_diff.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        text = r.stdout
        self.assertIn(coverage, text, "the calendar's coverage end is the fact doing the refusing; it has to appear")
        # Round 108 changed what the tool may say here: it still admits the artifact stops short, and then answers from the reviewed
        # rule set. Both halves are pinned, because an answer without the admission would be a claim about an artifact that does not exist.
        self.assertIn("the archive is current, not stalled", text)
        self.assertIn("tests/test_nyse_rules_independently.py", text)


if __name__ == "__main__":
    unittest.main()
