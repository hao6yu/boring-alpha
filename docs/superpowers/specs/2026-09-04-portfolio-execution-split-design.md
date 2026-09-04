# Portfolio / execution split

Status: **approved, not yet implemented**
Date: 2026-09-04
Revised: 2026-09-04 — records are flat and matched by key, rather than a
fill holding its order.

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
    date: date
    symbol: str
    side: str
    quantity: float
    price: float
    notional: float         # actually filled, <= intended_notional
    cost: float
    intended_notional: float
    reference_price: float
```

Both records are flat, and a fill is matched to its order by
`(date, symbol, side)`. The strategy issues at most one order per symbol per
session, so that key is unique by construction.

Flat records rather than a `Fill.order` reference, for three reasons. A broker
returns fills that know nothing about our objects, and reconciliation will match
them by instrument, side and date; modelling the link as an object reference
would model something the live system does not have. Serialization stays direct,
with no nested blob in JSON and no indirection in the CSV writer. And an order
that fills for nothing — which happens when buys scale to zero — is visible by
the absence of a matching fill, rather than requiring a zero-quantity fill to
represent it.

The cost is that `intended_notional` and `reference_price` appear on both
records. That duplication is deliberate: they are exactly the fields the trade
ledger needs, and denormalising them onto a ledger row is the ordinary shape for
this kind of record.

`Fill` replaces `Trade`. `BacktestResult` gains `orders` alongside `fills`, so
an order that filled partially, or not at all, is visible rather than inferred
from a quantity.

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
