"""Constructed tax-return sensitivities, never historical strategy evidence."""

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import TaxConfig
from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, Fill, PriceBar
from boring_alpha.tax.loss_sensitivity import (
    LossDeductionPolicy, evaluate_deduction_year, load_loss_deduction_policy,
)
from boring_alpha.tax.overlay import apply_overlay, run_scenarios
from boring_alpha.tax.policy import SCENARIOS, Scenario
from boring_alpha.tax.yearend import Amounts


def _tax() -> TaxConfig:
    return TaxConfig(Path("fictional.csv"), .35, .20, .28, .5, {"A": 1.0}, {"A": "standard"})


def _policy(**overrides) -> LossDeductionPolicy:
    return LossDeductionPolicy(**{
        "annual_capacity": 3000.0, "outside_ordinary_income": 100000.0,
        "savings_destination": "outside_account", **overrides,
    })


def _fixture(*, size: float = 1.0, hold_final: bool = False, terminal_price: float = 80.):
    # Lose $5,000, stay out >30 days, then gain $3,000 the following year.
    days = [date(2023, 1, 2), date(2023, 11, 20), date(2023, 12, 29),
            date(2024, 1, 2), date(2024, 6, 28), date(2024, 12, 31)]
    prices = [100., 50., 50., 50., terminal_price, terminal_price]
    data = MarketData([PriceBar(day, "A", price, price) for day, price in zip(days, prices)],
                      {day: 1.0 for day in days}, source="synthetic")
    table = DistributionTable([(day, "A", price, 0.) for day, price in zip(days, prices)],
                              splits={"A": []}, sha256="d" * 64, source="synthetic")
    fills = []
    for index, side in [(0, "BUY"), (1, "SELL"), (3, "BUY")] + ([] if hold_final else [(4, "SELL")]):
        price = prices[index]
        amount = 100 * size * price
        fills.append(Fill(days[index], "A", side, 100 * size, price, amount, 0., amount, price))
    terminal = 100. * terminal_price
    equity = [10000., 5000., 5000., 5000., terminal, terminal]
    cash = [0., 5000., 5000., 0., 0. if hold_final else terminal, 0. if hold_final else terminal]
    curve = tuple(EquityPoint(day, value * size, liquid * size, (value - liquid) * size)
                  for day, value, liquid in zip(days, equity, cash))
    result = BacktestResult(name="fictional-loss-then-gain", initial_equity=10000. * size,
                            equity_curve=curve, fills=tuple(fills), decisions=())
    return result, data, table


def _run(policy=None, **fixture_options):
    result, data, table = _fixture(**fixture_options)
    return apply_overlay(result, data, table, _tax(), Scenario("fifo", "deferral", "base"),
                         initial_cash=result.initial_equity, code_sha256="c" * 64,
                         loss_sensitivity=policy)


class PolicyTests(unittest.TestCase):
    def test_required_assumptions_cannot_be_omitted_or_misspelled(self):
        valid = _policy().as_dict(_tax())
        for field in ("annual_capacity", "outside_ordinary_income", "savings_destination"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                LossDeductionPolicy.from_dict({key: value for key, value in valid.items() if key != field})
        with self.assertRaises(ValueError):
            LossDeductionPolicy.from_dict({**valid, "unknown": 3})

    def test_boolean_nonfinite_negative_and_non_numeric_amounts_are_refused(self):
        for field in ("annual_capacity", "outside_ordinary_income", "ordinary_rate"):
            for value in (False, True, float("nan"), float("inf"), -1., "3000", 10 ** 400):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    _policy(**{field: value})

    def test_upper_limits_and_destination_are_explicit(self):
        for changes in ({"annual_capacity": 3000.01}, {"ordinary_rate": 1.01},
                        {"savings_destination": False}, {"savings_destination": "reinvest"},
                        {"savings_destination": []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                _policy(**changes)
        self.assertEqual(_policy(annual_capacity=1500).annual_capacity, 1500.)

    def test_json_and_toml_load_the_same_explicit_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "sensitivity.json"
            toml_path = root / "sensitivity.toml"
            json_path.write_text(json.dumps(_policy().as_dict(_tax())))
            toml_path.write_text('[loss_sensitivity]\nannual_capacity = 3000\noutside_ordinary_income = 100000\nsavings_destination = "outside_account"\nordinary_rate = 0.35\n')
            self.assertEqual(load_loss_deduction_policy(json_path), load_loss_deduction_policy(toml_path))

    def test_loader_refuses_duplicate_json_fields_and_extra_toml_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "sensitivity.json"
            json_path.write_text('{"annual_capacity": 0, "annual_capacity": 3000}')
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_loss_deduction_policy(json_path)
            toml_path = root / "sensitivity.toml"
            toml_path.write_text('[loss_sensitivity]\nannual_capacity=3000\n[other]\nvalue=1')
            with self.assertRaisesRegex(ValueError, "only"):
                load_loss_deduction_policy(toml_path)

    def test_identity_pins_every_resolved_assumption(self):
        policy = _policy()
        original = policy.sha256(_tax())
        self.assertEqual(original, _policy(ordinary_rate=.35).sha256(_tax()))
        for changes in ({"annual_capacity": 1500.}, {"outside_ordinary_income": 2000.},
                        {"ordinary_rate": .24}, {"savings_destination": "contribute_to_account"}):
            with self.subTest(changes=changes):
                self.assertNotEqual(original, _policy(**changes).sha256(_tax()))


class DeductionArithmeticTests(unittest.TestCase):
    def test_fractional_loss_pools_never_carry_or_deduct_negative_roundoff(self):
        year = evaluate_deduction_year(Amounts(short_losses=1.111, long_losses=2.222),
                                       0., 0., _tax(), _policy())
        self.assertEqual(year.taxes.short_carry_out, 0.)
        self.assertEqual(year.taxes.long_carry_out, 0.)
        self.assertLessEqual(year.long_deduction, 2.222)
        self.assertEqual(year.ordinary_tax_savings, year.deduction * .35)

    def test_net_capital_gains_first_then_consume_short_losses_before_long(self):
        year = evaluate_deduction_year(Amounts(short_losses=2000., short_gains=1000., long_losses=5000.),
                                       0., 0., _tax(), _policy())
        self.assertEqual(year.short_deduction, 1000.)
        self.assertEqual(year.long_deduction, 2000.)
        self.assertEqual(year.taxes.short_carry_out, 0.)
        self.assertEqual(year.taxes.long_carry_out, 3000.)
        self.assertEqual(year.ordinary_tax_savings, 1050.)
        self.assertEqual(year.taxes.tax, 0.)  # household credit is not negative account tax

    def test_declared_outside_income_and_capacity_both_bound_the_deduction(self):
        for policy, expected in ((_policy(outside_ordinary_income=700.), 700.),
                                 (_policy(annual_capacity=1500.), 1500.),
                                 (_policy(outside_ordinary_income=0.), 0.),
                                 (_policy(annual_capacity=0.), 0.)):
            with self.subTest(policy=policy):
                year = evaluate_deduction_year(Amounts(short_losses=10000.), 0., 0., _tax(), policy)
                self.assertEqual(year.deduction, expected)
                self.assertEqual(year.taxes.short_carry_out, 10000. - expected)

    def test_all_gain_netting_finishes_before_any_ordinary_deduction(self):
        year = evaluate_deduction_year(Amounts(short_losses=5000., long_gains=6000.),
                                       0., 0., _tax(), _policy())
        self.assertEqual(year.deduction, 0.)
        self.assertEqual(year.ordinary_tax_savings, 0.)
        self.assertEqual(year.taxes.tax, 200.)

    def test_explicit_marginal_rate_affects_savings_not_account_tax(self):
        year = evaluate_deduction_year(Amounts(short_losses=5000., ordinary_income=100.),
                                       0., 0., _tax(), _policy(ordinary_rate=.24))
        self.assertEqual(year.ordinary_tax_savings, 720.)
        self.assertEqual(year.taxes.tax, 35.)


class OverlaySensitivityTests(unittest.TestCase):
    def test_default_output_stays_baseline_and_the_fixed_grid_stays_eight(self):
        baseline = _run()
        self.assertNotIn("loss_sensitivity", baseline)
        self.assertTrue(any("capital-loss deduction" in text for text in baseline["totals"]["known_omissions"]))
        result, data, table = _fixture()
        scenarios = run_scenarios(result, data, table, _tax(), initial_cash=result.initial_equity,
                                  code_sha256="c" * 64)
        self.assertEqual(list(scenarios), [scenario.key for scenario in SCENARIOS])
        self.assertEqual(len(scenarios), 8)
        self.assertTrue(all("loss_sensitivity" not in output for output in scenarios.values()))

    def test_zero_capacity_matches_baseline_economics_exactly(self):
        baseline, sensitivity = _run(), _run(_policy(annual_capacity=0.))
        for key, value in baseline["wealth"].items():
            self.assertEqual(sensitivity["wealth"][key], value)
        self.assertEqual(sensitivity["metrics"], baseline["metrics"])
        for baseline_year, sensitivity_year in zip(baseline["by_year"], sensitivity["by_year"]):
            for key, value in baseline_year.items():
                self.assertEqual(sensitivity_year[key], value)

    def test_year_one_credit_consumes_carry_and_increases_future_tax(self):
        baseline, sensitivity = _run(), _run(_policy())
        first, second = sensitivity["by_year"]
        self.assertEqual(first["capital_loss_deduction"], 3000.)
        self.assertEqual(first["ordinary_tax_savings"], 1050.)
        self.assertEqual(first["short_carry_out"], 2000.)
        self.assertEqual(second["tax"], 350.)
        self.assertEqual(baseline["by_year"][1]["tax"], 0.)
        self.assertEqual(sensitivity["wealth"]["after_tax_post_liquidation"], 7650.)
        self.assertEqual(sensitivity["wealth"]["household_terminal_wealth"], 8700.)
        self.assertEqual(sensitivity["wealth"]["contributed_tax_savings_post_liquidation"], 0.)
        self.assertEqual(sensitivity["wealth"]["outside_tax_savings_post_liquidation"], 1050.)
        self.assertEqual(first["scale"], second["scale"])  # outside money never grows the account

    def test_terminal_liquidation_replaces_final_deduction_from_same_carry_in(self):
        sensitivity = _run(_policy(), hold_final=True)
        final = sensitivity["by_year"][-1]
        self.assertEqual(final["capital_loss_deduction"], 2000.)
        self.assertEqual(sensitivity["wealth"]["outside_tax_savings_pre_liquidation"], 1750.)
        terminal = sensitivity["loss_sensitivity"]["terminal_liquidation"]
        self.assertEqual(terminal["capital_loss_deduction"], 0.)
        self.assertEqual(terminal["ordinary_tax_savings_adjustment"], -700.)
        self.assertEqual(sensitivity["wealth"]["outside_tax_savings_post_liquidation"], 1050.)
        self.assertEqual(sensitivity["totals"]["tax_liquidation"], 350.)
        self.assertEqual(sensitivity["wealth"]["household_terminal_wealth"], 8700.)

    def test_contributions_change_only_following_year_scale_and_are_not_cagr(self):
        sensitivity = _run(_policy(savings_destination="contribute_to_account"))
        first, second = sensitivity["by_year"]
        self.assertEqual(first["scale"], 1.)
        self.assertEqual(first["tax_savings_contributed"], 1050.)
        self.assertAlmostEqual(second["scale"], 1.21)
        self.assertAlmostEqual(second["short_gains"], 3630.)
        self.assertAlmostEqual(second["tax"], 570.5)
        self.assertAlmostEqual(sensitivity["wealth"]["after_tax_post_liquidation"], 9109.5)
        self.assertEqual(sensitivity["wealth"]["contributed_tax_savings_post_liquidation"], 1050.)
        self.assertEqual(sensitivity["wealth"]["outside_tax_savings_post_liquidation"], 0.)
        self.assertIsNone(sensitivity["metrics"]["after_tax_cagr"])
        self.assertIsNone(sensitivity["metrics"]["tax_drag_bps"])

    def test_terminal_contribution_is_replaced_not_counted_twice(self):
        sensitivity = _run(_policy(savings_destination="contribute_to_account"), hold_final=True)
        self.assertEqual(sensitivity["wealth"]["contributed_tax_savings_pre_liquidation"], 1750.)
        self.assertEqual(sensitivity["wealth"]["contributed_tax_savings_post_liquidation"], 1050.)
        self.assertAlmostEqual(sensitivity["totals"]["tax_liquidation"], 570.5)
        self.assertAlmostEqual(sensitivity["wealth"]["household_terminal_wealth"], 9109.5)

    def test_contributed_savings_do_not_create_a_mixed_account_size_tax_rate(self):
        baseline = _run(terminal_price=150.)
        sensitivity = _run(_policy(savings_destination="contribute_to_account"), terminal_price=150.)
        self.assertGreater(baseline["wealth"]["pre_tax_terminal"], 10000.)
        self.assertGreater(baseline["metrics"]["effective_tax_rate"], 0.)
        self.assertGreater(sensitivity["wealth"]["contributed_tax_savings_post_liquidation"], 0.)
        self.assertGreater(sensitivity["totals"]["taxes_paid"], 0.)
        self.assertIsNone(sensitivity["metrics"]["effective_tax_rate"])
        self.assertIsNone(sensitivity["metrics"]["after_tax_cagr"])
        self.assertIsNone(sensitivity["metrics"]["tax_drag_bps"])

    def test_absent_sensitivity_preserves_existing_negative_cash_income_behavior(self):
        # This pins the baseline's existing fixed-rate arithmetic, not a claim
        # about the deductibility of real negative-yield cash instruments.
        days = [date(2024, 1, 2), date(2024, 12, 31)]
        data = MarketData([PriceBar(day, "A", 1., 1.) for day in days],
                          {day: .9 for day in days}, source="synthetic")
        table = DistributionTable([(day, "A", 1., 0.) for day in days],
                                  splits={"A": []}, sha256="d" * 64, source="synthetic")
        result = BacktestResult(name="negative-cash-income", initial_equity=100., decisions=(), fills=(),
                               equity_curve=(EquityPoint(days[0], 100., 100., 0.),
                                             EquityPoint(days[1], 90., 90., 0.)))
        output = apply_overlay(result, data, table, _tax(), SCENARIOS[0],
                               initial_cash=100., code_sha256="c" * 64)
        self.assertAlmostEqual(output["totals"]["taxes_paid"], -3.5)
        self.assertAlmostEqual(output["wealth"]["after_tax_post_liquidation"], 93.5)
        disabled = apply_overlay(result, data, table, _tax(), SCENARIOS[0],
                                 initial_cash=100., code_sha256="c" * 64,
                                 loss_sensitivity=_policy(annual_capacity=0.))
        for key, value in output['wealth'].items():
            self.assertEqual(disabled['wealth'][key], value)
        self.assertEqual(disabled['metrics'], output['metrics'])

    def test_liquidating_an_unrealized_loss_can_add_a_terminal_deduction(self):
        days = [date(2024, 1, 2), date(2024, 12, 31)]
        prices = [100., 50.]
        data = MarketData([PriceBar(day, "A", price, price) for day, price in zip(days, prices)],
                          {day: 1. for day in days}, source="synthetic")
        table = DistributionTable([(day, "A", price, 0.) for day, price in zip(days, prices)],
                                  splits={"A": []}, sha256="d" * 64, source="synthetic")
        result = BacktestResult(name="unrealized-loss", initial_equity=10000., decisions=(),
                               fills=(Fill(days[0], "A", "BUY", 100., 100., 10000., 0., 10000., 100.),),
                               equity_curve=(EquityPoint(days[0], 10000., 0., 10000.),
                                             EquityPoint(days[1], 5000., 0., 5000.)))
        output = apply_overlay(result, data, table, _tax(), SCENARIOS[0],
                               initial_cash=10000., code_sha256="c" * 64, loss_sensitivity=_policy())
        self.assertEqual(output["by_year"][0]["capital_loss_deduction"], 0.)
        self.assertEqual(output["loss_sensitivity"]["terminal_liquidation"]["capital_loss_deduction"], 3000.)
        self.assertEqual(output["loss_sensitivity"]["terminal_liquidation"]["short_carry_out"], 2000.)
        self.assertEqual(output["wealth"]["outside_tax_savings_pre_liquidation"], 0.)
        self.assertEqual(output["wealth"]["outside_tax_savings_post_liquidation"], 1050.)
        self.assertEqual(output["wealth"]["household_terminal_wealth"], 6050.)

    def test_fixed_dollar_capacity_makes_account_size_material(self):
        small, large = _run(_policy()), _run(_policy(), size=100.)
        self.assertEqual(small["loss_sensitivity"]["initial_account_size"], 10000.)
        self.assertEqual(large["loss_sensitivity"]["initial_account_size"], 1000000.)
        self.assertEqual(small["wealth"]["outside_tax_savings_post_liquidation"], 1050.)
        self.assertEqual(large["wealth"]["outside_tax_savings_post_liquidation"], 2100.)
        self.assertNotEqual(large["wealth"]["household_terminal_wealth"],
                            small["wealth"]["household_terminal_wealth"] * 100.)

    def test_sensitivity_requires_an_explicit_policy_not_boolean_opt_in(self):
        with self.assertRaisesRegex(ValueError, "explicit LossDeductionPolicy"):
            _run(False)

    def test_holding_period_leap_anniversary_routes_a_realized_gain_to_short(self):
        days = [date(2023, 3, 1), date(2024, 3, 1)]
        prices = [100., 110.]
        data = MarketData([PriceBar(day, "A", price, price) for day, price in zip(days, prices)],
                          {day: 1. for day in days}, source="synthetic")
        table = DistributionTable([(day, "A", price, 0.) for day, price in zip(days, prices)],
                                  splits={"A": []}, sha256="d" * 64, source="synthetic")
        fills = tuple(Fill(day, "A", side, 10., price, 10. * price, 0., 10. * price, price)
                      for day, side, price in zip(days, ("BUY", "SELL"), prices))
        result = BacktestResult(name="anniversary", initial_equity=1000., decisions=(), fills=fills,
                               equity_curve=(EquityPoint(days[0], 1000., 0., 1000.),
                                             EquityPoint(days[1], 1100., 1100., 0.)))
        output = apply_overlay(result, data, table, _tax(), SCENARIOS[0],
                               initial_cash=1000., code_sha256="c" * 64)
        self.assertEqual(output["by_year"][-1]["short_gains"], 100.)
        self.assertEqual(output["by_year"][-1]["long_gains"], 0.)
        self.assertEqual(output["totals"]["taxes_paid"], 35.)
