# Portfolio / Execution Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `Portfolio.rebalance` into a portfolio layer that emits orders and an execution layer that fills them, without changing a single number the backtest produces.

**Architecture:** One rebalance becomes three named steps — `plan_rebalance` returns `Order` intents from targets and holdings, a pure `execute` applies the cost model and the sell-then-scaled-buys rule to return `Fill`s, and `Portfolio.apply` mutates cash and positions. Execution takes a plain `dict[str, float]` of prices rather than `MarketData`, so a future paper mode can feed it broker quotes. `Order` and `Fill` are flat records matched by `(date, symbol, side)`.

**Tech Stack:** Python 3.11+, standard library only, `unittest`, frozen slotted dataclasses.

**Spec:** `docs/superpowers/specs/2026-09-04-portfolio-execution-split-design.md`

## Global Constraints

- Python 3.11 or newer. Standard library only — no third-party dependencies, ever.
- Tests are `unittest`, run with `.venv/bin/python -m unittest discover -s tests`.
- All 183 existing tests must pass at every task boundary.
- Domain records are `@dataclass(frozen=True, slots=True)`.
- **Behaviour-neutral.** Equity curves, `metrics.json`, `decisions.json`, `criteria.json` and `summary.md` must be byte-identical to the captured baseline. Run identifiers WILL change, because the code hash is part of run identity by design. The only permitted artifact difference is the two new trades-CSV columns added in Task 4.
- Baseline for comparison is at `/private/tmp/claude-501/-Users-haoyu-development-boring-alpha/2daab586-da89-4f60-b5c7-7def20db32b1/scratchpad/baseline/current/` (`backtest/` and `sweep/` subdirectories, `provenance.jsonl` already removed).
- Never run `boring-alpha` against a checked-in config except where a step says to; it writes into `experiments/`.
- Ordering matters for byte-identical output: sells execute before buys, and within each side symbols are processed in sorted order.

---

### Task 1: Order record and portfolio planning

**Files:**
- Modify: `src/boring_alpha/domain.py` (add `Order` after `PriceBar`)
- Modify: `src/boring_alpha/portfolio/account.py` (add `plan_rebalance`; leave `rebalance` untouched)
- Test: `tests/test_planning.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `boring_alpha.domain.Order(date, symbol, side, intended_notional, reference_price)` and `Portfolio.plan_rebalance(prices: dict[str, float], target_weights: dict[str, float], reference_prices: dict[str, float], day: date) -> list[Order]`. Task 2 consumes `Order`; Task 3 calls `plan_rebalance`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_planning.py`:

```python
"""Planning turns targets into order intents without touching the book."""

from datetime import date
import unittest

from boring_alpha.domain import Order
from boring_alpha.portfolio.account import Portfolio

DAY = date(2025, 2, 3)
PRICES = {"A": 10.0, "B": 20.0}
REFERENCES = {"A": 9.0, "B": 21.0}


class PlanRebalanceTests(unittest.TestCase):
    def test_a_flat_book_plans_one_buy_per_target(self) -> None:
        portfolio = Portfolio(1_000.0, ("A", "B"))
        orders = portfolio.plan_rebalance(PRICES, {"A": 0.5, "B": 0.5}, REFERENCES, DAY)
        self.assertEqual(
            orders,
            [
                Order(DAY, "A", "BUY", 500.0, 9.0),
                Order(DAY, "B", "BUY", 500.0, 21.0),
            ],
        )

    def test_planning_does_not_mutate_cash_or_positions(self) -> None:
        portfolio = Portfolio(1_000.0, ("A", "B"))
        portfolio.plan_rebalance(PRICES, {"A": 1.0, "B": 0.0}, REFERENCES, DAY)
        self.assertEqual(portfolio.cash, 1_000.0)
        self.assertEqual(portfolio.positions, {"A": 0.0, "B": 0.0})

    def test_an_overweight_holding_plans_a_sell(self) -> None:
        portfolio = Portfolio(0.0, ("A", "B"))
        portfolio.positions["A"] = 100.0
        orders = portfolio.plan_rebalance(PRICES, {"A": 0.0, "B": 1.0}, REFERENCES, DAY)
        self.assertEqual(orders[0], Order(DAY, "A", "SELL", 1_000.0, 9.0))
        self.assertEqual(orders[1], Order(DAY, "B", "BUY", 1_000.0, 21.0))

    def test_a_holding_already_at_target_plans_nothing(self) -> None:
        portfolio = Portfolio(0.0, ("A", "B"))
        portfolio.positions["A"] = 100.0
        orders = portfolio.plan_rebalance(PRICES, {"A": 1.0, "B": 0.0}, REFERENCES, DAY)
        self.assertEqual(orders, [])

    def test_orders_are_planned_in_sorted_symbol_order(self) -> None:
        portfolio = Portfolio(1_000.0, ("B", "A"))
        orders = portfolio.plan_rebalance(PRICES, {"A": 0.5, "B": 0.5}, REFERENCES, DAY)
        self.assertEqual([order.symbol for order in orders], ["A", "B"])

    def test_the_reference_price_is_recorded_not_the_execution_price(self) -> None:
        portfolio = Portfolio(1_000.0, ("A", "B"))
        orders = portfolio.plan_rebalance(PRICES, {"A": 1.0, "B": 0.0}, REFERENCES, DAY)
        self.assertEqual(orders[0].reference_price, 9.0)
        self.assertNotEqual(orders[0].reference_price, PRICES["A"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_planning -v`
Expected: FAIL — `ImportError: cannot import name 'Order' from 'boring_alpha.domain'`

- [ ] **Step 3: Add the Order record**

In `src/boring_alpha/domain.py`, insert after the `PriceBar` class:

```python
@dataclass(frozen=True, slots=True)
class Order:
    """An intent to trade, priced at the moment the decision was made.

    `reference_price` is the decision-time price — for BA-001 the month-end
    close — not the price the order will fill at. The gap between the two is
    slippage, and recording it is what lets a paper fill be compared with a
    modelled one.
    """

    date: date
    symbol: str
    side: str
    intended_notional: float
    reference_price: float
```

- [ ] **Step 4: Add plan_rebalance**

In `src/boring_alpha/portfolio/account.py`, change the import line to:

```python
from boring_alpha.domain import Order, Trade
```

Then add this method to `Portfolio`, immediately before `rebalance`:

```python
    def plan_rebalance(
        self,
        prices: dict[str, float],
        target_weights: dict[str, float],
        reference_prices: dict[str, float],
        day: date,
    ) -> list[Order]:
        """Targets and holdings in, order intents out. Pure: nothing is mutated.

        Sizing uses equity at execution prices, which is what the engine fills
        at. No cost model appears here; costs belong to execution.
        """

        equity = self.cash + sum(
            quantity * prices[symbol] for symbol, quantity in self.positions.items()
        )
        orders: list[Order] = []
        for symbol in sorted(self.positions):
            current = self.positions[symbol] * prices[symbol]
            difference = equity * target_weights.get(symbol, 0.0) - current
            if abs(difference) <= 1e-10:
                continue
            orders.append(
                Order(
                    day,
                    symbol,
                    "BUY" if difference > 0.0 else "SELL",
                    abs(difference),
                    reference_prices[symbol],
                )
            )
        return orders
```

- [ ] **Step 5: Run the new test and the whole suite**

Run: `.venv/bin/python -m unittest tests.test_planning -v`
Expected: PASS, 6 tests.

Run: `.venv/bin/python -m unittest discover -s tests`
Expected: PASS, 189 tests (183 existing + 6 new).

- [ ] **Step 6: Commit**

```bash
git add src/boring_alpha/domain.py src/boring_alpha/portfolio/account.py tests/test_planning.py
git commit -m "Add Order record and pure rebalance planning

The portfolio layer can now express what it wants to trade without deciding
how it fills. Planning is pure and records the decision-time reference price,
so slippage against the eventual fill becomes measurable.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Execution layer and Fill record

**Files:**
- Modify: `src/boring_alpha/domain.py` (add `Fill` after `Order`; leave `Trade` in place for now)
- Create: `src/boring_alpha/execution/__init__.py`
- Create: `src/boring_alpha/execution/simulator.py`
- Modify: `src/boring_alpha/portfolio/account.py` (add `apply`)
- Test: `tests/test_execution.py` (create)

**Interfaces:**
- Consumes: `boring_alpha.domain.Order` from Task 1.
- Produces: `boring_alpha.domain.Fill(date, symbol, side, quantity, price, notional, cost, intended_notional, reference_price)`; `boring_alpha.execution.CostModel(cost_bps)` with `.rate` and `.cost(notional)`; `boring_alpha.execution.execute(orders: list[Order], prices: dict[str, float], cash: float, cost_model: CostModel) -> list[Fill]`; `Portfolio.apply(fills: list[Fill]) -> None`. Task 3 wires all four into the engine.

**Note on transitional state:** this task leaves `Trade` and `Portfolio.rebalance` in place and unused by the new code. Task 3 deletes both. Reviewing this task, expect both old and new paths to exist.

- [ ] **Step 1: Write the failing test**

Create `tests/test_execution.py`:

```python
"""Execution turns intents into fills: costs, cash limits, and ordering."""

from datetime import date
import unittest

from boring_alpha.domain import Order
from boring_alpha.execution import CostModel, execute
from boring_alpha.portfolio.account import AccountingError, Portfolio

DAY = date(2025, 2, 3)
PRICES = {"A": 10.0, "B": 20.0}
FREE = CostModel(0.0)


class ExecutionTests(unittest.TestCase):
    def test_a_buy_fills_at_the_execution_price(self) -> None:
        orders = [Order(DAY, "A", "BUY", 500.0, 9.0)]
        fills = execute(orders, PRICES, 1_000.0, FREE)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].price, 10.0)
        self.assertAlmostEqual(fills[0].quantity, 50.0)
        self.assertAlmostEqual(fills[0].notional, 500.0)
        self.assertAlmostEqual(fills[0].intended_notional, 500.0)
        self.assertEqual(fills[0].reference_price, 9.0)

    def test_costs_are_charged_at_the_configured_rate(self) -> None:
        fills = execute([Order(DAY, "A", "BUY", 100.0, 9.0)], PRICES, 1_000.0, CostModel(10.0))
        self.assertAlmostEqual(fills[0].cost, 0.10)

    def test_sells_execute_before_buys(self) -> None:
        orders = [
            Order(DAY, "B", "BUY", 100.0, 21.0),
            Order(DAY, "A", "SELL", 100.0, 9.0),
        ]
        fills = execute(orders, PRICES, 0.0, FREE)
        self.assertEqual([(f.symbol, f.side) for f in fills], [("A", "SELL"), ("B", "BUY")])

    def test_each_side_fills_in_sorted_symbol_order(self) -> None:
        orders = [
            Order(DAY, "B", "BUY", 100.0, 21.0),
            Order(DAY, "A", "BUY", 100.0, 9.0),
        ]
        fills = execute(orders, PRICES, 1_000.0, FREE)
        self.assertEqual([fill.symbol for fill in fills], ["A", "B"])

    def test_sale_proceeds_fund_a_purchase_in_the_same_batch(self) -> None:
        orders = [
            Order(DAY, "A", "SELL", 1_000.0, 9.0),
            Order(DAY, "B", "BUY", 1_000.0, 21.0),
        ]
        fills = execute(orders, PRICES, 0.0, FREE)
        self.assertAlmostEqual(fills[1].notional, 1_000.0)

    def test_buys_scale_pro_rata_when_cash_is_short(self) -> None:
        orders = [
            Order(DAY, "A", "BUY", 500.0, 9.0),
            Order(DAY, "B", "BUY", 500.0, 21.0),
        ]
        fills = execute(orders, PRICES, 1_000.0, CostModel(100.0))
        expected = 500.0 * (1_000.0 / 1_010.0)
        for fill in fills:
            self.assertAlmostEqual(fill.notional, expected)
            self.assertAlmostEqual(fill.intended_notional, 500.0)

    def test_a_partially_filled_order_reports_both_notionals(self) -> None:
        fills = execute([Order(DAY, "A", "BUY", 1_000.0, 9.0)], PRICES, 500.0, FREE)
        self.assertAlmostEqual(fills[0].notional, 500.0)
        self.assertAlmostEqual(fills[0].intended_notional, 1_000.0)
        self.assertLess(fills[0].notional, fills[0].intended_notional)

    def test_no_orders_means_no_fills(self) -> None:
        self.assertEqual(execute([], PRICES, 1_000.0, FREE), [])


class ApplyTests(unittest.TestCase):
    def test_applying_fills_moves_cash_and_positions(self) -> None:
        portfolio = Portfolio(1_000.0, ("A", "B"))
        fills = execute([Order(DAY, "A", "BUY", 500.0, 9.0)], PRICES, 1_000.0, FREE)
        portfolio.apply(fills)
        self.assertAlmostEqual(portfolio.cash, 500.0)
        self.assertAlmostEqual(portfolio.positions["A"], 50.0)

    def test_a_sale_returns_proceeds_net_of_cost(self) -> None:
        portfolio = Portfolio(0.0, ("A", "B"))
        portfolio.positions["A"] = 100.0
        fills = execute([Order(DAY, "A", "SELL", 1_000.0, 9.0)], PRICES, 0.0, CostModel(100.0))
        portfolio.apply(fills)
        self.assertAlmostEqual(portfolio.cash, 1_000.0 - 10.0)
        self.assertAlmostEqual(portfolio.positions["A"], 0.0)

    def test_overspending_raises_an_accounting_error(self) -> None:
        portfolio = Portfolio(100.0, ("A",))
        fills = execute([Order(DAY, "A", "BUY", 1_000.0, 9.0)], PRICES, 1_000.0, FREE)
        with self.assertRaises(AccountingError):
            portfolio.apply(fills)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_execution -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'boring_alpha.execution'`

- [ ] **Step 3: Add the Fill record**

In `src/boring_alpha/domain.py`, insert after the `Order` class:

```python
@dataclass(frozen=True, slots=True)
class Fill:
    """What actually happened to an order.

    Flat, and matched to its order by (date, symbol, side): a broker returns
    fills that know nothing about our objects, so the link is a key rather than
    a reference. `intended_notional` and `reference_price` are carried here too
    because they are what the trade ledger needs.
    """

    date: date
    symbol: str
    side: str
    quantity: float
    price: float
    notional: float
    cost: float
    intended_notional: float
    reference_price: float
```

- [ ] **Step 4: Create the execution package**

Create `src/boring_alpha/execution/__init__.py`:

```python
from boring_alpha.execution.simulator import CostModel, execute

__all__ = ["CostModel", "execute"]
```

Create `src/boring_alpha/execution/simulator.py`:

```python
"""Turning order intents into fills.

This is the layer a paper or live mode replaces: it is the only place that
knows what a trade costs and what price it gets. It takes a plain mapping of
prices rather than a market dataset, so the same function can be fed broker
quotes.
"""

from __future__ import annotations

from dataclasses import dataclass

from boring_alpha.domain import Fill, Order


@dataclass(frozen=True, slots=True)
class CostModel:
    """Proportional cost per traded notional, per side."""

    cost_bps: float

    @property
    def rate(self) -> float:
        return self.cost_bps / 10_000.0

    def cost(self, notional: float) -> float:
        return notional * self.rate


def _fill(order: Order, price: float, notional: float, cost_model: CostModel) -> Fill:
    return Fill(
        date=order.date,
        symbol=order.symbol,
        side=order.side,
        quantity=notional / price,
        price=price,
        notional=notional,
        cost=cost_model.cost(notional),
        intended_notional=order.intended_notional,
        reference_price=order.reference_price,
    )


def execute(
    orders: list[Order],
    prices: dict[str, float],
    cash: float,
    cost_model: CostModel,
) -> list[Fill]:
    """Fill orders against a cash-only account.

    Sells settle first, then buys are scaled pro rata to the cash actually
    available afterwards, so the account can never go short of cash. A buy that
    scales down is a partial fill, and says so: its notional is below the
    intended notional it carries.
    """

    sells = sorted(
        (order for order in orders if order.side == "SELL"), key=lambda order: order.symbol
    )
    buys = sorted(
        (order for order in orders if order.side == "BUY"), key=lambda order: order.symbol
    )

    fills: list[Fill] = []
    available = cash
    for order in sells:
        fill = _fill(order, prices[order.symbol], order.intended_notional, cost_model)
        available += fill.notional - fill.cost
        fills.append(fill)

    required = sum(
        order.intended_notional * (1.0 + cost_model.rate) for order in buys
    )
    scale = min(1.0, available / required) if required > 0.0 else 1.0
    for order in buys:
        fill = _fill(
            order, prices[order.symbol], order.intended_notional * scale, cost_model
        )
        available -= fill.notional + fill.cost
        fills.append(fill)
    return fills
```

- [ ] **Step 5: Add Portfolio.apply**

In `src/boring_alpha/portfolio/account.py`, change the import line to:

```python
from boring_alpha.domain import Fill, Order, Trade
```

Then add this method to `Portfolio`, immediately after `plan_rebalance`:

```python
    def apply(self, fills: list[Fill]) -> None:
        """Book fills against cash and positions, preserving the cash-only rule."""

        for fill in fills:
            if fill.side == "SELL":
                self.positions[fill.symbol] -= fill.quantity
                self.cash += fill.notional - fill.cost
            else:
                self.positions[fill.symbol] += fill.quantity
                self.cash -= fill.notional + fill.cost
        if self.cash < -1e-7:
            raise AccountingError(f"cash-only portfolio became negative: {self.cash}")
        if abs(self.cash) < 1e-9:
            self.cash = 0.0
```

- [ ] **Step 6: Run the new test and the whole suite**

Run: `.venv/bin/python -m unittest tests.test_execution -v`
Expected: PASS, 11 tests.

Run: `.venv/bin/python -m unittest discover -s tests`
Expected: PASS, 200 tests.

- [ ] **Step 7: Commit**

```bash
git add src/boring_alpha/domain.py src/boring_alpha/execution src/boring_alpha/portfolio/account.py tests/test_execution.py
git commit -m "Add the execution layer and the Fill record

execute() is the only place that knows what a trade costs and what price it
gets, which is what makes it the layer a paper mode replaces. It takes a plain
price mapping rather than a market dataset so the same function can be fed
broker quotes. A buy scaled down by available cash is now an explicit partial
fill rather than a silently smaller trade.

The old rebalance path is still in place and is removed in the next step.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Wire the engine and retire the fused path

**Files:**
- Modify: `src/boring_alpha/backtest/engine.py` (imports, `__init__`, the rebalance block in `run`, the result construction)
- Modify: `src/boring_alpha/domain.py` (delete `Trade`; rename `BacktestResult.trades` to `fills`; add `orders`)
- Modify: `src/boring_alpha/portfolio/account.py` (delete `rebalance` and the `Trade` import)
- Modify: `src/boring_alpha/metrics/performance.py:78-79,97`
- Modify: `src/boring_alpha/report.py:99-112`
- Modify: `tests/test_metrics.py` (replace `Trade` with `Fill`)
- Modify: `tests/test_portfolio.py` (delete the two tests that call `rebalance`; execution now covers them)
- Modify: `tests/test_backtest.py:39-42,112,213-214` (`.trades` becomes `.fills`)
- Modify: `tests/test_ragged.py:57-58` (`.trades` becomes `.fills`)

**Interfaces:**
- Consumes: `Order` and `plan_rebalance` from Task 1; `Fill`, `CostModel`, `execute`, `Portfolio.apply` from Task 2.
- Produces: `BacktestResult.fills: tuple[Fill, ...]` and `BacktestResult.orders: tuple[Order, ...]`. Task 4 reads both when writing the trades CSV.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_attribution.py`:

```python


class OrderLedgerTests(unittest.TestCase):
    def test_every_fill_matches_an_order_by_date_symbol_and_side(self) -> None:
        _, result = _run()
        keys = {(order.date, order.symbol, order.side) for order in result.orders}
        for fill in result.fills:
            self.assertIn((fill.date, fill.symbol, fill.side), keys)

    def test_the_reference_price_is_the_decision_month_end_close(self) -> None:
        data, result = _run()
        for order in result.orders:
            self.assertEqual(order.reference_price, data.bar(SIGNAL, order.symbol).close)

    def test_fills_never_exceed_what_was_intended(self) -> None:
        _, result = _run()
        for fill in result.fills:
            self.assertLessEqual(fill.notional, fill.intended_notional + 1e-9)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_attribution -v`
Expected: FAIL — `AttributeError: 'BacktestResult' object has no attribute 'orders'`

- [ ] **Step 3: Update the domain record**

In `src/boring_alpha/domain.py`, delete the entire `Trade` class. Then in `BacktestResult`:

Rename the `trades` field **in place**, keeping its position:

```python
    fills: tuple[Fill, ...]
```

and append `orders` as the **last** field of the class, after `cash_interest`:

```python
    orders: tuple[Order, ...] = ()
```

Position matters twice here. Several tests construct `BacktestResult` with five
positional arguments (`name, initial_equity, equity_curve, fills, decisions`),
so `fills` must stay where `trades` was. And `orders` carries a default, so it
must follow every field that does not, or the dataclass raises at import.

- [ ] **Step 4: Delete the fused rebalance**

In `src/boring_alpha/portfolio/account.py`, delete the whole `rebalance` method (from `def rebalance(` through `return trades`). Change the import line to:

```python
from boring_alpha.domain import Fill, Order
```

- [ ] **Step 5: Wire the engine**

In `src/boring_alpha/backtest/engine.py`, change the domain import to:

```python
from boring_alpha.domain import BacktestResult, EquityPoint, Fill, Order, SignalSnapshot
```

and add:

```python
from boring_alpha.execution import CostModel, execute
```

In `Backtester.__init__`, immediately after `self.cost_bps = cost_bps`, add:

```python
        self.cost_model = CostModel(cost_bps)
```

In `run`, replace the two ledger locals:

```python
        trades: list[Trade] = []
```

with:

```python
        fills: list[Fill] = []
        orders: list[Order] = []
```

Replace the whole `if pending is not None:` block with:

```python
            if pending is not None:
                prices = {
                    symbol: self.data.bar(day, symbol).open for symbol in self.symbols
                }
                references = {
                    symbol: self.data.bar(pending.as_of, symbol).close
                    for symbol in self.symbols
                }
                new_orders = portfolio.plan_rebalance(
                    prices, pending.target_weights, references, day
                )
                new_fills = execute(new_orders, prices, portfolio.cash, self.cost_model)
                portfolio.apply(new_fills)
                for fill in new_fills:
                    contributions[fill.symbol] -= fill.cost
                orders.extend(new_orders)
                fills.extend(new_fills)
                decisions.append(pending)
                pending = None
```

In the `return BacktestResult(...)` call, replace `trades=tuple(trades),` with:

```python
            fills=tuple(fills),
            orders=tuple(orders),
```

- [ ] **Step 6: Update the metrics consumers**

In `src/boring_alpha/metrics/performance.py`, replace the three lines that read `result.trades`:

```python
    total_cost = sum(fill.cost for fill in result.fills)
    traded_notional = sum(fill.notional for fill in result.fills)
```

and

```python
        "trade_count": len(result.fills),
```

- [ ] **Step 7: Update the report writer**

In `src/boring_alpha/report.py`, inside `_trades_csv`, replace the loop body so it reads from `result.fills`. Keep the header row exactly as it is — the new columns arrive in Task 4:

```python
    for fill in result.fills:
        writer.writerow(
            [
                fill.date,
                fill.symbol,
                fill.side,
                fill.quantity,
                fill.price,
                fill.notional,
                fill.cost,
            ]
        )
```

- [ ] **Step 8: Update the tests that named Trade**

In `tests/test_metrics.py`, change the import to use `Fill`:

```python
from boring_alpha.domain import BacktestResult, EquityPoint, Fill, PriceBar
```

Replace each `Trade(...)` construction with a `Fill(...)` carrying the two extra fields. There are three, in `test_turnover_annualizes_against_average_equity_and_elapsed_years` and `test_one_way_turnover_counts_one_side_of_a_round_trip`:

```python
        trades = (Fill(date(2024, 1, 2), "A", "BUY", 1.0, 50.0, 50.0, 0.0, 50.0, 50.0),)
```

```python
        trades = (
            Fill(date(2024, 1, 2), "A", "BUY", 1.0, 100.0, 100.0, 0.0, 100.0, 100.0),
            Fill(date(2024, 12, 31), "A", "SELL", 1.0, 100.0, 100.0, 0.0, 100.0, 100.0),
        )
```

Every `BacktestResult("t", 100.0, curve, trades, ())` positional call still works, because `fills` occupies the position `trades` used to.

In `tests/test_backtest.py` and `tests/test_ragged.py`, rename the attribute at
every read. These are the nine occurrences:

```bash
sed -i '' 's/result\.trades/result.fills/g; s/base\.trades/base.fills/g; s/other\.trades/other.fills/g' tests/test_backtest.py tests/test_ragged.py
```

Then confirm none remain:

```bash
grep -rn '\.trades' tests || echo "no .trades references left"
```

In `tests/test_portfolio.py`, delete `test_buys_scale_pro_rata_when_costs_exceed_cash` and `test_sale_proceeds_fund_purchases_in_the_same_rebalance` — `tests/test_execution.py` now covers both behaviours against the new seam. Keep `test_negative_cash_raises_a_runtime_error_subclass`, but rewrite it to use `apply`:

```python
    def test_negative_cash_raises_a_runtime_error_subclass(self) -> None:
        portfolio = Portfolio(1_000.0, ("A",))
        portfolio.cash = -1.0
        with self.assertRaises(AccountingError) as caught:
            portfolio.apply([])
        self.assertIsInstance(caught.exception, RuntimeError)
```

- [ ] **Step 9: Run the whole suite**

Run: `.venv/bin/python -m unittest discover -s tests`
Expected: PASS. Count will be 201 (200 from Task 2, plus 3 new attribution tests, minus 2 deleted portfolio tests).

If anything fails, fix the implementation, not the test — these tests encode the behaviour that must not change.

- [ ] **Step 10: Prove the refactor changed no numbers**

```bash
BASE=/private/tmp/claude-501/-Users-haoyu-development-boring-alpha/2daab586-da89-4f60-b5c7-7def20db32b1/scratchpad/baseline/current
.venv/bin/boring-alpha backtest configs/ba_001_multi_asset_trend.toml > /tmp/after_backtest.txt
.venv/bin/boring-alpha sweep configs/ba_001_multi_asset_trend.toml > /tmp/after_sweep.txt
RUN=$(grep -o 'BoringAlpha run [0-9a-f]*' /tmp/after_backtest.txt | awk '{print $3}')
SWEEP=$(grep -o 'BoringAlpha sweep [0-9a-f]*' /tmp/after_sweep.txt | awk '{print $3}')
for f in strategy_equity.csv benchmark_equity.csv cash_equity.csv metrics.json decisions.json strategy_trades.csv benchmark_trades.csv; do
  diff -q "$BASE/backtest/$f" "experiments/BA-001/$RUN/$f" || echo "DIFFERS: $f"
done
for f in criteria.json summary.md; do
  diff -q "$BASE/sweep/$f" "experiments/BA-001/sweeps/$SWEEP/$f" || echo "DIFFERS: $f"
done
```

Expected: no output at all. Every file identical, including the trades CSVs, because the new columns are not added until Task 4.

If any file differs, stop and find the cause. Likely suspects, in order: fill ordering (sells before buys, sorted within each side), the `abs(difference) <= 1e-10` threshold in `plan_rebalance` versus the old asymmetric thresholds, or buys being dropped instead of filled at zero notional when `scale` is zero.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "Split the portfolio and execution layers in the engine

One rebalance is now three named steps: plan, execute, apply. The cost model
and the fill assumption live only in the middle one, which is the step a paper
mode replaces. Trade is gone; BacktestResult carries fills and the orders that
produced them, so an order that filled partially is visible rather than
inferred.

Verified behaviour-neutral: the demo backtest and sweep reproduce equity
curves, metrics, decisions, criteria and summary byte-identically against a
baseline captured before the change.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Record intent and slippage in the ledger

**Files:**
- Modify: `src/boring_alpha/report.py` (`ARTIFACT_SCHEMA`, `_trades_csv`)
- Modify: `README.md` ("Run artifacts" section)
- Test: `tests/test_slippage.py` (create)

**Interfaces:**
- Consumes: `BacktestResult.fills` from Task 3.
- Produces: no new code interfaces. `strategy_trades.csv` and `benchmark_trades.csv` gain two trailing columns; `artifact_schema` becomes 5.

- [ ] **Step 1: Write the failing test**

Create `tests/test_slippage.py`:

```python
"""The ledger must record what was intended, not only what happened."""

from datetime import date
import unittest

from boring_alpha.backtest.engine import Backtester
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.report import ARTIFACT_SCHEMA, _trades_csv
from boring_alpha.signals.trend import MultiAssetTrend

ANCHOR, SIGNAL, FILL = date(2023, 12, 29), date(2024, 12, 31), date(2025, 1, 2)


def _run():
    bars = [
        PriceBar(ANCHOR, "A", 100.0, 100.0),
        PriceBar(SIGNAL, "A", 120.0, 120.0),
        # The open gaps up from the month-end close: that gap is the slippage.
        PriceBar(FILL, "A", 132.0, 132.0),
    ]
    days = [ANCHOR, SIGNAL, FILL]
    data = MarketData(bars, {day: 1.0 for day in days}, source="test")
    return Backtester(
        data, ("A",), initial_cash=1_000.0, cost_bps=0.0, start=FILL, end=FILL
    ).run(MultiAssetTrend(("A",), 12, 1.0))


class SlippageTests(unittest.TestCase):
    def test_the_schema_records_the_wider_ledger(self) -> None:
        self.assertEqual(ARTIFACT_SCHEMA, 5)

    def test_the_ledger_header_names_intent_and_reference(self) -> None:
        header = _trades_csv(_run()).splitlines()[0]
        self.assertEqual(
            header,
            "date,symbol,side,quantity,price,notional,cost,intended_notional,reference_price",
        )

    def test_the_reference_price_differs_from_the_fill_price(self) -> None:
        row = _trades_csv(_run()).splitlines()[1].split(",")
        self.assertEqual(float(row[4]), 132.0)   # filled at the next open
        self.assertEqual(float(row[8]), 120.0)   # decided at the month-end close

    def test_a_fully_filled_order_reports_equal_notionals(self) -> None:
        row = _trades_csv(_run()).splitlines()[1].split(",")
        self.assertAlmostEqual(float(row[5]), float(row[7]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_slippage -v`
Expected: FAIL — `AssertionError: 4 != 5`

- [ ] **Step 3: Widen the ledger**

In `src/boring_alpha/report.py`, change the schema constant:

```python
ARTIFACT_SCHEMA = 5
```

In `_trades_csv`, change the header row and add the two values to each row:

```python
    writer.writerow(
        [
            "date",
            "symbol",
            "side",
            "quantity",
            "price",
            "notional",
            "cost",
            "intended_notional",
            "reference_price",
        ]
    )
    for fill in result.fills:
        writer.writerow(
            [
                fill.date,
                fill.symbol,
                fill.side,
                fill.quantity,
                fill.price,
                fill.notional,
                fill.cost,
                fill.intended_notional,
                fill.reference_price,
            ]
        )
```

- [ ] **Step 4: Run the new test and the whole suite**

Run: `.venv/bin/python -m unittest tests.test_slippage -v`
Expected: PASS, 4 tests.

Run: `.venv/bin/python -m unittest discover -s tests`
Expected: PASS, 205 tests.

- [ ] **Step 5: Confirm only the permitted artifact changed**

```bash
BASE=/private/tmp/claude-501/-Users-haoyu-development-boring-alpha/2daab586-da89-4f60-b5c7-7def20db32b1/scratchpad/baseline/current
.venv/bin/boring-alpha backtest configs/ba_001_multi_asset_trend.toml > /tmp/after4.txt
RUN=$(grep -o 'BoringAlpha run [0-9a-f]*' /tmp/after4.txt | awk '{print $3}')
for f in strategy_equity.csv benchmark_equity.csv cash_equity.csv metrics.json decisions.json; do
  diff -q "$BASE/backtest/$f" "experiments/BA-001/$RUN/$f" || echo "UNEXPECTED DIFF: $f"
done
echo "--- trades CSV: expect two new trailing columns and identical leading fields ---"
head -3 "experiments/BA-001/$RUN/strategy_trades.csv"
diff <(cut -d, -f1-7 "$BASE/backtest/strategy_trades.csv") \
     <(cut -d, -f1-7 "experiments/BA-001/$RUN/strategy_trades.csv") && echo "leading columns identical"
```

Expected: no `UNEXPECTED DIFF` lines, and `leading columns identical`.

- [ ] **Step 6: Update the README**

In `README.md`, in the "Run artifacts" section, replace the sentence `artifact_schema` is 4; a manifest without that field predates the schema.` with:

```markdown
`artifact_schema` is 5; a manifest without that field predates the schema.

The trade ledgers record `intended_notional` beside the filled notional, so an
order that was scaled down by available cash is visible as a partial fill, and
`reference_price` — the month-end close the decision was made on — beside the
fill price. The difference between those two prices is slippage; in the
backtest it is the overnight gap, and it is the figure a paper fill will be
compared against.
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Record intent and reference price in the trade ledger

The ledger now carries the notional an order asked for beside the notional it
got, so a buy scaled down by available cash is visible as a partial fill, and
the month-end close the decision was made on beside the price it filled at.
The gap between those prices is slippage: in the backtest it is the overnight
move, currently invisible, and it is what a paper fill will be measured
against. artifact_schema is 5.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done when

- 205 tests pass.
- The demo backtest and sweep reproduce equity, metrics, decisions, criteria and summary byte-identically against the baseline.
- `Portfolio` no longer knows what a trade costs; `execution` is the only module that does.
- `strategy_trades.csv` shows a reference price that differs from the fill price.
