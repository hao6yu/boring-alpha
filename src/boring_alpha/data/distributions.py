"""Distributions for the tax overlay: unadjusted closes and cash dividends per share.

The engine never sees this table. It exists so that after-tax accounting can
separate the income the adjusted price series silently reinvests from the
capital gain it reports, and it is read only by the tax overlay.

Units are split-adjusted, matching the `close` column and the adjusted series
(see tools/fetch_market_data.py). A split is not a taxable event, so an
account kept in split-adjusted shares is equivalent to one kept in
certificate shares; the split records are required anyway so that a reader
can see them.
"""

from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Iterable

from boring_alpha.data.market import MarketData

REQUIRED_COLUMNS = frozenset({"date", "symbol", "close", "dividend"})

Row = tuple[date, str, float, float]


class DistributionTable:
    """Unadjusted close and cash dividend per share, by session and symbol."""

    def __init__(
        self,
        rows: Iterable[Row],
        *,
        splits: dict[str, list[dict[str, str]]],
        sha256: str,
        source: str,
    ) -> None:
        closes: dict[tuple[date, str], float] = {}
        dividends: dict[tuple[date, str], float] = {}
        symbol_dates: dict[str, list[date]] = defaultdict(list)
        for day, symbol, close, dividend in rows:
            if not (math.isfinite(close) and math.isfinite(dividend)):
                raise ValueError(f"distribution row for {symbol} on {day} is not finite")
            if close <= 0.0:
                raise ValueError(f"non-positive close for {symbol} on {day}")
            if dividend < 0.0:
                raise ValueError(f"negative dividend for {symbol} on {day}")
            key = (day, symbol)
            if key in closes:
                raise ValueError(f"duplicate distribution row for {symbol} on {day}")
            closes[key] = close
            dividends[key] = dividend
            symbol_dates[symbol].append(day)
        if not closes:
            raise ValueError("distribution table contains no rows")
        self._closes = closes
        self._dividends = dividends
        self.symbol_dates = {
            symbol: tuple(sorted(days)) for symbol, days in symbol_dates.items()
        }
        self.dates = tuple(sorted({day for day, _ in closes}))
        self.splits = {symbol: list(records) for symbol, records in splits.items()}
        self.sha256 = sha256
        self.source = source

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.symbol_dates))

    def close(self, day: date, symbol: str) -> float:
        try:
            return self._closes[(day, symbol)]
        except KeyError as exc:
            raise ValueError(f"no distribution row for {symbol} on {day}") from exc

    def dividend(self, day: date, symbol: str) -> float:
        try:
            return self._dividends[(day, symbol)]
        except KeyError as exc:
            raise ValueError(f"no distribution row for {symbol} on {day}") from exc

    def ex_dates(self, symbol: str) -> tuple[date, ...]:
        """Sessions on which the symbol paid a dividend."""

        return tuple(
            day
            for day in self.symbol_dates.get(symbol, ())
            if self._dividends[(day, symbol)] > 0.0
        )

    def through(self, end: date) -> "DistributionTable":
        """A copy holding only sessions on or before `end`, matching MarketData.through."""

        rows = [
            (day, symbol, self._closes[(day, symbol)], self._dividends[(day, symbol)])
            for day, symbol in sorted(self._closes)
            if day <= end
        ]
        if not rows:
            raise ValueError(f"truncating distributions at {end} leaves no rows")
        return DistributionTable(
            rows, splits=self.splits, sha256=self.sha256, source=f"{self.source}:truncated={end}"
        )

    def require_coverage(self, data: MarketData, symbols: tuple[str, ...]) -> None:
        """Every priced session for `symbols` must have a distribution row."""

        for day in data.dates:
            bars = data.by_date[day]
            for symbol in symbols:
                if symbol in bars and (day, symbol) not in self._closes:
                    raise ValueError(
                        f"no distribution row for {symbol} on {day}; the distributions "
                        "file must cover every priced session"
                    )


def split_records(manifest: dict) -> dict[str, list[dict[str, str]]]:
    """Split records from a v2 snapshot manifest or a sweep's embedded block."""

    if "splits" not in manifest:
        raise ValueError(
            "the distributions manifest records no 'splits' key; a v2 snapshot "
            "manifest or a sweep's embedded distributions_manifest block is required"
        )
    return {symbol: list(records) for symbol, records in manifest["splits"].items()}


def load_distributions(
    path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    manifest_block: dict | None = None,
) -> DistributionTable:
    """Read `distributions_daily.csv` and the split records that belong with it."""

    if (manifest_path is None) == (manifest_block is None):
        raise ValueError("exactly one of manifest_path or manifest_block is required")
    manifest = (
        manifest_block
        if manifest_block is not None
        else json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    )
    splits = split_records(manifest)

    raw = Path(path).read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if set(reader.fieldnames or ()) != REQUIRED_COLUMNS:
        raise ValueError(
            f"distribution CSV columns must be exactly {sorted(REQUIRED_COLUMNS)}, "
            f"got {reader.fieldnames}"
        )
    rows: list[Row] = []
    for row_number, row in enumerate(reader, start=2):
        try:
            rows.append(
                (
                    date.fromisoformat(row["date"]),
                    row["symbol"].strip().upper(),
                    float(row["close"]),
                    float(row["dividend"]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid distribution row {row_number}: {row}") from exc
    return DistributionTable(
        rows,
        splits=splits,
        sha256=hashlib.sha256(raw).hexdigest(),
        source=f"csv:{Path(path).name}",
    )
