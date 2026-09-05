"""One reviewable freeze record, with an explicit draft/confirm workflow.

Confirmation records a deliberate research choice, not a security credential.
The identity contains everything shown for review and never changes when the
draft is confirmed. Reading a freeze never opens its original config or data.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping

from boring_alpha.research_contract import (
    FAMILY_ID, canonical_json, canonical_sha256, code_fingerprint,
    evaluator_fingerprint, require_digest, validate_contract,
)
from boring_alpha.research_family import PROTECTED_START


_IDENTITY_KEYS = {
    "strategy_id", "family_id", "strategy_spec_sha256", "contract",
    "code_sha256", "evaluator_sha256", "input_manifest_sha256",
    "charter_text", "charter_sha256",
}


def _legacy_contract(contract: Mapping) -> dict:
    required = {"strategy_id", "family_id", "strategy_spec_sha256", "synthetic", "periods",
                "tax_policy_sha256", "calendar_sha256", "calendar_authority_sha256"}
    if set(contract) != required:
        raise ValueError("BA-001 freeze contract has missing or extra fields")
    if contract["strategy_id"] != "BA-001" or contract["family_id"] != FAMILY_ID:
        raise ValueError("BA-001 freeze contract has an invalid strategy/family")
    require_digest(contract["strategy_spec_sha256"], "contract.strategy_spec_sha256")
    for key in ("tax_policy_sha256", "calendar_sha256", "calendar_authority_sha256"):
        require_digest(contract[key], f"contract.{key}")
    if type(contract["synthetic"]) is not bool:
        raise ValueError("contract.synthetic must be boolean")
    periods = contract["periods"]
    if not isinstance(periods, dict) or not periods or set(periods) - {"development", "validation", "sealed", "exploratory"}:
        raise ValueError("BA-001 freeze contract requires named periods")
    intervals = []
    for name, period in periods.items():
        if not isinstance(period, dict) or set(period) != {"start", "end", "status"}:
            raise ValueError("freeze periods require exact start, end and status")
        if period["status"] != ("unopened" if name == "sealed" else "seen"):
            raise ValueError("freeze period has an invalid evidence status")
        try:
            start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
        except (TypeError, ValueError) as exc:
            raise ValueError("freeze periods require fixed ISO dates") from exc
        if start > end or start.isoformat() != period["start"] or end.isoformat() != period["end"]:
            raise ValueError("freeze period has invalid date bounds")
        if not contract["synthetic"]:
            if name != "sealed" and end >= PROTECTED_START:
                raise ValueError(f"historical {name} cannot label protected dates on or after {PROTECTED_START} as seen")
            if name == "sealed" and start != PROTECTED_START:
                raise ValueError(f"historical sealed period must start at the family protected boundary {PROTECTED_START}")
        intervals.append((start, end))
    intervals.sort()
    if any(left[1] >= right[0] for left, right in zip(intervals, intervals[1:])):
        raise ValueError("freeze periods must not overlap")
    return json.loads(canonical_json(contract))


def _validated(record: object) -> dict:
    if not isinstance(record, Mapping) or set(record) != {"schema_version", "status", "identity", "confirmation"}:
        raise ValueError("freeze record has missing or extra fields")
    if type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise ValueError("unsupported freeze schema")
    if record["status"] not in ("draft", "confirmed"):
        raise ValueError("freeze status must be draft or confirmed")
    identity = record["identity"]
    if not isinstance(identity, Mapping) or set(identity) != _IDENTITY_KEYS:
        raise ValueError("freeze identity has missing or extra fields")
    strategy_id = identity["strategy_id"]
    if strategy_id not in ("BA-001", "BA-002") or identity["family_id"] != FAMILY_ID:
        raise ValueError("freeze identity has an unregistered strategy/family")
    for field in ("strategy_spec_sha256", "code_sha256", "evaluator_sha256", "input_manifest_sha256", "charter_sha256"):
        require_digest(identity[field], f"freeze.{field}")
    charter = identity["charter_text"]
    if not isinstance(charter, str) or not charter.strip():
        raise ValueError("freeze requires the complete nonempty charter text")
    if hashlib.sha256(charter.encode("utf-8")).hexdigest() != identity["charter_sha256"]:
        raise ValueError("freeze charter text does not match charter_sha256")
    contract = identity["contract"]
    if not isinstance(contract, Mapping):
        raise ValueError("freeze contract must be an object")
    contract = validate_contract(contract) if strategy_id == "BA-002" else _legacy_contract(contract)
    if contract["strategy_id"] != strategy_id or contract["family_id"] != identity["family_id"]:
        raise ValueError("freeze identity differs from its contract")
    if strategy_id == "BA-001" and contract["strategy_spec_sha256"] != identity["strategy_spec_sha256"]:
        raise ValueError("freeze strategy spec differs from its BA-001 contract")
    confirmation = record["confirmation"]
    if record["status"] == "draft":
        if confirmation is not None:
            raise ValueError("draft freeze must not contain a confirmation")
    else:
        if not isinstance(confirmation, Mapping) or set(confirmation) != {"reason", "confirmed_at"}:
            raise ValueError("confirmed freeze requires reason and confirmed_at")
        if not isinstance(confirmation["reason"], str) or not confirmation["reason"].strip():
            raise ValueError("freeze confirmation requires a nonempty reason")
        timestamp = confirmation["confirmed_at"]
        try:
            parsed = datetime.fromisoformat(timestamp)
        except (TypeError, ValueError) as exc:
            raise ValueError("freeze confirmation requires a UTC timestamp") from exc
        if not timestamp.endswith("Z") or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError("freeze confirmation requires a UTC timestamp")
    # Reject NaN/inf everywhere and return a detached JSON-only record.
    return json.loads(canonical_json(dict(record)))


def build_freeze(config, contract, *, input_manifest_sha256: str, charter_text: str,
                 code_sha256: str | None = None, evaluator_sha256: str | None = None) -> dict:
    """Build a draft without writing anything or reading original input paths."""
    if not isinstance(charter_text, str) or not charter_text.strip():
        raise ValueError("freeze requires the complete nonempty charter text")
    code = code_fingerprint() if code_sha256 is None else code_sha256
    evaluator = evaluator_sha256 if evaluator_sha256 is not None else (
        evaluator_fingerprint() if config.strategy.strategy_id == "BA-002" else code
    )
    return _validated({
        "schema_version": 1,
        "status": "draft",
        "identity": {
            "strategy_id": config.strategy.strategy_id,
            "family_id": FAMILY_ID,
            "strategy_spec_sha256": config.strategy_spec_sha256,
            "contract": contract,
            "code_sha256": code,
            "evaluator_sha256": evaluator,
            "input_manifest_sha256": input_manifest_sha256,
            "charter_text": charter_text,
            "charter_sha256": hashlib.sha256(charter_text.encode("utf-8")).hexdigest(),
        },
        "confirmation": None,
    })


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate freeze JSON field: {key}")
        result[key] = value
    return result


def load_freeze(path: str | Path, require_confirmed: bool = False) -> dict:
    """Load just this record; no config, calendar, market data or journal reads."""
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read research freeze {path}: {exc}") from exc
    record = _validated(record)
    if require_confirmed and record["status"] != "confirmed":
        raise ValueError("historical execution requires a confirmed research freeze")
    return record


def freeze_sha256(record: object) -> str:
    """Hash reviewed identity, excluding the later confirmation metadata."""
    return canonical_sha256(_validated(record)["identity"])


def archival_freeze(record: object) -> dict:
    """Identity-only draft envelope; live confirmation belongs in provenance.

    This copy is never execution approval. Historical archive classification
    separately requires a matching, externally confirmed freeze.
    """
    frozen = _validated(record)
    frozen['status'], frozen['confirmation'] = 'draft', None
    return frozen


def confirm_freeze(path: str | Path, *, expected_sha256: str, reason: str) -> dict:
    """Confirm the displayed full identity and initialize its run journal.

    Repeating the same confirmation is idempotent. A changed draft requires
    its newly displayed hash; neither a hash prefix nor a stale hash suffices.
    """
    require_digest(expected_sha256, "expected freeze hash")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("confirming a research freeze requires a nonempty reason")
    path = Path(path)
    record = load_freeze(path)
    if freeze_sha256(record) != expected_sha256:
        raise ValueError("freeze identity changed: review it and supply its full current hash")
    if not record["identity"]["contract"]["synthetic"]:
        from boring_alpha.research_family import canonical_journal_path
        from boring_alpha.research_state import RunJournal
        journal = RunJournal(canonical_journal_path(record["identity"]["strategy_id"]))
        if record["status"] == "confirmed":
            journal.validate()
        else:
            journal.initialize()
    if record["status"] == "confirmed":
        return record
    record["status"] = "confirmed"
    record["confirmation"] = {
        "reason": reason.strip(),
        "confirmed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    record = _validated(record)
    # One atomic publication; no lock, receipt, approval ledger or lease.
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as stream:
            temporary_path = Path(stream.name)
            stream.write(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return record
