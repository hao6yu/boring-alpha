"""Canonical in-memory market dataset and validation."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
import calendar
from collections import defaultdict
from datetime import date
import hashlib
import json
from typing import Iterable

from boring_alpha.domain import PriceBar


class MarketData:
    """Aligned total-return bars plus one-session cash growth factors."""

    def __init__(
        self,
        bars: Iterable[PriceBar],
        cash_factors: dict[date, float],
        *,
        source: str,
    ) -> None:
        by_date: dict[date, dict[str, PriceBar]] = defaultdict(dict)
        symbol_dates: dict[str, list[date]] = defaultdict(list)
        for bar in bars:
            if bar.open <= 0.0 or bar.close <= 0.0:
                raise ValueError(f"non-positive price for {bar.symbol} on {bar.date}")
            if bar.symbol in by_date[bar.date]:
                raise ValueError(f"duplicate bar for {bar.symbol} on {bar.date}")
            by_date[bar.date][bar.symbol] = bar
            symbol_dates[bar.symbol].append(bar.date)

        if not by_date:
            raise ValueError("market dataset contains no bars")
        self.by_date = {day: dict(values) for day, values in by_date.items()}
        self.dates = tuple(sorted(self.by_date))
        self.symbol_dates = {
            symbol: tuple(sorted(days)) for symbol, days in symbol_dates.items()
        }
        self.cash_factors = dict(cash_factors)
        self.source = source

        for day in self.dates:
            factor = self.cash_factors.get(day)
            if factor is None:
                raise ValueError(f"missing cash factor for {day}")
            if factor <= 0.0:
                raise ValueError(f"cash factor must be positive on {day}")

        running = 1.0
        self.cash_index: dict[date, float] = {}
        for day in self.dates:
            running *= self.cash_factors[day]
            self.cash_index[day] = running

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.symbol_dates))

    def bar(self, day: date, symbol: str) -> PriceBar:
        try:
            return self.by_date[day][symbol]
        except KeyError as exc:
            raise ValueError(f"missing {symbol} bar on {day}") from exc

    def last_shared_session_in_month(
        self, symbols: tuple[str, ...], year: int, month: int
    ) -> date | None:
        """Latest session in the calendar month on which every symbol has a bar."""

        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        low = bisect_left(self.dates, first)
        high = bisect_right(self.dates, last)
        for index in range(high - 1, low - 1, -1):
            day = self.dates[index]
            bars = self.by_date[day]
            if all(symbol in bars for symbol in symbols):
                return day
        return None

    def through(self, end: date) -> "MarketData":
        """A copy holding only sessions on or before `end`.

        Truncating before the engine runs is what makes an evaluation period a
        seal: data after the boundary never reaches the engine or the metrics,
        and does not enter the data fingerprint.
        """

        bars = [
            bar
            for day in self.dates
            if day <= end
            for bar in self.by_date[day].values()
        ]
        if not bars:
            raise ValueError(f"truncating at {end} leaves no bars")
        factors = {day: factor for day, factor in self.cash_factors.items() if day <= end}
        return MarketData(bars, factors, source=f"{self.source}:truncated={end}")

    def require_complete_calendar(
        self, symbols: tuple[str, ...], start: date, end: date
    ) -> None:
        missing_symbols = set(symbols) - set(self.symbol_dates)
        if missing_symbols:
            raise ValueError(f"dataset is missing symbols: {sorted(missing_symbols)}")
        for day in self.dates:
            if start <= day <= end:
                missing = set(symbols) - set(self.by_date[day])
                if missing:
                    raise ValueError(f"missing bars on {day}: {sorted(missing)}")

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for day in self.dates:
            for symbol in sorted(self.by_date[day]):
                bar = self.by_date[day][symbol]
                row = [day.isoformat(), symbol, repr(bar.open), repr(bar.close)]
                digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8"))
            digest.update(repr(self.cash_factors[day]).encode("ascii"))
        return digest.hexdigest()
