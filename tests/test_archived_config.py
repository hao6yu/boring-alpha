"""Embedded config must agree with the contract without consulting live files."""

from copy import deepcopy
from pathlib import Path
import json

import pytest

from boring_alpha.archived_config import validate_archived_config
from boring_alpha.config import load_config
from boring_alpha.demo import prepare_ba002_demo
from boring_alpha.research_contract import expected_row_definitions


@pytest.fixture(scope="module")
def archive_records(tmp_path_factory):
    root = tmp_path_factory.mktemp("pure-config-fixture")
    paths = prepare_ba002_demo(root)
    config = load_config(paths["development"])
    contract = json.loads((root / "research/freeze.json").read_text())["identity"]["contract"]
    manifest = {
        "strategy_id": "BA-002", "strategy_spec_sha256": config.strategy_spec_sha256,
        "config_toml": config.raw_bytes.decode(),
        "evaluation_period": "development", "backtest_start": "2018-01-01",
        "backtest_end": "2018-12-31", "evaluation_start": "2018-01-01",
        "evaluation_end": "2018-12-31", "evidence_status": "synthetic",
        "data_source": "synthetic:fictional-fixture",
        "tax_policy_sha256": contract["tax_policy_sha256"],
        "grid": {key: "description is not behavior" for key in expected_row_definitions()},
    }
    return manifest, contract


def test_original_embedded_config_matches_loader_hash_without_file_reads(archive_records, monkeypatch):
    manifest, contract = deepcopy(archive_records)
    # Contract and original periods_path may be deleted/moved after publication.
    # This validator must not open them or call the ordinary path-based loader.
    def forbidden(*args, **kwargs):
        raise AssertionError("archive validation attempted a live filesystem read")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)
    assert validate_archived_config(manifest, contract) is None


@pytest.mark.parametrize("before,after", [
    ('exposure = 0.60', 'exposure = 0.90'),
    ('cost_bps = 10', 'cost_bps = 0'),
    ('source = "synthetic"', 'source = "csv"'),
    ('start = "2018-01-01"', 'start = "2018-02-01"'),
    ('end = "2018-12-31"', 'end = "2018-11-30"'),
    ('horizons = [9, 12, 15]', 'horizons = [9, 12]'),
    ('warmup_months = 15', 'warmup_months = 12'),
    ('lookback_months = 15', 'lookback_months = 12'),
    ('sleeve_weight = 0.125', 'sleeve_weight = 0.10'),
    ('initial_cash = 100000', 'initial_cash = 5000'),
    ('rebalance = "annual"', 'rebalance = "monthly"'),
    ('ordinary_rate = 0.35', 'ordinary_rate = 0.37'),
    ('SPY = 0.95', 'SPY = 0.50'),
    ('GLD = "collectibles"', 'GLD = "standard"'),
    ('"SPY", "IWM"', '"QQQ", "IWM"'),
    ('period = "development"', 'period = "validation"'),
    ('cost_bps = 10', 'cost_bps = true'),
    ('warmup_months = 15', 'warmup_months = 15.0'),
])
def test_embedded_behavior_tampering_is_refused(archive_records, before, after):
    manifest, contract = deepcopy(archive_records)
    assert before in manifest["config_toml"]
    manifest["config_toml"] = manifest["config_toml"].replace(before, after)
    with pytest.raises(ValueError):
        validate_archived_config(manifest, contract)


@pytest.mark.parametrize("field,value", [
    ("strategy_spec_sha256", "0" * 64),
    ("backtest_start", "2018-02-01"),
    ("evaluation_end", "2018-11-30"),
    ("evaluation_period", "validation"),
    ("evidence_status", "seen"),
    ("data_source", "csv:truncated=2018-12-31"),
    ("strategy_id", "BA-001"),
    ("tax_policy_sha256", "0" * 64),
])
def test_manifest_metadata_tampering_is_refused(archive_records, field, value):
    manifest, contract = deepcopy(archive_records)
    manifest[field] = value
    with pytest.raises(ValueError):
        validate_archived_config(manifest, contract)


def test_nonempty_quality_override_is_not_an_unhashed_control(archive_records):
    manifest, contract = deepcopy(archive_records)
    manifest["config_toml"] += "\n[quality]\nmax_stale_closes = 1000000000000\n"
    with pytest.raises(ValueError, match="quality"):
        validate_archived_config(manifest, contract)


def test_diagnostic_clusters_are_validated_but_do_not_change_behavior_identity(archive_records):
    manifest, contract = deepcopy(archive_records)
    manifest["config_toml"] += '\n[clusters]\nequities = ["SPY", "IWM", "EFA", "EEM"]\n'
    assert validate_archived_config(manifest, contract) is None
    manifest["config_toml"] += 'other = ["SPY"]\n'
    with pytest.raises(ValueError, match="overlap"):
        validate_archived_config(manifest, contract)


def test_unregistered_grid_diagnostics_cannot_masquerade_as_gating_rows(archive_records):
    manifest, contract = deepcopy(archive_records)
    manifest["grid"]["reference_12"] = "diagnostic"
    with pytest.raises(ValueError, match="grid"):
        validate_archived_config(manifest, contract)


def test_original_paths_are_locations_not_mutable_frozen_inputs(archive_records):
    manifest, contract = deepcopy(archive_records)
    manifest["config_toml"] = manifest["config_toml"].replace(
        '../research/freeze.json', '/a/nonexistent/original/freeze.json',
    ).replace('../data/distributions_daily.csv', '/a/moved/distributions.csv')
    assert validate_archived_config(manifest, contract) is None


def test_historical_config_normalization_uses_only_archived_semantics(archive_records):
    from boring_alpha.config import (
        BenchmarkConfig, DataConfig, ExecutionConfig, PortfolioConfig, StrategyConfig,
        _strategy_spec_hash,
    )
    from boring_alpha.research_contract import SYMBOLS

    manifest, contract = deepcopy(archive_records)
    contract["synthetic"] = False
    contract["data_methodology"] = "yahoo-adjusted-v2+dgs3mo-v1"
    contract["periods"]["sealed"] = {"start": "2020-01-01", "end": "2021-12-31", "status": "unopened"}
    before, data_tail = manifest["config_toml"].split("[data]\n", 1)
    _, after = data_tail.split("[backtest]\n", 1)
    manifest["config_toml"] = before + '''[data]
source = "csv"
prices_path = "/DO-NOT-READ/market.csv"
cash_path = "/DO-NOT-READ/cash.csv"
methodology = "yahoo-adjusted-v2+dgs3mo-v1"
[backtest]
''' + after
    manifest["data_source"] = "csv:truncated=2018-12-31"
    manifest["evidence_status"] = "seen"
    manifest["strategy_spec_sha256"] = _strategy_spec_hash(
        StrategyConfig("BA-002", "name is not behavior", SYMBOLS, 15, 0.125, (9, 12, 15), 15),
        PortfolioConfig(100000.0), ExecutionConfig(10.0),
        DataConfig(source="csv", methodology="yahoo-adjusted-v2+dgs3mo-v1"),
        BenchmarkConfig(0.6, "annual"),
    )
    assert validate_archived_config(manifest, contract) is None
    manifest["config_toml"] = manifest["config_toml"].replace("yahoo-adjusted-v2+dgs3mo-v1", "yahoo-adjusted-v1+dgs3mo-v1")
    with pytest.raises(ValueError, match="methodology"):
        validate_archived_config(manifest, contract)
