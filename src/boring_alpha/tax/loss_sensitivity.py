"""Explicit, non-gating capital-loss deduction sensitivity.

IRS Publication 550 (https://www.irs.gov/publications/p550), capital losses and
carryovers: an allowable ordinary-income deduction reduces carryovers, using
short-term losses first. This is a fixed-rate scenario, not a tax-return
calculator. Available capacity and outside ordinary taxable income are declared
after other household uses; they are not inferred from the trading account.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import tomllib

from boring_alpha.config import TaxConfig
from boring_alpha.tax.yearend import Amounts, YearTax, net_and_tax

SENSITIVITY_VERSION = "capital-loss-deduction-sensitivity-v1"
MAX_ANNUAL_CAPACITY = 3000.0
SAVINGS_DESTINATIONS = {"outside_account", "contribute_to_account"}


def _number(value: object, name: str, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"loss sensitivity {name} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"loss sensitivity {name} must be finite") from exc
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"loss sensitivity {name} must be finite and nonnegative")
    if maximum is not None and number > maximum:
        raise ValueError(f"loss sensitivity {name} must not exceed {maximum:g}")
    return number


@dataclass(frozen=True, slots=True)
class LossDeductionPolicy:
    """The same explicit household assumptions apply to each evaluated year.

    ``annual_capacity`` is unused tax-return-level capacity, not an allowance
    for each simultaneous account. Married-filing-separately users must supply
    their applicable smaller capacity (at most $1,500). ``outside_ordinary_income``
    is income remaining available at the declared marginal rate before this
    deduction; other deductions, brackets and household capital trades are not
    calculated here. A zero capacity disables the benefit without changing the
    baseline economic results.
    """

    annual_capacity: float
    outside_ordinary_income: float
    savings_destination: str
    ordinary_rate: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "annual_capacity", _number(
            self.annual_capacity, "annual_capacity", MAX_ANNUAL_CAPACITY
        ))
        object.__setattr__(self, "outside_ordinary_income", _number(
            self.outside_ordinary_income, "outside_ordinary_income"
        ))
        if not isinstance(self.savings_destination, str) or self.savings_destination not in SAVINGS_DESTINATIONS:
            raise ValueError("loss sensitivity savings_destination must be outside_account or contribute_to_account")
        if self.ordinary_rate is not None:
            object.__setattr__(self, "ordinary_rate", _number(self.ordinary_rate, "ordinary_rate", 1.0))

    @classmethod
    def from_dict(cls, record: object) -> "LossDeductionPolicy":
        required = {"annual_capacity", "outside_ordinary_income", "savings_destination"}
        if not isinstance(record, dict) or not required <= record.keys() or record.keys() - required - {"ordinary_rate"}:
            raise ValueError("loss sensitivity requires annual_capacity, outside_ordinary_income and savings_destination; only ordinary_rate is optional")
        if "ordinary_rate" in record and record["ordinary_rate"] is None:
            raise ValueError("loss sensitivity ordinary_rate must be a number when supplied")
        return cls(**record)

    def rate(self, tax: TaxConfig) -> float:
        return _number(tax.ordinary_rate if self.ordinary_rate is None else self.ordinary_rate, "ordinary_rate", 1.0)

    def as_dict(self, tax: TaxConfig | None = None) -> dict:
        return {
            "annual_capacity": self.annual_capacity,
            "outside_ordinary_income": self.outside_ordinary_income,
            "savings_destination": self.savings_destination,
            "ordinary_rate": self.rate(tax) if tax is not None else self.ordinary_rate,
        }

    def sha256(self, tax: TaxConfig) -> str:
        payload = {"version": SENSITIVITY_VERSION, **self.as_dict(tax)}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    record: dict = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("loss sensitivity JSON contains a duplicate field")
        record[key] = value
    return record


def load_loss_deduction_policy(path: Path | str) -> LossDeductionPolicy:
    """Read a strict JSON object or TOML containing only [loss_sensitivity]."""

    path = Path(path)
    if path.suffix.lower() == ".json":
        record = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields)
    elif path.suffix.lower() == ".toml":
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        if document.keys() != {"loss_sensitivity"}:
            raise ValueError("loss sensitivity TOML must contain only [loss_sensitivity]")
        record = document["loss_sensitivity"]
    else:
        raise ValueError("loss sensitivity policy must be a .json or .toml file")
    return LossDeductionPolicy.from_dict(record)


@dataclass(frozen=True, slots=True)
class DeductionYear:
    taxes: YearTax
    short_deduction: float
    long_deduction: float
    ordinary_tax_savings: float

    @property
    def deduction(self) -> float:
        return self.short_deduction + self.long_deduction

    def as_dict(self) -> dict:
        return {
            "capital_loss_deduction": self.deduction,
            "short_loss_deduction": self.short_deduction,
            "long_loss_deduction": self.long_deduction,
            "ordinary_tax_savings": self.ordinary_tax_savings,
        }


def evaluate_deduction_year(
    amounts: Amounts, short_carry: float, long_carry: float,
    tax: TaxConfig, policy: LossDeductionPolicy,
) -> DeductionYear:
    """Net capital items first, then consume the explicitly usable deduction.

    Investment-account tax remains separate from tax savings on outside income.
    Only the reduced carryovers can enter the next year. Terminal liquidation
    must call this afresh from the final year's same incoming carryovers.
    """

    outcome = net_and_tax(amounts, short_carry, long_carry, tax)
    deduction = min(
        outcome.short_carry_out + outcome.long_carry_out,
        policy.annual_capacity, policy.outside_ordinary_income,
    )
    short = min(outcome.short_carry_out, deduction)
    long = min(outcome.long_carry_out, max(deduction - short, 0.0))
    short_out = max(outcome.short_carry_out - short, 0.0)
    long_out = max(outcome.long_carry_out - long, 0.0)
    return DeductionYear(
        taxes=replace(
            outcome, short_carry_out=short_out, long_carry_out=long_out,
            short_carry_used=max(short_carry - short_out, 0.0),
            long_carry_used=max(long_carry - long_out, 0.0),
        ),
        short_deduction=short, long_deduction=long,
        ordinary_tax_savings=(short + long) * policy.rate(tax),
    )
