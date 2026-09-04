"""The overlay reproduces hand-computed taxes on small constructed runs (spec §4)."""

from datetime import date
from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import load_tax_policy
from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, Fill, PriceBar
from boring_alpha.tax.overlay import apply_overlay, run_scenarios
from boring_alpha.tax.policy import SCENARIOS, Scenario

POLICY = """
[tax]
distributions_path = "distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.5
[tax.qualified_fraction]
A = 1.0
C = 0.0
[tax.gains_class]
A = "standard"
C = "commodity_pool"
"""
CODE = "c" * 64
BASE = Scenario("fifo", "deferral", "base")
LOW = Scenario("fifo", "deferral", "low")
MTM = Scenario("fifo", "mtm_60_40", "base")


def _policy():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "policy.toml"
        path.write_text(POLICY, encoding="utf-8")
        return load_tax_policy(path, ("A", "C"))


def _market(days, adjusted: dict[str, list[float]], cash_factor: float = 1.0) -> MarketData:
    bars = [
        PriceBar(day, symbol, price, price)
        for symbol, series in adjusted.items()
        for day, price in zip(days, series)
    ]
    return MarketData(bars, {day: cash_factor for day in days}, source="test")


def _table(days, unadjusted: dict[str, list[float]], dividends: dict[str, list[float]] | None = None):
    rows = []
    for symbol, series in unadjusted.items():
        paid = (dividends or {}).get(symbol, [0.0] * len(series))
        rows.extend((day, symbol, close, dividend) for day, close, dividend in zip(days, series, paid))
    return DistributionTable(rows, splits={s: [] for s in unadjusted}, sha256="d" * 64, source="test")


def _fill(day, symbol, side, quantity, price, cost=0.0) -> Fill:
    notional = quantity * price
    return Fill(day, symbol, side, quantity, price, notional, cost, notional, price)


def _result(name, curve, fills) -> BacktestResult:
    return BacktestResult(
        name=name,
        initial_equity=curve[0][1],
        equity_curve=tuple(EquityPoint(day, equity, cash, equity - cash) for day, equity, cash in curve),
        fills=tuple(fills),
        decisions=(),
    )


class BuyAndHoldWithDividendTests(unittest.TestCase):
    """Ten engine units of A bought for 990 on 2024-01-02 and held to 2025-12-31.

    Unadjusted close 100, then 99 after a 1.00 dividend on 2024-06-14, then
    110, 120, 130. Adjusted close is 99 before and equal to unadjusted after
    (factor 0.99 → 1.0). Real shares: 9.9, plus a 0.1 child lot on the ex-date.
    """

    DAYS = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 6, 14), date(2024, 12, 31),
            date(2025, 6, 30), date(2025, 12, 31)]

    def setUp(self) -> None:
        self.tax = _policy()
        self.data = _market(self.DAYS, {"A": [99.0, 99.0, 99.0, 110.0, 120.0, 130.0]})
        self.table = _table(
            self.DAYS, {"A": [100.0, 100.0, 99.0, 110.0, 120.0, 130.0]},
            {"A": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]},
        )
        curve = [
            (date(2024, 1, 2), 990.0, 0.0), (date(2024, 6, 14), 990.0, 0.0),
            (date(2024, 12, 31), 1100.0, 0.0), (date(2025, 6, 30), 1200.0, 0.0),
            (date(2025, 12, 31), 1300.0, 0.0),
        ]
        self.result = _result("hold", curve, [_fill(date(2024, 1, 2), "A", "BUY", 10.0, 99.0)])

    def _run(self, scenario=BASE) -> dict:
        return apply_overlay(
            self.result, self.data, self.table, self.tax, scenario, initial_cash=990.0, code_sha256=CODE
        )

    def test_the_dividend_is_qualified_income_taxed_in_its_year(self) -> None:
        out = self._run()
        first = out["by_year"][0]
        self.assertEqual(first["year"], 2024)
        self.assertAlmostEqual(first["qualified_income"], 9.9)
        self.assertAlmostEqual(first["ordinary_income"], 0.0)
        self.assertAlmostEqual(first["tax"], 9.9 * 0.20)
        self.assertAlmostEqual(first["scale"], 1.0)
        self.assertAlmostEqual(first["pre_tax_equity"], 1100.0)
        self.assertAlmostEqual(first["after_tax_equity"], 1100.0 - 1.98)

    def test_the_low_set_makes_half_the_dividend_ordinary(self) -> None:
        first = self._run(LOW)["by_year"][0]
        self.assertAlmostEqual(first["qualified_income"], 4.95)
        self.assertAlmostEqual(first["ordinary_income"], 4.95)
        self.assertAlmostEqual(first["tax"], 4.95 * 0.20 + 4.95 * 0.35)

    def test_the_second_year_is_rescaled_and_liquidation_is_computed_separately(self) -> None:
        out = self._run()
        second = out["by_year"][1]
        scale = 1.0 - 1.98 / 1100.0
        self.assertAlmostEqual(second["scale"], scale)
        self.assertAlmostEqual(second["tax"], 0.0)   # nothing realised in 2025 before liquidation
        self.assertAlmostEqual(out["wealth"]["pre_tax_terminal"], 1300.0)
        self.assertAlmostEqual(out["wealth"]["after_tax_pre_liquidation"], scale * 1300.0)
        # Liquidation: 9.9 shares (basis 990) and 0.1 shares (basis 9.9) sold at 130, both long-term.
        long_gain = (9.9 * 130.0 - 990.0) + (0.1 * 130.0 - 9.9)
        self.assertAlmostEqual(long_gain, 300.1)
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], long_gain * scale * 0.20)
        self.assertAlmostEqual(
            out["wealth"]["after_tax_post_liquidation"],
            scale * 1300.0 - long_gain * scale * 0.20,
        )

    def test_metrics_follow_from_the_wealth_figures(self) -> None:
        out = self._run()
        days = (date(2025, 12, 31) - date(2024, 1, 2)).days + 1
        expected_pre = (1300.0 / 990.0) ** (365.2425 / days) - 1.0
        expected_after = (out["wealth"]["after_tax_post_liquidation"] / 990.0) ** (365.2425 / days) - 1.0
        self.assertAlmostEqual(out["metrics"]["pre_tax_cagr"], expected_pre)
        self.assertAlmostEqual(out["metrics"]["after_tax_cagr"], expected_after)
        self.assertAlmostEqual(out["metrics"]["tax_drag_bps"], (expected_pre - expected_after) * 1e4)
        total_tax = out["totals"]["taxes_paid"] + out["totals"]["tax_liquidation"]
        self.assertAlmostEqual(out["metrics"]["effective_tax_rate"], total_tax / 310.0)

    def test_identities_hold_and_the_implied_price_matches_the_close(self) -> None:
        checks = self._run()["identity_checks"]
        self.assertLess(checks["share_identity_max_relative_deviation"], 1e-9)
        self.assertTrue(checks["share_identity_passed"])
        self.assertLess(checks["income_plus_gain_relative_deviation"], 1e-9)
        self.assertTrue(checks["income_plus_gain_passed"])
        self.assertEqual(checks["ex_dates_checked"], 1)
        self.assertAlmostEqual(checks["implied_reinvestment_price_ratio_min"], 1.0)
        self.assertAlmostEqual(checks["implied_reinvestment_price_ratio_max"], 1.0)
        self.assertTrue(checks["implied_price_check_passed"])

    def test_the_record_names_scenario_policy_and_provenance(self) -> None:
        out = self._run()
        self.assertEqual(out["scenario"]["key"], "fifo-deferral-base")
        self.assertEqual(out["policy"]["overlay_version"], "tax-overlay-v1")
        self.assertEqual(out["policy"]["code_sha256"], CODE)
        self.assertEqual(out["policy"]["distributions_sha256"], "d" * 64)
        self.assertEqual(len(out["policy"]["tax_policy_sha256"]), 64)
        self.assertIn("NAV convention", out["policy"]["nav_convention"])
        self.assertTrue(any("GLD" in item for item in out["totals"]["known_omissions"]))
        self.assertEqual(out["totals"]["open_lots_at_end"], 2)
        self.assertAlmostEqual(out["totals"]["unrealized_gain_at_end"], 300.1)

    def test_all_eight_scenarios_run_and_are_deterministic(self) -> None:
        first = run_scenarios(self.result, self.data, self.table, self.tax, initial_cash=990.0, code_sha256=CODE)
        second = run_scenarios(self.result, self.data, self.table, self.tax, initial_cash=990.0, code_sha256=CODE)
        self.assertEqual(list(first), [scenario.key for scenario in SCENARIOS])
        self.assertEqual(first, second)
        self.assertGreater(first["fifo-deferral-low"]["by_year"][0]["tax"], first["fifo-deferral-base"]["by_year"][0]["tax"])


class UnqualifiedHoldingTests(unittest.TestCase):
    """Bought 2024-05-20, dividend 2024-06-14, sold 2024-06-17: 28 days in the window."""

    DAYS = [date(2024, 5, 17), date(2024, 5, 20), date(2024, 6, 14), date(2024, 6, 17), date(2024, 12, 31)]

    def test_income_is_ordinary_when_the_61_day_test_fails(self) -> None:
        tax = _policy()
        data = _market(self.DAYS, {"A": [99.0, 99.0, 99.0, 99.0, 99.0]})
        table = _table(self.DAYS, {"A": [100.0, 100.0, 99.0, 99.0, 99.0]}, {"A": [0.0, 0.0, 1.0, 0.0, 0.0]})
        curve = [(date(2024, 5, 20), 990.0, 0.0), (date(2024, 6, 14), 990.0, 0.0),
                 (date(2024, 6, 17), 990.0, 990.0), (date(2024, 12, 31), 990.0, 990.0)]
        fills = [_fill(date(2024, 5, 20), "A", "BUY", 10.0, 99.0), _fill(date(2024, 6, 17), "A", "SELL", 10.0, 99.0)]
        out = apply_overlay(_result("flip", curve, fills), data, table, tax, BASE, initial_cash=990.0, code_sha256=CODE)
        year = out["by_year"][0]
        self.assertAlmostEqual(year["qualified_income"], 0.0)
        self.assertAlmostEqual(year["ordinary_income"], 9.9)
        # The parent lot lost 9.9 (proceeds 980.1 on basis 990) and the child broke even; short-term.
        self.assertAlmostEqual(year["short_losses"], 9.9)
        self.assertAlmostEqual(year["tax"], 9.9 * 0.35)
        self.assertAlmostEqual(year["short_carry_out"], 9.9)


class WashSaleThroughTheOverlayTests(unittest.TestCase):
    """Buy 10 at 100, sell at 90 a month later, buy back 10 at 90 two weeks after, hold to year end at 95."""

    DAYS = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 2, 1), date(2024, 2, 15), date(2024, 12, 31)]

    def test_the_loss_is_disallowed_and_moves_into_the_replacement_lot(self) -> None:
        tax = _policy()
        data = _market(self.DAYS, {"A": [100.0, 100.0, 90.0, 90.0, 95.0]})
        table = _table(self.DAYS, {"A": [100.0, 100.0, 90.0, 90.0, 95.0]})
        curve = [(date(2024, 1, 2), 1000.0, 0.0), (date(2024, 2, 1), 900.0, 900.0),
                 (date(2024, 2, 15), 900.0, 0.0), (date(2024, 12, 31), 950.0, 0.0)]
        fills = [
            _fill(date(2024, 1, 2), "A", "BUY", 10.0, 100.0),
            _fill(date(2024, 2, 1), "A", "SELL", 10.0, 90.0),
            _fill(date(2024, 2, 15), "A", "BUY", 10.0, 90.0),
        ]
        out = apply_overlay(_result("wash", curve, fills), data, table, tax, BASE, initial_cash=1000.0, code_sha256=CODE)
        year = out["by_year"][0]
        self.assertAlmostEqual(year["wash_disallowed"], 100.0)
        self.assertAlmostEqual(year["short_losses"], 0.0)        # the loss was not recognised
        self.assertAlmostEqual(year["tax"], 0.0)
        self.assertEqual(out["totals"]["wash_sale_count"], 1)
        self.assertAlmostEqual(out["totals"]["wash_sale_disallowed_total"], 100.0)
        # Liquidation at 95: replacement basis 900 + 100 = 1000 against proceeds 950, a 50 loss,
        # held from the tacked date 2024-01-16 to 2024-12-31: short-term.
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], 0.0)
        self.assertAlmostEqual(out["totals"]["unrealized_gain_at_end"], -50.0)
        self.assertTrue(out["identity_checks"]["income_plus_gain_passed"])


class CommodityPoolTests(unittest.TestCase):
    """Ten shares of C bought at 100 on 2024-01-02, 120 at the 2024 year end, 130 at the 2025 year end."""

    DAYS = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 12, 31), date(2025, 12, 31)]

    def setUp(self) -> None:
        self.tax = _policy()
        self.data = _market(self.DAYS, {"C": [100.0, 100.0, 120.0, 130.0]})
        self.table = _table(self.DAYS, {"C": [100.0, 100.0, 120.0, 130.0]})
        curve = [(date(2024, 1, 2), 1000.0, 0.0), (date(2024, 12, 31), 1200.0, 0.0), (date(2025, 12, 31), 1300.0, 0.0)]
        self.result = _result("pool", curve, [_fill(date(2024, 1, 2), "C", "BUY", 10.0, 100.0)])

    def test_mark_to_market_realises_each_year_sixty_forty(self) -> None:
        out = apply_overlay(self.result, self.data, self.table, self.tax, MTM, initial_cash=1000.0, code_sha256=CODE)
        first, second = out["by_year"]
        self.assertAlmostEqual(first["marks_long"], 120.0)
        self.assertAlmostEqual(first["marks_short"], 80.0)
        self.assertAlmostEqual(first["tax"], 120.0 * 0.20 + 80.0 * 0.35)
        scale = 1.0 - first["tax"] / 1200.0
        self.assertAlmostEqual(second["scale"], scale)
        self.assertAlmostEqual(second["marks_long"], 60.0 * scale)
        self.assertAlmostEqual(second["tax"], (60.0 * 0.20 + 40.0 * 0.35) * scale)
        # Basis was stepped to market at the last mark, so liquidation realises nothing more.
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], 0.0)
        self.assertAlmostEqual(out["totals"]["unrealized_gain_at_end"], 0.0)
        self.assertTrue(out["identity_checks"]["income_plus_gain_passed"])

    def test_deferral_realises_everything_at_liquidation(self) -> None:
        out = apply_overlay(self.result, self.data, self.table, self.tax, BASE, initial_cash=1000.0, code_sha256=CODE)
        self.assertAlmostEqual(out["totals"]["taxes_paid"], 0.0)
        self.assertAlmostEqual(out["wealth"]["after_tax_pre_liquidation"], 1300.0)
        # 729 days: long-term; 300 gain at 20%.
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], 60.0)
        self.assertAlmostEqual(out["wealth"]["after_tax_post_liquidation"], 1240.0)


class CashInterestTests(unittest.TestCase):
    def test_interest_on_cash_is_ordinary_income(self) -> None:
        tax = _policy()
        days = [date(2024, 1, 2), date(2024, 12, 31)]
        data = _market(days, {"A": [1.0, 1.0]}, cash_factor=1.0001)
        table = _table(days, {"A": [1.0, 1.0]})
        curve = [(date(2024, 1, 2), 1000.0, 1000.0), (date(2024, 12, 31), 1000.1, 1000.1)]
        out = apply_overlay(_result("cash", curve, []), data, table, tax, BASE, initial_cash=1000.0, code_sha256=CODE)
        year = out["by_year"][0]
        self.assertAlmostEqual(year["cash_interest"], 0.1)
        self.assertAlmostEqual(year["tax"], 0.1 * 0.35)
        self.assertEqual(out["totals"]["open_lots_at_end"], 0)
        self.assertTrue(out["identity_checks"]["share_identity_passed"])


class GuardTests(unittest.TestCase):
    def test_a_curve_with_fewer_than_two_points_is_refused(self) -> None:
        tax = _policy()
        days = [date(2024, 1, 2)]
        with self.assertRaisesRegex(ValueError, "two equity observations"):
            apply_overlay(
                _result("short", [(date(2024, 1, 2), 1.0, 1.0)], []),
                _market(days, {"A": [1.0]}), _table(days, {"A": [1.0]}), tax, BASE,
                initial_cash=1.0, code_sha256=CODE,
            )

    def test_a_symbol_without_a_gains_class_is_refused(self) -> None:
        tax = _policy()
        days = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 12, 31)]
        data = _market(days, {"Z": [1.0, 1.0, 1.0]})
        table = _table(days, {"Z": [1.0, 1.0, 1.0]})
        curve = [(date(2024, 1, 2), 10.0, 0.0), (date(2024, 12, 31), 10.0, 0.0)]
        with self.assertRaisesRegex(ValueError, "no gains class"):
            apply_overlay(_result("z", curve, [_fill(date(2024, 1, 2), "Z", "BUY", 10.0, 1.0)]),
                          data, table, tax, BASE, initial_cash=10.0, code_sha256=CODE)


if __name__ == "__main__":
    unittest.main()
