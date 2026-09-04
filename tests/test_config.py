from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import load_config


class ConfigTests(unittest.TestCase):
    def test_checked_in_config_is_valid_and_fixed_sleeves_sum_to_one(self) -> None:
        config = load_config(Path("configs/ba_001_multi_asset_trend.toml"))
        self.assertEqual(config.strategy.strategy_id, "BA-001")
        self.assertAlmostEqual(
            len(config.strategy.symbols) * config.strategy.sleeve_weight, 1.0
        )

    def test_rejects_leveraged_sleeves(self) -> None:
        content = """
[strategy]
id = "X"
name = "Bad"
symbols = ["A", "B"]
lookback_months = 12
sleeve_weight = 0.6
[portfolio]
initial_cash = 1000
[execution]
cost_bps = 0
[data]
source = "synthetic"
start = "2020-01-01"
end = "2022-01-01"
[backtest]
start = "2021-01-01"
end = "2022-01-01"
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.toml"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exceed 100%"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
