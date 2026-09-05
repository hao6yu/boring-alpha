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
    MultiHorizonTrend,
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

    def check_admission(self, config: AppConfig, unseal_reason: str | None) -> None: ...
    def research_context(self, config: AppConfig): ...
    def requires_managed_run(self, config: AppConfig) -> bool: ...

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

    def check_admission(self, config, unseal_reason):
        from boring_alpha.evaluation import check_legacy_review_gates
        check_legacy_review_gates(config, unseal_reason)

    def requires_managed_run(self, config):
        from boring_alpha.research_access import PROTECTED_START
        return config.data.source == "csv" and config.backtest.end >= PROTECTED_START

    def research_context(self, config):
        from boring_alpha.research_access import legacy_research_context
        return legacy_research_context(config) if self.requires_managed_run(config) else None

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


class BA002Profile:
    """The fixed multi-horizon candidate; seen-history screening, not Advance."""

    strategy_id = "BA-002"

    def check_admission(self, config, unseal_reason):
        from boring_alpha.evaluation import SealedRunError
        self.validate_config(config)
        if unseal_reason is not None:
            raise SealedRunError("BA-002 uses a confirmed freeze and --reveal for first holdout access, not --unseal")

    def requires_managed_run(self, config):
        return config.data.source == "csv"

    def research_context(self, config):
        from boring_alpha.research_access import research_context
        return research_context(config)

    def validate_config(self, config: AppConfig) -> None:
        from boring_alpha.research_contract import SYMBOLS

        if (
            tuple(sorted(config.strategy.symbols)) != tuple(sorted(SYMBOLS))
            or config.strategy.horizons != (9, 12, 15)
            or config.strategy.warmup_months != 15
            or config.strategy.lookback_months != 15
            or config.strategy.sleeve_weight != 0.125
            or config.portfolio.initial_cash != 100000
            or config.execution.cost_bps != 10
            or config.benchmark is None
            or config.benchmark.exposure != 0.6
            or config.benchmark.rebalance != "annual"
        ):
            raise ValueError("BA-002 configuration differs from its fixed research definition")
        if config.tax is None or config.research is None:
            raise ValueError("BA-002 requires its complete tax policy and research contract/calendar")
        if config.quality_overrides:
            raise ValueError("BA-002 does not permit unregistered data-quality overrides")

    def grid(self, config: AppConfig) -> dict[str, VariantSpec]:
        from boring_alpha.research_contract import HORIZONS

        self.validate_config(config)
        return {
            row: VariantSpec(
                f"{'/'.join(str(h) for h in horizons)}-month equal votes at "
                f"{20 if row == 'double_cost' else 10} bps; common 15-month warmup",
                20.0 if row == "double_cost" else 10.0,
                lambda cfg, _, horizons=horizons: MultiHorizonTrend(
                    cfg.strategy.symbols, horizons, cfg.strategy.sleeve_weight, warmup_months=15
                ),
                lambda cfg: gating_benchmark(cfg, 15),
            )
            for row, horizons in HORIZONS.items()
        }

    def reference_policy(self, config: AppConfig) -> SignalPolicy:
        policy = MultiHorizonTrend(config.strategy.symbols, (12,), 0.125, warmup_months=15)
        policy.name = "12-month reference (common 15-month readiness; non-gating)"
        return policy

    def evaluate_period(self, variants: dict, extras: dict) -> PeriodOutcome:
        from boring_alpha.criteria_ba002 import evaluate_period

        if "evidence" not in extras:
            raise ValueError("BA-002 cannot be evaluated from pre-tax variants alone")
        return evaluate_period(extras["evidence"])

    def classify(self, development, validation):
        from boring_alpha.criteria_ba002 import classify

        return classify(development, validation)


PROFILES: dict[str, StrategyProfile] = {"BA-001": BA001Profile(), "BA-002": BA002Profile()}


def profile_for(strategy_id: str) -> StrategyProfile:
    try:
        return PROFILES[strategy_id]
    except KeyError:
        raise ValueError(
            f"no evaluation profile is registered for strategy {strategy_id!r}; "
            f"known profiles: {', '.join(sorted(PROFILES))}"
        ) from None
