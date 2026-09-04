"""The scenario grid and the identity of a tax policy (spec §4.9, §4.11).

Three tax inputs are declared rather than known: how lots are selected, what a
commodity pool's K-1 allocates, and what fraction of equity distributions is
qualified. The grid runs every combination; a conclusion that depends on one
combination is not a conclusion. The grid is fixed here, not in configuration,
so it cannot be narrowed after a result is seen.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from boring_alpha.config import TaxConfig

OVERLAY_VERSION = "tax-overlay-v1"
LOT_METHODS: tuple[str, ...] = ("hifo", "fifo")
COMMODITY_TREATMENTS: tuple[str, ...] = ("deferral", "mtm_60_40")
QUALIFIED_SETS: tuple[str, ...] = ("base", "low")


@dataclass(frozen=True, slots=True)
class Scenario:
    lot_method: str
    commodity_treatment: str
    qualified_set: str

    def __post_init__(self) -> None:
        for field_name, value, allowed in (
            ("lot_method", self.lot_method, LOT_METHODS),
            ("commodity_treatment", self.commodity_treatment, COMMODITY_TREATMENTS),
            ("qualified_set", self.qualified_set, QUALIFIED_SETS),
        ):
            if value not in allowed:
                raise ValueError(f"{field_name} must be one of {', '.join(allowed)}, got {value!r}")

    @property
    def key(self) -> str:
        return f"{self.lot_method}-{self.commodity_treatment}-{self.qualified_set}"

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "lot_method": self.lot_method,
            "commodity_treatment": self.commodity_treatment,
            "qualified_set": self.qualified_set,
        }


SCENARIOS: tuple[Scenario, ...] = tuple(
    Scenario(method, treatment, qualified)
    for method in LOT_METHODS
    for treatment in COMMODITY_TREATMENTS
    for qualified in QUALIFIED_SETS
)


def policy_record(tax: TaxConfig) -> dict[str, object]:
    """The policy as applied. The file path is where the data lives, not what the policy is."""

    return {
        "ordinary_rate": tax.ordinary_rate,
        "long_term_rate": tax.long_term_rate,
        "collectibles_rate": tax.collectibles_rate,
        "qualified_fraction_low": tax.qualified_fraction_low,
        "qualified_fraction": dict(sorted(tax.qualified_fraction.items())),
        "gains_class": dict(sorted(tax.gains_class.items())),
    }


def policy_sha256(tax: TaxConfig) -> str:
    canonical = json.dumps(policy_record(tax), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def qualified_fraction(tax: TaxConfig, scenario: Scenario, symbol: str) -> float:
    """The share of a symbol's distributions eligible for the long-term rate.

    The low set caps every positive fraction at `qualified_fraction_low`; it
    never raises one, and a symbol that pays no qualified income stays at zero.
    """

    base = tax.qualified_fraction[symbol]
    if scenario.qualified_set == "low" and base > 0.0:
        return min(base, tax.qualified_fraction_low)
    return base
