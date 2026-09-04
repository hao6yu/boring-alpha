"""Content-addressed, write-once experiment artifacts."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import date
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from boring_alpha.config import AppConfig
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult


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
) -> tuple[str, Path]:
    config_hash = hashlib.sha256(config.raw_bytes).hexdigest()
    data_hash = data.fingerprint()
    code_hash = _code_fingerprint()
    identity = f"{config_hash}:{data_hash}:{code_hash}"
    run_id = hashlib.sha256(identity.encode("ascii")).hexdigest()[:16]
    run_dir = config.report.output_dir / config.strategy.strategy_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    warnings = []
    if config.data.source == "synthetic":
        warnings.append("SYNTHETIC DATA: results have no economic or predictive meaning.")

    manifest = {
        "run_id": run_id,
        "strategy_id": config.strategy.strategy_id,
        "strategy_name": config.strategy.name,
        "config_path": str(config.path),
        "config_sha256": config_hash,
        "data_sha256": data_hash,
        "code_sha256": code_hash,
        "data_source": data.source,
        "backtest_start": config.backtest.start,
        "backtest_end": config.backtest.end,
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
    return run_id, run_dir
