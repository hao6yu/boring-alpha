"""Tests for the rule priced as an insurance contract.

The headline is uncomfortable and therefore needs pinning: the rule's claim is genuinely large (+2.80%/yr) and
its premium is larger, and the net is negative at *every* crash threshold from 3% to 8%. That invariance is the
reason to trust the number rather than dismiss it as an artefact of where I drew the line, so it is tested as an
invariance and not as a single measurement. The bucket decomposition summing to the headline is the other
load-bearing property: if a month were counted twice, the whole contract reading would be decoration.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import insurance_pricing as ip                     # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402


class TheBucketsAddUp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.p = ip.price(cls.data, 0.05, 20_000.0)

    def test_claim_and_premium_sum_exactly_to_the_headline(self):
        """A month counted in two buckets would make the contract story decorative."""

        self.assertAlmostEqual(self.p["claim"] + self.p["premium_rally"] + self.p["premium_flat"],
                               self.p["net"], places=8)

    def test_every_month_is_in_exactly_one_bucket(self):
        self.assertEqual(self.p["n_claim"] + self.p["n_premium"] + self.p["n_flat"], self.p["months"])
        self.assertEqual(self.p["months"], 404)

    def test_the_claim_is_positive_and_the_premium_negative_because_that_is_what_the_words_mean(self):
        """If the crash bucket were negative the rule would be losing money in crashes, which would make it a
        worse contract than the arithmetic suggests and would have shown up three rounds ago."""

        self.assertGreater(self.p["claim"], 0.0)
        self.assertLess(self.p["premium_rally"], 0.0)


class TheContractLosesMoney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.p = ip.price(cls.data, 0.05, 20_000.0)

    def test_the_premium_exceeds_the_claim_which_is_the_rounds_finding(self):
        self.assertGreater(abs(self.p["premium_rally"] + self.p["premium_flat"]), abs(self.p["claim"]))
        self.assertLess(self.p["net"], 0.0)

    def test_the_claim_is_most_of_the_premium_so_this_is_a_cheap_policy_not_a_broken_one(self):
        """The distinction that matters: a −0.25%/yr net on a +2.80%/yr claim is ~9% loading, which is a
        functioning product with a price. A rule with no claim at all would be a different finding entirely."""

        ratio = abs(self.p["claim"]) / abs(self.p["premium_rally"] + self.p["premium_flat"])
        self.assertGreater(ratio, 0.85, "measured 0.919: the claim recovers 92 cents of every premium dollar")
        self.assertLess(ratio, 1.0)

    def test_the_net_cost_is_not_a_transaction_cost(self):
        """The broker takes almost none of it, which is what makes the loss structural rather than negotiable."""

        self.assertLess(self.p["bill"], abs(self.p["net"]) / 4.0)
        self.assertGreater(self.p["turnover"], 0.5, "a rule that never traded could not be called over-traded away")

    def test_the_cover_is_real_drawdown_and_not_just_a_volatility_claim(self):
        """Held: -29.4%. Unhedged: -51.8%. My first version of this assertion had the two reversed and passed
        nothing but my own sign error; the cover is real, and the test now says which number is which."""

        self.assertAlmostEqual(self.p["dd_rule"], -0.294, places=3)
        self.assertAlmostEqual(self.p["dd_held"], -0.518, places=3)
        self.assertGreater(abs(self.p["dd_held"]) - abs(self.p["dd_rule"]), 0.20)


class TheVerdictIsNotADefinition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_the_net_cost_is_the_same_number_at_every_claim_threshold(self):
        """The strongest result in the file. Crash buckets from 3% to 8% change the month counts from 61 to 14
        and leave the net cost at −0.25%/yr, because the rule's behaviour is a continuous function of volatility
        and my threshold only chooses how to label the months it was already reacting to."""

        nets = [ip.price(self.data, c, 20_000.0)["net"] for c in (0.03, 0.04, 0.05, 0.06, 0.08)]
        for n in nets:
            self.assertAlmostEqual(n, nets[0], places=1,
                                   msg="the verdict moved with the definition; it is not a finding")
        self.assertLess(nets[0], 0.0)

    def test_the_claim_count_falls_sharply_as_the_definition_tightens(self):
        """Paired with the test above: the counts move enormously, the verdict not at all. If both had been flat
        the buckets would have been meaningless."""

        a = ip.price(self.data, 0.03, 20_000.0)["n_claim"]
        b = ip.price(self.data, 0.08, 20_000.0)["n_claim"]
        self.assertGreater(a, b * 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
