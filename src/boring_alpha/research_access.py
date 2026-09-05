"""Profile preflight and explicit run context for a small, local research lab.

MarketData contains market observations only. This module owns the run journal,
read-once input snapshot and disk-code baseline. A confirmed freeze is reviewed
once; ordinary seen runs reuse it. Only first holdout access needs --reveal.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from boring_alpha.config import AppConfig
from boring_alpha.data.calendar import SessionCalendar
from boring_alpha.research_contract import canonical_sha256, contract_sha256, evaluator_fingerprint

PROTECTED_START = date(2022, 1, 1)


def capture_execution_identity() -> tuple[str, str]:
    from boring_alpha.report import code_fingerprint
    return code_fingerprint(), evaluator_fingerprint()


@dataclass(frozen=True)
class ResearchContext:
    contract: dict
    calendar: SessionCalendar
    freeze: dict

    @property
    def approved_contract(self):
        return self.contract if self.freeze["status"] == "confirmed" and not self.contract["synthetic"] else None


@dataclass(frozen=True)
class CapturedResearchInputs:
    """Read once: hashes, computation and archived inputs describe the same bytes."""
    sources: Mapping[str, bytes]
    manifests: Mapping[str, bytes]
    source_paths: Mapping[str, str]

    def __post_init__(self):
        for field in ("sources", "manifests"):
            values = getattr(self, field)
            if any(type(raw) is not bytes for raw in values.values()):
                raise ValueError("captured research inputs must be immutable bytes")
            object.__setattr__(self, field, MappingProxyType(dict(values)))
        object.__setattr__(self, "source_paths", MappingProxyType(dict(self.source_paths)))

    @property
    def sha256(self):
        hashes = {key: hashlib.sha256(raw).hexdigest() for key, raw in self.sources.items()}
        hashes.update({f"{key}_manifest": hashlib.sha256(raw).hexdigest() for key, raw in self.manifests.items()})
        return canonical_sha256({"identity_version": "raw-access-inputs-v1", "sha256": hashes})

    def manifest(self, label):
        raw = self.manifests.get(label)
        if raw is None:
            return None
        try:
            record = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"captured {label} manifest is not readable JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f"captured {label} manifest must be an object")
        return record


def capture_inputs(config):
    paths = {"prices": config.data.prices_path, "cash": config.data.cash_path}
    if config.tax is not None:
        paths["distributions"] = config.tax.distributions_path
    sources, manifests = {}, {}
    for label, path in paths.items():
        if path is None:
            raise ValueError(f"an explicit {label} input is required")
        sources[label] = path.read_bytes()
        manifest_path = path.parent / "manifest.json"
        if manifest_path.is_file():
            manifests[label] = manifest_path.read_bytes()
    return CapturedResearchInputs(sources, manifests, {key: str(path) for key, path in paths.items()})


def synthetic_input_sha256(config):
    """Generator settings, not config locations or selected evaluation window.

    This descriptor is for fictional fixtures only; historical freezes bind
    the actual captured source and manifest bytes instead.
    """
    data = config.data
    if data.source != 'synthetic':
        raise ValueError('a synthetic input descriptor requires synthetic data')
    return canonical_sha256({
        'generator': 'synthetic-v1', 'symbols': list(config.strategy.symbols),
        'start': str(data.start), 'end': str(data.end), 'seed': data.seed,
        'annual_cash_rate': data.annual_cash_rate, 'regime': data.regime,
    })


@dataclass
class RunContext:
    research: ResearchContext | None
    execution_identity: tuple[str, str]
    inputs: CapturedResearchInputs | None = None
    attempt: object | None = None
    artifact_path: str | None = None

    def verify(self):
        if capture_execution_identity() != self.execution_identity:
            raise ValueError("implementation or evaluator changed during execution; refusing mixed-code evidence")
        return self.execution_identity

    @property
    def revealed_diagnostic(self):
        return bool(self.attempt and self.attempt.revealed_diagnostic)

    def finish(self, error=None):
        if self.attempt is not None:
            if error is not None or self.artifact_path is None:
                self.attempt.fail(str(error or "run ended without a completed artifact"))
            else:
                self.attempt.complete(self.artifact_path)
            self.attempt = None


@dataclass(frozen=True)
class LoadedRun:
    data: object
    context: RunContext


def _selected_context(config):
    from boring_alpha.research_freeze import load_freeze
    if config.research is None:
        raise ValueError("research calendar and freeze paths are required; use research prepare")
    freeze = load_freeze(config.research.freeze_path, require_confirmed=config.data.source != "synthetic")
    selected = freeze["identity"]
    contract = selected["contract"]
    calendar = SessionCalendar.load(config.research.calendar_path)
    synthetic = config.data.source == "synthetic"
    if contract["synthetic"] is not synthetic or calendar.synthetic is not synthetic:
        raise ValueError("synthetic freeze/calendar cannot authorize historical CSV inputs, or vice versa")
    if selected["strategy_spec_sha256"] != config.strategy_spec_sha256:
        raise ValueError("configuration differs from the selected frozen strategy specification")
    return ResearchContext(contract, calendar, freeze)


def research_context(config):
    """BA-002's profile-specific behavior and independent-calendar preflight."""
    from boring_alpha.tax.policy import policy_record, policy_sha256
    selected = _selected_context(config)
    contract, calendar = selected.contract, selected.calendar
    if config.quality_overrides:
        raise ValueError("BA-002 does not permit unregistered data-quality overrides")
    rule = contract["rule"]
    comparisons = {
        "symbols": (sorted(config.strategy.symbols), sorted(contract["symbols"])),
        "horizons": (config.strategy.horizons, tuple(rule["horizons"])),
        "warmup_months": (config.strategy.warmup_months, rule["warmup_months"]),
        "lookback_months": (config.strategy.lookback_months, rule["warmup_months"]),
        "sleeve_weight": (config.strategy.sleeve_weight, rule["sleeve_weight"]),
        "initial_cash": (config.portfolio.initial_cash, contract["initial_cash"]),
        "cost_bps": (config.execution.cost_bps, contract["grid"]["base"]["cost_bps"]),
        "data_methodology": (("synthetic-v1" if config.data.source == "synthetic" else config.data.methodology), contract["data_methodology"]),
        "calendar_sha256": (calendar.sha256, contract["calendar_sha256"]),
        "calendar_authority_sha256": (calendar.authority_sha256, contract["calendar_authority_sha256"]),
    }
    if config.benchmark is None or config.tax is None:
        raise ValueError("BA-002 requires its contracted benchmark and complete tax policy")
    comparisons.update({
        "benchmark.exposure": (config.benchmark.exposure, contract["benchmark"]["exposure"]),
        "benchmark.rebalance": (config.benchmark.rebalance, contract["benchmark"]["rebalance"]),
        "tax_policy_sha256": (policy_sha256(config.tax), contract["tax_policy_sha256"]),
        "tax_policy": (policy_record(config.tax), contract.get("tax_policy", policy_record(config.tax))),
    })
    for label, (actual, expected) in comparisons.items():
        if actual != expected:
            raise ValueError(f"configuration {label} differs from the selected BA-002 contract")
    period = contract["periods"].get(config.evaluation.period)
    if period is None or (config.backtest.start.isoformat(), config.backtest.end.isoformat()) != (period["start"], period["end"]):
        raise ValueError("BA-002 backtest must match its contract period exactly; exploratory aliases cannot bypass it")
    if (config.evaluation.start, config.evaluation.end) != (config.backtest.start, config.backtest.end):
        raise ValueError("BA-002 registry and contract windows must match exactly")
    calendar.requirements(config.backtest.start, config.backtest.end, (9, 12, 15), warmup_months=15)
    return selected


def legacy_research_context(config):
    from boring_alpha.tax.policy import policy_sha256
    selected = _selected_context(config)
    contract = selected.contract
    if (contract['calendar_sha256'], contract['calendar_authority_sha256'], contract['tax_policy_sha256']) != (
        selected.calendar.sha256, selected.calendar.authority_sha256,
        policy_sha256(config.tax) if config.tax else canonical_sha256({'tax_policy': None}),
    ):
        raise ValueError('legacy calendar or tax policy differs from the confirmed freeze')
    period = contract["periods"].get(config.evaluation.period)
    if period is None or (period["start"], period["end"]) != (config.backtest.start.isoformat(), config.backtest.end.isoformat()):
        raise ValueError("legacy freeze does not cover this exact period")
    return selected


def validate_ba002_inputs(config, data, distributions, context=None):
    selected = context.research if context is not None else research_context(config)
    if selected is None:
        raise ValueError("BA-002 requires its selected research context")
    selected.calendar.validate_inputs(data, distributions, config.strategy.symbols,
                                     config.backtest.start, config.backtest.end, (9, 12, 15), warmup_months=15)
    return selected


def captured_distributions(context, end):
    from boring_alpha.data.distributions import load_distributions_bytes
    if context is None or context.inputs is None:
        return None
    inputs = context.inputs
    manifest = inputs.manifest("distributions")
    if "distributions" not in inputs.sources or manifest is None:
        raise ValueError("captured distributions require the source and its snapshot manifest")
    path = inputs.source_paths["distributions"]
    table = load_distributions_bytes(inputs.sources["distributions"], manifest_block=manifest,
                                     source_name=Path(path).name, end=end)
    return table, manifest, {
        "source_sha256": table.source_sha256, "source_path": path,
        "created_at": manifest.get("created_at"), "methodology": manifest.get("methodology"),
        "input_capture": "read-once-snapshot",
    }


def prepare_run(config, unseal_reason=None, *, reveal_reason=None, repair_of=None, repair_reason=None):
    from boring_alpha.evaluation import check_evaluation_gates
    from boring_alpha.profiles import profile_for
    from boring_alpha.research_state import FrozenAccessIdentity, RunJournal
    from boring_alpha.tax.policy import policy_sha256

    baseline = capture_execution_identity()
    profile = profile_for(config.strategy.strategy_id)
    check_evaluation_gates(config, unseal_reason)
    selected = profile.research_context(config)
    context = RunContext(selected, baseline)
    if config.data.source == "synthetic":
        if reveal_reason or repair_of or repair_reason:
            raise ValueError("synthetic runs do not reveal or repair historical coverage")
        return context
    if not profile.requires_managed_run(config):
        if reveal_reason or repair_of or repair_reason:
            raise ValueError("reveal/repair applies only to a managed historical run")
        return context
    inputs = capture_inputs(config)
    frozen = selected.freeze["identity"]
    expected_evaluator = baseline[1] if config.strategy.strategy_id == "BA-002" else baseline[0]
    if (frozen["code_sha256"], frozen["evaluator_sha256"], frozen["input_manifest_sha256"]) != (baseline[0], expected_evaluator, inputs.sha256):
        raise ValueError("code, evaluator or input snapshot differs from the confirmed freeze; prepare a new draft for a reviewed repair")
    for label in inputs.sources:
        manifest = inputs.manifest(label)
        if manifest and manifest.get("synthetic") is True:
            raise ValueError("a synthetic snapshot cannot supply historical research")
        if config.strategy.strategy_id == "BA-002" and (not manifest or manifest.get("methodology") != config.data.methodology):
            raise ValueError("snapshot methodology differs from the frozen methodology")
    context.inputs = inputs
    identity = FrozenAccessIdentity(
        candidate_id=config.strategy.strategy_id, period=config.evaluation.period,
        start=min(config.backtest.start, PROTECTED_START) if config.backtest.end >= PROTECTED_START else config.backtest.start,
        end=config.backtest.end, contract_sha256=canonical_sha256(selected.contract),
        code_sha256=baseline[0], evaluator_sha256=expected_evaluator,
        policy_sha256=policy_sha256(config.tax) if config.tax else canonical_sha256({"tax_policy": None}),
        calendar_sha256=selected.calendar.sha256, input_manifest_sha256=inputs.sha256,
        synthetic=False,
    )
    context.attempt = RunJournal(config.research.journal_path).begin(
        identity, reveal_reason=reveal_reason or unseal_reason, repair_of=repair_of, repair_reason=repair_reason,
    )
    return context


@contextmanager
def open_run(config, unseal_reason=None, **options):
    """The supported historical lifecycle; completion is explicit on context."""
    from boring_alpha.data.loader import load_market_data
    context = prepare_run(config, unseal_reason, **options)
    try:
        context.verify()
        if context.attempt is not None:
            context.attempt.start_access()
        context.verify()
        data = load_market_data(config, context=context)
        context.verify()
        yield LoadedRun(data, context)
    except BaseException as exc:
        context.finish(error=exc)
        raise
    else:
        context.finish()


def synthetic_run_context(config):
    """Direct synthetic engine callers need no journal, but retain provenance."""
    if config.data.source != "synthetic":
        raise ValueError("historical research requires open_run and its explicit RunContext")
    return prepare_run(config)
