"""Run-journal tests use fictional identities and temporary files, never data."""

from dataclasses import replace
from datetime import date
import json
import multiprocessing
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from boring_alpha.research_state import FrozenAccessIdentity, ResearchAccessError, RunJournal, resolve_family


def identity(**changes):
    return FrozenAccessIdentity(**{
        "candidate_id": "BA-002", "period": "sealed", "start": date(2030, 1, 1), "end": date(2030, 12, 31),
        "contract_sha256": "a" * 64, "code_sha256": "b" * 64, "policy_sha256": "c" * 64,
        "calendar_sha256": "d" * 64, "input_manifest_sha256": "e" * 64, "evaluator_sha256": "f" * 64,
        "synthetic": False, **changes,
    })


def crash_after_access(path, record):
    import os
    attempt = RunJournal(path).begin(FrozenAccessIdentity.from_dict(record), reveal_reason="fictional crash fixture")
    attempt.start_access()
    os._exit(0)


class RunJournalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "fictional-journal.json"
        self.journal = RunJournal(self.path)
        self.journal.initialize()
        self.identity = identity()

    def events(self):
        return json.loads(self.path.read_text())["events"]

    def first(self):
        attempt = self.journal.begin(self.identity, reveal_reason="explicit fictional first reveal")
        attempt.start_access()
        attempt.complete("fictional-first-artifact")
        return attempt

    def test_registered_family_is_not_a_candidate_rename_escape_hatch(self):
        self.assertEqual(resolve_family("BA-001"), "BA-TREND")
        self.assertEqual(resolve_family("BA-002"), "BA-TREND")
        for unknown in ("BA-003", "exploratory", "OTHER", "ba-002", []):
            with self.subTest(unknown=unknown), self.assertRaisesRegex(ResearchAccessError, "unregistered"):
                resolve_family(unknown)

    def test_identity_round_trip_and_each_bound_field_changes_hash(self):
        self.assertEqual(FrozenAccessIdentity.from_dict(self.identity.as_dict()), self.identity)
        for field in ("contract_sha256", "code_sha256", "policy_sha256", "calendar_sha256", "input_manifest_sha256", "evaluator_sha256"):
            with self.subTest(field=field):
                self.assertNotEqual(replace(self.identity, **{field: "0" * 64}).sha256, self.identity.sha256)
        self.assertNotEqual(replace(self.identity, end=date(2030, 12, 30)).sha256, self.identity.sha256)
        self.assertNotEqual(replace(self.identity, period="exploratory").sha256, self.identity.sha256)

    def test_malformed_identity_rejects_nonfinite_numbers_and_wrong_types(self):
        for changes in ({"code_sha256": float("nan")}, {"calendar_sha256": float("inf")},
                        {"synthetic": 1}, {"start": "2030-01-01"}, {"period": " "},
                        {"start": date(2031, 1, 1)}, {"policy_sha256": "A" * 64}):
            with self.subTest(changes=changes), self.assertRaises(ResearchAccessError):
                identity(**changes)
        corrupted = self.identity.as_dict()
        corrupted["family_id"] = "NEW-FAMILY"
        with self.assertRaisesRegex(ResearchAccessError, "lineage"):
            FrozenAccessIdentity.from_dict(corrupted)

    def test_initialization_contains_no_approval_and_preserves_existing_events(self):
        self.assertEqual(json.loads(self.path.read_text()), {"schema_version": 2, "events": []})
        self.first()
        before = self.path.read_bytes()
        self.journal.initialize()
        self.assertEqual(self.path.read_bytes(), before)

    def test_first_holdout_requires_reason_and_refusal_is_an_event(self):
        attempt = self.journal.begin(self.identity, reveal_reason="  ")
        self.assertEqual(self.events()[-1]["event"], "attempted")
        with self.assertRaisesRegex(ResearchAccessError, "reveal reason"):
            attempt.start_access()
        self.assertEqual([event["event"] for event in self.events()], ["attempted", "refused"])
        self.assertFalse(self.first().rerun)

    def test_access_is_durable_before_return_and_old_events_never_change(self):
        attempt = self.journal.begin(self.identity, reveal_reason="fictional reveal")
        before = self.events()
        attempt.start_access()
        self.assertEqual(self.events()[:len(before)], before)
        self.assertEqual(self.events()[-1]["event"], "access_started")
        before = self.events()
        attempt.complete("fictional-artifact")
        self.assertEqual(self.events()[:len(before)], before)
        self.assertEqual(self.events()[-1]["artifact"], "fictional-artifact")

    def test_identical_retry_needs_no_new_reveal_reason(self):
        self.first()
        retry = self.journal.begin(self.identity)
        retry.start_access()
        self.assertTrue(retry.rerun)
        self.assertFalse(retry.revealed_diagnostic)
        retry.complete("identical")

    def test_changed_candidate_cannot_reset_family_even_with_reveal_reason(self):
        self.first()
        renamed = self.journal.begin(replace(self.identity, candidate_id="BA-001"), reveal_reason="new name")
        with self.assertRaisesRegex(ResearchAccessError, "family.*already revealed"):
            renamed.start_access()
        self.assertEqual(self.events()[-1]["event"], "refused")

    def test_changed_overlapping_window_cannot_claim_a_fresh_reveal(self):
        self.first()
        for changes in ({"start": date(2030, 6, 1)}, {"end": date(2031, 1, 1)}, {"period": "exploratory"}):
            with self.subTest(changes=changes):
                attempt = self.journal.begin(replace(self.identity, **changes), reveal_reason="new request")
                with self.assertRaisesRegex(ResearchAccessError, "already revealed"):
                    attempt.start_access()

    def test_seen_runs_are_logged_without_reveal_ceremony_and_can_change(self):
        seen = identity(start=date(2018, 1, 1), end=date(2021, 12, 31), period="validation")
        for current in (seen, replace(seen, code_sha256="0" * 64)):
            attempt = self.journal.begin(current)
            attempt.start_access()
            attempt.complete("seen-artifact")
        self.assertEqual([event["event"] for event in self.events()], ["attempted", "access_started", "completed"] * 2)
        self.assertFalse(self.first().rerun)

    def test_synthetic_access_does_not_reveal_historical_coverage(self):
        synthetic = self.journal.begin(replace(self.identity, synthetic=True))
        synthetic.start_access()
        synthetic.complete("synthetic")
        missing_reason = self.journal.begin(self.identity)
        with self.assertRaisesRegex(ResearchAccessError, "reveal reason"):
            missing_reason.start_access()

    def test_failure_before_access_does_not_reveal_but_failure_after_access_does(self):
        with self.assertRaisesRegex(RuntimeError, "before"):
            with self.journal.begin(self.identity):
                raise RuntimeError("before")
        self.assertEqual([event["event"] for event in self.events()], ["attempted", "failed"])
        with self.assertRaisesRegex(RuntimeError, "after"):
            with self.journal.begin(self.identity, reveal_reason="fictional first reveal") as attempt:
                attempt.start_access()
                self.assertFalse(attempt.rerun)
                raise RuntimeError("after")
        retry = self.journal.begin(self.identity)
        retry.start_access()
        self.assertTrue(retry.rerun)
        retry.complete("retry")

    def test_hard_crash_leaves_reveal_and_releases_lock_for_exact_retry(self):
        child = multiprocessing.get_context("spawn").Process(target=crash_after_access, args=(str(self.path), self.identity.as_dict()))
        child.start()
        child.join(timeout=10)
        self.assertEqual(child.exitcode, 0)
        self.assertEqual(self.events()[-1]["event"], "access_started")
        retry = self.journal.begin(self.identity)
        retry.start_access()
        self.assertTrue(retry.rerun)
        retry.complete("after-crash")

    def test_concurrent_family_access_is_refused_and_journaled(self):
        barrier = threading.Barrier(2)
        successful, errors = [], []

        def access():
            attempt = RunJournal(self.path).begin(self.identity, reveal_reason="fictional concurrent reveal")
            barrier.wait(timeout=5)
            try:
                attempt.start_access()
                successful.append(attempt)
            except ResearchAccessError as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=access) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(len(successful), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("active", errors[0])
        self.assertEqual(sum(event["event"] == "access_started" for event in self.events()), 1)
        self.assertEqual(sum(event["event"] == "refused" for event in self.events()), 1)
        successful[0].complete("winner")

    def test_explicit_code_and_evaluator_repair_stays_revealed_diagnostic_on_retry(self):
        first = self.first()
        corrected = replace(self.identity, code_sha256="0" * 64, evaluator_sha256="1" * 64)
        repair = self.journal.begin(corrected, repair_of=first.attempt_id, repair_reason="fix documented evaluator bug")
        repair.start_access()
        self.assertEqual(repair.repair_of, first.attempt_id)
        self.assertTrue(repair.revealed_diagnostic)
        self.assertFalse(repair.rerun)
        self.assertTrue(self.events()[-1]["revealed_diagnostic"])
        repair.complete("diagnostic-repair")
        retry = self.journal.begin(corrected)
        retry.start_access()
        self.assertTrue(retry.rerun)
        self.assertTrue(retry.revealed_diagnostic)
        self.assertEqual(retry.repair_of, first.attempt_id)
        self.assertEqual(self.events()[-1]["repair_of"], first.attempt_id)
        retry.complete("diagnostic-rerun")
        original = self.journal.begin(self.identity)
        original.start_access()
        self.assertTrue(original.rerun)
        self.assertFalse(original.revealed_diagnostic)
        original.complete("original-reproduction")

    def test_repair_cannot_change_any_noncode_identity_field(self):
        first = self.first()
        changes = [{field: "0" * 64} for field in ("contract_sha256", "policy_sha256", "calendar_sha256", "input_manifest_sha256")]
        changes += [{"candidate_id": "BA-001"}, {"period": "exploratory"}, {"start": date(2030, 2, 1)}, {"end": date(2031, 1, 1)}, {"synthetic": True}]
        for change in changes:
            with self.subTest(change=change):
                repair = self.journal.begin(replace(self.identity, **change), repair_of=first.attempt_id, repair_reason="must not permit tuning")
                with self.assertRaisesRegex(ResearchAccessError, "only code/evaluator"):
                    repair.start_access()
                self.assertEqual(self.events()[-1]["event"], "refused")

    def test_repair_requires_real_prior_access_reference_and_reason(self):
        pending = self.journal.begin(self.identity)
        pending.fail("never accessed")
        for details in ({"repair_of": pending.attempt_id, "repair_reason": "not accessed"},
                        {"repair_of": "missing", "repair_reason": "unknown"},
                        {"repair_of": pending.attempt_id}, {"repair_reason": "no reference"}):
            with self.subTest(details=details):
                repair = self.journal.begin(self.identity, **details)
                with self.assertRaisesRegex(ResearchAccessError, "repair requires"):
                    repair.start_access()

    def test_missing_corrupt_and_unwritable_journal_refuse_without_reset(self):
        with self.assertRaisesRegex(ResearchAccessError, "journal"):
            RunJournal(self.path.parent / "missing.json").begin(self.identity)
        original = self.path.read_text()
        for bad in ("{", "{}", '{"schema_version": true, "events": []}', '{"schema_version": 2, "events": [NaN]}'):
            self.path.write_text(bad)
            with self.subTest(bad=bad), self.assertRaisesRegex(ResearchAccessError, "journal"):
                self.journal.initialize()
            self.assertEqual(self.path.read_text(), bad)
        self.path.write_text(original)
        with patch("boring_alpha.research_state.os.replace", side_effect=OSError("read only")):
            with self.assertRaisesRegex(ResearchAccessError, "journal"):
                self.journal.begin(self.identity)
        self.assertEqual(self.events(), [])

    def test_corrupt_lifecycle_refuses_instead_of_replenishing_holdout(self):
        self.first()
        contents = json.loads(self.path.read_text())
        contents["events"] = [event for event in contents["events"] if event["event"] != "access_started"]
        self.path.write_text(json.dumps(contents))
        with self.assertRaisesRegex(ResearchAccessError, "sequence"):
            self.journal.begin(self.identity)

    def test_completion_requires_access_and_context_requires_an_artifact(self):
        attempt = self.journal.begin(self.identity)
        with self.assertRaisesRegex(ResearchAccessError, "access"):
            attempt.complete("not-produced")
        attempt.fail("preflight did not continue")
        with self.journal.begin(self.identity, reveal_reason="fictional first reveal") as started:
            started.start_access()
            with self.assertRaisesRegex(ResearchAccessError, "twice"):
                started.start_access()
        self.assertEqual(self.events()[-1]["event"], "failed")
