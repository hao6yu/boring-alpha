"""Strict CSV loader for canonical BoringAlpha data."""

from __future__ import annotations

import csv
from datetime import date
import io
import math
from pathlib import Path
from collections.abc import Iterator

from boring_alpha.domain import PriceBar
from boring_alpha.data.market import MarketData


def _csv_rows(raw: bytes, source: str, required: set[str] | frozenset[str]) -> Iterator[tuple[int, dict]]:
    """Yield CSV rows without allowing parser diagnostics to quote source data."""
    try:
        decoded = raw.decode("utf-8")
    except UnicodeError:
        raise ValueError(f"invalid {source} CSV: field 'encoding' (UTF-8 required)") from None
    with io.StringIO(decoded, newline="") as handle:
        reader = csv.DictReader(handle)
        try:
            columns = reader.fieldnames or ()
            if len(columns) != len(required) or set(columns) != required:
                # A corrupt header may itself contain an observation. Never
                # include the received columns in an error or its traceback.
                raise ValueError(f"{source} CSV columns must be exactly {sorted(required)}")
            for row_number, row in enumerate(reader, start=2):
                yield row_number, row
        except csv.Error:
            raise ValueError(
                f"invalid {source} row {reader.line_num}: field 'CSV structure'"
            ) from None


def _csv_date(row: dict, source: str, row_number: int) -> date:
    try:
        return date.fromisoformat(row["date"])
    except (KeyError, TypeError, ValueError):
        # A malformed date cannot safely be assigned to either side of the
        # evaluation boundary. Fail closed without echoing any part of its row.
        raise ValueError(f"invalid {source} row {row_number}: field 'date'") from None


def _csv_symbol(row: dict, source: str, row_number: int) -> str:
    value = row.get("symbol")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid {source} row {row_number}: field 'symbol'")
    return value.strip().upper()


def _csv_number(row: dict, field: str, source: str, row_number: int) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError(f"invalid {source} row {row_number}: field '{field}'") from None
    if not math.isfinite(value):
        raise ValueError(f"invalid {source} row {row_number}: field '{field}' (not a finite number)")
    return value


def _csv_row_shape(row: dict, source: str, row_number: int) -> None:
    if None in row:
        raise ValueError(f"invalid {source} row {row_number}: field 'columns'")


def load_csv_market_data(
    prices_path: Path, cash_path: Path, *, end: date | None = None
) -> MarketData:
    """Read only observations available through ``end``.

    Date filtering deliberately precedes numeric parsing. A snapshot may
    physically contain later rows; they are not observations made available
    to the bounded evaluation, its validation, or its semantic fingerprint.
    """
    return load_csv_market_data_bytes(prices_path.read_bytes(), cash_path.read_bytes(), end=end)


def load_csv_market_data_bytes(
    prices: bytes, cash: bytes, *, end: date | None = None
) -> MarketData:
    """Parse the exact immutable bytes covered by an input authorization."""
    if type(prices) is not bytes or type(cash) is not bytes:
        raise ValueError("captured market inputs must be immutable bytes")
    bars: list[PriceBar] = []
    for row_number, row in _csv_rows(prices, "price", {"date", "symbol", "tr_open", "tr_close"}):
        day = _csv_date(row, "price", row_number)
        if end is not None and day > end:
            continue
        _csv_row_shape(row, "price", row_number)
        symbol = _csv_symbol(row, "price", row_number)
        opening = _csv_number(row, "tr_open", "price", row_number)
        close = _csv_number(row, "tr_close", "price", row_number)
        for field, value in (("tr_open", opening), ("tr_close", close)):
            if value <= 0:
                raise ValueError(f"invalid price row {row_number}: field '{field}' (non-positive price)")
        bars.append(PriceBar(date=day, symbol=symbol, open=opening, close=close))

    cash_factors: dict[date, float] = {}
    for row_number, row in _csv_rows(cash, "cash", {"date", "cash_factor"}):
        day = _csv_date(row, "cash", row_number)
        if end is not None and day > end:
            continue
        _csv_row_shape(row, "cash", row_number)
        if day in cash_factors:
            raise ValueError(f"invalid cash row {row_number}: field 'date' (duplicate cash date)")
        factor = _csv_number(row, "cash_factor", "cash", row_number)
        if factor <= 0:
            raise ValueError(f"invalid cash row {row_number}: field 'cash_factor' (must be positive)")
        cash_factors[day] = factor

    return MarketData(bars, cash_factors, source="csv")
