"""A small, procedural run journal: log attempts and never forget a reveal.

This is a one-person lab's accident guard, not a cryptographic seal. A confirmed
freeze is checked by the caller; this file contains no approvals. Events are
append-only, written atomically, and one process may access a family at a time.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from types import MappingProxyType
import uuid


REGISTERED_FAMILIES = MappingProxyType({"BA-001": "BA-TREND", "BA-002": "BA-TREND"})
PROTECTED_FROM = MappingProxyType({"BA-TREND": date(2022, 1, 1)})
_HASH_FIELDS = ("contract_sha256", "code_sha256", "policy_sha256", "calendar_sha256",
                "input_manifest_sha256", "evaluator_sha256")


class ResearchAccessError(ValueError):
    """Refusal before parsing observations, or inability to record an attempt."""


def resolve_family(candidate_id: str) -> str:
    try:
        return REGISTERED_FAMILIES[candidate_id]
    except (KeyError, TypeError) as exc:
        raise ResearchAccessError(f"unregistered research candidate {candidate_id!r}; resolve reviewed lineage before input access") from exc


@dataclass(frozen=True)
class FrozenAccessIdentity:
    candidate_id: str
    period: str
    start: date
    end: date
    contract_sha256: str
    code_sha256: str
    policy_sha256: str
    calendar_sha256: str
    input_manifest_sha256: str
    evaluator_sha256: str
    synthetic: bool = False

    def __post_init__(self) -> None:
        resolve_family(self.candidate_id)
        if not isinstance(self.period, str) or not self.period.strip():
            raise ResearchAccessError("frozen access period must be nonempty")
        if type(self.start) is not date or type(self.end) is not date or self.start > self.end:
            raise ResearchAccessError("frozen access interval must contain ordered dates")
        if type(self.synthetic) is not bool:
            raise ResearchAccessError("frozen access synthetic marker must be boolean")
        for field in _HASH_FIELDS:
            if not isinstance(getattr(self, field), str) or re.fullmatch(r"[0-9a-f]{64}", getattr(self, field)) is None:
                raise ResearchAccessError(f"frozen access {field} must be a canonical SHA-256 hash")

    @property
    def family_id(self) -> str:
        return resolve_family(self.candidate_id)

    def as_dict(self) -> dict:
        return {"candidate_id": self.candidate_id, "family_id": self.family_id,
                "period": self.period, "start": self.start.isoformat(), "end": self.end.isoformat(),
                **{field: getattr(self, field) for field in _HASH_FIELDS}, "synthetic": self.synthetic}

    @classmethod
    def from_dict(cls, value: dict) -> "FrozenAccessIdentity":
        fields = {"candidate_id", "family_id", "period", "start", "end", "synthetic", *_HASH_FIELDS}
        if not isinstance(value, dict) or set(value) != fields:
            raise ResearchAccessError("frozen access identity has missing or unrecognized fields")
        try:
            start, end = date.fromisoformat(value["start"]), date.fromisoformat(value["end"])
        except (TypeError, ValueError) as exc:
            raise ResearchAccessError("frozen access dates must be ISO dates") from exc
        if value["start"] != start.isoformat() or value["end"] != end.isoformat():
            raise ResearchAccessError("frozen access dates must be canonical ISO dates")
        result = cls(candidate_id=value["candidate_id"], period=value["period"], start=start, end=end,
                     **{field: value[field] for field in _HASH_FIELDS}, synthetic=value["synthetic"])
        if value["family_id"] != result.family_id:
            raise ResearchAccessError("frozen access family differs from the reviewed lineage")
        return result

    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _records(value: dict) -> dict:
    """Validate the event stream and derive receipts without editing old events."""
    if not isinstance(value, dict) or set(value) != {"schema_version", "events"} or type(value["schema_version"]) is not int or value["schema_version"] != 2 or not isinstance(value["events"], list):
        raise ResearchAccessError("run journal must contain schema_version 2 and events")
    records = {}
    fields = {"attempted": {"identity", "reveal_reason", "repair_of", "repair_reason"},
              "access_started": {"rerun", "repair_of", "revealed_diagnostic"},
              "completed": {"artifact"}, "failed": {"reason"}, "refused": {"reason"}}
    for event in value["events"]:
        if not isinstance(event, dict) or not isinstance(event.get("event"), str) or event["event"] not in fields or set(event) != {"event", "attempt_id", "at"} | fields[event["event"]]:
            raise ResearchAccessError("run journal event has missing or unrecognized fields")
        kind, key = event["event"], event["attempt_id"]
        if not _text(key) or not _text(event["at"]):
            raise ResearchAccessError("run journal event identity/time is invalid")
        if kind == "attempted":
            if key in records or any(event[field] is not None and not _text(event[field]) for field in ("reveal_reason", "repair_of", "repair_reason")):
                raise ResearchAccessError("run journal attempted event is invalid")
            records[key] = {**event, "identity": FrozenAccessIdentity.from_dict(event["identity"]), "accessed": False}
        else:
            record = records.get(key)
            allowed = {"access_started": {"attempted"}, "completed": {"access_started"},
                       "failed": {"attempted", "access_started"}, "refused": {"attempted"}}
            if record is None or record["event"] not in allowed[kind]:
                raise ResearchAccessError("run journal event sequence is invalid")
            if kind == "access_started":
                if type(event["rerun"]) is not bool or type(event["revealed_diagnostic"]) is not bool or (event["repair_of"] is not None and not _text(event["repair_of"])):
                    raise ResearchAccessError("run journal access flags must be boolean")
                if event["revealed_diagnostic"] != (event["repair_of"] is not None):
                    raise ResearchAccessError("run journal diagnostic access must retain its repair reference")
                record["accessed"] = True
            elif not _text(event.get("artifact", event.get("reason"))):
                raise ResearchAccessError("run journal completion/failure detail is invalid")
            record.update(event)
    return records


def _durable_write(path: Path, value: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{path.name}.", dir=path.parent, delete=False) as handle:
            temporary = handle.name
            handle.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            os.unlink(temporary)


class RunJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        """Explicit setup only; preserve existing events and imply no approval."""
        if self.path.exists() or self.path.is_symlink():
            with self._locked():
                return
        try:
            with self.path.open("xb") as handle:
                handle.write(b'{"schema_version": 2, "events": []}\n')
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise ResearchAccessError(f"run journal cannot be initialized: {exc}") from exc

    @contextmanager
    def _locked(self):
        try:
            if not self.path.is_file() or self.path.is_symlink():
                raise ResearchAccessError("run journal must be an existing regular, non-symlink file; initialize it explicitly")
            with self.path.with_name(self.path.name + ".lock").open("a+b") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    value = json.loads(self.path.read_text())
                    _records(value)
                    yield value
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except ResearchAccessError:
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ResearchAccessError(f"run journal cannot be read or durably written: {exc}") from exc

    def _append(self, value: dict, key: str, kind: str, **details) -> None:
        value["events"].append({"event": kind, "attempt_id": key, "at": datetime.now(timezone.utc).isoformat(), **details})
        _records(value)
        _durable_write(self.path, value)

    def begin(self, identity: FrozenAccessIdentity, *, reveal_reason=None, repair_of=None, repair_reason=None) -> "AccessAttempt":
        if not isinstance(identity, FrozenAccessIdentity):
            raise ResearchAccessError("a validated frozen access identity is required")
        details = {"reveal_reason": reveal_reason, "repair_of": repair_of, "repair_reason": repair_reason}
        if any(value is not None and not isinstance(value, str) for value in details.values()):
            raise ResearchAccessError("reveal and repair details must be text")
        details = {key: (value.strip() or None) if value is not None else None for key, value in details.items()}
        key = uuid.uuid4().hex
        with self._locked() as value:
            self._append(value, key, "attempted", identity=identity.as_dict(), **details)
        return AccessAttempt(self, identity, key)


class AccessAttempt:
    def __init__(self, journal: RunJournal, identity: FrozenAccessIdentity, attempt_id: str) -> None:
        self.journal, self.identity, self.attempt_id = journal, identity, attempt_id
        self.rerun, self.repair_of, self.revealed_diagnostic = False, None, False
        self._execution_lock, self._started, self._finished = None, False, False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if not self._finished:
            self.fail(str(exc) or type(exc).__name__ if exc is not None else "attempt exited without a completed artifact")
        return False

    def _release(self) -> None:
        if self._execution_lock is not None:
            fcntl.flock(self._execution_lock.fileno(), fcntl.LOCK_UN)
            self._execution_lock.close()
            self._execution_lock = None

    def _access_error(self, record, previous) -> str | None:
        protected = not self.identity.synthetic and self.identity.end >= PROTECTED_FROM[self.identity.family_id]
        self.rerun = any(other["identity"] == self.identity for other in previous.values())
        overlaps = [other for other in previous.values() if not other["identity"].synthetic
                    and other["identity"].family_id == self.identity.family_id
                    and other["identity"].end >= PROTECTED_FROM[self.identity.family_id]
                    and other["identity"].start <= self.identity.end and self.identity.start <= other["identity"].end]
        if record["repair_of"] is not None or record["repair_reason"] is not None:
            original = previous.get(record["repair_of"])
            stable = lambda item: {key: val for key, val in item.as_dict().items() if key not in {"code_sha256", "evaluator_sha256"}}
            if not protected or original is None or not record["repair_reason"] or original not in overlaps or any(stable(other["identity"]) != stable(self.identity) for other in overlaps):
                return "repair requires a prior accessed attempt, a reason, and identical candidate/contract/window/policy/calendar/inputs; only code/evaluator may change"
            self.repair_of, self.revealed_diagnostic = record["repair_of"], True
        elif protected and overlaps and not self.rerun:
            return "this family's overlapping coverage is already revealed; use an identical frozen rerun or an explicit code/evaluator repair"
        elif protected and not overlaps and not record["reveal_reason"]:
            return "first holdout access requires a nonempty reveal reason"
        if self.rerun:
            self.revealed_diagnostic = self.revealed_diagnostic or any(other.get("revealed_diagnostic", False) for other in previous.values() if other["identity"] == self.identity)
            if self.revealed_diagnostic and self.repair_of is None:
                self.repair_of = next(other["repair_of"] for other in previous.values()
                                      if other["identity"] == self.identity and other.get("repair_of"))
        return None

    def start_access(self) -> None:
        if self._started or self._finished:
            raise ResearchAccessError("this attempt cannot start access twice")
        error = None
        try:
            self._execution_lock = self.journal.path.with_name(f"{self.journal.path.name}.{self.identity.family_id}.access.lock").open("a+b")
            try:
                fcntl.flock(self._execution_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                error = "another attempt in this research family is active"
            with self.journal._locked() as value:
                records = _records(value)
                record = records[self.attempt_id]
                if record["event"] != "attempted" or record["identity"] != self.identity:
                    raise ResearchAccessError("run journal attempt changed before access")
                error = error or self._access_error(record, {key: row for key, row in records.items() if row["accessed"]})
                self.journal._append(value, self.attempt_id, "refused" if error else "access_started",
                                     **({"reason": error} if error else {"rerun": self.rerun, "repair_of": self.repair_of, "revealed_diagnostic": self.revealed_diagnostic}))
            if error:
                self._finished = True
                raise ResearchAccessError(error)
            self._started = True
        except BaseException as exc:
            self._release()
            if isinstance(exc, OSError):
                raise ResearchAccessError(f"run journal access cannot be durably recorded: {exc}") from exc
            raise

    def complete(self, artifact: str | Path) -> None:
        if not self._started or self._finished:
            raise ResearchAccessError("artifact completion requires an active access attempt")
        if not isinstance(artifact, (str, Path)) or not _text(str(artifact)):
            raise ResearchAccessError("completed attempt must identify its artifact")
        self._finish("completed", artifact=str(artifact))

    def fail(self, reason: str) -> None:
        if not self._finished:
            self._finish("failed", reason=reason if _text(reason) else "unspecified execution failure")

    def _finish(self, kind: str, **details) -> None:
        try:
            with self.journal._locked() as value:
                self.journal._append(value, self.attempt_id, kind, **details)
            self._finished = True
        finally:
            self._release()
