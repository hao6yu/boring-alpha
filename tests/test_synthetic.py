from datetime import date
import statistics
import unittest

from boring_alpha.data.synthetic import generate_synthetic_market_data

START, END = date(2000, 1, 3), date(2020, 12, 31)
SEEDS = tuple(range(20))


def _pooled_mean_session_return(regime: str) -> float:
    returns: list[float] = []
    for seed in SEEDS:
        data = generate_synthetic_market_data(
            ("A",), START, END, seed=seed, annual_cash_rate=0.0, regime=regime
        )
        days = data.symbol_dates["A"]
        returns.extend(
            data.bar(days[i], "A").close / data.bar(days[i - 1], "A").close - 1.0
            for i in range(1, len(days))
        )
    return statistics.mean(returns)


class SyntheticRegimeTests(unittest.TestCase):
    def test_random_walk_has_no_detectable_drift(self) -> None:
        # Pooled over 20 seeds and ~5,000 sessions each, the standard error of
        # the mean is near 2e-5, so 1e-4 is a wide margin around zero.
        self.assertLess(abs(_pooled_mean_session_return("random_walk")), 1e-4)

    def test_trending_regime_drifts_upward(self) -> None:
        self.assertGreater(_pooled_mean_session_return("trending"), 1e-4)

    def test_default_regime_is_trending(self) -> None:
        kwargs = {"symbols": ("A",), "start": START, "end": date(2001, 12, 31),
                  "seed": 3, "annual_cash_rate": 0.01}
        self.assertEqual(
            generate_synthetic_market_data(**kwargs).fingerprint(),
            generate_synthetic_market_data(**kwargs, regime="trending").fingerprint(),
        )

    def test_regimes_produce_different_data(self) -> None:
        kwargs = {"symbols": ("A",), "start": START, "end": date(2001, 12, 31),
                  "seed": 3, "annual_cash_rate": 0.01}
        self.assertNotEqual(
            generate_synthetic_market_data(**kwargs, regime="trending").fingerprint(),
            generate_synthetic_market_data(**kwargs, regime="random_walk").fingerprint(),
        )

    def test_random_walk_is_deterministic(self) -> None:
        kwargs = {"symbols": ("A", "B"), "start": START, "end": date(2001, 12, 31),
                  "seed": 9, "annual_cash_rate": 0.01, "regime": "random_walk"}
        self.assertEqual(
            generate_synthetic_market_data(**kwargs).fingerprint(),
            generate_synthetic_market_data(**kwargs).fingerprint(),
        )

    def test_unknown_regime_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "regime must be"):
            generate_synthetic_market_data(
                ("A",), START, END, seed=1, annual_cash_rate=0.0, regime="mean_reverting"
            )


if __name__ == "__main__":
    unittest.main()
