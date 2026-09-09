"""Tests for `rehearse_forward.py`, the rehearsal that stands between "we think the seal works" and "we know".

Round 107 ran the rehearsal and it passed — 2026-09-30 seals, 2026-10-30 seals, both chains verify, the real corpus left byte-identical —
and then found that nothing in the suite ran it. The artifact that proves the forward path had no class under it (r100), so the proof was
good until the next refactor and then silently was not. Same round's habit: a check needs its negative test (r93), so the second class
here breaks the audit inside the rehearsal on purpose and requires the tool to notice.
"""

from __future__ import annotations

import contextlib
import csv
import datetime as dt
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                                  # noqa: E402
import rehearse_forward as rf                                 # noqa: E402

BOOKS = ROOT / "data" / "paper" / "books"      # where the five forward chains actually live (`paper.PAPER_DIR / "books"`)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "<absent>"


def real_state() -> dict:
    """Every byte the forward ledger could plausibly be moved by: the five chains, the models, the corpus pointer."""

    files = [ROOT / "data" / "current" / "market_daily.csv", ROOT / "data" / "current" / "cash_daily.csv",
             ROOT / "data" / "paper" / "ledger.jsonl", ROOT / "data" / "paper" / "shadow.jsonl"]
    files += sorted(BOOKS.glob("*/ledger.jsonl"))
    files += sorted(BOOKS.glob("*/shadow.jsonl"))
    files += sorted(BOOKS.glob("*/model.json"))
    return {str(p.relative_to(ROOT)): digest(p) for p in files}


class TheRehearsal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = real_state()
        cls.rows = {s: rf.run(s, 5_000.0, 500.0) for s in rf.SCENARIOS}

    def tearDown(self):
        self.assertEqual(real_state(), self.before, "the rehearsal touched something under the real paths")

    def test_every_scenario_passes_every_check_it_makes(self):
        for scenario, checks in self.rows.items():
            failed = [c for c in checks if not c[1]]
            self.assertGreaterEqual(len(checks), 10, f"{scenario} made {len(checks)} checks, which is not a rehearsal")
            self.assertEqual(failed, [], f"{scenario}: {[c[0] for c in failed]}")

    def test_the_two_months_the_forward_test_actually_needs_are_reached(self):
        labels = " ".join(label for checks in self.rows.values() for label, _, _ in checks)
        for want in ("2026-09-30 sealed", "2026-10-30 sealed"):
            self.assertIn(want, labels, f"the rehearsal no longer reaches {want}")

    def test_the_first_deposit_is_accrued_and_not_assumed(self):
        """The book opens with the anchor and deposits a month later, so entry two must carry $500.00 of transfers or say why not."""

        rows = [c for c in self.rows["flat"] if "2026-10-30 accrued" in c[0]]
        self.assertEqual(len(rows), 1)
        label, passed, detail = rows[0]
        self.assertTrue(passed, detail)
        self.assertIn("$500.00", detail)

    def test_a_month_with_no_session_is_skipped_rather_than_sealed(self):
        sealed = [c[0] for c in self.rows["skipped"] if c[0].endswith("sealed")]
        self.assertEqual(len(sealed), len(rf.SEALS["skipped"]), sealed)

    def test_the_crash_scenario_seals_only_what_survived(self):
        sealed = [c[0] for c in self.rows["crash"] if c[0].endswith("sealed")]
        self.assertEqual(len(sealed), len(rf.SEALS["crash"]), sealed)
        self.assertTrue(all(c[1] for c in self.rows["crash"]), "the crash scenario must be survivable, not merely survivable-ish")

    def test_the_tool_exits_clean_over_all_scenarios(self):
        argv, saved = ["rehearse_forward.py", "--scenario", "all"], sys.argv
        sys.argv = argv
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = rf.main()
        finally:
            sys.argv = saved
        self.assertEqual(code, 0, out.getvalue()[-600:])
        self.assertIn("the real corpus is byte-identical", out.getvalue())

    def test_an_unknown_scenario_is_refused_with_the_names_that_do_exist(self):
        argv, saved = ["rehearse_forward.py", "--scenario", "hopeful"], sys.argv
        sys.argv = argv
        try:
            with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as stop:
                rf.main()
        finally:
            sys.argv = saved
        self.assertEqual(stop.exception.code, 2)
        self.assertIn("flat", err.getvalue())


class ItCanFail(unittest.TestCase):
    def test_an_audit_finding_inside_the_rehearsal_makes_the_rehearsal_fail(self):
        """Every check here has to be able to say no, including the one that audits the sealed entries.

        `audit_entries.audit` is patched to report one finding. The rehearsal must turn that into a failed check and a nonzero exit,
        because the alternative — a rehearsal that prints `all checks passed` while the audit under it disagrees — is the check that
        can only print pass (r92).
        """

        import audit_entries
        saved = audit_entries.audit
        audit_entries.audit = lambda rows, model: [{"kind": "injected", "index": 1, "detail": "a finding that is not real"}]
        try:
            checks = rf.run("flat", 5_000.0, 500.0)
            self.addCleanup(setattr, audit_entries, "audit", saved)
            self.addCleanup(rf.run, "flat", 5_000.0, 500.0)          # leave the scratch state as a passing run would
            failing = [c for c in checks if not c[1]]
            self.assertEqual(len(failing), 1, f"expected exactly the injected failure, got {[c[0] for c in failing]}")
            self.assertIn("no sealed entry contradicts itself", failing[0][0])
            self.assertIn("injected", failing[0][2], "a failure that does not say what failed is not a failure, it is noise")
        finally:
            audit_entries.audit = saved

    def test_main_reports_failed_checks_rather_than_printing_pass(self):
        import audit_entries
        saved = audit_entries.audit
        audit_entries.audit = lambda rows, model: [{"kind": "injected", "index": 1, "detail": "not real"}]
        argv, saved_argv = ["rehearse_forward.py", "--scenario", "flat"], sys.argv
        sys.argv = argv
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = rf.main()
        finally:
            sys.argv = saved_argv
            audit_entries.audit = saved
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out.getvalue())
        self.assertIn("CHECKS FAILED", out.getvalue())


class TheRehearsalIsWhatItClaims(unittest.TestCase):
    def test_the_scratch_book_is_never_the_real_book(self):
        """The tool's own guard, re-asserted from outside: the rehearsal writes a book named `rehearsal`, under a scratch root."""

        self.assertNotIn("rehearsal", [p.parent.name for p in BOOKS.glob("*/model.json")],
                         "a rehearsal book escaped into the real ledger directory")

    def test_the_scenarios_are_the_four_ways_a_month_can_be_abnormal(self):
        self.assertEqual(sorted(rf.SCENARIOS), ["crash", "divergent", "flat", "skipped"])
        self.assertEqual(set(rf.SEALS), set(rf.SCENARIOS), "a scenario without a seal expectation is a scenario nobody grades")

    def test_the_rehearsal_reads_the_same_opening_and_deposit_the_engine_uses(self):
        """A rehearsal priced at a different deposit than the books actually take proves nothing."""

        checks = rf.run("flat", paper.OPENING, paper.MONTHLY)
        self.assertTrue(all(c[1] for c in checks), [c[0] for c in checks if not c[1]])


#: A fetch that fetches nothing: it copies the archived snapshot into a directory whose name is a fetch stamp and repoints the pointer the
#: way the real fetcher does. Enough for the wiring to be judged, and no network in the suite — the real fetch is what `--scenario fetch`
#: exists to be run by hand, once, before a seal date.
FAKE_FETCH = (
    "import datetime as dt, json, shutil, sys, pathlib;"
    "out = pathlib.Path(sys.argv[1]);"
    "snap = out / 'snapshots' / dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ');snap.mkdir(parents=True);"
    "[shutil.copyfile(str(pathlib.Path('data/current')/f), str(snap/f))"
    " for f in ('market_daily.csv','cash_daily.csv','distributions_daily.csv')];"
    "(snap/'manifest.json').write_text(json.dumps({'methodology': 'fixture-fetch', 'coverage': {}}));"
    "tmp = out/'current.tmp';tmp.symlink_to('snapshots/' + snap.name);tmp.replace(out/'current');"
    "print('wrote fixture snapshot ' + str(snap))"
)


class TheFetchScenario(unittest.TestCase):
    """`--scenario fetch` rehearses the first command of the month. Offline here: only the wiring is under test, not the vendor."""

    def setUp(self):
        self.checks = rf.run_fetch(rf.next_seal_date(rf.corpus_last()),
                                   [sys.executable, "-c", FAKE_FETCH, "{out}"])

    def detail(self, needle):
        return next((name, passed, d) for name, passed, d in self.checks if needle in name)

    def test_the_scenario_reports_the_checks_that_make_a_fetch_rehearsed(self):
        self.assertEqual(len(self.checks), 7, [n for n, _p, _d in self.checks])
        self.assertTrue(all(p for _n, p, _d in self.checks),
                        [n for n, p, _d in self.checks if not p])

    def test_the_copy_gained_a_snapshot_only_a_fetch_could_have_named(self):
        name, passed, detail = self.detail("named by a fetch stamp")
        self.assertTrue(passed, detail)
        self.assertRegex(detail, r"current. -> \d{8}T\d{6}Z", f"a rehearsal must not pass this: {detail}")

    def test_the_manifest_is_checked_because_it_is_the_completion_marker(self):
        self.assertTrue(self.detail("manifest landed last")[1])

    def test_the_diff_tool_reports_the_directory_it_opened_and_it_was_the_copy(self):
        name, passed, detail = self.detail("which directory it opened")
        self.assertTrue(passed, f"corpus_diff must name the scratch tree it read: {detail}")

    def test_a_seal_is_due_or_refused_but_the_loop_never_crashes_on_a_fetched_corpus(self):
        name, passed, detail = self.detail("instead of crashing")
        self.assertTrue(passed, detail)
        self.assertTrue("sealed" in detail or "refused" in detail, detail)

    def test_the_real_archive_is_still_untouched_after_a_fetched_rehearsal(self):
        name, passed, detail = self.detail("no file under the real data")
        self.assertTrue(passed, detail)
        self.assertIn("the real corpus still ends", detail,
                      "the detail has to say what the archive looks like now, not merely that nothing moved")


class ThePublishedScenario(unittest.TestCase):
    """Round 116: the half of the month that is not the engine — the block above, run as an operator runs it, on a copy.

    The engine scenarios drive `paper.py` in-process on one scratch book. This drives eleven processes over the five live books, which is
    the only way the redirection that makes it disposable, and the refusal that keeps the month from being sealed twice, ever get tested.
    """

    @classmethod
    def setUpClass(cls):
        cls.checks = rf.run_published()
        cls.by_name = {name: (passed, detail) for name, passed, detail in cls.checks}

    def test_the_whole_published_block_ran_and_passed_on_the_first_real_seal_date(self):
        self.assertGreaterEqual(len(self.checks), 13, "a scenario that quietly ran four commands is not the published block")
        failed = [name for name, passed, _ in self.checks if not passed]
        self.assertEqual(failed, [], "\n".join(f"{n}: {d}" for n, p_, d in self.checks if not p_))
        steps = [name for name in self.by_name if "`tools/paper.py step" in name]
        shelf = rf.PAPER_ROOT / "books"
        live = sorted(d.name for d in shelf.iterdir() if (d / "ledger.jsonl").exists())
        self.assertEqual(len(steps), len(live) + 1, f"the block must seal the root and {live}")

    def test_the_month_refuses_to_be_sealed_twice(self):
        name = next((n for n in self.by_name if "twice" in n), None)
        self.assertIsNotNone(name, "a rehearsal that never re-runs the month has not rehearsed the likeliest operator slip")
        passed, detail = self.by_name[name]
        self.assertTrue(passed, detail)
        self.assertIn("already closed", detail)

    def test_the_real_tree_is_left_byte_identical_and_the_check_names_every_file(self):
        name = next(n for n in self.by_name if "real data/ tree" in n)
        passed, detail = self.by_name[name]
        self.assertTrue(passed, detail)
        self.assertIn("0 files changed", detail)
        self.assertGreater(len(rf.tree_manifest(rf.DATA_ROOT)), 20, "a manifest over one file would pass by construction")

    def test_only_the_fetch_is_dropped_and_the_dodge_points_at_the_scenario_that_runs_it(self):
        """Round 8 removed the second excuse: `corpus_diff.py` follows the resolver now, so the published block runs 12 of its 13 commands."""

        names = " ".join(self.by_name)
        self.assertNotIn("fetch_market_data", names.replace("REHEARSAL", ""), "a rehearsal that fetches can write a real snapshot")
        self.assertEqual(set(rf.SKIP), {"fetch_market_data.py"}, "a skipped command whose dodge is stale is a skipped command forever")
        self.assertIn("--scenario fetch", rf.SKIP["fetch_market_data.py"])
        self.assertIn("corpus_diff", names, "the diff belongs to the block, and it can now read a copy")

    def test_the_default_seal_date_is_the_one_the_objective_names(self):
        self.assertEqual(rf.next_seal_date(rf.corpus_last()), dt.date(2026, 9, 30))
        self.assertEqual(rf.next_seal_date(dt.date(2026, 9, 30)), dt.date(2026, 10, 30))
        self.assertEqual(rf.next_seal_date(dt.date(2026, 1, 15)), dt.date(2026, 1, 30), "2026-01-31 is a Saturday")

    def test_the_synthetic_corpus_is_named_as_such_and_says_what_it_invented(self):
        dir_ = Path(tempfile.mkdtemp(prefix="ba-test-published-"))
        try:
            snapshot = rf.build_published_copy(dir_, dt.date(2026, 9, 30))
            self.assertTrue(snapshot.name.startswith("REHEARSAL-"))
            side = json.loads((snapshot / "REHEARSAL.json").read_text())
            self.assertTrue(side["synthetic"])
            self.assertEqual(side["real_corpus_last_session"], str(rf.corpus_last()))
            self.assertIn("not_evidence", side)
            dates = [row["date"] for row in csv.DictReader((snapshot / "market_daily.csv").open(newline=""))]
            self.assertLessEqual(max(dates), "2026-09-30")
            self.assertGreater(max(dates), str(rf.corpus_last()), "the whole point was to make a seal due")
            self.assertFalse((dir_ / "data" / "current").readlink().is_absolute(),
                             "a pointer that resolves back into the real tree is not a copy")
        finally:
            shutil.rmtree(dir_, ignore_errors=True)

    def test_the_scenario_is_reachable_without_the_engine_scenarios(self):
        """The night before a seal date, the thing being doubted is the block, not the engine."""

        argv, saved = sys.argv, sys.argv[:]
        sys.argv = ["rehearse_forward.py", "--scenario", "published"]
        try:
            code = rf.main()
        finally:
            sys.argv = saved
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
