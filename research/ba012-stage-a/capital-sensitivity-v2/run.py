"""Run the two authorized larger-capital cases on pinned v2 inputs, offline."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import ba012_sizing as sizing
import prepare_ba012_settlements as settlements
import run_ba012_stage_a as original_runner


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    return {"path": str(path.relative_to(HERE)), "sha256": digest(path)}


def main():
    plan_path = HERE / "plan.json"
    plan_hash = digest(plan_path)
    assert plan_hash == plan_path.with_suffix(".json.sha256").read_text().split()[0]
    plan = json.loads(plan_path.read_text())
    assert plan["capitals_usd"] == [25000, 100000]
    for source in plan["inputs"]:
        assert digest(ROOT / source["path"]) == source["sha256"], source["path"]
    _, design = settlements.verified_design(
        ROOT / "research/ba012-stage-a/settlement-amendment-v2.json",
        ROOT / "research/ba012-stage-a/rolls-v2.json")
    source_path = ROOT / "research/ba012-stage-a/settlement-inputs-v2-continuation.json"
    source = json.loads(source_path.read_text())
    assert source["schema"] == settlements.SCHEMA
    assert source["amendment_sha256"] == settlements.AMENDMENT_SHA256
    assert source["base_protocol_sha256"] == sizing.PROTOCOL_SHA256
    assert source["calendar_sha256"] == design["calendar_sha256"]
    assert source["rolls_v2_sha256"] == design["rolls_sha256"]
    assert source["market_order"] == list(sizing.SYMBOLS)
    calendar = design["calendar"]["joint_sessions"]
    month_indices = [i for i, day in enumerate(calendar) if day >= "2018-01-01"
        and (i == len(calendar) - 1 or calendar[i + 1][:7] != day[:7])]
    cases = source["monthly_cases"]
    assert len(cases) == len(month_indices) == 72
    assert [x["decision_date_chicago"] for x in cases] == [calendar[i] for i in month_indices]
    for case, index in zip(cases, month_indices):
        assert case["required_intervals"] == 252
        if case["status"] == "READY":
            assert case["valid_intervals"] == 252
            assert case["interval_dates"] == calendar[index - 251:index + 1]
            assert case["window_first_endpoint"] == calendar[index - 252]
        else:
            assert case["status"] == "DATA_INCOMPLETE"
            assert "dollar_movements" not in case and "signs" not in case
    assert sum(x["status"] == "READY" for x in cases) == 25
    baseline = {x["decision_date_chicago"]: x["sizing"] for x in source["pilot_sizing"]["per_date"]}
    runtime = original_runner.runtime_provenance()
    script_hash = digest(Path(__file__))
    output = HERE / "results"
    output.mkdir(exist_ok=False)
    dates, files, solved = [], [], 0
    started = time.monotonic()
    for case in cases:
        day = {"decision_date_chicago": case["decision_date_chicago"], "input_status": case["status"],
               "capital_results": {"5000": baseline[case["decision_date_chicago"]]}}
        if case["status"] == "DATA_INCOMPLETE":
            day["missing_interval_dates"] = case["missing_interval_dates"]
        else:
            day.update(window_first_endpoint=case["window_first_endpoint"], signs=case["signs"])
        for equity in plan["capitals_usd"]:
            if case["status"] == "DATA_INCOMPLETE":
                result = {"status": "DATA_INCOMPLETE", "optimum_verified": False,
                          "decision": "UNRESOLVED", "quantities": None}
            else:
                result = sizing.size_stage_a(case["dollar_movements"], case["signs"], equity,
                                            max_nodes=plan["max_search_nodes_per_case"])
                solved += 1
                print(json.dumps({"completed_sizing_calls": solved, "of": 50,
                    "date": case["decision_date_chicago"], "equity": equity,
                    "status": result["status"], "decision": result["decision"],
                    "nodes": result["search"]["nodes"]}), flush=True)
            day["capital_results"][str(equity)] = result
        dates.append(day)
        files.append(save(output / (case["decision_date_chicago"] + ".json"), day))
    for source_item in plan["inputs"]:
        assert digest(ROOT / source_item["path"]) == source_item["sha256"]
    assert digest(Path(__file__)) == script_hash
    summaries = {str(equity): original_runner._capital_summary(dates, equity)
                 for equity in [5000] + plan["capitals_usd"]}
    summary = {"schema": "ba012-v2-capital-sensitivity-result-v1", "status": "INCOMPLETE_STUDY",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.monotonic() - started,
        "plan_sha256": plan_hash, "script_sha256": script_hash,
        "input": {"path": str(source_path), "sha256": digest(source_path), "schema": source["schema"]},
        "amendment_sha256": source["amendment_sha256"], "rolls_v2_sha256": source["rolls_v2_sha256"],
        "base_protocol_sha256": sizing.PROTOCOL_SHA256, "capital_summaries": summaries,
        "baseline_5000_reused": True, "new_sizing_calls": solved,
        "per_date_files": files, "runtime": runtime,
        "strategy_pnl_calculated": False, "additional_data_cost_usd": "0", "live_orders_submitted": False,
        "label": "Sizing participation on hypothetical child exposures applied to parent settlement history; no return, liquidity or funded pass"}
    target = HERE / "summary.json"
    save(target, summary)
    target.with_suffix(".json.sha256").write_text(digest(target) + "  " + target.name + "\n")
    print(json.dumps({"summary": str(target), "capital_counts": {key: {name: row[name]
        for name in ("verdict", "optimum_verified_cases", "nonzero_cases", "cash_cases", "search_limit_cases", "input_incomplete_cases")}
        for key, row in summaries.items()}}), flush=True)


if __name__ == "__main__":
    main()
