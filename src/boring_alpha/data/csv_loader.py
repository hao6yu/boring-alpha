"""Strict CSV loader for canonical BoringAlpha data."""

from __future__ import annotations

import csv
from datetime import date
import io
from pathlib import Path

from boring_alpha.domain import PriceBar
from boring_alpha.data.market import MarketData


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
    with io.StringIO(prices.decode("utf-8"), newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol", "tr_open", "tr_close"}
        if set(reader.fieldnames or ()) != required:
            raise ValueError(
                f"price CSV columns must be exactly {sorted(required)}, got {reader.fieldnames}"
            )
        for row_number, row in enumerate(reader, start=2):
            try:
                day = date.fromisoformat(row["date"])
                if end is not None and day > end:
                    continue
                bars.append(
                    PriceBar(
                        date=day,
                        symbol=row["symbol"].strip().upper(),
                        open=float(row["tr_open"]),
                        close=float(row["tr_close"]),
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid price row {row_number}: {row}") from exc

    cash_factors: dict[date, float] = {}
    with io.StringIO(cash.decode("utf-8"), newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "cash_factor"}
        if set(reader.fieldnames or ()) != required:
            raise ValueError(
                f"cash CSV columns must be exactly {sorted(required)}, got {reader.fieldnames}"
            )
        for row_number, row in enumerate(reader, start=2):
            try:
                day = date.fromisoformat(row["date"])
                if end is not None and day > end:
                    continue
                if day in cash_factors:
                    raise ValueError(f"duplicate cash date {day}")
                cash_factors[day] = float(row["cash_factor"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid cash row {row_number}: {row}") from exc

    return MarketData(bars, cash_factors, source="csv")
