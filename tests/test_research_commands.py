"""The freeze CLI reviews metadata; it must not run or parse market inputs."""

from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from boring_alpha import cli, research_commands
from boring_alpha.config import load_config
from boring_alpha.demo import prepare_ba002_demo
from boring_alpha.research_contract import canonical_sha256
from boring_alpha.research_freeze import freeze_sha256, load_freeze


@pytest.fixture
def laboratory(tmp_path):
    paths = prepare_ba002_demo(tmp_path)
    config_path = paths["development"]
    config_path.write_text(config_path.read_text().replace('freeze.json', 'command-freeze.json'))
    charter = tmp_path / "fictional-charter.md"
    charter.write_text("# Fictional BA-002 charter\nTest preparation only, not market evidence.\n")
    config = load_config(config_path)
    # Install traps after fixture construction. That construction generates
    # fictional prices; none of the commands below may load or evaluate them.
    forbidden = (
        "boring_alpha.data.loader.load_market_data",
        "boring_alpha.data.loader.load_csv_market_data",
        "boring_alpha.data.loader.load_csv_market_data_bytes",
        "boring_alpha.data.loader.generate_synthetic_market_data",
        "boring_alpha.data.csv_loader.load_csv_market_data_bytes",
        "boring_alpha.data.distributions.load_distributions",
        "boring_alpha.data.distributions.load_distributions_bytes",
        "boring_alpha.research_access.open_run",
        "boring_alpha.research_state.RunJournal",
        "boring_alpha.research_family.canonical_journal_path",
        "boring_alpha.cli.run_backtest",
        "boring_alpha.cli.run_sweep_command",
    )
    with ExitStack() as stack:
        for target in forbidden:
            stack.enter_context(patch(target, side_effect=AssertionError(f"review-only command called {target}")))
        yield SimpleNamespace(root=tmp_path, paths=paths, config_path=config_path,
                              charter=charter, config=config,
                              freeze=config.research.freeze_path, journal=tmp_path / "must-not-exist.json")


def prepare(lab):
    assert research_commands.prepare_research_freeze(lab.config_path, lab.charter) == 0
    return load_freeze(lab.freeze)


def invoke(*arguments):
    with patch("sys.argv", ["boring-alpha", *map(str, arguments)]), pytest.raises(SystemExit) as exited:
        cli.main()
    return exited.value.code


def test_prepare_produces_a_reviewable_draft_without_journal_or_numeric_reads(laboratory, capsys):
    with patch.object(research_commands, "capture_inputs", side_effect=AssertionError("synthetic raw capture")):
        draft = prepare(laboratory)
    output = capsys.readouterr().out
    assert draft["status"] == "draft"
    assert draft["confirmation"] is None
    assert draft["identity"]["charter_text"] == laboratory.charter.read_text()
    assert draft["identity"]["charter_sha256"] == hashlib.sha256(laboratory.charter.read_bytes()).hexdigest()
    data = laboratory.config.data
    assert draft["identity"]["input_manifest_sha256"] == canonical_sha256({
        'generator': 'synthetic-v1', 'symbols': list(laboratory.config.strategy.symbols),
        'start': str(data.start), 'end': str(data.end), 'seed': data.seed,
        'annual_cash_rate': data.annual_cash_rate, 'regime': data.regime,
    })
    assert freeze_sha256(draft) in output
    assert "SYNTHETIC ONLY" in output
    assert "Draft prepared; no execution, confirmation or journal initialization occurred." in output
    assert not laboratory.journal.exists()
    assert not (laboratory.root / "experiments").exists()


def test_show_is_read_only_and_does_not_reopen_source_configuration(laboratory, capsys):
    draft = prepare(laboratory)
    before = laboratory.freeze.read_bytes()
    with patch.object(research_commands, "load_config", side_effect=AssertionError("config read")), patch.object(
        research_commands.SessionCalendar, "load", side_effect=AssertionError("calendar read")
    ), patch.object(research_commands, "capture_inputs", side_effect=AssertionError("market input read")):
        assert research_commands.show_research_freeze(laboratory.freeze) == 0
    output = capsys.readouterr().out
    assert f"Full identity: {freeze_sha256(draft)}" in output
    assert "Status: draft" in output
    assert laboratory.freeze.read_bytes() == before
    assert not laboratory.journal.exists()


def test_confirm_synthetic_draft_keeps_identity_and_never_initializes_journal(laboratory, capsys):
    draft = prepare(laboratory)
    reviewed = freeze_sha256(draft)
    assert research_commands.confirm_research_freeze(laboratory.config_path, reviewed, "  reviewed fictional test settings  ") == 0
    confirmed = load_freeze(laboratory.freeze, require_confirmed=True)
    assert confirmed["identity"] == draft["identity"]
    assert freeze_sha256(confirmed) == reviewed
    assert confirmed["confirmation"]["reason"] == "reviewed fictional test settings"
    assert "No strategy was run and no holdout was revealed." in capsys.readouterr().out
    before = laboratory.freeze.read_bytes()
    research_commands.confirm_research_freeze(laboratory.config_path, reviewed, "same identity")
    assert laboratory.freeze.read_bytes() == before
    assert not laboratory.journal.exists()
    assert not (laboratory.root / "experiments").exists()


@pytest.mark.parametrize("short_hash", [False, True])
def test_confirmation_requires_the_exact_full_displayed_hash(laboratory, short_hash):
    draft = prepare(laboratory)
    bad_hash = freeze_sha256(draft)[:12] if short_hash else "0" * 64
    before = laboratory.freeze.read_bytes()
    with pytest.raises(ValueError, match="hash|SHA-256"):
        research_commands.confirm_research_freeze(laboratory.config_path, bad_hash, "reviewed")
    assert laboratory.freeze.read_bytes() == before
    assert not laboratory.journal.exists()


@pytest.mark.parametrize("reason", ["", " \n\t "])
def test_confirmation_requires_a_human_reason(laboratory, reason):
    draft = prepare(laboratory)
    before = laboratory.freeze.read_bytes()
    with pytest.raises(ValueError, match="nonempty reason"):
        research_commands.confirm_research_freeze(laboratory.config_path, freeze_sha256(draft), reason)
    assert laboratory.freeze.read_bytes() == before
    assert not laboratory.journal.exists()


@pytest.mark.parametrize("old,new", [
    ("cost_bps = 10", "cost_bps = 11"),
    ("ordinary_rate = 0.35", "ordinary_rate = 0.36"),
    ("seed = 21", "seed = 22"),
])
def test_confirmation_refuses_configuration_changed_since_preparation(laboratory, old, new):
    draft = prepare(laboratory)
    before = laboratory.freeze.read_bytes()
    laboratory.config_path.write_text(laboratory.config_path.read_text().replace(old, new))
    with pytest.raises(ValueError, match="differs|changed|draft|contract"):
        research_commands.confirm_research_freeze(laboratory.config_path, freeze_sha256(draft), "stale review")
    assert laboratory.freeze.read_bytes() == before
    assert not laboratory.journal.exists()


@pytest.mark.parametrize("changed", ["calendar", "window", "code"])
def test_confirmation_refuses_other_reviewed_identity_changes(laboratory, changed):
    draft = prepare(laboratory)
    before = laboratory.freeze.read_bytes()
    with ExitStack() as stack:
        if changed == "calendar":
            path = laboratory.config.research.calendar_path
            calendar = json.loads(path.read_text())
            calendar["version"] = "different-fictional-version"
            path.write_text(json.dumps(calendar))
        elif changed == "window":
            path = laboratory.config_path.parent / "evaluation_periods.toml"
            path.write_text(path.read_text().replace("2018-01-01", "2018-02-01"))
            path = laboratory.config_path
            path.write_text(path.read_text().replace("2018-01-01", "2018-02-01"))
        else:
            stack.enter_context(patch("boring_alpha.research_freeze.code_fingerprint", return_value="9" * 64))
        with pytest.raises(ValueError, match="differ.*draft"):
            research_commands.confirm_research_freeze(laboratory.config_path, freeze_sha256(draft), "stale review")
    assert laboratory.freeze.read_bytes() == before
    assert not laboratory.journal.exists()


def test_show_refuses_a_charter_edited_without_updating_its_identity(laboratory):
    draft = prepare(laboratory)
    draft["identity"]["charter_text"] += "Unreviewed edit.\n"
    laboratory.freeze.write_text(json.dumps(draft))
    with pytest.raises(ValueError, match="charter_sha256"):
        research_commands.show_research_freeze(laboratory.freeze)


def test_preparing_again_does_not_overwrite_a_confirmed_review(laboratory):
    draft = prepare(laboratory)
    research_commands.confirm_research_freeze(laboratory.config_path, freeze_sha256(draft), "Fictional review")
    before = laboratory.freeze.read_bytes()
    with pytest.raises(ValueError, match="choose a new research.freeze_path"):
        research_commands.prepare_research_freeze(laboratory.config_path, laboratory.charter)
    assert laboratory.freeze.read_bytes() == before


def test_prepare_explains_dataset_ended_registry_without_creating_a_draft(laboratory):
    registry = laboratory.config_path.parent / "evaluation_periods.toml"
    before = registry.read_text()
    assert 'end = 2019-12-31' in before
    registry.write_text(before.replace('end = 2019-12-31', 'end = "dataset"'))
    with pytest.raises(ValueError, match="fixed reviewed end date"):
        research_commands.prepare_research_freeze(laboratory.config_path, laboratory.charter)
    assert not laboratory.freeze.exists()


def test_prepare_historical_branch_only_captures_raw_bytes_and_leaves_a_draft(laboratory):
    # Exercise the historical branch with fake metadata and a mocked byte
    # capture. No historical calendar, approval, data or journal is created.
    config = replace(laboratory.config, data=replace(laboratory.config.data,
        source="csv", methodology="yahoo-adjusted-v2+dgs3mo-v1"))
    calendar = SimpleNamespace(synthetic=False, sha256="1" * 64, authority_sha256="2" * 64, requirements=Mock())
    periods = {
        "development": {"start": "2018-01-01", "end": "2018-12-31", "status": "seen"},
        "validation": {"start": "2019-01-01", "end": "2019-12-31", "status": "seen"},
        "sealed": {"start": "2022-01-01", "end": "2022-12-31", "status": "unopened"},
    }
    with patch.object(research_commands, "load_config", return_value=config), patch.object(
        research_commands.SessionCalendar, "load", return_value=calendar
    ), patch.object(research_commands, "_periods", return_value=periods), patch.object(
        research_commands, "capture_inputs", return_value=SimpleNamespace(sha256="3" * 64)
    ) as capture, patch("boring_alpha.research_family.canonical_journal_path", return_value=laboratory.journal):
        draft = prepare(laboratory)
    capture.assert_called_once_with(config)
    assert draft["identity"]["input_manifest_sha256"] == "3" * 64
    assert draft["status"] == "draft"
    assert draft["confirmation"] is None
    assert not laboratory.journal.exists()


def test_cli_prepare_show_confirm_dispatches_the_complete_workflow(laboratory, capsys):
    assert invoke("research", "prepare", laboratory.config_path, "--charter", laboratory.charter) == 0
    draft = load_freeze(laboratory.freeze)
    assert invoke("research", "show", laboratory.freeze) == 0
    assert invoke("research", "confirm", laboratory.config_path, "--hash", freeze_sha256(draft), "--reason", "reviewed fictional CLI fixture") == 0
    output = capsys.readouterr().out
    assert "Status: draft" in output
    assert "Status: confirmed" in output
    assert load_freeze(laboratory.freeze)["confirmation"]["reason"] == "reviewed fictional CLI fixture"
    assert not laboratory.journal.exists()


def test_cli_reports_invalid_confirmation_as_exit_two_without_modification(laboratory, capsys):
    draft = prepare(laboratory)
    before = laboratory.freeze.read_bytes()
    assert invoke("research", "confirm", laboratory.config_path, "--hash", freeze_sha256(draft), "--reason", " ") == 2
    assert "error:" in capsys.readouterr().err
    assert laboratory.freeze.read_bytes() == before
    assert not laboratory.journal.exists()
