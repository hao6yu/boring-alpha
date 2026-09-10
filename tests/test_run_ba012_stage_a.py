"""Synthetic runner integration; never opens historical prices or a network."""
import json
from pathlib import Path
import sys
import urllib.request

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_ba012_stage_a as runner


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", lambda *a, **k: pytest.fail("No network in runner tests"))
    monkeypatch.setattr(runner.inputs, "read_archives", lambda *a, **k: pytest.fail("Runner must never read price archives"))


@pytest.fixture
def synthetic():
    design = runner.inputs.load_design()  # Frozen rules only, never price files.
    sessions = design["calendar"]["joint_sessions"]
    indices = [i for i, day in enumerate(sessions) if day >= "2018-01-01"
               and (i == len(sessions) - 1 or sessions[i + 1][:7] != day[:7])]
    t = np.arange(252)
    rows = np.column_stack([np.sin(2 * np.pi * k * t / 252) for k in range(1, 6)])
    rows *= np.sqrt(251 / 126) * 200 / np.sqrt(252)
    movements = [[str(value) for value in row] for row in rows]
    report = {"schema": runner.inputs.SCHEMA, "market_order": list(runner.sizing.SYMBOLS),
              "protocol_sha256": runner.sizing.PROTOCOL_SHA256,
              "calendar_sha256": design["calendar_sha256"], "rolls_sha256": design["rolls_sha256"],
              "strategy_pnl_calculated": False, "sizing_calculated": False, "status": "READY",
              "monthly_cases": [
                  {"decision_date_chicago": sessions[i], "status": "READY", "required_intervals": 252,
                   "valid_intervals": 252, "interval_dates": sessions[i - 251:i + 1],
                   "window_first_endpoint": sessions[i - 252], "signs": [0] * 5,
                   "dollar_movements": movements}
                  for i in indices]}
    return report, design


def missing_case(report, index=0):
    case = report["monthly_cases"][index]
    case.update(status="DATA_INCOMPLETE", valid_intervals=251,
                missing_interval_dates=[case["interval_dates"][-1]])
    del case["dollar_movements"], case["signs"]
    report["status"] = "DATA_INCOMPLETE"


def test_all_cash_rejection_requires_all_72_complete_verified_cases(synthetic):
    report, design = synthetic
    dates, summary = runner.run_report(report, design)
    assert len(dates) == 72
    assert summary["status"] == "COMPLETE_SIZING_ONLY"
    assert summary["primary_capital_verdict"] == "ALL_CASH_REJECT_CAPITAL_SPECIFICATION"
    assert not summary["strategy_pnl_calculated"] and not summary["raw_archives_reopened"]
    for row in summary["capital_summaries"].values():
        assert row["cash_cases"] == row["optimum_verified_cases"] == 72
        assert row["participation_fraction_among_verified_cases"] == 0


def test_missing_data_is_skipped_not_cash_or_capital_failure(synthetic):
    report, design = synthetic
    missing_case(report)
    calls = []
    def tracked(*args, **kwargs):
        calls.append(args[2])
        return runner.sizing.size_stage_a(*args, **kwargs)
    dates, summary = runner.run_report(report, design, size_fn=tracked)
    assert len(calls) == 71 * 3
    assert dates[0]["capital_results"]["5000"]["quantities"] is None
    assert summary["status"] == "INCOMPLETE_STUDY"
    assert summary["primary_capital_verdict"] == "INCOMPLETE_STUDY_NO_CAPITAL_VERDICT"
    assert summary["capital_summaries"]["5000"]["cash_cases"] == 71


def test_partial_nonzero_is_participation_evidence_with_incomplete_study(synthetic):
    report, design = synthetic
    missing_case(report)
    report["monthly_cases"][1]["signs"] = [1] * 5
    dates, summary = runner.run_report(report, design)
    primary = summary["capital_summaries"]["5000"]
    assert dates[1]["capital_results"]["5000"]["decision"] == "NONZERO"
    assert primary["verdict"] == "INCOMPLETE_STUDY_WITH_PARTICIPATION_EVIDENCE"
    assert primary["nonzero_cases"] == 1 and primary["cash_cases"] == 70
    assert primary["participation_fraction_among_verified_cases"] == pytest.approx(1 / 71)
    assert primary["terminal_annual_dollar_vol_nonzero_cases"]["count"] == 1
    assert summary["status"] == "INCOMPLETE_STUDY"


def test_search_limit_never_becomes_cash_or_all_cash_rejection(synthetic):
    report, design = synthetic
    report["monthly_cases"][0]["signs"] = [1] * 5
    dates, summary = runner.run_report(report, design, max_nodes=1)
    assert dates[0]["capital_results"]["5000"]["status"] == "SEARCH_LIMIT"
    primary = summary["capital_summaries"]["5000"]
    assert primary["search_limit_cases"] == 1 and primary["cash_cases"] == 71
    assert primary["verdict"] == "INCOMPLETE_STUDY_NO_CAPITAL_VERDICT"


def test_invalid_zero_variance_window_stays_unresolved(synthetic):
    report, design = synthetic
    report["monthly_cases"][0]["dollar_movements"] = [["0.1"] * 5 for _ in range(252)]
    dates, summary = runner.run_report(report, design)
    assert dates[0]["capital_results"]["5000"]["status"] == "INVALID_RISK_INPUT"
    assert summary["primary_capital_verdict"] == "INCOMPLETE_STUDY_NO_CAPITAL_VERDICT"
    assert summary["capital_summaries"]["5000"]["invalid_risk_input_cases"] == 1


@pytest.mark.parametrize("tamper", [
    lambda report: report.update(protocol_sha256="0" * 64),
    lambda report: report.update(calendar_sha256="0" * 64),
    lambda report: report.update(rolls_sha256="0" * 64),
    lambda report: report["monthly_cases"].pop(),
    lambda report: report["monthly_cases"][0]["interval_dates"].reverse(),
    lambda report: report["monthly_cases"][0].update(window_first_endpoint="2016-01-11"),
    lambda report: report["monthly_cases"][0].update(signs=[1, 1, .5, 1, 1]),
])
def test_tampered_design_or_causal_window_fails_before_sizing(synthetic, tamper):
    report, design = synthetic
    tamper(report)
    with pytest.raises(runner.RunnerError):
        runner.run_report(report, design, size_fn=lambda *a, **k: pytest.fail("Invalid input reached sizing"))


def test_cli_input_checksum_failure_cannot_open_mapping_or_write_outputs(synthetic, tmp_path, monkeypatch, capsys):
    report, _ = synthetic
    source = tmp_path / "synthetic.json"
    source.write_text(json.dumps(report))
    output = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", ["runner", "--input", str(source), "--input-sha256", "0" * 64,
                        "--mapping", str(tmp_path / "does-not-exist.json"), "--output-dir", str(output)])
    assert runner.main() == 2
    assert not output.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "RUNNER_FAILED"


def test_synthetic_cli_writes_hashed_dates_and_runtime_provenance(synthetic, tmp_path, monkeypatch, capsys):
    report, design = synthetic
    # A metadata-only synthetic mapping seam; mapping bytes are still checked
    # against the input hash and no provider/archive is involved.
    mapping = tmp_path / "synthetic-mapping.json"
    mapping.write_text('{"synthetic_mapping":true}\n')
    report["mapping_sha256"] = runner.sha256_file(mapping)
    source = tmp_path / "synthetic-input.json"
    source.write_text(json.dumps(report))
    output = tmp_path / "output"
    monkeypatch.setattr(runner.inputs, "mapping_index", lambda *_: ({}, {}))
    monkeypatch.setattr(sys, "argv", ["runner", "--input", str(source), "--input-sha256", runner.sha256_file(source),
                        "--mapping", str(mapping), "--output-dir", str(output)])
    assert runner.main() == 0
    result = json.loads((output / "summary.json").read_text())
    assert len(result["per_date_files"]) == 72
    for item in result["per_date_files"]:
        assert runner.sha256_file(output / item["path"]) == item["sha256"]
    assert result["input"]["sha256"] == runner.sha256_file(source)
    assert result["runtime"]["numpy"]["version"] == np.__version__
    assert result["runtime"]["numpy"]["installed_files_hashed"] > 1
    assert all(len(item["sha256"]) == 64 for item in result["runtime"]["code_files"])
    assert result["runtime"]["python"]["executable_sha256"]
    assert json.loads(capsys.readouterr().out)["summary_sha256"] == runner.sha256_file(output / "summary.json")
