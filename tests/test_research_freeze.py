"""Freeze workflow uses only fictional contracts and temporary records."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from boring_alpha.research_freeze import (
    build_freeze, confirm_freeze, freeze_sha256, load_freeze,
)
from test_criteria_ba002 import evidence_inputs
from test_research_contract import historical_contract


def draft(*, historical=False, strategy_id="BA-002"):
    config = SimpleNamespace(strategy=SimpleNamespace(strategy_id=strategy_id),
                             strategy_spec_sha256="1" * 64)
    if strategy_id == "BA-002":
        contract = historical_contract() if historical else evidence_inputs()["contract"]
    else:
        contract = {
            "strategy_id": "BA-001", "family_id": "BA-TREND",
            "strategy_spec_sha256": config.strategy_spec_sha256,
            "synthetic": not historical,
            "tax_policy_sha256": "5" * 64, "calendar_sha256": "6" * 64,
            "calendar_authority_sha256": "7" * 64,
            "periods": {"sealed": {"start": "2030-01-01", "end": "2030-12-31", "status": "unopened"}},
        }
    return build_freeze(config, contract, input_manifest_sha256="2" * 64,
                        charter_text="# Fictional research\nNo market observations.\n",
                        code_sha256="3" * 64, evaluator_sha256="4" * 64)


def write_record(tmp_path, record):
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_hash_is_exact_canonical_identity_not_confirmation():
    record = draft()
    expected = hashlib.sha256(json.dumps(record["identity"], sort_keys=True,
                                        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert freeze_sha256(record) == expected
    record["status"] = "confirmed"
    record["confirmation"] = {"reason": "Reviewed", "confirmed_at": "2026-09-04T12:00:00Z"}
    assert freeze_sha256(record) == expected


@pytest.mark.parametrize("field", ["strategy_spec_sha256", "code_sha256", "evaluator_sha256", "input_manifest_sha256"])
def test_every_operational_identity_hash_changes_freeze(field):
    original = draft()
    changed = deepcopy(original)
    changed["identity"][field] = "a" * 64
    assert freeze_sha256(changed) != freeze_sha256(original)


def test_charter_and_contract_changes_change_review_identity():
    original = draft()
    changed = deepcopy(original)
    changed["identity"]["charter_text"] += "An explicit amendment.\n"
    changed["identity"]["charter_sha256"] = hashlib.sha256(changed["identity"]["charter_text"].encode()).hexdigest()
    assert freeze_sha256(changed) != freeze_sha256(original)
    changed = deepcopy(original)
    changed["identity"]["contract"]["periods"]["development"]["start"] = "2010-02-01"
    assert freeze_sha256(changed) != freeze_sha256(original)


def test_build_defaults_fingerprints_and_detaches_contract():
    config = SimpleNamespace(strategy=SimpleNamespace(strategy_id="BA-002"), strategy_spec_sha256="1" * 64)
    contract = evidence_inputs()["contract"]
    with patch("boring_alpha.research_freeze.code_fingerprint", return_value="3" * 64) as code, patch(
        "boring_alpha.research_freeze.evaluator_fingerprint", return_value="4" * 64
    ) as evaluator, patch.object(Path, "read_bytes", side_effect=AssertionError("original input opened")):
        record = build_freeze(config, contract, input_manifest_sha256="2" * 64, charter_text="Fictional charter")
    code.assert_called_once_with()
    evaluator.assert_called_once_with()
    contract["periods"]["development"]["start"] = "1990-01-01"
    assert record["identity"]["contract"]["periods"]["development"]["start"] == "2010-01-01"


def test_legacy_evaluator_defaults_to_frozen_code():
    contract = draft(strategy_id="BA-001")["identity"]["contract"]
    config = SimpleNamespace(strategy=SimpleNamespace(strategy_id="BA-001"), strategy_spec_sha256="1" * 64)
    with patch("boring_alpha.research_freeze.evaluator_fingerprint", side_effect=AssertionError("BA-002 evaluator selected")):
        record = build_freeze(config, contract, input_manifest_sha256="2" * 64,
                              charter_text="Fictional legacy charter", code_sha256="3" * 64)
    assert record["identity"]["evaluator_sha256"] == "3" * 64


def test_reading_freeze_never_reads_referenced_inputs_or_journal(tmp_path):
    record = draft(historical=True)
    path = write_record(tmp_path, record)
    original = Path.read_text
    def guarded(actual, *args, **kwargs):
        assert actual == path, "reader opened something other than the freeze"
        return original(actual, *args, **kwargs)
    with patch.object(Path, "read_text", guarded), patch.object(Path, "read_bytes", side_effect=AssertionError("input read")):
        assert load_freeze(path) == record
        assert len(freeze_sha256(record)) == 64


def test_draft_is_not_confirmation(tmp_path):
    path = write_record(tmp_path, draft(historical=True))
    with pytest.raises(ValueError, match="confirmed"):
        load_freeze(path, require_confirmed=True)


def test_synthetic_confirmation_does_not_touch_a_real_journal(tmp_path):
    record = draft()
    path = write_record(tmp_path, record)
    journal = tmp_path / "must-not-exist.json"
    with patch("boring_alpha.research_state.RunJournal", side_effect=AssertionError("journal instantiated")):
        confirmed = confirm_freeze(path, expected_sha256=freeze_sha256(record),
                                   reason="  Review the fictional demo  ", journal_path=journal)
    assert confirmed["confirmation"]["reason"] == "Review the fictional demo"
    assert load_freeze(path, require_confirmed=True) == confirmed
    assert freeze_sha256(confirmed) == freeze_sha256(record)
    assert not journal.exists()


def test_historical_confirmation_initializes_one_journal_and_is_idempotent(tmp_path):
    record = draft(historical=True)
    path = write_record(tmp_path, record)
    journal = tmp_path / "journal.json"
    confirmed = confirm_freeze(path, expected_sha256=freeze_sha256(record),
                               reason="Fictional workflow test only", journal_path=journal)
    assert journal.is_file()
    assert json.loads(journal.read_text())["schema_version"] == 2
    journal_before = journal.read_bytes()
    freeze_before = path.read_bytes()
    assert confirm_freeze(path, expected_sha256=freeze_sha256(record),
                          reason="A retry must not rewrite confirmation", journal_path=journal) == confirmed
    assert journal.read_bytes() == journal_before
    assert path.read_bytes() == freeze_before


@pytest.mark.parametrize("expected", ["2" * 64, "1" * 12, "A" * 64, "", None])
def test_wrong_or_partial_hash_cannot_confirm_or_initialize_journal(tmp_path, expected):
    record = draft(historical=True)
    path = write_record(tmp_path, record)
    journal = tmp_path / "journal.json"
    with pytest.raises(ValueError):
        confirm_freeze(path, expected_sha256=expected, reason="Review", journal_path=journal)
    assert load_freeze(path)["status"] == "draft"
    assert not journal.exists()


@pytest.mark.parametrize("reason", ["", " \n ", None, 123])
def test_confirmation_requires_a_real_reason(tmp_path, reason):
    record = draft(historical=True)
    path = write_record(tmp_path, record)
    journal = tmp_path / "journal.json"
    with pytest.raises(ValueError, match="reason"):
        confirm_freeze(path, expected_sha256=freeze_sha256(record), reason=reason, journal_path=journal)
    assert not journal.exists()


def test_journal_failure_leaves_freeze_as_draft(tmp_path):
    record = draft(historical=True)
    path = write_record(tmp_path, record)
    with patch("boring_alpha.research_state.RunJournal.initialize", side_effect=ValueError("corrupt journal")):
        with pytest.raises(ValueError, match="corrupt journal"):
            confirm_freeze(path, expected_sha256=freeze_sha256(record), reason="Review", journal_path=tmp_path / "journal.json")
    assert load_freeze(path) == record


def test_failed_atomic_publication_preserves_draft_and_removes_temporary_file(tmp_path):
    record = draft()
    path = write_record(tmp_path, record)
    with patch("boring_alpha.research_freeze.os.replace", side_effect=OSError("disk error")):
        with pytest.raises(OSError, match="disk error"):
            confirm_freeze(path, expected_sha256=freeze_sha256(record), reason="Review", journal_path=tmp_path / "journal.json")
    assert load_freeze(path) == record
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("mutation", [
    "schema_bool", "schema_new", "extra_record", "missing_identity", "extra_identity",
    "bad_digest", "unknown_strategy", "unknown_family", "charter_tamper", "empty_charter",
    "nonfinite", "contract_change", "draft_with_confirmation", "confirmed_without_reason", "bad_time",
])
def test_strict_record_validation(tmp_path, mutation):
    record = draft()
    identity = record["identity"]
    if mutation == "schema_bool": record["schema_version"] = True
    elif mutation == "schema_new": record["schema_version"] = 2
    elif mutation == "extra_record": record["approved"] = True
    elif mutation == "missing_identity": identity.pop("code_sha256")
    elif mutation == "extra_identity": identity["original_path"] = "/not/a/freeze/field"
    elif mutation == "bad_digest": identity["input_manifest_sha256"] = "BAD"
    elif mutation == "unknown_strategy": identity["strategy_id"] = "BA-003"
    elif mutation == "unknown_family": identity["family_id"] = "UNSEEN-AGAIN"
    elif mutation == "charter_tamper": identity["charter_text"] += "Undeclared edit"
    elif mutation == "empty_charter": identity["charter_text"] = ""
    elif mutation == "nonfinite": identity["contract"]["initial_cash"] = float("nan")
    elif mutation == "contract_change": identity["contract"]["rule"]["horizons"] = [6, 9, 12]
    elif mutation == "draft_with_confirmation": record["confirmation"] = {"reason": "Bypass", "confirmed_at": "2026-09-04T12:00:00Z"}
    elif mutation == "confirmed_without_reason": record.update(status="confirmed", confirmation={"reason": "", "confirmed_at": "2026-09-04T12:00:00Z"})
    elif mutation == "bad_time": record.update(status="confirmed", confirmation={"reason": "Review", "confirmed_at": "2026-09-04T12:00:00"})
    with pytest.raises(ValueError):
        load_freeze(write_record(tmp_path, record))


@pytest.mark.parametrize("mutation", ["spec", "extra", "empty_periods", "open_end", "bad_status", "overlap"])
def test_legacy_contract_is_bound_and_strict(tmp_path, mutation):
    record = draft(strategy_id="BA-001")
    contract = record["identity"]["contract"]
    if mutation == "spec": contract["strategy_spec_sha256"] = "a" * 64
    elif mutation == "extra": contract["approval"] = True
    elif mutation == "empty_periods": contract["periods"] = {}
    elif mutation == "open_end": contract["periods"]["sealed"]["end"] = None
    elif mutation == "bad_status": contract["periods"]["sealed"]["status"] = "seen"
    elif mutation == "overlap": contract["periods"]["development"] = {"start": "2030-01-01", "end": "2030-06-01", "status": "seen"}
    with pytest.raises(ValueError):
        load_freeze(write_record(tmp_path, record))


def test_duplicate_json_fields_are_refused(tmp_path):
    path = tmp_path / "freeze.json"
    path.write_text('{"schema_version": 1, "schema_version": 2}')
    with pytest.raises(ValueError, match="duplicate"):
        load_freeze(path)
