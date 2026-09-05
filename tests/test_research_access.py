"""Explicit run lifecycle tests use temporary fictional inputs, never history."""

import csv
import io
from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from boring_alpha.config import ResearchConfig, _strategy_spec_hash, load_config
from boring_alpha.data.calendar import SessionCalendar
from boring_alpha.data.distributions import load_distributions
from boring_alpha.data.loader import load_market_data
from boring_alpha.demo import prepare_ba002_demo
from boring_alpha.research_access import (
    ResearchContext, RunContext, capture_inputs, open_run, prepare_run,
    research_context, validate_ba002_inputs,
)
from boring_alpha.research_freeze import build_freeze, confirm_freeze, freeze_sha256, load_freeze

BASELINE = ("a" * 64, "b" * 64)


def rehash(config):
    return replace(config, strategy_spec_sha256=_strategy_spec_hash(
        config.strategy, config.portfolio, config.execution, config.data, config.benchmark,
    ))


class ResearchContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.journal = self.root / "journal.json"
        patch("boring_alpha.research_family.canonical_journal_path", return_value=self.journal).start()
        self.paths = prepare_ba002_demo(self.root)
        self.config = load_config(self.paths["development"])
        self.addCleanup(patch.stopall)
        patch("boring_alpha.research_access.capture_execution_identity", return_value=BASELINE).start()

    def test_synthetic_uses_draft_and_never_reads_or_initializes_a_journal(self):
        original = Path.read_text
        forbidden = self.journal
        def guarded(path, *args, **kwargs):
            if path == forbidden:
                raise AssertionError("historical journal was read")
            return original(path, *args, **kwargs)
        with patch("boring_alpha.research_family.canonical_journal_path", side_effect=AssertionError("journal located")), patch.object(Path, "read_text", guarded), patch(
            "boring_alpha.research_state.RunJournal", side_effect=AssertionError("journal instantiated")
        ):
            selected = research_context(self.config)
            self.assertEqual(selected.freeze["status"], "draft")
            self.assertIsNone(selected.approved_contract)
            with open_run(self.config) as run:
                self.assertIsNone(run.context.attempt)
                self.assertEqual(run.data.dates[-1], date(2018, 12, 31))
                self.assertFalse(any(name.startswith("_research") for name in vars(run.data)))
        self.assertFalse(forbidden.exists())

    def test_config_rule_benchmark_cost_and_capital_must_match_contract(self):
        cases = [
            replace(self.config, strategy=replace(self.config.strategy, horizons=(9, 12))),
            replace(self.config, strategy=replace(self.config.strategy, warmup_months=18)),
            replace(self.config, execution=replace(self.config.execution, cost_bps=20)),
            replace(self.config, portfolio=replace(self.config.portfolio, initial_cash=5000)),
            replace(self.config, benchmark=replace(self.config.benchmark, rebalance="monthly")),
            replace(self.config, tax=replace(self.config.tax, ordinary_rate=0.24)),
        ]
        for config in cases:
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, "contract"):
                research_context(config)

    def _proposed_historical_fixture(self):
        # Generated demo values only. False metadata exercises managed CSV
        # in an isolated temporary directory; it is not actual market data.
        calendar_path = self.config.research.calendar_path
        calendar_record = json.loads(calendar_path.read_text())
        calendar_record["synthetic"] = False
        calendar = SessionCalendar.from_dict(calendar_record)
        calendar_path.write_text(json.dumps(calendar_record))
        contract = load_freeze(self.config.research.freeze_path)["identity"]["contract"]
        contract.update(synthetic=False, data_methodology="yahoo-adjusted-v2+dgs3mo-v1",
                        calendar_sha256=calendar.sha256, calendar_authority_sha256=calendar.authority_sha256)
        contract["periods"]["sealed"] = {"start": "2022-01-01", "end": "2023-12-31", "status": "unopened"}
        prices, cash = self.root / "data/prices.csv", self.root / "data/cash.csv"
        with self.config.tax.distributions_path.open() as stream:
            rows = list(csv.DictReader(stream))
        prices.write_text("date,symbol,tr_open,tr_close\n" + "".join(
            f"{row['date']},{row['symbol']},{row['close']},{row['close']}\n" for row in rows
        ))
        cash.write_text("date,cash_factor\n" + "".join(f"{day},1\n" for day in sorted({row["date"] for row in rows})))
        manifest = self.config.tax.distributions_path.parent / "manifest.json"
        manifest.write_text(json.dumps({"methodology": contract["data_methodology"],
                                        "synthetic": False, "splits": {symbol: [] for symbol in self.config.strategy.symbols}}))
        config = rehash(replace(self.config, data=replace(
            self.config.data, source="csv", methodology=contract["data_methodology"], prices_path=prices, cash_path=cash,
        )))
        record = build_freeze(config, contract, input_manifest_sha256=capture_inputs(config).sha256,
                              charter_text="Fictional CSV workflow test, not a historical authorization",
                              code_sha256=BASELINE[0], evaluator_sha256=BASELINE[1])
        config.research.freeze_path.write_text(json.dumps(record))
        return config, record

    def _confirm(self, config, record):
        return confirm_freeze(config.research.freeze_path, expected_sha256=freeze_sha256(record),
                              reason="Temporary fictional workflow test only")

    def test_csv_cannot_use_a_synthetic_freeze_or_calendar(self):
        config = replace(self.config, data=replace(self.config.data, source="csv"))
        record = load_freeze(config.research.freeze_path)
        self._confirm(config, record)
        with patch("boring_alpha.research_access.capture_inputs", side_effect=AssertionError("prices read")):
            with self.assertRaisesRegex(ValueError, "synthetic.*historical"):
                prepare_run(config)

    def test_historical_draft_refuses_before_input_capture_or_journal_creation(self):
        config, _ = self._proposed_historical_fixture()
        with patch("boring_alpha.research_access.capture_inputs", side_effect=AssertionError("prices read")):
            with self.assertRaisesRegex(ValueError, "confirmed"):
                prepare_run(config)
        self.assertFalse(self.journal.exists())

    def test_confirmed_freeze_cannot_claim_a_different_calendar(self):
        config, record = self._proposed_historical_fixture()
        record["identity"]["contract"]["calendar_sha256"] = "0" * 64
        config.research.freeze_path.write_text(json.dumps(record))
        self._confirm(config, record)
        with self.assertRaisesRegex(ValueError, "calendar_sha256.*contract"):
            research_context(config)

    def test_execution_does_not_silently_initialize_a_missing_journal(self):
        config, record = self._proposed_historical_fixture()
        self._confirm(config, record)
        self.journal.unlink()  # Only this temporary empty test journal.
        with self.assertRaisesRegex(ValueError, "existing regular"):
            with open_run(config):
                self.fail("unlogged run entered")
        self.assertFalse(self.journal.exists())

    def test_one_confirmed_freeze_covers_both_seen_windows_without_extra_approvals(self):
        config, record = self._proposed_historical_fixture()
        self._confirm(config, record)
        frozen_bytes = config.research.freeze_path.read_bytes()
        validation = replace(config,
            backtest=replace(config.backtest, start=date(2019, 1, 1), end=date(2019, 12, 31)),
            evaluation=replace(config.evaluation, period="validation", start=date(2019, 1, 1), end=date(2019, 12, 31)),
        )
        for current in (config, validation, config):
            with open_run(current) as run:
                self.assertFalse(any(name.startswith("_research") for name in vars(run.data)))
                run.context.artifact_path = f"fictional-{current.evaluation.period}-artifact"
        self.assertEqual(config.research.freeze_path.read_bytes(), frozen_bytes)
        events = json.loads(self.journal.read_text())["events"]
        self.assertEqual([event["event"] for event in events], ["attempted", "access_started", "completed"] * 3)
        self.assertTrue(all(event["reveal_reason"] is None for event in events if event["event"] == "attempted"))
        self.assertEqual(set(json.loads(self.journal.read_text())), {"schema_version", "events"})

    def test_managed_csv_requires_explicit_context_instead_of_private_dataset_state(self):
        config, record = self._proposed_historical_fixture()
        self._confirm(config, record)
        with patch("boring_alpha.data.loader._load_market_data", side_effect=AssertionError("unmanaged parse")):
            with self.assertRaisesRegex(ValueError, "open_run"):
                load_market_data(config)

    def test_complete_inputs_use_independent_calendar_and_missing_session_fails(self):
        with open_run(self.config) as run:
            data = run.data
            distributions = load_distributions(self.config.tax.distributions_path,
                manifest_path=self.config.tax.distributions_path.parent / "manifest.json", end=self.config.backtest.end)
            selected = validate_ba002_inputs(self.config, data, distributions, run.context)
            self.assertTrue(selected.calendar.synthetic)
            removed = date(2018, 1, 2)
            data.by_date.pop(removed)
            data.dates = tuple(day for day in data.dates if day != removed)
            data.cash_factors.pop(removed)
            distributions.symbol_dates = {symbol: tuple(day for day in days if day != removed)
                                          for symbol, days in distributions.symbol_dates.items()}
            with self.assertRaisesRegex(ValueError, "calendar coverage mismatch"):
                validate_ba002_inputs(self.config, data, distributions, run.context)


CSV_CONFIG = """
[strategy]
id = "BA-001"
name = "Fictional bounded access fixture"
symbols = ["A"]
lookback_months = 12
sleeve_weight = 1.0
[portfolio]
initial_cash = 1000
[execution]
cost_bps = 10
[data]
source = "csv"
methodology = "fictional-v1"
prices_path = "prices.csv"
cash_path = "cash.csv"
[backtest]
start = 2021-01-01
end = 2021-01-31
[evaluation]
period = "development"
[report]
output_dir = "out"
"""


class LoaderAccessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(patch.stopall)
        patch("boring_alpha.research_access.capture_execution_identity", return_value=BASELINE).start()
        self.root = Path(self.temporary.name)
        self.journal = self.root / "journal.json"
        patch("boring_alpha.research_family.canonical_journal_path", return_value=self.journal).start()
        (self.root / "evaluation_periods.toml").write_text("[BA-001.development]\nstart = 2021-01-01\nend = 2021-01-31\n")
        path = self.root / "config.toml"
        path.write_text(CSV_CONFIG)
        (self.root / "prices.csv").write_text("date,symbol,tr_open,tr_close\n2021-01-04,A,100,100\n2022-01-03,A,PROTECTED,PROTECTED\n")
        (self.root / "cash.csv").write_text("date,cash_factor\n2021-01-04,1\n2022-01-03,PROTECTED\n")
        self.config = load_config(path)

    def test_unknown_profile_is_refused_before_any_price_input(self):
        config = replace(self.config, strategy=replace(self.config.strategy, strategy_id="RENAMED"))
        with patch("boring_alpha.data.loader.load_csv_market_data", side_effect=AssertionError("prices read")):
            with self.assertRaisesRegex(ValueError, "profile"):
                load_market_data(config)

    def test_seen_bounded_csv_filters_before_numeric_parsing_and_returns_only_data(self):
        from boring_alpha.data.csv_loader import load_csv_market_data
        with patch("boring_alpha.data.loader.load_csv_market_data", wraps=load_csv_market_data) as reader:
            data = load_market_data(self.config)
        self.assertEqual(data.dates, (date(2021, 1, 4),))
        self.assertEqual(reader.call_args.kwargs, {"end": date(2021, 1, 31)})
        self.assertFalse(any(name.startswith("_research") for name in vars(data)))

    def test_protected_exploratory_alias_requires_a_freeze_before_parsing(self):
        config = replace(self.config, backtest=replace(self.config.backtest, end=date(2022, 1, 31)),
                         evaluation=replace(self.config.evaluation, period="exploratory", start=None, end=None))
        with patch("boring_alpha.data.loader.load_csv_market_data", side_effect=AssertionError("prices read")):
            with self.assertRaisesRegex(ValueError, "freeze"):
                load_market_data(config)

    def test_legacy_unseal_reason_does_not_replace_a_family_freeze(self):
        config = replace(self.config,
            backtest=replace(self.config.backtest, start=date(2022, 1, 1), end=date(2022, 1, 31)),
            evaluation=replace(self.config.evaluation, period="sealed", start=date(2022, 1, 1), end=date(2022, 1, 31)))
        with patch("boring_alpha.evaluation.check_legacy_review_gates"), patch(
            "boring_alpha.data.loader.load_csv_market_data", side_effect=AssertionError("prices read")
        ):
            with self.assertRaisesRegex(ValueError, "freeze"):
                load_market_data(config, "this sentence is not a freeze")

    def _mock_run(self, attempt):
        return patch("boring_alpha.research_access.prepare_run", return_value=RunContext(None, BASELINE, attempt=attempt))

    def test_access_start_precedes_csv_read_and_loading_failure_is_recorded(self):
        attempt = Mock()
        def refuse(*args, **kwargs):
            attempt.start_access.assert_called_once_with()
            raise ValueError("fictional loading failure")
        with self._mock_run(attempt), patch("boring_alpha.data.loader.load_csv_market_data", side_effect=refuse):
            with self.assertRaisesRegex(ValueError, "fictional loading failure"):
                with open_run(self.config):
                    self.fail("failed loading yielded a run")
        attempt.fail.assert_called_once_with("fictional loading failure")

    def test_attempt_location_and_id_are_flushed_before_access_can_fail(self):
        attempt = Mock()
        attempt.journal.path = self.journal
        attempt.attempt_id = "fictional-attempt-id"
        output = io.StringIO()
        flushed = Mock(wraps=output.flush)
        output.flush = flushed
        def refused():
            self.assertIn(f"Research journal: {self.journal}", output.getvalue())
            self.assertIn("Attempt ID: fictional-attempt-id", output.getvalue())
            flushed.assert_called_once_with()
            raise ValueError("fictional access refusal")
        attempt.start_access.side_effect = refused
        with self._mock_run(attempt), patch("sys.stdout", output), patch(
            "boring_alpha.data.loader.load_market_data", side_effect=AssertionError("parsed before refusal")
        ), self.assertRaisesRegex(ValueError, "access refusal"):
            with open_run(self.config):
                self.fail("refused run yielded")
        attempt.fail.assert_called_once_with("fictional access refusal")

    def test_successful_loading_keeps_attempt_open_until_context_publication(self):
        attempt = Mock()
        with self._mock_run(attempt):
            with open_run(self.config) as run:
                attempt.complete.assert_not_called()
                run.context.artifact_path = "fictional-artifact"
        attempt.complete.assert_called_once_with("fictional-artifact")
        self.assertIsNone(run.context.attempt)

    def test_downstream_failure_is_recorded_automatically(self):
        attempt = Mock()
        with self._mock_run(attempt), self.assertRaisesRegex(ValueError, "overlay failure"):
            with open_run(self.config):
                raise ValueError("fictional overlay failure")
        attempt.fail.assert_called_once_with("fictional overlay failure")
        attempt.complete.assert_not_called()

    def test_finishing_without_an_artifact_is_failure_not_completion(self):
        attempt = Mock()
        with self._mock_run(attempt):
            with open_run(self.config):
                pass
        attempt.complete.assert_not_called()
        attempt.fail.assert_called_once_with("run ended without a completed artifact")

    def test_keyboard_interrupt_records_failure_before_propagating(self):
        attempt = Mock()
        with self._mock_run(attempt), self.assertRaises(KeyboardInterrupt):
            with open_run(self.config):
                raise KeyboardInterrupt("fictional interrupt")
        attempt.fail.assert_called_once_with("fictional interrupt")

    def test_access_identity_binds_the_earlier_protected_input_prefix(self):
        config = replace(self.config,
            backtest=replace(self.config.backtest, start=date(2025, 1, 1), end=date(2025, 12, 31)),
            evaluation=replace(self.config.evaluation, period="exploratory", start=None, end=None),
            research=ResearchConfig(self.root / "calendar.json", self.root / "freeze.json"))
        selected = ResearchContext({"fictional": True}, Mock(sha256="c" * 64), {"identity": {
            "code_sha256": BASELINE[0], "evaluator_sha256": BASELINE[0],
            "input_manifest_sha256": capture_inputs(config).sha256}})
        with patch("boring_alpha.research_access.legacy_research_context", return_value=selected), patch(
            "boring_alpha.research_state.RunJournal"
        ) as journal:
            prepare_run(config)
        identity = journal.return_value.begin.call_args.args[0]
        self.assertEqual(identity.start, date(2022, 1, 1))
        self.assertEqual(identity.end, date(2025, 12, 31))

    def test_raw_access_identity_changes_with_future_bytes_but_observations_stay_truncated(self):
        first = capture_inputs(self.config).sha256
        path = self.config.data.prices_path
        path.write_text(path.read_text().replace("PROTECTED", "REVISED"))
        self.assertNotEqual(first, capture_inputs(self.config).sha256)
        self.assertEqual(load_market_data(self.config).dates, (date(2021, 1, 4),))
