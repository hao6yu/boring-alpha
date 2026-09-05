"""Tax lots in real shares (spec §4.2, §4.3, §4.6).

Engine quantities are in adjusted units: a position of `q` units is worth
`q · A` at adjusted close `A`. A real account holding that value at unadjusted
close `P` holds `q · A / P` shares. Lots are kept in those real shares with
unadjusted-dollar basis, so gains, holding periods and wash sales follow the
rules a broker's statement would, and the past is not flattered by adjusted
prices that already contain reinvested distributions.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData

LOT_METHODS: tuple[str, ...] = ("hifo", "fifo")
_SHARE_TOLERANCE = 1e-9


def adjustment_factor(data: MarketData, table: DistributionTable, day: date, symbol: str) -> float:
    """Adjusted over unadjusted close, sampled once per ex-date interval.

    Yahoo's adjusted closes carry only about seven significant digits, so the
    raw `data.bar(day, symbol).close / table.close(day, symbol)` ratio jitters
    by up to roughly 1e-6 relative between ex-dates even though the ratio is
    supposed to be exactly constant there (both series are split- and
    dividend-adjusted). To make the factor piecewise-constant by construction,
    this samples it at one reference session per interval: the latest ex-date
    of `symbol` in `table` (a session where `table.dividend(...) > 0`) that is
    on or before `day`, found with `bisect` on `table.ex_dates(symbol)`; when
    there is none on or before `day`, the earliest session of `symbol` in the
    table is used instead. If that reference session is earlier than the
    first date of `data`, the first date of `data` is used instead, so the
    whole first interval shares that one sample.

    Real shares bought and sold within one interval therefore use exactly one
    factor, so a full exit closes exactly instead of tripping the over-sell
    guard on Yahoo's rounding; the share-identity check then measures that
    rounding jitter directly rather than being broken by it.
    """

    ex_dates = table.ex_dates(symbol)
    index = bisect_right(ex_dates, day)
    reference = ex_dates[index - 1] if index > 0 else table.symbol_dates[symbol][0]
    if reference < data.dates[0]:
        reference = data.dates[0]
    return data.bar(reference, symbol).close / table.close(reference, symbol)


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
    purchase_id: int = 0
    """Stable acquisition order, shared by slices of one purchase."""
    share_offset: float = 0.0
    dividend_claims: list["DividendHolding"] = field(default_factory=list)

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


@dataclass(frozen=True, slots=True)
class DividendHolding:
    """One share slice's dividend entitlement and actual ownership interval.

    These records never use a wash sale's tacked capital-gain holding period.
    Partial dispositions and replacement-lot splits partition the cash claim;
    they do not rewrite the holding interval of shares already disposed of.
    """

    symbol: str
    ex_date: date
    acquired: date
    cash: float
    closed: date | None = None


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
        self.closed_dividends: list[DividendHolding] = []

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
            purchase_id=self._next_id,
        )
        self._next_id += 1
        self.lots[lot.lot_id] = lot
        self._open.setdefault(symbol, []).append(lot)
        return lot

    def split(self, lot: Lot, shares: float) -> Lot:
        """Keep the first `shares` in `lot`, returning the remaining slice.

        Every slice has one basis per share and one capital-gain holding
        period. In particular, a wash adjustment affecting four of ten shares
        must not average that adjustment over all ten.
        """

        if not 0.0 < shares < lot.shares:
            raise ValueError("a split must leave positive shares in both slices")
        fraction = shares / lot.shares
        remainder = replace(
            lot,
            lot_id=self._next_id,
            shares=lot.shares - shares,
            basis=lot.basis * (1.0 - fraction),
            replacement_capacity=max(lot.replacement_capacity - shares, 0.0),
            disallowed_attached=lot.disallowed_attached * (1.0 - fraction),
            share_offset=lot.share_offset + shares,
            dividend_claims=[replace(claim, cash=claim.cash * (1.0 - fraction))
                             for claim in lot.dividend_claims],
        )
        self._next_id += 1
        self.lots[remainder.lot_id] = remainder
        self._open[lot.symbol].append(remainder)
        lot.shares = shares
        lot.basis *= fraction
        lot.replacement_capacity = min(lot.replacement_capacity, shares)
        lot.disallowed_attached *= fraction
        lot.dividend_claims = [replace(claim, cash=claim.cash * fraction)
                              for claim in lot.dividend_claims]
        return remainder

    def dividend_holdings(self) -> tuple[DividendHolding, ...]:
        """Immutable disposal history plus the claims on shares still held."""

        return tuple(self.closed_dividends) + tuple(
            claim for lots in self._open.values() for lot in lots for claim in lot.dividend_claims
        )

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
            order = sorted(open_lots, key=lambda lot: (
                -lot.basis_per_share, lot.acquired, lot.purchase_id, lot.share_offset
            ))
        else:
            order = sorted(open_lots, key=lambda lot: (
                lot.acquired, lot.purchase_id, lot.share_offset
            ))

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
            self.closed_dividends.extend(
                replace(claim, cash=claim.cash * fraction, closed=day)
                for claim in lot.dividend_claims
            )
            lot.dividend_claims = [replace(claim, cash=claim.cash * (1.0 - fraction))
                                  for claim in lot.dividend_claims]
            lot.shares -= take
            lot.basis -= lot_basis
            lot.disallowed_attached *= 1.0 - fraction
            lot.share_offset += take
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
        F(ex_date) / F(previous session): one pooled child lot's shares are
        the sum of the recipients' shares times (growth − 1) and its basis is
        the sum of their cash, so real shares keep matching engine units
        exactly in total. One child lot per (ex-date, symbol) rather than one
        per recipient lot keeps the lot count linear in the number of
        ex-dates instead of doubling at every one — a sleeve held through N
        ex-dates would otherwise open 2^N lots. An income distribution leaves
        a parent's basis alone and is taxed; a return of capital reduces a
        parent's basis by its cash instead, and any excess over that basis is
        a capital gain realised on the ex-date. Lots acquired on or after the
        ex-date, including the child lot this call opens, receive nothing.
        """

        if dividend_per_share < 0.0:
            raise ValueError(f"negative dividend {dividend_per_share!r} for {symbol} on {ex_date}")
        recipients = [
            lot
            for lot in list(self._open.get(symbol, ()))
            if lot.acquired < ex_date and lot.shares * dividend_per_share > 0.0
        ]
        if not recipients:
            return []
        child: Lot | None = None
        if growth > 1.0:
            total_shares = sum(lot.shares for lot in recipients)
            total_cash = sum(lot.shares * dividend_per_share for lot in recipients)
            child = self.buy(
                symbol, ex_date, total_shares * (growth - 1.0), total_cash, source="reinvest"
            )
        events: list[Distribution] = []
        for lot in recipients:
            cash = lot.shares * dividend_per_share
            if return_of_capital:
                reduction = min(cash, lot.basis)
                lot.basis -= reduction
                excess = cash - reduction
                if excess > 0.0:
                    self.extra_realized.append(
                        Realized(symbol, lot.lot_id, lot.opened, ex_date, 0.0, excess, 0.0)
                    )
            else:
                lot.dividend_claims.append(DividendHolding(symbol, ex_date, lot.acquired, cash))
            events.append(
                Distribution(
                    symbol, ex_date, lot.lot_id, lot.opened, cash, return_of_capital,
                    child.lot_id if child is not None else None,
                )
            )
        return events


WASH_SALE_WINDOW = timedelta(days=30)


class WashSaleLedger:
    """Match losses against purchases in the order the purchases occur.

    Both exchange fills and reinvestments enter through `purchase`. There is
    no reservation for a known future fill, which could otherwise jump ahead
    of an earlier reinvestment. Realized records are immutable snapshots;
    later replacements replace just their disallowed-loss field, so a January
    purchase can correctly change the preceding December's taxable loss.
    """

    def __init__(self, book: LotBook) -> None:
        self.book = book
        self.realized: list[Realized] = []
        self._pending: list[int] = []

    def _match(self, index: int, candidates: list[Lot]) -> None:
        record = self.realized[index]
        loss = record.basis - record.proceeds
        remaining = record.shares * (1.0 - record.disallowed / loss)
        disallowed = record.disallowed
        for candidate in sorted(candidates, key=lambda lot: (
            lot.acquired, lot.purchase_id, lot.share_offset
        )):
            if remaining <= _SHARE_TOLERANCE:
                break
            if candidate.replacement_capacity <= _SHARE_TOLERANCE:
                continue
            take = min(candidate.replacement_capacity, remaining)
            if take < candidate.shares - _SHARE_TOLERANCE:
                self.book.split(candidate, take)
            add = loss * take / record.shares
            candidate.basis += add
            candidate.disallowed_attached += add
            candidate.opened -= record.sold - record.opened
            candidate.replacement_capacity -= take
            disallowed += add
            remaining -= take
        self.realized[index] = replace(record, disallowed=min(loss, disallowed))

    def sell(self, records: list[Realized]) -> None:
        """Record a sale after all its shares have left the book."""

        for record in records:
            index = len(self.realized)
            self.realized.append(record)
            if record.basis <= record.proceeds or record.shares <= _SHARE_TOLERANCE:
                continue
            self._match(index, [
                lot for lot in self.book.open_lots(record.symbol)
                if record.sold - WASH_SALE_WINDOW <= lot.acquired <= record.sold
            ])
            if self.realized[index].disallowed < record.basis - record.proceeds:
                self._pending.append(index)

    def purchase(self, day: date, symbol: str) -> None:
        """Offer today's new shares to still-unmatched losses, oldest first."""

        active: list[int] = []
        for index in self._pending:
            record = self.realized[index]
            if day > record.sold + WASH_SALE_WINDOW:
                continue
            if record.symbol == symbol:
                self._match(index, [
                    lot for lot in self.book.open_lots(symbol) if lot.acquired == day
                ])
            if self.realized[index].disallowed < record.basis - record.proceeds:
                active.append(index)
        self._pending = active
