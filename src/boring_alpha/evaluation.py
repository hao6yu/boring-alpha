"""Gates that implement a strategy charter's period-sealing policy.

These are deliberately not cryptographic. Anyone can create the file a gate
looks for. They exist so that looking at data you promised not to look at yet
is a deliberate, reviewable act rather than an accident.
"""

from __future__ import annotations

from boring_alpha.config import AppConfig

REQUIRED_REVIEWS: dict[str, tuple[str, ...]] = {
    "validation": ("development",),
    "sealed": ("development", "validation"),
}


class SealedRunError(RuntimeError):
    """Raised when a sealed evaluation period is run without an explicit unseal."""


def check_evaluation_gates(config: AppConfig, unseal_reason: str | None) -> None:
    """One profile-owned admission interface, shared by all entry points."""
    from boring_alpha.profiles import profile_for
    profile_for(config.strategy.strategy_id).check_admission(config, unseal_reason)


def check_legacy_review_gates(config: AppConfig, unseal_reason: str | None) -> None:
    """Preserve BA-001's review-file semantics; profiles own their use."""

    period = config.evaluation.period
    if period == "sealed" and not (unseal_reason or "").strip():
        raise SealedRunError(
            "the sealed period requires --unseal with a reason; "
            "a sealed run is a one-way decision and must be logged in the charter"
        )
    if unseal_reason is not None and period != "sealed":
        raise ValueError(f"--unseal applies only to the sealed period, not {period}")

    strategy_id = config.strategy.strategy_id
    for stage in REQUIRED_REVIEWS.get(period, ()):
        pattern = f"{strategy_id}-{stage}*.md"
        if not sorted(config.evaluation.review_dir.glob(pattern)):
            raise ValueError(
                f"a written {stage} review is required before a {period} run: "
                f"expected {config.evaluation.review_dir / pattern}"
            )
