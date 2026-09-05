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
from datetime import date
import math

from boring_alpha.config import TaxConfig
from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, Fill
from boring_alpha.tax.lots import (
    Distribution,
    LotBook,
    Realized,
    WashSaleLedger,
    adjustment_factor,
)
from boring_alpha.tax.loss_sensitivity import (
    LossDeductionPolicy,
    SENSITIVITY_VERSION,
    evaluate_deduction_year,
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
    "next rebalance are not modelled. Their size depends on each account's "
    "available cash and tax liability; no cash-sufficiency assumption is made."
)
KNOWN_OMISSIONS = (
    "GLD expense sales: the trust sells gold to pay its expense ratio and holders "
    "recognise their share with a basis adjustment; not modelled, bounded near one "
    "hundredth of one percent of portfolio return a year (spec §4.6).",
    "State tax, the 3.8% net investment income tax and historical rate changes are "
    "ignored; rates are a fixed federal-only scenario (spec §4.9).",
    "Commodity-pool interest income is not separated from futures gains under the "
    "mark-to-market treatment (spec §4.5).",
    "The ordinary-income capital-loss deduction is excluded from baseline and "
    "gating results. It can be examined only in a separate, explicit household "
    "tax sensitivity; available capacity and future carryover effects matter.",
)
# The identity compares real shares times unadjusted close against engine
# units times adjusted close on every session. With a piecewise-constant
# adjustment factor (see adjustment_factor) the difference is exactly
# Yahoo's rounding of the adjusted close, observed up to ~1e-6 relative; 1e-5
# passes that while still catching a genuine unit error, and the maximum
# deviation is reported regardless of whether the check passes.
SHARE_IDENTITY_TOLERANCE = 1e-5
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
    loss_sensitivity: LossDeductionPolicy | None = None,
) -> dict:
    if loss_sensitivity is not None and not isinstance(loss_sensitivity, LossDeductionPolicy):
        raise ValueError("loss_sensitivity must be an explicit LossDeductionPolicy")
    curve = result.equity_curve
    if len(curve) < 2:
        raise ValueError("at least two equity observations are required")
    if initial_cash <= 0.0:
        raise ValueError("initial cash must be positive")
    if result.initial_equity > 0.0:
        relative = abs(result.initial_equity - initial_cash) / result.initial_equity
        if relative > 1e-9:
            raise ValueError(
                f"result.initial_equity ({result.initial_equity!r}) does not match "
                f"initial_cash ({initial_cash!r})"
            )
    sessions = [point.date for point in curve]
    first, last = sessions[0], sessions[-1]
    symbols = sorted({fill.symbol for fill in result.fills})
    for symbol in symbols:
        if symbol not in tax.gains_class:
            raise ValueError(f"the tax policy names no gains class for {symbol}")
    session_set = set(sessions)
    seen_fills: set[tuple[date, str]] = set()
    for fill in result.fills:
        if fill.date not in session_set:
            raise ValueError(
                f"a fill for {fill.symbol} on {fill.date} is not a session of the equity curve"
            )
        key = (fill.date, fill.symbol)
        if key in seen_fills:
            raise ValueError(
                "the engine never fills one symbol twice in a session; the inputs are inconsistent"
            )
        seen_fills.add(key)
    table.require_coverage(data, tuple(symbols))
    index_of = {day: index for index, day in enumerate(data.dates)}

    def factor(day: date, symbol: str) -> float:
        return adjustment_factor(data, table, day, symbol)

    # ---- Phase A: replay the run in real shares --------------------------------
    book = LotBook(scenario.lot_method)
    wash = WashSaleLedger(book)
    fills_by_date: dict[date, list[Fill]] = defaultdict(list)
    for fill in result.fills:
        fills_by_date[fill.date].append(fill)
    engine_units: dict[str, float] = defaultdict(float)
    distributions: list[Distribution] = []
    marks: list[tuple[date, float]] = []
    interest_by_year: dict[int, float] = defaultdict(float)
    year_end_equity: dict[int, float] = {}
    implied_ratios: list[float] = []
    ex_dates_without_growth = 0
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
            if growth <= 1.0:
                ex_dates_without_growth += 1
            implied_ratios.append(
                (dividend / (growth - 1.0)) / table.close(day, symbol) if growth > 1.0 else math.inf
            )
            return_of_capital = tax.gains_class[symbol] == "commodity_pool"
            events = book.distribute(symbol, day, dividend, growth, return_of_capital=return_of_capital)
            distributions.extend(events)
            child_id = next((event.child_lot_id for event in events if event.child_lot_id is not None), None)
            if child_id is not None:
                wash.purchase(day, symbol)

        for fill in fills_by_date.get(day, ()):
            if fill.quantity == 0.0:
                continue
            shares = fill.quantity * factor(day, fill.symbol)
            if fill.side == "SELL":
                engine_units[fill.symbol] -= fill.quantity
                records = book.sell(fill.symbol, day, shares, fill.notional - fill.cost)
                wash.sell(records)
            else:
                engine_units[fill.symbol] += fill.quantity
                book.buy(
                    fill.symbol,
                    day,
                    shares,
                    fill.notional + fill.cost,
                )
                wash.purchase(day, fill.symbol)

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
                        marks.append((day, value - lot.basis))
                        lot.basis = value

    realized = wash.realized + book.extra_realized
    dividend_holdings = book.dividend_holdings()
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
        for holding in dividend_holdings:
            if holding.ex_date.year != year:
                continue
            fraction = (
                qualified_fraction(tax, scenario, holding.symbol)
                if qualifies(holding.acquired, holding.closed or last, holding.ex_date)
                else 0.0
            )
            amounts.qualified_income += holding.cash * fraction
            amounts.ordinary_income += holding.cash * (1.0 - fraction)
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
        for mark_day, amount in marks:
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
    contributed_savings = outside_savings = 0.0
    liquidation_savings_adjustment = 0.0
    terminal_deduction = None
    for year in years:
        equity = year_end_equity[year]
        if equity <= 0.0:
            raise ValueError(f"equity at the {year} year end is not positive; the NAV convention needs it")
        amounts = amounts_for(year, include_liquidation=False).scaled(scale)
        deduction = (
            evaluate_deduction_year(amounts, short_carry, long_carry, tax, loss_sensitivity)
            if loss_sensitivity is not None else None
        )
        outcome = deduction.taxes if deduction is not None else net_and_tax(amounts, short_carry, long_carry, tax)
        contribution = outside = 0.0
        if deduction is not None:
            if loss_sensitivity.savings_destination == "contribute_to_account":
                contribution = deduction.ordinary_tax_savings
            else:
                outside = deduction.ordinary_tax_savings
        if year == years[-1]:
            liquidation_amounts = amounts_for(year, include_liquidation=True).scaled(scale)
            if loss_sensitivity is not None:
                # These are alternative final tax returns from the same carry-in,
                # not a second annual deduction after the no-liquidation return.
                terminal_deduction = evaluate_deduction_year(
                    liquidation_amounts, short_carry, long_carry, tax, loss_sensitivity
                )
                with_liquidation = terminal_deduction.taxes
                liquidation_savings_adjustment = (
                    terminal_deduction.ordinary_tax_savings - deduction.ordinary_tax_savings
                )
            else:
                with_liquidation = net_and_tax(liquidation_amounts, short_carry, long_carry, tax)
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
                "after_tax_equity": scale * equity - outcome.tax + contribution,
                **({
                    **deduction.as_dict(),
                    "tax_savings_contributed": contribution,
                    "tax_savings_outside": outside,
                } if deduction is not None else {}),
            }
        )
        taxes_paid += outcome.tax
        contributed_savings += contribution
        outside_savings += outside
        short_carry, long_carry = outcome.short_carry_out, outcome.long_carry_out
        scale = scale - outcome.tax / equity + contribution / equity
        if loss_sensitivity is not None and year != years[-1] and (not math.isfinite(scale) or scale <= 0.0):
            raise ValueError("year-end tax exhausts the account under the NAV convention")
        # A scale above one can also arise from the baseline's existing signed
        # cash-income tax arithmetic. Contributions are identified by their
        # explicit cash-flow field, not inferred from the level of NAV scale.

    pre_tax_terminal = curve[-1].equity
    pre_liquidation = by_year[-1]["after_tax_equity"]
    post_liquidation = pre_liquidation - tax_liquidation
    contributed_post = contributed_savings
    outside_post = outside_savings
    if loss_sensitivity is not None:
        if loss_sensitivity.savings_destination == "contribute_to_account":
            post_liquidation += liquidation_savings_adjustment
            contributed_post += liquidation_savings_adjustment
        else:
            outside_post += liquidation_savings_adjustment

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
        + sum(amount for _, amount in marks)
    )
    pnl_deviation = abs(income_total + gains_total - adjusted_pnl) / max(abs(adjusted_pnl), initial_cash)
    finite_ratios = [ratio for ratio in implied_ratios if math.isfinite(ratio)]
    ratio_min = min(finite_ratios) if finite_ratios else None
    ratio_max = max(finite_ratios) if finite_ratios else None
    implied_ok = ex_dates_without_growth == 0 and all(
        abs(ratio - 1.0) <= IMPLIED_PRICE_TOLERANCE for ratio in finite_ratios
    )

    days = (last - first).days + 1
    pre_tax_cagr = _cagr(pre_tax_terminal, initial_cash, days)
    after_tax_cagr = _cagr(post_liquidation, initial_cash, days) if post_liquidation > 0.0 else None
    if loss_sensitivity is not None and loss_sensitivity.savings_destination == "contribute_to_account":
        # A terminal/initial ratio with external deposits is not a self-financing
        # investment return. No money-weighted or household CAGR is claimed.
        after_tax_cagr = None
    profit = pre_tax_terminal - initial_cash
    total_tax = taxes_paid + tax_liquidation

    output = {
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
            "wash_sale_count": len(
                {(record.sold, record.symbol) for record in realized if record.disallowed > 0.0}
            ),
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
            "tax_drag_bps": (
                (pre_tax_cagr - after_tax_cagr) * 10_000.0 if after_tax_cagr is not None else None
            ),
            "effective_tax_rate": (
                total_tax / profit if profit > 0.0 and not (
                    loss_sensitivity is not None
                    and loss_sensitivity.savings_destination == "contribute_to_account"
                ) else None
            ),
        },
        "identity_checks": {
            "share_identity_max_relative_deviation": share_deviation,
            "share_identity_passed": share_deviation <= SHARE_IDENTITY_TOLERANCE,
            "income_plus_gain_relative_deviation": pnl_deviation,
            "income_plus_gain_passed": pnl_deviation <= PNL_IDENTITY_TOLERANCE,
            "ex_dates_checked": len(implied_ratios),
            "ex_dates_without_growth": ex_dates_without_growth,
            "implied_reinvestment_price_ratio_min": ratio_min,
            "implied_reinvestment_price_ratio_max": ratio_max,
            "implied_price_check_passed": implied_ok,
        },
    }
    if loss_sensitivity is not None:
        output["loss_sensitivity"] = {
            "version": SENSITIVITY_VERSION,
            "non_gating": True,
            "policy": loss_sensitivity.as_dict(tax),
            "policy_sha256": loss_sensitivity.sha256(tax),
            "initial_account_size": initial_cash,
            "timing": "Savings are recognised at each evaluated calendar year's final observation; terminal liquidation replaces that year's deduction, it does not add another one.",
            "contribution_convention": "Contributed savings increase the following year's NAV scale. This is a stylized proportional rescaling, not new real-share lots with fresh basis, funding costs or an exact deposit simulation. Contribution-mode CAGR, tax drag and effective tax rate are suppressed.",
            "household_scope": "Alternative standalone accounts each use the declared remaining household capacity; their benefits must not be summed as simultaneous accounts. Outside savings are retained without interest or reinvestment. Income brackets and other household transactions are not calculated.",
            "terminal_liquidation": {
                **terminal_deduction.as_dict(),
                "short_carry_out": terminal_deduction.taxes.short_carry_out,
                "long_carry_out": terminal_deduction.taxes.long_carry_out,
                "ordinary_tax_savings_adjustment": liquidation_savings_adjustment,
            },
        }
        output["wealth"].update({
            "outside_tax_savings_pre_liquidation": outside_savings,
            "outside_tax_savings_post_liquidation": outside_post,
            "contributed_tax_savings_pre_liquidation": contributed_savings,
            "contributed_tax_savings_post_liquidation": contributed_post,
            "household_terminal_wealth": post_liquidation + outside_post,
        })
        output["totals"]["known_omissions"] = [
            item for item in KNOWN_OMISSIONS if not item.startswith("The ordinary-income capital-loss deduction")
        ]
    return output


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
