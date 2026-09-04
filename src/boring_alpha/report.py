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
from boring_alpha.domain import BacktestResult

ARTIFACT_SCHEMA = 4


def _json_default(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"cannot encode {type(value).__name__}")


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=_json_default) + "\n"


def _write_once(path: Path, content: str) -> None:
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


def _code_fingerprint() -> str:
    package_root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for source_path in sorted(package_root.rglob("*.py")):
        digest.update(source_path.relative_to(package_root).as_posix().encode("utf-8"))
        digest.update(source_path.read_bytes())
    return digest.hexdigest()


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
    writer.writerow(["date", "symbol", "side", "quantity", "price", "notional", "cost"])
    for trade in result.trades:
        writer.writerow(
            [
                trade.date,
                trade.symbol,
                trade.side,
                trade.quantity,
                trade.price,
                trade.notional,
                trade.cost,
            ]
        )
    return output.getvalue()


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
    code_hash = _code_fingerprint()
    evaluation = config.evaluation
    evaluation_key = f"{evaluation.period}:{evaluation.start}:{evaluation.end}"
    identity = f"{config_hash}:{data_hash}:{code_hash}:{evaluation_key}"
    run_id = hashlib.sha256(identity.encode("ascii")).hexdigest()[:16]
    run_dir = config.report.output_dir / config.strategy.strategy_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    if config.data.source == "synthetic":
        warnings.append("SYNTHETIC DATA: results have no economic or predictive meaning.")
    if not config.evaluation.is_evidence:
        warnings.append(
            f"EXPLORATORY RUN: not evidence about {config.strategy.strategy_id}."
        )
    warnings.extend(data.warnings)
    for result in (strategy, benchmark, cash):
        warnings.extend(result.warnings)

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
    decisions = [asdict(snapshot) for snapshot in strategy.decisions]
    metrics = {
        "strategy": strategy_metrics,
        "static_benchmark": benchmark_metrics,
        "cash_benchmark": cash_metrics,
    }

    _write_once(run_dir / "manifest.json", _json(manifest))
    _write_once(run_dir / "metrics.json", _json(metrics))
    _write_once(run_dir / "decisions.json", _json(decisions))
    _write_once(run_dir / "strategy_equity.csv", _equity_csv(strategy))
    _write_once(run_dir / "benchmark_equity.csv", _equity_csv(benchmark))
    _write_once(run_dir / "cash_equity.csv", _equity_csv(cash))
    _write_once(run_dir / "strategy_trades.csv", _trades_csv(strategy))
    _write_once(run_dir / "benchmark_trades.csv", _trades_csv(benchmark))

    # Identity is immutable; the environment a run was reproduced in is not.
    # Appending keeps every invocation instead of making the write-once check
    # fire on a Python upgrade or an unrelated commit.
    provenance = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": sys.version.split()[0],
        "unseal_reason": unseal_reason,
        **git_provenance(Path(__file__).resolve().parent.parent.parent),
    }
    with (run_dir / "provenance.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(provenance, sort_keys=True) + "\n")
    return run_id, run_dir
