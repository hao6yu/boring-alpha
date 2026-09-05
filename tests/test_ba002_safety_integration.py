"""Read-once handoff checks use fictional CSVs and a mocked run journal."""

from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from boring_alpha.config import ResearchConfig, load_config
from boring_alpha.demo import prepare_ba002_demo
from boring_alpha.research_access import ResearchContext, capture_inputs, open_run


class ReadOnceByteHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        demo = prepare_ba002_demo(self.root / "fictional-demo")
        base = load_config(demo["development"])
        self.addCleanup(patch.stopall)
        patch("boring_alpha.research_access.capture_execution_identity", return_value=("a" * 64, "b" * 64)).start()
        self.prices = self.root / "prices.csv"
        self.cash = self.root / "cash.csv"
        self.distributions = self.root / "distributions.csv"
        self.manifest = self.root / "manifest.json"
        self.prices.write_text("date,symbol,tr_open,tr_close\n2025-01-02,A,100,100\n2030-01-02,A,PROTECTED,PROTECTED\n")
        self.cash.write_text("date,cash_factor\n2025-01-02,1\n2030-01-02,PROTECTED\n")
        self.distributions.write_text("date,symbol,close,dividend\n2025-01-02,A,100,0\n2030-01-02,A,PROTECTED,PROTECTED\n")
        self.manifest.write_text(json.dumps({"methodology": "fictional-v1", "splits": {"A": []}}))
        self.config = replace(
            base,
            strategy=replace(base.strategy, strategy_id="BA-001", symbols=("A",), sleeve_weight=1.0),
            backtest=replace(base.backtest, start=date(2025, 1, 1), end=date(2025, 1, 31)),
            evaluation=replace(base.evaluation, period="exploratory", start=None, end=None),
            data=replace(base.data, source="csv", prices_path=self.prices, cash_path=self.cash, methodology="fictional-v1"),
            tax=replace(base.tax, distributions_path=self.distributions),
            research=ResearchConfig(self.root / "unused-calendar.json", self.root / "unused-freeze.json", self.root / "unused-journal.json"),
        )
        # Profile selection and the journal backend are mocked; capture, frozen
        # hash comparison, lifecycle and all readers below are real.
        self.context = ResearchContext({"fixture": "TOCTOU"}, Mock(sha256="c" * 64), {"identity": {
            "code_sha256": "a" * 64, "evaluator_sha256": "a" * 64,
            "input_manifest_sha256": capture_inputs(self.config).sha256,
        }})

    def test_replacement_after_authorization_cannot_change_parsed_market_or_tax_inputs(self):
        from boring_alpha.research_access import captured_distributions

        originally_captured = capture_inputs(self.config).sha256
        attempt = Mock()

        def replace_sources():
            self.prices.write_text(self.prices.read_text().replace(",100,100", ",123,123"))
            self.cash.write_text(self.cash.read_text().replace("2025-01-02,1\n", "2025-01-02,1.0001\n"))
            self.distributions.write_text(self.distributions.read_text().replace(",100,0", ",456,3"))
            self.manifest.write_text(json.dumps({"methodology": "replaced-v2", "splits": {"A": []}}))

        attempt.start_access.side_effect = replace_sources
        with patch("boring_alpha.research_access.legacy_research_context", return_value=self.context), patch(
            "boring_alpha.research_state.RunJournal"
        ) as ledger:
            ledger.return_value.begin.return_value = attempt
            with open_run(self.config, reveal_reason="Fictional read-once fixture") as run:
                data = run.data
                table, manifest, provenance = captured_distributions(run.context, date(2025, 1, 31))
                run.context.artifact_path = "fictional-byte-handoff"
            identity = ledger.return_value.begin.call_args.args[0]
        self.assertEqual(identity.input_manifest_sha256, originally_captured)
        self.assertNotEqual(identity.input_manifest_sha256, capture_inputs(self.config).sha256)
        self.assertEqual(data.bar(date(2025, 1, 2), "A").close, 100)
        self.assertEqual(data.cash_factors[date(2025, 1, 2)], 1)
        self.assertEqual(table.close(date(2025, 1, 2), "A"), 100)
        self.assertEqual(table.dividend(date(2025, 1, 2), "A"), 0)
        self.assertEqual(manifest["methodology"], "fictional-v1")
        self.assertEqual(provenance["methodology"], "fictional-v1")
        self.assertEqual(table.dates, (date(2025, 1, 2),))
        self.assertFalse(any(name.startswith("_research") for name in vars(data)))
        attempt.complete.assert_called_once_with("fictional-byte-handoff")

    def test_captured_market_loading_does_not_reopen_any_input_path(self):
        attempt = Mock()

        def remove_sources():
            for path in (self.prices, self.cash, self.distributions, self.manifest):
                path.unlink()

        attempt.start_access.side_effect = remove_sources
        with patch("boring_alpha.research_access.legacy_research_context", return_value=self.context), patch(
            "boring_alpha.research_state.RunJournal"
        ) as ledger:
            ledger.return_value.begin.return_value = attempt
            with open_run(self.config, reveal_reason="Fictional source-removal fixture") as run:
                data = run.data
                from boring_alpha.research_access import captured_distributions
                table = captured_distributions(run.context, date(2025, 1, 31))[0]
                run.context.artifact_path = "fictional-source-removal"
        self.assertEqual(data.bar(date(2025, 1, 2), "A").close, 100)
        self.assertEqual(table.dates, (date(2025, 1, 2),))
