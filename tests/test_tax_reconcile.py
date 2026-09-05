"""Archive consistency uses an independent, hand-computed account history."""

from dataclasses import replace
from datetime import date
import unittest

from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, Fill, PriceBar
from boring_alpha.tax.reconcile import validate_replay


DAYS = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))


def account():
    data = MarketData(
        [PriceBar(day, "A", op, close) for day, op, close in zip(DAYS, (10.0, 11.0, 12.0), (10.0, 12.0, 11.0))],
        {DAYS[0]: 9.0, DAYS[1]: 1.1, DAYS[2]: 1.0},
        source="hand-calculated",
    )
    # $100 -> buy five for $50 plus $1 cost: cash49, stock50.
    # Next session cash earns $4.90; sell two for $22 less $1: cash74.90,
    # three shares close at $12 = $36. Final equity74.90+33 = $107.90.
    fills = (
        Fill(DAYS[0], "A", "BUY", 5.0, 10.0, 50.0, 1.0, 50.0, 10.0),
        Fill(DAYS[1], "A", "SELL", 2.0, 11.0, 22.0, 1.0, 22.0, 10.0),
    )
    curve = (
        EquityPoint(DAYS[0], 99.0, 49.0, 50.0),
        EquityPoint(DAYS[1], 110.9, 74.9, 36.0),
        EquityPoint(DAYS[2], 107.9, 74.9, 33.0),
    )
    return BacktestResult("hand", 100.0, curve, fills, ()), data


class ReplayReconciliationTests(unittest.TestCase):
    def test_cash_interest_costs_partial_sale_and_final_hold_reconcile(self):
        result, data = account()
        validate_replay(result, data, 100.0)

    def test_empty_or_incomplete_trade_ledger_is_refused(self):
        result, data = account()
        for fills in ((), result.fills[:1], result.fills[1:]):
            with self.subTest(fills=fills), self.assertRaisesRegex(ValueError, "replay"):
                validate_replay(replace(result, fills=fills), data, 100.0)

    def test_cash_exposure_and_equity_are_each_independently_checked(self):
        result, data = account()
        for field in ("cash", "gross_exposure", "equity"):
            corrupt = replace(result.equity_curve[-1], **{field: getattr(result.equity_curve[-1], field) + 1.0})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "mismatch"):
                validate_replay(replace(result, equity_curve=result.equity_curve[:-1] + (corrupt,)), data, 100.0)

    def test_missing_duplicate_and_out_of_order_sessions_are_refused(self):
        result, data = account()
        curves = (result.equity_curve[::2], result.equity_curve + result.equity_curve[-1:], result.equity_curve[::-1])
        for curve in curves:
            with self.subTest(curve=curve), self.assertRaisesRegex(ValueError, "replay equity"):
                validate_replay(replace(result, equity_curve=curve), data, 100.0)

    def test_nonfinite_account_and_fill_values_are_refused(self):
        result, data = account()
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite"):
                validate_replay(result, data, value)
            for field in ("cash", "gross_exposure", "equity"):
                point = replace(result.equity_curve[0], **{field: value})
                with self.subTest(value=value, field=field), self.assertRaisesRegex(ValueError, "finite"):
                    validate_replay(replace(result, equity_curve=(point,) + result.equity_curve[1:]), data, 100.0)
            for field in ("quantity", "price", "notional", "cost", "intended_notional", "reference_price"):
                fill = replace(result.fills[0], **{field: value})
                with self.subTest(value=value, field=field), self.assertRaisesRegex(ValueError, "finite"):
                    validate_replay(replace(result, fills=(fill,) + result.fills[1:]), data, 100.0)

    def test_corrupt_notional_price_side_and_quantity_are_refused(self):
        result, data = account()
        changes = ({"notional": 49.0}, {"price": 9.0}, {"side": "BAD"}, {"quantity": -5.0})
        for change in changes:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "replay"):
                validate_replay(replace(result, fills=(replace(result.fills[0], **change),) + result.fills[1:]), data, 100.0)

    def test_empty_trade_ledger_is_valid_for_an_actual_cash_account(self):
        result, data = account()
        cash = replace(result, fills=(), equity_curve=(
            EquityPoint(DAYS[0], 100.0, 100.0, 0.0),
            EquityPoint(DAYS[1], 110.0, 110.0, 0.0),
            EquityPoint(DAYS[2], 110.0, 110.0, 0.0),
        ))
        validate_replay(cash, data, 100.0)


if __name__ == "__main__":
    unittest.main()
