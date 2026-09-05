"""Rebuild what the overlay needs from a sweep directory's archived files (spec §7).

A sweep keeps every run's equity curve and trade ledger and the exact prices
and cash it saw, so any past sweep can be scored under a new policy, or by a
corrected overlay, without re-running it. Run names mirror `run_sweep`'s so an
`aftertax` result and an in-sweep `tax.json` compare key for key.
"""

from __future__ import annotations

import csv
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import tomllib

from boring_alpha.data.csv_loader import load_csv_market_data
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, Fill
from boring_alpha.report import READABLE_SCHEMAS


def read_manifest(sweep_dir: Path) -> dict:
    path = sweep_dir / "manifest.json"
    if not path.is_file():
        raise ValueError(f"{sweep_dir} holds no manifest.json; is it a sweep directory?")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for key in ("sweep_id", "strategy_id", "config_toml", "grid", "data_sha256"):
        if key not in manifest:
            raise ValueError(f"{path} records no {key}; it predates the sweep artifact format")
    if type(manifest.get("artifact_schema")) is not int or manifest["artifact_schema"] not in READABLE_SCHEMAS:
        raise ValueError(f"{path} has unsupported artifact_schema {manifest.get('artifact_schema')!r}")
    if not isinstance(manifest["grid"], dict) or "base" not in manifest["grid"]:
        raise ValueError(f"{path} records no complete variant grid")
    if manifest.get("strategy_id") == "BA-002" and manifest.get("artifact_schema") != 7:
        raise ValueError("BA-002 requires complete schema-7 evidence, not a legacy archive")
    if manifest.get("artifact_schema") == 7:
        if manifest.get("strategy_id") != "BA-002":
            raise ValueError("schema-7 evidence is reserved for the BA-002 profile")
        if manifest.get("complete") is not True:
            raise ValueError("schema-7 sweep has no completed publication")
        if manifest.get("run_map") != schema7_run_map():
            raise ValueError("schema-7 sweep has an incomplete or changed account mapping")
    return manifest


def _config_of(manifest: dict) -> dict:
    return tomllib.loads(manifest["config_toml"])


def initial_cash_from(manifest: dict) -> float:
    return float(_config_of(manifest)["portfolio"]["initial_cash"])


def symbols_from(manifest: dict) -> tuple[str, ...]:
    return tuple(str(symbol).upper() for symbol in _config_of(manifest)["strategy"]["symbols"])


def read_equity_csv(path: Path) -> tuple[EquityPoint, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        return tuple(
            EquityPoint(
                date.fromisoformat(row["date"]),
                float(row["equity"]),
                float(row["cash"]),
                float(row["gross_exposure"]),
            )
            for row in csv.DictReader(handle)
        )


def read_trades_csv(path: Path) -> tuple[Fill, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        return tuple(
            Fill(
                date=date.fromisoformat(row["date"]),
                symbol=row["symbol"],
                side=row["side"],
                quantity=float(row["quantity"]),
                price=float(row["price"]),
                notional=float(row["notional"]),
                cost=float(row["cost"]),
                intended_notional=float(row["intended_notional"]),
                reference_price=float(row["reference_price"]),
            )
            for row in csv.DictReader(handle)
        )


def reconstruct_result(
    name: str, equity_path: Path, trades_path: Path, initial_cash: float
) -> BacktestResult:
    """A `BacktestResult` with the fields the overlay reads; decisions are not needed."""

    return BacktestResult(
        name=name,
        initial_equity=initial_cash,
        equity_curve=read_equity_csv(equity_path),
        fills=read_trades_csv(trades_path),
        decisions=(),
    )


def require_run_window(result: BacktestResult, data: MarketData, manifest: dict) -> None:
    """A truncated curve must not masquerade as the registered archived run."""

    backtest = _config_of(manifest)["backtest"]
    start = date.fromisoformat(str(backtest["start"]))
    end = date.fromisoformat(str(backtest["end"]))
    expected = tuple(day for day in data.shared_sessions(symbols_from(manifest)) if start <= day <= end)
    if tuple(point.date for point in result.equity_curve) != expected:
        raise ValueError(f"{result.name} equity curve does not cover the sweep's declared backtest window")


def gunzip_to(source: Path, target: Path) -> None:
    with gzip.open(source, "rb") as packed, target.open("wb") as unpacked:
        shutil.copyfileobj(packed, unpacked)


def market_data_from_archive(sweep_dir: Path, manifest: dict | None = None) -> MarketData:
    """The dataset the sweep saw, from its archived inputs."""

    manifest = read_manifest(sweep_dir) if manifest is None else manifest
    for name in ("input_prices.csv.gz", "input_cash.csv.gz"):
        if not (sweep_dir / name).is_file():
            raise ValueError(f"{sweep_dir} archived no {name}; it cannot be re-scored")
    with tempfile.TemporaryDirectory() as directory:
        prices = Path(directory) / "market_daily.csv"
        cash = Path(directory) / "cash_daily.csv"
        gunzip_to(sweep_dir / "input_prices.csv.gz", prices)
        gunzip_to(sweep_dir / "input_cash.csv.gz", cash)
        data = load_csv_market_data(prices, cash)
    if data.fingerprint() != manifest["data_sha256"]:
        raise ValueError("archived market data fingerprint does not match manifest.data_sha256")
    return data


def tax_run_name(variant: str, role: str) -> str | None:
    """Which tax run a variant directory's file is. Mirrors `run_sweep`:
    the base variant is the strategy and the gating benchmark; the
    exposure-matched directory holds that allocation and cash; the static_full
    directory holds full static; every other variant contributes its strategy only."""

    if variant == "base":
        return "strategy" if role == "strategy" else "benchmark"
    if variant == "exposure_matched":
        return "exposure_matched" if role == "strategy" else "cash"
    if variant == "static_full":
        return "static_full" if role == "strategy" else None
    return f"variant:{variant}" if role == "strategy" else None


def schema7_run_map() -> dict[str, dict[str, str]]:
    from boring_alpha.research_contract import expected_account_map
    mapping = {
        account: {"variant": row, "role": role}
        for row, roles in expected_account_map().items() for role, account in roles.items()
    }
    mapping.update({
        "exposure_matched": {"variant": "exposure_matched", "role": "strategy"},
        "cash": {"variant": "exposure_matched", "role": "benchmark"},
        "static_full": {"variant": "static_full", "role": "strategy"},
        "reference_12": {"variant": "reference_12", "role": "strategy"},
    })
    return mapping


def _variant_names(manifest: dict) -> set[str]:
    names = set(manifest["grid"]) | {"exposure_matched"}
    if "benchmark" in _config_of(manifest):
        names.add("static_full")
    if manifest.get("artifact_schema") == 7:
        names.add("reference_12")
    if any(not isinstance(name, str) or Path(name).name != name or name in (".", "..") for name in names):
        raise ValueError("sweep manifest has an invalid variant name")
    return names


def verify_archive_artifacts(sweep_dir: Path, manifest: dict) -> str:
    """Verify every stored checksum, including all inputs consumed by replay.

    Schema-5 and earlier schema-6 sweeps did not store file checksums. Their
    market fingerprint and independent account replay remain mandatory, but
    the missing checksums are explicitly reported as legacy provenance.
    """

    hashes = manifest.get("artifacts_sha256")
    if hashes is None:
        if manifest.get("artifact_schema") == 7:
            raise ValueError("schema-7 sweep requires artifact checksums")
        return "legacy-unverified: per-file checksums were not recorded"
    required = {"input_prices.csv.gz", "input_cash.csv.gz"}
    if "distributions_manifest" in manifest:
        required.add("input_distributions.csv.gz")
    if manifest.get("artifact_schema") == 7:
        required.update({"criteria.json", "tax.json", "research_contract.json", "freeze.json", "calendar.json",
                         "account_map.json", "summary.md"})
    for name in _variant_names(manifest):
        required.update(
            f"variants/{name}/{role}_{kind}.csv"
            for role in ("strategy", "benchmark") for kind in ("equity", "trades")
        )
        required.add(f"variants/{name}/strategy_decisions.json")
        if manifest.get("artifact_schema") == 7:
            required.add(f"variants/{name}/benchmark_decisions.json")
    if not isinstance(hashes, dict) or not required.issubset(hashes):
        raise ValueError("sweep artifacts_sha256 does not cover all required archived inputs")
    for name, expected in hashes.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"invalid archived path in artifacts_sha256: {name!r}")
        path = sweep_dir / relative
        if not path.is_file():
            raise ValueError(f"missing archived artifact: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"archived artifact checksum mismatch: {name}")
    return "verified"


def run_files(sweep_dir: Path, manifest: dict | None = None) -> list[tuple[str, Path, Path]]:
    """(run name, equity CSV, trades CSV) for every archived run, in a stable order."""

    manifest = read_manifest(sweep_dir) if manifest is None else manifest
    variants = sweep_dir / "variants"
    if not variants.is_dir():
        raise ValueError(f"{sweep_dir} holds no variants/ directory")
    expected = _variant_names(manifest)
    actual = {path.name for path in variants.iterdir() if path.is_dir()}
    if actual != expected:
        raise ValueError(
            f"archived variant coverage differs from manifest: missing {sorted(expected - actual)}, "
            f"unexpected {sorted(actual - expected)}"
        )
    files: list[tuple[str, Path, Path]] = []
    explicit = manifest.get("run_map") if manifest.get("artifact_schema") == 7 else None
    for variant in sorted(expected):
        variant_dir = variants / variant
        for role in ("strategy", "benchmark"):
            for kind in ("equity", "trades"):
                if not (variant_dir / f"{role}_{kind}.csv").is_file():
                    raise ValueError(f"missing archived artifact: {variant}/{role}_{kind}.csv")
            name = next((key for key, location in explicit.items()
                         if location == {"variant": variant, "role": role}), None) if explicit is not None else tax_run_name(variant_dir.name, role)
            if name is None:
                continue
            files.append((name, variant_dir / f"{role}_equity.csv", variant_dir / f"{role}_trades.csv"))
    return files
