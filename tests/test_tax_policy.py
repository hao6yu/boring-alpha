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
