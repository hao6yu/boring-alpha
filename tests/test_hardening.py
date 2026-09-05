"""Guards added after review: exact evidence windows, verdict inputs, non-finite data."""

from datetime import date
from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import load_config
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar

PERIODS = """
[BA-001.development]
start = 2007-01-01
end = 2017-12-31

[BA-001.sealed]
start = 2022-01-01
end = "dataset"
"""

CONFIG = """
[strategy]
id = "BA-001"
name = "T"
symbols = ["A", "B"]
lookback_months = 12
sleeve_weight = 0.5
[portfolio]
initial_cash = 1000
[execution]
cost_bps = 10
[data]
source = "csv"
methodology = "test-v1"
prices_path = "../data/p.csv"
cash_path = "../data/c.csv"
[backtest]
start = "2007-01-01"
end = "2017-12-31"
[evaluation]
period = "development"
[report]
output_dir = "../experiments"
"""


def _load(config: str = CONFIG):
    root = Path(tempfile.mkdtemp())
    (root / "configs").mkdir()
    (root / "configs" / "evaluation_periods.toml").write_text(PERIODS, encoding="utf-8")
    path = root / "configs" / "run.toml"
    path.write_text(config, encoding="utf-8")
    return load_config(path)


class ExactWindowTests(unittest.TestCase):
    """An evidence period must be run whole, or it is not that period."""

    def test_the_registered_window_is_accepted(self) -> None:
        self.assertEqual(_load().backtest.start, date(2007, 1, 1))

    def test_a_late_start_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "must start on the development period start"):
            _load(CONFIG.replace('start = "2007-01-01"', 'start = "2017-01-01"'))

    def test_an_early_end_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "must cover the development period exactly"):
            _load(CONFIG.replace('end = "2017-12-31"', 'end = "2016-12-31"'))

    def test_a_dataset_ended_period_fixes_only_its_start(self) -> None:
        sealed = (
            CONFIG.replace('period = "development"', 'period = "sealed"')
            .replace('start = "2007-01-01"\nend = "2017-12-31"', 'start = "2022-01-01"\nend = "2024-06-30"')
        )
        self.assertIsNone(_load(sealed).evaluation.end)

    def test_a_dataset_ended_period_still_fixes_its_start(self) -> None:
        sealed = (
            CONFIG.replace('period = "development"', 'period = "sealed"')
            .replace('start = "2007-01-01"\nend = "2017-12-31"', 'start = "2023-01-01"\nend = "2024-06-30"')
        )
        with self.assertRaisesRegex(ValueError, "must start on the sealed period"):
            _load(sealed)

    def test_exploratory_windows_stay_unconstrained(self) -> None:
        loose = CONFIG.replace('period = "development"', 'period = "exploratory"').replace(
            'start = "2007-01-01"', 'start = "2011-03-01"'
        )
        self.assertEqual(_load(loose).backtest.start, date(2011, 3, 1))


class StrategySpecHashTests(unittest.TestCase):
    """Two runs are comparable only if the strategy they ran is identical."""

    def test_the_same_strategy_hashes_the_same_under_a_different_window(self) -> None:
        # Development and validation differ in window and nothing else, so the
        # spec hash must ignore it. Comparing a config with itself, as an earlier
        # version of this test did, proves nothing.
        sealed = (
            CONFIG.replace('period = "development"', 'period = "sealed"')
            .replace('start = "2007-01-01"\nend = "2017-12-31"', 'start = "2022-01-01"\nend = "2025-06-30"')
        )
        development, other = _load(), _load(sealed)
        self.assertNotEqual(development.backtest.start, other.backtest.start)
        self.assertEqual(development.strategy_spec_sha256, other.strategy_spec_sha256)

    def test_symbol_order_does_not_change_the_hash(self) -> None:
        reordered = CONFIG.replace('symbols = ["A", "B"]', 'symbols = ["B", "A"]')
        self.assertEqual(_load().strategy_spec_sha256, _load(reordered).strategy_spec_sha256)

    def test_a_different_universe_changes_the_hash(self) -> None:
        other = CONFIG.replace('symbols = ["A", "B"]', 'symbols = ["A", "C"]')
        self.assertNotEqual(_load().strategy_spec_sha256, _load(other).strategy_spec_sha256)

    def test_a_different_sleeve_weight_changes_the_hash(self) -> None:
        other = CONFIG.replace("sleeve_weight = 0.5", "sleeve_weight = 0.25")
        self.assertNotEqual(_load().strategy_spec_sha256, _load(other).strategy_spec_sha256)

    def test_different_initial_capital_changes_the_hash(self) -> None:
        other = CONFIG.replace("initial_cash = 1000", "initial_cash = 500000")
        self.assertNotEqual(_load().strategy_spec_sha256, _load(other).strategy_spec_sha256)

    def test_a_different_cost_assumption_changes_the_hash(self) -> None:
        other = CONFIG.replace("cost_bps = 10", "cost_bps = 25")
        self.assertNotEqual(_load().strategy_spec_sha256, _load(other).strategy_spec_sha256)


class NonFiniteTests(unittest.TestCase):
    """NaN passes a `<= 0` guard, so it needs its own."""

    DAY = date(2025, 1, 2)

    def _market(self, bar: PriceBar, factor: float) -> None:
        MarketData([bar], {self.DAY: factor}, source="t")

    def test_a_nan_price_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a finite number"):
            self._market(PriceBar(self.DAY, "A", float("nan"), 1.0), 1.0)

    def test_an_infinite_price_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a finite number"):
            self._market(PriceBar(self.DAY, "A", 1.0, float("inf")), 1.0)

    def test_a_nan_cash_factor_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a finite number"):
            self._market(PriceBar(self.DAY, "A", 1.0, 1.0), float("nan"))

    def test_an_infinite_cash_factor_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a finite number"):
            self._market(PriceBar(self.DAY, "A", 1.0, 1.0), float("inf"))

    def test_a_non_finite_configuration_number_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            _load(CONFIG.replace("cost_bps = 10", "cost_bps = nan"))


if __name__ == "__main__":
    unittest.main()


class ContributionRankingTests(unittest.TestCase):
    """C5 removes the largest contributor, so the two definitions must be told apart.

    The charter ranks by share of excess return over cash. Raw profit disagrees
    whenever holding periods differ: a sleeve deployed continuously at barely
    above the cash rate earns a large raw number while contributing almost
    nothing the portfolio could not have had by sitting in cash. A fixture where
    both definitions pick the same sleeve cannot catch a regression to raw
    profit, which is what C5 gated on before review.
    """

    def _staged_run(self):
        from dataclasses import replace as _replace
        from datetime import timedelta
        from boring_alpha.backtest.engine import Backtester
        from boring_alpha.data.market import MarketData
        from boring_alpha.domain import PriceBar, SignalSnapshot

        factor = 1.05 ** (1 / 252)          # a 5% annual cash rate
        days, day = [], date(2023, 12, 1)
        while len(days) < 320:
            if day.weekday() < 5:
                days.append(day)
            day += timedelta(days=1)
        # The weight turns on well before the price moves, so the position is
        # actually established in time to capture it. Signalling and jumping on
        # the same day would mean buying after the move.
        switch = days[-70]
        jump = days[-20]

        bars = []
        for index, session in enumerate(days):
            plodder = 100.0 * (1.052 ** (index / 252))     # grinds just above cash
            sprinter = 100.0 if session < jump else 103.0   # flat, then brief and sharp
            bars.append(PriceBar(session, "PLODDER", plodder, plodder))
            bars.append(PriceBar(session, "SPRINTER", sprinter, sprinter))
        data = MarketData(bars, {s: factor for s in days}, source="test")

        class Staged:
            """PLODDER is held throughout; SPRINTER only at the end."""

            name = "staged"

            def snapshot(self, market, as_of):
                return SignalSnapshot(
                    as_of=as_of,
                    target_weights={
                        "PLODDER": 0.5,
                        "SPRINTER": 0.5 if as_of >= switch else 0.0,
                    },
                    asset_returns={},
                    cash_return=0.0,
                    name=self.name,
                )

        return Backtester(
            data, ("PLODDER", "SPRINTER"), initial_cash=100_000.0, cost_bps=0.0,
            start=days[0], end=days[-1],
        ).run(Staged())

    def test_raw_profit_and_excess_over_cash_pick_different_sleeves(self) -> None:
        result = self._staged_run()
        raw_top = max(result.contributions, key=result.contributions.get)
        excess_top = max(result.excess_contributions, key=result.excess_contributions.get)
        self.assertEqual(raw_top, "PLODDER", result.contributions)
        self.assertEqual(excess_top, "SPRINTER", result.excess_contributions)

    def test_the_charter_s_definition_charges_parked_capital_for_forgone_cash(self) -> None:
        result = self._staged_run()
        # PLODDER sat invested all period, so almost all of its profit was cash
        # the portfolio would have earned anyway: it keeps under a tenth of its
        # raw number. SPRINTER was deployed briefly and keeps most of its own.
        plodder_kept = result.excess_contributions["PLODDER"] / result.contributions["PLODDER"]
        sprinter_kept = result.excess_contributions["SPRINTER"] / result.contributions["SPRINTER"]
        self.assertLess(plodder_kept, 0.10, result.contributions)
        self.assertGreater(sprinter_kept, 0.50, result.contributions)


class SweepRanksOnTheCharterDefinitionTests(unittest.TestCase):
    """The sweep itself must pick C5's sleeve by excess over cash, not raw profit.

    Proving the two definitions differ is not enough: the earlier bug was that
    `run_sweep` consulted the wrong one. This fixture makes them disagree by a
    wide margin and pins which one the sweep actually uses.
    """

    CASH_PCT, PLODDER_PCT = 5.0, 6.5
    SPRINT_FROM, SPRINT_PCT = date(2023, 1, 3), 18.0

    def _build(self, root: Path) -> Path:
        from datetime import timedelta

        (root / "configs").mkdir()
        (root / "data").mkdir()
        days, day = [], date(2019, 1, 1)
        while day <= date(2023, 12, 29):
            if day.weekday() < 5:
                days.append(day)
            day += timedelta(days=1)

        factor = (1.0 + self.CASH_PCT / 100.0) ** (1 / 252)
        jump = days.index(self.SPRINT_FROM)
        prices = ["date,symbol,tr_open,tr_close"]
        cash = ["date,cash_factor"]
        for index, session in enumerate(days):
            cash.append(f"{session},{factor:.12f}")
            # PLODDER beats cash by a hair for five years: always held, so nearly
            # all of its large raw profit is cash it would have earned anyway.
            plodder = 100.0 * ((1.0 + self.PLODDER_PCT / 100.0) ** (index / 252))
            # SPRINTER is flat until its trailing return can clear cash, then
            # rises hard: held under a year, so it keeps most of what it makes.
            sprinter = (
                100.0
                if index < jump
                else 100.0 * ((1.0 + self.SPRINT_PCT / 100.0) ** ((index - jump) / 252))
            )
            prices.append(f"{session},PLODDER,{plodder:.6f},{plodder:.6f}")
            prices.append(f"{session},SPRINTER,{sprinter:.6f},{sprinter:.6f}")

        (root / "data" / "p.csv").write_text("\n".join(prices) + "\n", encoding="utf-8")
        (root / "data" / "c.csv").write_text("\n".join(cash) + "\n", encoding="utf-8")
        (root / "configs" / "evaluation_periods.toml").write_text(
            "[BA-001.development]\nstart = 2021-01-01\nend = 2023-12-31\n", encoding="utf-8"
        )
        path = root / "configs" / "run.toml"
        path.write_text(
            '\n[strategy]\nid = "BA-001"\nname = "Ranking"\n'
            'symbols = ["PLODDER", "SPRINTER"]\nlookback_months = 12\nsleeve_weight = 0.5\n'
            "[portfolio]\ninitial_cash = 100000\n[execution]\ncost_bps = 10\n"
            '[data]\nsource = "csv"\nmethodology = "test-v1"\n'
            'prices_path = "../data/p.csv"\ncash_path = "../data/c.csv"\n'
            '[backtest]\nstart = "2021-01-01"\nend = "2023-12-31"\n'
            '[evaluation]\nperiod = "development"\n'
            '[report]\noutput_dir = "../experiments"\n',
            encoding="utf-8",
        )
        return path

    def _sweep(self):
        from boring_alpha.data import load_market_data
        from boring_alpha.sweep import run_sweep

        root = Path(tempfile.mkdtemp())
        config = load_config(self._build(root))
        # This hand-crafted CSV is a tax/ranking fixture, not a historical
        # invocation. Isolate its regression from the separately tested access
        # gate without changing its deliberately discriminating prices/dates.
        from unittest.mock import patch
        from boring_alpha.research_access import RunContext, capture_execution_identity
        context = RunContext(None, capture_execution_identity())
        with patch("boring_alpha.research_access.prepare_run", return_value=context):
            return run_sweep(config, load_market_data(config))

    def test_the_fixture_makes_the_two_rankings_disagree(self) -> None:
        sweep = self._sweep()
        raw_top = max(sweep.contributions, key=sweep.contributions.get)
        excess_top = max(sweep.excess_contributions, key=sweep.excess_contributions.get)
        self.assertEqual(raw_top, "PLODDER", sweep.contributions)
        self.assertEqual(excess_top, "SPRINTER", sweep.excess_contributions)

    def test_c5_removes_the_sleeve_the_charter_names(self) -> None:
        # Ranking on raw profit would drop PLODDER here. The charter defines
        # contribution as share of excess return over cash, which is SPRINTER.
        self.assertEqual(self._sweep().top_sleeve, "SPRINTER")


class SweepEvidenceTests(SweepRanksOnTheCharterDefinitionTests):
    """Principle 6 asks for decisions, trades and curves — not only aggregates."""

    def _written(self):
        from boring_alpha.data import load_market_data
        from boring_alpha.sweep import GRID, run_sweep, write_sweep_report

        root = Path(tempfile.mkdtemp())
        config = load_config(self._build(root))
        # Same fictional CSV fixture as _sweep; access policy has independent
        # end-to-end refusal tests in test_research_access.
        from unittest.mock import patch
        from boring_alpha.research_access import RunContext, capture_execution_identity
        context = RunContext(None, capture_execution_identity())
        with patch("boring_alpha.research_access.prepare_run", return_value=context):
            data = load_market_data(config)
        sweep = run_sweep(config, data)
        _, sweep_dir = write_sweep_report(config, data, sweep)
        return sweep_dir, GRID, data

    def test_every_variant_keeps_its_own_evidence(self) -> None:
        sweep_dir, grid, _ = self._written()
        for name in grid:
            for artifact in (
                "strategy_equity.csv", "strategy_trades.csv",
                "strategy_decisions.json", "benchmark_equity.csv",
            ):
                self.assertTrue(
                    (sweep_dir / "variants" / name / artifact).is_file(),
                    f"missing variants/{name}/{artifact}",
                )

    def test_the_dataset_the_sweep_saw_is_preserved_and_reloadable(self) -> None:
        import gzip
        from boring_alpha.data.csv_loader import load_csv_market_data

        sweep_dir, _, data = self._written()
        root = Path(tempfile.mkdtemp())
        for name in ("prices", "cash"):
            raw = gzip.decompress((sweep_dir / f"input_{name}.csv.gz").read_bytes())
            (root / f"{name}.csv").write_bytes(raw)
        restored = load_csv_market_data(root / "prices.csv", root / "cash.csv")
        # A hash proves the inputs changed; this proves the old run can be rebuilt.
        self.assertEqual(restored.fingerprint(), data.fingerprint())


class MethodologyIdentityTests(unittest.TestCase):
    """Two CSV datasets built differently are not the same strategy input."""

    def test_csv_data_must_declare_its_methodology(self) -> None:
        with self.assertRaisesRegex(ValueError, "data.methodology is required"):
            _load(CONFIG.replace('source = "csv"\n', 'source = "csv"\n', 1).replace(
                'methodology = "test-v1"\n', ""
            ))

    def test_a_different_methodology_changes_the_spec_hash(self) -> None:
        other = CONFIG.replace('methodology = "test-v1"', 'methodology = "test-v2"')
        self.assertNotEqual(_load().strategy_spec_sha256, _load(other).strategy_spec_sha256)


class QualityOverrideTests(unittest.TestCase):
    """A NaN threshold silently disables its check, because NaN fails every
    ordered comparison. That is worse than no override at all."""

    def test_a_non_finite_threshold_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            _load(CONFIG + "\n[quality]\nmax_session_return = nan\n")

    def test_a_non_positive_magnitude_threshold_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be positive"):
            _load(CONFIG + "\n[quality]\nmax_open_gap = 0.0\n")

    def test_a_negative_cash_floor_is_allowed(self) -> None:
        config = _load(CONFIG + "\n[quality]\nmin_cash_rate = -0.25\n")
        self.assertEqual(config.quality_overrides["min_cash_rate"], -0.25)


class DatasetEndedRunTests(unittest.TestCase):
    """"Through the latest complete dataset" must mean exactly that."""

    def _run_dir(self, backtest_end: str) -> Path:
        from datetime import timedelta

        root = Path(tempfile.mkdtemp())
        (root / "configs").mkdir()
        (root / "data").mkdir()
        days, day = [], date(2021, 1, 1)
        while day <= date(2024, 6, 28):
            if day.weekday() < 5:
                days.append(day)
            day += timedelta(days=1)
        prices = ["date,symbol,tr_open,tr_close"] + [
            f"{d},{s},100.0,100.0" for d in days for s in ("A", "B")
        ]
        cash = ["date,cash_factor"] + [f"{d},1.00002" for d in days]
        (root / "data" / "p.csv").write_text("\n".join(prices) + "\n", encoding="utf-8")
        (root / "data" / "c.csv").write_text("\n".join(cash) + "\n", encoding="utf-8")
        (root / "configs" / "evaluation_periods.toml").write_text(
            '[BA-001.sealed]\nstart = 2022-01-01\nend = "dataset"\n', encoding="utf-8"
        )
        path = root / "configs" / "run.toml"
        path.write_text(
            '\n[strategy]\nid = "BA-001"\nname = "D"\nsymbols = ["A", "B"]\n'
            "lookback_months = 12\nsleeve_weight = 0.5\n"
            "[portfolio]\ninitial_cash = 1000\n[execution]\ncost_bps = 10\n"
            '[data]\nsource = "csv"\nmethodology = "test-v1"\n'
            'prices_path = "../data/p.csv"\ncash_path = "../data/c.csv"\n'
            f'[backtest]\nstart = "2022-01-01"\nend = "{backtest_end}"\n'
            '[evaluation]\nperiod = "sealed"\n'
            '[report]\noutput_dir = "../experiments"\n',
            encoding="utf-8",
        )
        return path

    def test_stopping_short_of_the_data_is_refused(self) -> None:
        from boring_alpha.data import load_market_data

        path = self._run_dir("2023-12-29")
        reviews = path.parent.parent / "docs" / "reviews"
        reviews.mkdir(parents=True)
        for stage in ("development", "validation"):
            (reviews / f"BA-001-{stage}.md").write_text("reviewed", encoding="utf-8")
        config = load_config(path)
        # Isolate the legacy dataset-ended invariant. Actual family access and
        # --unseal refusal are tested without mocks in test_research_access.
        from unittest.mock import patch
        from boring_alpha.research_access import RunContext, capture_execution_identity
        context = RunContext(None, capture_execution_identity())
        with patch("boring_alpha.research_access.prepare_run", return_value=context):
            with self.assertRaisesRegex(ValueError, "must extend through the latest complete session"):
                load_market_data(config, "reviewed")

    def test_running_through_the_last_session_is_accepted(self) -> None:
        from boring_alpha.data import load_market_data

        path = self._run_dir("2024-06-28")
        reviews = path.parent.parent / "docs" / "reviews"
        reviews.mkdir(parents=True)
        for stage in ("development", "validation"):
            (reviews / f"BA-001-{stage}.md").write_text("reviewed", encoding="utf-8")
        config = load_config(path)
        from unittest.mock import patch
        from boring_alpha.research_access import RunContext, capture_execution_identity
        context = RunContext(None, capture_execution_identity())
        with patch("boring_alpha.research_access.prepare_run", return_value=context):
            data = load_market_data(config, "reviewed")
        self.assertEqual(data.dates[-1], date(2024, 6, 28))


class MethodologyManifestTests(unittest.TestCase):
    """A declared methodology that disagrees with the snapshot is a mismatch,
    not a formality. Requiring the string without checking it only proves
    someone typed something."""

    def _snapshot(self, manifest_methodology: str | None, declared: str) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "configs").mkdir()
        snapshot = root / "data" / "current"
        snapshot.mkdir(parents=True)
        days = ["2021-01-04", "2021-01-05"]
        (snapshot / "p.csv").write_text(
            "date,symbol,tr_open,tr_close\n"
            + "".join(f"{d},{s},100.0,100.0\n" for d in days for s in ("A", "B")),
            encoding="utf-8",
        )
        (snapshot / "c.csv").write_text(
            "date,cash_factor\n" + "".join(f"{d},1.00002\n" for d in days), encoding="utf-8"
        )
        if manifest_methodology is not None:
            (snapshot / "manifest.json").write_text(
                f'{{"methodology": "{manifest_methodology}"}}', encoding="utf-8"
            )
        path = root / "configs" / "run.toml"
        path.write_text(
            '\n[strategy]\nid = "BA-001"\nname = "M"\nsymbols = ["A", "B"]\n'
            "lookback_months = 12\nsleeve_weight = 0.5\n"
            "[portfolio]\ninitial_cash = 1000\n[execution]\ncost_bps = 10\n"
            f'[data]\nsource = "csv"\nmethodology = "{declared}"\n'
            'prices_path = "../data/current/p.csv"\ncash_path = "../data/current/c.csv"\n'
            '[backtest]\nstart = "2021-01-01"\nend = "2021-01-31"\n'
            '[evaluation]\nperiod = "development"\n'
            '[report]\noutput_dir = "../experiments"\n',
            encoding="utf-8",
        )
        (path.parent / "evaluation_periods.toml").write_text(
            "[BA-001.development]\nstart = 2021-01-01\nend = 2021-01-31\n", encoding="utf-8"
        )
        return path

    def test_a_mismatched_methodology_is_refused(self) -> None:
        from boring_alpha.data import load_market_data

        config = load_config(self._snapshot("yahoo-adjusted-v2+dgs3mo-v1", "yahoo-adjusted-v1+dgs3mo-v1"))
        with self.assertRaisesRegex(ValueError, "methodology"):
            load_market_data(config)

    def test_a_matching_methodology_loads(self) -> None:
        from boring_alpha.data import load_market_data

        config = load_config(self._snapshot("yahoo-adjusted-v1+dgs3mo-v1", "yahoo-adjusted-v1+dgs3mo-v1"))
        self.assertEqual(len(load_market_data(config).dates), 2)

    def test_data_outside_a_snapshot_is_allowed_but_unverified(self) -> None:
        from boring_alpha.data import load_market_data

        # Hand-built CSVs have no manifest to check against; that is not an error,
        # but the run records that the claim went unverified.
        config = load_config(self._snapshot(None, "hand-built-v1"))
        data = load_market_data(config)
        self.assertTrue(any("unverified" in w for w in data.warnings), data.warnings)
