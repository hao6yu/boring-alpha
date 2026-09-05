"""Independent, immutable expected sessions for BA-002's coverage checks.

This module consumes an archived authority's enumerated sessions. It neither
invents exchange holidays nor derives sessions from the data being checked.
The synthetic marker describes a fixture and never authorizes historical use.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _month(day: date, offset: int = 0) -> tuple[int, int]:
    year, zero_month = divmod(day.year * 12 + day.month - 1 + offset, 12)
    return year, zero_month + 1


def _dates(values: object, name: str) -> tuple[date, ...]:
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"calendar {name} must be an array of ISO dates")
    try:
        result = tuple(date.fromisoformat(value) for value in values)
    except ValueError as exc:
        raise ValueError(f"calendar {name} must contain ISO dates") from exc
    if list(values) != [value.isoformat() for value in result]:
        raise ValueError(f"calendar {name} must contain canonical ISO dates")
    if tuple(sorted(set(result))) != result:
        raise ValueError(f"calendar {name} must be unique and chronologically sorted")
    return result


@dataclass(frozen=True)
class SessionRequirements:
    decision_date: date
    warmup_start: date
    evaluation_sessions: tuple[date, ...]
    required_sessions: tuple[date, ...]
    anchors: Mapping[date, Mapping[int, date]]


@dataclass(frozen=True)
class SessionCalendar:
    source: str
    version: str
    coverage_start: date
    coverage_end: date
    sessions: tuple[date, ...]
    synthetic: bool = False
    closures: tuple[date, ...] = ()
    half_days: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("calendar source must be a nonempty independent authority")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("calendar version must be nonempty")
        if type(self.synthetic) is not bool:
            raise ValueError("calendar synthetic must be boolean")
        if type(self.coverage_start) is not date or type(self.coverage_end) is not date:
            raise ValueError("calendar coverage bounds must be dates")
        if self.coverage_start > self.coverage_end:
            raise ValueError("calendar coverage is reversed")
        for name in ("sessions", "closures", "half_days"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(type(day) is not date for day in values):
                raise ValueError(f"calendar {name} must be an immutable tuple of dates")
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"calendar {name} must be unique and chronologically sorted")
            if any(not self.coverage_start <= day <= self.coverage_end for day in values):
                raise ValueError(f"calendar {name} falls outside declared coverage")
        if not self.sessions:
            raise ValueError("calendar has no sessions")
        if set(self.closures) & set(self.sessions):
            raise ValueError("calendar closure is also declared an open session")
        if not set(self.half_days) <= set(self.sessions):
            raise ValueError("calendar half-days must be open sessions")

    @classmethod
    def from_dict(cls, value: dict) -> "SessionCalendar":
        required = {"schema_version", "source", "version", "coverage_start", "coverage_end", "sessions", "synthetic"}
        allowed = required | {"closures", "half_days", "sha256"}
        if not isinstance(value, dict) or not required <= value.keys() or not value.keys() <= allowed:
            raise ValueError("calendar artifact has missing or unrecognized fields")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("calendar schema_version must be 1")
        try:
            bounds = [date.fromisoformat(value[key]) for key in ("coverage_start", "coverage_end")]
        except (ValueError, TypeError) as exc:
            raise ValueError("calendar coverage bounds must be ISO dates") from exc
        if [value["coverage_start"], value["coverage_end"]] != [day.isoformat() for day in bounds]:
            raise ValueError("calendar coverage bounds must be canonical ISO dates")
        result = cls(
            source=value["source"], version=value["version"],
            coverage_start=bounds[0], coverage_end=bounds[1],
            sessions=_dates(value["sessions"], "sessions"), synthetic=value["synthetic"],
            closures=_dates(value.get("closures", []), "closures"),
            half_days=_dates(value.get("half_days", []), "half_days"),
        )
        if "sha256" in value and value["sha256"] != result.sha256:
            raise ValueError("calendar artifact hash does not match its canonical content")
        return result

    @classmethod
    def load(cls, path: str | Path) -> "SessionCalendar":
        try:
            return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"calendar artifact cannot be read: {exc}") from exc

    def as_dict(self) -> dict:
        return {
            "schema_version": 1, "source": self.source, "version": self.version,
            "coverage_start": self.coverage_start.isoformat(), "coverage_end": self.coverage_end.isoformat(),
            "sessions": [day.isoformat() for day in self.sessions], "synthetic": self.synthetic,
            "closures": [day.isoformat() for day in self.closures],
            "half_days": [day.isoformat() for day in self.half_days],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical(self.as_dict())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def authority_sha256(self) -> str:
        return hashlib.sha256(_canonical({
            "schema_version": 1, "source": self.source,
            "version": self.version, "synthetic": self.synthetic,
        })).hexdigest()

    def _require_coverage(self, start: date, end: date) -> None:
        if type(start) is not date or type(end) is not date or start > end:
            raise ValueError("calendar request has invalid date bounds")
        if self.coverage_start > start or self.coverage_end < end:
            raise ValueError(f"calendar coverage does not reach required interval {start} through {end}")

    def expected_sessions(self, start: date, end: date) -> tuple[date, ...]:
        self._require_coverage(start, end)
        sessions = tuple(day for day in self.sessions if start <= day <= end)
        if not sessions:
            raise ValueError(f"calendar has no expected session in {start} through {end}")
        return sessions

    def _month_end(self, year: int, month: int) -> date:
        return self.expected_sessions(date(year, month, 1), date(year, month, monthrange(year, month)[1]))[-1]

    def requirements(
        self, start: date, end: date, horizons: Iterable[int], *, warmup_months: int = 15
    ) -> SessionRequirements:
        horizons = tuple(horizons)
        if not horizons or any(type(h) is not int or h <= 0 for h in horizons) or len(set(horizons)) != len(horizons):
            raise ValueError("calendar horizons must be distinct positive integers")
        if type(warmup_months) is not int or warmup_months < max(horizons):
            raise ValueError("calendar warmup must be an integer at least as long as every horizon")
        evaluation = self.expected_sessions(start, end)
        decision = self._month_end(*_month(evaluation[0], -1))
        warmup_start = self._month_end(*_month(decision, -warmup_months))
        required = self.expected_sessions(warmup_start, end)
        # Include the preceding decision and every decision that could execute
        # within the evaluation. Coverage must prove each whole anchor month.
        decisions = {decision}
        for year, month in sorted({_month(day) for day in evaluation}):
            # A partly observed final month is not a proven month end and
            # cannot execute a subsequent decision inside this run anyway.
            month_end = date(year, month, monthrange(year, month)[1])
            if month_end <= end:
                candidate = self._month_end(year, month)
                if candidate < evaluation[-1]:
                    decisions.add(candidate)
        anchors = {
            day: MappingProxyType({horizon: self._month_end(*_month(day, -horizon)) for horizon in horizons})
            for day in sorted(decisions)
        }
        return SessionRequirements(decision, warmup_start, evaluation, required, MappingProxyType(anchors))

    def validate_inputs(
        self, data: MarketData, distributions: DistributionTable,
        symbols: tuple[str, ...], start: date, end: date, horizons: Iterable[int], *, warmup_months: int = 15,
    ) -> SessionRequirements:
        req = self.requirements(start, end, horizons, warmup_months=warmup_months)
        if not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("calendar coverage requires distinct symbols")
        expected = set(req.required_sessions)

        def check(actual: Iterable[date], label: str) -> None:
            observed = {day for day in actual if req.warmup_start <= day <= end}
            if observed != expected:
                missing, unexpected = sorted(expected - observed), sorted(observed - expected)
                raise ValueError(
                    f"{label} calendar coverage mismatch: missing {missing[:5]}, unexpected {unexpected[:5]}"
                )

        check(data.dates, "price")
        check(data.cash_factors, "cash")
        for symbol in symbols:
            check((day for day in data.dates if symbol in data.by_date[day]), f"price {symbol}")
            check(distributions.symbol_dates.get(symbol, ()), f"distribution {symbol}")
        return req

    def validate_output_sessions(self, dates: Iterable[date], start: date, end: date) -> None:
        if tuple(dates) != self.expected_sessions(start, end):
            raise ValueError("output curve sessions do not match the independent calendar's exact evaluation sessions")
