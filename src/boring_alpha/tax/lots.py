"""Tax lots in real shares (spec §4.2, §4.3, §4.6).

Engine quantities are in adjusted units: a position of `q` units is worth
`q · A` at adjusted close `A`. A real account holding that value at unadjusted
close `P` holds `q · A / P` shares. Lots are kept in those real shares with
unadjusted-dollar basis, so gains, holding periods and wash sales follow the
rules a broker's statement would, and the past is not flattered by adjusted
prices that already contain reinvested distributions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Sequence

from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData

LOT_METHODS: tuple[str, ...] = ("hifo", "fifo")
_SHARE_TOLERANCE = 1e-9


def adjustment_factor(data: MarketData, table: DistributionTable, day: date, symbol: str) -> float:
    """Adjusted over unadjusted close on `day`: engine units times this are real shares.

    The ratio changes only at ex-dates (both series are split-adjusted), so it
    is constant between distributions and a lot's real shares grow only when a
    child lot is opened.
    """

    return data.bar(day, symbol).close / table.close(day, symbol)


@dataclass
class Lot:
    lot_id: int
    symbol: str
    opened: date
    """Start of the holding period. A wash sale tacks the sold lot's holding
    period on, which moves this earlier than `acquired`."""
    acquired: date
    """The purchase or reinvestment date; the wash-sale window is measured from it."""
    shares: float
    basis: float
    """Total dollars: notional plus trading cost, plus any disallowed loss attached."""
    source: str
    closed: date | None = None
    replacement_capacity: float = 0.0
    """Shares of this lot not yet used as replacement shares in a wash sale."""
    disallowed_attached: float = 0.0

    @property
    def basis_per_share(self) -> float:
        return self.basis / self.shares if self.shares > 0.0 else 0.0


@dataclass(frozen=True, slots=True)
class Realized:
    symbol: str
    lot_id: int
    opened: date
    sold: date
    shares: float
    proceeds: float
    basis: float
    disallowed: float = 0.0

    @property
    def gain(self) -> float:
        # A disallowed wash-sale loss is not recognised now: it moved into the
        # replacement lot's basis and will be recognised when that lot is sold.
        return self.proceeds - self.basis + self.disallowed


@dataclass(frozen=True, slots=True)
class Distribution:
    """One lot's share of a distribution on an ex-date (spec §4.3)."""

    symbol: str
    ex_date: date
    lot_id: int
    lot_opened: date
    cash: float
    return_of_capital: bool
    child_lot_id: int | None


class LotBook:
    """Open lots per symbol, sold by a declared method."""

    def __init__(self, method: str) -> None:
        if method not in LOT_METHODS:
            raise ValueError(f"lot method must be one of {', '.join(LOT_METHODS)}, got {method!r}")
        self.method = method
        self.lots: dict[int, Lot] = {}
        self._open: dict[str, list[Lot]] = {}
        self._next_id = 1
        self.extra_realized: list[Realized] = []
        """Return of capital beyond a lot's basis, realised as gain on the ex-date."""

    def open_lots(self, symbol: str) -> tuple[Lot, ...]:
        return tuple(self._open.get(symbol, ()))

    def shares_held(self, symbol: str) -> float:
        return sum(lot.shares for lot in self._open.get(symbol, ()))

    def buy(
        self,
        symbol: str,
        day: date,
        shares: float,
        basis: float,
        *,
        source: str = "buy",
        opened: date | None = None,
        extra_basis: float = 0.0,
        replacement_capacity: float | None = None,
    ) -> Lot:
        """Open a lot. `extra_basis` and `opened` carry a wash sale's disallowed
        loss and tacked holding period into a purchase made after the loss sale."""

        if shares <= 0.0:
            raise ValueError(f"a lot needs positive shares, got {shares!r} for {symbol} on {day}")
        if basis < 0.0 or extra_basis < 0.0:
            raise ValueError(f"a lot's basis cannot be negative ({basis!r}) for {symbol} on {day}")
        lot = Lot(
            lot_id=self._next_id,
            symbol=symbol,
            opened=opened or day,
            acquired=day,
            shares=shares,
            basis=basis + extra_basis,
            source=source,
            replacement_capacity=shares if replacement_capacity is None else replacement_capacity,
            disallowed_attached=extra_basis,
        )
        self._next_id += 1
        self.lots[lot.lot_id] = lot
        self._open.setdefault(symbol, []).append(lot)
        return lot

    def sell(self, symbol: str, day: date, shares: float, proceeds: float) -> list[Realized]:
        """Close `shares` of `symbol` by the book's method; proceeds are split pro rata."""

        open_lots = self._open.get(symbol, [])
        held = sum(lot.shares for lot in open_lots)
        if shares > held + _SHARE_TOLERANCE:
            raise ValueError(
                f"selling {shares} {symbol} shares on {day} but only {held} are held; "
                "the engine cannot produce this, so the inputs are inconsistent"
            )
        shares = min(shares, held)
        if self.method == "hifo":
            order = sorted(open_lots, key=lambda lot: (-lot.basis_per_share, lot.lot_id))
        else:
            order = sorted(open_lots, key=lambda lot: (lot.opened, lot.lot_id))

        records: list[Realized] = []
        remaining = shares
        for lot in order:
            if remaining <= _SHARE_TOLERANCE:
                break
            take = min(lot.shares, remaining)
            fraction = take / lot.shares
            lot_basis = lot.basis * fraction
            lot_proceeds = proceeds * (take / shares) if shares > 0.0 else 0.0
            records.append(
                Realized(symbol, lot.lot_id, lot.opened, day, take, lot_proceeds, lot_basis)
            )
            lot.shares -= take
            lot.basis -= lot_basis
            remaining -= take
            if lot.shares <= _SHARE_TOLERANCE:
                lot.shares = 0.0
                lot.basis = 0.0
                lot.closed = day
                open_lots.remove(lot)
            # Shares just sold cannot serve as replacement shares for a wash sale.
            lot.replacement_capacity = min(lot.replacement_capacity, lot.shares)
        return records

    def distribute(
        self,
        symbol: str,
        ex_date: date,
        dividend_per_share: float,
        growth: float,
        *,
        return_of_capital: bool,
    ) -> list[Distribution]:
        """Pay `dividend_per_share` to every lot held into `ex_date`, reinvesting it.

        `growth` is the reinvestment factor the adjusted series implies,
        F(ex_date) / F(previous session): the child lot's shares are the parent's
        times (growth − 1) and its basis is the cash, so real shares keep
        matching engine units exactly. An income distribution leaves the parent's
        basis alone and is taxed; a return of capital reduces the parent's basis
        by the cash instead, and any excess over that basis is a capital gain
        realised on the ex-date. Lots acquired on or after the ex-date, including
        the child lots this call opens, receive nothing.
        """

        if dividend_per_share < 0.0:
            raise ValueError(f"negative dividend {dividend_per_share!r} for {symbol} on {ex_date}")
        events: list[Distribution] = []
        for lot in list(self._open.get(symbol, ())):
            if lot.acquired >= ex_date:
                continue
            cash = lot.shares * dividend_per_share
            if cash <= 0.0:
                continue
            child: Lot | None = None
            if growth > 1.0:
                child = self.buy(symbol, ex_date, lot.shares * (growth - 1.0), cash, source="reinvest")
            if return_of_capital:
                reduction = min(cash, lot.basis)
                lot.basis -= reduction
                excess = cash - reduction
                if excess > 0.0:
                    self.extra_realized.append(
                        Realized(symbol, lot.lot_id, lot.opened, ex_date, 0.0, excess, 0.0)
                    )
            events.append(
                Distribution(
                    symbol, ex_date, lot.lot_id, lot.opened, cash, return_of_capital,
                    child.lot_id if child is not None else None,
                )
            )
        return events


WASH_SALE_WINDOW = timedelta(days=30)


@dataclass
class FuturePurchase:
    """A buy fill dated after a loss sale, still inside the wash-sale window.

    Its lot does not exist yet, so the disallowed loss and the tacked holding
    period wait here and are applied when the lot is opened.
    """

    symbol: str
    acquired: date
    shares: float
    replacement_capacity: float
    pending_basis: float = 0.0
    pending_tack_days: int = 0


def apply_wash_sales(
    records: list[Realized],
    existing: "Sequence[Lot]",
    future: "Sequence[FuturePurchase]",
) -> list[Realized]:
    """Disallow losses matched to replacement shares (spec §4.6).

    A loss sale is a wash sale to the extent the same symbol was acquired within
    30 calendar days before or after, counting reinvested distributions as
    purchases. Replacement shares are matched once, in acquisition order. For an
    existing lot the disallowed loss is added to its basis and the sold lot's
    holding period is tacked onto its own; for a purchase still in the future
    both wait on the `FuturePurchase` until the lot is opened. Shares sold in the
    loss sale itself never replace themselves: `LotBook.sell` has already reduced
    their lot's capacity to what remains.
    """

    adjusted: list[Realized] = []
    tacked: set[int] = set()
    for record in records:
        loss = record.basis - record.proceeds
        if loss <= 0.0 or record.shares <= 0.0:
            adjusted.append(record)
            continue
        low, high = record.sold - WASH_SALE_WINDOW, record.sold + WASH_SALE_WINDOW
        candidates: list[Lot | FuturePurchase] = [
            lot
            for lot in existing
            if lot.symbol == record.symbol
            and low <= lot.acquired <= high
            and lot.replacement_capacity > _SHARE_TOLERANCE
        ]
        candidates += [
            purchase
            for purchase in future
            if purchase.symbol == record.symbol
            and low <= purchase.acquired <= high
            and purchase.replacement_capacity > _SHARE_TOLERANCE
        ]
        candidates.sort(key=lambda item: item.acquired)
        holding_days = (record.sold - record.opened).days
        matched = 0.0
        for candidate in candidates:
            if matched >= record.shares - _SHARE_TOLERANCE:
                break
            take = min(candidate.replacement_capacity, record.shares - matched)
            share_of_loss = loss * (take / record.shares)
            if isinstance(candidate, Lot):
                candidate.basis += share_of_loss
                candidate.disallowed_attached += share_of_loss
                if candidate.lot_id not in tacked:
                    candidate.opened = candidate.opened - timedelta(days=holding_days)
                    tacked.add(candidate.lot_id)
            else:
                candidate.pending_basis += share_of_loss
                candidate.pending_tack_days = max(candidate.pending_tack_days, holding_days)
            candidate.replacement_capacity -= take
            matched += take
        adjusted.append(replace(record, disallowed=loss * (matched / record.shares)))
    return adjusted
