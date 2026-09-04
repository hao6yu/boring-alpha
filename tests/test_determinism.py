from datetime import date
import unittest

from boring_alpha.data.synthetic import generate_synthetic_market_data


class DeterminismTests(unittest.TestCase):
    def test_synthetic_fingerprint_is_stable(self) -> None:
        kwargs = {
            "symbols": ("A", "B"),
            "start": date(2020, 1, 1),
            "end": date(2021, 1, 1),
            "seed": 7,
            "annual_cash_rate": 0.02,
        }
        first = generate_synthetic_market_data(**kwargs)
        second = generate_synthetic_market_data(**kwargs)
        self.assertEqual(first.fingerprint(), second.fingerprint())


if __name__ == "__main__":
    unittest.main()
