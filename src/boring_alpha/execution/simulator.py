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
