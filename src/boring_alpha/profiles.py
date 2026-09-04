"""Per-strategy evaluation profiles: what a sweep runs and how it is judged.

A charter fixes a grid of variants, the criteria applied to them, and the
advance / reject / inconclusive rule. Those belong to the strategy, not to the
laboratory, so each strategy registers a profile here and the sweep and
classify commands ask the profile rather than assuming BA-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from boring_alpha.backtest.engine import SignalPolicy
from boring_alpha.config import AppConfig
from boring_alpha.criteria import (
    BASE,
    DOUBLE_COST,
    DROP_TOP_SLEEVE,
    LOOKBACK_15,
    LOOKBACK_9,
    PeriodOutcome,
    Verdict,
)
from boring_alpha.criteria import classify as _classify_ba001
from boring_alpha.criteria import evaluate_period as _evaluate_period_ba001
from boring_alpha.signals import (
    ExcludingSleeve,
    FixedAllocation,
    MultiAssetTrend,
    TargetExposureAllocation,
)


@dataclass(frozen=True)
class VariantSpec:
    """One cell of a sweep grid.

    `strategy` receives the configuration and, when `needs_top_sleeve` is set,
    the base variant's largest-contributing sleeve; otherwise `None`.
    `benchmark` builds the gating benchmark the variant is judged against.
    """

    description: str
    cost_bps: float
    strategy: Callable[[AppConfig, str | None], SignalPolicy]
    benchmark: Callable[[AppConfig], SignalPolicy]
    needs_top_sleeve: bool = False


class StrategyProfile(Protocol):
    strategy_id: str

    def grid(self, config: AppConfig) -> dict[str, VariantSpec]: ...

    def evaluate_period(
        self, variants: dict[str, dict[str, dict[str, float]]], extras: dict[str, object]
    ) -> PeriodOutcome: ...

    def classify(self, development: dict, validation: dict) -> Verdict: ...


def gating_benchmark(config: AppConfig, lookback_months: int) -> SignalPolicy:
    """Full static equal-weight, or the configured target-exposure allocation.

    The benchmark takes the variant's own lookback so that strategy and
    benchmark series start on the same session.
    """

    symbols, weight = config.strategy.symbols, config.strategy.sleeve_weight
    if config.benchmark is not None:
        return TargetExposureAllocation(
            symbols, lookback_months, weight, config.benchmark.exposure, config.benchmark.rebalance
        )
    return FixedAllocation(symbols, lookback_months, weight)


class BA001Profile:
    """BA-001 Multi-Asset Trend: the charter's C1 to C5 on its five-variant grid."""

    strategy_id = "BA-001"

    def grid(self, config: AppConfig) -> dict[str, VariantSpec]:
        lookback = config.strategy.lookback_months
        cost = config.execution.cost_bps

        def trend(months: int) -> Callable[[AppConfig, str | None], SignalPolicy]:
            def build(config: AppConfig, top_sleeve: str | None) -> SignalPolicy:
                return MultiAssetTrend(
                    config.strategy.symbols, months, config.strategy.sleeve_weight
                )

            return build

        def trend_without_top_sleeve(months: int) -> Callable[[AppConfig, str | None], SignalPolicy]:
            def build(config: AppConfig, top_sleeve: str | None) -> SignalPolicy:
                if top_sleeve is None:
                    raise ValueError(
                        f"{DROP_TOP_SLEEVE} needs the base variant's top sleeve"
                    )
                return ExcludingSleeve(
                    MultiAssetTrend(config.strategy.symbols, months, config.strategy.sleeve_weight),
                    top_sleeve,
                )

            return build

        def static(months: int) -> Callable[[AppConfig], SignalPolicy]:
            return lambda config: gating_benchmark(config, months)

        return {
            BASE: VariantSpec(
                f"{lookback}-month lookback at {cost:g} bps (pre-registered)",
                cost, trend(lookback), static(lookback),
            ),
            DOUBLE_COST: VariantSpec(
                f"{lookback}-month lookback at {2 * cost:g} bps",
                2.0 * cost, trend(lookback), static(lookback),
            ),
            LOOKBACK_9: VariantSpec(
                f"9-month lookback at {cost:g} bps", cost, trend(9), static(9),
            ),
            LOOKBACK_15: VariantSpec(
                f"15-month lookback at {cost:g} bps", cost, trend(15), static(15),
            ),
            DROP_TOP_SLEEVE: VariantSpec(
                f"{lookback}-month lookback at {cost:g} bps, top sleeve in cash",
                cost, trend_without_top_sleeve(lookback), static(lookback),
                needs_top_sleeve=True,
            ),
        }

    def evaluate_period(
        self, variants: dict[str, dict[str, dict[str, float]]], extras: dict[str, object]
    ) -> PeriodOutcome:
        return _evaluate_period_ba001(variants)

    def classify(self, development: dict, validation: dict) -> Verdict:
        return _classify_ba001(development, validation)


PROFILES: dict[str, StrategyProfile] = {"BA-001": BA001Profile()}


def profile_for(strategy_id: str) -> StrategyProfile:
    try:
        return PROFILES[strategy_id]
    except KeyError:
        raise ValueError(
            f"no evaluation profile is registered for strategy {strategy_id!r}; "
            f"known profiles: {', '.join(sorted(PROFILES))}"
        ) from None
