from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID = """
[strategy]
id = "X"
name = "Valid"
symbols = ["A", "B"]
lookback_months = 12
sleeve_weight = 0.5
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
[evaluation]
period = "exploratory"
[report]
output_dir = "out"
"""


def _load(content: str):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "nested" / "config.toml"
        path.parent.mkdir()
        path.write_text(content, encoding="utf-8")
        return load_config(path), path


class ConfigTests(unittest.TestCase):
    def test_checked_in_config_is_valid_and_fixed_sleeves_sum_to_one(self) -> None:
        config = load_config(REPO_ROOT / "configs" / "ba_001_multi_asset_trend.toml")
        self.assertEqual(config.strategy.strategy_id, "BA-001")
        self.assertAlmostEqual(
            len(config.strategy.symbols) * config.strategy.sleeve_weight, 1.0
        )
        self.assertEqual(config.report.output_dir, REPO_ROOT / "experiments")

    def test_relative_paths_resolve_against_the_config_directory(self) -> None:
        config, path = _load(VALID)
        self.assertEqual(config.report.output_dir, path.resolve().parent / "out")

    def test_rejects_leveraged_sleeves(self) -> None:
        with self.assertRaisesRegex(ValueError, "exceed 100%"):
            _load(VALID.replace("sleeve_weight = 0.5", "sleeve_weight = 0.6"))

    def test_unknown_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown.*lookback_month\\b"):
            _load(VALID.replace("lookback_months = 12", "lookback_month = 12"))

    def test_unknown_table_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown.*exectuion"):
            _load(VALID.replace("[execution]", "[exectuion]"))

    def test_keys_for_the_other_data_source_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "prices_path.*synthetic"):
            _load(VALID.replace('source = "synthetic"', 'source = "synthetic"\nprices_path = "x.csv"'))

    def test_datetime_values_are_rejected_for_date_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "backtest.start must be an ISO date"):
            _load(VALID.replace('start = "2021-01-01"', "start = 2021-01-01T00:00:00"))

    def test_missing_required_key_is_reported_as_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "execution.cost_bps.*required"):
            _load(VALID.replace("cost_bps = 0\n", ""))


if __name__ == "__main__":
    unittest.main()


class ClusterValidationTests(unittest.TestCase):
    def _with_clusters(self, table: str):
        return _load(VALID + table)

    def test_a_bare_string_is_rejected_rather_than_split_into_letters(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a list of symbols"):
            self._with_clusters('\n[clusters]\ngrowth = "A"\n')

    def test_overlapping_clusters_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            self._with_clusters('\n[clusters]\none = ["A"]\ntwo = ["A", "B"]\n')

    def test_a_symbol_outside_the_universe_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the universe"):
            self._with_clusters('\n[clusters]\none = ["Z"]\n')

    def test_valid_clusters_are_normalised(self) -> None:
        config, _ = self._with_clusters('\n[clusters]\none = ["a"]\ntwo = ["b"]\n')
        self.assertEqual(config.clusters, {"one": ("A",), "two": ("B",)})


BENCHMARK = VALID + """
[benchmark]
exposure = 0.6
rebalance = "annual"
"""

BA001_SPEC_HASH = "595a25e57ed68d4e863eeb69b40248345840b809b0f213609ddd14b4cd952110"


ENSEMBLE = VALID.replace("lookback_months = 12", "lookback_months = 15\nhorizons = [9, 12, 15]")


class EnsembleConfigTests(unittest.TestCase):
    def test_defaults_are_absent_for_legacy_strategy(self):
        config, _ = _load(VALID)
        self.assertIsNone(config.strategy.horizons)
        self.assertIsNone(config.strategy.warmup_months)
        self.assertIsNone(config.research)

    def test_ensemble_defaults_common_warmup_to_fifteen(self):
        config, _ = _load(ENSEMBLE)
        self.assertEqual(config.strategy.horizons, (9, 12, 15))
        self.assertEqual(config.strategy.warmup_months, 15)

    def test_pair_keeps_common_warmup_and_rejects_inconsistent_lookback(self):
        config, _ = _load(ENSEMBLE.replace("[9, 12, 15]", "[9, 12]"))
        self.assertEqual(config.strategy.warmup_months, 15)
        with self.assertRaisesRegex(ValueError, "lookback_months.*warmup_months"):
            _load(ENSEMBLE.replace("lookback_months = 15", "lookback_months = 12"))

    def test_horizons_are_strict_positive_unique_integers(self):
        for bad in ("[]", "[9, 9]", "[0, 12]", "[-1, 12]", "[9.0, 12]", "[true, 12]", '["9", 12]', '"9,12"'):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "horizons"):
                _load(ENSEMBLE.replace("[9, 12, 15]", bad))

    def test_warmup_is_strict_and_at_least_maximum_horizon(self):
        for bad in ("true", "15.0", "0", "12"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "warmup_months"):
                _load(ENSEMBLE.replace("horizons =", f"warmup_months = {bad}\nhorizons ="))
        with self.assertRaisesRegex(ValueError, "warmup_months.*horizons"):
            _load(VALID.replace("lookback_months = 12", "lookback_months = 15\nwarmup_months = 15"))

    def test_longer_explicit_warmup_is_allowed_and_changes_spec(self):
        original, _ = _load(ENSEMBLE)
        longer, _ = _load(ENSEMBLE.replace("lookback_months = 15", "lookback_months = 18\nwarmup_months = 18"))
        self.assertEqual(longer.strategy.warmup_months, 18)
        self.assertNotEqual(original.strategy_spec_sha256, longer.strategy_spec_sha256)

    def test_active_horizons_change_spec_but_order_does_not(self):
        full, _ = _load(ENSEMBLE)
        pair, _ = _load(ENSEMBLE.replace("[9, 12, 15]", "[9, 12]"))
        reordered, _ = _load(ENSEMBLE.replace("[9, 12, 15]", "[15, 9, 12]"))
        self.assertNotEqual(full.strategy_spec_sha256, pair.strategy_spec_sha256)
        self.assertEqual(full.strategy_spec_sha256, reordered.strategy_spec_sha256)

    def test_research_paths_resolve_without_loading_external_files(self):
        text = ENSEMBLE + """
[research]
calendar_path = "research/calendar.json"
freeze_path = "research/freeze.json"
journal_path = "research/journal.json"
"""
        config, path = _load(text)
        for name in ("calendar", "freeze", "journal"):
            self.assertEqual(getattr(config.research, name + "_path"), (path.parent / "research" / (name + ".json")).resolve())
        missing = text.replace('journal_path = "research/journal.json"', "")
        with self.assertRaisesRegex(ValueError, "research.journal_path.*required"):
            _load(missing)

    def test_research_locations_do_not_impersonate_semantic_identity(self):
        text = ENSEMBLE + """
[research]
calendar_path = "two.json"
freeze_path = "three.json"
journal_path = "four.json"
"""
        original, _ = _load(ENSEMBLE)
        located, _ = _load(text)
        self.assertEqual(original.strategy_spec_sha256, located.strategy_spec_sha256)


class BenchmarkConfigTests(unittest.TestCase):
    def test_an_absent_table_means_no_override(self) -> None:
        config, _ = _load(VALID)
        self.assertIsNone(config.benchmark)

    def test_the_table_is_parsed(self) -> None:
        config, _ = _load(BENCHMARK)
        assert config.benchmark is not None
        self.assertAlmostEqual(config.benchmark.exposure, 0.6)
        self.assertEqual(config.benchmark.rebalance, "annual")

    def test_the_table_enters_the_spec_hash_only_when_present(self) -> None:
        without, _ = _load(VALID)
        annual, _ = _load(BENCHMARK)
        monthly, _ = _load(BENCHMARK.replace('"annual"', '"monthly"'))
        half, _ = _load(BENCHMARK.replace("0.6", "0.5"))
        hashes = {without.strategy_spec_sha256, annual.strategy_spec_sha256,
                  monthly.strategy_spec_sha256, half.strategy_spec_sha256}
        self.assertEqual(len(hashes), 4)

    def test_ba_001_development_spec_hash_is_unchanged(self) -> None:
        # The value recorded in both real BA-001 sweeps. Adding an optional table
        # must not move it, or the archived record would no longer describe the
        # checked-in configuration.
        config = load_config(REPO_ROOT / "configs" / "ba_001_development.toml")
        self.assertEqual(config.strategy_spec_sha256, BA001_SPEC_HASH)

    def test_exposure_outside_the_unit_interval_is_refused(self) -> None:
        for bad in ("0.0", "1.5", "-0.2"):
            with self.assertRaisesRegex(ValueError, "benchmark.exposure"):
                _load(BENCHMARK.replace("0.6", bad))

    def test_an_unknown_schedule_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "benchmark.rebalance"):
            _load(BENCHMARK.replace('"annual"', '"weekly"'))

    def test_an_incomplete_table_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "benchmark.rebalance is required"):
            _load(VALID + "\n[benchmark]\nexposure = 0.6\n")
        with self.assertRaisesRegex(ValueError, "benchmark.exposure is required"):
            _load(VALID + '\n[benchmark]\nrebalance = "annual"\n')

    def test_an_unknown_key_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown key"):
            _load(BENCHMARK + "band = 0.02\n")


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
