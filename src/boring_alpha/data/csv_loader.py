"""Strict CSV loader for canonical BoringAlpha data."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from boring_alpha.domain import PriceBar
from boring_alpha.data.market import MarketData


def load_csv_market_data(prices_path: Path, cash_path: Path) -> MarketData:
    bars: list[PriceBar] = []
    with prices_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol", "tr_open", "tr_close"}
        if set(reader.fieldnames or ()) != required:
            raise ValueError(
                f"price CSV columns must be exactly {sorted(required)}, got {reader.fieldnames}"
            )
        for row_number, row in enumerate(reader, start=2):
            try:
                bars.append(
                    PriceBar(
                        date=date.fromisoformat(row["date"]),
                        symbol=row["symbol"].strip().upper(),
                        open=float(row["tr_open"]),
                        close=float(row["tr_close"]),
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid price row {row_number}: {row}") from exc

    cash_factors: dict[date, float] = {}
    with cash_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "cash_factor"}
        if set(reader.fieldnames or ()) != required:
            raise ValueError(
                f"cash CSV columns must be exactly {sorted(required)}, got {reader.fieldnames}"
            )
        for row_number, row in enumerate(reader, start=2):
            try:
                day = date.fromisoformat(row["date"])
                if day in cash_factors:
                    raise ValueError(f"duplicate cash date {day}")
                cash_factors[day] = float(row["cash_factor"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid cash row {row_number}: {row}") from exc

    return MarketData(bars, cash_factors, source=f"csv:{prices_path}:{cash_path}")
