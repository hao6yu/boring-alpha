"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

from boring_alpha.backtest import Backtester
from boring_alpha.config import (
    DATASET_END,
    UNBOUNDED_PERIOD,
    AppConfig,
    load_config,
    load_tax_policy,
)
from boring_alpha.data import load_market_data
from boring_alpha.data.distributions import FINGERPRINT_VERSION, load_distributions
from boring_alpha.evaluation import SealedRunError, check_evaluation_gates
from boring_alpha.metrics import calculate_metrics
from boring_alpha.report import (
    ARTIFACT_SCHEMA,
    code_fingerprint,
    json_text,
    write_once,
    write_report,
)
from boring_alpha.criteria import Verdict
from boring_alpha.profiles import profile_for
from boring_alpha.research_access import open_run
from boring_alpha.signals import CashAllocation
from boring_alpha.sweep import benchmark_description, run_sweep, write_sweep_report
from boring_alpha.tax import OVERLAY_VERSION, policy_sha256, run_scenarios
from boring_alpha.tax.reconcile import validate_replay
from boring_alpha.tax.reconstruct import (
    gunzip_to,
    initial_cash_from,
    market_data_from_archive,
    read_manifest,
    reconstruct_result,
    require_run_window,
    run_files,
    symbols_from,
    verify_archive_artifacts,
)

__all__ = [
    "SealedRunError",
    "check_evaluation_gates",
    "build_parser",
    "main",
    "run_aftertax",
    "run_backtest",
]


def _banners(config: AppConfig, run_context=None) -> list[str]:
    """Everything a reader must not miss about what this run is worth.

    Printed above and below the metrics table, because the table is where a
    reader forms an impression that a footnote will not undo.
    """

    banners: list[str] = []
    if config.data.source == "synthetic":
        banners.append("SYNTHETIC DATA — OUTPUT HAS NO ECONOMIC MEANING")
    if not config.evaluation.is_evidence:
        banners.append(
            f"EXPLORATORY RUN — NOT EVIDENCE ABOUT {config.strategy.strategy_id} "
            "(unbounded window, no sealing)"
        )
    if run_context is not None and run_context.revealed_diagnostic:
        banners.append("REVEALED-DATA REPAIR — DIAGNOSTIC ONLY, NOT A FRESH HOLDOUT")
    elif config.strategy.strategy_id == "BA-002" and config.data.source != "synthetic":
        banners.append("RETROSPECTIVE HOLDOUT — unopened at freeze, now evaluated"
                       if config.evaluation.period == "sealed" else
                       "SEEN RESEARCH HISTORY — NOT INDEPENDENT VALIDATION")
    return banners


def _percentage(value: float) -> str:
    return f"{value * 100:8.2f}%"


def run_backtest(config_path: Path, unseal_reason: str | None = None, **options) -> int:
    config = load_config(config_path)
    with open_run(config, unseal_reason, **options) as run:
        return _run_backtest_loaded(config, run.data, unseal_reason, run.context)

def _run_backtest_loaded(config: AppConfig, data, unseal_reason, run_context) -> int:
    profile = profile_for(config.strategy.strategy_id)
    primary = profile.grid(config)["base"]
    if config.strategy.strategy_id == "BA-002":
        from boring_alpha.research_access import validate_ba002_inputs
        from boring_alpha.sweep import _distributions_for
        run_context.verify()
        table, _, _ = _distributions_for(config, data, run_context)
        validate_ba002_inputs(config, data, table, run_context)
    engine = Backtester(
        data,
        config.strategy.symbols,
        initial_cash=config.portfolio.initial_cash,
        cost_bps=config.execution.cost_bps,
        start=config.backtest.start,
        end=config.backtest.end,
    )
    strategy = engine.run(primary.strategy(config, None))
    benchmark = engine.run(primary.benchmark(config))
    cash = engine.run(CashAllocation(config.strategy.symbols))
    strategy_metrics = calculate_metrics(strategy, data)
    benchmark_metrics = calculate_metrics(benchmark, data)
    cash_metrics = calculate_metrics(cash, data)
    run_id, run_dir = write_report(
        config,
        data,
        strategy,
        benchmark,
        cash,
        strategy_metrics,
        benchmark_metrics,
        cash_metrics,
        unseal_reason=unseal_reason,
        run_context=run_context,
    )
    run_context.artifact_path = str(run_dir)

    banners = _banners(config, run_context)
    print(f"BoringAlpha run {run_id}")
    for banner in banners:
        print(banner)
    if config.data.source != "synthetic":
        print(data.source)
    period = config.evaluation.period
    window = (
        "unbounded"
        if period == UNBOUNDED_PERIOD
        else f"{config.evaluation.start}..{config.evaluation.end or DATASET_END}"
    )
    print(f"Evaluation period: {period} ({window})")
    print(f"Benchmark: {benchmark_description(config)}")
    if config.strategy.strategy_id == "BA-002":
        print("Primary ensemble diagnostic only; use sweep for the complete after-tax research screen.")
    print(f"{'Metric':<24}{'Strategy':>14}{'Static':>14}{'Cash':>14}")
    print(f"{'Total return':<24}{_percentage(float(strategy_metrics['total_return'])):>14}{_percentage(float(benchmark_metrics['total_return'])):>14}{_percentage(float(cash_metrics['total_return'])):>14}")
    print(f"{'CAGR':<24}{_percentage(float(strategy_metrics['cagr'])):>14}{_percentage(float(benchmark_metrics['cagr'])):>14}{_percentage(float(cash_metrics['cagr'])):>14}")
    print(f"{'Volatility':<24}{_percentage(float(strategy_metrics['annualized_volatility'])):>14}{_percentage(float(benchmark_metrics['annualized_volatility'])):>14}{_percentage(float(cash_metrics['annualized_volatility'])):>14}")
    print(f"{'Max drawdown':<24}{_percentage(float(strategy_metrics['max_drawdown'])):>14}{_percentage(float(benchmark_metrics['max_drawdown'])):>14}{_percentage(float(cash_metrics['max_drawdown'])):>14}")
    print(f"{'Sharpe vs cash':<24}{float(strategy_metrics['sharpe_vs_cash']):>14.2f}{float(benchmark_metrics['sharpe_vs_cash']):>14.2f}{float(cash_metrics['sharpe_vs_cash']):>14.2f}")
    warnings = list(data.warnings) + [
        warning for result in (strategy, benchmark, cash) for warning in result.warnings
    ]
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"  - {warning}")
    if unseal_reason:
        print(f"SEALED RUN unsealed: {unseal_reason}")
        print(f"Record this run in the {config.strategy.strategy_id} charter change log.")
    for banner in banners:
        print(banner)
    print(f"Artifacts: {run_dir}")
    return 0


def run_sweep_command(config_path: Path, unseal_reason: str | None = None, **options) -> int:
    config = load_config(config_path)
    with open_run(config, unseal_reason, **options) as run:
        return _run_sweep_loaded(config, run.data, unseal_reason, run.context)

def _run_sweep_loaded(config, data, unseal_reason, run_context) -> int:
    sweep = run_sweep(config, data, run_context=run_context)
    sweep_id, sweep_dir = write_sweep_report(config, data, sweep, unseal_reason=unseal_reason)
    run_context.artifact_path = str(sweep_dir)

    banners = _banners(config, run_context)
    print(f"BoringAlpha sweep {sweep_id} ({config.evaluation.period} period)")
    for banner in banners:
        print(banner)
    for criterion in sweep.outcome.criteria:
        print(f"  {criterion.name} {'pass' if criterion.passed else 'FAIL'}: {criterion.detail}")
    print(f"All criteria passed for this period: {'yes' if sweep.outcome.passed else 'NO'}")
    print("Research eligibility needs both seen periods: boring-alpha classify <development> <validation>"
          if config.strategy.strategy_id == "BA-002" else
          "A verdict needs both periods: boring-alpha classify <development> <validation>")
    for warning in list(data.warnings) + list(sweep.warnings):
        print(f"  - {warning}")
    if unseal_reason:
        print(f"SEALED SWEEP unsealed: {unseal_reason}")
        print(f"Record this sweep in the {config.strategy.strategy_id} charter change log.")
    for banner in banners:
        print(banner)
    print(f"Artifacts: {sweep_dir}")
    return 0


def _read_criteria(sweep_dir: Path, expected_period: str) -> dict:
    try:
        criteria = json.loads((sweep_dir / "criteria.json").read_text(encoding="utf-8"))
        period = criteria["evaluation_period"]
    except (KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"{sweep_dir} does not hold a readable sweep: {exc}") from exc
    if period != expected_period:
        raise ValueError(f"{sweep_dir} holds a {period} sweep, expected {expected_period}")
    return criteria


def run_classify(development_dir: Path, validation_dir: Path, freeze_path: Path | None = None) -> int:
    development = _read_criteria(development_dir, "development")
    validation = _read_criteria(validation_dir, "validation")

    if development.get("strategy_id") == "BA-002" or validation.get("strategy_id") == "BA-002":
        from boring_alpha.ba002_artifacts import load_ba002_evidence
        from boring_alpha.criteria_ba002 import classify, evaluate_period
        first = load_ba002_evidence(development_dir, freeze_path)
        second = load_ba002_evidence(validation_dir, freeze_path)
        verdict = classify(first, second)
        print("SYNTHETIC DATA — NO ECONOMIC MEANING" if first.synthetic else
              "SEEN RESEARCH HISTORY — NOT INDEPENDENT VALIDATION")
        print(f"BA-002 research eligibility: {verdict.value}")
        for label, evidence in (("Seen research A", first), ("Seen research B", second)):
            print(f"\n{label}: {evidence.start}..{evidence.end}")
            for criterion in evaluate_period(evidence).criteria:
                print(f"  {criterion.name} {'pass' if criterion.passed else 'FAIL'}: {criterion.detail}")
        print("\nEligibility is not authorization to reveal a holdout or trade.")
        return 0

    # A verdict combining two unrelated sweeps would be confidently wrong. The
    # inputs must agree on everything except the window they cover, and a field
    # that is merely absent proves nothing — so absence is refused too, rather
    # than skipped.
    for field, message in (
        ("artifact_schema", "different artifact schemas"),
        ("strategy_id", "different strategies"),
        ("strategy_spec_sha256", "different strategy definitions"),
        ("code_sha256", "different code revisions"),
    ):
        for label, criteria in (("development", development), ("validation", validation)):
            if field not in criteria:
                raise ValueError(
                    f"the {label} sweep records no {field}; it predates the checks that "
                    "make a verdict trustworthy. Re-run the sweep on current code."
                )
        if development[field] != validation[field]:
            raise ValueError(
                f"refusing to classify {message}: "
                f"{field} is {development[field]!r} in the development sweep and "
                f"{validation[field]!r} in the validation sweep"
            )
    schema = development["artifact_schema"]
    if type(schema) is not int or schema not in (5, 6):
        readable = "5, 6 (BA-001); schema 7 requires complete BA-002 evidence"
        raise ValueError(
            f"these sweeps use artifact schema {schema}, but this code reads schemas "
            f"{readable}. Re-run them rather than comparing artifacts across schema versions."
        )
    # A tax policy is part of what was scored. Two sweeps scored under different
    # policies, or one scored and one not, cannot share a verdict.
    policies = (development.get("tax_policy_sha256"), validation.get("tax_policy_sha256"))
    if (policies[0] is not None or policies[1] is not None) and policies[0] != policies[1]:
        raise ValueError(
            "refusing to classify different tax policies: tax_policy_sha256 is "
            f"{policies[0]!r} in the development sweep and {policies[1]!r} in the "
            "validation sweep"
        )

    strategy_id = development["strategy_id"]
    profile = profile_for(strategy_id)
    verdict = profile.classify(development["variants"], validation["variants"])

    print(f"{strategy_id} classification: {verdict.value.upper()}")
    for label, criteria in (("development", development), ("validation", validation)):
        print(f"\n{label}:")
        for criterion in criteria["criteria"]:
            print(
                f"  {criterion['name']} {'pass' if criterion['passed'] else 'FAIL'}: "
                f"{criterion['detail']}"
            )
    if verdict is Verdict.INCONCLUSIVE:
        print(
            "\nInconclusive is a real outcome, not a failure to decide. "
            "Record it in the registry rather than searching for a variant that advances."
        )
    print("\nWrite the decision under docs/reviews/ without changing the charter retroactively.")
    return 0


def run_aftertax(sweep_dir: Path, policy_path: Path, distributions_path: Path | None = None) -> int:
    """Score an existing sweep after tax under a policy file (spec §7).

    Runs are rebuilt from the archived equity curves and trade ledgers and the
    archived prices and cash. Distributions come from `--distributions` (with the
    snapshot manifest beside it) or, when the sweep archived them, from the sweep
    itself. The output is named by every input including the overlay's code
    fingerprint, so a corrected overlay produces a separately identified result
    and identical inputs are idempotent.
    """

    manifest = read_manifest(sweep_dir)
    archived_files_status = verify_archive_artifacts(sweep_dir, manifest)
    files = run_files(sweep_dir, manifest)
    symbols = symbols_from(manifest)
    initial_cash = initial_cash_from(manifest)
    policy = load_tax_policy(policy_path, symbols)
    data = market_data_from_archive(sweep_dir, manifest)

    if distributions_path is not None:
        manifest_path = distributions_path.parent / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"no manifest.json beside {distributions_path}; a v2 snapshot is required")
        snapshot = json.loads(manifest_path.read_text(encoding="utf-8"))
        table = load_distributions(distributions_path, manifest_path=manifest_path, end=data.dates[-1])
        provenance = {
            "source": "external-snapshot",
            "source_path": str(distributions_path),
            "source_sha256": table.source_sha256,
            "created_at": snapshot.get("created_at"),
        }
        distribution_status = "external snapshot: canonical input fingerprint recorded"
    else:
        archived = sweep_dir / "input_distributions.csv.gz"
        block = manifest.get("distributions_manifest")
        if not archived.is_file() or block is None:
            raise ValueError(
                f"{sweep_dir} archived no distributions; pass --distributions with the "
                "snapshot's distributions_daily.csv"
            )
        with tempfile.TemporaryDirectory() as directory:
            unpacked = Path(directory) / "distributions_daily.csv"
            gunzip_to(archived, unpacked)
            table = load_distributions(unpacked, manifest_block=block)
        version = block.get("fingerprint_version")
        if version is not None and version != FINGERPRINT_VERSION:
            raise ValueError(f"unsupported distributions fingerprint version: {version!r}")
        if version == FINGERPRINT_VERSION:
            if (
                table.sha256 != block.get("sha256")
                or table.sha256 != manifest.get("distributions_sha256")
                or table.csv_sha256 != block.get("csv_sha256")
            ):
                raise ValueError("archived distributions fingerprint does not match the sweep manifest")
            distribution_status = "verified"
        else:
            # Old sweeps stored a full snapshot hash beside a truncated CSV.
            # That claimed source hash cannot verify the bytes now in hand.
            distribution_status = "legacy-unverified: no canonical archive fingerprint was recorded"
        snapshot = block
        provenance = {
            "source": "sweep-archive",
            "archive_csv_sha256": table.source_sha256,
            "legacy_claimed_source_sha256": block.get("sha256") if version is None else None,
        }
    table = table.through(data.dates[-1])
    table.require_coverage(data, symbols)
    block = {
        "methodology": table.methodology,
        "splits": table.splits,
        "sha256": table.sha256,
        "csv_sha256": table.csv_sha256,
        "fingerprint_version": FINGERPRINT_VERSION,
    }

    code_hash = code_fingerprint()
    runs: dict[str, dict] = {}
    for name, equity_path, trades_path in files:
        result = reconstruct_result(name, equity_path, trades_path, initial_cash)
        require_run_window(result, data, manifest)
        validate_replay(result, data, initial_cash)
        runs[name] = run_scenarios(
            result, data, table, policy, initial_cash=initial_cash, code_sha256=code_hash
        )

    policy_hash = policy_sha256(policy)
    output = sweep_dir / f"tax-{policy_hash[:12]}-{table.sha256[:12]}-{code_hash[:12]}.json"
    write_once(
        output,
        json_text(
            {
                "artifact_schema": manifest["artifact_schema"] if manifest["strategy_id"] == "BA-002" else ARTIFACT_SCHEMA,
                "sweep_id": manifest["sweep_id"],
                "strategy_id": manifest["strategy_id"],
                "code_sha256": code_hash,
                "source": "aftertax",
                "tax_policy_sha256": policy_hash,
                "distributions_sha256": table.sha256,
                "distributions_manifest": block,
                "overlay_version": OVERLAY_VERSION,
                "runs": runs,
            }
        ),
    )
    provenance.update({
        "artifact": output.name,
        "archived_files_verification": archived_files_status,
        "market_data_verification": "verified",
        "distributions_verification": distribution_status,
    })
    with (sweep_dir / "distributions_provenance.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(provenance, sort_keys=True) + "\n")

    print(f"BoringAlpha aftertax {manifest['sweep_id']} ({manifest['strategy_id']}), policy {policy_hash[:12]}")
    if manifest["strategy_id"] == "BA-002":
        print("DIAGNOSTIC RESCORE — does not replace the frozen eligibility tax.json")
    if "benchmark" in manifest:
        print(f"Benchmark: {manifest['benchmark']}")
    for status in (archived_files_status, distribution_status):
        if status.startswith("legacy-unverified"):
            print(f"Archive provenance: {status}")
    print(f"{'Run':<24}{'Pre-tax CAGR':>14}{'After-tax worst':>17}{'Worst scenario':>24}{'Best':>10}")
    for name, scenarios in runs.items():
        def rank(key: str) -> float:
            cagr = scenarios[key]["metrics"]["after_tax_cagr"]
            return cagr if cagr is not None else float("-inf")

        def render(value: float | None) -> str:
            return "n/a" if value is None else f"{value:.4f}"

        worst_key = min(scenarios, key=rank)
        best_key = max(scenarios, key=rank)
        worst = scenarios[worst_key]["metrics"]
        print(
            f"{name:<24}{worst['pre_tax_cagr']:>14.4f}{render(worst['after_tax_cagr']):>17}"
            f"{worst_key:>24}{render(scenarios[best_key]['metrics']['after_tax_cagr']):>10}"
        )
        for scenario_name, scenario in scenarios.items():
            failed = [
                check for check in ("share_identity_passed", "income_plus_gain_passed", "implied_price_check_passed")
                if not scenario["identity_checks"][check]
            ]
            if failed:
                print(f"  identity checks failed for {name} / {scenario_name}: {', '.join(failed)}")
    print(f"Written: {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="boring-alpha", description="No free lunch. No magic backtests."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    backtest = subparsers.add_parser("backtest", help="run a configured backtest")
    backtest.add_argument("config", type=Path, help="path to a TOML configuration")
    backtest.add_argument(
        "--unseal",
        metavar="REASON",
        help="run a sealed evaluation period; the reason is recorded in the provenance log",
    )

    sweep = subparsers.add_parser(
        "sweep", help="run the charter's pre-registered grid for one period"
    )
    sweep.add_argument("config", type=Path, help="path to a TOML configuration")
    sweep.add_argument(
        "--unseal",
        metavar="REASON",
        help="run a sealed evaluation period; the reason is recorded in the provenance log",
    )

    classify_parser = subparsers.add_parser(
        "classify", help="classify a strategy from its development and validation sweeps"
    )
    classify_parser.add_argument("development", type=Path, help="development sweep directory")
    classify_parser.add_argument("validation", type=Path, help="validation sweep directory")
    classify_parser.add_argument(
        "--freeze", type=Path, default=None,
        help="independently confirmed freeze record for historical BA-002 classification",
    )

    aftertax = subparsers.add_parser(
        "aftertax", help="score an existing sweep after tax under a policy file"
    )
    aftertax.add_argument("sweep", type=Path, help="sweep directory to re-score")
    aftertax.add_argument(
        "--policy", type=Path, required=True, help="TOML file holding only a [tax] table"
    )
    aftertax.add_argument(
        "--distributions",
        type=Path,
        default=None,
        help="distributions_daily.csv of a v2 snapshot (manifest.json beside it); "
        "omit to use the sweep's own archived distributions",
    )
    for command in (backtest, sweep):
        command.add_argument('--reveal', metavar='REASON', help='explicitly acknowledge first family holdout access')
        command.add_argument('--repair-of', metavar='ATTEMPT_ID', help='replay a revealed attempt after a documented code-only repair')
        command.add_argument('--repair-reason', metavar='REASON', help='explain the code-only repair; never restores unseen status')
    research = subparsers.add_parser('research', help='prepare, inspect or confirm a freeze without evaluating observations')
    actions = research.add_subparsers(dest='research_action', required=True)
    prepare = actions.add_parser('prepare', help='generate a reviewable draft, hashing inputs without numeric parsing')
    prepare.add_argument('config', type=Path)
    prepare.add_argument('--charter', type=Path, required=True)
    show = actions.add_parser('show', help='show the full proposed identity and confirmation status')
    show.add_argument('freeze', type=Path)
    confirm = actions.add_parser('confirm', help='confirm the exact displayed identity; does not open a holdout')
    confirm.add_argument('config', type=Path)
    confirm.add_argument('--hash', dest='identity_hash', required=True)
    confirm.add_argument('--reason', required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "backtest":
            raise SystemExit(run_backtest(args.config, unseal_reason=args.unseal,
                                         reveal_reason=args.reveal, repair_of=args.repair_of, repair_reason=args.repair_reason))
        if args.command == "sweep":
            raise SystemExit(run_sweep_command(args.config, unseal_reason=args.unseal,
                                              reveal_reason=args.reveal, repair_of=args.repair_of, repair_reason=args.repair_reason))
        if args.command == "classify":
            raise SystemExit(run_classify(args.development, args.validation, args.freeze))
        if args.command == "aftertax":
            raise SystemExit(run_aftertax(args.sweep, args.policy, args.distributions))
        if args.command == 'research':
            from boring_alpha.research_commands import prepare_research_freeze, show_research_freeze, confirm_research_freeze
            if args.research_action == 'prepare':
                raise SystemExit(prepare_research_freeze(args.config, args.charter))
            if args.research_action == 'show':
                raise SystemExit(show_research_freeze(args.freeze))
            if args.research_action == 'confirm':
                raise SystemExit(confirm_research_freeze(args.config, args.identity_hash, args.reason))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
