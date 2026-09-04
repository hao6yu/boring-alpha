"""Content-addressed, write-once experiment artifacts."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import date
import hashlib
import io
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from boring_alpha.config import AppConfig
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, SignalSnapshot

ARTIFACT_SCHEMA = 5


def _json_default(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"cannot encode {type(value).__name__}")


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=_json_default) + "\n"


def snapshot_record(snapshot: SignalSnapshot) -> dict[str, Any]:
    """A decision as written to artifacts.

    `hold` appears only when set. Decisions files written before the field
    existed are therefore reproduced byte for byte, and a reader sees the key
    only where it means something.
    """

    record = asdict(snapshot)
    if not record.get("hold"):
        record.pop("hold", None)
    return record


def write_once(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"refusing to overwrite changed experiment artifact: {path}")
        return
    path.write_text(content, encoding="utf-8")


def git_provenance(root: Path, code_path: Path | None = None) -> dict[str, object]:
    """Commit and dirty state of the repository holding the running code.

    `git -C` searches upward, so a package installed inside a checkout would
    otherwise report that checkout's commit as the provenance of code built
    elsewhere. The repository is used only when it actually contains the module.
    """

    code_path = (code_path or Path(__file__)).resolve()

    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ("git", "-C", str(root), *args), capture_output=True, text=True, timeout=5
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout if result.returncode == 0 else None

    unknown: dict[str, object] = {"git_commit": None, "git_dirty": None}
    toplevel = git("rev-parse", "--show-toplevel")
    if toplevel is None:
        return unknown
    try:
        code_path.relative_to(Path(toplevel.strip()).resolve())
    except ValueError:
        return unknown
    commit = git("rev-parse", "HEAD")
    if commit is None:
        return unknown
    status = git("status", "--porcelain")
    return {
        "git_commit": commit.strip(),
        "git_dirty": None if status is None else bool(status.strip()),
    }


def code_fingerprint() -> str:
    package_root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for source_path in sorted(package_root.rglob("*.py")):
        digest.update(source_path.relative_to(package_root).as_posix().encode("utf-8"))
        digest.update(source_path.read_bytes())
    return digest.hexdigest()


def write_once_bytes(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise RuntimeError(f"refusing to overwrite changed experiment artifact: {path}")
        return
    path.write_bytes(content)


def equity_csv(result: BacktestResult) -> str:
    return _equity_csv(result)


def trades_csv(result: BacktestResult) -> str:
    return _trades_csv(result)


def decisions_json(result: BacktestResult) -> str:
    return json_text([snapshot_record(snapshot) for snapshot in result.decisions])


def _equity_csv(result: BacktestResult) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["date", "equity", "cash", "gross_exposure"])
    for point in result.equity_curve:
        writer.writerow([point.date, point.equity, point.cash, point.gross_exposure])
    return output.getvalue()


def _trades_csv(result: BacktestResult) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "date",
            "symbol",
            "side",
            "quantity",
            "price",
            "notional",
            "cost",
            "intended_notional",
            "reference_price",
        ]
    )
    for fill in result.fills:
        writer.writerow(
            [
                fill.date,
                fill.symbol,
                fill.side,
                fill.quantity,
                fill.price,
                fill.notional,
                fill.cost,
                fill.intended_notional,
                fill.reference_price,
            ]
        )
    return output.getvalue()


def run_warnings(config: AppConfig, data: MarketData, results: tuple[BacktestResult, ...]) -> list[str]:
    """Everything an artifact must say about what its numbers are worth."""

    warnings: list[str] = []
    if config.data.source == "synthetic":
        warnings.append("SYNTHETIC DATA: results have no economic or predictive meaning.")
    if not config.evaluation.is_evidence:
        warnings.append(f"EXPLORATORY RUN: not evidence about {config.strategy.strategy_id}.")
    warnings.extend(data.warnings)
    for result in results:
        warnings.extend(result.warnings)
    return warnings


def append_provenance(run_dir: Path, unseal_reason: str | None) -> None:
    """Record the environment this invocation ran in, without touching identity."""

    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": sys.version.split()[0],
        "unseal_reason": unseal_reason,
        **git_provenance(Path(__file__).resolve().parent.parent.parent),
    }
    with (run_dir / "provenance.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_report(
    config: AppConfig,
    data: MarketData,
    strategy: BacktestResult,
    benchmark: BacktestResult,
    cash: BacktestResult,
    strategy_metrics: dict[str, float | int],
    benchmark_metrics: dict[str, float | int],
    cash_metrics: dict[str, float | int],
    unseal_reason: str | None = None,
) -> tuple[str, Path]:
    config_hash = hashlib.sha256(config.raw_bytes).hexdigest()
    data_hash = data.fingerprint()
    code_hash = code_fingerprint()
    evaluation = config.evaluation
    evaluation_key = f"{evaluation.period}:{evaluation.start}:{evaluation.end}"
    identity = f"{config_hash}:{data_hash}:{code_hash}:{evaluation_key}"
    run_id = hashlib.sha256(identity.encode("ascii")).hexdigest()[:16]
    run_dir = config.report.output_dir / config.strategy.strategy_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    warnings = run_warnings(config, data, (strategy, benchmark, cash))

    manifest = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "run_id": run_id,
        "strategy_id": config.strategy.strategy_id,
        "strategy_name": config.strategy.name,
        "config_toml": config.raw_bytes.decode("utf-8"),
        "config_sha256": config_hash,
        "data_sha256": data_hash,
        "code_sha256": code_hash,
        "data_source": data.source,
        "backtest_start": config.backtest.start,
        "backtest_end": config.backtest.end,
        "evaluation_period": config.evaluation.period,
        "evaluation_start": config.evaluation.start,
        "evaluation_end": config.evaluation.end,
        "data_start": data.dates[0],
        "data_end": data.dates[-1],
        "warnings": warnings,
    }
    decisions = [snapshot_record(snapshot) for snapshot in strategy.decisions]
    metrics = {
        "strategy": strategy_metrics,
        "static_benchmark": benchmark_metrics,
        "cash_benchmark": cash_metrics,
    }

    write_once(run_dir / "manifest.json", json_text(manifest))
    write_once(run_dir / "metrics.json", json_text(metrics))
    write_once(run_dir / "decisions.json", json_text(decisions))
    write_once(run_dir / "strategy_equity.csv", _equity_csv(strategy))
    write_once(run_dir / "benchmark_equity.csv", _equity_csv(benchmark))
    write_once(run_dir / "cash_equity.csv", _equity_csv(cash))
    write_once(run_dir / "strategy_trades.csv", _trades_csv(strategy))
    write_once(run_dir / "benchmark_trades.csv", _trades_csv(benchmark))

    # Identity is immutable; the environment a run was reproduced in is not.
    append_provenance(run_dir, unseal_reason)
    return run_id, run_dir
