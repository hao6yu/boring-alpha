"""Independent cash-and-quantity examples; no market history or network."""

import math

import pytest

from boring_alpha.futures_account import FuturesAccount, MissingMark


def test_price_round_trip_does_not_create_profit_without_trades():
    account = FuturesAccount(1000)
    account.trade({"A": 5, "B": -5}, {"A": 100, "B": 100}, 0)
    assert account.mark({"A": 200, "B": 100}) == 500
    assert account.equity == 1500
    assert account.mark({"A": 100, "B": 100}) == -500
    assert account.equity == 1000
    assert account.quantities == {"A": 5, "B": -5}


def test_rebalance_charges_for_drift_even_with_unchanged_names():
    account = FuturesAccount(1000)
    account.trade({"A": 5, "B": -5}, {"A": 100, "B": 100}, 0)
    account.mark({"A": 200, "B": 100})
    # At $1500 equity, +/- $750 requires 3.75 A and -7.5 B.
    notional, fee = account.trade({"A": 3.75, "B": -7.5}, {"A": 200, "B": 100}, 10)
    assert notional == 500  # sell 1.25 A for $250 and 2.5 B for $250
    assert fee == 0.5
    assert account.equity == 1499.5


def test_round_trip_pays_both_entry_and_exit_fees():
    account = FuturesAccount(1000)
    account.trade({"A": 5, "B": -5}, {"A": 100, "B": 100}, 100)
    account.mark({"A": 100, "B": 100})
    account.trade({}, {"A": 100, "B": 100}, 100)
    assert account.equity == 980
    assert account.fees_paid == 20
    assert account.traded_notional == 2000


def test_funding_uses_quantity_and_the_event_mark_not_entry_notional():
    account = FuturesAccount(1000)
    account.trade({"A": 2, "B": -3}, {"A": 100, "B": 100}, 0)
    assert account.fund("A", 0.01, 110) == pytest.approx(2.2)
    assert account.fund("B", 0.01, 120) == pytest.approx(-3.6)
    assert account.equity == pytest.approx(1001.4)
    assert account.quantities == {"A": 2, "B": -3}


def test_missing_mark_never_closes_or_discards_a_position():
    account = FuturesAccount(1000)
    account.trade({"A": 5, "B": -5}, {"A": 100, "B": 100}, 0)
    with pytest.raises(MissingMark):
        account.mark({"B": 100})
    assert account.equity == 1000
    assert account.quantities["A"] == 5
    account.mark({"A": 50, "B": 100})
    assert account.equity == 750


def test_rebalance_cannot_silently_erase_unmarked_profit():
    account = FuturesAccount(1000)
    account.trade({"A": 5}, {"A": 100}, 0)
    with pytest.raises(ValueError, match="mark held"):
        account.trade({}, {"A": 110}, 0)
    assert account.quantities == {"A": 5}
    account.mark({"A": 110})
    account.trade({}, {"A": 110}, 0)
    assert account.equity == 1050


@pytest.mark.parametrize("price", [0, -1, math.nan, math.inf])
def test_invalid_prices_fail_before_changing_account(price):
    account = FuturesAccount(1000)
    with pytest.raises(ValueError):
        account.trade({"A": 1}, {"A": price}, 0)
    assert account.equity == 1000
    assert not account.quantities
