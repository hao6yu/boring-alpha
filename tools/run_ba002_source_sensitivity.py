#!/usr/bin/env python3
"""Offline BA-002 fixed-rule source sensitivity on its two already-seen windows.

This is a separately authorized diagnostic, not the formal BA-002 sweep API.
It never invents a ResearchContext, confirms a freeze, changes a journal, or
produces classification-compatible evidence. Each invocation evaluates one of
two whitelisted input methodologies on one complete fixed seen window. The
reference config supplies the unchanged rule and tax policy, NOT input paths.

Usage: .venv/bin/python tools/run_ba002_source_sensitivity.py --snapshot PATH
       --period development --output NEW_CASE_DIRECTORY
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import gzip
import hashlib
import json
import math
from pathlib import Path

from boring_alpha.backtest import Backtester
from boring_alpha.config import load_config
from boring_alpha.criteria_ba002 import MAX_DRAWDOWN, PRIMARY_MARGIN
from boring_alpha.data.calendar import SessionCalendar
from boring_alpha.data.csv_loader import load_csv_market_data_bytes
from boring_alpha.data.distributions import load_distributions_bytes
from boring_alpha.data.quality import QualityThresholds, enforce, inspect
from boring_alpha.metrics import calculate_metrics
from boring_alpha.profiles import BA002Profile
from boring_alpha.report import code_fingerprint, decisions_json, equity_csv, json_text, trades_csv, write_once_bytes
from boring_alpha.research_contract import canonical_sha256, evaluator_fingerprint, expected_account_map, expected_row_definitions
from boring_alpha.sweep import _cash_rows, _gzip_bytes, _gzip_csv, _price_rows
from boring_alpha.tax import OVERLAY_VERSION, policy_sha256, run_scenarios
from boring_alpha.tax.policy import SCENARIOS, policy_record
from boring_alpha.tax.reconcile import validate_replay
from boring_alpha.tax.reconstruct import reconstruct_result
from tools.check_ba002_seen_prices import bounded_local_bytes


ROOT = Path(__file__).resolve().parents[1]
KIND = "ba002-seen-source-sensitivity-v1"
START, END = date(2006, 2, 28), date(2021, 12, 31)
WINDOWS = {
    "development": (date(2007, 6, 1), date(2017, 12, 31)),
    "validation": (date(2018, 1, 1), END),
}
METHODS = frozenset({
    "yahoo-adjusted-v3-tlt-20121101+dgs3mo-v1",
    "tiingo-adjusted-v1-seen-splits+dgs3mo-v1",
})
POLICY_SHA256 = "9abb91e20b43a0d18a9e8404439145f13e5cf338d4eed4fd7363293146f54542"
INPUT_COLUMNS = {
    "market_daily.csv": ["date", "symbol", "tr_open", "tr_close"],
    "cash_daily.csv": ["date", "cash_factor"],
    "distributions_daily.csv": ["date", "symbol", "close", "dividend"],
}
CHECKS = ("share_identity_passed", "income_plus_gain_passed", "implied_price_check_passed")
RUNTIME_CODE_SHA256 = "a63a77df3adb569a6048336fdba40c775013fcd80fac3ad6a55002b09ea7dbb8"
RUNTIME_ARCHIVE_SHA256 = "b11169ebc882b6221387fbc90efcbb5c2e73645dfff53c703b2cfd3149e2b746"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def reference_config(period):
    if period not in WINDOWS:
        raise ValueError("only the two fixed already-seen periods are permitted")
    config = load_config(ROOT / "configs" / f"ba_002_{period}.toml")
    BA002Profile().validate_config(config)
    if config.strategy.strategy_id != "BA-002" or config.evaluation.period != period:
        raise ValueError("reference configuration has the wrong strategy or period")
    if (config.backtest.start, config.backtest.end) != WINDOWS[period] or (
        config.evaluation.start, config.evaluation.end
    ) != WINDOWS[period]:
        raise ValueError("reference configuration does not match the complete fixed seen window")
    if policy_sha256(config.tax) != POLICY_SHA256:
        raise ValueError("reference tax policy differs from the fixed stylized baseline")
    return config


def code_identity():
    scripts = {name: (Path(__file__).parent / name).read_bytes() for name in (
        "run_ba002_source_sensitivity.py", "build_ba002_source_snapshots.py",
        "check_ba002_seen_prices.py", "check_ba002_tiingo.py", "tiingo_seen_reference.py",
    )}
    identity = {
        "code_sha256": code_fingerprint(), "evaluator_sha256": evaluator_fingerprint(),
        "script_sha256": {name: digest(raw) for name, raw in scripts.items()},
    }
    return identity, scripts


def research_materials(identity):
    protocol = (ROOT / "docs/decisions/2026-09-05-ba002-source-sensitivity.md").read_bytes()
    archive = (ROOT / "research/ba002-seen-code-a63a77df3adb.tar.gz").read_bytes()
    if identity["code_sha256"] != RUNTIME_CODE_SHA256 or digest(archive) != RUNTIME_ARCHIVE_SHA256:
        raise ValueError("the reviewed runtime source archive no longer identifies the running implementation")
    return {"protocol.md": protocol, "code/runtime.tar.gz": archive}


def private_output(path):
    output, allowed = Path(path).resolve(), (ROOT / "experiments").resolve()
    if output == allowed or not output.is_relative_to(allowed):
        raise ValueError("licensed source-sensitivity artifacts must stay in a new directory under experiments")
    if output.exists():
        raise FileExistsError("source-sensitivity output already exists; it will not be overwritten")
    return output


def load_inputs(snapshot, period, config, calendar):
    """Read once, check source hashes, then date-filter before numeric loaders."""
    end = WINDOWS[period][1]
    snapshot = Path(snapshot)
    manifest_raw = (snapshot / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest.get("methodology") not in METHODS or manifest.get("synthetic") is not False or manifest.get("complete") is not True:
        raise ValueError("snapshot is not one of the two reviewed source methodologies")
    if (manifest.get("start"), manifest.get("end"), manifest.get("calendar_sha256")) != (str(START), str(END), calendar.sha256):
        raise ValueError("snapshot bounds or calendar differ from the fixed seen range")
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict) or not set(INPUT_COLUMNS) <= set(hashes) or set(hashes) - set(INPUT_COLUMNS) - {"issuer_evidence.json"}:
        raise ValueError("snapshot manifest requires the three CSV hashes and only optional issuer evidence")
    sources = {name: (snapshot / name).read_bytes() for name in hashes}
    for name, raw in sources.items():
        if hashes[name] != digest(raw):
            raise ValueError(f"snapshot checksum mismatch: {name}")
    # The shared helper applies the hard 2006-02-28..2021-12-31 outer cap;
    # the numerical loaders then apply this case's (possibly earlier) end.
    bounded = {name: bounded_local_bytes(sources[name], columns) for name, columns in INPUT_COLUMNS.items()}
    data = load_csv_market_data_bytes(bounded["market_daily.csv"], bounded["cash_daily.csv"], end=end)
    table = load_distributions_bytes(bounded["distributions_daily.csv"], manifest_block=manifest, end=end)
    if set(data.symbols) != set(config.strategy.symbols) or set(table.symbols) != set(config.strategy.symbols):
        raise ValueError("snapshot price/distribution universe is not the exact fixed eight ETFs")
    if data.dates[0] < START or data.dates[-1] > end or table.dates[0] < START or table.dates[-1] > end:
        raise ValueError("bounded loaders returned observations outside this case")
    if calendar.synthetic:
        raise ValueError("a synthetic calendar cannot validate a historical source diagnostic")
    calendar.validate_inputs(data, table, config.strategy.symbols, *WINDOWS[period], (9, 12, 15), warmup_months=15)
    data.warnings = tuple(enforce(inspect(data, config.strategy.symbols, QualityThresholds())))
    return (data, table, manifest, manifest_raw, {name: digest(raw) for name, raw in sources.items()},
            {name: raw for name, raw in sources.items() if name not in INPUT_COLUMNS})


def checked_tax(scenarios, tax, table, identity):
    """Fail invalid accounting before any descriptive performance comparison."""
    if set(scenarios) != {scenario.key for scenario in SCENARIOS}:
        raise ValueError("source diagnostic requires every fixed tax scenario")
    for scenario in SCENARIOS:
        record = scenarios[scenario.key]
        if record.get("scenario") != scenario.as_dict() or "loss_sensitivity" in record:
            raise ValueError("tax scenario differs from the fixed non-deduction grid")
        policy = record.get("policy", {})
        expected = {
            **policy_record(tax), "tax_policy_sha256": POLICY_SHA256,
            "distributions_sha256": table.sha256, "overlay_version": OVERLAY_VERSION,
            "code_sha256": identity["code_sha256"],
        }
        if any(policy.get(key) != value for key, value in expected.items()):
            raise ValueError("tax scenario policy, source, or code identity differs")
        if any(record.get("identity_checks", {}).get(check) is not True for check in CHECKS):
            raise ValueError("tax accounting identity check failed")
        cagr = record.get("metrics", {}).get("after_tax_cagr")
        wealth = record.get("wealth", {}).get("after_tax_post_liquidation")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in (cagr, wealth)) or wealth <= 0:
            raise ValueError("post-liquidation after-tax comparison is undefined or non-finite")
    json.dumps(scenarios, allow_nan=False)


def summarize_row(row_id, metrics, scenarios):
    returns = {
        role: {key: Decimal(str(value["metrics"]["after_tax_cagr"])) for key, value in records.items()}
        for role, records in scenarios.items()
    }
    worst, best = min(returns["strategy"].values()), max(returns["benchmark"].values())
    margin = worst - best
    drawdowns = {}
    for role in ("strategy", "benchmark"):
        value = metrics[role]["max_drawdown"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -1 <= value <= 0:
            raise ValueError("invalid pre-tax drawdown metric")
        drawdowns[role] = -Decimal(str(value))
    return_ok = margin >= PRIMARY_MARGIN if row_id == "base" else margin > 0
    risk_ok = drawdowns["strategy"] <= MAX_DRAWDOWN and drawdowns["strategy"] <= drawdowns["benchmark"]
    return {
        "worst_strategy_after_tax_cagr": float(worst), "best_benchmark_after_tax_cagr": float(best),
        "independent_extrema_margin_bps_per_year": float(margin * 10000),
        "matched_scenario_margin_bps_per_year": {
            key: float((returns["strategy"][key] - returns["benchmark"][key]) * 10000)
            for key in returns["strategy"]
        },
        "strategy_pre_tax_cost_net_drawdown": float(drawdowns["strategy"]),
        "benchmark_pre_tax_cost_net_drawdown": float(drawdowns["benchmark"]),
        "descriptive_original_threshold_comparison": {
            "primary_margin_min_bps": 50 if row_id == "base" else None,
            "stress_margin_strictly_positive": row_id != "base",
            "return_threshold_met": return_ok, "drawdown_thresholds_met": risk_ok,
            "all_original_numeric_thresholds_met": return_ok and risk_ok,
            "formal_eligibility": False,
        },
    }


def run_case(snapshot, period, output):
    """One complete source/window case; refuses any pre-existing output path."""
    output = private_output(output)
    config = reference_config(period)
    identity, script_bytes = code_identity()
    materials = research_materials(identity)
    calendar = SessionCalendar.load(config.research.calendar_path)
    data, table, source_manifest, source_manifest_raw, source_hashes, source_extras = load_inputs(snapshot, period, config, calendar)
    if source_manifest.get("builder_sha256") != identity["script_sha256"]["build_ba002_source_snapshots.py"]:
        raise ValueError("snapshot builder identity differs from the archived builder implementation")
    profile = BA002Profile()
    grid = profile.grid(config)
    definitions = expected_row_definitions()
    if tuple(grid) != tuple(definitions):
        raise ValueError("profile grid differs from the fixed five-row definition")
    rule = {
        "strategy": asdict(config.strategy), "portfolio": asdict(config.portfolio),
        "execution": asdict(config.execution), "benchmark": asdict(config.benchmark),
        "rows": definitions, "tax_policy_sha256": POLICY_SHA256,
    }
    case_identity = {
        "kind": KIND, "period": period, "window": [str(day) for day in WINDOWS[period]],
        "methodology": source_manifest["methodology"], "source_sha256": source_hashes,
        "source_manifest_sha256": digest(source_manifest_raw), "rule_sha256": canonical_sha256(rule),
        "reference_config_sha256": digest(config.raw_bytes), "calendar_sha256": calendar.sha256,
        "protocol_sha256": digest(materials["protocol.md"]),
        "runtime_archive_sha256": digest(materials["code/runtime.tar.gz"]),
        **identity,
    }
    case_id = canonical_sha256(case_identity)[:16]
    output.mkdir(parents=True, exist_ok=False)
    artifacts = {}

    def publish(name, raw):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        write_once_bytes(target, raw)
        artifacts[name] = digest(raw)

    publish("input_prices.csv.gz", _gzip_csv(_price_rows(data)))
    publish("input_cash.csv.gz", _gzip_csv(_cash_rows(data)))
    publish("input_distributions.csv.gz", _gzip_bytes(table.canonical_csv()))
    publish("source_manifest.json", source_manifest_raw)
    for name, raw in source_extras.items():
        publish(f"source/{name}", raw)
    publish("calendar.json", calendar.canonical_bytes())
    publish("reference_config.toml", config.raw_bytes)
    publish("rule.json", json_text(rule).encode())
    publish("account_map.json", json_text(expected_account_map()).encode())
    for name, raw in script_bytes.items():
        publish(f"code/{name}", raw)
    for name, raw in materials.items():
        publish(name, raw)
    notes = {
        "kind": KIND, "formal_eligibility": False,
        "reference_config_path": str(config.path),
        "reference_config_role": "Fixed trading rule, tax scenario policy and exact seen window only. Its original input/freeze/report paths are NOT used.",
        "actual_snapshot": str(Path(snapshot).resolve()), "actual_methodology": source_manifest["methodology"],
        "actual_source_sha256": source_hashes,
        "reference_strategy_spec_sha256": config.strategy_spec_sha256,
        "reference_strategy_spec_scope": "The old config identity includes its original Yahoo-v2 source; this is not the identity of the current diagnostic input.",
        "evidence_status": "already-seen source sensitivity, not formal advancement evidence",
        "authorization_scope": "Two reviewed methodologies, two seen windows, unchanged five-row rule and eight tax scenarios. No holdout, live trading, or formal classification.",
        "omitted_formal_sweep_diagnostics": "No ex-post exposure-matched account, full-static account, cash-only account, 12-month reference, or Sharpe bootstrap; all five required strategy/benchmark pairs are present.",
    }
    publish("configuration_notes.json", json_text(notes).encode())

    # Rehydrate exactly the archived bounded inputs, not mutable source paths.
    replay_data = load_csv_market_data_bytes(gzip.decompress((output / "input_prices.csv.gz").read_bytes()),
                                            gzip.decompress((output / "input_cash.csv.gz").read_bytes()), end=WINDOWS[period][1])
    replay_table = load_distributions_bytes(gzip.decompress((output / "input_distributions.csv.gz").read_bytes()),
                                            manifest_block=source_manifest, end=WINDOWS[period][1])
    if replay_data.fingerprint() != data.fingerprint() or replay_table.sha256 != table.sha256:
        raise ValueError("archived inputs do not reproduce their semantic fingerprints")
    calendar.validate_inputs(replay_data, replay_table, config.strategy.symbols, *WINDOWS[period], (9, 12, 15), warmup_months=15)
    summary, all_metrics, all_tax, verification, warnings = {}, {}, {}, {}, list(data.warnings)
    for row_id, spec in grid.items():
        signals = {"strategy": spec.strategy(config, None), "benchmark": spec.benchmark(config)}
        actual_definition = {
            "horizons": list(signals["strategy"].horizons), "warmup_months": signals["strategy"].warmup_months,
            "cost_bps": spec.cost_bps, "benchmark": {"exposure": signals["benchmark"].exposure,
                "rebalance": signals["benchmark"].rebalance, "cost_bps": spec.cost_bps},
        }
        if actual_definition != definitions[row_id]:
            raise ValueError("profile row differs from the fixed strategy/benchmark pairing")
        row_metrics, row_tax, row_checks = {}, {}, {}
        for role, signal in signals.items():
            result = Backtester(replay_data, config.strategy.symbols, initial_cash=config.portfolio.initial_cash,
                                cost_bps=spec.cost_bps, start=WINDOWS[period][0], end=WINDOWS[period][1]).run(signal)
            prefix = f"variants/{row_id}/{role}"
            publish(f"{prefix}_equity.csv", equity_csv(result).encode())
            publish(f"{prefix}_trades.csv", trades_csv(result).encode())
            publish(f"{prefix}_decisions.json", decisions_json(result).encode())
            publish(f"{prefix}_orders.json", json_text([asdict(order) for order in result.orders]).encode())
            reconstructed = reconstruct_result(result.name, output / f"{prefix}_equity.csv",
                                               output / f"{prefix}_trades.csv", config.portfolio.initial_cash)
            validate_replay(reconstructed, replay_data, config.portfolio.initial_cash)
            calendar.validate_output_sessions(tuple(point.date for point in reconstructed.equity_curve), *WINDOWS[period])
            row_metrics[role] = calculate_metrics(reconstructed, replay_data)
            row_tax[role] = run_scenarios(reconstructed, replay_data, replay_table, config.tax,
                                         initial_cash=config.portfolio.initial_cash, code_sha256=identity["code_sha256"])
            checked_tax(row_tax[role], config.tax, replay_table, identity)
            row_checks[role] = {"archived_fill_account_replay_passed": True, "exact_calendar_passed": True,
                                "all_eight_tax_scenario_identities_passed": True}
            warnings.extend(f"{row_id}/{role}: {warning}" for warning in result.warnings)
            publish(f"{prefix}_tax.json", json_text(row_tax[role]).encode())
        summary[row_id] = summarize_row(row_id, row_metrics, row_tax)
        all_metrics[row_id], all_tax[row_id], verification[row_id] = row_metrics, row_tax, row_checks
        print(f"{source_manifest['methodology']} / {period} / {row_id}: completed paired eight-scenario diagnostic", flush=True)
    publish("metrics.json", json_text(all_metrics).encode())
    publish("tax.json", json_text(all_tax).encode())
    publish("summary.json", json_text({"kind": KIND, "formal_eligibility": False, "rows": summary}).encode())
    publish("verification.json", json_text(verification).encode())
    if code_identity()[0] != identity:
        raise ValueError("code or diagnostic script changed during execution; refusing complete publication")
    if {name: digest(raw) for name, raw in research_materials(identity).items()} != {
        name: digest(raw) for name, raw in materials.items()
    }:
        raise ValueError("protocol or runtime archive changed during execution")
    for name, expected_hash in artifacts.items():
        if digest((output / name).read_bytes()) != expected_hash:
            raise ValueError("diagnostic artifact changed before completion")
    manifest = {
        "kind": KIND, "diagnostic_schema": 1, "formal_eligibility": False, "complete": True,
        "case_id": case_id, "identity": case_identity, "rows": definitions,
        "source_methodology": source_manifest["methodology"], "period": period,
        "data_sha256": replay_data.fingerprint(), "distributions_sha256": replay_table.sha256,
        "tax_policy_sha256": POLICY_SHA256, "accounts": 10, "tax_scenarios_per_account": 8,
        "account_map": expected_account_map(), "warnings": warnings,
        "artifacts_sha256": artifacts,
        "scope": "Exploratory source-sensitivity diagnostic only. No formal BA-002 eligibility, freeze, journal, or holdout action.",
    }
    # Deliberately no artifact_schema/sweep_id/criteria.json: standard readers
    # cannot reinterpret these conditional results as formal BA-002 evidence.
    write_once_bytes(output / "manifest.json", json_text(manifest).encode())
    return manifest, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--period", choices=tuple(WINDOWS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest, summary = run_case(args.snapshot, args.period, args.output)
    print(json_text({"kind": KIND, "formal_eligibility": False, "case_id": manifest["case_id"],
                     "artifacts": str(args.output.resolve()), "rows": summary}))


if __name__ == "__main__":
    main()
