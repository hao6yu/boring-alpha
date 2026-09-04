"""Year-end tax arithmetic (spec §4.5, §4.7): character, netting, carryovers, the bill.

Everything here is a pure function of amounts already expressed in the dollars
they will be taxed in. The overlay scales raw amounts by the after-tax NAV
factor before calling `net_and_tax`, and carries the returned loss pools into
the next year.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, timedelta

from boring_alpha.config import TaxConfig

LONG_TERM_DAYS = 365
QUALIFIED_WINDOW = timedelta(days=60)
QUALIFIED_MIN_DAYS = 60
MARK_LONG_SHARE = 0.6


def is_long_term(opened: date, sold: date) -> bool:
    """"More than one year", approximated as more than 365 days."""

    return (sold - opened).days > LONG_TERM_DAYS


def qualifies(opened: date, closed: date, ex_date: date) -> bool:
    """Held more than 60 days within the 121-day window beginning 60 days before the ex-date."""

    start = max(opened, ex_date - QUALIFIED_WINDOW)
    end = min(closed, ex_date + QUALIFIED_WINDOW)
    return (end - start).days > QUALIFIED_MIN_DAYS


@dataclass
class Amounts:
    """Taxable amounts of one calendar year. Losses are positive magnitudes; marks are signed."""

    qualified_income: float = 0.0
    ordinary_income: float = 0.0
    cash_interest: float = 0.0
    short_gains: float = 0.0
    short_losses: float = 0.0
    long_gains: float = 0.0
    long_losses: float = 0.0
    collectibles_gains: float = 0.0
    collectibles_losses: float = 0.0
    marks_long: float = 0.0
    marks_short: float = 0.0
    return_of_capital: float = 0.0
    wash_disallowed: float = 0.0

    def scaled(self, factor: float) -> "Amounts":
        return Amounts(**{item.name: getattr(self, item.name) * factor for item in fields(self)})

    def as_dict(self) -> dict[str, float]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    def add_gain(
        self, amount: float, *, long_term: bool, gains_class: str, mark_to_market: bool
    ) -> None:
        """Route one realised amount into its bucket.

        A mark-to-market amount is split 60/40 whatever its term, signed, as a
        Section 1256 allocation is. Otherwise short-term goes to the short pool,
        long-term collectibles to the 28% bucket, and other long-term to the
        long pool; losses are recorded as magnitudes.
        """

        if mark_to_market:
            self.marks_long += MARK_LONG_SHARE * amount
            self.marks_short += (1.0 - MARK_LONG_SHARE) * amount
            return
        if not long_term:
            if amount >= 0.0:
                self.short_gains += amount
            else:
                self.short_losses -= amount
        elif gains_class == "collectibles":
            if amount >= 0.0:
                self.collectibles_gains += amount
            else:
                self.collectibles_losses -= amount
        else:
            if amount >= 0.0:
                self.long_gains += amount
            else:
                self.long_losses -= amount


@dataclass(frozen=True, slots=True)
class YearTax:
    tax: float
    income_tax: float
    gains_tax: float
    short_net: float
    long_net: float
    collectibles_net: float
    short_carry_used: float
    long_carry_used: float
    short_carry_out: float
    long_carry_out: float


def net_and_tax(amounts: Amounts, short_carry: float, long_carry: float, tax: TaxConfig) -> YearTax:
    """Net one year's gains and losses and compute its tax (spec §4.7).

    1. Carryovers keep their character. The short-term carryover offsets net
       short-term gain; the long-term carryover offsets the collectibles bucket
       first, then other long-term gain.
    2. Long-term losses net against collectibles gains, and collectibles losses
       against long-term gains, before any cross-character offset.
    3. A net short-term loss offsets remaining long-term gain, collectibles
       first; a net long-term loss offsets remaining short-term gain.
    4. Whatever stays negative carries forward in its own pool, without limit.
    Income is taxed by character and is never offset by capital losses.
    """

    short = amounts.short_gains - amounts.short_losses + amounts.marks_short
    long = amounts.long_gains - amounts.long_losses + amounts.marks_long
    coll = amounts.collectibles_gains - amounts.collectibles_losses

    short_used = min(short_carry, max(short, 0.0))
    short -= short_used
    coll_used = min(long_carry, max(coll, 0.0))
    coll -= coll_used
    long_used = min(long_carry - coll_used, max(long, 0.0))
    long -= long_used

    if long < 0.0 < coll:
        use = min(-long, coll)
        coll -= use
        long += use
    elif coll < 0.0 < long:
        use = min(-coll, long)
        long -= use
        coll += use

    if short < 0.0:
        use = min(-short, max(coll, 0.0))
        coll -= use
        short += use
        use = min(-short, max(long, 0.0))
        long -= use
        short += use
    elif short > 0.0:
        if coll < 0.0:
            use = min(-coll, short)
            coll += use
            short -= use
        if long < 0.0:
            use = min(-long, short)
            long += use
            short -= use

    short_out = short_carry - short_used + max(-short, 0.0)
    long_out = long_carry - coll_used - long_used + max(-long, 0.0) + max(-coll, 0.0)
    gains_tax = (
        max(short, 0.0) * tax.ordinary_rate
        + max(long, 0.0) * tax.long_term_rate
        + max(coll, 0.0) * tax.collectibles_rate
    )
    income_tax = (
        amounts.qualified_income * tax.long_term_rate
        + (amounts.ordinary_income + amounts.cash_interest) * tax.ordinary_rate
    )
    return YearTax(
        tax=gains_tax + income_tax,
        income_tax=income_tax,
        gains_tax=gains_tax,
        short_net=short,
        long_net=long,
        collectibles_net=coll,
        short_carry_used=short_used,
        long_carry_used=coll_used + long_used,
        short_carry_out=short_out,
        long_carry_out=long_out,
    )
