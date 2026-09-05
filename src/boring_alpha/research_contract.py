"""Canonical BA-002 behavior, independently comparable with a freeze record.

This module does not grant authorization or register dates. A synthetic
contract is useful for tests but cannot satisfy a historical execution gate.
The human charter is archived separately; editable prose is not run identity.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping

from boring_alpha.research_family import FAMILY_ID, PROTECTED_START


CONTRACT_VERSION = "BA-002-research-contract-v1"
ROWS = ("base", "double_cost", "without_9", "without_12", "without_15")
SYMBOLS = ("SPY", "IWM", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC")
HORIZONS = {
    "base": (9, 12, 15),
    "double_cost": (9, 12, 15),
    "without_9": (12, 15),
    "without_12": (9, 15),
    "without_15": (9, 12),
}


def expected_account_map() -> dict[str, dict[str, str]]:
    return {
        row: {
            "strategy": "strategy" if row == "base" else f"variant:{row}",
            "benchmark": "benchmark" if row == "base" else f"benchmark:{row}",
        }
        for row in ROWS
    }


def expected_row_definitions() -> dict[str, dict]:
    return {
        row: {
            "horizons": list(HORIZONS[row]),
            "warmup_months": 15,
            "cost_bps": 20.0 if row == "double_cost" else 10.0,
            "benchmark": {
                "exposure": 0.6,
                "rebalance": "annual",
                "cost_bps": 20.0 if row == "double_cost" else 10.0,
            },
        }
        for row in ROWS
    }


def canonical_json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("research identity must be finite JSON data") from exc


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def require_exact_behavior(actual: object, expected: object, name: str) -> None:
    """Numeric representation may vary; booleans must never impersonate numbers."""
    if isinstance(expected, dict):
        if not isinstance(actual, Mapping) or set(actual) != set(expected):
            raise ValueError(f"{name} has missing or extra fields")
        for key, value in expected.items():
            require_exact_behavior(actual[key], value, f"{name}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
            raise ValueError(f"{name} differs from the BA-002 definition")
        for index, value in enumerate(expected):
            require_exact_behavior(actual[index], value, f"{name}[{index}]")
    elif isinstance(expected, bool):
        if actual is not expected:
            raise ValueError(f"{name} differs from the BA-002 definition")
    elif isinstance(expected, (float, int)):
        if type(actual) not in (int, float) or not math.isfinite(actual) or actual != expected:
            raise ValueError(f"{name} differs from the BA-002 definition")
    elif actual != expected or type(actual) is not type(expected):
        raise ValueError(f"{name} differs from the BA-002 definition")


def _fixed_behavior() -> dict:
    # Lazy import keeps config/profile modules free to use this identity helper.
    from boring_alpha.tax.policy import SCENARIOS

    return {
        "contract_version": CONTRACT_VERSION,
        "family_id": FAMILY_ID,
        "strategy_id": "BA-002",
        "symbols": list(SYMBOLS),
        "rule": {
            "name": "equal-vote-cash-relative-trend",
            "horizons": [9, 12, 15],
            "warmup_months": 15,
            "sleeve_weight": 0.125,
            "rebalance": "monthly",
            "execution": "next-session-open",
            "cash_redistribution": False,
        },
        "grid": expected_row_definitions(),
        "benchmark": {
            "exposure": 0.6,
            "rebalance": "annual",
            "initial_allocation": "first-evaluation-session",
        },
        "initial_cash": 100000.0,
        "scenarios": [scenario.as_dict() for scenario in SCENARIOS],
        "criteria": {
            "primary_margin_min": 0.005,
            "stress_margin_exclusive_min": 0.0,
            "max_drawdown": 0.20,
            "no_worse_drawdown_than_benchmark": True,
            "return_convention": "post-liquidation-after-tax-cagr-nav-rescaling",
            "drawdown_convention": "pre-tax-cost-net-magnitude",
            "extrema": "independent-worst-strategy-minus-best-benchmark",
            "aggregation": "every-row-every-seen-period",
        },
    }


def build_contract(
    *,
    synthetic: bool,
    periods: Mapping[str, Mapping[str, object]],
    data_methodology: str,
    tax_policy_sha256: str,
    calendar_sha256: str,
    calendar_authority_sha256: str,
    tax_policy: Mapping[str, object] | None = None,
) -> dict:
    """Create a proposed contract; this is not an approval/freeze operation."""
    contract = {
        **_fixed_behavior(),
        "synthetic": synthetic,
        "periods": {
            name: {key: value.isoformat() if isinstance(value, date) else value for key, value in period.items()}
            for name, period in periods.items()
        },
        "data_methodology": data_methodology,
        "tax_policy_sha256": tax_policy_sha256,
        "calendar_sha256": calendar_sha256,
        "calendar_authority_sha256": calendar_authority_sha256,
    }
    if tax_policy is not None:
        contract["tax_policy"] = dict(tax_policy)
    return validate_contract(contract)


def _validate_tax_policy(policy: object) -> None:
    keys = {
        "ordinary_rate", "long_term_rate", "collectibles_rate", "qualified_fraction_low",
        "qualified_fraction", "gains_class",
    }
    if not isinstance(policy, Mapping) or set(policy) != keys:
        raise ValueError("contract.tax_policy must contain the complete policy with no extra fields")
    for key in ("ordinary_rate", "long_term_rate", "collectibles_rate", "qualified_fraction_low"):
        value = policy[key]
        upper_inclusive = key == "qualified_fraction_low"
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (value > 1 if upper_inclusive else value >= 1):
            raise ValueError(f"contract.tax_policy.{key} must be a finite rate/fraction")
    if policy["collectibles_rate"] > min(policy["ordinary_rate"], 0.28):
        raise ValueError("contract.tax_policy.collectibles_rate exceeds the selected cap")
    fractions = policy["qualified_fraction"]
    if not isinstance(fractions, Mapping) or set(fractions) != set(SYMBOLS):
        raise ValueError("contract.tax_policy.qualified_fraction must cover the exact universe")
    for symbol, value in fractions.items():
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"contract.tax_policy.qualified_fraction.{symbol} must be finite in [0, 1]")
    classes = {
        symbol: "collectibles" if symbol == "GLD" else "commodity_pool" if symbol == "DBC" else "standard"
        for symbol in SYMBOLS
    }
    require_exact_behavior(policy["gains_class"], classes, "contract.tax_policy.gains_class")


def validate_contract(contract: Mapping[str, object]) -> dict:
    if not isinstance(contract, Mapping):
        raise ValueError("research contract must be an object")
    fixed = _fixed_behavior()
    required = set(fixed) | {
        "synthetic", "periods", "data_methodology", "tax_policy_sha256",
        "calendar_sha256", "calendar_authority_sha256",
    }
    if not required.issubset(contract) or set(contract) - required - {"tax_policy"}:
        raise ValueError("research contract has missing or extra fields")
    for key, value in fixed.items():
        require_exact_behavior(contract[key], value, f"contract.{key}")
    if type(contract["synthetic"]) is not bool:
        raise ValueError("contract.synthetic must be boolean")
    for key in ("tax_policy_sha256", "calendar_sha256", "calendar_authority_sha256"):
        require_digest(contract[key], f"contract.{key}")
    methodology = contract["data_methodology"]
    if not isinstance(methodology, str) or not methodology.strip():
        raise ValueError("contract.data_methodology is required")
    if not contract["synthetic"] and methodology != "yahoo-adjusted-v2+dgs3mo-v1":
        raise ValueError("historical BA-002 methodology differs from the selected v2 inputs")
    if "tax_policy" in contract:
        _validate_tax_policy(contract["tax_policy"])
        if canonical_sha256(contract["tax_policy"]) != contract["tax_policy_sha256"]:
            raise ValueError("contract tax policy contents do not match tax_policy_sha256")
    elif not contract["synthetic"]:
        raise ValueError("historical research contract requires complete tax_policy contents")
    periods = contract["periods"]
    required_periods = {"development", "validation"} | (set() if contract["synthetic"] else {"sealed"})
    if not isinstance(periods, Mapping) or not required_periods.issubset(periods) or set(periods) - {"development", "validation", "sealed"}:
        raise ValueError("contract requires development and validation periods, and a historical sealed period")
    previous_end: date | None = None
    for name in ("development", "validation", "sealed"):
        if name not in periods:
            continue
        record = periods[name]
        if not isinstance(record, Mapping) or set(record) != {"start", "end", "status"}:
            raise ValueError(f"contract period {name} requires exact start, end and status")
        expected_status = "unopened" if name == "sealed" else "seen"
        if record["status"] != expected_status:
            raise ValueError(f"contract period {name} must have {expected_status!r} status")
        try:
            start, end = date.fromisoformat(record["start"]), date.fromisoformat(record["end"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"contract period {name} requires fixed ISO dates") from exc
        if start > end or previous_end is not None and start <= previous_end:
            raise ValueError("contract periods must be ordered, disjoint complete intervals")
        if not contract['synthetic']:
            if name != 'sealed' and end >= PROTECTED_START:
                raise ValueError(f'historical {name} cannot label protected dates on or after {PROTECTED_START} as seen')
            if name == 'sealed' and start != PROTECTED_START:
                raise ValueError(f'historical sealed period must start at the family protected boundary {PROTECTED_START}')
        previous_end = end
    # JSON round-trip both rejects non-finite metadata and detaches mutable input.
    return json.loads(canonical_json(dict(contract)))


def load_contract(path: str | Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read research contract {path}: {exc}") from exc
    return validate_contract(value)


def contract_sha256(contract: Mapping[str, object]) -> str:
    return canonical_sha256(validate_contract(contract))


def require_approved_contract(contract: Mapping[str, object], approved_contract: Mapping[str, object] | None) -> None:
    """Cross-check independently loaded freeze contents, never a self-asserted flag."""
    selected = validate_contract(contract)
    if selected["synthetic"]:
        raise ValueError("synthetic contracts cannot authorize historical research")
    if approved_contract is None:
        raise ValueError("historical evidence requires an independently approved contract")
    approved = validate_contract(approved_contract)
    if approved["synthetic"] or canonical_sha256(selected) != canonical_sha256(approved):
        raise ValueError("selected contract differs from the independently approved freeze")


def _source_fingerprint(paths: list[Path]) -> str:
    package_root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for source_path in sorted(paths):
        digest.update(source_path.relative_to(package_root).as_posix().encode("utf-8"))
        digest.update(source_path.read_bytes())
    return digest.hexdigest()


def code_fingerprint() -> str:
    """Matches the reporter, without importing report/config back into the evaluator."""
    return _source_fingerprint(list(Path(__file__).resolve().parent.rglob("*.py")))


def evaluator_fingerprint() -> str:
    package_root = Path(__file__).resolve().parent
    return _source_fingerprint([
        package_root / name
        for name in ("criteria_ba002.py", "period_evidence.py", "research_contract.py")
    ])
