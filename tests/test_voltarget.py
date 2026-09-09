"""A volatility-targeted weight must be computable from what was knowable, only.

The headline test is the look-ahead one. A trend gate that reads today's close and
then sizes today's position will look magnificent in a backtest and worthless in
an account, and the first version of this module did exactly that. Everything else
here checks arithmetic that a wrong sign or an off-by-one could silently corrupt.
"""

import math
import unittest

from boring_alpha.signals.voltarget import (
    VolTargetPolicy,
    moving_average,
    rolling_volatility,
)


def prices_from(daily_returns, start=100.0):
    out, value = [], start
    for r in daily_returns:
        value *= 1.0 + r
        out.append(value)
    return out


def returns_from(closes):
    return [0.0] + [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]


class NoLookAhead(unittest.TestCase):
    def setUp(self):
        self.returns = [0.001 * math.sin(i / 5.0) for i in range(400)]
        self.closes = prices_from(self.returns)
        self.policy = VolTargetPolicy(
            target_vol=0.15, vol_window=20, trend_window=50, max_weight=1.5,
            rebalance_band=0.0,
        )

    def test_todays_close_cannot_change_todays_weight(self):
        base = self.policy.raw_weights(self.closes, returns_from(self.closes))
        tampered_closes = list(self.closes)
        tampered_returns = list(returns_from(self.closes))
        probe = 300
        # A violent move on the probe day: it must not move that day's weight.
        tampered_closes[probe] *= 1.25
        tampered_returns[probe] = 0.25
        moved = self.policy.raw_weights(tampered_closes, tampered_returns)
        self.assertAlmostEqual(base[probe], moved[probe], places=12)

    def test_yesterdays_close_still_can(self):
        """The negative control. If this passes too, the gate is not firing at all."""

        base = self.policy.raw_weights(self.closes, returns_from(self.closes))
        tampered = list(self.closes)
        probe = 300
        tampered[probe - 1] *= 0.70
        moved = self.policy.raw_weights(tampered, returns_from(tampered))
        self.assertNotAlmostEqual(base[probe], moved[probe], places=6)

    def test_weight_is_bounded_by_the_cap(self):
        weights = self.policy.raw_weights(self.closes, returns_from(self.closes))
        live = [w for w in weights if w is not None]
        self.assertLessEqual(max(live), self.policy.max_weight + 1e-12)


class Arithmetic(unittest.TestCase):
    def test_realised_vol_matches_a_hand_computed_window(self):
        returns = [0.01, -0.01, 0.02, -0.02] + [0.0] * 30
        vol = rolling_volatility(returns, 5)
        window = returns[0:5]
        mean = sum(window) / 5
        expected = math.sqrt(sum((v - mean) ** 2 for v in window) / 4 * 252)
        self.assertAlmostEqual(vol[5], expected, places=12)

    def test_no_output_before_the_window_is_full(self):
        vol = rolling_volatility([0.01] * 10, 20)
        self.assertTrue(all(v is None for v in vol))

    def test_double_the_moves_halve_the_weight(self):
        """The whole idea, in one line: twice the risk, half the size."""

        calm = [0.02 * ((-1) ** i) for i in range(400)]
        wild = [r * 2.0 for r in calm]
        policy = VolTargetPolicy(target_vol=0.15, vol_window=30, trend_window=None,
                                 rebalance_band=0.0)
        a = policy.raw_weights(prices_from(calm), calm)[100]
        b = policy.raw_weights(prices_from(wild), wild)[100]
        self.assertLess(a, policy.max_weight - 1e-9, "test is void if the cap binds")
        self.assertAlmostEqual(b, a / 2.0, places=6)

    def test_zero_realised_volatility_emits_no_weight_rather_than_an_infinite_one(self):
        """target / 0 is infinity. Silence is the only honest answer."""

        closes = [100.0] * 400
        policy = VolTargetPolicy(target_vol=0.15, vol_window=30, trend_window=None)
        self.assertTrue(all(w is None for w in policy.raw_weights(closes, returns_from(closes))))

    def test_moving_average_excludes_the_current_bar(self):
        average = moving_average([1.0, 2.0, 3.0, 4.0], 2)
        self.assertIsNone(average[0])
        self.assertIsNone(average[1])
        self.assertAlmostEqual(average[2], 1.5)
        self.assertAlmostEqual(average[3], 2.5)


class BandsAndGates(unittest.TestCase):
    def test_a_small_desired_change_does_not_trade(self):
        returns = [0.001 * ((-1) ** i) for i in range(400)]
        closes = prices_from(returns)
        policy = VolTargetPolicy(target_vol=0.15, vol_window=20, trend_window=None,
                                 rebalance_band=0.10)
        traded = [t for _, t in policy.weights(closes, returns) if t > 0]
        # One trade to fund the book, then nothing: a constant series has no news.
        self.assertEqual(len(traded), 1)

    def test_a_volatility_spike_trades_despite_the_band(self):
        returns = [0.001] * 120 + [0.06] * 60
        closes = prices_from(returns)
        policy = VolTargetPolicy(target_vol=0.10, vol_window=20, trend_window=None,
                                 rebalance_band=0.10)
        traded = [t for _, t in policy.weights(closes, returns) if t > 0.10]
        self.assertGreaterEqual(len(traded), 1)

    def test_a_trend_gate_floors_weight_below_the_mean(self):
        returns = [0.004] * 200 + [-0.01] * 120
        closes = prices_from(returns)
        policy = VolTargetPolicy(target_vol=0.15, vol_window=30, trend_window=100,
                                 min_weight=0.0, rebalance_band=0.0)
        weights = [w for w in policy.raw_weights(closes, returns) if w is not None]
        self.assertAlmostEqual(weights[-1], 0.0, places=9)

    def test_noise_around_the_mean_does_not_de_risk(self):
        """The 1% hysteresis exists so price hovering on the line is not a signal."""

        returns = [0.0005 * ((-1) ** i) for i in range(400)]
        closes = prices_from(returns, start=100.0)
        policy = VolTargetPolicy(target_vol=0.15, vol_window=30, trend_window=100,
                                 rebalance_band=0.0)
        weights = [w for w in policy.raw_weights(closes, returns_from(closes)) if w is not None]
        self.assertGreater(weights[-1], 0.0)


class Guards(unittest.TestCase):
    def test_absurd_parameters_are_refused(self):
        for bad in (
            dict(target_vol=0.0),
            dict(target_vol=1.5),
            dict(vol_window=2),
            dict(trend_window=5),
            dict(max_weight=4.0),
            dict(min_weight=0.5, max_weight=0.4),
            dict(rebalance_band=1.5),
        ):
            with self.subTest(**bad):
                with self.assertRaises(ValueError):
                    VolTargetPolicy(**bad)

    def test_the_default_policy_is_lean(self):
        policy = VolTargetPolicy()
        self.assertEqual(policy.trend_window, 200)
        self.assertEqual(policy.max_weight, 1.0)
        self.assertLessEqual(policy.rebalance_band, 0.10)


if __name__ == "__main__":
    unittest.main()


class Cadence(unittest.TestCase):
    """Cost, not signal, sets the review interval. These tests pin the interval."""

    @staticmethod
    def churn_fixture():
        """Alternating calm and wild blocks: this is what moves realised vol.

        Sign flips alone do not. An earlier version of these tests used them and
        passed vacuously, because an alternating series has constant standard
        deviation and a vol target therefore never moves.
        """

        returns = []
        for block in range(16):
            amplitude = 0.002 if block % 2 == 0 else 0.035
            for tick in range(25):
                returns.append(amplitude if tick % 2 == 0 else -amplitude)
        return prices_from(returns), returns

    def test_no_trade_ever_lands_on_a_non_review_session(self):
        """The invariant, stated exactly. Counting trades proves nothing on its own."""

        closes, returns = self.churn_fixture()
        weekly = VolTargetPolicy(target_vol=0.30, vol_window=20, trend_window=None,
                                 rebalance_band=0.02, review_every=5)
        path = weekly.weights(closes, returns)
        first_trade = next(i for i, (_, turn) in enumerate(path) if turn > 0)
        for position, (_, turn) in enumerate(path):
            if turn <= 0.0 or position == first_trade:
                continue
            self.assertEqual(position % 5, 0, f"traded on session {position}")

    def test_a_weekly_book_trades_far_less_than_a_daily_one(self):
        """The reason cadence exists, measured on a fixture that actually churns."""

        closes, returns = self.churn_fixture()
        common = dict(target_vol=0.30, vol_window=20, trend_window=None, rebalance_band=0.02)
        quick = sum(1 for _, t in VolTargetPolicy(review_every=1, **common)
                    .weights(closes, returns) if t > 0)
        slow = sum(1 for _, t in VolTargetPolicy(review_every=5, **common)
                   .weights(closes, returns) if t > 0)
        self.assertGreater(quick, 50, f"fixture must churn, got {quick}")
        self.assertLess(slow * 3, quick, f"weekly {slow} vs daily {quick}")

    def test_a_weekly_review_still_reacts_to_a_crash(self):
        returns = [0.003] * 200 + [-0.05] * 40
        closes = prices_from(returns)
        weekly = VolTargetPolicy(target_vol=0.10, vol_window=20, trend_window=None,
                                 rebalance_band=0.05, review_every=5)
        path = [w for w, _ in weekly.weights(closes, returns) if w is not None]
        self.assertLess(path[-1], max(path) * 0.75, "shock must still reduce exposure")

    def test_absurd_cadence_is_refused(self):
        for bad in (dict(review_every=0), dict(review_every=200)):
            with self.subTest(**bad):
                with self.assertRaises(ValueError):
                    VolTargetPolicy(**bad)
