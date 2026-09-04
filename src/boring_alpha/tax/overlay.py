"""The after-tax overlay (spec §4): pre-tax artifacts in, after-tax wealth out.

A pure function of a run's fills and equity curve, the market data it ran on,
the distributions table, a tax policy and one scenario. It never touches the
engine. Phase A replays the run chronologically in real shares: distributions
open child lots, sales close lots by the scenario's method, wash sales are
applied as they happen, commodity pools are marked at year ends when the
scenario says so. Phase B taxes each calendar year under the after-tax NAV
convention (spec §4.8): raw amounts are scaled by the cumulative factor, taxed,
and the factor is reduced by the tax paid over that year-end equity.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import math

from boring_alpha.config import TaxConfig
from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, Fill
from boring_alpha.tax.lots import (
    WASH_SALE_WINDOW,
    Distribution,
    FuturePurchase,
    LotBook,
    Realized,
    adjustment_factor,
    apply_wash_sales,
)
from boring_alpha.tax.policy import (
    OVERLAY_VERSION,
    SCENARIOS,
    Scenario,
    policy_record,
    policy_sha256,
    qualified_fraction,
)
from boring_alpha.tax.yearend import Amounts, is_long_term, net_and_tax, qualifies

NAV_CONVENTION = (
    "after-tax NAV convention (spec §4.8): the pre-tax path is rescaled at each "
    "year end by the tax paid over that year-end equity. Raising the cash to pay, "
    "its trading cost, the gain realised doing so, and exposure drift until the "
    "next rebalance are not modelled; both accounts hold enough cash that these "
    "are second order."
)
KNOWN_OMISSIONS = (
    "GLD expense sales: the trust sells gold to pay its expense ratio and holders "
    "recognise their share with a basis adjustment; not modelled, bounded near one "
    "hundredth of one percent of portfolio return a year (spec §4.6).",
    "State tax, the 3.8% net investment income tax and historical rate changes are "
    "ignored; rates are a fixed federal-only scenario (spec §4.9).",
    "Commodity-pool interest income is not separated from futures gains under the "
    "mark-to-market treatment (spec §4.5).",
    "Reinvested distributions inherit no wash-sale role once a later loss sale's "
    "window opens after them; only purchases known at sale time are matched.",
)
SHARE_IDENTITY_TOLERANCE = 1e-6
PNL_IDENTITY_TOLERANCE = 1e-6
IMPLIED_PRICE_TOLERANCE = 0.05
DAYS_PER_YEAR = 365.2425


def _cagr(terminal: float, initial: float, days: int) -> float:
    return (terminal / initial) ** (DAYS_PER_YEAR / days) - 1.0


def apply_overlay(
    result: BacktestResult,
    data: MarketData,
    table: DistributionTable,
    tax: TaxConfig,
    scenario: Scenario,
    *,
    initial_cash: float,
    code_sha256: str,
) -> dict:
    curve = result.equity_curve
    if len(curve) < 2:
        raise ValueError("at least two equity observations are required")
    if initial_cash <= 0.0:
        raise ValueError("initial cash must be positive")
    sessions = [point.date for point in curve]
    first, last = sessions[0], sessions[-1]
    symbols = sorted({fill.symbol for fill in result.fills})
    for symbol in symbols:
        if symbol not in tax.gains_class:
            raise ValueError(f"the tax policy names no gains class for {symbol}")
    table.require_coverage(data, tuple(symbols))
    index_of = {day: index for index, day in enumerate(data.dates)}

    def factor(day: date, symbol: str) -> float:
        return adjustment_factor(data, table, day, symbol)

    # ---- Phase A: replay the run in real shares --------------------------------
    book = LotBook(scenario.lot_method)
    fills_by_date: dict[date, list[Fill]] = defaultdict(list)
    for fill in result.fills:
        fills_by_date[fill.date].append(fill)
    future: dict[tuple[date, str], FuturePurchase] = {}
    for fill in result.fills:
        if fill.side == "BUY":
            shares = fill.quantity * factor(fill.date, fill.symbol)
            future[(fill.date, fill.symbol)] = FuturePurchase(fill.symbol, fill.date, shares, shares)

    engine_units: dict[str, float] = defaultdict(float)
    realized: list[Realized] = []
    distributions: list[Distribution] = []
    marks: list[tuple[date, str, float]] = []
    interest_by_year: dict[int, float] = defaultdict(float)
    year_end_equity: dict[int, float] = {}
    implied_ratios: list[float] = []
    share_deviation = 0.0

    for index, day in enumerate(sessions):
        point = curve[index]
        if index > 0:
            interest_by_year[day.year] += curve[index - 1].cash * (data.cash_factors[day] - 1.0)

        for symbol in symbols:
            dividend = table.dividend(day, symbol)
            if dividend <= 0.0:
                continue
            previous = index_of[day] - 1
            growth = (
                factor(day, symbol) / factor(data.dates[previous], symbol) if previous >= 0 else 1.0
            )
            implied_ratios.append(
                (dividend / (growth - 1.0)) / table.close(day, symbol) if growth > 1.0 else math.inf
            )
            return_of_capital = tax.gains_class[symbol] == "commodity_pool"
            distributions.extend(
                book.distribute(symbol, day, dividend, growth, return_of_capital=return_of_capital)
            )

        for fill in fills_by_date.get(day, ()):
            shares = fill.quantity * factor(day, fill.symbol)
            if fill.side == "SELL":
                engine_units[fill.symbol] -= fill.quantity
                records = book.sell(fill.symbol, day, shares, fill.notional - fill.cost)
                window = [
                    purchase
                    for (purchase_day, symbol), purchase in future.items()
                    if symbol == fill.symbol and day < purchase_day <= day + WASH_SALE_WINDOW
                ]
                realized.extend(apply_wash_sales(records, book.open_lots(fill.symbol), window))
            else:
                engine_units[fill.symbol] += fill.quantity
                purchase = future.pop((day, fill.symbol))
                book.buy(
                    fill.symbol,
                    day,
                    shares,
                    fill.notional + fill.cost,
                    opened=day - timedelta(days=purchase.pending_tack_days)
                    if purchase.pending_tack_days
                    else None,
                    extra_basis=purchase.pending_basis,
                    replacement_capacity=purchase.replacement_capacity,
                )

        for symbol in symbols:
            engine_value = engine_units[symbol] * data.bar(day, symbol).close
            real_value = book.shares_held(symbol) * table.close(day, symbol)
            share_deviation = max(
                share_deviation, abs(real_value - engine_value) / max(abs(engine_value), 1.0)
            )

        year_end = index == len(sessions) - 1 or sessions[index + 1].year != day.year
        if year_end:
            year_end_equity[day.year] = point.equity
            if scenario.commodity_treatment == "mtm_60_40":
                for symbol in symbols:
                    if tax.gains_class[symbol] != "commodity_pool":
                        continue
                    price = table.close(day, symbol)
                    for lot in book.open_lots(symbol):
                        value = lot.shares * price
                        marks.append((day, symbol, value - lot.basis))
                        lot.basis = value

    realized.extend(book.extra_realized)
    liquidation: list[Realized] = []
    unrealized = 0.0
    open_lots = 0
    for symbol in symbols:
        price = table.close(last, symbol)
        for lot in book.open_lots(symbol):
            proceeds = lot.shares * price
            liquidation.append(Realized(symbol, lot.lot_id, lot.opened, last, lot.shares, proceeds, lot.basis))
            unrealized += proceeds - lot.basis
            open_lots += 1

    # ---- Phase B: tax each calendar year under the NAV convention ---------------
    def amounts_for(year: int, *, include_liquidation: bool) -> Amounts:
        amounts = Amounts()
        for event in distributions:
            if event.ex_date.year != year:
                continue
            if event.return_of_capital:
                amounts.return_of_capital += event.cash
                continue
            lot = book.lots[event.lot_id]
            fraction = (
                qualified_fraction(tax, scenario, event.symbol)
                if qualifies(lot.opened, lot.closed or last, event.ex_date)
                else 0.0
            )
            amounts.qualified_income += event.cash * fraction
            amounts.ordinary_income += event.cash * (1.0 - fraction)
        records = [record for record in realized if record.sold.year == year]
        if include_liquidation:
            records += [record for record in liquidation if record.sold.year == year]
        for record in records:
            gains_class = tax.gains_class[record.symbol]
            mark_to_market = (
                gains_class == "commodity_pool" and scenario.commodity_treatment == "mtm_60_40"
            )
            amounts.add_gain(
                record.gain,
                long_term=is_long_term(record.opened, record.sold),
                gains_class=gains_class,
                mark_to_market=mark_to_market,
            )
            amounts.wash_disallowed += record.disallowed
        for mark_day, _, amount in marks:
            if mark_day.year == year:
                amounts.add_gain(amount, long_term=False, gains_class="commodity_pool", mark_to_market=True)
        amounts.cash_interest += interest_by_year.get(year, 0.0)
        return amounts

    years = sorted(year_end_equity)
    scale = 1.0
    short_carry = long_carry = 0.0
    by_year: list[dict] = []
    taxes_paid = 0.0
    tax_liquidation = 0.0
    for year in years:
        equity = year_end_equity[year]
        if equity <= 0.0:
            raise ValueError(f"equity at the {year} year end is not positive; the NAV convention needs it")
        amounts = amounts_for(year, include_liquidation=False).scaled(scale)
        outcome = net_and_tax(amounts, short_carry, long_carry, tax)
        if year == years[-1]:
            with_liquidation = net_and_tax(
                amounts_for(year, include_liquidation=True).scaled(scale), short_carry, long_carry, tax
            )
            tax_liquidation = with_liquidation.tax - outcome.tax
        by_year.append(
            {
                "year": year,
                **amounts.as_dict(),
                "short_carry_used": outcome.short_carry_used,
                "long_carry_used": outcome.long_carry_used,
                "short_carry_out": outcome.short_carry_out,
                "long_carry_out": outcome.long_carry_out,
                "scale": scale,
                "income_tax": outcome.income_tax,
                "gains_tax": outcome.gains_tax,
                "tax": outcome.tax,
                "pre_tax_equity": equity,
                "after_tax_equity": scale * equity - outcome.tax,
            }
        )
        taxes_paid += outcome.tax
        short_carry, long_carry = outcome.short_carry_out, outcome.long_carry_out
        scale = scale - outcome.tax / equity

    pre_tax_terminal = curve[-1].equity
    pre_liquidation = by_year[-1]["after_tax_equity"]
    post_liquidation = pre_liquidation - tax_liquidation

    # ---- Identities ---------------------------------------------------------------
    adjusted_pnl = (
        sum(fill.notional - fill.cost for fill in result.fills if fill.side == "SELL")
        - sum(fill.notional + fill.cost for fill in result.fills if fill.side == "BUY")
        + sum(record.proceeds for record in liquidation)
    )
    income_total = sum(event.cash for event in distributions if not event.return_of_capital)
    gains_total = (
        sum(record.gain for record in realized)
        + sum(record.gain for record in liquidation)
        + sum(amount for _, _, amount in marks)
    )
    pnl_deviation = abs(income_total + gains_total - adjusted_pnl) / max(abs(adjusted_pnl), initial_cash)
    finite_ratios = [ratio for ratio in implied_ratios if math.isfinite(ratio)]
    ratio_min = min(finite_ratios) if finite_ratios else None
    ratio_max = max(finite_ratios) if finite_ratios else None
    implied_ok = len(finite_ratios) == len(implied_ratios) and all(
        abs(ratio - 1.0) <= IMPLIED_PRICE_TOLERANCE for ratio in finite_ratios
    )

    days = (last - first).days + 1
    pre_tax_cagr = _cagr(pre_tax_terminal, initial_cash, days)
    after_tax_cagr = _cagr(post_liquidation, initial_cash, days) if post_liquidation > 0.0 else -1.0
    profit = pre_tax_terminal - initial_cash
    total_tax = taxes_paid + tax_liquidation

    return {
        "scenario": scenario.as_dict(),
        "policy": {
            **policy_record(tax),
            "tax_policy_sha256": policy_sha256(tax),
            "distributions_sha256": table.sha256,
            "overlay_version": OVERLAY_VERSION,
            "code_sha256": code_sha256,
            "nav_convention": NAV_CONVENTION,
        },
        "by_year": by_year,
        "totals": {
            "taxes_paid": taxes_paid,
            "tax_liquidation": tax_liquidation,
            "wash_sale_count": sum(1 for record in realized if record.disallowed > 0.0),
            "wash_sale_disallowed_total": sum(record.disallowed for record in realized),
            "return_of_capital_total": sum(
                event.cash for event in distributions if event.return_of_capital
            ),
            "unrealized_gain_at_end": unrealized,
            "open_lots_at_end": open_lots,
            "known_omissions": list(KNOWN_OMISSIONS),
        },
        "wealth": {
            "pre_tax_terminal": pre_tax_terminal,
            "after_tax_pre_liquidation": pre_liquidation,
            "after_tax_post_liquidation": post_liquidation,
        },
        "metrics": {
            "pre_tax_cagr": pre_tax_cagr,
            "after_tax_cagr": after_tax_cagr,
            "tax_drag_bps": (pre_tax_cagr - after_tax_cagr) * 10_000.0,
            "effective_tax_rate": total_tax / profit if profit > 0.0 else None,
        },
        "identity_checks": {
            "share_identity_max_relative_deviation": share_deviation,
            "share_identity_passed": share_deviation <= SHARE_IDENTITY_TOLERANCE,
            "income_plus_gain_relative_deviation": pnl_deviation,
            "income_plus_gain_passed": pnl_deviation <= PNL_IDENTITY_TOLERANCE,
            "ex_dates_checked": len(implied_ratios),
            "implied_reinvestment_price_ratio_min": ratio_min,
            "implied_reinvestment_price_ratio_max": ratio_max,
            "implied_price_check_passed": implied_ok,
        },
    }


def run_scenarios(
    result: BacktestResult,
    data: MarketData,
    table: DistributionTable,
    tax: TaxConfig,
    *,
    initial_cash: float,
    code_sha256: str,
) -> dict[str, dict]:
    """Every scenario of the fixed grid, keyed by scenario key, in grid order."""

    return {
        scenario.key: apply_overlay(
            result, data, table, tax, scenario, initial_cash=initial_cash, code_sha256=code_sha256
        )
        for scenario in SCENARIOS
    }
