"""After-tax evaluation: a pure overlay over pre-tax run artifacts (spec §4)."""

from boring_alpha.tax.overlay import apply_overlay, run_scenarios
from boring_alpha.tax.policy import (
    OVERLAY_VERSION,
    SCENARIOS,
    Scenario,
    policy_record,
    policy_sha256,
    qualified_fraction,
)

__all__ = [
    "OVERLAY_VERSION",
    "SCENARIOS",
    "Scenario",
    "apply_overlay",
    "policy_record",
    "policy_sha256",
    "qualified_fraction",
    "run_scenarios",
]
