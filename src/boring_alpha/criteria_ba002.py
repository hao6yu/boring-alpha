"""BA-002's approved numerical research bar, not a trading authorization."""

from decimal import Decimal
from enum import Enum

from boring_alpha.criteria import Criterion, PeriodOutcome
from boring_alpha.period_evidence import (
    COMMON_IDENTITY_FIELDS, PeriodEvidence, validate_period_evidence,
)


PRIMARY_MARGIN = Decimal("0.005")
MAX_DRAWDOWN = Decimal("0.20")


class ResearchEligibility(str, Enum):
    ELIGIBLE = "eligible to request holdout evaluation"
    NOT_ELIGIBLE = "not eligible"


def evaluate_period(evidence: PeriodEvidence) -> PeriodOutcome:
    """Every row passes independently; returns and periods are never pooled."""
    validate_period_evidence(evidence)
    criteria = []
    for row in evidence.rows:
        primary = row.row_id == "base"
        return_ok = row.margin >= PRIMARY_MARGIN if primary else row.margin > 0
        threshold = "at least 50 bps/year" if primary else "strictly positive"
        criteria.extend((
            Criterion(
                f"{row.row_id}:return",
                f"independent worst strategy minus best benchmark is {threshold}",
                return_ok,
                f"worst strategy {row.strategy.worst_cagr}; best benchmark {row.benchmark.best_cagr}; "
                f"margin {row.margin * 10000} bps/year; required {threshold}; "
                f"both accounts {row.cost_bps} bps per side",
            ),
            Criterion(
                f"{row.row_id}:absolute_drawdown",
                "pre-tax cost-net drawdown magnitude is at most 20%",
                row.strategy.drawdown <= MAX_DRAWDOWN,
                f"strategy drawdown {row.strategy.drawdown}; cap {MAX_DRAWDOWN}",
            ),
            Criterion(
                f"{row.row_id}:relative_drawdown",
                "pre-tax cost-net drawdown is no worse than the paired benchmark",
                row.strategy.drawdown <= row.benchmark.drawdown,
                f"strategy drawdown {row.strategy.drawdown}; benchmark {row.benchmark.drawdown}",
            ),
        ))
    return PeriodOutcome(tuple(criteria))


def classify(development: PeriodEvidence, validation: PeriodEvidence) -> ResearchEligibility:
    """Screen the two already-seen windows; never emit BA-001's ADVANCE label."""
    validate_period_evidence(development)
    validate_period_evidence(validation)
    if development.period != "development" or validation.period != "validation":
        raise ValueError("BA-002 classification requires development and validation separately")
    if development.synthetic != validation.synthetic or development.evidence_status != validation.evidence_status:
        raise ValueError("periods have incompatible evidence status")
    for field in COMMON_IDENTITY_FIELDS:
        if development.identity[field] != validation.identity[field]:
            raise ValueError(f"periods have incompatible {field}")
    if development.contract_json != validation.contract_json:
        raise ValueError("periods have incompatible selected contracts")
    return (
        ResearchEligibility.ELIGIBLE
        if evaluate_period(development).passed and evaluate_period(validation).passed
        else ResearchEligibility.NOT_ELIGIBLE
    )
