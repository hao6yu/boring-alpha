"""The monthly runner may only do what the published procedure says, in the order it says it, and must stop when anything fails.

`tools/monthly.py` is orchestration, and orchestration is where a careful project dies: a fetch that does not happen before a seal, a
report printed off a chain that failed to verify, a `--force` that nobody remembers adding. So these tests do not check that the
commands work — each tool has its own file for that — they check that the runner cannot be anything other than the runbook plus the
books on disk. The command list is re-parsed from `docs/RUNBOOK.md` here and compared to the runner's own reading, so a change to the
document is a change to the plan or a failing test (r89: publish the procedure, let tests re-derive it).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import monthly                                           # noqa: E402
import paper                                             # noqa: E402


class Stub:
    """Replace the runner's subprocess call with a script: return codes per matching fragment."""

    def __init__(self, fail_on: str | None = None, codes: dict[str, int] | None = None):
        self.calls: list[list[str]] = []
        self.fail_on = fail_on
        self.codes = codes or {}
        self.saved = None

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        code = 0
        for fragment, value in self.codes.items():
            if fragment in joined:
                code = value
        if self.fail_on and self.fail_on in joined:
            code = 1
        return subprocess.CompletedProcess(argv, code, stdout=f"stub output for {joined}", stderr="")

    def __enter__(self):
        self.saved = monthly.subprocess.run
        monthly.subprocess.run = self
        return self

    def __exit__(self, *exc):
        monthly.subprocess.run = self.saved


def run_main(argv: list[str]) -> tuple[int, str]:
    saved, sys.argv = sys.argv, ["monthly.py", *argv]
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = monthly.main()
    finally:
        sys.argv = saved
    return code, out.getvalue()


class ThePlanIsTheRunbook(unittest.TestCase):
    def test_the_runner_and_the_document_read_the_same_block_the_same_way(self):
        block = re.search(r"```sh\n(.*?)\n```", (ROOT / "docs" / "RUNBOOK.md").read_text(), re.DOTALL).group(1)
        published = [l.split("#")[0].strip() for l in block.splitlines() if l.split("#")[0].strip()]
        from_plan = [" ".join(row[0]) for row in monthly.plan()
                     if row[1] == "published procedure"]
        self.assertEqual(from_plan, published)

    def test_every_book_on_disk_is_sealed_even_though_the_document_names_only_one(self):
        sealed = {row[0][row[0].index("--book") + 1] for row in monthly.plan() if "step" in row[0] and "--book" in row[0]}
        self.assertEqual(sealed, set(monthly.books_on_disk()))
        self.assertIn("tilt_band", sealed)

    def test_the_checks_come_after_the_seals_and_the_fetch_comes_first(self):
        names = [" ".join(row[0]) for row in monthly.plan()]
        fetch = next(i for i, n in enumerate(names) if "fetch_market_data" in n)
        seals = [i for i, n in enumerate(names) if " step" in n]
        checks = [i for i, n in enumerate(names) if "verify" in n or "audit_entries" in n]
        self.assertLess(fetch, min(seals), "a seal may not run before the corpus moves")
        self.assertLess(max(seals), min(checks), "a check must run after the seals it is checking")

    def test_it_names_the_integrity_and_screen_commands_by_name(self):
        names = " ".join(" ".join(row[0]) for row in monthly.plan())
        for needed in ("journalctl.py verify", "audit_entries.py", "forward_p0.py --status", "paper.py compare"):
            self.assertIn(needed, names)


class ASealThatIsNotDueIsSkippedAndSaidOutLoud(unittest.TestCase):
    def test_a_corpus_that_has_not_moved_makes_no_seal_due(self):
        head = monthly.head_of("tilt_band")
        self.assertIsNotNone(head)
        self.assertIn("already closed", monthly.not_due("tilt_band", head.asof))

    def test_a_corpus_one_session_later_makes_every_seal_due(self):
        head = monthly.head_of("tilt_band")
        self.assertIsNone(monthly.not_due("tilt_band", head.asof + dt.timedelta(days=1)))

    def test_a_book_with_no_anchor_is_refused_rather_than_sealed_from_nothing(self):
        self.assertEqual(monthly.not_due("no_such_book", dt.date(2026, 10, 30)), "the book has no anchor")

    def test_a_not_due_seal_is_logged_as_skipped_and_the_run_still_succeeds(self):
        rows = monthly.plan()
        with Stub() as stub:
            ran, passed, log = monthly.run(rows)
        self.assertEqual(ran, len(rows))
        self.assertEqual(passed, len(rows))
        skipped = [r for r in log if r.get("skipped")]
        self.assertTrue(skipped, "no seal was marked not due, so this test proves nothing")
        self.assertEqual(len(skipped), len(monthly.books_on_disk()) + 1, "the root book has a seal too")
        for command in stub.calls:                                   # nothing that writes may have run
            self.assertNotIn("step", command)


class AFailureStopsTheMonth(unittest.TestCase):
    def test_the_first_failing_command_ends_the_run_and_the_rest_never_happen(self):
        rows = monthly.plan()
        with Stub(fail_on="audit_entries") as stub:
            ran, passed, log = monthly.run(rows)
        self.assertLess(passed, ran)
        self.assertEqual(log[-1]["exit"], 1)
        wanted = next(i for i, row in enumerate(rows) if "audit_entries" in " ".join(row[0]))
        due_before = sum(1 for row in rows[:wanted + 1] if not (row[2] if len(row) > 2 else None))
        self.assertEqual(len(stub.calls), due_before, "the runner kept going past the command that failed")
        self.assertTrue(any("audit_entries" in c for c in stub.calls[-1]))

    def test_a_stopped_run_prints_no_summary_because_a_half_month_is_not_a_month(self):
        with Stub(fail_on="journalctl") as stub:
            code, text = run_main([])
        self.assertEqual(code, 1)
        self.assertIn("STOPPED", text)
        self.assertIn("no summary is printed", text)
        self.assertNotIn("the stopping conditions again", text)
        self.assertNotIn("tools/paper.py compare", " ".join(" ".join(c) for c in stub.calls))

    def test_a_clean_run_ends_with_the_screen_read_after_the_seals(self):
        with Stub(codes={"fetch_market_data": 0}) as stub:
            code, text = run_main([])
        self.assertEqual(code, 0)
        self.assertIn("after the seals", text)
        self.assertEqual(" ".join(" ".join(c) for c in stub.calls).count("forward_p0.py --status"), 2,
                         "the screen runs once before and once after: the second reading is the one that matters")


class TheRunnerTakesNoKnobs(unittest.TestCase):
    def test_there_is_no_way_to_make_it_trump_a_refusal(self):
        saved, sys.argv = sys.argv, ["monthly.py", "--help"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                monthly.main()
        finally:
            sys.argv = saved
        text = out.getvalue().lower()
        for forbidden in ("--force", "--yes", "--tilt", "--band", "--skip-verify", "--asof"):
            self.assertNotIn(forbidden, text, f"{forbidden} would let an operator overrule a refusal")
        self.assertIn("--dry-run", text)

    def test_the_interpreter_is_the_one_running_this_file_not_a_hardcoded_path(self):
        resolved = monthly.resolve([".venv/bin/python", "tools/paper.py", "step"])
        self.assertEqual(resolved[0], sys.executable)
        self.assertEqual(resolved[1:], ["tools/paper.py", "step"])

    def test_a_command_that_is_not_an_interpreter_is_left_alone(self):
        self.assertEqual(monthly.resolve(["git", "status"]), ["git", "status"])

    def test_the_runbook_points_at_the_runner_so_the_document_and_the_tool_are_one_thing(self):
        text = (ROOT / "docs" / "RUNBOOK.md").read_text()
        self.assertIn("tools/monthly.py", text)


class TheDryRunRunsNothing(unittest.TestCase):
    def test_it_prints_the_whole_plan_and_calls_nothing(self):
        with Stub() as stub:
            code, text = run_main(["--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(stub.calls, [], "a dry run that executes is a wet run")
        self.assertGreaterEqual(text.count(".venv/bin/python"), len(monthly.published_commands()))
        self.assertIn("not due", text)


if __name__ == "__main__":
    unittest.main()
