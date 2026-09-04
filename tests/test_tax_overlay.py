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
HIFO = Scenario("hifo", "deferral", "base")

# The shared POLICY plus a collectibles-taxed symbol G, for the one test that
# needs it (finding 4's collectibles case). Kept separate from POLICY/_policy()
# so every other test's universe of ("A", "C") is untouched.
COLLECTIBLES_POLICY = POLICY.replace(
    "A = 1.0\nC = 0.0\n", "A = 1.0\nC = 0.0\nG = 0.0\n"
).replace(
    'A = "standard"\nC = "commodity_pool"\n',
    'A = "standard"\nC = "commodity_pool"\nG = "collectibles"\n',
)


def _policy():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "policy.toml"
        path.write_text(POLICY, encoding="utf-8")
        return load_tax_policy(path, ("A", "C"))


def _policy_with_collectibles():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "policy.toml"
        path.write_text(COLLECTIBLES_POLICY, encoding="utf-8")
        return load_tax_policy(path, ("A", "C", "G"))


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


class QualifiedDividendUsesTheAcquiredDateTests(unittest.TestCase):
    """A dividend must be judged by how long the lot was actually held, not by
    a wash-sale tack that lengthens the holding period for gain-character
    purposes only.

    Lot Y: 10 units bought 2024-05-01, sold at a loss on 2024-06-20 (proceeds
    900 against basis 1000: a 100 loss). Lot X: 10 units bought 2024-06-01,
    still open on 2024-06-20 and so a wash-sale replacement for Y's loss (its
    acquisition date is within 30 days of the sale) -- the whole 100 loss
    tacks onto X, and X's `opened` moves back by 50 days (Y's holding period)
    to 2024-04-12. X is then fully sold on 2024-07-05: 34 days after its real
    acquisition date (2024-06-01), so its 2024-06-14 dividend is unqualified
    under the 61-day test using `acquired`. Using the tacked `opened`
    (2024-04-12) instead would count 81 days and wrongly qualify it. Factor
    stays at 1.0 throughout (adjusted == unadjusted), so growth is 1.0 and no
    child lot complicates the picture.
    """

    DAYS = [date(2024, 5, 1), date(2024, 6, 1), date(2024, 6, 14), date(2024, 6, 20), date(2024, 7, 5)]

    def test_the_dividend_on_the_wash_saled_lot_stays_ordinary(self) -> None:
        tax = _policy()
        data = _market(self.DAYS, {"A": [100.0] * 5})
        table = _table(self.DAYS, {"A": [100.0] * 5}, {"A": [0.0, 0.0, 1.0, 0.0, 0.0]})
        curve = [
            (date(2024, 5, 1), 1000.0, 0.0),
            (date(2024, 6, 1), 2000.0, 0.0),
            (date(2024, 6, 14), 2000.0, 0.0),
            (date(2024, 6, 20), 1100.0, 900.0),
            (date(2024, 7, 5), 1000.0, 1900.0),
        ]
        fills = [
            _fill(date(2024, 5, 1), "A", "BUY", 10.0, 100.0),
            _fill(date(2024, 6, 1), "A", "BUY", 10.0, 100.0),
            _fill(date(2024, 6, 20), "A", "SELL", 10.0, 90.0),
            _fill(date(2024, 7, 5), "A", "SELL", 10.0, 90.0),
        ]
        out = apply_overlay(
            _result("tacked-dividend", curve, fills), data, table, tax, BASE,
            initial_cash=1000.0, code_sha256=CODE,
        )
        year = out["by_year"][0]
        # Both lots' dividends are unqualified (Y: 50 days; X: 34 days by its
        # real acquisition date), so the whole 20 of income is ordinary.
        self.assertAlmostEqual(year["ordinary_income"], 20.0)
        self.assertAlmostEqual(year["qualified_income"], 0.0)


class ReinvestedLotsAsWashSaleReplacementsTests(unittest.TestCase):
    """A reinvested distribution counts as a purchase for a still-open wash
    sale window, even though the code only learns of it when the ex-date
    arrives (spec §4.6).

    Buy 20 units of A on 2023-12-01 (outside any window that matters here).
    Sell 10 at a loss on 2024-02-01: proceeds 900 against basis 1000 for those
    ten (a 100 loss); no candidate is open or scheduled at that moment, so
    none of it is disallowed yet. The factor is 0.995 from 2023-12-01 through
    2024-02-14 (so the remaining 9.95 real shares are consistent at both the
    buy and the sell) and steps to 1.0 exactly on the 2024-02-15 ex-date,
    where a 0.50/share dividend pools the still-held 9.95 shares into one
    child lot of 9.95 x (1/0.995 - 1) = 0.05 shares. That child's own
    replacement capacity (0.05 shares) is smaller than the 9.95 shares still
    unmatched from the February loss, so only 0.05 shares' worth of the loss
    -- 100 x 0.05 / 9.95, about 0.5025 -- moves onto the child; the rest of
    the loss stays unmatched (there is nothing left to absorb it here).
    """

    def test_the_childs_capacity_matches_part_of_the_open_loss(self) -> None:
        tax = _policy()
        days = [date(2023, 12, 1), date(2024, 2, 1), date(2024, 2, 14), date(2024, 2, 15), date(2024, 12, 31)]
        data = _market(days, {"A": [99.5, 99.5, 99.5, 100.0, 100.0]})
        table = _table(days, {"A": [100.0] * 5}, {"A": [0.0, 0.0, 0.0, 0.5, 0.0]})
        curve = [
            (date(2023, 12, 1), 2000.0, 0.0),
            (date(2024, 2, 1), 1900.0, 900.0),
            (date(2024, 2, 14), 1900.0, 900.0),
            (date(2024, 2, 15), 1900.0, 900.0),
            (date(2024, 12, 31), 1900.0, 900.0),
        ]
        fills = [
            _fill(date(2023, 12, 1), "A", "BUY", 20.0, 100.0),
            _fill(date(2024, 2, 1), "A", "SELL", 10.0, 90.0),
        ]
        out = apply_overlay(
            _result("reinvest-replacement", curve, fills), data, table, tax, BASE,
            initial_cash=2000.0, code_sha256=CODE,
        )

        factor_before, factor_after, dividend_ps = 0.995, 1.0, 0.5
        sold_shares = 10.0 * factor_before          # 9.95, real shares sold at the loss
        held_shares = 10.0 * factor_before          # 9.95, real shares still held into the ex-date
        growth = factor_after / factor_before
        child_shares = held_shares * (growth - 1.0)  # 0.05
        loss = 100.0
        loss_per_share = loss / sold_shares
        disallowed = min(child_shares, sold_shares) * loss_per_share   # child's own capacity limits it
        child_cash = held_shares * dividend_ps
        child_basis = child_cash + disallowed
        remaining_basis = 1000.0
        remaining_proceeds = held_shares * 100.0     # unadjusted close at "last" is 100
        child_proceeds = child_shares * 100.0
        expected_unrealized = (remaining_proceeds - remaining_basis) + (child_proceeds - child_basis)

        self.assertEqual(out["totals"]["wash_sale_count"], 1)
        self.assertAlmostEqual(out["totals"]["wash_sale_disallowed_total"], disallowed)
        self.assertAlmostEqual(out["totals"]["unrealized_gain_at_end"], expected_unrealized)
        self.assertTrue(out["identity_checks"]["share_identity_passed"])
        self.assertTrue(out["identity_checks"]["income_plus_gain_passed"])


class WashSaleCountTests(unittest.TestCase):
    """Two lots realise a loss on the same sale and are both fully replaced by
    one later purchase: that is one wash-sale event, not two, even though it
    produced two disallowed lot-level records.
    """

    def test_wash_sale_count_is_by_distinct_sale_not_by_lot_record(self) -> None:
        tax = _policy()
        days = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 10), date(2024, 1, 15), date(2024, 12, 31)]
        data = _market(days, {"A": [100.0] * 5})
        table = _table(days, {"A": [100.0] * 5})
        curve = [
            (date(2024, 1, 2), 1000.0, 0.0),
            (date(2024, 1, 3), 2000.0, 0.0),
            (date(2024, 1, 10), 1000.0, 1000.0),
            (date(2024, 1, 15), 1000.0, 1000.0),
            (date(2024, 12, 31), 1000.0, 1000.0),
        ]
        fills = [
            _fill(date(2024, 1, 2), "A", "BUY", 10.0, 100.0),
            _fill(date(2024, 1, 3), "A", "BUY", 10.0, 100.0),
            _fill(date(2024, 1, 10), "A", "SELL", 20.0, 50.0),
            _fill(date(2024, 1, 15), "A", "BUY", 20.0, 90.0),
        ]
        out = apply_overlay(
            _result("two-lots-one-sale", curve, fills), data, table, tax, BASE,
            initial_cash=1000.0, code_sha256=CODE,
        )
        self.assertEqual(out["totals"]["wash_sale_count"], 1)
        self.assertAlmostEqual(out["totals"]["wash_sale_disallowed_total"], 1000.0)


class LotMethodComparisonTests(unittest.TestCase):
    """Two lots of A bought at different prices, one partial sale: HIFO and
    FIFO select different lots and so realise different short-term gain or
    loss on the same fill.

    Buy 10 @ 100 (basis 1000), buy 10 @ 120 (basis 1200), sell 15 @ 110
    (proceeds 1650; 1650 / 15 = 110/share exactly, so the engine's pro-rata
    split gives every share the same 110). HIFO sells the 120/share lot first
    (fully: 1100 proceeds against 1200 basis, a 100 loss on 10 shares), then 5
    shares of the 100/share lot (550 proceeds against 500 basis, a 50 gain) --
    net a 50 short-term loss, no tax, the whole 50 carried forward. FIFO sells
    the 100/share lot first (fully: 1100 against 1000, a 100 gain), then 5
    shares of the 120/share lot (550 against 600, a 50 loss) -- net a 50
    short-term gain, taxed at the ordinary rate.
    """

    def setUp(self) -> None:
        self.tax = _policy()
        self.data = _market([date(2024, 1, 2), date(2024, 1, 3), date(2024, 12, 31)], {"A": [100.0, 100.0, 100.0]})
        self.table = _table([date(2024, 1, 2), date(2024, 1, 3), date(2024, 12, 31)], {"A": [100.0, 100.0, 100.0]})
        curve = [
            (date(2024, 1, 2), 1000.0, 0.0),
            (date(2024, 1, 3), 2200.0, 0.0),
            (date(2024, 12, 31), 1650.0, 1650.0),
        ]
        fills = [
            _fill(date(2024, 1, 2), "A", "BUY", 10.0, 100.0),
            _fill(date(2024, 1, 3), "A", "BUY", 10.0, 120.0),
            _fill(date(2024, 12, 31), "A", "SELL", 15.0, 110.0),
        ]
        self.result = _result("two-lots-hifo-fifo", curve, fills)

        proceeds_total = 15.0 * 110.0
        self.lot2_gain = proceeds_total * (10.0 / 15.0) - 1200.0             # -100.0
        self.lot1_remainder_gain = (
            proceeds_total * (5.0 / 15.0) - 1000.0 * (5.0 / 10.0)
        )                                                                    # +50.0
        self.lot1_gain = proceeds_total * (10.0 / 15.0) - 1000.0             # +100.0
        self.lot2_remainder_gain = (
            proceeds_total * (5.0 / 15.0) - 1200.0 * (5.0 / 10.0)
        )                                                                    # -50.0

    def test_hifo_sells_the_highest_basis_lot_first(self) -> None:
        year = apply_overlay(
            self.result, self.data, self.table, self.tax, HIFO, initial_cash=1000.0, code_sha256=CODE
        )["by_year"][0]
        net = self.lot2_gain + self.lot1_remainder_gain
        self.assertLess(net, 0.0)
        self.assertAlmostEqual(year["short_losses"], -self.lot2_gain)
        self.assertAlmostEqual(year["short_gains"], self.lot1_remainder_gain)
        self.assertAlmostEqual(year["tax"], 0.0)
        self.assertAlmostEqual(year["short_carry_out"], -net)

    def test_fifo_sells_the_oldest_lot_first(self) -> None:
        year = apply_overlay(
            self.result, self.data, self.table, self.tax, BASE, initial_cash=1000.0, code_sha256=CODE
        )["by_year"][0]
        net = self.lot1_gain + self.lot2_remainder_gain
        self.assertGreater(net, 0.0)
        self.assertAlmostEqual(year["short_gains"], self.lot1_gain)
        self.assertAlmostEqual(year["short_losses"], -self.lot2_remainder_gain)
        self.assertAlmostEqual(year["tax"], net * 0.35)
        self.assertAlmostEqual(year["short_carry_out"], 0.0)


class CollectiblesTests(unittest.TestCase):
    """Ten units of G, a collectibles-taxed symbol, bought at 100 and only
    liquidated at 130 after 729 days: a 300 long-term gain taxed at the 28%
    collectibles rate, not the long-term capital gains rate.
    """

    def test_liquidation_uses_the_collectibles_rate(self) -> None:
        tax = _policy_with_collectibles()
        days = [date(2024, 1, 2), date(2025, 12, 31)]
        data = _market(days, {"G": [100.0, 130.0]})
        table = _table(days, {"G": [100.0, 130.0]})
        curve = [(date(2024, 1, 2), 1000.0, 0.0), (date(2025, 12, 31), 1300.0, 0.0)]
        result = _result("collectibles", curve, [_fill(date(2024, 1, 2), "G", "BUY", 10.0, 100.0)])
        out = apply_overlay(result, data, table, tax, BASE, initial_cash=1000.0, code_sha256=CODE)
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], 300.0 * 0.28)


class SameDaySellAndDistributionTests(unittest.TestCase):
    """The ex-date and the sale fall in the same session: the sold lot was
    still held going into that session, so it receives the dividend, and the
    sale's gain is computed off proceeds net of the fill's trading cost.
    """

    def test_a_same_day_sale_still_receives_the_dividend(self) -> None:
        tax = _policy()
        days = [date(2024, 1, 2), date(2024, 6, 14)]
        data = _market(days, {"A": [100.0, 100.0]})
        table = _table(days, {"A": [100.0, 100.0]}, {"A": [0.0, 1.0]})
        curve = [(date(2024, 1, 2), 1000.0, 0.0), (date(2024, 6, 14), 1049.0, 1049.0)]
        fills = [
            _fill(date(2024, 1, 2), "A", "BUY", 10.0, 100.0),
            _fill(date(2024, 6, 14), "A", "SELL", 10.0, 105.0, cost=1.0),
        ]
        out = apply_overlay(
            _result("same-day", curve, fills), data, table, tax, BASE, initial_cash=1000.0, code_sha256=CODE
        )
        year = out["by_year"][0]
        # Income: the 10 shares still held into the ex-date, at 1.00/share.
        self.assertAlmostEqual(year["qualified_income"] + year["ordinary_income"], 10.0 * 1.0)
        # Gain: proceeds are the fill's notional (1050) less its cost (1.0), against basis 1000.
        self.assertAlmostEqual(year["short_gains"], (1050.0 - 1.0) - 1000.0)


class CarryoverAcrossYearsTests(unittest.TestCase):
    """A short-term loss in year one, with nothing to offset it, carries into
    year two and offsets part of a short-term gain there; only the excess
    above the carryover is taxed.
    """

    def test_the_carryover_is_used_and_only_the_excess_is_taxed(self) -> None:
        tax = _policy()
        days = [date(2024, 1, 2), date(2024, 6, 1), date(2025, 1, 2), date(2025, 6, 1)]
        data = _market(days, {"A": [100.0] * 4})
        table = _table(days, {"A": [100.0] * 4})
        curve = [
            (date(2024, 1, 2), 1000.0, 0.0),
            (date(2024, 6, 1), 900.0, 900.0),
            (date(2025, 1, 2), 1000.0, 0.0),
            (date(2025, 6, 1), 1150.0, 1150.0),
        ]
        fills = [
            _fill(date(2024, 1, 2), "A", "BUY", 10.0, 100.0),
            _fill(date(2024, 6, 1), "A", "SELL", 10.0, 90.0),
            _fill(date(2025, 1, 2), "A", "BUY", 10.0, 100.0),
            _fill(date(2025, 6, 1), "A", "SELL", 10.0, 115.0),
        ]
        out = apply_overlay(
            _result("carryover", curve, fills), data, table, tax, BASE, initial_cash=1000.0, code_sha256=CODE
        )
        first, second = out["by_year"]
        self.assertAlmostEqual(first["short_losses"], 100.0)
        self.assertAlmostEqual(first["tax"], 0.0)
        self.assertAlmostEqual(first["short_carry_out"], 100.0)
        self.assertAlmostEqual(second["short_carry_used"], 100.0)
        self.assertAlmostEqual(second["tax"], (150.0 - 100.0) * 0.35)


class ImpliedPriceCheckTests(unittest.TestCase):
    """A dividend paid while the adjusted series does not rise at all: the
    reinvestment price implied by the data cannot be computed, and the
    identity check must flag it rather than silently reporting a pass.
    """

    def test_a_dividend_without_growth_fails_the_implied_price_check(self) -> None:
        tax = _policy()
        days = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 6, 14), date(2024, 12, 31)]
        data = _market(days, {"A": [100.0] * 4})
        table = _table(days, {"A": [100.0] * 4}, {"A": [0.0, 0.0, 1.0, 0.0]})
        curve = [
            (date(2024, 1, 2), 1000.0, 0.0),
            (date(2024, 6, 14), 1000.0, 0.0),
            (date(2024, 12, 31), 1000.0, 0.0),
        ]
        result = _result("flat-adjusted", curve, [_fill(date(2024, 1, 2), "A", "BUY", 10.0, 100.0)])
        out = apply_overlay(result, data, table, tax, BASE, initial_cash=1000.0, code_sha256=CODE)
        checks = out["identity_checks"]
        self.assertEqual(checks["ex_dates_checked"], 1)
        self.assertEqual(checks["ex_dates_without_growth"], 1)
        self.assertFalse(checks["implied_price_check_passed"])


class NegativeAfterTaxWealthTests(unittest.TestCase):
    """When the after-tax path does not survive to a positive terminal value,
    CAGR and tax drag are undefined -- reported as None, not a −100% sentinel.
    """

    def test_after_tax_cagr_is_none_when_wealth_is_not_positive(self) -> None:
        tax = _policy()
        days = [date(2024, 1, 2), date(2024, 12, 31)]
        data = _market(days, {"A": [1.0, 1.0]}, cash_factor=5.0)
        table = _table(days, {"A": [1.0, 1.0]})
        curve = [(date(2024, 1, 2), 100.0, 100.0), (date(2024, 12, 31), 100.0, 100.0)]
        out = apply_overlay(
            _result("big-interest", curve, []), data, table, tax, BASE, initial_cash=100.0, code_sha256=CODE
        )
        self.assertLessEqual(out["wealth"]["after_tax_post_liquidation"], 0.0)
        self.assertIsNone(out["metrics"]["after_tax_cagr"])
        self.assertIsNone(out["metrics"]["tax_drag_bps"])


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

    def test_two_fills_for_the_same_symbol_on_the_same_day_are_refused(self) -> None:
        tax = _policy()
        days = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 12, 31)]
        data = _market(days, {"A": [1.0, 1.0, 1.0]})
        table = _table(days, {"A": [1.0, 1.0, 1.0]})
        curve = [(date(2024, 1, 2), 10.0, 0.0), (date(2024, 12, 31), 10.0, 0.0)]
        fills = [
            _fill(date(2024, 1, 2), "A", "BUY", 5.0, 1.0),
            _fill(date(2024, 1, 2), "A", "BUY", 5.0, 1.0),
        ]
        with self.assertRaisesRegex(ValueError, "twice in a session"):
            apply_overlay(_result("dup", curve, fills), data, table, tax, BASE,
                          initial_cash=10.0, code_sha256=CODE)

    def test_a_fill_outside_the_equity_curves_sessions_is_refused(self) -> None:
        tax = _policy()
        days = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 1, 3), date(2024, 12, 31)]
        data = _market(days, {"A": [1.0, 1.0, 1.0, 1.0]})
        table = _table(days, {"A": [1.0, 1.0, 1.0, 1.0]})
        curve = [(date(2024, 1, 2), 10.0, 0.0), (date(2024, 12, 31), 10.0, 0.0)]
        fills = [_fill(date(2024, 1, 3), "A", "BUY", 10.0, 1.0)]
        with self.assertRaisesRegex(ValueError, "not a session"):
            apply_overlay(_result("stray", curve, fills), data, table, tax, BASE,
                          initial_cash=10.0, code_sha256=CODE)

    def test_an_initial_equity_mismatch_is_refused(self) -> None:
        tax = _policy()
        days = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 12, 31)]
        data = _market(days, {"A": [1.0, 1.0, 1.0]})
        table = _table(days, {"A": [1.0, 1.0, 1.0]})
        result = BacktestResult(
            name="mismatch",
            initial_equity=20.0,
            equity_curve=(
                EquityPoint(date(2024, 1, 2), 10.0, 0.0, 10.0),
                EquityPoint(date(2024, 12, 31), 10.0, 0.0, 10.0),
            ),
            fills=(),
            decisions=(),
        )
        with self.assertRaisesRegex(ValueError, "initial_equity"):
            apply_overlay(result, data, table, tax, BASE, initial_cash=10.0, code_sha256=CODE)


if __name__ == "__main__":
    unittest.main()
