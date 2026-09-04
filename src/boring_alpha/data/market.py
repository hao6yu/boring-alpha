"""Canonical in-memory market dataset and validation."""

from __future__ import annotations

from bisect import bisect_right
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

    def date_on_or_before(self, symbol: str, target: date) -> date | None:
        days = self.symbol_dates.get(symbol, ())
        index = bisect_right(days, target) - 1
        return days[index] if index >= 0 else None

    def shared_date_on_or_before(self, symbols: tuple[str, ...], target: date) -> date | None:
        candidates = [self.date_on_or_before(symbol, target) for symbol in symbols]
        if any(day is None for day in candidates):
            return None
        candidate = min(day for day in candidates if day is not None)
        while candidate is not None:
            if all(candidate in self.by_date and symbol in self.by_date[candidate] for symbol in symbols):
                return candidate
            previous = [self.date_on_or_before(symbol, candidate) for symbol in symbols]
            if any(day is None for day in previous):
                return None
            next_candidate = min(day for day in previous if day is not None)
            if next_candidate == candidate:
                earlier = date.fromordinal(candidate.toordinal() - 1)
                previous = [self.date_on_or_before(symbol, earlier) for symbol in symbols]
                if any(day is None for day in previous):
                    return None
                next_candidate = min(day for day in previous if day is not None)
            candidate = next_candidate
        return None

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
        digest.update(self.source.encode("utf-8"))
        for day in self.dates:
            for symbol in sorted(self.by_date[day]):
                bar = self.by_date[day][symbol]
                row = [day.isoformat(), symbol, repr(bar.open), repr(bar.close)]
                digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8"))
            digest.update(repr(self.cash_factors[day]).encode("ascii"))
        return digest.hexdigest()
