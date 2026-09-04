# After-Tax Overlay Implementation Plan (plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute after-tax results for every run a sweep produces, under a fixed eight-scenario grid, from the pre-tax artifacts alone; wire them into sweeps as `tax.json`; add an `aftertax` command that re-scores existing sweeps; and write the post-hoc after-tax note on BA-001's two archived sweeps.

**Architecture:** The overlay is a pure function over a `BacktestResult`, the `MarketData` it ran on, a `DistributionTable`, a `TaxConfig` and a `Scenario`. It converts fills to real (split-adjusted) shares, keeps tax lots with unadjusted-price basis, lets each ex-date open a child lot, applies wash sales chronologically, and then computes year-end tax with character-retaining carryovers under the after-tax NAV convention (rescaling the pre-tax path at each year end). Nothing in the engine changes. The sweep runs the overlay for every scenario on every run and writes `tax.json`; `aftertax` reconstructs runs from archived CSVs and does the same.

**Tech Stack:** Python ≥ 3.11, standard library only, `unittest`-style tests run with pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-after-tax-evaluation-design.md` (revision 3.1). This plan implements §4 (all subsections), §5.3 (secondary rows), §7, §8, and the matching parts of §9 and §12 steps 3, 6, 7. Plan 1 (`docs/superpowers/plans/2026-09-04-after-tax-foundations.md`, merged) built the interfaces this plan consumes.

## Global Constraints

- Python ≥ 3.11; no third-party dependencies may be added.
- Tests are `unittest.TestCase` classes in `tests/test_*.py`, run with `.venv/bin/python -m pytest -q`. The suite passes today at 339 executions (3 subtests) and must pass after every task.
- The engine, signal policies, portfolio, execution, loader and gates do not change. The overlay never reaches into engine internals; it reads `BacktestResult.fills`, `BacktestResult.equity_curve`, `MarketData`, and a `DistributionTable`.
- Exact strings from the spec: `OVERLAY_VERSION = "tax-overlay-v1"`; scenario axes `hifo | fifo`, `deferral | mtm_60_40`, `base | low`, eight scenarios fixed in code, keyed `"{lot_method}-{commodity_treatment}-{qualified_set}"`; gains classes `standard | collectibles | commodity_pool`; `[tax]` keys exactly `distributions_path, ordinary_rate, long_term_rate, collectibles_rate, qualified_fraction_low, qualified_fraction, gains_class`; `collectibles_rate ≤ min(ordinary_rate, 0.28)`; artifact file `tax.json`; post-hoc file `tax-<policy-hash-12>-<distributions-hash-12>-<code-hash-12>.json`; manifest block `distributions_manifest`; archived input `input_distributions.csv.gz`.
- `artifact_schema` becomes `6` in Task 7 and only there; `READABLE_SCHEMAS` becomes `(5, 6)`. Existing tests that assert `5` are updated in that task; the classify fixtures stay at 5 and must still classify.
- Holding-period rules as stated in the spec: long-term if `(sale_date − open_date).days > 365`; qualified if held more than 60 days within the 121-day window beginning 60 days before the ex-date; wash-sale window 30 calendar days either side.
- The after-tax NAV convention (spec §4.8): taxes are computed from unscaled amounts multiplied by the cumulative scale `c`; `c_{y+1} = c_y − tax_y / W_y`; liquidation is the final year computed twice, and `tax_liquidation` is the difference.
- Drawdown is never recomputed after tax.
- Artifacts are write-once. Nothing under `experiments/` or `data/` is edited or deleted; Task 9 reads two archived sweeps and adds one file to each sweep directory through the write-once path.
- Commit after every task; imperative one-line subject, short body, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Never run a sealed-period evaluation. Never fetch from the network.

---

## File structure

| Path | Responsibility | Task |
|---|---|---|
| `src/boring_alpha/domain.py` | `GAINS_CLASSES` shared vocabulary | 1 |
| `src/boring_alpha/config.py` | `TaxConfig`, `[tax]` schema, `_load_tax`, `load_tax_policy` for standalone policy files | 1 |
| `src/boring_alpha/tax/__init__.py` | package exports | 1 |
| `src/boring_alpha/tax/policy.py` | `Scenario`, `SCENARIOS`, `OVERLAY_VERSION`, `policy_record`, `policy_sha256`, `qualified_fraction` | 1 |
| `configs/tax_policy.toml` | the stylized BA-001 policy the note uses | 1 |
| `src/boring_alpha/tax/lots.py` | `Lot`, `Realized`, `Distribution`, `LotBook` (buy, sell by method, distribute), `FuturePurchase`, `apply_wash_sales` | 2, 3, 4 |
| `src/boring_alpha/tax/yearend.py` | `Amounts`, `YearTax`, `net_and_tax`, `qualifies`, `is_long_term`, `classify_gain` | 5 |
| `src/boring_alpha/tax/overlay.py` | `apply_overlay`, `run_scenarios`, output dict | 6 |
| `src/boring_alpha/sweep.py` | tax runs, `tax.json`, summary block, manifest fields, distributions archive, `static_full` row | 7 |
| `src/boring_alpha/report.py` | `ARTIFACT_SCHEMA = 6`, `READABLE_SCHEMAS = (5, 6)` | 7 |
| `src/boring_alpha/tax/reconstruct.py` | `BacktestResult` and `MarketData` from archived sweep files | 8 |
| `src/boring_alpha/cli.py` | `aftertax` command | 8 |
| `docs/notes/2026-09-04-BA-001-after-tax.md` | the post-hoc note | 9 |
| Tests | `tests/test_tax_policy.py`, `tests/test_tax_lots.py`, `tests/test_tax_yearend.py`, `tests/test_tax_overlay.py`, additions to `tests/test_config.py`, `tests/test_sweep.py`, `tests/test_cli.py`, `tests/test_classify.py`, `tests/test_report.py`, `tests/test_gates.py`, `tests/test_slippage.py` | per task |

---

### Task 1: The `[tax]` configuration, the scenario grid, and the policy hash

**Files:**
- Modify: `src/boring_alpha/domain.py` (add `GAINS_CLASSES` after `REBALANCE_SCHEDULES`)
- Modify: `src/boring_alpha/config.py` (`TaxConfig`, schema entry, `_load_tax`, `load_tax_policy`, `AppConfig.tax`)
- Create: `src/boring_alpha/tax/__init__.py`, `src/boring_alpha/tax/policy.py`
- Create: `configs/tax_policy.toml`
- Test: `tests/test_config.py` (append), `tests/test_tax_policy.py`

**Interfaces:**
- Consumes: `_require`, `_finite`, `_resolve_path`, `_SCHEMA` from `config.py`; `REBALANCE_SCHEDULES` pattern in `domain.py`.
- Produces: `domain.GAINS_CLASSES = ("standard", "collectibles", "commodity_pool")`; `config.TaxConfig(distributions_path: Path, ordinary_rate: float, long_term_rate: float, collectibles_rate: float, qualified_fraction_low: float, qualified_fraction: dict[str, float], gains_class: dict[str, str])`; `AppConfig.tax: TaxConfig | None`; `config.load_tax_policy(path, symbols) -> TaxConfig`; `tax.policy.Scenario(lot_method, commodity_treatment, qualified_set)` with `.key`; `tax.policy.SCENARIOS` (8); `tax.policy.OVERLAY_VERSION`; `tax.policy.policy_record(tax) -> dict`; `tax.policy.policy_sha256(tax) -> str`; `tax.policy.qualified_fraction(tax, scenario, symbol) -> float`.

- [ ] **Step 1: Write the failing config tests**

Append to `tests/test_config.py`:

```python
TAX = VALID + """
[tax]
distributions_path = "../data/distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.5

[tax.qualified_fraction]
A = 0.95
B = 0.0

[tax.gains_class]
A = "standard"
B = "collectibles"
"""


class TaxConfigTests(unittest.TestCase):
    def test_an_absent_table_means_no_tax_policy(self) -> None:
        config, _ = _load(VALID)
        self.assertIsNone(config.tax)

    def test_the_table_is_parsed_and_the_path_resolved_against_the_config(self) -> None:
        config, path = _load(TAX)
        assert config.tax is not None
        self.assertAlmostEqual(config.tax.ordinary_rate, 0.35)
        self.assertAlmostEqual(config.tax.long_term_rate, 0.20)
        self.assertAlmostEqual(config.tax.collectibles_rate, 0.28)
        self.assertAlmostEqual(config.tax.qualified_fraction_low, 0.5)
        self.assertEqual(config.tax.qualified_fraction, {"A": 0.95, "B": 0.0})
        self.assertEqual(config.tax.gains_class, {"A": "standard", "B": "collectibles"})
        self.assertEqual(
            config.tax.distributions_path,
            (path.parent / ".." / "data" / "distributions_daily.csv").resolve(),
        )

    def test_the_tax_table_does_not_enter_the_strategy_spec_hash(self) -> None:
        without, _ = _load(VALID)
        with_tax, _ = _load(TAX)
        self.assertEqual(without.strategy_spec_sha256, with_tax.strategy_spec_sha256)

    def test_collectibles_rate_may_not_exceed_the_cap_or_the_ordinary_rate(self) -> None:
        with self.assertRaisesRegex(ValueError, "collectibles_rate"):
            _load(TAX.replace("collectibles_rate = 0.28", "collectibles_rate = 0.30"))
        with self.assertRaisesRegex(ValueError, "collectibles_rate"):
            _load(TAX.replace("ordinary_rate = 0.35", "ordinary_rate = 0.24"))

    def test_rates_must_lie_in_the_unit_interval(self) -> None:
        with self.assertRaisesRegex(ValueError, "tax.ordinary_rate"):
            _load(TAX.replace("ordinary_rate = 0.35", "ordinary_rate = 1.0"))
        with self.assertRaisesRegex(ValueError, "tax.qualified_fraction_low"):
            _load(TAX.replace("qualified_fraction_low = 0.5", "qualified_fraction_low = 1.5"))

    def test_every_symbol_needs_a_fraction_and_a_class(self) -> None:
        with self.assertRaisesRegex(ValueError, "tax.qualified_fraction is missing B"):
            _load(TAX.replace("B = 0.0\n", ""))
        with self.assertRaisesRegex(ValueError, "tax.gains_class is missing B"):
            _load(TAX.replace('B = "collectibles"\n', ""))

    def test_unknown_symbols_fractions_and_classes_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "not in strategy.symbols"):
            _load(TAX.replace("[tax.gains_class]", "[tax.gains_class]\nZ = \"standard\""))
        with self.assertRaisesRegex(ValueError, "tax.qualified_fraction.A"):
            _load(TAX.replace("A = 0.95", "A = 1.2"))
        with self.assertRaisesRegex(ValueError, "tax.gains_class.B"):
            _load(TAX.replace('B = "collectibles"', 'B = "futures"'))

    def test_unknown_keys_are_refused(self) -> None:
        # The key must sit in [tax] itself; appended text would land in the last sub-table.
        with self.assertRaisesRegex(ValueError, "unknown key"):
            _load(TAX.replace("qualified_fraction_low = 0.5", 'qualified_fraction_low = 0.5\nlot_method = "hifo"'))

    def test_a_standalone_policy_file_loads_for_a_symbol_set(self) -> None:
        from boring_alpha.config import load_tax_policy

        text = TAX[TAX.index("[tax]"):]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.toml"
            path.write_text(text, encoding="utf-8")
            policy = load_tax_policy(path, ("A", "B"))
            self.assertAlmostEqual(policy.ordinary_rate, 0.35)
            with self.assertRaisesRegex(ValueError, "not in strategy.symbols"):
                load_tax_policy(path, ("A",))
            (Path(directory) / "bad.toml").write_text("[strategy]\nid = \"X\"\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "only a \\[tax\\] table"):
                load_tax_policy(Path(directory) / "bad.toml", ("A", "B"))

    def test_the_checked_in_ba_001_policy_loads_for_the_charter_universe(self) -> None:
        from boring_alpha.config import load_tax_policy

        policy = load_tax_policy(
            REPO_ROOT / "configs" / "tax_policy.toml",
            ("SPY", "IWM", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC"),
        )
        self.assertEqual(policy.gains_class["GLD"], "collectibles")
        self.assertEqual(policy.gains_class["DBC"], "commodity_pool")
        self.assertAlmostEqual(policy.qualified_fraction["EEM"], 0.61)
```

- [ ] **Step 2: Write the failing policy tests**

Create `tests/test_tax_policy.py`:

```python
"""The scenario grid is fixed in code and the policy hash names what was applied."""

from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import load_tax_policy
from boring_alpha.tax.policy import (
    OVERLAY_VERSION,
    SCENARIOS,
    Scenario,
    policy_record,
    policy_sha256,
    qualified_fraction,
)

POLICY = """
[tax]
distributions_path = "distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.5

[tax.qualified_fraction]
A = 0.95
B = 0.3
C = 0.0

[tax.gains_class]
A = "standard"
B = "standard"
C = "commodity_pool"
"""


def _policy(text: str = POLICY):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "policy.toml"
        path.write_text(text, encoding="utf-8")
        return load_tax_policy(path, ("A", "B", "C"))


class GridTests(unittest.TestCase):
    def test_there_are_exactly_eight_scenarios_in_a_fixed_order(self) -> None:
        self.assertEqual(len(SCENARIOS), 8)
        self.assertEqual(
            [scenario.key for scenario in SCENARIOS],
            [
                "hifo-deferral-base", "hifo-deferral-low",
                "hifo-mtm_60_40-base", "hifo-mtm_60_40-low",
                "fifo-deferral-base", "fifo-deferral-low",
                "fifo-mtm_60_40-base", "fifo-mtm_60_40-low",
            ],
        )
        self.assertEqual(SCENARIOS[0], Scenario("hifo", "deferral", "base"))

    def test_an_unknown_axis_value_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "lot_method"):
            Scenario("lifo", "deferral", "base")
        with self.assertRaisesRegex(ValueError, "commodity_treatment"):
            Scenario("hifo", "k1", "base")
        with self.assertRaisesRegex(ValueError, "qualified_set"):
            Scenario("hifo", "deferral", "high")

    def test_the_overlay_version_is_named(self) -> None:
        self.assertEqual(OVERLAY_VERSION, "tax-overlay-v1")


class PolicyHashTests(unittest.TestCase):
    def test_the_record_excludes_the_path_and_the_hash_is_stable(self) -> None:
        policy = _policy()
        record = policy_record(policy)
        self.assertNotIn("distributions_path", record)
        self.assertEqual(record["gains_class"], {"A": "standard", "B": "standard", "C": "commodity_pool"})
        self.assertEqual(policy_sha256(policy), policy_sha256(_policy()))
        self.assertEqual(len(policy_sha256(policy)), 64)

    def test_changing_a_rate_or_a_class_changes_the_hash(self) -> None:
        base = policy_sha256(_policy())
        self.assertNotEqual(base, policy_sha256(_policy(POLICY.replace("0.35", "0.32"))))
        self.assertNotEqual(base, policy_sha256(_policy(POLICY.replace('B = "standard"', 'B = "collectibles"'))))

    def test_the_path_does_not_change_the_hash(self) -> None:
        self.assertEqual(
            policy_sha256(_policy()),
            policy_sha256(_policy(POLICY.replace("distributions_daily.csv", "elsewhere.csv"))),
        )


class QualifiedFractionTests(unittest.TestCase):
    def test_the_low_set_caps_every_positive_fraction(self) -> None:
        policy = _policy()
        base, low = Scenario("hifo", "deferral", "base"), Scenario("hifo", "deferral", "low")
        self.assertAlmostEqual(qualified_fraction(policy, base, "A"), 0.95)
        self.assertAlmostEqual(qualified_fraction(policy, low, "A"), 0.5)
        # A fraction already below the low value is not raised to it.
        self.assertAlmostEqual(qualified_fraction(policy, low, "B"), 0.3)
        # Zero stays zero: bonds and commodity pools pay no qualified income.
        self.assertAlmostEqual(qualified_fraction(policy, low, "C"), 0.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_tax_policy.py -q`
Expected: `TaxConfigTests` fail (`AttributeError: 'AppConfig' object has no attribute 'tax'`, `unknown table(s) in configuration: tax`); `test_tax_policy.py` fails to import (`ModuleNotFoundError: No module named 'boring_alpha.tax'`).

- [ ] **Step 4: Add the shared vocabulary**

In `src/boring_alpha/domain.py`, directly after the `REBALANCE_SCHEDULES` line, add:

```python
# How a symbol's capital gains are taxed in the after-tax overlay. Shared by
# configuration validation and the tax package, defined once.
GAINS_CLASSES: tuple[str, ...] = ("standard", "collectibles", "commodity_pool")
```

- [ ] **Step 5: Add the configuration**

In `src/boring_alpha/config.py`:

Change the domain import to `from boring_alpha.domain import GAINS_CLASSES, REBALANCE_SCHEDULES`.

After `BenchmarkConfig`, add:

```python
@dataclass(frozen=True, slots=True)
class TaxConfig:
    """Stylized tax policy for the after-tax overlay (spec §4.9).

    Federal-only rates declared for the record; the account holder's real rates
    belong in an untracked local file. `qualified_fraction` is the base set;
    the scenario grid also runs every income-paying symbol at
    `qualified_fraction_low`. The path names the distributions file; it is not
    part of the policy's identity.
    """

    distributions_path: Path
    ordinary_rate: float
    long_term_rate: float
    collectibles_rate: float
    qualified_fraction_low: float
    qualified_fraction: dict[str, float]
    gains_class: dict[str, str]


COLLECTIBLES_RATE_CAP = 0.28
_TAX_KEYS = frozenset(
    {
        "distributions_path", "ordinary_rate", "long_term_rate", "collectibles_rate",
        "qualified_fraction_low", "qualified_fraction", "gains_class",
    }
)
```

In `AppConfig`, add `tax: TaxConfig | None` immediately after `benchmark: BenchmarkConfig | None`.

In `_SCHEMA`, add `"tax": _TAX_KEYS,` after the `"benchmark"` entry.

After `_load_benchmark`, add:

```python
def _rate(raw: dict[str, object], key: str) -> float:
    value = _finite(float(_require(raw, "tax", key)), f"tax.{key}")
    if not 0.0 <= value < 1.0:
        raise ValueError(f"tax.{key} must be in [0, 1), got {value!r}")
    return value


def _load_symbol_table(
    raw: dict[str, object], name: str, symbols: tuple[str, ...], kind: str
) -> dict[str, object]:
    """`[tax.<name>]`: one entry per symbol of the universe, no extras."""

    table = _require(raw, "tax", name)
    if not isinstance(table, dict):
        raise ValueError(f"tax.{name} must be a table of symbol = value")
    result: dict[str, object] = {}
    for symbol, value in table.items():
        upper = symbol.upper()
        if upper not in symbols:
            raise ValueError(f"tax.{name} names {symbol}, which is not in strategy.symbols")
        if kind == "fraction":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"tax.{name}.{symbol} must be a number in [0, 1]")
            number = _finite(float(value), f"tax.{name}.{symbol}")
            if not 0.0 <= number <= 1.0:
                raise ValueError(f"tax.{name}.{symbol} must be in [0, 1], got {value!r}")
            result[upper] = number
        else:
            label = str(value).lower()
            if label not in GAINS_CLASSES:
                raise ValueError(
                    f"tax.{name}.{symbol} must be one of {', '.join(GAINS_CLASSES)}, got {value!r}"
                )
            result[upper] = label
    missing = sorted(set(symbols) - set(result))
    if missing:
        raise ValueError(f"tax.{name} is missing {', '.join(missing)}")
    return result


def _load_tax(
    raw: dict[str, object] | None, symbols: tuple[str, ...], root: Path
) -> TaxConfig | None:
    if raw is None:
        return None
    unknown = sorted(set(raw) - _TAX_KEYS)
    if unknown:
        raise ValueError(f"unknown key(s) in [tax]: {', '.join(unknown)}")
    ordinary = _rate(raw, "ordinary_rate")
    long_term = _rate(raw, "long_term_rate")
    collectibles = _rate(raw, "collectibles_rate")
    cap = min(ordinary, COLLECTIBLES_RATE_CAP)
    if collectibles > cap + 1e-12:
        raise ValueError(
            f"tax.collectibles_rate must not exceed min(ordinary_rate, {COLLECTIBLES_RATE_CAP}) "
            f"= {cap:.4f}, got {collectibles!r}; the statutory rule is the ordinary rate "
            "capped at 28%"
        )
    low = _finite(
        float(_require(raw, "tax", "qualified_fraction_low")), "tax.qualified_fraction_low"
    )
    if not 0.0 <= low <= 1.0:
        raise ValueError(f"tax.qualified_fraction_low must be in [0, 1], got {low!r}")
    fractions = _load_symbol_table(raw, "qualified_fraction", symbols, "fraction")
    classes = _load_symbol_table(raw, "gains_class", symbols, "class")
    path = _resolve_path(
        _require(raw, "tax", "distributions_path"), root, "tax.distributions_path"
    )
    return TaxConfig(
        distributions_path=path,
        ordinary_rate=ordinary,
        long_term_rate=long_term,
        collectibles_rate=collectibles,
        qualified_fraction_low=low,
        qualified_fraction={k: float(v) for k, v in fractions.items()},
        gains_class={k: str(v) for k, v in classes.items()},
    )


def load_tax_policy(path: str | Path, symbols: tuple[str, ...]) -> TaxConfig:
    """A standalone policy file: exactly one `[tax]` table, validated for `symbols`.

    Used by the `aftertax` command, which scores archived sweeps whose own
    configuration carried no tax table.
    """

    policy_path = Path(path).resolve()
    raw = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    if set(raw) != {"tax"} or not isinstance(raw["tax"], dict):
        raise ValueError(f"{policy_path} must contain only a [tax] table")
    tax = _load_tax(raw["tax"], tuple(symbol.upper() for symbol in symbols), policy_path.parent)
    assert tax is not None
    return tax
```

In `load_config`, after `benchmark = _load_benchmark(raw.get("benchmark"))`, add `tax = _load_tax(raw.get("tax"), strategy.symbols, root)`, and in the `AppConfig(...)` construction add `tax=tax,` after `benchmark=benchmark,`. The spec hash call is unchanged: the tax policy is a scoring policy, not part of what the strategy is.

- [ ] **Step 6: Create the tax package and the grid**

Create `src/boring_alpha/tax/__init__.py`:

```python
"""After-tax evaluation: a pure overlay over pre-tax run artifacts (spec §4)."""

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
    "policy_record",
    "policy_sha256",
    "qualified_fraction",
]
```

Create `src/boring_alpha/tax/policy.py`:

```python
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
```

Create `configs/tax_policy.toml`:

```toml
# Stylized, federal-only tax policy for the after-tax overlay (spec §4.9).
# Rates are a scenario for the record, not anyone's actual bracket; real rates
# belong in an untracked local copy. State tax, the 3.8% net investment income
# tax and historical rate changes are ignored by construction. The base
# qualified fractions for IWM, EFA and EEM are the issuers' reported 2019
# figures as cited in the design review; SPY's is an expectation. The scenario
# grid also runs every income-paying sleeve at qualified_fraction_low.

[tax]
distributions_path = "../data/current/distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.50

[tax.qualified_fraction]
SPY = 0.95
IWM = 0.71
EFA = 0.95
EEM = 0.61
IEF = 0.0
TLT = 0.0
GLD = 0.0
DBC = 0.0

[tax.gains_class]
SPY = "standard"
IWM = "standard"
EFA = "standard"
EEM = "standard"
IEF = "standard"
TLT = "standard"
GLD = "collectibles"
DBC = "commodity_pool"
```

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_tax_policy.py -q`
Expected: all pass (10 new config tests, 7 new policy tests).

- [ ] **Step 8: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `356 passed, 3 subtests passed`.

```bash
git add src/boring_alpha/domain.py src/boring_alpha/config.py src/boring_alpha/tax/__init__.py src/boring_alpha/tax/policy.py configs/tax_policy.toml tests/test_config.py tests/test_tax_policy.py
git commit -m "Declare the tax policy table and the fixed eight-scenario grid

A [tax] table names the distributions file, three stylized rates, a low
qualified fraction and per-symbol fractions and gains classes; it does not
enter the strategy spec hash, since it scores a strategy rather than
defining one. The scenario grid — two lot methods, two commodity-pool
treatments, two qualified sets — is fixed in code. A standalone policy
file loader serves the aftertax command, and the BA-001 policy is checked
in for the post-hoc note.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Lots in real shares — opening and selling by method

**Files:**
- Create: `src/boring_alpha/tax/lots.py`
- Test: `tests/test_tax_lots.py`

**Interfaces:**
- Consumes: `MarketData.bar(day, symbol).close`; `DistributionTable.close(day, symbol)`.
- Produces: `adjustment_factor(data, table, day, symbol) -> float` (A/P); `Lot` (fields `lot_id, symbol, opened, acquired, shares, basis, source, closed, replacement_capacity, disallowed_attached`, property `basis_per_share`); `Realized` (frozen: `symbol, lot_id, opened, sold, shares, proceeds, basis, disallowed=0.0`, property `gain = proceeds − basis + disallowed`); `LotBook(method)` with `.lots`, `.open_lots(symbol)`, `.shares_held(symbol)`, `.buy(symbol, day, shares, basis, *, source="buy", opened=None, extra_basis=0.0, replacement_capacity=None) -> Lot`, `.sell(symbol, day, shares, proceeds) -> list[Realized]`. Tasks 3 and 4 add `distribute` and wash sales to the same class and module.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tax_lots.py`:

```python
"""Tax lots are kept in real shares with unadjusted-dollar basis (spec §4.2)."""

from datetime import date
import unittest

from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.tax.lots import LotBook, Realized, adjustment_factor

D0, D1, D2, D3 = date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)


def _market(prices: dict[str, list[float]], days=(D0, D1, D2, D3)) -> MarketData:
    """Adjusted bars with open equal to close."""

    bars = [
        PriceBar(day, symbol, price, price)
        for symbol, series in prices.items()
        for day, price in zip(days, series)
    ]
    return MarketData(bars, {day: 1.0 for day in days}, source="test")


def _table(closes: dict[str, list[float]], dividends: dict[str, list[float]] | None = None,
           days=(D0, D1, D2, D3)) -> DistributionTable:
    """Unadjusted closes and per-share dividends, zero unless given."""

    rows = []
    for symbol, series in closes.items():
        paid = (dividends or {}).get(symbol, [0.0] * len(series))
        rows.extend((day, symbol, close, dividend) for day, close, dividend in zip(days, series, paid))
    return DistributionTable(rows, splits={symbol: [] for symbol in closes}, sha256="0" * 64, source="test")


class AdjustmentFactorTests(unittest.TestCase):
    def test_factor_is_adjusted_over_unadjusted_close(self) -> None:
        data = _market({"A": [50.0, 50.0, 50.0, 50.0]})
        table = _table({"A": [100.0, 100.0, 100.0, 100.0]})
        self.assertAlmostEqual(adjustment_factor(data, table, D0, "A"), 0.5)
        # Ten engine units at a factor of 0.5 are five real shares: the past is
        # adjusted downwards, so old lots hold fewer real shares than units.
        self.assertAlmostEqual(10.0 * adjustment_factor(data, table, D0, "A"), 5.0)


class BuyTests(unittest.TestCase):
    def test_a_buy_opens_a_lot_with_full_replacement_capacity(self) -> None:
        book = LotBook("fifo")
        lot = book.buy("A", D0, 10.0, 1001.0)
        self.assertEqual(lot.lot_id, 1)
        self.assertEqual((lot.opened, lot.acquired, lot.source), (D0, D0, "buy"))
        self.assertAlmostEqual(lot.basis_per_share, 100.1)
        self.assertAlmostEqual(lot.replacement_capacity, 10.0)
        self.assertEqual(book.open_lots("A"), (lot,))
        self.assertAlmostEqual(book.shares_held("A"), 10.0)

    def test_tacked_opening_and_attached_basis_are_honoured(self) -> None:
        book = LotBook("fifo")
        lot = book.buy("A", D2, 4.0, 400.0, opened=D0, extra_basis=25.0, replacement_capacity=1.0)
        self.assertEqual((lot.opened, lot.acquired), (D0, D2))
        self.assertAlmostEqual(lot.basis, 425.0)
        self.assertAlmostEqual(lot.disallowed_attached, 25.0)
        self.assertAlmostEqual(lot.replacement_capacity, 1.0)

    def test_non_positive_shares_or_negative_basis_are_refused(self) -> None:
        book = LotBook("fifo")
        with self.assertRaisesRegex(ValueError, "shares"):
            book.buy("A", D0, 0.0, 1.0)
        with self.assertRaisesRegex(ValueError, "basis"):
            book.buy("A", D0, 1.0, -1.0)

    def test_an_unknown_method_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "lot method"):
            LotBook("lifo")


class SellTests(unittest.TestCase):
    """Two lots: 10 shares at 1001 (100.1 each) on D0, 10 shares at 1200 (120 each) on D1.
    Fifteen shares sold on D3 for 1650 net of cost."""

    def _book(self, method: str) -> LotBook:
        book = LotBook(method)
        book.buy("A", D0, 10.0, 1001.0)
        book.buy("A", D1, 10.0, 1200.0)
        return book

    def test_fifo_sells_the_earliest_lot_first_and_splits_the_second(self) -> None:
        book = self._book("fifo")
        records = book.sell("A", D3, 15.0, 1650.0)
        self.assertEqual([(r.lot_id, r.shares) for r in records], [(1, 10.0), (2, 5.0)])
        self.assertAlmostEqual(records[0].proceeds, 1100.0)
        self.assertAlmostEqual(records[0].basis, 1001.0)
        self.assertAlmostEqual(records[0].gain, 99.0)
        self.assertAlmostEqual(records[1].proceeds, 550.0)
        self.assertAlmostEqual(records[1].basis, 600.0)
        self.assertAlmostEqual(records[1].gain, -50.0)
        remaining = book.open_lots("A")
        self.assertEqual([lot.lot_id for lot in remaining], [2])
        self.assertAlmostEqual(remaining[0].shares, 5.0)
        self.assertAlmostEqual(remaining[0].basis, 600.0)
        self.assertEqual(book.lots[1].closed, D3)
        self.assertIsNone(book.lots[2].closed)

    def test_hifo_sells_the_highest_basis_per_share_first(self) -> None:
        book = self._book("hifo")
        records = book.sell("A", D3, 15.0, 1650.0)
        self.assertEqual([(r.lot_id, r.shares) for r in records], [(2, 10.0), (1, 5.0)])
        self.assertAlmostEqual(records[0].gain, -100.0)
        self.assertAlmostEqual(records[1].basis, 500.5)
        self.assertAlmostEqual(records[1].gain, 49.5)
        remaining = book.open_lots("A")
        self.assertEqual([lot.lot_id for lot in remaining], [1])
        self.assertAlmostEqual(remaining[0].basis, 500.5)

    def test_records_carry_opening_and_sale_dates(self) -> None:
        records = self._book("fifo").sell("A", D3, 15.0, 1650.0)
        self.assertEqual((records[0].opened, records[0].sold), (D0, D3))
        self.assertEqual(records[1].opened, D1)

    def test_selling_reduces_replacement_capacity_to_what_remains(self) -> None:
        book = self._book("fifo")
        book.sell("A", D3, 15.0, 1650.0)
        self.assertAlmostEqual(book.lots[1].replacement_capacity, 0.0)
        self.assertAlmostEqual(book.lots[2].replacement_capacity, 5.0)

    def test_selling_more_than_held_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "only 20"):
            self._book("fifo").sell("A", D3, 20.5, 1.0)

    def test_a_rounding_sliver_over_the_holding_is_tolerated(self) -> None:
        records = self._book("fifo").sell("A", D3, 20.0 + 1e-10, 2200.0)
        self.assertAlmostEqual(sum(r.shares for r in records), 20.0)

    def test_gain_is_proceeds_less_basis_plus_disallowed(self) -> None:
        record = Realized("A", 1, D0, D3, 1.0, 90.0, 100.0, disallowed=6.0)
        self.assertAlmostEqual(record.gain, -4.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_tax_lots.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'boring_alpha.tax.lots'`.

- [ ] **Step 3: Implement**

Create `src/boring_alpha/tax/lots.py`:

```python
"""Tax lots in real shares (spec §4.2, §4.3, §4.6).

Engine quantities are in adjusted units: a position of `q` units is worth
`q · A` at adjusted close `A`. A real account holding that value at unadjusted
close `P` holds `q · A / P` shares. Lots are kept in those real shares with
unadjusted-dollar basis, so gains, holding periods and wash sales follow the
rules a broker's statement would, and the past is not flattered by adjusted
prices that already contain reinvested distributions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData

LOT_METHODS: tuple[str, ...] = ("hifo", "fifo")
_SHARE_TOLERANCE = 1e-9


def adjustment_factor(data: MarketData, table: DistributionTable, day: date, symbol: str) -> float:
    """Adjusted over unadjusted close on `day`: engine units times this are real shares.

    The ratio changes only at ex-dates (both series are split-adjusted), so it
    is constant between distributions and a lot's real shares grow only when a
    child lot is opened.
    """

    return data.bar(day, symbol).close / table.close(day, symbol)


@dataclass
class Lot:
    lot_id: int
    symbol: str
    opened: date
    """Start of the holding period. A wash sale tacks the sold lot's holding
    period on, which moves this earlier than `acquired`."""
    acquired: date
    """The purchase or reinvestment date; the wash-sale window is measured from it."""
    shares: float
    basis: float
    """Total dollars: notional plus trading cost, plus any disallowed loss attached."""
    source: str
    closed: date | None = None
    replacement_capacity: float = 0.0
    """Shares of this lot not yet used as replacement shares in a wash sale."""
    disallowed_attached: float = 0.0

    @property
    def basis_per_share(self) -> float:
        return self.basis / self.shares if self.shares > 0.0 else 0.0


@dataclass(frozen=True, slots=True)
class Realized:
    symbol: str
    lot_id: int
    opened: date
    sold: date
    shares: float
    proceeds: float
    basis: float
    disallowed: float = 0.0

    @property
    def gain(self) -> float:
        # A disallowed wash-sale loss is not recognised now: it moved into the
        # replacement lot's basis and will be recognised when that lot is sold.
        return self.proceeds - self.basis + self.disallowed


class LotBook:
    """Open lots per symbol, sold by a declared method."""

    def __init__(self, method: str) -> None:
        if method not in LOT_METHODS:
            raise ValueError(f"lot method must be one of {', '.join(LOT_METHODS)}, got {method!r}")
        self.method = method
        self.lots: dict[int, Lot] = {}
        self._open: dict[str, list[Lot]] = {}
        self._next_id = 1

    def open_lots(self, symbol: str) -> tuple[Lot, ...]:
        return tuple(self._open.get(symbol, ()))

    def shares_held(self, symbol: str) -> float:
        return sum(lot.shares for lot in self._open.get(symbol, ()))

    def buy(
        self,
        symbol: str,
        day: date,
        shares: float,
        basis: float,
        *,
        source: str = "buy",
        opened: date | None = None,
        extra_basis: float = 0.0,
        replacement_capacity: float | None = None,
    ) -> Lot:
        """Open a lot. `extra_basis` and `opened` carry a wash sale's disallowed
        loss and tacked holding period into a purchase made after the loss sale."""

        if shares <= 0.0:
            raise ValueError(f"a lot needs positive shares, got {shares!r} for {symbol} on {day}")
        if basis < 0.0 or extra_basis < 0.0:
            raise ValueError(f"a lot's basis cannot be negative ({basis!r}) for {symbol} on {day}")
        lot = Lot(
            lot_id=self._next_id,
            symbol=symbol,
            opened=opened or day,
            acquired=day,
            shares=shares,
            basis=basis + extra_basis,
            source=source,
            replacement_capacity=shares if replacement_capacity is None else replacement_capacity,
            disallowed_attached=extra_basis,
        )
        self._next_id += 1
        self.lots[lot.lot_id] = lot
        self._open.setdefault(symbol, []).append(lot)
        return lot

    def sell(self, symbol: str, day: date, shares: float, proceeds: float) -> list[Realized]:
        """Close `shares` of `symbol` by the book's method; proceeds are split pro rata."""

        open_lots = self._open.get(symbol, [])
        held = sum(lot.shares for lot in open_lots)
        if shares > held + _SHARE_TOLERANCE:
            raise ValueError(
                f"selling {shares} {symbol} shares on {day} but only {held} are held; "
                "the engine cannot produce this, so the inputs are inconsistent"
            )
        shares = min(shares, held)
        if self.method == "hifo":
            order = sorted(open_lots, key=lambda lot: (-lot.basis_per_share, lot.lot_id))
        else:
            order = sorted(open_lots, key=lambda lot: (lot.opened, lot.lot_id))

        records: list[Realized] = []
        remaining = shares
        for lot in order:
            if remaining <= _SHARE_TOLERANCE:
                break
            take = min(lot.shares, remaining)
            fraction = take / lot.shares
            lot_basis = lot.basis * fraction
            lot_proceeds = proceeds * (take / shares) if shares > 0.0 else 0.0
            records.append(
                Realized(symbol, lot.lot_id, lot.opened, day, take, lot_proceeds, lot_basis)
            )
            lot.shares -= take
            lot.basis -= lot_basis
            remaining -= take
            if lot.shares <= _SHARE_TOLERANCE:
                lot.shares = 0.0
                lot.basis = 0.0
                lot.closed = day
                open_lots.remove(lot)
            # Shares just sold cannot serve as replacement shares for a wash sale.
            lot.replacement_capacity = min(lot.replacement_capacity, lot.shares)
        return records
```

(`replace` and `timedelta` are imported now because Tasks 3 and 4 use them in this module.)

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_tax_lots.py -q`
Expected: `13 passed`.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `369 passed, 3 subtests passed`.

```bash
git add src/boring_alpha/tax/lots.py tests/test_tax_lots.py
git commit -m "Keep tax lots in real shares and sell them by a declared method

Engine units convert to real shares through the adjusted-over-unadjusted
close ratio; lots carry unadjusted-dollar basis, an acquisition date for
the wash-sale window and a holding-period start that a wash sale may tack
earlier. Sales close lots highest-basis-first or first-in-first-out, split
proceeds pro rata and leave a closed date behind.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Distributions open their own lots

**Files:**
- Modify: `src/boring_alpha/tax/lots.py` (add `Distribution`; add `extra_realized` to `LotBook.__init__`; add `LotBook.distribute`)
- Test: `tests/test_tax_lots.py` (append)

**Interfaces:**
- Consumes: `LotBook.buy`, `Lot`, `Realized` from Task 2.
- Produces: `Distribution` (frozen: `symbol, ex_date, lot_id, lot_opened, cash, return_of_capital, child_lot_id`); `LotBook.extra_realized: list[Realized]` (return of capital beyond basis, realised on the ex-date with zero shares); `LotBook.distribute(symbol, ex_date, dividend_per_share, growth, *, return_of_capital) -> list[Distribution]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tax_lots.py` (before the `if __name__` block):

```python
class DistributionTests(unittest.TestCase):
    """Adjusted close 99 throughout; unadjusted 100, then 99 after a 1.00 dividend on D1.
    The factor A/P is 0.99 before the ex-date and 1.0 after, so growth is 1/0.99."""

    def setUp(self) -> None:
        self.data = _market({"A": [99.0, 99.0, 99.0, 99.0]})
        self.table = _table({"A": [100.0, 99.0, 99.0, 99.0]}, {"A": [0.0, 1.0, 0.0, 0.0]})
        before = adjustment_factor(self.data, self.table, D0, "A")
        after = adjustment_factor(self.data, self.table, D1, "A")
        self.growth = after / before

    def _buy_ten_units(self, book: LotBook):
        # Ten engine units bought on D0 for 990 are 9.9 real shares at 100.
        shares = 10.0 * adjustment_factor(self.data, self.table, D0, "A")
        return book.buy("A", D0, shares, 990.0)

    def test_income_opens_a_child_lot_and_leaves_the_parent_basis_alone(self) -> None:
        book = LotBook("fifo")
        parent = self._buy_ten_units(book)
        events = book.distribute("A", D1, 1.0, self.growth, return_of_capital=False)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertAlmostEqual(event.cash, 9.9)
        self.assertFalse(event.return_of_capital)
        self.assertEqual((event.lot_id, event.lot_opened, event.ex_date), (parent.lot_id, D0, D1))
        child = book.lots[event.child_lot_id]
        self.assertAlmostEqual(child.shares, 0.1)
        self.assertAlmostEqual(child.basis, 9.9)
        self.assertEqual((child.opened, child.acquired, child.source), (D1, D1, "reinvest"))
        self.assertAlmostEqual(parent.basis, 990.0)
        # Real shares now equal the engine's ten units at the post-dividend factor.
        self.assertAlmostEqual(
            book.shares_held("A"), 10.0 * adjustment_factor(self.data, self.table, D1, "A")
        )
        # The reinvestment price the data implies is the unadjusted close.
        self.assertAlmostEqual(event.cash / child.shares, 99.0)

    def test_income_plus_gain_equals_the_adjusted_profit(self) -> None:
        book = LotBook("fifo")
        self._buy_ten_units(book)
        events = book.distribute("A", D1, 1.0, self.growth, return_of_capital=False)
        # Sold on D3: ten engine units at 99 are 990, the same as ten real shares at 99.
        records = book.sell("A", D3, book.shares_held("A"), 990.0)
        income = sum(event.cash for event in events)
        gains = sum(record.gain for record in records)
        self.assertAlmostEqual(income, 9.9)
        self.assertAlmostEqual(gains, -9.9)
        self.assertAlmostEqual(income + gains, 990.0 - 990.0, places=9)

    def test_return_of_capital_reduces_the_parent_and_is_not_income(self) -> None:
        book = LotBook("fifo")
        parent = self._buy_ten_units(book)
        events = book.distribute("A", D1, 1.0, self.growth, return_of_capital=True)
        self.assertTrue(events[0].return_of_capital)
        self.assertAlmostEqual(parent.basis, 980.1)
        self.assertAlmostEqual(book.lots[events[0].child_lot_id].basis, 9.9)
        self.assertAlmostEqual(sum(lot.basis for lot in book.open_lots("A")), 990.0)
        records = book.sell("A", D3, book.shares_held("A"), 990.0)
        self.assertAlmostEqual(sum(record.gain for record in records), 0.0, places=9)
        self.assertEqual(book.extra_realized, [])

    def test_return_of_capital_beyond_basis_is_a_gain_on_the_ex_date(self) -> None:
        book = LotBook("fifo")
        shares = 10.0 * adjustment_factor(self.data, self.table, D0, "A")
        lot = book.buy("A", D0, shares, 5.0)   # an implausibly low basis, to force the excess
        book.distribute("A", D1, 1.0, self.growth, return_of_capital=True)
        self.assertAlmostEqual(lot.basis, 0.0)
        self.assertEqual(len(book.extra_realized), 1)
        excess = book.extra_realized[0]
        self.assertAlmostEqual(excess.gain, 4.9)
        self.assertEqual((excess.shares, excess.sold, excess.opened), (0.0, D1, D0))

    def test_a_lot_bought_on_the_ex_date_receives_nothing(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D1, 10.0, 990.0)
        self.assertEqual(book.distribute("A", D1, 1.0, self.growth, return_of_capital=False), [])
        self.assertEqual(len(book.lots), 1)

    def test_child_lots_do_not_receive_the_distribution_that_created_them(self) -> None:
        book = LotBook("fifo")
        self._buy_ten_units(book)
        events = book.distribute("A", D1, 1.0, self.growth, return_of_capital=False)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(book.lots), 2)

    def test_no_growth_means_no_child_lot_but_the_cash_is_still_recorded(self) -> None:
        book = LotBook("fifo")
        self._buy_ten_units(book)
        events = book.distribute("A", D1, 1.0, 1.0, return_of_capital=False)
        self.assertIsNone(events[0].child_lot_id)
        self.assertAlmostEqual(events[0].cash, 9.9)

    def test_a_negative_dividend_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "dividend"):
            LotBook("fifo").distribute("A", D1, -1.0, 1.0, return_of_capital=False)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_tax_lots.py -q -k Distribution`
Expected: FAIL — `AttributeError: 'LotBook' object has no attribute 'distribute'`.

- [ ] **Step 3: Implement**

In `src/boring_alpha/tax/lots.py`, add after `Realized`:

```python
@dataclass(frozen=True, slots=True)
class Distribution:
    """One lot's share of a distribution on an ex-date (spec §4.3)."""

    symbol: str
    ex_date: date
    lot_id: int
    lot_opened: date
    cash: float
    return_of_capital: bool
    child_lot_id: int | None
```

In `LotBook.__init__`, after `self._next_id = 1`, add:

```python
        self.extra_realized: list[Realized] = []
        """Return of capital beyond a lot's basis, realised as gain on the ex-date."""
```

Add this method to `LotBook` after `sell`:

```python
    def distribute(
        self,
        symbol: str,
        ex_date: date,
        dividend_per_share: float,
        growth: float,
        *,
        return_of_capital: bool,
    ) -> list[Distribution]:
        """Pay `dividend_per_share` to every lot held into `ex_date`, reinvesting it.

        `growth` is the reinvestment factor the adjusted series implies,
        F(ex_date) / F(previous session): the child lot's shares are the parent's
        times (growth − 1) and its basis is the cash, so real shares keep
        matching engine units exactly. An income distribution leaves the parent's
        basis alone and is taxed; a return of capital reduces the parent's basis
        by the cash instead, and any excess over that basis is a capital gain
        realised on the ex-date. Lots acquired on or after the ex-date, including
        the child lots this call opens, receive nothing.
        """

        if dividend_per_share < 0.0:
            raise ValueError(f"negative dividend {dividend_per_share!r} for {symbol} on {ex_date}")
        events: list[Distribution] = []
        for lot in list(self._open.get(symbol, ())):
            if lot.acquired >= ex_date:
                continue
            cash = lot.shares * dividend_per_share
            if cash <= 0.0:
                continue
            child: Lot | None = None
            if growth > 1.0:
                child = self.buy(symbol, ex_date, lot.shares * (growth - 1.0), cash, source="reinvest")
            if return_of_capital:
                reduction = min(cash, lot.basis)
                lot.basis -= reduction
                excess = cash - reduction
                if excess > 0.0:
                    self.extra_realized.append(
                        Realized(symbol, lot.lot_id, lot.opened, ex_date, 0.0, excess, 0.0)
                    )
            events.append(
                Distribution(
                    symbol, ex_date, lot.lot_id, lot.opened, cash, return_of_capital,
                    child.lot_id if child is not None else None,
                )
            )
        return events
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_tax_lots.py -q`
Expected: `21 passed`.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `377 passed, 3 subtests passed`.

```bash
git add src/boring_alpha/tax/lots.py tests/test_tax_lots.py
git commit -m "Let each distribution open a child lot from the data-implied reinvestment

Every lot held into an ex-date receives its cash and a child lot whose
shares come from the growth the adjusted series implies, so real shares
keep matching engine units and income plus gain equals the adjusted
profit. Income leaves the parent's basis alone; return of capital reduces
it, with any excess realised as gain on the ex-date.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Wash sales

**Files:**
- Modify: `src/boring_alpha/tax/lots.py` (add `WASH_SALE_WINDOW`, `FuturePurchase`, `apply_wash_sales`)
- Test: `tests/test_tax_lots.py` (append)

**Interfaces:**
- Consumes: `Lot`, `Realized`, `LotBook` from Tasks 2 and 3.
- Produces: `WASH_SALE_WINDOW = timedelta(days=30)`; `FuturePurchase(symbol, acquired, shares, replacement_capacity, pending_basis=0.0, pending_tack_days=0)`; `apply_wash_sales(records: list[Realized], existing: Sequence[Lot], future: Sequence[FuturePurchase]) -> list[Realized]`. Task 6 calls this after every sale and applies a `FuturePurchase`'s pending fields when its buy is opened.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tax_lots.py` (before the `if __name__` block), and add `from datetime import timedelta` and `from boring_alpha.tax.lots import FuturePurchase, apply_wash_sales` to the imports at the top of the file:

```python
class WashSaleTests(unittest.TestCase):
    """A 10-share lot bought at 1000 on D0 and sold on 2024-02-01 for 900: a 100 loss."""

    SOLD = date(2024, 2, 1)

    def _loss(self) -> tuple[LotBook, list[Realized]]:
        book = LotBook("fifo")
        book.buy("A", D0, 10.0, 1000.0)
        return book, book.sell("A", self.SOLD, 10.0, 900.0)

    def test_a_purchase_thirty_days_later_disallows_the_whole_loss(self) -> None:
        book, records = self._loss()
        future = FuturePurchase("A", self.SOLD + timedelta(days=30), 10.0, 10.0)
        adjusted = apply_wash_sales(records, book.open_lots("A"), [future])
        self.assertAlmostEqual(adjusted[0].disallowed, 100.0)
        self.assertAlmostEqual(adjusted[0].gain, 0.0)
        self.assertAlmostEqual(future.pending_basis, 100.0)
        self.assertEqual(future.pending_tack_days, (self.SOLD - D0).days)
        self.assertAlmostEqual(future.replacement_capacity, 0.0)

    def test_thirty_one_days_later_is_outside_the_window(self) -> None:
        book, records = self._loss()
        future = FuturePurchase("A", self.SOLD + timedelta(days=31), 10.0, 10.0)
        adjusted = apply_wash_sales(records, book.open_lots("A"), [future])
        self.assertAlmostEqual(adjusted[0].disallowed, 0.0)
        self.assertAlmostEqual(future.pending_basis, 0.0)

    def test_partial_replacement_disallows_a_proportional_share(self) -> None:
        book, records = self._loss()
        future = FuturePurchase("A", self.SOLD + timedelta(days=10), 4.0, 4.0)
        adjusted = apply_wash_sales(records, book.open_lots("A"), [future])
        self.assertAlmostEqual(adjusted[0].disallowed, 40.0)
        self.assertAlmostEqual(adjusted[0].gain, -60.0)
        self.assertAlmostEqual(future.pending_basis, 40.0)

    def test_an_existing_lot_is_adjusted_immediately(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D0, 10.0, 1000.0)                                 # lot 1, sold at a loss
        replacement = book.buy("A", date(2024, 1, 20), 10.0, 950.0)     # lot 2, inside the window
        records = book.sell("A", self.SOLD, 10.0, 900.0)                # fifo sells lot 1
        self.assertEqual(records[0].lot_id, 1)
        adjusted = apply_wash_sales(records, book.open_lots("A"), [])
        self.assertAlmostEqual(adjusted[0].disallowed, 100.0)
        self.assertAlmostEqual(replacement.basis, 1050.0)
        self.assertAlmostEqual(replacement.disallowed_attached, 100.0)
        self.assertEqual(
            replacement.opened, date(2024, 1, 20) - timedelta(days=(self.SOLD - D0).days)
        )
        self.assertEqual(replacement.acquired, date(2024, 1, 20))
        self.assertAlmostEqual(replacement.replacement_capacity, 0.0)

    def test_replacement_shares_are_matched_once(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D0, 10.0, 1000.0)
        book.buy("A", D1, 10.0, 1000.0)
        book.buy("A", date(2024, 1, 20), 10.0, 950.0)   # lot 3: the only replacement
        first = apply_wash_sales(book.sell("A", self.SOLD, 10.0, 900.0), book.open_lots("A"), [])
        second = apply_wash_sales(book.sell("A", self.SOLD, 10.0, 900.0), book.open_lots("A"), [])
        self.assertAlmostEqual(first[0].disallowed, 100.0)
        self.assertAlmostEqual(second[0].disallowed, 0.0)

    def test_the_shares_sold_do_not_replace_themselves(self) -> None:
        book = LotBook("fifo")
        book.buy("A", date(2024, 1, 25), 10.0, 1000.0)   # bought within 30 days of the sale
        records = book.sell("A", self.SOLD, 10.0, 900.0)  # and sold in full
        adjusted = apply_wash_sales(records, book.open_lots("A"), [])
        self.assertAlmostEqual(adjusted[0].disallowed, 0.0)

    def test_the_unsold_remainder_of_the_same_lot_does_replace(self) -> None:
        book = LotBook("fifo")
        book.buy("A", date(2024, 1, 25), 10.0, 1000.0)
        records = book.sell("A", self.SOLD, 4.0, 360.0)   # a 40 loss on four shares; six remain
        adjusted = apply_wash_sales(records, book.open_lots("A"), [])
        self.assertAlmostEqual(adjusted[0].disallowed, 40.0)
        self.assertAlmostEqual(book.lots[1].basis, 640.0)

    def test_gains_and_other_symbols_are_untouched(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D0, 10.0, 1000.0)
        other = book.buy("B", D1, 10.0, 1000.0)
        records = book.sell("A", self.SOLD, 10.0, 1100.0)
        adjusted = apply_wash_sales(records, book.open_lots("A") + book.open_lots("B"), [])
        self.assertAlmostEqual(adjusted[0].disallowed, 0.0)
        self.assertAlmostEqual(other.basis, 1000.0)
        self.assertAlmostEqual(other.replacement_capacity, 10.0)

    def test_reinvested_lots_count_as_purchases(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D0, 10.0, 1000.0)
        # A child lot of 0.1 shares opened by a distribution inside the window.
        book.distribute("A", date(2024, 1, 20), 1.0, 1.01, return_of_capital=False)
        records = book.sell("A", self.SOLD, 10.0, 900.0)   # fifo: the parent lot
        adjusted = apply_wash_sales(records, book.open_lots("A"), [])
        self.assertAlmostEqual(adjusted[0].disallowed, 100.0 * 0.1 / 10.0)

    def test_a_replacement_lot_is_tacked_once_per_call(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D0, 5.0, 500.0)
        book.buy("A", D1, 5.0, 500.0)
        replacement = book.buy("A", date(2024, 1, 20), 10.0, 950.0)
        records = book.sell("A", self.SOLD, 10.0, 900.0)   # two loss records, one replacement lot
        apply_wash_sales(records, book.open_lots("A"), [])
        self.assertEqual(
            replacement.opened, date(2024, 1, 20) - timedelta(days=(self.SOLD - D0).days)
        )
        self.assertAlmostEqual(replacement.basis, 1050.0)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_tax_lots.py -q -k WashSale`
Expected: FAIL — `ImportError: cannot import name 'FuturePurchase'`.

- [ ] **Step 3: Implement**

Append to `src/boring_alpha/tax/lots.py`:

```python
WASH_SALE_WINDOW = timedelta(days=30)


@dataclass
class FuturePurchase:
    """A buy fill dated after a loss sale, still inside the wash-sale window.

    Its lot does not exist yet, so the disallowed loss and the tacked holding
    period wait here and are applied when the lot is opened.
    """

    symbol: str
    acquired: date
    shares: float
    replacement_capacity: float
    pending_basis: float = 0.0
    pending_tack_days: int = 0


def apply_wash_sales(
    records: list[Realized],
    existing: "Sequence[Lot]",
    future: "Sequence[FuturePurchase]",
) -> list[Realized]:
    """Disallow losses matched to replacement shares (spec §4.6).

    A loss sale is a wash sale to the extent the same symbol was acquired within
    30 calendar days before or after, counting reinvested distributions as
    purchases. Replacement shares are matched once, in acquisition order. For an
    existing lot the disallowed loss is added to its basis and the sold lot's
    holding period is tacked onto its own; for a purchase still in the future
    both wait on the `FuturePurchase` until the lot is opened. Shares sold in the
    loss sale itself never replace themselves: `LotBook.sell` has already reduced
    their lot's capacity to what remains.
    """

    adjusted: list[Realized] = []
    for record in records:
        loss = record.basis - record.proceeds
        if loss <= 0.0 or record.shares <= 0.0:
            adjusted.append(record)
            continue
        low, high = record.sold - WASH_SALE_WINDOW, record.sold + WASH_SALE_WINDOW
        candidates: list[Lot | FuturePurchase] = [
            lot
            for lot in existing
            if lot.symbol == record.symbol
            and low <= lot.acquired <= high
            and lot.replacement_capacity > _SHARE_TOLERANCE
        ]
        candidates += [
            purchase
            for purchase in future
            if purchase.symbol == record.symbol
            and low <= purchase.acquired <= high
            and purchase.replacement_capacity > _SHARE_TOLERANCE
        ]
        candidates.sort(key=lambda item: item.acquired)
        holding_days = (record.sold - record.opened).days
        matched = 0.0
        tacked: set[int] = set()
        for candidate in candidates:
            if matched >= record.shares - _SHARE_TOLERANCE:
                break
            take = min(candidate.replacement_capacity, record.shares - matched)
            share_of_loss = loss * (take / record.shares)
            if isinstance(candidate, Lot):
                candidate.basis += share_of_loss
                candidate.disallowed_attached += share_of_loss
                if candidate.lot_id not in tacked:
                    candidate.opened = candidate.opened - timedelta(days=holding_days)
                    tacked.add(candidate.lot_id)
            else:
                candidate.pending_basis += share_of_loss
                candidate.pending_tack_days = max(candidate.pending_tack_days, holding_days)
            candidate.replacement_capacity -= take
            matched += take
        adjusted.append(replace(record, disallowed=loss * (matched / record.shares)))
    return adjusted
```

Add `from typing import Sequence` to the module's imports (the quoted annotations above then resolve).

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_tax_lots.py -q`
Expected: `31 passed`.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `387 passed, 3 subtests passed`.

```bash
git add src/boring_alpha/tax/lots.py tests/test_tax_lots.py
git commit -m "Adjust wash sales rather than count them

A loss sale is disallowed to the extent the same symbol was acquired
within thirty days either side, counting reinvested distributions. The
disallowed loss moves into the replacement lot's basis and the sold lot's
holding period is tacked on; purchases still in the future carry both
until their lot is opened. Replacement shares are matched once and the
shares sold never replace themselves.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Year-end arithmetic — character, netting, carryovers, the tax bill

**Files:**
- Create: `src/boring_alpha/tax/yearend.py`
- Test: `tests/test_tax_yearend.py`

**Interfaces:**
- Consumes: `TaxConfig` rates.
- Produces: `is_long_term(opened, sold) -> bool`; `qualifies(opened, closed, ex_date) -> bool`; `Amounts` (mutable dataclass, fields `qualified_income, ordinary_income, cash_interest, short_gains, short_losses, long_gains, long_losses, collectibles_gains, collectibles_losses, marks_long, marks_short, return_of_capital, wash_disallowed`, methods `scaled(factor) -> Amounts`, `add_gain(amount, *, long_term, gains_class, mark_to_market)`, `as_dict()`); `YearTax` (frozen: `tax, income_tax, gains_tax, short_net, long_net, collectibles_net, short_carry_used, long_carry_used, short_carry_out, long_carry_out`); `net_and_tax(amounts, short_carry, long_carry, tax) -> YearTax`. Task 6 fills `Amounts` per year and calls `net_and_tax`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tax_yearend.py`:

```python
"""Character, netting and carryovers follow the rules the spec states (§4.5, §4.7)."""

from datetime import date
from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import load_tax_policy
from boring_alpha.tax.yearend import Amounts, is_long_term, net_and_tax, qualifies

POLICY = """
[tax]
distributions_path = "distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.5
[tax.qualified_fraction]
A = 1.0
[tax.gains_class]
A = "standard"
"""


def _policy():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "policy.toml"
        path.write_text(POLICY, encoding="utf-8")
        return load_tax_policy(path, ("A",))


class HoldingPeriodTests(unittest.TestCase):
    def test_more_than_365_days_is_long_term(self) -> None:
        opened = date(2023, 3, 1)
        self.assertFalse(is_long_term(opened, date(2024, 2, 29)))   # 365 days
        self.assertTrue(is_long_term(opened, date(2024, 3, 1)))     # 366 days

    def test_qualified_needs_more_than_sixty_days_inside_the_window(self) -> None:
        ex_date = date(2024, 6, 14)
        opened = date(2024, 5, 15)
        self.assertTrue(qualifies(opened, date(2024, 7, 15), ex_date))    # 61 days held in window
        self.assertFalse(qualifies(opened, date(2024, 7, 14), ex_date))   # 60 days

    def test_days_outside_the_window_do_not_count(self) -> None:
        ex_date = date(2024, 6, 14)
        # Held for years before, sold the day after the ex-date: only 61 window days.
        self.assertTrue(qualifies(date(2020, 1, 1), date(2024, 6, 15), ex_date))
        self.assertFalse(qualifies(date(2020, 1, 1), date(2024, 6, 14), ex_date))

    def test_the_window_may_cross_a_year_end(self) -> None:
        ex_date = date(2024, 12, 20)
        self.assertTrue(qualifies(date(2024, 11, 1), date(2025, 2, 28), ex_date))
        self.assertFalse(qualifies(date(2024, 12, 1), date(2025, 1, 15), ex_date))


class AmountsTests(unittest.TestCase):
    def test_scaled_multiplies_every_field(self) -> None:
        amounts = Amounts(qualified_income=10.0, short_gains=20.0, marks_long=6.0, wash_disallowed=1.0)
        scaled = amounts.scaled(2.0)
        self.assertAlmostEqual(scaled.qualified_income, 20.0)
        self.assertAlmostEqual(scaled.short_gains, 40.0)
        self.assertAlmostEqual(scaled.marks_long, 12.0)
        self.assertAlmostEqual(scaled.wash_disallowed, 2.0)
        self.assertAlmostEqual(amounts.short_gains, 20.0)   # the original is untouched

    def test_gains_route_by_term_and_class(self) -> None:
        amounts = Amounts()
        amounts.add_gain(100.0, long_term=False, gains_class="standard", mark_to_market=False)
        amounts.add_gain(-30.0, long_term=False, gains_class="collectibles", mark_to_market=False)
        amounts.add_gain(50.0, long_term=True, gains_class="standard", mark_to_market=False)
        amounts.add_gain(-20.0, long_term=True, gains_class="standard", mark_to_market=False)
        amounts.add_gain(70.0, long_term=True, gains_class="collectibles", mark_to_market=False)
        amounts.add_gain(-10.0, long_term=True, gains_class="collectibles", mark_to_market=False)
        self.assertEqual((amounts.short_gains, amounts.short_losses), (100.0, 30.0))
        self.assertEqual((amounts.long_gains, amounts.long_losses), (50.0, 20.0))
        self.assertEqual((amounts.collectibles_gains, amounts.collectibles_losses), (70.0, 10.0))

    def test_mark_to_market_splits_sixty_forty_regardless_of_term(self) -> None:
        amounts = Amounts()
        amounts.add_gain(100.0, long_term=False, gains_class="commodity_pool", mark_to_market=True)
        amounts.add_gain(-50.0, long_term=True, gains_class="commodity_pool", mark_to_market=True)
        self.assertAlmostEqual(amounts.marks_long, 30.0)
        self.assertAlmostEqual(amounts.marks_short, 20.0)
        self.assertEqual(amounts.short_gains, 0.0)

    def test_as_dict_lists_every_field(self) -> None:
        record = Amounts(cash_interest=3.0).as_dict()
        self.assertEqual(record["cash_interest"], 3.0)
        self.assertEqual(len(record), 13)


class NettingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tax = _policy()

    def test_a_short_gain_is_taxed_at_the_ordinary_rate(self) -> None:
        year = net_and_tax(Amounts(short_gains=100.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 35.0)
        self.assertAlmostEqual(year.short_carry_out, 0.0)

    def test_a_short_loss_offsets_a_long_gain_and_the_rest_carries_as_short(self) -> None:
        year = net_and_tax(Amounts(short_losses=100.0, long_gains=50.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 0.0)
        self.assertAlmostEqual(year.long_net, 0.0)
        self.assertAlmostEqual(year.short_carry_out, 50.0)
        self.assertAlmostEqual(year.long_carry_out, 0.0)

    def test_a_short_carryover_reduces_a_short_gain(self) -> None:
        year = net_and_tax(Amounts(short_gains=100.0), 30.0, 0.0, self.tax)
        self.assertAlmostEqual(year.short_carry_used, 30.0)
        self.assertAlmostEqual(year.tax, 70.0 * 0.35)
        self.assertAlmostEqual(year.short_carry_out, 0.0)

    def test_a_long_carryover_offsets_collectibles_first(self) -> None:
        year = net_and_tax(Amounts(collectibles_gains=30.0, long_gains=50.0), 0.0, 40.0, self.tax)
        self.assertAlmostEqual(year.collectibles_net, 0.0)
        self.assertAlmostEqual(year.long_net, 40.0)
        self.assertAlmostEqual(year.long_carry_used, 40.0)
        self.assertAlmostEqual(year.tax, 40.0 * 0.20)

    def test_a_long_loss_offsets_a_short_gain(self) -> None:
        year = net_and_tax(Amounts(short_gains=100.0, long_losses=30.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 70.0 * 0.35)
        self.assertAlmostEqual(year.long_carry_out, 0.0)

    def test_long_losses_net_against_collectibles_gains_before_anything_else(self) -> None:
        year = net_and_tax(Amounts(collectibles_gains=100.0, long_losses=40.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.collectibles_net, 60.0)
        self.assertAlmostEqual(year.tax, 60.0 * 0.28)

    def test_an_unused_long_loss_carries_with_its_character(self) -> None:
        year = net_and_tax(Amounts(long_losses=100.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 0.0)
        self.assertAlmostEqual(year.long_carry_out, 100.0)
        self.assertAlmostEqual(year.short_carry_out, 0.0)

    def test_carryovers_not_needed_this_year_survive(self) -> None:
        year = net_and_tax(Amounts(), 25.0, 15.0, self.tax)
        self.assertAlmostEqual(year.short_carry_out, 25.0)
        self.assertAlmostEqual(year.long_carry_out, 15.0)

    def test_income_is_taxed_by_character_and_interest_as_ordinary(self) -> None:
        amounts = Amounts(qualified_income=100.0, ordinary_income=50.0, cash_interest=20.0)
        year = net_and_tax(amounts, 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.income_tax, 100.0 * 0.20 + 70.0 * 0.35)
        self.assertAlmostEqual(year.gains_tax, 0.0)
        self.assertAlmostEqual(year.tax, year.income_tax)

    def test_marks_enter_their_pools(self) -> None:
        year = net_and_tax(Amounts(marks_long=60.0, marks_short=40.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 60.0 * 0.20 + 40.0 * 0.35)

    def test_income_is_never_offset_by_capital_losses(self) -> None:
        year = net_and_tax(Amounts(ordinary_income=100.0, short_losses=500.0), 0.0, 0.0, self.tax)
        self.assertAlmostEqual(year.tax, 35.0)
        self.assertAlmostEqual(year.short_carry_out, 500.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_tax_yearend.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'boring_alpha.tax.yearend'`.

- [ ] **Step 3: Implement**

Create `src/boring_alpha/tax/yearend.py`:

```python
"""Year-end tax arithmetic (spec §4.5, §4.7): character, netting, carryovers, the bill.

Everything here is a pure function of amounts already expressed in the dollars
they will be taxed in. The overlay scales raw amounts by the after-tax NAV
factor before calling `net_and_tax`, and carries the returned loss pools into
the next year.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, timedelta

from boring_alpha.config import TaxConfig

LONG_TERM_DAYS = 365
QUALIFIED_WINDOW = timedelta(days=60)
QUALIFIED_MIN_DAYS = 60
MARK_LONG_SHARE = 0.6


def is_long_term(opened: date, sold: date) -> bool:
    """"More than one year", approximated as more than 365 days."""

    return (sold - opened).days > LONG_TERM_DAYS


def qualifies(opened: date, closed: date, ex_date: date) -> bool:
    """Held more than 60 days within the 121-day window beginning 60 days before the ex-date."""

    start = max(opened, ex_date - QUALIFIED_WINDOW)
    end = min(closed, ex_date + QUALIFIED_WINDOW)
    return (end - start).days > QUALIFIED_MIN_DAYS


@dataclass
class Amounts:
    """Taxable amounts of one calendar year. Losses are positive magnitudes; marks are signed."""

    qualified_income: float = 0.0
    ordinary_income: float = 0.0
    cash_interest: float = 0.0
    short_gains: float = 0.0
    short_losses: float = 0.0
    long_gains: float = 0.0
    long_losses: float = 0.0
    collectibles_gains: float = 0.0
    collectibles_losses: float = 0.0
    marks_long: float = 0.0
    marks_short: float = 0.0
    return_of_capital: float = 0.0
    wash_disallowed: float = 0.0

    def scaled(self, factor: float) -> "Amounts":
        return Amounts(**{item.name: getattr(self, item.name) * factor for item in fields(self)})

    def as_dict(self) -> dict[str, float]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    def add_gain(
        self, amount: float, *, long_term: bool, gains_class: str, mark_to_market: bool
    ) -> None:
        """Route one realised amount into its bucket.

        A mark-to-market amount is split 60/40 whatever its term, signed, as a
        Section 1256 allocation is. Otherwise short-term goes to the short pool,
        long-term collectibles to the 28% bucket, and other long-term to the
        long pool; losses are recorded as magnitudes.
        """

        if mark_to_market:
            self.marks_long += MARK_LONG_SHARE * amount
            self.marks_short += (1.0 - MARK_LONG_SHARE) * amount
            return
        if not long_term:
            if amount >= 0.0:
                self.short_gains += amount
            else:
                self.short_losses -= amount
        elif gains_class == "collectibles":
            if amount >= 0.0:
                self.collectibles_gains += amount
            else:
                self.collectibles_losses -= amount
        else:
            if amount >= 0.0:
                self.long_gains += amount
            else:
                self.long_losses -= amount


@dataclass(frozen=True, slots=True)
class YearTax:
    tax: float
    income_tax: float
    gains_tax: float
    short_net: float
    long_net: float
    collectibles_net: float
    short_carry_used: float
    long_carry_used: float
    short_carry_out: float
    long_carry_out: float


def net_and_tax(amounts: Amounts, short_carry: float, long_carry: float, tax: TaxConfig) -> YearTax:
    """Net one year's gains and losses and compute its tax (spec §4.7).

    1. Carryovers keep their character. The short-term carryover offsets net
       short-term gain; the long-term carryover offsets the collectibles bucket
       first, then other long-term gain.
    2. Long-term losses net against collectibles gains, and collectibles losses
       against long-term gains, before any cross-character offset.
    3. A net short-term loss offsets remaining long-term gain, collectibles
       first; a net long-term loss offsets remaining short-term gain.
    4. Whatever stays negative carries forward in its own pool, without limit.
    Income is taxed by character and is never offset by capital losses.
    """

    short = amounts.short_gains - amounts.short_losses + amounts.marks_short
    long = amounts.long_gains - amounts.long_losses + amounts.marks_long
    coll = amounts.collectibles_gains - amounts.collectibles_losses

    short_used = min(short_carry, max(short, 0.0))
    short -= short_used
    coll_used = min(long_carry, max(coll, 0.0))
    coll -= coll_used
    long_used = min(long_carry - coll_used, max(long, 0.0))
    long -= long_used

    if long < 0.0 < coll:
        use = min(-long, coll)
        coll -= use
        long += use
    elif coll < 0.0 < long:
        use = min(-coll, long)
        long -= use
        coll += use

    if short < 0.0:
        use = min(-short, max(coll, 0.0))
        coll -= use
        short += use
        use = min(-short, max(long, 0.0))
        long -= use
        short += use
    elif short > 0.0:
        if coll < 0.0:
            use = min(-coll, short)
            coll += use
            short -= use
        if long < 0.0:
            use = min(-long, short)
            long += use
            short -= use

    short_out = short_carry - short_used + max(-short, 0.0)
    long_out = long_carry - coll_used - long_used + max(-long, 0.0) + max(-coll, 0.0)
    gains_tax = (
        max(short, 0.0) * tax.ordinary_rate
        + max(long, 0.0) * tax.long_term_rate
        + max(coll, 0.0) * tax.collectibles_rate
    )
    income_tax = (
        amounts.qualified_income * tax.long_term_rate
        + (amounts.ordinary_income + amounts.cash_interest) * tax.ordinary_rate
    )
    return YearTax(
        tax=gains_tax + income_tax,
        income_tax=income_tax,
        gains_tax=gains_tax,
        short_net=short,
        long_net=long,
        collectibles_net=coll,
        short_carry_used=short_used,
        long_carry_used=coll_used + long_used,
        short_carry_out=short_out,
        long_carry_out=long_out,
    )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_tax_yearend.py -q`
Expected: `20 passed`.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `407 passed, 3 subtests passed`.

```bash
git add src/boring_alpha/tax/yearend.py tests/test_tax_yearend.py
git commit -m "Net a year's gains with character-retaining carryovers and tax them

Holding period and the 61-day qualified test as the spec states them;
gains routed by term and class, with mark-to-market amounts split 60/40;
carryovers keep their character and the long-term one offsets the 28%
bucket first; income is taxed by character and never offset by losses.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: The overlay — from pre-tax artifacts to after-tax wealth under one scenario

**Files:**
- Create: `src/boring_alpha/tax/overlay.py`
- Modify: `src/boring_alpha/tax/__init__.py` (export `apply_overlay`, `run_scenarios`)
- Test: `tests/test_tax_overlay.py`

**Interfaces:**
- Consumes: `LotBook`, `FuturePurchase`, `apply_wash_sales`, `adjustment_factor`, `WASH_SALE_WINDOW` (Tasks 2–4); `Amounts`, `net_and_tax`, `is_long_term`, `qualifies` (Task 5); `Scenario`, `SCENARIOS`, `OVERLAY_VERSION`, `policy_record`, `policy_sha256`, `qualified_fraction` (Task 1); `DistributionTable`; `MarketData`; `BacktestResult`.
- Produces: `apply_overlay(result, data, table, tax, scenario, *, initial_cash, code_sha256) -> dict` (the JSON-ready result described in spec §4.10, keys `scenario, policy, by_year, totals, wealth, metrics, identity_checks`); `run_scenarios(result, data, table, tax, *, initial_cash, code_sha256) -> dict[str, dict]` keyed by scenario key. Tasks 7 and 8 call `run_scenarios`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tax_overlay.py`:

```python
"""The overlay reproduces hand-computed taxes on small constructed runs (spec §4)."""

from datetime import date
from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import load_tax_policy
from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, Fill, PriceBar
from boring_alpha.tax.overlay import apply_overlay, run_scenarios
from boring_alpha.tax.policy import SCENARIOS, Scenario

POLICY = """
[tax]
distributions_path = "distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.5
[tax.qualified_fraction]
A = 1.0
C = 0.0
[tax.gains_class]
A = "standard"
C = "commodity_pool"
"""
CODE = "c" * 64
BASE = Scenario("fifo", "deferral", "base")
LOW = Scenario("fifo", "deferral", "low")
MTM = Scenario("fifo", "mtm_60_40", "base")


def _policy():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "policy.toml"
        path.write_text(POLICY, encoding="utf-8")
        return load_tax_policy(path, ("A", "C"))


def _market(days, adjusted: dict[str, list[float]], cash_factor: float = 1.0) -> MarketData:
    bars = [
        PriceBar(day, symbol, price, price)
        for symbol, series in adjusted.items()
        for day, price in zip(days, series)
    ]
    return MarketData(bars, {day: cash_factor for day in days}, source="test")


def _table(days, unadjusted: dict[str, list[float]], dividends: dict[str, list[float]] | None = None):
    rows = []
    for symbol, series in unadjusted.items():
        paid = (dividends or {}).get(symbol, [0.0] * len(series))
        rows.extend((day, symbol, close, dividend) for day, close, dividend in zip(days, series, paid))
    return DistributionTable(rows, splits={s: [] for s in unadjusted}, sha256="d" * 64, source="test")


def _fill(day, symbol, side, quantity, price, cost=0.0) -> Fill:
    notional = quantity * price
    return Fill(day, symbol, side, quantity, price, notional, cost, notional, price)


def _result(name, curve, fills) -> BacktestResult:
    return BacktestResult(
        name=name,
        initial_equity=curve[0][1],
        equity_curve=tuple(EquityPoint(day, equity, cash, equity - cash) for day, equity, cash in curve),
        fills=tuple(fills),
        decisions=(),
    )


class BuyAndHoldWithDividendTests(unittest.TestCase):
    """Ten engine units of A bought for 990 on 2024-01-02 and held to 2025-12-31.

    Unadjusted close 100, then 99 after a 1.00 dividend on 2024-06-14, then
    110, 120, 130. Adjusted close is 99 before and equal to unadjusted after
    (factor 0.99 → 1.0). Real shares: 9.9, plus a 0.1 child lot on the ex-date.
    """

    DAYS = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 6, 14), date(2024, 12, 31),
            date(2025, 6, 30), date(2025, 12, 31)]

    def setUp(self) -> None:
        self.tax = _policy()
        self.data = _market(self.DAYS, {"A": [99.0, 99.0, 99.0, 110.0, 120.0, 130.0]})
        self.table = _table(
            self.DAYS, {"A": [100.0, 100.0, 99.0, 110.0, 120.0, 130.0]},
            {"A": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]},
        )
        curve = [
            (date(2024, 1, 2), 990.0, 0.0), (date(2024, 6, 14), 990.0, 0.0),
            (date(2024, 12, 31), 1100.0, 0.0), (date(2025, 6, 30), 1200.0, 0.0),
            (date(2025, 12, 31), 1300.0, 0.0),
        ]
        self.result = _result("hold", curve, [_fill(date(2024, 1, 2), "A", "BUY", 10.0, 99.0)])

    def _run(self, scenario=BASE) -> dict:
        return apply_overlay(
            self.result, self.data, self.table, self.tax, scenario, initial_cash=990.0, code_sha256=CODE
        )

    def test_the_dividend_is_qualified_income_taxed_in_its_year(self) -> None:
        out = self._run()
        first = out["by_year"][0]
        self.assertEqual(first["year"], 2024)
        self.assertAlmostEqual(first["qualified_income"], 9.9)
        self.assertAlmostEqual(first["ordinary_income"], 0.0)
        self.assertAlmostEqual(first["tax"], 9.9 * 0.20)
        self.assertAlmostEqual(first["scale"], 1.0)
        self.assertAlmostEqual(first["pre_tax_equity"], 1100.0)
        self.assertAlmostEqual(first["after_tax_equity"], 1100.0 - 1.98)

    def test_the_low_set_makes_half_the_dividend_ordinary(self) -> None:
        first = self._run(LOW)["by_year"][0]
        self.assertAlmostEqual(first["qualified_income"], 4.95)
        self.assertAlmostEqual(first["ordinary_income"], 4.95)
        self.assertAlmostEqual(first["tax"], 4.95 * 0.20 + 4.95 * 0.35)

    def test_the_second_year_is_rescaled_and_liquidation_is_computed_separately(self) -> None:
        out = self._run()
        second = out["by_year"][1]
        scale = 1.0 - 1.98 / 1100.0
        self.assertAlmostEqual(second["scale"], scale)
        self.assertAlmostEqual(second["tax"], 0.0)   # nothing realised in 2025 before liquidation
        self.assertAlmostEqual(out["wealth"]["pre_tax_terminal"], 1300.0)
        self.assertAlmostEqual(out["wealth"]["after_tax_pre_liquidation"], scale * 1300.0)
        # Liquidation: 9.9 shares (basis 990) and 0.1 shares (basis 9.9) sold at 130, both long-term.
        long_gain = (9.9 * 130.0 - 990.0) + (0.1 * 130.0 - 9.9)
        self.assertAlmostEqual(long_gain, 300.1)
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], long_gain * scale * 0.20)
        self.assertAlmostEqual(
            out["wealth"]["after_tax_post_liquidation"],
            scale * 1300.0 - long_gain * scale * 0.20,
        )

    def test_metrics_follow_from_the_wealth_figures(self) -> None:
        out = self._run()
        days = (date(2025, 12, 31) - date(2024, 1, 2)).days + 1
        expected_pre = (1300.0 / 990.0) ** (365.2425 / days) - 1.0
        expected_after = (out["wealth"]["after_tax_post_liquidation"] / 990.0) ** (365.2425 / days) - 1.0
        self.assertAlmostEqual(out["metrics"]["pre_tax_cagr"], expected_pre)
        self.assertAlmostEqual(out["metrics"]["after_tax_cagr"], expected_after)
        self.assertAlmostEqual(out["metrics"]["tax_drag_bps"], (expected_pre - expected_after) * 1e4)
        total_tax = out["totals"]["taxes_paid"] + out["totals"]["tax_liquidation"]
        self.assertAlmostEqual(out["metrics"]["effective_tax_rate"], total_tax / 310.0)

    def test_identities_hold_and_the_implied_price_matches_the_close(self) -> None:
        checks = self._run()["identity_checks"]
        self.assertLess(checks["share_identity_max_relative_deviation"], 1e-9)
        self.assertTrue(checks["share_identity_passed"])
        self.assertLess(checks["income_plus_gain_relative_deviation"], 1e-9)
        self.assertTrue(checks["income_plus_gain_passed"])
        self.assertEqual(checks["ex_dates_checked"], 1)
        self.assertAlmostEqual(checks["implied_reinvestment_price_ratio_min"], 1.0)
        self.assertAlmostEqual(checks["implied_reinvestment_price_ratio_max"], 1.0)
        self.assertTrue(checks["implied_price_check_passed"])

    def test_the_record_names_scenario_policy_and_provenance(self) -> None:
        out = self._run()
        self.assertEqual(out["scenario"]["key"], "fifo-deferral-base")
        self.assertEqual(out["policy"]["overlay_version"], "tax-overlay-v1")
        self.assertEqual(out["policy"]["code_sha256"], CODE)
        self.assertEqual(out["policy"]["distributions_sha256"], "d" * 64)
        self.assertEqual(len(out["policy"]["tax_policy_sha256"]), 64)
        self.assertIn("NAV convention", out["policy"]["nav_convention"])
        self.assertTrue(any("GLD" in item for item in out["totals"]["known_omissions"]))
        self.assertEqual(out["totals"]["open_lots_at_end"], 2)
        self.assertAlmostEqual(out["totals"]["unrealized_gain_at_end"], 300.1)

    def test_all_eight_scenarios_run_and_are_deterministic(self) -> None:
        first = run_scenarios(self.result, self.data, self.table, self.tax, initial_cash=990.0, code_sha256=CODE)
        second = run_scenarios(self.result, self.data, self.table, self.tax, initial_cash=990.0, code_sha256=CODE)
        self.assertEqual(list(first), [scenario.key for scenario in SCENARIOS])
        self.assertEqual(first, second)
        self.assertGreater(first["fifo-deferral-low"]["by_year"][0]["tax"], first["fifo-deferral-base"]["by_year"][0]["tax"])


class UnqualifiedHoldingTests(unittest.TestCase):
    """Bought 2024-05-20, dividend 2024-06-14, sold 2024-06-17: 28 days in the window."""

    DAYS = [date(2024, 5, 17), date(2024, 5, 20), date(2024, 6, 14), date(2024, 6, 17), date(2024, 12, 31)]

    def test_income_is_ordinary_when_the_61_day_test_fails(self) -> None:
        tax = _policy()
        data = _market(self.DAYS, {"A": [99.0, 99.0, 99.0, 99.0, 99.0]})
        table = _table(self.DAYS, {"A": [100.0, 100.0, 99.0, 99.0, 99.0]}, {"A": [0.0, 0.0, 1.0, 0.0, 0.0]})
        curve = [(date(2024, 5, 20), 990.0, 0.0), (date(2024, 6, 14), 990.0, 0.0),
                 (date(2024, 6, 17), 990.0, 990.0), (date(2024, 12, 31), 990.0, 990.0)]
        fills = [_fill(date(2024, 5, 20), "A", "BUY", 10.0, 99.0), _fill(date(2024, 6, 17), "A", "SELL", 10.0, 99.0)]
        out = apply_overlay(_result("flip", curve, fills), data, table, tax, BASE, initial_cash=990.0, code_sha256=CODE)
        year = out["by_year"][0]
        self.assertAlmostEqual(year["qualified_income"], 0.0)
        self.assertAlmostEqual(year["ordinary_income"], 9.9)
        # The parent lot lost 9.9 (proceeds 980.1 on basis 990) and the child broke even; short-term.
        self.assertAlmostEqual(year["short_losses"], 9.9)
        self.assertAlmostEqual(year["tax"], 9.9 * 0.35)
        self.assertAlmostEqual(year["short_carry_out"], 9.9)


class WashSaleThroughTheOverlayTests(unittest.TestCase):
    """Buy 10 at 100, sell at 90 a month later, buy back 10 at 90 two weeks after, hold to year end at 95."""

    DAYS = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 2, 1), date(2024, 2, 15), date(2024, 12, 31)]

    def test_the_loss_is_disallowed_and_moves_into_the_replacement_lot(self) -> None:
        tax = _policy()
        data = _market(self.DAYS, {"A": [100.0, 100.0, 90.0, 90.0, 95.0]})
        table = _table(self.DAYS, {"A": [100.0, 100.0, 90.0, 90.0, 95.0]})
        curve = [(date(2024, 1, 2), 1000.0, 0.0), (date(2024, 2, 1), 900.0, 900.0),
                 (date(2024, 2, 15), 900.0, 0.0), (date(2024, 12, 31), 950.0, 0.0)]
        fills = [
            _fill(date(2024, 1, 2), "A", "BUY", 10.0, 100.0),
            _fill(date(2024, 2, 1), "A", "SELL", 10.0, 90.0),
            _fill(date(2024, 2, 15), "A", "BUY", 10.0, 90.0),
        ]
        out = apply_overlay(_result("wash", curve, fills), data, table, tax, BASE, initial_cash=1000.0, code_sha256=CODE)
        year = out["by_year"][0]
        self.assertAlmostEqual(year["wash_disallowed"], 100.0)
        self.assertAlmostEqual(year["short_losses"], 0.0)        # the loss was not recognised
        self.assertAlmostEqual(year["tax"], 0.0)
        self.assertEqual(out["totals"]["wash_sale_count"], 1)
        self.assertAlmostEqual(out["totals"]["wash_sale_disallowed_total"], 100.0)
        # Liquidation at 95: replacement basis 900 + 100 = 1000 against proceeds 950, a 50 loss,
        # held from the tacked date 2024-01-16 to 2024-12-31: short-term.
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], 0.0)
        self.assertAlmostEqual(out["totals"]["unrealized_gain_at_end"], -50.0)
        self.assertTrue(out["identity_checks"]["income_plus_gain_passed"])


class CommodityPoolTests(unittest.TestCase):
    """Ten shares of C bought at 100 on 2024-01-02, 120 at the 2024 year end, 130 at the 2025 year end."""

    DAYS = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 12, 31), date(2025, 12, 31)]

    def setUp(self) -> None:
        self.tax = _policy()
        self.data = _market(self.DAYS, {"C": [100.0, 100.0, 120.0, 130.0]})
        self.table = _table(self.DAYS, {"C": [100.0, 100.0, 120.0, 130.0]})
        curve = [(date(2024, 1, 2), 1000.0, 0.0), (date(2024, 12, 31), 1200.0, 0.0), (date(2025, 12, 31), 1300.0, 0.0)]
        self.result = _result("pool", curve, [_fill(date(2024, 1, 2), "C", "BUY", 10.0, 100.0)])

    def test_mark_to_market_realises_each_year_sixty_forty(self) -> None:
        out = apply_overlay(self.result, self.data, self.table, self.tax, MTM, initial_cash=1000.0, code_sha256=CODE)
        first, second = out["by_year"]
        self.assertAlmostEqual(first["marks_long"], 120.0)
        self.assertAlmostEqual(first["marks_short"], 80.0)
        self.assertAlmostEqual(first["tax"], 120.0 * 0.20 + 80.0 * 0.35)
        scale = 1.0 - first["tax"] / 1200.0
        self.assertAlmostEqual(second["scale"], scale)
        self.assertAlmostEqual(second["marks_long"], 60.0 * scale)
        self.assertAlmostEqual(second["tax"], (60.0 * 0.20 + 40.0 * 0.35) * scale)
        # Basis was stepped to market at the last mark, so liquidation realises nothing more.
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], 0.0)
        self.assertAlmostEqual(out["totals"]["unrealized_gain_at_end"], 0.0)
        self.assertTrue(out["identity_checks"]["income_plus_gain_passed"])

    def test_deferral_realises_everything_at_liquidation(self) -> None:
        out = apply_overlay(self.result, self.data, self.table, self.tax, BASE, initial_cash=1000.0, code_sha256=CODE)
        self.assertAlmostEqual(out["totals"]["taxes_paid"], 0.0)
        self.assertAlmostEqual(out["wealth"]["after_tax_pre_liquidation"], 1300.0)
        # 729 days: long-term; 300 gain at 20%.
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], 60.0)
        self.assertAlmostEqual(out["wealth"]["after_tax_post_liquidation"], 1240.0)


class CashInterestTests(unittest.TestCase):
    def test_interest_on_cash_is_ordinary_income(self) -> None:
        tax = _policy()
        days = [date(2024, 1, 2), date(2024, 12, 31)]
        data = _market(days, {"A": [1.0, 1.0]}, cash_factor=1.0001)
        table = _table(days, {"A": [1.0, 1.0]})
        curve = [(date(2024, 1, 2), 1000.0, 1000.0), (date(2024, 12, 31), 1000.1, 1000.1)]
        out = apply_overlay(_result("cash", curve, []), data, table, tax, BASE, initial_cash=1000.0, code_sha256=CODE)
        year = out["by_year"][0]
        self.assertAlmostEqual(year["cash_interest"], 0.1)
        self.assertAlmostEqual(year["tax"], 0.1 * 0.35)
        self.assertEqual(out["totals"]["open_lots_at_end"], 0)
        self.assertTrue(out["identity_checks"]["share_identity_passed"])


class GuardTests(unittest.TestCase):
    def test_a_curve_with_fewer_than_two_points_is_refused(self) -> None:
        tax = _policy()
        days = [date(2024, 1, 2)]
        with self.assertRaisesRegex(ValueError, "two equity observations"):
            apply_overlay(
                _result("short", [(date(2024, 1, 2), 1.0, 1.0)], []),
                _market(days, {"A": [1.0]}), _table(days, {"A": [1.0]}), tax, BASE,
                initial_cash=1.0, code_sha256=CODE,
            )

    def test_a_symbol_without_a_gains_class_is_refused(self) -> None:
        tax = _policy()
        days = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 12, 31)]
        data = _market(days, {"Z": [1.0, 1.0, 1.0]})
        table = _table(days, {"Z": [1.0, 1.0, 1.0]})
        curve = [(date(2024, 1, 2), 10.0, 0.0), (date(2024, 12, 31), 10.0, 0.0)]
        with self.assertRaisesRegex(ValueError, "no gains class"):
            apply_overlay(_result("z", curve, [_fill(date(2024, 1, 2), "Z", "BUY", 10.0, 1.0)]),
                          data, table, tax, BASE, initial_cash=10.0, code_sha256=CODE)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_tax_overlay.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'boring_alpha.tax.overlay'`.

- [ ] **Step 3: Implement**

Create `src/boring_alpha/tax/overlay.py`:

```python
"""The after-tax overlay (spec §4): pre-tax artifacts in, after-tax wealth out.

A pure function of a run's fills and equity curve, the market data it ran on,
the distributions table, a tax policy and one scenario. It never touches the
engine. Phase A replays the run chronologically in real shares: distributions
open child lots, sales close lots by the scenario's method, wash sales are
applied as they happen, commodity pools are marked at year ends when the
scenario says so. Phase B taxes each calendar year under the after-tax NAV
convention (spec §4.8): raw amounts are scaled by the cumulative factor, taxed,
and the factor is reduced by the tax paid over that year-end equity.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import math

from boring_alpha.config import TaxConfig
from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, Fill
from boring_alpha.tax.lots import (
    WASH_SALE_WINDOW,
    Distribution,
    FuturePurchase,
    LotBook,
    Realized,
    adjustment_factor,
    apply_wash_sales,
)
from boring_alpha.tax.policy import (
    OVERLAY_VERSION,
    SCENARIOS,
    Scenario,
    policy_record,
    policy_sha256,
    qualified_fraction,
)
from boring_alpha.tax.yearend import Amounts, is_long_term, net_and_tax, qualifies

NAV_CONVENTION = (
    "after-tax NAV convention (spec §4.8): the pre-tax path is rescaled at each "
    "year end by the tax paid over that year-end equity. Raising the cash to pay, "
    "its trading cost, the gain realised doing so, and exposure drift until the "
    "next rebalance are not modelled; both accounts hold enough cash that these "
    "are second order."
)
KNOWN_OMISSIONS = (
    "GLD expense sales: the trust sells gold to pay its expense ratio and holders "
    "recognise their share with a basis adjustment; not modelled, bounded near one "
    "hundredth of one percent of portfolio return a year (spec §4.6).",
    "State tax, the 3.8% net investment income tax and historical rate changes are "
    "ignored; rates are a fixed federal-only scenario (spec §4.9).",
    "Commodity-pool interest income is not separated from futures gains under the "
    "mark-to-market treatment (spec §4.5).",
    "Reinvested distributions inherit no wash-sale role once a later loss sale's "
    "window opens after them; only purchases known at sale time are matched.",
)
SHARE_IDENTITY_TOLERANCE = 1e-6
PNL_IDENTITY_TOLERANCE = 1e-6
IMPLIED_PRICE_TOLERANCE = 0.05
DAYS_PER_YEAR = 365.2425


def _cagr(terminal: float, initial: float, days: int) -> float:
    return (terminal / initial) ** (DAYS_PER_YEAR / days) - 1.0


def apply_overlay(
    result: BacktestResult,
    data: MarketData,
    table: DistributionTable,
    tax: TaxConfig,
    scenario: Scenario,
    *,
    initial_cash: float,
    code_sha256: str,
) -> dict:
    curve = result.equity_curve
    if len(curve) < 2:
        raise ValueError("at least two equity observations are required")
    if initial_cash <= 0.0:
        raise ValueError("initial cash must be positive")
    sessions = [point.date for point in curve]
    first, last = sessions[0], sessions[-1]
    symbols = sorted({fill.symbol for fill in result.fills})
    for symbol in symbols:
        if symbol not in tax.gains_class:
            raise ValueError(f"the tax policy names no gains class for {symbol}")
    table.require_coverage(data, tuple(symbols))
    index_of = {day: index for index, day in enumerate(data.dates)}

    def factor(day: date, symbol: str) -> float:
        return adjustment_factor(data, table, day, symbol)

    # ---- Phase A: replay the run in real shares --------------------------------
    book = LotBook(scenario.lot_method)
    fills_by_date: dict[date, list[Fill]] = defaultdict(list)
    for fill in result.fills:
        fills_by_date[fill.date].append(fill)
    future: dict[tuple[date, str], FuturePurchase] = {}
    for fill in result.fills:
        if fill.side == "BUY":
            shares = fill.quantity * factor(fill.date, fill.symbol)
            future[(fill.date, fill.symbol)] = FuturePurchase(fill.symbol, fill.date, shares, shares)

    engine_units: dict[str, float] = defaultdict(float)
    realized: list[Realized] = []
    distributions: list[Distribution] = []
    marks: list[tuple[date, str, float]] = []
    interest_by_year: dict[int, float] = defaultdict(float)
    year_end_equity: dict[int, float] = {}
    implied_ratios: list[float] = []
    share_deviation = 0.0

    for index, day in enumerate(sessions):
        point = curve[index]
        if index > 0:
            interest_by_year[day.year] += curve[index - 1].cash * (data.cash_factors[day] - 1.0)

        for symbol in symbols:
            dividend = table.dividend(day, symbol)
            if dividend <= 0.0:
                continue
            previous = index_of[day] - 1
            growth = (
                factor(day, symbol) / factor(data.dates[previous], symbol) if previous >= 0 else 1.0
            )
            implied_ratios.append(
                (dividend / (growth - 1.0)) / table.close(day, symbol) if growth > 1.0 else math.inf
            )
            return_of_capital = tax.gains_class[symbol] == "commodity_pool"
            distributions.extend(
                book.distribute(symbol, day, dividend, growth, return_of_capital=return_of_capital)
            )

        for fill in fills_by_date.get(day, ()):
            shares = fill.quantity * factor(day, fill.symbol)
            if fill.side == "SELL":
                engine_units[fill.symbol] -= fill.quantity
                records = book.sell(fill.symbol, day, shares, fill.notional - fill.cost)
                window = [
                    purchase
                    for (purchase_day, symbol), purchase in future.items()
                    if symbol == fill.symbol and day < purchase_day <= day + WASH_SALE_WINDOW
                ]
                realized.extend(apply_wash_sales(records, book.open_lots(fill.symbol), window))
            else:
                engine_units[fill.symbol] += fill.quantity
                purchase = future.pop((day, fill.symbol))
                book.buy(
                    fill.symbol,
                    day,
                    shares,
                    fill.notional + fill.cost,
                    opened=day - timedelta(days=purchase.pending_tack_days)
                    if purchase.pending_tack_days
                    else None,
                    extra_basis=purchase.pending_basis,
                    replacement_capacity=purchase.replacement_capacity,
                )

        for symbol in symbols:
            engine_value = engine_units[symbol] * data.bar(day, symbol).close
            real_value = book.shares_held(symbol) * table.close(day, symbol)
            share_deviation = max(
                share_deviation, abs(real_value - engine_value) / max(abs(engine_value), 1.0)
            )

        year_end = index == len(sessions) - 1 or sessions[index + 1].year != day.year
        if year_end:
            year_end_equity[day.year] = point.equity
            if scenario.commodity_treatment == "mtm_60_40":
                for symbol in symbols:
                    if tax.gains_class[symbol] != "commodity_pool":
                        continue
                    price = table.close(day, symbol)
                    for lot in book.open_lots(symbol):
                        value = lot.shares * price
                        marks.append((day, symbol, value - lot.basis))
                        lot.basis = value

    realized.extend(book.extra_realized)
    liquidation: list[Realized] = []
    unrealized = 0.0
    open_lots = 0
    for symbol in symbols:
        price = table.close(last, symbol)
        for lot in book.open_lots(symbol):
            proceeds = lot.shares * price
            liquidation.append(Realized(symbol, lot.lot_id, lot.opened, last, lot.shares, proceeds, lot.basis))
            unrealized += proceeds - lot.basis
            open_lots += 1

    # ---- Phase B: tax each calendar year under the NAV convention ---------------
    def amounts_for(year: int, *, include_liquidation: bool) -> Amounts:
        amounts = Amounts()
        for event in distributions:
            if event.ex_date.year != year:
                continue
            if event.return_of_capital:
                amounts.return_of_capital += event.cash
                continue
            lot = book.lots[event.lot_id]
            fraction = (
                qualified_fraction(tax, scenario, event.symbol)
                if qualifies(lot.opened, lot.closed or last, event.ex_date)
                else 0.0
            )
            amounts.qualified_income += event.cash * fraction
            amounts.ordinary_income += event.cash * (1.0 - fraction)
        records = [record for record in realized if record.sold.year == year]
        if include_liquidation:
            records += [record for record in liquidation if record.sold.year == year]
        for record in records:
            gains_class = tax.gains_class[record.symbol]
            mark_to_market = (
                gains_class == "commodity_pool" and scenario.commodity_treatment == "mtm_60_40"
            )
            amounts.add_gain(
                record.gain,
                long_term=is_long_term(record.opened, record.sold),
                gains_class=gains_class,
                mark_to_market=mark_to_market,
            )
            amounts.wash_disallowed += record.disallowed
        for mark_day, _, amount in marks:
            if mark_day.year == year:
                amounts.add_gain(amount, long_term=False, gains_class="commodity_pool", mark_to_market=True)
        amounts.cash_interest += interest_by_year.get(year, 0.0)
        return amounts

    years = sorted(year_end_equity)
    scale = 1.0
    short_carry = long_carry = 0.0
    by_year: list[dict] = []
    taxes_paid = 0.0
    tax_liquidation = 0.0
    for year in years:
        equity = year_end_equity[year]
        if equity <= 0.0:
            raise ValueError(f"equity at the {year} year end is not positive; the NAV convention needs it")
        amounts = amounts_for(year, include_liquidation=False).scaled(scale)
        outcome = net_and_tax(amounts, short_carry, long_carry, tax)
        if year == years[-1]:
            with_liquidation = net_and_tax(
                amounts_for(year, include_liquidation=True).scaled(scale), short_carry, long_carry, tax
            )
            tax_liquidation = with_liquidation.tax - outcome.tax
        by_year.append(
            {
                "year": year,
                **amounts.as_dict(),
                "short_carry_used": outcome.short_carry_used,
                "long_carry_used": outcome.long_carry_used,
                "short_carry_out": outcome.short_carry_out,
                "long_carry_out": outcome.long_carry_out,
                "scale": scale,
                "income_tax": outcome.income_tax,
                "gains_tax": outcome.gains_tax,
                "tax": outcome.tax,
                "pre_tax_equity": equity,
                "after_tax_equity": scale * equity - outcome.tax,
            }
        )
        taxes_paid += outcome.tax
        short_carry, long_carry = outcome.short_carry_out, outcome.long_carry_out
        scale = scale - outcome.tax / equity

    pre_tax_terminal = curve[-1].equity
    pre_liquidation = by_year[-1]["after_tax_equity"]
    post_liquidation = pre_liquidation - tax_liquidation

    # ---- Identities ---------------------------------------------------------------
    adjusted_pnl = (
        sum(fill.notional - fill.cost for fill in result.fills if fill.side == "SELL")
        - sum(fill.notional + fill.cost for fill in result.fills if fill.side == "BUY")
        + sum(record.proceeds for record in liquidation)
    )
    income_total = sum(event.cash for event in distributions if not event.return_of_capital)
    gains_total = (
        sum(record.gain for record in realized)
        + sum(record.gain for record in liquidation)
        + sum(amount for _, _, amount in marks)
    )
    pnl_deviation = abs(income_total + gains_total - adjusted_pnl) / max(abs(adjusted_pnl), initial_cash)
    finite_ratios = [ratio for ratio in implied_ratios if math.isfinite(ratio)]
    ratio_min = min(finite_ratios) if finite_ratios else None
    ratio_max = max(finite_ratios) if finite_ratios else None
    implied_ok = len(finite_ratios) == len(implied_ratios) and all(
        abs(ratio - 1.0) <= IMPLIED_PRICE_TOLERANCE for ratio in finite_ratios
    )

    days = (last - first).days + 1
    pre_tax_cagr = _cagr(pre_tax_terminal, initial_cash, days)
    after_tax_cagr = _cagr(post_liquidation, initial_cash, days) if post_liquidation > 0.0 else -1.0
    profit = pre_tax_terminal - initial_cash
    total_tax = taxes_paid + tax_liquidation

    return {
        "scenario": scenario.as_dict(),
        "policy": {
            **policy_record(tax),
            "tax_policy_sha256": policy_sha256(tax),
            "distributions_sha256": table.sha256,
            "overlay_version": OVERLAY_VERSION,
            "code_sha256": code_sha256,
            "nav_convention": NAV_CONVENTION,
        },
        "by_year": by_year,
        "totals": {
            "taxes_paid": taxes_paid,
            "tax_liquidation": tax_liquidation,
            "wash_sale_count": sum(1 for record in realized if record.disallowed > 0.0),
            "wash_sale_disallowed_total": sum(record.disallowed for record in realized),
            "return_of_capital_total": sum(
                event.cash for event in distributions if event.return_of_capital
            ),
            "unrealized_gain_at_end": unrealized,
            "open_lots_at_end": open_lots,
            "known_omissions": list(KNOWN_OMISSIONS),
        },
        "wealth": {
            "pre_tax_terminal": pre_tax_terminal,
            "after_tax_pre_liquidation": pre_liquidation,
            "after_tax_post_liquidation": post_liquidation,
        },
        "metrics": {
            "pre_tax_cagr": pre_tax_cagr,
            "after_tax_cagr": after_tax_cagr,
            "tax_drag_bps": (pre_tax_cagr - after_tax_cagr) * 10_000.0,
            "effective_tax_rate": total_tax / profit if profit > 0.0 else None,
        },
        "identity_checks": {
            "share_identity_max_relative_deviation": share_deviation,
            "share_identity_passed": share_deviation <= SHARE_IDENTITY_TOLERANCE,
            "income_plus_gain_relative_deviation": pnl_deviation,
            "income_plus_gain_passed": pnl_deviation <= PNL_IDENTITY_TOLERANCE,
            "ex_dates_checked": len(implied_ratios),
            "implied_reinvestment_price_ratio_min": ratio_min,
            "implied_reinvestment_price_ratio_max": ratio_max,
            "implied_price_check_passed": implied_ok,
        },
    }


def run_scenarios(
    result: BacktestResult,
    data: MarketData,
    table: DistributionTable,
    tax: TaxConfig,
    *,
    initial_cash: float,
    code_sha256: str,
) -> dict[str, dict]:
    """Every scenario of the fixed grid, keyed by scenario key, in grid order."""

    return {
        scenario.key: apply_overlay(
            result, data, table, tax, scenario, initial_cash=initial_cash, code_sha256=code_sha256
        )
        for scenario in SCENARIOS
    }
```

In `src/boring_alpha/tax/__init__.py`, add `from boring_alpha.tax.overlay import apply_overlay, run_scenarios` and add both names to `__all__`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_tax_overlay.py -q`
Expected: `15 passed`. If a hand-computed figure disagrees, check the arithmetic in the test's docstring first: the fixtures were computed by hand and are stated in full so a disagreement is diagnosable.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `422 passed, 3 subtests passed`.

```bash
git add src/boring_alpha/tax/overlay.py src/boring_alpha/tax/__init__.py tests/test_tax_overlay.py
git commit -m "Compute after-tax wealth from pre-tax artifacts under one scenario

The overlay replays a run in real shares — distributions open child lots,
sales close lots by method, wash sales apply as they happen, commodity
pools are marked at year ends when the scenario says so — then taxes each
calendar year under the after-tax NAV convention and computes liquidation
as the final year taxed twice. It reports the share and income-plus-gain
identities and the ratio of the data-implied reinvestment price to the
unadjusted close, which is what makes the split-adjusted-units assumption
self-checking on every ex-date.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Tax in the sweep — `tax.json`, the after-tax block, schema 6

**Files:**
- Modify: `src/boring_alpha/report.py` (`ARTIFACT_SCHEMA = 6`, `READABLE_SCHEMAS = (5, 6)`)
- Modify: `src/boring_alpha/sweep.py`
- Modify: `tests/test_slippage.py:45`, `tests/test_report.py:93`, `tests/test_gates.py:128` (schema value 5 → 6)
- Test: `tests/test_sweep.py` (append)

**Interfaces:**
- Consumes: `run_scenarios`, `policy_sha256`, `OVERLAY_VERSION` (Tasks 1, 6); `load_distributions`, `DistributionTable.through/require_coverage/sha256/splits`; `AppConfig.tax`, `AppConfig.benchmark`; `FixedAllocation`.
- Produces: `SweepResult.static_full: dict | None`, `SweepResult.tax: dict | None`, `SweepResult.distributions: DistributionTable | None`; tax run names `strategy`, `benchmark`, `exposure_matched`, `cash`, `static_full`, `variant:<name>`; `tax.json` shape `{artifact_schema, sweep_id, strategy_id, code_sha256, tax_policy_sha256, distributions_sha256, distributions_manifest, overlay_version, runs}`; manifest keys `tax_policy_sha256`, `distributions_sha256`, `distributions_manifest`; criteria keys `tax_policy_sha256`, `distributions_sha256`; archived `input_distributions.csv.gz`. Task 8 mirrors the run names.

- [ ] **Step 1: Update the schema assertions and write the failing sweep tests**

Change the literal `5` to `6` in these three assertions: `tests/test_slippage.py:45` (`self.assertEqual(ARTIFACT_SCHEMA, 6)`), `tests/test_report.py:93` (`manifest["artifact_schema"], 6`), `tests/test_gates.py:128`. Leave `tests/test_classify.py` at 5: those fixtures prove schema-5 artifacts stay classifiable.

Append to `tests/test_sweep.py` (add `import gzip` to the imports):

```python
TAX_TABLE = """
[tax]
distributions_path = "../data/distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.5
[tax.qualified_fraction]
A = 1.0
B = 1.0
C = 0.0
D = 0.0
[tax.gains_class]
A = "standard"
B = "standard"
C = "standard"
D = "commodity_pool"
"""
BENCHMARK_TABLE = '\n[benchmark]\nexposure = 0.6\nrebalance = "annual"\n'


def _write_distributions(root: Path, data: MarketData) -> None:
    """A distributions file consistent with synthetic prices: unadjusted equals
    adjusted (no dividends were ever paid), one row per priced session and symbol."""

    (root / "data").mkdir(exist_ok=True)
    lines = ["date,symbol,close,dividend"]
    for day in data.dates:
        for symbol in sorted(data.by_date[day]):
            lines.append(f"{day.isoformat()},{symbol},{data.by_date[day][symbol].close!r},0.0")
    (root / "data" / "distributions_daily.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "data" / "manifest.json").write_text(
        json.dumps({"methodology": "synthetic-test", "created_at": "2026-09-04T00:00:00+00:00",
                    "splits": {symbol: [] for symbol in ("A", "B", "C", "D")}}),
        encoding="utf-8",
    )


def _config_with(root: Path, extra: str):
    (root / "configs").mkdir()
    (root / "configs" / "evaluation_periods.toml").write_text(PERIODS, encoding="utf-8")
    path = root / "configs" / "run.toml"
    path.write_text(CONFIG + extra, encoding="utf-8")
    return load_config(path)


class TaxWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = _config_with(self.root, TAX_TABLE)
        self.data = load_market_data(self.config)
        _write_distributions(self.root, self.data)
        self.sweep = run_sweep(self.config, self.data)
        _, self.sweep_dir = write_sweep_report(self.config, self.data, self.sweep)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _tax_json(self) -> dict:
        return json.loads((self.sweep_dir / "tax.json").read_text(encoding="utf-8"))

    def test_tax_json_holds_every_run_under_every_scenario(self) -> None:
        tax = self._tax_json()
        self.assertEqual(tax["artifact_schema"], 6)
        self.assertEqual(tax["overlay_version"], "tax-overlay-v1")
        expected_runs = {"strategy", "benchmark", "exposure_matched", "cash"} | {
            f"variant:{name}" for name in GRID if name != "base"
        }
        self.assertEqual(set(tax["runs"]), expected_runs)
        for scenarios in tax["runs"].values():
            self.assertEqual(len(scenarios), 8)
            self.assertIn("hifo-deferral-base", scenarios)
            self.assertIn("after_tax_post_liquidation", scenarios["fifo-mtm_60_40-low"]["wealth"])

    def test_the_cash_run_pays_tax_only_on_interest(self) -> None:
        cash = self._tax_json()["runs"]["cash"]["hifo-deferral-base"]
        self.assertGreater(sum(year["cash_interest"] for year in cash["by_year"]), 0.0)
        self.assertEqual(cash["totals"]["open_lots_at_end"], 0)
        self.assertTrue(cash["identity_checks"]["share_identity_passed"])

    def test_identities_hold_on_the_synthetic_strategy(self) -> None:
        strategy = self._tax_json()["runs"]["strategy"]["hifo-deferral-base"]
        self.assertTrue(strategy["identity_checks"]["share_identity_passed"])
        self.assertTrue(strategy["identity_checks"]["income_plus_gain_passed"])
        self.assertEqual(strategy["identity_checks"]["ex_dates_checked"], 0)

    def test_manifest_and_criteria_carry_the_tax_identity(self) -> None:
        manifest = json.loads((self.sweep_dir / "manifest.json").read_text(encoding="utf-8"))
        criteria = json.loads((self.sweep_dir / "criteria.json").read_text(encoding="utf-8"))
        tax = self._tax_json()
        self.assertEqual(manifest["artifact_schema"], 6)
        self.assertEqual(manifest["tax_policy_sha256"], tax["tax_policy_sha256"])
        self.assertEqual(manifest["distributions_sha256"], tax["distributions_sha256"])
        self.assertEqual(manifest["distributions_manifest"]["methodology"], "synthetic-test")
        self.assertEqual(manifest["distributions_manifest"]["splits"], {s: [] for s in "ABCD"})
        self.assertEqual(criteria["tax_policy_sha256"], tax["tax_policy_sha256"])
        self.assertEqual(criteria["distributions_sha256"], tax["distributions_sha256"])

    def test_the_distributions_input_is_archived_beside_prices_and_cash(self) -> None:
        with gzip.open(self.sweep_dir / "input_distributions.csv.gz", "rt", encoding="utf-8") as handle:
            header = handle.readline().strip()
            first = handle.readline().strip()
        self.assertEqual(header, "date,symbol,close,dividend")
        self.assertTrue(first.startswith("2019-10-01,A,"))

    def test_the_summary_has_an_after_tax_block(self) -> None:
        summary = (self.sweep_dir / "summary.md").read_text(encoding="utf-8")
        self.assertIn("## After tax", summary)
        self.assertIn("| strategy |", summary)
        self.assertIn("hifo-deferral-base", summary)
        self.assertIn("NAV convention", summary)

    def test_the_after_tax_figures_enter_the_profile_extras_unchanged_for_ba_001(self) -> None:
        self.assertIsNotNone(self.sweep.tax)
        self.assertTrue(self.sweep.outcome.criteria)   # BA-001's criteria ignore extras and still evaluate


class NoTaxTests(unittest.TestCase):
    def test_without_a_tax_table_nothing_tax_related_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = _config(Path(directory))
            data = load_market_data(config)
            sweep = run_sweep(config, data)
            _, sweep_dir = write_sweep_report(config, data, sweep)
            self._check(sweep, sweep_dir)

    def _check(self, sweep, sweep_dir: Path) -> None:
        self.assertIsNone(sweep.tax)
        self.assertFalse((sweep_dir / "tax.json").exists())
        self.assertFalse((sweep_dir / "input_distributions.csv.gz").exists())
        manifest = json.loads((sweep_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("tax_policy_sha256", manifest)
        self.assertEqual(manifest["artifact_schema"], 6)
        self.assertNotIn("## After tax", (sweep_dir / "summary.md").read_text(encoding="utf-8"))


class StaticFullRowTests(unittest.TestCase):
    def test_a_target_exposure_benchmark_adds_the_full_static_secondary_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config_with(root, BENCHMARK_TABLE + TAX_TABLE)
            data = load_market_data(config)
            _write_distributions(root, data)
            sweep = run_sweep(config, data)
            _, sweep_dir = write_sweep_report(config, data, sweep)
            self.assertIsNotNone(sweep.static_full)
            self.assertGreater(float(sweep.static_full["average_gross_exposure"]), 0.9)
            self.assertLess(float(sweep.variants["base"]["static"]["average_gross_exposure"]), 0.7)
            self.assertTrue((sweep_dir / "variants" / "static_full" / "strategy_equity.csv").is_file())
            tax = json.loads((sweep_dir / "tax.json").read_text(encoding="utf-8"))
            self.assertIn("static_full", tax["runs"])
            summary = (sweep_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("| Metric | Strategy | Static | Exposure-matched | Cash |", summary)
            self.assertIn("Full static", summary)

    def test_without_a_benchmark_table_there_is_no_static_full_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = _config_with(Path(directory), "")
            sweep = run_sweep(config, load_market_data(config))
            self.assertIsNone(sweep.static_full)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_sweep.py tests/test_slippage.py tests/test_report.py tests/test_gates.py -q`
Expected: the three schema assertions fail (`5 != 6`); `TaxWiringTests` fail on `tax.json` missing; `StaticFullRowTests` fail on `static_full` attribute; `NoTaxTests` fail on `sweep.tax`.

- [ ] **Step 3: Bump the schema**

In `src/boring_alpha/report.py`, change `ARTIFACT_SCHEMA = 5` to `ARTIFACT_SCHEMA = 6` and `READABLE_SCHEMAS: tuple[int, ...] = (ARTIFACT_SCHEMA,)` to `READABLE_SCHEMAS: tuple[int, ...] = (5, ARTIFACT_SCHEMA)`, with the comment `# Schema 6 adds tax fields and removes nothing, so schema-5 sweeps stay classifiable.`

- [ ] **Step 4: Wire the sweep**

In `src/boring_alpha/sweep.py`:

Imports: add `import json`; add `from boring_alpha.data.distributions import DistributionTable, load_distributions`; change the signals import to `from boring_alpha.signals import CashAllocation, FixedAllocation, ScaledAllocation`; add `from boring_alpha.tax import OVERLAY_VERSION, policy_sha256, run_scenarios`.

Extend `SweepResult` with three trailing fields:

```python
    static_full: dict[str, float] | None = None
    """Metrics of the fully invested monthly static allocation when a
    target-exposure benchmark gates; None when full static is the benchmark."""
    tax: dict | None = None
    """Every run under every scenario, plus the policy and distributions identity;
    None when the configuration has no [tax] table."""
    distributions: DistributionTable | None = None
```

Add after `_engine`:

```python
TAX_BASE_SCENARIO = "hifo-deferral-base"


def _distributions_for(config: AppConfig, data: MarketData) -> tuple[DistributionTable, dict]:
    """The distributions table a tax run uses, truncated like the market data,
    and the manifest block that travels into the sweep so it is self-contained."""

    assert config.tax is not None
    path = config.tax.distributions_path
    manifest_path = path.parent / "manifest.json"
    if config.data.prices_path is not None and path.parent != config.data.prices_path.parent:
        raise ValueError(
            f"tax.distributions_path {path} must sit in the same snapshot directory as "
            f"data.prices_path {config.data.prices_path}: distributions and prices must "
            "come from one fetch"
        )
    if not manifest_path.is_file():
        raise ValueError(f"no manifest.json beside {path.name}; a v2 snapshot is required for tax")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    table = load_distributions(path, manifest_path=manifest_path).through(data.dates[-1])
    table.require_coverage(data, config.strategy.symbols)
    block = {
        "methodology": manifest.get("methodology"),
        "created_at": manifest.get("created_at"),
        "splits": table.splits,
        "sha256": table.sha256,
    }
    return table, block
```

In `run_sweep`, after `cash_metrics = calculate_metrics(cash, data)`, add:

```python
    static_full_result: BacktestResult | None = None
    static_full: dict[str, float] | None = None
    if config.benchmark is not None:
        # The gating benchmark is the target-exposure allocation; the fully
        # invested monthly static stays as a secondary row so the reader can
        # still see the comparison BA-001 was judged on.
        static_full_result = _engine(config, data, cost).run(
            FixedAllocation(config.strategy.symbols, lookback, config.strategy.sleeve_weight)
        )
        static_full = calculate_metrics(static_full_result, data)

    tax: dict | None = None
    table: DistributionTable | None = None
    if config.tax is not None:
        table, block = _distributions_for(config, data)
        code_hash = code_fingerprint()
        tax_runs: dict[str, BacktestResult] = {
            "strategy": base_strategy,
            "benchmark": base_static,
            "exposure_matched": matched,
            "cash": cash,
        }
        if static_full_result is not None:
            tax_runs["static_full"] = static_full_result
        for name, (strategy, _) in runs.items():
            if name != BASE:
                tax_runs[f"variant:{name}"] = strategy
        tax = {
            "tax_policy_sha256": policy_sha256(config.tax),
            "distributions_sha256": table.sha256,
            "distributions_manifest": block,
            "overlay_version": OVERLAY_VERSION,
            "runs": {
                name: run_scenarios(
                    result, data, table, config.tax,
                    initial_cash=config.portfolio.initial_cash, code_sha256=code_hash,
                )
                for name, result in tax_runs.items()
            },
        }
```

Change the `SweepResult(...)` construction: `outcome=profile.evaluate_period(variants, {"tax": tax, "static_full": static_full}),`; `runs={**runs, "exposure_matched": (matched, cash), **({"static_full": (static_full_result, cash)} if static_full_result is not None else {})},`; and add `static_full=static_full, tax=tax, distributions=table,` before the closing parenthesis.

In `_summary`, after the pre-registered metrics table loop (the `for label, key in (...)` block) and before `interval = sweep.sharpe_interval`, add:

```python
    if sweep.static_full is not None:
        lines += [
            "",
            "Full static (fully invested, rebalanced monthly), the comparison BA-001 was "
            "judged on, kept as a secondary row: "
            f"CAGR {float(sweep.static_full['cagr']):.4f}, "
            f"max drawdown {float(sweep.static_full['max_drawdown']):.4f}, "
            f"Sharpe vs cash {float(sweep.static_full['sharpe_vs_cash']):.4f}.",
        ]
```

At the end of `_summary`, before `if sweep.warnings:`, add `lines += _after_tax_lines(sweep)` and define, after `_summary`:

```python
def _after_tax_lines(sweep: SweepResult) -> list[str]:
    if sweep.tax is None:
        return []
    tax = sweep.tax
    lines = [
        "",
        "## After tax",
        "",
        f"Overlay {tax['overlay_version']}; policy {tax['tax_policy_sha256'][:12]}; "
        f"distributions {tax['distributions_sha256'][:12]}. Eight scenarios: lot method × "
        "commodity-pool treatment × qualified set. An after-tax conclusion must hold under "
        "every scenario; the worst and best are shown.",
        "",
        "| Run | Pre-tax CAGR | After-tax CAGR (worst) | Worst scenario | After-tax CAGR (best) "
        "| Tax drag, worst (bps) | Wash-sale disallowed |",
        "|---|---:|---:|---|---:|---:|---:|",
    ]
    failed_checks: list[str] = []
    for name, scenarios in tax["runs"].items():
        worst_key = min(scenarios, key=lambda key: scenarios[key]["metrics"]["after_tax_cagr"])
        best_key = max(scenarios, key=lambda key: scenarios[key]["metrics"]["after_tax_cagr"])
        worst, best, base = scenarios[worst_key], scenarios[best_key], scenarios[TAX_BASE_SCENARIO]
        lines.append(
            f"| {name} | {worst['metrics']['pre_tax_cagr']:.4f} | "
            f"{worst['metrics']['after_tax_cagr']:.4f} | {worst_key} | "
            f"{best['metrics']['after_tax_cagr']:.4f} | {worst['metrics']['tax_drag_bps']:.1f} | "
            f"{base['totals']['wash_sale_disallowed_total']:.2f} |"
        )
        checks = base["identity_checks"]
        for check in ("share_identity_passed", "income_plus_gain_passed", "implied_price_check_passed"):
            if not checks[check]:
                failed_checks.append(f"{name}: {check} is false")
    policy = next(iter(next(iter(tax["runs"].values())).values()))["policy"]
    lines += [
        "",
        f"Rates: ordinary {policy['ordinary_rate']:.0%}, long-term {policy['long_term_rate']:.0%}, "
        f"collectibles {policy['collectibles_rate']:.0%}; a federal-only stylized scenario. "
        f"{policy['nav_convention']} Drawdown is pre-tax throughout.",
    ]
    if failed_checks:
        lines += ["", "**Identity checks failed:** " + "; ".join(failed_checks) + "."]
    return lines
```

In `write_sweep_report`: in the manifest dict, after `"warnings": ...`, add:

```python
                **(
                    {
                        "tax_policy_sha256": sweep.tax["tax_policy_sha256"],
                        "distributions_sha256": sweep.tax["distributions_sha256"],
                        "distributions_manifest": sweep.tax["distributions_manifest"],
                    }
                    if sweep.tax is not None
                    else {}
                ),
```

In the criteria dict, after `"sharpe_interval": sweep.sharpe_interval,`, add:

```python
                **(
                    {
                        "tax_policy_sha256": sweep.tax["tax_policy_sha256"],
                        "distributions_sha256": sweep.tax["distributions_sha256"],
                        "static_full": sweep.static_full,
                    }
                    if sweep.tax is not None
                    else ({"static_full": sweep.static_full} if sweep.static_full is not None else {})
                ),
```

After the `write_once(sweep_dir / "summary.md", ...)` line, add:

```python
    if sweep.tax is not None:
        write_once(
            sweep_dir / "tax.json",
            json_text(
                {
                    "artifact_schema": ARTIFACT_SCHEMA,
                    "sweep_id": sweep_id,
                    "strategy_id": config.strategy.strategy_id,
                    "code_sha256": code_hash,
                    **sweep.tax,
                }
            ),
        )
```

After the two `write_once_bytes(... input_prices / input_cash ...)` lines, add:

```python
    if sweep.distributions is not None:
        write_once_bytes(
            sweep_dir / "input_distributions.csv.gz",
            _gzip_csv(_distribution_rows(sweep.distributions)),
        )
```

and define, after `_cash_rows`:

```python
def _distribution_rows(table: DistributionTable) -> list[list[str]]:
    rows = [["date", "symbol", "close", "dividend"]]
    for day in table.dates:
        for symbol in table.symbols:
            if day in table.symbol_dates.get(symbol, ()):
                rows.append([day.isoformat(), symbol, repr(table.close(day, symbol)), repr(table.dividend(day, symbol))])
    return rows
```

(`table.symbol_dates[symbol]` is a sorted tuple; membership on a tuple is linear, which is fine at this size, but use `set(table.symbol_dates.get(symbol, ()))` precomputed per symbol if the archive step proves slow on real data.)

Also update the module docstring's first paragraph to end with: `When a configuration carries a [tax] table, every run is also scored after tax under the fixed scenario grid and the result is written beside the criteria.`

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_sweep.py tests/test_slippage.py tests/test_report.py tests/test_gates.py tests/test_classify.py -q`
Expected: all pass (the schema-5 classify fixtures still classify under `READABLE_SCHEMAS = (5, 6)`).

- [ ] **Step 6: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `432 passed, 3 subtests passed`.

```bash
git add src/boring_alpha/report.py src/boring_alpha/sweep.py tests/test_sweep.py tests/test_slippage.py tests/test_report.py tests/test_gates.py
git commit -m "Score every sweep run after tax and write tax.json

When a configuration carries a [tax] table the sweep loads the
distributions from the same snapshot as prices, runs the overlay under
all eight scenarios for the strategy, the gating benchmark, full static
when a target-exposure benchmark gates, the exposure-matched allocation,
cash and every variant, and writes tax.json beside criteria.json. The
manifest and criteria carry the policy and distributions hashes, the
distributions input is archived, the summary gains an after-tax block,
and artifact schema becomes 6 with schema 5 still classifiable.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: The `aftertax` command — re-score an archived sweep

**Files:**
- Create: `src/boring_alpha/tax/reconstruct.py`
- Modify: `src/boring_alpha/cli.py` (`run_aftertax`, parser, `main`)
- Modify: `README.md` (an "After tax" section)
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `load_tax_policy`, `load_distributions`, `run_scenarios`, `policy_sha256`, `OVERLAY_VERSION`, `code_fingerprint`, `write_once`, `json_text`, `ARTIFACT_SCHEMA`, `load_csv_market_data`.
- Produces: `reconstruct.read_manifest(sweep_dir) -> dict`, `reconstruct.initial_cash_from(manifest) -> float`, `reconstruct.symbols_from(manifest) -> tuple[str, ...]`, `reconstruct.read_equity_csv(path) -> tuple[EquityPoint, ...]`, `reconstruct.read_trades_csv(path) -> tuple[Fill, ...]`, `reconstruct.reconstruct_result(name, equity_path, trades_path, initial_cash) -> BacktestResult`, `reconstruct.market_data_from_archive(sweep_dir) -> MarketData`, `reconstruct.tax_run_name(variant, role) -> str | None`, `reconstruct.run_files(sweep_dir) -> list[tuple[str, Path, Path]]`; `cli.run_aftertax(sweep_dir, policy_path, distributions_path=None) -> int`; output file `tax-<policy12>-<distributions12>-<code12>.json`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py` (add `import json`, `import gzip` and `from boring_alpha.config import load_config`, `from boring_alpha.data import load_market_data`, `from boring_alpha.sweep import run_sweep, write_sweep_report`, `from boring_alpha.report import code_fingerprint`, `from boring_alpha.metrics import calculate_metrics`, `from boring_alpha.tax.reconstruct import reconstruct_result, tax_run_name`, `from boring_alpha.cli import run_aftertax` to the imports):

```python
SWEEP_PERIODS = """
[BA-001.development]
start = 2021-01-01
end = 2022-12-31
"""

SWEEP_CONFIG = """
[strategy]
id = "BA-001"
name = "After-tax Test"
symbols = ["A", "B", "C", "D"]
lookback_months = 12
sleeve_weight = 0.25
[portfolio]
initial_cash = 10000
[execution]
cost_bps = 10
[data]
source = "synthetic"
start = "2019-10-01"
end = "2024-12-31"
seed = 21
annual_cash_rate = 0.02
[backtest]
start = "2021-01-01"
end = "2022-12-31"
[evaluation]
period = "development"
[clusters]
growth = ["A", "B"]
defensive = ["C", "D"]
[report]
output_dir = "../experiments"
"""

TAX_ONLY = """
[tax]
distributions_path = "../data/distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.5
[tax.qualified_fraction]
A = 1.0
B = 1.0
C = 0.0
D = 0.0
[tax.gains_class]
A = "standard"
B = "standard"
C = "standard"
D = "commodity_pool"
"""


class AfterTaxCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "configs").mkdir()
        (self.root / "configs" / "evaluation_periods.toml").write_text(SWEEP_PERIODS, encoding="utf-8")
        plain = self.root / "configs" / "plain.toml"
        plain.write_text(SWEEP_CONFIG, encoding="utf-8")
        taxed = self.root / "configs" / "taxed.toml"
        taxed.write_text(SWEEP_CONFIG + TAX_ONLY, encoding="utf-8")
        self.policy = self.root / "configs" / "policy.toml"
        self.policy.write_text(TAX_ONLY.replace("../data/", "../data/"), encoding="utf-8")
        self.plain_config = load_config(plain)
        self.taxed_config = load_config(taxed)
        self.data = load_market_data(self.plain_config)
        self._write_distributions()
        _, self.plain_dir = write_sweep_report(
            self.plain_config, self.data, run_sweep(self.plain_config, self.data)
        )
        _, self.taxed_dir = write_sweep_report(
            self.taxed_config, self.data, run_sweep(self.taxed_config, self.data)
        )
        self.distributions = self.root / "data" / "distributions_daily.csv"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_distributions(self) -> None:
        (self.root / "data").mkdir()
        lines = ["date,symbol,close,dividend"]
        for day in self.data.dates:
            for symbol in sorted(self.data.by_date[day]):
                lines.append(f"{day.isoformat()},{symbol},{self.data.by_date[day][symbol].close!r},0.0")
        self.distributions_text = "\n".join(lines) + "\n"
        (self.root / "data" / "distributions_daily.csv").write_text(self.distributions_text, encoding="utf-8")
        (self.root / "data" / "manifest.json").write_text(
            json.dumps({"methodology": "synthetic-test", "created_at": "2026-09-04T00:00:00+00:00",
                        "splits": {s: [] for s in "ABCD"}}),
            encoding="utf-8",
        )

    def _outputs(self, sweep_dir: Path) -> list[Path]:
        return sorted(sweep_dir.glob("tax-*.json"))

    def test_aftertax_reproduces_the_in_sweep_result_exactly(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            status = run_aftertax(self.plain_dir, self.policy, self.distributions)
        self.assertEqual(status, 0)
        outputs = self._outputs(self.plain_dir)
        self.assertEqual(len(outputs), 1)
        produced = json.loads(outputs[0].read_text(encoding="utf-8"))
        in_sweep = json.loads((self.taxed_dir / "tax.json").read_text(encoding="utf-8"))
        self.assertEqual(produced["runs"], in_sweep["runs"])
        self.assertEqual(produced["tax_policy_sha256"], in_sweep["tax_policy_sha256"])
        self.assertEqual(produced["distributions_sha256"], in_sweep["distributions_sha256"])
        self.assertEqual(produced["source"], "aftertax")
        self.assertEqual(produced["artifact_schema"], 6)

    def test_the_output_name_carries_policy_distributions_and_code(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            run_aftertax(self.plain_dir, self.policy, self.distributions)
        name = self._outputs(self.plain_dir)[0].name
        in_sweep = json.loads((self.taxed_dir / "tax.json").read_text(encoding="utf-8"))
        self.assertEqual(
            name,
            f"tax-{in_sweep['tax_policy_sha256'][:12]}-{in_sweep['distributions_sha256'][:12]}"
            f"-{code_fingerprint()[:12]}.json",
        )

    def test_running_twice_is_idempotent(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            run_aftertax(self.plain_dir, self.policy, self.distributions)
            run_aftertax(self.plain_dir, self.policy, self.distributions)
        self.assertEqual(len(self._outputs(self.plain_dir)), 1)

    def test_an_archived_distributions_input_makes_the_sweep_self_contained(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            status = run_aftertax(self.taxed_dir, self.policy, None)
        self.assertEqual(status, 0)
        produced = json.loads(self._outputs(self.taxed_dir)[0].read_text(encoding="utf-8"))
        in_sweep = json.loads((self.taxed_dir / "tax.json").read_text(encoding="utf-8"))
        self.assertEqual(produced["runs"], in_sweep["runs"])
        self.assertEqual(produced["distributions_manifest"], in_sweep["distributions_manifest"])

    def test_a_sweep_without_an_archive_needs_the_distributions_argument(self) -> None:
        with self.assertRaisesRegex(ValueError, "--distributions"):
            run_aftertax(self.plain_dir, self.policy, None)

    def test_the_policy_must_cover_the_sweep_s_universe(self) -> None:
        narrow = self.root / "configs" / "narrow.toml"
        narrow.write_text(TAX_ONLY.replace("D = 0.0\n", "").replace('D = "commodity_pool"\n', ""), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "is missing D"):
            run_aftertax(self.plain_dir, narrow, self.distributions)

    def test_the_command_prints_one_line_per_run(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run_aftertax(self.plain_dir, self.policy, self.distributions)
        text = output.getvalue()
        self.assertIn("strategy", text)
        self.assertIn("cash", text)
        self.assertIn("worst", text)


class ReconstructionTests(unittest.TestCase):
    def test_a_reconstructed_run_has_the_archived_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            (root / "configs" / "evaluation_periods.toml").write_text(SWEEP_PERIODS, encoding="utf-8")
            path = root / "configs" / "run.toml"
            path.write_text(SWEEP_CONFIG, encoding="utf-8")
            config = load_config(path)
            data = load_market_data(config)
            sweep = run_sweep(config, data)
            _, sweep_dir = write_sweep_report(config, data, sweep)
            base = sweep_dir / "variants" / "base"
            rebuilt = reconstruct_result(
                "base", base / "strategy_equity.csv", base / "strategy_trades.csv", 10000.0
            )
            metrics = calculate_metrics(rebuilt, data)
            archived = json.loads((sweep_dir / "criteria.json").read_text(encoding="utf-8"))
            for key, value in archived["variants"]["base"]["strategy"].items():
                self.assertAlmostEqual(float(metrics[key]), float(value), places=9, msg=key)
            self.assertEqual(len(rebuilt.fills), len(sweep.runs["base"][0].fills))

    def test_run_names_mirror_the_sweep_s(self) -> None:
        self.assertEqual(tax_run_name("base", "strategy"), "strategy")
        self.assertEqual(tax_run_name("base", "benchmark"), "benchmark")
        self.assertEqual(tax_run_name("exposure_matched", "strategy"), "exposure_matched")
        self.assertEqual(tax_run_name("exposure_matched", "benchmark"), "cash")
        self.assertEqual(tax_run_name("static_full", "strategy"), "static_full")
        self.assertIsNone(tax_run_name("static_full", "benchmark"))
        self.assertEqual(tax_run_name("lookback_9", "strategy"), "variant:lookback_9")
        self.assertIsNone(tax_run_name("lookback_9", "benchmark"))
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_cli.py -q`
Expected: FAIL — `ImportError: cannot import name 'run_aftertax'` (and the reconstruct module missing).

- [ ] **Step 3: Implement the reconstruction module**

Create `src/boring_alpha/tax/reconstruct.py`:

```python
"""Rebuild what the overlay needs from a sweep directory's archived files (spec §7).

A sweep keeps every run's equity curve and trade ledger and the exact prices
and cash it saw, so any past sweep can be scored under a new policy, or by a
corrected overlay, without re-running it. Run names mirror `run_sweep`'s so an
`aftertax` result and an in-sweep `tax.json` compare key for key.
"""

from __future__ import annotations

import csv
from datetime import date
import gzip
import json
from pathlib import Path
import shutil
import tempfile
import tomllib

from boring_alpha.data.csv_loader import load_csv_market_data
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, Fill


def read_manifest(sweep_dir: Path) -> dict:
    path = sweep_dir / "manifest.json"
    if not path.is_file():
        raise ValueError(f"{sweep_dir} holds no manifest.json; is it a sweep directory?")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for key in ("sweep_id", "strategy_id", "config_toml"):
        if key not in manifest:
            raise ValueError(f"{path} records no {key}; it predates the sweep artifact format")
    return manifest


def _config_of(manifest: dict) -> dict:
    return tomllib.loads(manifest["config_toml"])


def initial_cash_from(manifest: dict) -> float:
    return float(_config_of(manifest)["portfolio"]["initial_cash"])


def symbols_from(manifest: dict) -> tuple[str, ...]:
    return tuple(str(symbol).upper() for symbol in _config_of(manifest)["strategy"]["symbols"])


def read_equity_csv(path: Path) -> tuple[EquityPoint, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        return tuple(
            EquityPoint(
                date.fromisoformat(row["date"]),
                float(row["equity"]),
                float(row["cash"]),
                float(row["gross_exposure"]),
            )
            for row in csv.DictReader(handle)
        )


def read_trades_csv(path: Path) -> tuple[Fill, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        return tuple(
            Fill(
                date=date.fromisoformat(row["date"]),
                symbol=row["symbol"],
                side=row["side"],
                quantity=float(row["quantity"]),
                price=float(row["price"]),
                notional=float(row["notional"]),
                cost=float(row["cost"]),
                intended_notional=float(row["intended_notional"]),
                reference_price=float(row["reference_price"]),
            )
            for row in csv.DictReader(handle)
        )


def reconstruct_result(
    name: str, equity_path: Path, trades_path: Path, initial_cash: float
) -> BacktestResult:
    """A `BacktestResult` with the fields the overlay reads; decisions are not needed."""

    return BacktestResult(
        name=name,
        initial_equity=initial_cash,
        equity_curve=read_equity_csv(equity_path),
        fills=read_trades_csv(trades_path),
        decisions=(),
    )


def gunzip_to(source: Path, target: Path) -> None:
    with gzip.open(source, "rb") as packed, target.open("wb") as unpacked:
        shutil.copyfileobj(packed, unpacked)


def market_data_from_archive(sweep_dir: Path) -> MarketData:
    """The dataset the sweep saw, from its archived inputs."""

    for name in ("input_prices.csv.gz", "input_cash.csv.gz"):
        if not (sweep_dir / name).is_file():
            raise ValueError(f"{sweep_dir} archived no {name}; it cannot be re-scored")
    with tempfile.TemporaryDirectory() as directory:
        prices = Path(directory) / "market_daily.csv"
        cash = Path(directory) / "cash_daily.csv"
        gunzip_to(sweep_dir / "input_prices.csv.gz", prices)
        gunzip_to(sweep_dir / "input_cash.csv.gz", cash)
        return load_csv_market_data(prices, cash)


def tax_run_name(variant: str, role: str) -> str | None:
    """Which tax run a variant directory's file is. Mirrors `run_sweep`:
    the base variant is the strategy and the gating benchmark; the
    exposure-matched directory holds that allocation and cash; the static_full
    directory holds full static; every other variant contributes its strategy only."""

    if variant == "base":
        return "strategy" if role == "strategy" else "benchmark"
    if variant == "exposure_matched":
        return "exposure_matched" if role == "strategy" else "cash"
    if variant == "static_full":
        return "static_full" if role == "strategy" else None
    return f"variant:{variant}" if role == "strategy" else None


def run_files(sweep_dir: Path) -> list[tuple[str, Path, Path]]:
    """(run name, equity CSV, trades CSV) for every archived run, in a stable order."""

    variants = sweep_dir / "variants"
    if not variants.is_dir():
        raise ValueError(f"{sweep_dir} holds no variants/ directory")
    files: list[tuple[str, Path, Path]] = []
    for variant_dir in sorted(variants.iterdir()):
        if not variant_dir.is_dir():
            continue
        for role in ("strategy", "benchmark"):
            name = tax_run_name(variant_dir.name, role)
            if name is None:
                continue
            files.append((name, variant_dir / f"{role}_equity.csv", variant_dir / f"{role}_trades.csv"))
    return files
```

- [ ] **Step 4: Implement the command**

In `src/boring_alpha/cli.py`:

Add imports: `import tempfile`; `from boring_alpha.config import DATASET_END, UNBOUNDED_PERIOD, AppConfig, load_config, load_tax_policy`; `from boring_alpha.data.distributions import load_distributions`; `from boring_alpha.report import ARTIFACT_SCHEMA, READABLE_SCHEMAS, code_fingerprint, json_text, write_once, write_report`; `from boring_alpha.tax import OVERLAY_VERSION, policy_sha256, run_scenarios`; `from boring_alpha.tax.reconstruct import gunzip_to, initial_cash_from, market_data_from_archive, read_manifest, reconstruct_result, run_files, symbols_from`.

Add after `run_classify`:

```python
def run_aftertax(sweep_dir: Path, policy_path: Path, distributions_path: Path | None = None) -> int:
    """Score an existing sweep after tax under a policy file (spec §7).

    Runs are rebuilt from the archived equity curves and trade ledgers and the
    archived prices and cash. Distributions come from `--distributions` (with the
    snapshot manifest beside it) or, when the sweep archived them, from the sweep
    itself. The output is named by every input including the overlay's code
    fingerprint, so a corrected overlay produces a separately identified result
    and identical inputs are idempotent.
    """

    manifest = read_manifest(sweep_dir)
    symbols = symbols_from(manifest)
    initial_cash = initial_cash_from(manifest)
    policy = load_tax_policy(policy_path, symbols)
    data = market_data_from_archive(sweep_dir)

    if distributions_path is not None:
        manifest_path = distributions_path.parent / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"no manifest.json beside {distributions_path}; a v2 snapshot is required")
        snapshot = json.loads(manifest_path.read_text(encoding="utf-8"))
        table = load_distributions(distributions_path, manifest_path=manifest_path)
        block = {
            "methodology": snapshot.get("methodology"),
            "created_at": snapshot.get("created_at"),
            "splits": table.splits,
            "sha256": table.sha256,
        }
    else:
        archived = sweep_dir / "input_distributions.csv.gz"
        block = manifest.get("distributions_manifest")
        if not archived.is_file() or block is None:
            raise ValueError(
                f"{sweep_dir} archived no distributions; pass --distributions with the "
                "snapshot's distributions_daily.csv"
            )
        with tempfile.TemporaryDirectory() as directory:
            unpacked = Path(directory) / "distributions_daily.csv"
            gunzip_to(archived, unpacked)
            table = load_distributions(unpacked, manifest_block=block)
        # The archive holds the truncated rows; the identity is the source file's,
        # recorded in the block, so results match the in-sweep tax.json exactly.
        table.sha256 = block["sha256"]
    table = table.through(data.dates[-1])
    table.require_coverage(data, symbols)

    code_hash = code_fingerprint()
    runs: dict[str, dict] = {}
    for name, equity_path, trades_path in run_files(sweep_dir):
        result = reconstruct_result(name, equity_path, trades_path, initial_cash)
        runs[name] = run_scenarios(
            result, data, table, policy, initial_cash=initial_cash, code_sha256=code_hash
        )

    policy_hash = policy_sha256(policy)
    output = sweep_dir / f"tax-{policy_hash[:12]}-{table.sha256[:12]}-{code_hash[:12]}.json"
    write_once(
        output,
        json_text(
            {
                "artifact_schema": ARTIFACT_SCHEMA,
                "sweep_id": manifest["sweep_id"],
                "strategy_id": manifest["strategy_id"],
                "code_sha256": code_hash,
                "source": "aftertax",
                "tax_policy_sha256": policy_hash,
                "distributions_sha256": table.sha256,
                "distributions_manifest": block,
                "overlay_version": OVERLAY_VERSION,
                "runs": runs,
            }
        ),
    )

    print(f"BoringAlpha aftertax {manifest['sweep_id']} ({manifest['strategy_id']}), policy {policy_hash[:12]}")
    print(f"{'Run':<24}{'Pre-tax CAGR':>14}{'After-tax worst':>17}{'Worst scenario':>24}{'Best':>10}")
    for name, scenarios in runs.items():
        worst_key = min(scenarios, key=lambda key: scenarios[key]["metrics"]["after_tax_cagr"])
        best_key = max(scenarios, key=lambda key: scenarios[key]["metrics"]["after_tax_cagr"])
        worst = scenarios[worst_key]["metrics"]
        print(
            f"{name:<24}{worst['pre_tax_cagr']:>14.4f}{worst['after_tax_cagr']:>17.4f}"
            f"{worst_key:>24}{scenarios[best_key]['metrics']['after_tax_cagr']:>10.4f}"
        )
        checks = scenarios[worst_key]["identity_checks"]
        failed = [
            check for check in ("share_identity_passed", "income_plus_gain_passed", "implied_price_check_passed")
            if not checks[check]
        ]
        if failed:
            print(f"  identity checks failed for {name}: {', '.join(failed)}")
    print(f"Written: {output}")
    return 0
```

In `build_parser`, before `return parser`:

```python
    aftertax = subparsers.add_parser(
        "aftertax", help="score an existing sweep after tax under a policy file"
    )
    aftertax.add_argument("sweep", type=Path, help="sweep directory to re-score")
    aftertax.add_argument(
        "--policy", type=Path, required=True, help="TOML file holding only a [tax] table"
    )
    aftertax.add_argument(
        "--distributions",
        type=Path,
        default=None,
        help="distributions_daily.csv of a v2 snapshot (manifest.json beside it); "
        "omit to use the sweep's own archived distributions",
    )
```

In `main`, add `if args.command == "aftertax": raise SystemExit(run_aftertax(args.sweep, args.policy, args.distributions))` before the `except`.

Add `"run_aftertax"` to `__all__`.

- [ ] **Step 5: Document**

In `README.md`, after the "## Run artifacts" section, add:

```markdown
## After tax

A configuration may carry a `[tax]` table (see `configs/tax_policy.toml` for
the stylized BA-001 policy). When it does, every run in a sweep is also scored
after tax by a pure overlay over the pre-tax artifacts: fills are converted to
real shares, distributions open their own lots, sales close lots by method,
wash sales are adjusted, and each calendar year is taxed with
character-retaining carryovers under an after-tax NAV convention (the pre-tax
path is rescaled at each year end by the tax paid). Three inputs are declared
rather than known — lot selection, a commodity pool's tax character, and the
qualified fraction of equity distributions — so the overlay runs a fixed grid
of eight scenarios and any after-tax conclusion must hold under all of them.
Results land in `tax.json` beside `criteria.json`, with a summary block in
`summary.md`. Drawdown is never recomputed after tax.

Any archived sweep can be re-scored without re-running it:

```bash
boring-alpha aftertax experiments/BA-001/sweeps/<id> --policy configs/tax_policy.toml \
    --distributions data/current/distributions_daily.csv
```

The output is named by the policy, the distributions and the overlay's code
fingerprint, so a corrected overlay produces a separately identified file and
identical inputs are idempotent. Rates in the checked-in policy are a
federal-only stylized scenario, not anyone's bracket; real rates belong in an
untracked local copy.
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_cli.py -q`
Expected: all pass (7 `AfterTaxCommandTests`, 2 `ReconstructionTests`, plus the three pre-existing).

- [ ] **Step 7: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `441 passed, 3 subtests passed`.

```bash
git add src/boring_alpha/tax/reconstruct.py src/boring_alpha/cli.py README.md tests/test_cli.py
git commit -m "Add an aftertax command that re-scores archived sweeps

Runs are rebuilt from the archived equity curves, trade ledgers, prices
and cash; distributions come from a v2 snapshot or from the sweep's own
archive; the policy is a standalone TOML file. The output is named by the
policy, the distributions and the overlay's code fingerprint, reproduces
an in-sweep tax.json exactly on the same inputs, and is idempotent.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: The post-hoc after-tax note on BA-001

The overlay's first real use: score BA-001's two archived sweeps under the stylized policy and write down what they show. This is a diagnostic computed after the results were known; it changes nothing about BA-001's classification and the note says so in its first line.

**Files:**
- Create: `docs/notes/2026-09-04-BA-001-after-tax.md`
- Reads: `experiments/BA-001/sweeps/4b9d1479f811d108`, `experiments/BA-001/sweeps/f0a36ea722ebefd4`, `data/current/distributions_daily.csv` (the v2 snapshot); writes one `tax-*.json` into each sweep directory through the write-once path (git-ignored).

**Interfaces:**
- Consumes: the `aftertax` command (Task 8), `configs/tax_policy.toml` (Task 1).
- Produces: the note plan 2's closing review cites.

- [ ] **Step 1: Score both sweeps**

```bash
.venv/bin/boring-alpha aftertax experiments/BA-001/sweeps/4b9d1479f811d108 \
    --policy configs/tax_policy.toml --distributions data/current/distributions_daily.csv
.venv/bin/boring-alpha aftertax experiments/BA-001/sweeps/f0a36ea722ebefd4 \
    --policy configs/tax_policy.toml --distributions data/current/distributions_daily.csv
```

Expected: each prints a header, one line per run (`strategy`, `benchmark`, `exposure_matched`, `cash`, `variant:double_cost`, `variant:lookback_9`, `variant:lookback_15`, `variant:drop_top_sleeve`), and `Written: .../tax-<policy12>-<distributions12>-<code12>.json`. Keep both outputs. If either prints `identity checks failed`, keep going: the note reports it.

The archived prices came from the v1 snapshot and the distributions from the v2 snapshot, fetched a few hours apart. If Yahoo revised any historical price in between, the share identity or the implied-price check will say so. That is what the checks are for; report what they say and do not adjust anything.

- [ ] **Step 2: Extract the figures**

```bash
python3 - <<'EOF'
import glob, json
for label, sweep in (("development", "4b9d1479f811d108"), ("validation", "f0a36ea722ebefd4")):
    path = sorted(glob.glob(f"experiments/BA-001/sweeps/{sweep}/tax-*.json"))[-1]
    tax = json.load(open(path))
    print(f"\n### {label} — {path.split('/')[-1]}")
    print("| Run | Pre-tax CAGR | After-tax CAGR, worst | Worst scenario | After-tax CAGR, best | Drag, worst (bps) | Taxes paid (base) | Liquidation tax (base) | Wash-sale disallowed (base) |")
    print("|---|---:|---:|---|---:|---:|---:|---:|---:|")
    for run, scenarios in tax["runs"].items():
        worst = min(scenarios, key=lambda k: scenarios[k]["metrics"]["after_tax_cagr"])
        best = max(scenarios, key=lambda k: scenarios[k]["metrics"]["after_tax_cagr"])
        w, b, base = scenarios[worst]["metrics"], scenarios[best]["metrics"], scenarios["hifo-deferral-base"]
        print(f"| {run} | {w['pre_tax_cagr']:.4f} | {w['after_tax_cagr']:.4f} | {worst} | {b['after_tax_cagr']:.4f} | "
              f"{w['tax_drag_bps']:.0f} | {base['totals']['taxes_paid']:.0f} | {base['totals']['tax_liquidation']:.0f} | "
              f"{base['totals']['wash_sale_disallowed_total']:.0f} |")
    print("\nIdentity checks (base scenario):")
    for run, scenarios in tax["runs"].items():
        c = scenarios["hifo-deferral-base"]["identity_checks"]
        ratio = "n/a" if c["implied_reinvestment_price_ratio_min"] is None else f"{c['implied_reinvestment_price_ratio_min']:.4f} to {c['implied_reinvestment_price_ratio_max']:.4f}"
        print(f"- {run}: share identity {'ok' if c['share_identity_passed'] else 'FAILED'} (max dev {c['share_identity_max_relative_deviation']:.2e}); "
              f"income+gain {'ok' if c['income_plus_gain_passed'] else 'FAILED'} (dev {c['income_plus_gain_relative_deviation']:.2e}); "
              f"implied price ratio {ratio} over {c['ex_dates_checked']} ex-dates, {'ok' if c['implied_price_check_passed'] else 'FAILED'}")
EOF
```

- [ ] **Step 3: Write the note**

Create `docs/notes/2026-09-04-BA-001-after-tax.md`. Paste the two tables and the identity-check lists from Step 2 verbatim where marked, and fill the bracketed sentences from those figures only — no figure may appear in prose that is not in a table:

```markdown
# BA-001 after tax: a post-hoc diagnostic

**This is a diagnostic computed after BA-001's results were known. It is not a
review, it changes nothing about BA-001's classification (Inconclusive), and
its figures were not available when the advancement criteria were written.**
Its purpose is to calibrate expectations for the successor and to exercise the
after-tax machinery on real trades before anything depends on it.

Date: 2026-09-04
Policy: `configs/tax_policy.toml` (federal-only stylized rates; ordinary 35%,
long-term 20%, collectibles 28%; base and low qualified sets)
Distributions: `data/current/distributions_daily.csv`, snapshot `20260904T192633Z`
Overlay: `tax-overlay-v1`; outputs are the `tax-*.json` files in each sweep directory
Convention: after-tax NAV convention (spec §4.8); drawdown is pre-tax throughout;
eight scenarios, worst and best shown; "base" is `hifo-deferral-base`.

## Development (2007–2017), sweep `4b9d1479f811d108`

<paste the development table>

## Validation (2018–2021), sweep `f0a36ea722ebefd4`

<paste the validation table>

## Identity checks

<paste both identity-check lists, each under a "development" / "validation" heading>

[One sentence per period stating whether all three checks passed for every run.
If any failed: name the run and the check, state that the archived prices come
from the v1 snapshot and the distributions from the v2 snapshot, and say that
the figures for that run are not to be cited until a sweep run on one snapshot
reproduces them.]

## What the figures say

- **Strategy against holding less.** [Compare the strategy's worst-scenario
  after-tax CAGR with the exposure-matched allocation's in each period, citing
  the table rows. State which is higher in each period and by how much, in
  basis points of CAGR.]
- **The cost of trading.** [Compare the strategy's tax drag with the exposure-
  matched allocation's and the benchmark's in each period.]
- **Wash sales.** [State the strategy's disallowed total in each period and
  whether it is material relative to its taxes paid.]
- **Scenario spread.** [State the gap between worst and best after-tax CAGR for
  the strategy in each period, and which axis drives it — read the worst and
  best scenario keys.]

## What this does and does not establish

It shows what BA-001's recorded trades would have cost after tax under a
declared policy. It does not re-open BA-001: the criteria were pre-tax, the
classification stands, and the successor's charter is where after-tax
criteria belong. The scenario grid is the safeguard against the inputs that
are declared rather than known; a conclusion that changes between worst and
best scenario is not a conclusion.
```

- [ ] **Step 4: Confirm the note is complete**

Run: `grep -n "^\[" docs/notes/2026-09-04-BA-001-after-tax.md; grep -c "<paste" docs/notes/2026-09-04-BA-001-after-tax.md`
Expected: no lines beginning with `[` and a count of `0` for `<paste`.

- [ ] **Step 5: Commit**

Nothing under `experiments/` or `data/` is tracked; only the note is committed.

```bash
git add docs/notes/2026-09-04-BA-001-after-tax.md
git commit -m "Record BA-001's after-tax diagnostic on both archived sweeps

<One line: identity checks passed for every run, or which failed and why the
affected figures are not to be cited.>

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review against the spec

**Spec coverage.** §4.1 inputs: Task 6 `apply_overlay` signature. §4.2 real shares, HIFO/FIFO, partial closes, over-sell error, share identity: Tasks 2 and 6. §4.3 child lots from data-implied growth, income vs return of capital, excess as gain, income-plus-gain identity: Tasks 3 and 6. §4.4 cash interest: Task 6. §4.5 qualified fraction with the 61-day test over the complete fill history, standard/collectibles/commodity_pool classes, two commodity treatments, collectibles cap: Tasks 1, 5, 6. §4.6 wash sales adjusted with matching once, tacking, future purchases; GLD omission stated with bound: Tasks 4 and 6 (`KNOWN_OMISSIONS`). §4.7 marks first, netting, character-retaining carryovers, collectibles bucket first, the tax formula: Task 5. §4.8 NAV convention, scale update, liquidation as the final year twice, named in outputs: Task 6. §4.9 policy table, validation, hash excluding the path, base fractions: Task 1 (`configs/tax_policy.toml` carries the spec's proposed values). §4.10 outputs: Task 6 (`by_year` holds scaled amounts and the scale, `totals`, `wealth`, `metrics`, `identity_checks` including the implied-price ratio carried forward from plan 1). §4.11 the fixed grid of eight: Task 1; "holds under all" as a criterion is spec 2's job, and the sweep exposes the full grid for it. §5.3 secondary rows when a target-exposure benchmark gates: Task 7 (`static_full`). §7 sweep runs, archive, embedded manifest, summary block, schema 6 with 5 readable, tax hashes in manifest and criteria, `aftertax` naming and idempotence: Tasks 7 and 8. §8 the note: Task 9. §9 tests named in the spec: real-share conversion (Task 2), HIFO/FIFO by hand (Task 2), child lots and identity (Task 3), return of capital (Task 3), wash sales 30 vs 31 days, reinvested lots, matched once (Task 4), holding period 365/366 (Task 5), qualified 61/60 and year-crossing window (Task 5), carryover character (Task 5), collectibles routing and cap (Tasks 1, 5), commodity pool both treatments (Task 6), cash interest (Task 6), rescaling and liquidation (Task 6), eight scenarios and determinism (Task 6), sweep writes and archives (Task 7), `aftertax` reconstruction equality and idempotence (Task 8). §12 steps 3, 6, 7: Tasks 1–6, 7–8, 9.

**Known simplifications, stated in code or docstrings rather than hidden:** the qualification test uses the parent lot's opening date and the date its last share was sold; reinvested child lots created after a loss sale are not matched as its replacements; a replacement lot is tacked once per sale; the low qualified set caps rather than replaces; commodity-pool interest is not separated. Each is in `KNOWN_OMISSIONS` or the relevant docstring. Plan 2's closing review should add a Revision 3.2 entry to the spec recording them alongside the note.

**Placeholder scan.** The only bracketed fields are in Task 9's note template, which a person fills from the Step 2 output; Step 4 checks none remain.

**Type consistency.** `LotBook.buy(symbol, day, shares, basis, *, source, opened, extra_basis, replacement_capacity)` is called that way in Tasks 3 and 6. `LotBook.sell(symbol, day, shares, proceeds) -> list[Realized]` in Tasks 2, 4, 6. `LotBook.distribute(symbol, ex_date, dividend_per_share, growth, *, return_of_capital) -> list[Distribution]` in Tasks 3, 4, 6. `apply_wash_sales(records, existing, future)` in Tasks 4 and 6; `FuturePurchase(symbol, acquired, shares, replacement_capacity)` in both. `Amounts.add_gain(amount, *, long_term, gains_class, mark_to_market)`, `Amounts.scaled`, `Amounts.as_dict`, `net_and_tax(amounts, short_carry, long_carry, tax) -> YearTax` in Tasks 5 and 6. `qualified_fraction(tax, scenario, symbol)`, `policy_sha256(tax)`, `policy_record(tax)`, `Scenario.key/as_dict`, `SCENARIOS` in Tasks 1, 6, 7, 8. `run_scenarios(result, data, table, tax, *, initial_cash, code_sha256)` in Tasks 6, 7, 8. `tax_run_name` (Task 8) mirrors the literal names Task 7 writes. `load_tax_policy(path, symbols)` in Tasks 1 and 8. Expected suite totals: 339 → 356 → 369 → 377 → 387 → 407 → 422 → 432 → 441; the count in the file is what matters if one differs.
