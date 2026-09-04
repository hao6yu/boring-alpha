# Portfolio / execution split

Status: **approved, not yet implemented**
Date: 2026-09-04

## Why

`docs/principles.md` §3 requires four separable layers, and says backtest, paper
and live modes must share the first three. Today the last two are fused:
`Portfolio.rebalance` values the book, derives target values, decides the
trades, and fills them at the open with costs, all in one function.

The consequence is not a bug — the accounting is correct — but a missing seam.
Nothing in the system emits an order. A paper fill therefore has nothing to be
compared against, so the milestone this laboratory exists for, comparing paper
results with historical simulation, cannot be reached without either this split
or a second implementation of the sizing rule that would silently drift from the
first.

## What changes

### Records

```python
@dataclass(frozen=True, slots=True)
class Order:
    date: date              # session the order is to be executed on
    symbol: str
    side: str               # BUY or SELL
    intended_notional: float
    reference_price: float  # decision-time price: the month-end close

@dataclass(frozen=True, slots=True)
class Fill:
    order: Order
    quantity: float
    price: float
    notional: float         # actually filled, <= order.intended_notional
    cost: float
```

`Fill` replaces `Trade` and exposes `date`, `symbol` and `side` as properties
delegating to its order, so existing call sites and artifact columns are
unchanged. `BacktestResult` gains `orders` alongside `fills`, so an order that
filled partially is visible rather than inferred from a quantity.

### Layers

- **Portfolio** keeps cash, positions and valuation, and gains
  `plan_rebalance(prices, targets, references) -> list[Order]`. Pure: no
  mutation, no cost model, no market data object.
- **Execution** is a new package with `CostModel` and a pure
  `execute(orders, prices, cash, cost_model) -> list[Fill]`. It applies sells
  first, then scales buys pro rata to the cash actually available afterwards —
  the existing rule, relocated. It takes a plain `dict[str, float]` of prices
  rather than `MarketData`, so paper mode can pass broker quotes.
- **Portfolio.apply(fills)** mutates cash and positions and keeps the
  negative-cash guard (`AccountingError`).

### Data flow

One rebalance becomes three named steps: decision → orders → fills → applied.
The cost model and the fill assumption live only in the middle step, which is
the point: that is the step paper mode replaces.

### Artifacts

The trades CSV gains `intended_notional` and `reference_price`;
`artifact_schema` becomes 5. Slippage becomes measurable. In the backtest it is
the overnight gap between the month-end close and the next session's open, which
is real, currently invisible, and directly relevant to the charter's reserved
question about execution-timing sensitivity.

## What deliberately does not change

Order sizes are still computed from equity at the execution open, not at the
decision close. A real order placed after a month-end close would be sized on
close-time equity; that is arguably more faithful, but it changes results, and
bundling a behaviour change into a refactor makes neither reviewable. Recording
`reference_price` now makes the alternative measurable later, as a declared
variant rather than a silent change to BA-001.

The charter is untouched. It fixes the execution timestamp and says nothing
about sizing, so no amendment is needed.

## Acceptance

The refactor is behaviour-neutral, and this is checked rather than asserted:

1. All 183 existing tests pass unchanged, except where a test names `Trade`.
2. The demo backtest and sweep are re-run and compared against a baseline
   captured before the change. Equity curves, `metrics.json`, `decisions.json`,
   `criteria.json` and `summary.md` must be byte-identical. Run identifiers will
   differ, because the code hash is part of run identity by design.
3. The only permitted artifact difference is the two new trades-CSV columns.
4. Any other difference is a bug in the refactor, not an improvement, and is
   fixed rather than explained.

New tests cover: `plan_rebalance` returning orders without mutating the
portfolio; `execute` scaling buys pro rata when sale proceeds are insufficient;
a partially filled order showing intended and filled notionals that differ; the
reference price being the decision month-end close rather than the fill price;
and the existing accounting identity continuing to hold through the new path.

## Out of scope

Broker connectivity, live orders, order types beyond market-on-open, whole-share
rounding, partial-fill modelling beyond the existing cash constraint, and any
change to signal or portfolio construction.
