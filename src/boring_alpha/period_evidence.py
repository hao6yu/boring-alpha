"""Validated, immutable economic inputs for one BA-002 research period.

Invalid evidence raises ValueError; it is not a failed financial criterion.
Archive loaders must verify file checksums and independently reconcile accounts
before calling the builder. No saved verdict or checksum-success flag is read.
Tax CAGRs and tax identity-check results are saved, checksum-verified inputs;
this builder validates their structure and identity but does not recompute tax.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from typing import Mapping

from boring_alpha.research_contract import (
    ROWS, canonical_json, code_fingerprint, contract_sha256,
    evaluator_fingerprint, expected_account_map, expected_row_definitions,
    require_approved_contract, require_digest, require_exact_behavior, validate_contract,
)
from boring_alpha.tax.policy import OVERLAY_VERSION, SCENARIOS


BA002_ARTIFACT_SCHEMA = 7
IDENTITY_FIELDS = (
    "strategy_spec_sha256", "code_sha256", "tax_policy_sha256",
    "distributions_sha256", "data_sha256", "contract_sha256", "evaluator_sha256",
    "calendar_sha256", "calendar_authority_sha256",
)
COMMON_IDENTITY_FIELDS = tuple(
    field for field in IDENTITY_FIELDS if field not in ("distributions_sha256", "data_sha256")
)
IDENTITY_CHECKS = (
    "share_identity_passed", "income_plus_gain_passed", "implied_price_check_passed",
)
DIAGNOSTIC_ACCOUNTS = frozenset(("cash", "exposure_matched", "static_full", "reference_12"))


def number(value: object, name: str) -> Decimal:
    """Use serialized precision; never round a display percent or accept bools."""
    if type(value) not in (int, float, Decimal):
        raise ValueError(f"{name} must be a defined finite number, not {value!r}")
    try:
        result = Decimal(str(value))
    except (ValueError, ArithmeticError) as exc:
        raise ValueError(f"{name} must be a defined finite number") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be a defined finite number")
    return result


def _mapping(value: object, name: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


@dataclass(frozen=True, slots=True)
class AccountEvidence:
    account_id: str
    drawdown: Decimal
    after_tax_cagrs: tuple[tuple[str, Decimal], ...]

    @property
    def worst_cagr(self) -> Decimal:
        return min(value for _, value in self.after_tax_cagrs)

    @property
    def best_cagr(self) -> Decimal:
        return max(value for _, value in self.after_tax_cagrs)


@dataclass(frozen=True, slots=True)
class RowEvidence:
    row_id: str
    cost_bps: Decimal
    horizons: tuple[int, ...]
    warmup_months: int
    strategy: AccountEvidence
    benchmark: AccountEvidence

    @property
    def margin(self) -> Decimal:
        return self.strategy.worst_cagr - self.benchmark.best_cagr

    @property
    def paired_margins(self) -> tuple[tuple[str, Decimal], ...]:
        benchmarks = dict(self.benchmark.after_tax_cagrs)
        return tuple((key, value - benchmarks[key]) for key, value in self.strategy.after_tax_cagrs)


@dataclass(frozen=True, slots=True)
class PeriodEvidence:
    rows: tuple[RowEvidence, ...]
    identities: tuple[tuple[str, str], ...]
    period: str
    start: str
    end: str
    evidence_status: str
    synthetic: bool
    contract_json: str

    @property
    def identity(self) -> dict[str, str]:
        return dict(self.identities)


def _account_returns(
    account: str,
    payload: Mapping,
    identities: Mapping[str, str],
    contract: Mapping,
) -> tuple[tuple[str, Decimal], ...]:
    if set(payload) != {scenario.key for scenario in SCENARIOS}:
        raise ValueError(f"tax account {account} has missing or extra scenarios")
    result = []
    for scenario in SCENARIOS:
        record = _mapping(payload[scenario.key], f"tax {account}/{scenario.key}")
        if record.get('loss_sensitivity') is not None:
            raise ValueError('capital-loss sensitivities are diagnostic only, not BA-002 gating scenarios')
        require_exact_behavior(record.get("scenario"), scenario.as_dict(), f"tax {account}/{scenario.key}.scenario")
        policy = _mapping(record.get("policy"), f"tax {account}/{scenario.key}.policy")
        for field in ("tax_policy_sha256", "distributions_sha256", "code_sha256"):
            if policy.get(field) != identities[field]:
                raise ValueError(f"tax {account}/{scenario.key} {field} differs from period identity")
        if policy.get("overlay_version") != OVERLAY_VERSION:
            raise ValueError(f"tax {account}/{scenario.key} has an incompatible overlay version")
        if "tax_policy" in contract:
            for field, expected in contract["tax_policy"].items():
                require_exact_behavior(policy.get(field), expected, f"tax {account}/{scenario.key}.policy.{field}")
        checks = _mapping(record.get("identity_checks"), f"tax {account}/{scenario.key}.identity_checks")
        for check in IDENTITY_CHECKS:
            if checks.get(check) is not True:
                raise ValueError(f"tax {account}/{scenario.key} {check} must be true")
        for check, value in checks.items():
            if check not in IDENTITY_CHECKS and value is not None:
                number(value, f"tax {account}/{scenario.key}.{check}")
        metrics = _mapping(record.get("metrics"), f"tax {account}/{scenario.key}.metrics")
        for metric, value in metrics.items():
            # Effective tax rate is legitimately undefined without a profit;
            # the gating CAGR below is never allowed to be undefined.
            if value is not None:
                number(value, f"tax {account}/{scenario.key}.{metric}")
        cagr = number(metrics.get("after_tax_cagr"), f"tax {account}/{scenario.key}.after_tax_cagr")
        if cagr <= -1:
            raise ValueError(f"tax {account}/{scenario.key} CAGR requires positive terminal wealth")
        result.append((scenario.key, cagr))
    return tuple(result)


def build_period_evidence(
    *,
    variants: Mapping,
    tax: Mapping,
    account_map: Mapping,
    row_definitions: Mapping,
    verification: Mapping,
    identities: Mapping,
    contract: Mapping,
    period: str,
    start: str | date,
    end: str | date,
    evidence_status: str,
    artifact_schema: int = BA002_ARTIFACT_SCHEMA,
    approved_contract: Mapping | None = None,
) -> PeriodEvidence:
    """Build from checked raw metrics and the actual run_scenarios payload shape.

    The verification booleans are the caller's results of mandatory independent
    reconciliation/calendar checks. An archive reader must run those checks;
    deserializing a saved True is not an implementation of this precondition.
    """
    if type(artifact_schema) is not int or artifact_schema != BA002_ARTIFACT_SCHEMA:
        raise ValueError("BA-002 evidence requires artifact schema 7")
    selected = validate_contract(contract)
    if not selected["synthetic"]:
        require_approved_contract(selected, approved_contract)
    if period not in selected["periods"]:
        raise ValueError(f"period {period!r} is absent from the selected contract")
    bounds = selected["periods"][period]
    start_text = start.isoformat() if isinstance(start, date) else start
    end_text = end.isoformat() if isinstance(end, date) else end
    if start_text != bounds["start"] or end_text != bounds["end"]:
        raise ValueError("evidence window differs from the complete contracted period")
    required_status = "synthetic" if selected["synthetic"] else bounds["status"]
    if evidence_status != required_status:
        raise ValueError(f"evidence status must be {required_status!r} for this contract")

    identities = _mapping(identities, "identities")
    if set(identities) != set(IDENTITY_FIELDS):
        raise ValueError("period identities have missing or extra fields")
    for field in IDENTITY_FIELDS:
        require_digest(identities[field], field)
    for field in ("tax_policy_sha256", "calendar_sha256", "calendar_authority_sha256"):
        if identities[field] != selected[field]:
            raise ValueError(f"{field} differs from the selected contract")
    if identities["contract_sha256"] != contract_sha256(selected):
        raise ValueError("contract_sha256 differs from the selected contract")
    if identities["evaluator_sha256"] != evaluator_fingerprint():
        raise ValueError("evaluator_sha256 does not identify the current frozen evaluator")
    if identities["code_sha256"] != code_fingerprint():
        raise ValueError("code_sha256 does not identify the current frozen implementation")

    variants = _mapping(variants, "variants")
    if set(variants) != set(ROWS):
        raise ValueError("BA-002 variants have missing or extra rows")
    require_exact_behavior(account_map, expected_account_map(), "account_map")
    require_exact_behavior(row_definitions, expected_row_definitions(), "row_definitions")
    require_exact_behavior(row_definitions, selected["grid"], "contract grid")
    tax = _mapping(tax, "tax")
    for field in ("tax_policy_sha256", "distributions_sha256"):
        if tax.get(field) != identities[field]:
            raise ValueError(f"tax {field} differs from period identity")
    if tax.get("overlay_version") != OVERLAY_VERSION:
        raise ValueError("tax payload has an incompatible overlay version")
    runs = _mapping(tax.get("runs"), "tax.runs")
    required_accounts = {account for pair in account_map.values() for account in pair.values()}
    if not required_accounts.issubset(runs) or set(runs) - required_accounts - DIAGNOSTIC_ACCOUNTS:
        raise ValueError("tax runs have missing gating accounts or unknown extra accounts")
    verification = _mapping(verification, "verification")
    if verification.get("calendar_complete") is not True:
        raise ValueError("independent calendar coverage verification must pass")
    reconciliations = _mapping(verification.get("account_reconciliation"), "account_reconciliation")
    for account in runs:
        if reconciliations.get(account) is not True:
            raise ValueError(f"independent account reconciliation must pass for {account}")
    returns = {
        account: _account_returns(account, _mapping(payload, f"tax.runs.{account}"), identities, selected)
        for account, payload in runs.items()
    }
    rows = []
    for row_id in ROWS:
        pair = _mapping(variants[row_id], f"variants.{row_id}")
        if set(pair) != {"strategy", "static"}:
            raise ValueError(f"variants.{row_id} requires exactly strategy and static metrics")
        accounts = {}
        for role, metric_key in (("strategy", "strategy"), ("benchmark", "static")):
            metrics = _mapping(pair[metric_key], f"variants.{row_id}.{metric_key}")
            # Pre-tax diagnostics are not alternative gates, but non-finite
            # published metrics still indicate invalid evidence.
            for name, value in metrics.items():
                number(value, f"variants.{row_id}.{metric_key}.{name}")
            drawdown = abs(number(metrics.get("max_drawdown"), f"{row_id}.{role}.max_drawdown"))
            if drawdown > 1:
                raise ValueError(f"{row_id}.{role}.max_drawdown exceeds a long-only account's value")
            account = account_map[row_id][role]
            accounts[role] = AccountEvidence(account, drawdown, returns[account])
        definition = row_definitions[row_id]
        rows.append(RowEvidence(
            row_id, number(definition["cost_bps"], f"{row_id}.cost_bps"),
            tuple(definition["horizons"]), definition["warmup_months"],
            accounts["strategy"], accounts["benchmark"],
        ))
    return PeriodEvidence(
        tuple(rows), tuple((field, identities[field]) for field in IDENTITY_FIELDS),
        period, start_text, end_text, evidence_status, selected["synthetic"], canonical_json(selected),
    )


def validate_period_evidence(evidence: PeriodEvidence) -> None:
    """Reject malformed manually constructed records, including stale code use."""
    if not isinstance(evidence, PeriodEvidence) or tuple(row.row_id for row in evidence.rows) != ROWS:
        raise ValueError("complete typed BA-002 period evidence is required")
    if len(evidence.identities) != len(IDENTITY_FIELDS) or set(evidence.identity) != set(IDENTITY_FIELDS):
        raise ValueError("period identities are incomplete")
    for field, value in evidence.identities:
        require_digest(value, field)
    try:
        contract = validate_contract(json.loads(evidence.contract_json))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("period has an invalid selected contract") from exc
    if evidence.identity["contract_sha256"] != contract_sha256(contract):
        raise ValueError("period contract identity differs from its selected contract")
    if type(evidence.synthetic) is not bool or evidence.synthetic is not contract["synthetic"]:
        raise ValueError("period synthetic status differs from its selected contract")
    bounds = contract["periods"].get(evidence.period)
    if bounds is None or evidence.start != bounds["start"] or evidence.end != bounds["end"]:
        raise ValueError("period window differs from its complete contracted period")
    required_status = "synthetic" if evidence.synthetic else bounds["status"]
    if evidence.evidence_status != required_status:
        raise ValueError("period evidence status differs from its selected contract")
    for field in ("tax_policy_sha256", "calendar_sha256", "calendar_authority_sha256"):
        if evidence.identity[field] != contract[field]:
            raise ValueError(f"period {field} differs from its selected contract")
    if evidence.identity["evaluator_sha256"] != evaluator_fingerprint():
        raise ValueError("period evaluator differs from the currently selected evaluator")
    if evidence.identity["code_sha256"] != code_fingerprint():
        raise ValueError("period code differs from the currently selected implementation")
    scenario_keys = tuple(scenario.key for scenario in SCENARIOS)
    definitions = expected_row_definitions()
    mappings = expected_account_map()
    for row in evidence.rows:
        if row.cost_bps != Decimal(str(definitions[row.row_id]["cost_bps"])) or row.horizons != tuple(definitions[row.row_id]["horizons"]) or type(row.warmup_months) is not int or row.warmup_months != 15:
            raise ValueError(f"{row.row_id} differs from the selected grid")
        for role, account in (("strategy", row.strategy), ("benchmark", row.benchmark)):
            if account.account_id != mappings[row.row_id][role]:
                raise ValueError(f"{row.row_id} has an incompatible account map")
            drawdown = number(account.drawdown, "drawdown")
            if drawdown < 0 or drawdown > 1:
                raise ValueError("drawdown magnitude must be between zero and one")
            if tuple(key for key, _ in account.after_tax_cagrs) != scenario_keys:
                raise ValueError("account has missing, extra, duplicate or reordered scenarios")
            for _, cagr in account.after_tax_cagrs:
                if number(cagr, "after_tax_cagr") <= -1:
                    raise ValueError("after-tax CAGR requires positive terminal wealth")
