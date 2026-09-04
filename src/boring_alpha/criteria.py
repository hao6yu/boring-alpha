"""BA-001's advancement criteria, evaluated mechanically.

The charter fixes C1 to C5 and the advance/reject/inconclusive rule. This module
computes the verdict from run metrics so that it cannot be talked into existence
after the numbers are known. Every criterion carries the arithmetic that decided
it, because a verdict a reader cannot check is not evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

DRAWDOWN_RATIO = 0.75
SHARPE_TOLERANCE = 0.10

BASE = "base"
DOUBLE_COST = "double_cost"
LOOKBACK_9 = "lookback_9"
LOOKBACK_15 = "lookback_15"
DROP_TOP_SLEEVE = "drop_top_sleeve"
VARIANTS = (BASE, DOUBLE_COST, LOOKBACK_9, LOOKBACK_15, DROP_TOP_SLEEVE)


class Verdict(str, Enum):
    ADVANCE = "advance"
    INCONCLUSIVE = "inconclusive"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class Criterion:
    name: str
    description: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class PeriodOutcome:
    criteria: tuple[Criterion, ...]

    @property
    def passed(self) -> bool:
        return all(criterion.passed for criterion in self.criteria)


def _drawdown(metrics: dict[str, float]) -> float:
    return abs(float(metrics["max_drawdown"]))


def _check_pair(variant: dict[str, dict[str, float]]) -> tuple[bool, str]:
    """C1 and C2 applied to one variant's strategy and static results."""

    strategy, static = variant["strategy"], variant["static"]
    limit = DRAWDOWN_RATIO * _drawdown(static)
    drawdown_ok = _drawdown(strategy) <= limit + 1e-12
    floor = float(static["sharpe_vs_cash"]) - SHARPE_TOLERANCE
    sharpe_ok = float(strategy["sharpe_vs_cash"]) >= floor - 1e-12
    detail = (
        f"drawdown {_drawdown(strategy):.4f} vs limit {limit:.4f} "
        f"({DRAWDOWN_RATIO} x {_drawdown(static):.4f}); "
        f"Sharpe {float(strategy['sharpe_vs_cash']):.4f} vs floor {floor:.4f}"
    )
    return drawdown_ok and sharpe_ok, detail


def evaluate_period(variants: dict[str, dict[str, dict[str, float]]]) -> PeriodOutcome:
    """Evaluate C1 to C5 for one evaluation period."""

    missing = [name for name in VARIANTS if name not in variants]
    if missing:
        raise ValueError(f"missing variants for criteria: {', '.join(missing)}")

    base_ok, base_detail = _check_pair(variants[BASE])
    strategy, static = variants[BASE]["strategy"], variants[BASE]["static"]
    limit = DRAWDOWN_RATIO * _drawdown(static)
    floor = float(static["sharpe_vs_cash"]) - SHARPE_TOLERANCE
    cost_ok, cost_detail = _check_pair(variants[DOUBLE_COST])
    nine_ok, nine_detail = _check_pair(variants[LOOKBACK_9])
    fifteen_ok, fifteen_detail = _check_pair(variants[LOOKBACK_15])
    sleeve_ok, sleeve_detail = _check_pair(variants[DROP_TOP_SLEEVE])

    return PeriodOutcome(
        (
            Criterion(
                "C1",
                "max drawdown at most 75% of the static benchmark's",
                _drawdown(strategy) <= limit + 1e-12,
                f"drawdown {_drawdown(strategy):.4f} vs limit {limit:.4f} "
                f"({DRAWDOWN_RATIO} x static {_drawdown(static):.4f})",
            ),
            Criterion(
                "C2",
                "Sharpe versus cash within 0.10 of the static benchmark's",
                float(strategy["sharpe_vs_cash"]) >= floor - 1e-12,
                f"Sharpe {float(strategy['sharpe_vs_cash']):.4f} vs floor {floor:.4f}",
            ),
            Criterion("C3", "C1 and C2 hold at twice the base cost", cost_ok, cost_detail),
            Criterion(
                "C4",
                "C1 and C2 hold at 9- and 15-month lookbacks",
                nine_ok and fifteen_ok,
                f"9-month: {nine_detail}; 15-month: {fifteen_detail}",
            ),
            Criterion(
                "C5",
                "C1 and C2 hold without the largest-contributing sleeve",
                sleeve_ok,
                sleeve_detail,
            ),
        )
    )


def _triggers_rejection(variants: dict[str, dict[str, dict[str, float]]]) -> bool:
    strategy, static = variants[BASE]["strategy"], variants[BASE]["static"]
    return (
        _drawdown(strategy) >= _drawdown(static)
        or float(strategy["sharpe_vs_cash"]) < 0.0
    )


def classify(development: dict, validation: dict) -> Verdict:
    """The charter's advance / reject / inconclusive rule."""

    if _triggers_rejection(development) or _triggers_rejection(validation):
        return Verdict.REJECT
    if evaluate_period(development).passed and evaluate_period(validation).passed:
        return Verdict.ADVANCE
    return Verdict.INCONCLUSIVE
