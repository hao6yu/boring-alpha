import unittest

from boring_alpha.portfolio.account import AccountingError, Portfolio


class PortfolioTests(unittest.TestCase):
    def test_negative_cash_raises_a_runtime_error_subclass(self) -> None:
        portfolio = Portfolio(1_000.0, ("A",))
        portfolio.cash = -1.0
        with self.assertRaises(AccountingError) as caught:
            portfolio.apply([])
        self.assertIsInstance(caught.exception, RuntimeError)


if __name__ == "__main__":
    unittest.main()
