"""Fictional source fixtures; no network, credentials, or historical execution."""

import csv
from dataclasses import replace
from datetime import date
import gzip
import io
import json
from types import SimpleNamespace

import pytest

from boring_alpha.data.quality import ERROR, Finding
from boring_alpha.domain import BacktestResult, EquityPoint
from boring_alpha.tax.reconstruct import read_manifest
from tools import run_ba002_source_sensitivity as runner


DAYS = (runner.START, date(2007, 5, 31), date(2007, 6, 1), date(2017, 12, 29), runner.END)


def encoded(columns, rows):
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue().encode()


class FixtureCalendar:
    """Sparse fictional dates; asserts driver routing, not exchange coverage."""

    synthetic = False
    sha256 = "c" * 64

    def canonical_bytes(self):
        return b'{"fixture":"fictional sparse calendar"}'

    def validate_inputs(self, data, table, symbols, start, end, horizons, *, warmup_months):
        assert horizons == (9, 12, 15) and warmup_months == 15
        assert (start, end) in runner.WINDOWS.values()
        expected = {day for day in DAYS if day <= end}
        assert set(data.dates) == expected and set(table.dates) == expected
        assert set(data.symbols) == set(symbols)

    def validate_output_sessions(self, days, start, end):
        assert tuple(days) == tuple(day for day in DAYS if start <= day <= end)


@pytest.fixture
def source(tmp_path, monkeypatch):
    config = runner.reference_config("development")  # Configuration only.
    calendar = FixtureCalendar()
    directory = tmp_path / "source"
    directory.mkdir()
    symbols = config.strategy.symbols
    payloads = {
        "market_daily.csv": encoded(runner.INPUT_COLUMNS["market_daily.csv"],
            [(day, symbol, 100, 100) for day in DAYS for symbol in symbols]
            + [("2022-01-03", "SPY", "UNAVAILABLE_FUTURE", "UNAVAILABLE_FUTURE")]),
        "cash_daily.csv": encoded(runner.INPUT_COLUMNS["cash_daily.csv"],
            [(day, 1) for day in DAYS] + [("2022-01-03", "UNAVAILABLE_FUTURE")]),
        "distributions_daily.csv": encoded(runner.INPUT_COLUMNS["distributions_daily.csv"],
            [(day, symbol, 100, 0) for day in DAYS for symbol in symbols]
            + [("2022-01-03", "SPY", "UNAVAILABLE_FUTURE", "UNAVAILABLE_FUTURE")]),
        "issuer_evidence.json": b'{"purpose":"fictional fixture"}',
    }
    for name, raw in payloads.items():
        (directory / name).write_bytes(raw)
    script_bytes = {"build_ba002_source_snapshots.py": b"fictional builder", "run_ba002_source_sensitivity.py": b"fictional driver"}
    identity = {"code_sha256": "a" * 64, "evaluator_sha256": "b" * 64,
                "script_sha256": {name: runner.digest(raw) for name, raw in script_bytes.items()}}
    manifest = {
        "methodology": "yahoo-adjusted-v3-tlt-20121101+dgs3mo-v1", "synthetic": False, "complete": True,
        "start": str(runner.START), "end": str(runner.END), "calendar_sha256": calendar.sha256,
        "builder_sha256": identity["script_sha256"]["build_ba002_source_snapshots.py"],
        "splits": {symbol: [] for symbol in symbols},
        "sha256": {name: runner.digest(raw) for name, raw in payloads.items()},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    # The deliberately sparse fixture is not claimed to satisfy real-world
    # gap thresholds. A separate test verifies quality refusals are propagated.
    monkeypatch.setattr(runner, "inspect", lambda *args: [])
    return SimpleNamespace(config=config, calendar=calendar, directory=directory, manifest=manifest,
                           payloads=payloads, root=tmp_path, identity=identity, scripts=script_bytes)


def rewrite_manifest(source):
    (source.directory / "manifest.json").write_text(json.dumps(source.manifest))


@pytest.mark.parametrize("period", tuple(runner.WINDOWS))
def test_reference_configuration_keeps_fixed_rule_and_tax_policy(period):
    config = runner.reference_config(period)
    assert (config.backtest.start, config.backtest.end) == runner.WINDOWS[period]
    assert config.strategy.horizons == (9, 12, 15)
    assert runner.policy_sha256(config.tax) == runner.POLICY_SHA256


@pytest.mark.parametrize("period", ["sealed", "exploratory", "development-short"])
def test_other_periods_refuse_before_configuration_access(monkeypatch, period):
    monkeypatch.setattr(runner, "load_config", lambda *args: pytest.fail("must refuse first"))
    with pytest.raises(ValueError, match="fixed already-seen"):
        runner.reference_config(period)


@pytest.mark.parametrize("change", ["horizons", "window", "tax"])
def test_reference_behavior_and_policy_changes_refuse(source, monkeypatch, change):
    config = source.config
    if change == "horizons":
        config = replace(config, strategy=replace(config.strategy, horizons=(6, 9, 12)))
    elif change == "window":
        config = replace(config, backtest=replace(config.backtest, start=date(2008, 1, 1)))
    else:
        config = replace(config, tax=replace(config.tax, ordinary_rate=0.36))
    monkeypatch.setattr(runner, "load_config", lambda *args: config)
    with pytest.raises(ValueError):
        runner.reference_config("development")


def test_inputs_are_date_bounded_and_issuer_evidence_hash_is_preserved(source):
    data, table, manifest, _, hashes, extras = runner.load_inputs(
        source.directory, "development", source.config, source.calendar
    )
    assert data.dates[-1] == date(2017, 12, 29)
    assert table.dates[-1] == date(2017, 12, 29)
    assert data.dates[0] == runner.START
    assert hashes == source.manifest["sha256"]
    assert extras == {"issuer_evidence.json": source.payloads["issuer_evidence.json"]}
    assert manifest["methodology"] in runner.METHODS


@pytest.mark.parametrize("filename", [*runner.INPUT_COLUMNS, "issuer_evidence.json"])
def test_any_source_checksum_mismatch_refuses_before_numeric_loading(source, monkeypatch, filename):
    (source.directory / filename).write_bytes(b"changed fixture")
    monkeypatch.setattr(runner, "load_csv_market_data_bytes", lambda *args, **kwargs: pytest.fail("hash must fail first"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.load_inputs(source.directory, "development", source.config, source.calendar)


@pytest.mark.parametrize("change", ["method", "synthetic", "incomplete", "end", "calendar", "missing_hash", "path_hash"])
def test_unreviewed_or_incomplete_source_manifest_refuses(source, change):
    if change == "method":
        source.manifest["methodology"] = "yahoo-adjusted-v2+dgs3mo-v1"
    elif change == "synthetic":
        source.manifest["synthetic"] = True
    elif change == "incomplete":
        source.manifest["complete"] = False
    elif change == "end":
        source.manifest["end"] = "2022-12-31"
    elif change == "calendar":
        source.manifest["calendar_sha256"] = "0" * 64
    elif change == "missing_hash":
        del source.manifest["sha256"]["cash_daily.csv"]
    else:
        source.manifest["sha256"]["../outside.csv"] = "0" * 64
    rewrite_manifest(source)
    with pytest.raises(ValueError):
        runner.load_inputs(source.directory, "development", source.config, source.calendar)


def test_existing_quality_errors_are_not_disabled(source, monkeypatch):
    monkeypatch.setattr(runner, "inspect", lambda *args: [Finding(ERROR, "fixture-error", "fictional quality failure")])
    with pytest.raises(ValueError, match="fictional quality failure"):
        runner.load_inputs(source.directory, "development", source.config, source.calendar)


def scenarios(cagrs):
    return {str(index): {"metrics": {"after_tax_cagr": value}} for index, value in enumerate(cagrs)}


def test_summary_uses_independent_extrema_not_best_matched_margin():
    report = runner.summarize_row("base", {"strategy": {"max_drawdown": -0.15}, "benchmark": {"max_drawdown": -0.16}},
                                 {"strategy": scenarios([0.06, 0.08]), "benchmark": scenarios([0.05, 0.07])})
    assert report["independent_extrema_margin_bps_per_year"] == -100
    assert set(report["matched_scenario_margin_bps_per_year"].values()) == {100}
    assert report["descriptive_original_threshold_comparison"]["return_threshold_met"] is False
    assert report["descriptive_original_threshold_comparison"]["formal_eligibility"] is False


@pytest.mark.parametrize("row, strategy, benchmark, expected", [
    ("base", .055, .05, True), ("base", .05499, .05, False),
    ("without_9", .05, .05, False), ("without_9", .050001, .05, True),
])
def test_original_numeric_return_threshold_boundaries(row, strategy, benchmark, expected):
    result = runner.summarize_row(row, {"strategy": {"max_drawdown": -.20}, "benchmark": {"max_drawdown": -.20}},
                                  {"strategy": scenarios([strategy]), "benchmark": scenarios([benchmark])})
    assert result["descriptive_original_threshold_comparison"]["all_original_numeric_thresholds_met"] is expected


@pytest.mark.parametrize("strategy, benchmark, expected", [(-.20, -.20, True), (-.200001, -.21, False), (-.15, -.149999, False)])
def test_original_drawdown_magnitude_and_relative_boundary(strategy, benchmark, expected):
    result = runner.summarize_row("base", {"strategy": {"max_drawdown": strategy}, "benchmark": {"max_drawdown": benchmark}},
                                  {"strategy": scenarios([.06]), "benchmark": scenarios([.05])})
    assert result["descriptive_original_threshold_comparison"]["drawdown_thresholds_met"] is expected


def install_fictional_runner(source, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", source.root)
    monkeypatch.setattr(runner, "reference_config", lambda period: source.config)
    monkeypatch.setattr(runner, "code_identity", lambda: (source.identity, source.scripts))
    monkeypatch.setattr(runner, "research_materials", lambda identity: {"protocol.md": b"fictional protocol", "code/runtime.tar.gz": b"fictional source archive"})
    monkeypatch.setattr(runner.SessionCalendar, "load", lambda path: source.calendar)
    calls = []

    class Engine:
        def __init__(self, data, symbols, *, initial_cash, cost_bps, start, end):
            self.data, self.initial, self.cost, self.start, self.end = data, initial_cash, cost_bps, start, end

        def run(self, signal):
            calls.append((self.cost, signal))
            return BacktestResult(signal.name, self.initial,
                tuple(EquityPoint(day, self.initial, self.initial, 0) for day in self.data.dates if self.start <= day <= self.end),
                (), ())

    monkeypatch.setattr(runner, "Backtester", Engine)
    return calls


def test_complete_fictional_case_archives_replayed_accounts_and_cannot_classify(source, monkeypatch):
    calls = install_fictional_runner(source, monkeypatch)
    output = source.root / "experiments/case"
    manifest, summary = runner.run_case(source.directory, "development", output)
    assert len(calls) == 10
    assert [cost for cost, _ in calls] == [10, 10, 20, 20, 10, 10, 10, 10, 10, 10]
    assert all(signal.warmup_months == 15 for _, signal in calls[::2])
    assert manifest["kind"] == runner.KIND and manifest["formal_eligibility"] is False
    assert manifest["complete"] is True and manifest["accounts"] == 10
    assert "artifact_schema" not in manifest and not (output / "criteria.json").exists()
    assert set(summary) == set(runner.expected_row_definitions())
    assert not b"UNAVAILABLE_FUTURE" in gzip.decompress((output / "input_prices.csv.gz").read_bytes())
    assert (output / "code/runtime.tar.gz").read_bytes() == b"fictional source archive"
    assert (output / "protocol.md").read_bytes() == b"fictional protocol"
    assert (output / "source/issuer_evidence.json").read_bytes() == source.payloads["issuer_evidence.json"]
    notes = json.loads((output / "configuration_notes.json").read_text())
    assert "NOT used" in notes["reference_config_role"]
    assert notes["actual_methodology"] == source.manifest["methodology"]
    for name, expected_hash in manifest["artifacts_sha256"].items():
        assert runner.digest((output / name).read_bytes()) == expected_hash
    tax = json.loads((output / "tax.json").read_text())
    assert sum(len(scenarios) for row in tax.values() for scenarios in row.values()) == 80
    for row in tax.values():
        for records in row.values():
            runner.checked_tax(records, source.config.tax, SimpleNamespace(sha256=manifest["distributions_sha256"]), source.identity)
    with pytest.raises(ValueError):
        read_manifest(output)
    with pytest.raises(FileExistsError):
        runner.run_case(source.directory, "development", output)


@pytest.mark.parametrize("failure", ["missing_scenario", "identity", "undefined", "policy", "deduction"])
def test_bad_tax_output_leaves_no_completed_case(source, monkeypatch, failure):
    install_fictional_runner(source, monkeypatch)
    original = runner.run_scenarios

    def broken(*args, **kwargs):
        records = original(*args, **kwargs)
        key = next(iter(records))
        if failure == "missing_scenario":
            del records[key]
        elif failure == "identity":
            records[key]["identity_checks"]["share_identity_passed"] = False
        elif failure == "undefined":
            records[key]["metrics"]["after_tax_cagr"] = None
        elif failure == "policy":
            records[key]["policy"]["tax_policy_sha256"] = "0" * 64
        else:
            records[key]["loss_sensitivity"] = {"non_gating": True}
        return records

    monkeypatch.setattr(runner, "run_scenarios", broken)
    output = source.root / "experiments/failed"
    with pytest.raises(ValueError):
        runner.run_case(source.directory, "development", output)
    assert not (output / "manifest.json").exists()


def test_public_or_broad_output_paths_refuse_before_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    for output in (tmp_path, tmp_path / "docs/case", tmp_path / "experiments"):
        with pytest.raises(ValueError, match="under experiments"):
            runner.private_output(output)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "experiments").mkdir()
    (tmp_path / "experiments/escaped").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="under experiments"):
        runner.private_output(tmp_path / "experiments/escaped/case")
