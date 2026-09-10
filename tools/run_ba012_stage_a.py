#!/usr/bin/env python3
"""Run frozen BA-012 sizing cases offline; never read raw bars or compute P&L."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ba012_sizing as sizing
import prepare_ba012_inputs as inputs

CAPITALS = (5000, 25000, 100000)
SCHEMA = "ba012-stage-a-sizing-v1"


class RunnerError(Exception):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_input_report(report, design):
    """Check exact monthly windows and frozen design before invoking sizing."""
    try:
        if (report["schema"] != inputs.SCHEMA or report["market_order"] != list(sizing.SYMBOLS)
                or report["protocol_sha256"] != sizing.PROTOCOL_SHA256
                or report["calendar_sha256"] != design["calendar_sha256"]
                or report["rolls_sha256"] != design["rolls_sha256"]
                or report["strategy_pnl_calculated"] is not False
                or report["sizing_calculated"] is not False):
            raise ValueError
        sessions = design["calendar"]["joint_sessions"]
        indices = [i for i, day in enumerate(sessions) if day >= "2018-01-01"
                   and (i == len(sessions) - 1 or sessions[i + 1][:7] != day[:7])]
        cases = report["monthly_cases"]
        if len(indices) != 72 or [case["decision_date_chicago"] for case in cases] != [sessions[i] for i in indices]:
            raise ValueError
        for index, case in zip(indices, cases):
            if index < 252 or case["required_intervals"] != 252:
                raise ValueError
            expected_dates = sessions[index - 251:index + 1]
            if case["status"] == "READY":
                if (case["valid_intervals"] != 252 or case["interval_dates"] != expected_dates
                        or case["window_first_endpoint"] != sessions[index - 252]
                        or len(case["dollar_movements"]) != 252
                        or any(len(row) != 5 for row in case["dollar_movements"])):
                    raise ValueError
                sizing._validated_signs(case["signs"])
            elif case["status"] == "DATA_INCOMPLETE":
                missing = case["missing_interval_dates"]
                if ("dollar_movements" in case or "signs" in case
                        or not isinstance(case["valid_intervals"], int)
                        or not 0 <= case["valid_intervals"] < 252
                        or missing != sorted(set(missing))
                        or not set(missing) <= set(expected_dates)
                        or len(missing) != 252 - case["valid_intervals"]):
                    raise ValueError
            else:
                raise ValueError
        expected_status = "READY" if all(case["status"] == "READY" for case in cases) else "DATA_INCOMPLETE"
        if report["status"] != expected_status:
            raise ValueError
    except (KeyError, TypeError, ValueError, ArithmeticError):
        raise RunnerError("invalid_input_report_or_frozen_design_mismatch") from None


def _stats(values):
    return {"count": len(values), "min": min(values) if values else None,
            "median": statistics.median(values) if values else None,
            "max": max(values) if values else None}


def _capital_summary(dates, equity):
    results = [day["capital_results"][str(equity)] for day in dates]
    counts = Counter(result["status"] for result in results)
    verified = [result for result in results if result["status"] == "OPTIMAL" and result["optimum_verified"]]
    nonzero = [result for result in verified if result["decision"] == "NONZERO"]
    cash = [result for result in verified if result["decision"] == "CASH"]
    complete = len(verified) == 72
    if complete and len(cash) == 72:
        verdict = "ALL_CASH_REJECT_CAPITAL_SPECIFICATION"
    elif complete:
        verdict = "COMPLETE_SIZING_PARTICIPATION_EVIDENCE"
    elif nonzero:
        verdict = "INCOMPLETE_STUDY_WITH_PARTICIPATION_EVIDENCE"
    else:
        verdict = "INCOMPLETE_STUDY_NO_CAPITAL_VERDICT"
    measured = [r for r in results if "annual_standalone_vol_usd" in r]
    return {
        "equity_usd": equity, "simulated_loss_budget_usd": equity / 5,
        "verdict": verdict, "expected_monthly_cases": 72,
        "input_ready_cases": sum(day["input_status"] == "READY" for day in dates),
        "input_incomplete_cases": counts["DATA_INCOMPLETE"],
        "invalid_risk_input_cases": counts["INVALID_RISK_INPUT"],
        "search_limit_cases": counts["SEARCH_LIMIT"],
        "optimum_verified_cases": len(verified), "cash_cases": len(cash), "nonzero_cases": len(nonzero),
        "participation_fraction_among_verified_cases": len(nonzero) / len(verified) if verified else None,
        "participation_denominator": "Only verified optimal cases; missing/invalid/unresolved cases are excluded, never treated as cash",
        "active_cases_by_market": {symbol: sum(bool(r["quantities"][i]) for r in nonzero)
                                   for i, symbol in enumerate(sizing.SYMBOLS)},
        "active_markets_nonzero_cases": _stats([sum(bool(n) for n in r["quantities"]) for r in nonzero]),
        "terminal_annual_dollar_vol_nonzero_cases": _stats([r["incumbent_terminal_annual_dollar_vol_usd"] for r in nonzero]),
        "terminal_annual_vol_fraction_of_post_entry_equity_nonzero_cases": _stats([
            r["incumbent_terminal_annual_dollar_vol_usd"] / r["incumbent_post_entry_equity_usd"] for r in nonzero]),
        "annual_one_contract_dollar_vol_by_market": {symbol: _stats([r["annual_standalone_vol_usd"][i] for r in measured])
                                                     for i, symbol in enumerate(sizing.SYMBOLS)},
        "scope": "Sizing participation only; neither a strategy-performance pass nor funded approval",
    }


def run_report(report, design, *, max_nodes=2_000_000, size_fn=None):
    """Pure in-memory integration seam; callers must verify file checksums."""
    validate_input_report(report, design)
    size_fn = sizing.size_stage_a if size_fn is None else size_fn
    dates = []
    for case in report["monthly_cases"]:
        day = {"decision_date_chicago": case["decision_date_chicago"],
               "input_status": case["status"], "capital_results": {}}
        if case["status"] == "DATA_INCOMPLETE":
            day["missing_interval_dates"] = case["missing_interval_dates"]
        else:
            day["window_first_endpoint"] = case["window_first_endpoint"]
            day["interval_first_date"] = case["interval_dates"][0]
            day["interval_last_date"] = case["interval_dates"][-1]
            day["signs"] = case["signs"]
        for equity in CAPITALS:
            if case["status"] == "DATA_INCOMPLETE":
                result = {"status": "DATA_INCOMPLETE", "optimum_verified": False,
                          "decision": "UNRESOLVED", "quantities": None}
            else:
                try:
                    result = size_fn(case["dollar_movements"], case["signs"], equity, max_nodes=max_nodes)
                except ValueError:
                    result = {"status": "INVALID_RISK_INPUT", "optimum_verified": False,
                              "decision": "UNRESOLVED", "quantities": None,
                              "reason": "Invalid, nonfinite, or zero-variance supplied sizing inputs; not a capital failure"}
            day["capital_results"][str(equity)] = result
        dates.append(day)
    summaries = {str(equity): _capital_summary(dates, equity) for equity in CAPITALS}
    return dates, {
        "schema": SCHEMA,
        "status": "COMPLETE_SIZING_ONLY" if all(s["optimum_verified_cases"] == 72 for s in summaries.values()) else "INCOMPLETE_STUDY",
        "primary_capital_verdict": summaries["5000"]["verdict"],
        "protocol_sha256": sizing.PROTOCOL_SHA256,
        "calendar_sha256": design["calendar_sha256"], "rolls_sha256": design["rolls_sha256"],
        "study_label": "Hypothetical child exposure applied to parent history; not historical child execution",
        "strategy_pnl_calculated": False, "raw_archives_reopened": False, "live_orders_submitted": False,
        "capital_summaries": summaries, "search_node_limit_per_case_per_capital": max_nodes,
        "limitations": [
            "Incomplete inputs and unverified optimization are not cash and do not establish capital failure.",
            "ALL_CASH rejection requires all 72 scheduled cases to have complete inputs and verified cash optima.",
            "A nonzero basket is sizing participation evidence only; no performance, liquidity, or funded pass is claimed.",
            "No path-dependent drawdown, future returns, native fills, or historical broker margin is modeled.",
        ],
    }


def runtime_provenance():
    code_paths = [Path(__file__), Path(sizing.__file__), Path(inputs.__file__), Path(inputs.archive.__file__)]
    code = [{"path": str(path.resolve()), "sha256": sha256_file(path)} for path in code_paths]
    distribution = importlib.metadata.distribution("numpy")
    library_files = []
    for item in sorted(distribution.files or (), key=str):
        name = str(item)
        if (name.startswith(("numpy/", "numpy.libs/")) and not name.endswith(".pyc")
                or name.endswith(".dist-info/RECORD") and name.startswith("numpy")):
            path = Path(distribution.locate_file(item))
            if path.is_file():
                library_files.append({"file": name, "sha256": sha256_file(path)})
    if not library_files:
        raise RunnerError("numpy_installed_file_manifest_unavailable")
    manifest_bytes = json.dumps(library_files, sort_keys=True, separators=(",", ":")).encode()
    return {
        "code_files": code,
        "python": {"version": sys.version, "implementation": platform.python_implementation(),
                   "executable": str(Path(sys.executable).resolve()), "executable_sha256": sha256_file(sys.executable)},
        "numpy": {"version": distribution.version, "installed_files_hashed": len(library_files),
                  "installed_file_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                  "installed_file_manifest": library_files},
        "platform": platform.platform(),
        "scope": "Actual runner/helper and installed NumPy file hashes plus Python executable/version; not a complete operating-system lockfile",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-nodes", type=int, default=2_000_000)
    args = parser.parse_args()
    try:
        if args.max_nodes < 1:
            raise RunnerError("node_limit_must_be_positive")
        design = inputs.load_design()
        raw = args.input.read_bytes()
        input_sha = hashlib.sha256(raw).hexdigest()
        if input_sha != args.input_sha256:
            raise RunnerError("input_checksum_mismatch")
        report = inputs.archive.load_json(raw)
        mapping_raw = args.mapping.read_bytes()
        if hashlib.sha256(mapping_raw).hexdigest() != report["mapping_sha256"]:
            raise RunnerError("mapping_checksum_mismatch")
        inputs.mapping_index(inputs.archive.load_json(mapping_raw), design)
        provenance = runtime_provenance()
        dates, summary = run_report(report, design, max_nodes=args.max_nodes)
        sizing.verify_frozen_protocol()
        if any(sha256_file(row["path"]) != row["sha256"] for row in provenance["code_files"]):
            raise RunnerError("implementation_changed_during_run")
        args.output_dir.mkdir(parents=True, exist_ok=False)
        files = []
        for day in dates:
            path = args.output_dir / (day["decision_date_chicago"] + ".json")
            path.write_text(json.dumps(day, indent=2, sort_keys=True, allow_nan=False) + "\n")
            files.append({"path": path.name, "sha256": sha256_file(path)})
        summary.update(created_utc=datetime.now(timezone.utc).isoformat(),
                       input={"path": str(args.input.resolve()), "sha256": input_sha},
                       mapping={"path": str(args.mapping.resolve()), "sha256": report["mapping_sha256"]},
                       runtime=provenance, per_date_files=files)
        target = args.output_dir / "summary.json"
        target.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
        print(json.dumps({"status": summary["status"], "primary_capital_verdict": summary["primary_capital_verdict"],
                          "summary": str(target), "summary_sha256": sha256_file(target)}))
        return 0 if summary["status"] == "COMPLETE_SIZING_ONLY" else 2
    except (RunnerError, inputs.InputError, inputs.archive.ArchiveError, OSError, KeyError, ValueError):
        print(json.dumps({"status": "RUNNER_FAILED", "failure": "Input, provenance, output, or risk-run validation failed; no capital verdict"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
