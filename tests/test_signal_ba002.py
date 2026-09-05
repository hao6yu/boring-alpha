"""Hand-computed ensemble examples, independent of the implementation helper."""

from datetime import date
import json
import unittest

from boring_alpha.backtest.engine import Backtester
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.report import json_text, snapshot_record
from boring_alpha.signals import MultiHorizonTrend


ANCHORS = (date(2023, 10, 31), date(2024, 1, 31), date(2024, 4, 30))
AS_OF = date(2025, 1, 31)


def _market(prices, *, factors=None, future=None):
    days = (*ANCHORS, AS_OF)
    bars = [PriceBar(day, symbol, values[i], values[i])
            for symbol, values in prices.items() for i, day in enumerate(days)]
    cash = dict(zip(days, factors or (1.0, 1.0, 1.0, 1.0)))
    if future is not None:
        next_day, next_price = future
        bars.extend(PriceBar(next_day, symbol, next_price, next_price) for symbol in prices)
        cash[next_day] = 1.0
    return MarketData(bars, cash, source="synthetic-hand-check")


class MultiHorizonSignalTests(unittest.TestCase):
    def test_zero_one_two_three_votes_and_inactive_sleeves_keep_cash(self):
        data = _market({
            "ZERO": (120, 120, 120, 100),
            "ONE": (120, 120, 80, 100),
            "TWO": (120, 80, 80, 100),
            "THREE": (80, 80, 80, 100),
        })
        snapshot = MultiHorizonTrend(data.symbols, (9, 12, 15), 0.2).snapshot(data, AS_OF)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.target_weights["ZERO"], 0.0)
        self.assertAlmostEqual(snapshot.target_weights["ONE"], 0.2 / 3)
        self.assertAlmostEqual(snapshot.target_weights["TWO"], 0.4 / 3)
        self.assertAlmostEqual(snapshot.target_weights["THREE"], 0.2)
        self.assertAlmostEqual(sum(snapshot.target_weights.values()), 0.4)
        self.assertIsNone(snapshot.cash_return)
        self.assertEqual(snapshot.asset_returns, {})

    def test_pair_uses_two_votes_not_three(self):
        data = _market({"A": (120, 120, 80, 100)})
        snapshot = MultiHorizonTrend(("A",), (9, 12), 0.6).snapshot(data, AS_OF)
        self.assertAlmostEqual(snapshot.target_weights["A"], 0.3)
        self.assertEqual(len(snapshot.horizon_evidence), 2)

    def test_each_vote_uses_its_own_cash_anchor(self):
        # Cash indexes: 1, 1.1, 1.32, 1.65. Hurdles: 65%, 50%, 25%.
        data = _market({"A": (100, 100, 100, 140)}, factors=(1.0, 1.1, 1.2, 1.25))
        snapshot = MultiHorizonTrend(("A",), (9, 12, 15), 0.6).snapshot(data, AS_OF)
        evidence = {entry.horizon_months: entry for entry in snapshot.horizon_evidence}
        self.assertAlmostEqual(snapshot.target_weights["A"], 0.2)
        for horizon, anchor, cash, vote in (
            (9, ANCHORS[2], 0.25, True),
            (12, ANCHORS[1], 0.50, False),
            (15, ANCHORS[0], 0.65, False),
        ):
            with self.subTest(horizon=horizon):
                record = evidence[horizon]
                self.assertEqual(record.anchor_date, anchor)
                self.assertAlmostEqual(record.cash_return, cash)
                self.assertAlmostEqual(record.asset_returns["A"], 0.4)
                self.assertIs(record.votes["A"], vote)
                self.assertAlmostEqual(record.target_weights["A"], 0.2 if vote else 0.0)

    def test_an_exact_tie_votes_cash(self):
        # Binary-exact indexes ensure this really is an equality fixture.
        data = _market({"A": (1, 2, 4, 8)}, factors=(1, 2, 2, 2))
        snapshot = MultiHorizonTrend(("A",), (9, 12, 15), 1.0).snapshot(data, AS_OF)
        self.assertEqual(snapshot.target_weights, {"A": 0.0})
        self.assertTrue(all(not item.votes["A"] for item in snapshot.horizon_evidence))

    def test_pair_without_fifteen_vote_still_requires_fifteen_month_history(self):
        data = _market({"A": (80, 80, 80, 100)})
        short = MarketData(
            [bar for day in data.dates if day != ANCHORS[0]
             for bar in data.by_date[day].values()],
            {day: value for day, value in data.cash_factors.items() if day != ANCHORS[0]},
            source="synthetic-short",
        )
        policy = MultiHorizonTrend(("A",), (9, 12), 1.0)
        self.assertIsNone(policy.snapshot(short, AS_OF))
        self.assertIsNotNone(policy.snapshot(data, AS_OF))

    def test_an_active_horizon_missing_its_anchor_has_no_signal(self):
        data = _market({"A": (80, 80, 80, 100)})
        missing = ANCHORS[1]
        short = MarketData(
            [bar for day in data.dates if day != missing
             for bar in data.by_date[day].values()],
            {day: value for day, value in data.cash_factors.items() if day != missing},
            source="synthetic-missing-anchor",
        )
        self.assertIsNone(MultiHorizonTrend(("A",), (9, 12, 15), 1.0).snapshot(short, AS_OF))

    def test_future_prices_and_cash_cannot_change_earlier_votes(self):
        next_day = date(2025, 2, 3)
        base = _market({"A": (120, 80, 80, 100)}, future=(next_day, 1.0))
        changed = _market({"A": (120, 80, 80, 100)}, future=(next_day, 1e9))
        factors = {**changed.cash_factors, next_day: 100.0}
        changed = MarketData(
            [bar for bars in changed.by_date.values() for bar in bars.values()],
            factors, source="synthetic-future-change",
        )
        policy = MultiHorizonTrend(("A",), (9, 12, 15), 1.0)
        self.assertEqual(policy.snapshot(base, AS_OF), policy.snapshot(changed, AS_OF))

    def test_decision_executes_only_at_next_session_open(self):
        next_day = date(2025, 2, 3)
        data = _market({"A": (80, 80, 80, 100)}, future=(next_day, 200.0))
        result = Backtester(data, ("A",), initial_cash=1000.0, cost_bps=0.0,
                            start=date(2025, 2, 1), end=next_day).run(
            MultiHorizonTrend(("A",), (9, 12, 15), 0.5)
        )
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.decisions[0].as_of, AS_OF)
        fill = result.fills[0]
        self.assertEqual((fill.date, fill.reference_price, fill.price), (next_day, 100.0, 200.0))
        self.assertAlmostEqual(fill.quantity, 2.5)

    def test_evidence_serializes_dates_and_null_legacy_cash_field(self):
        data = _market({"A": (80, 80, 80, 100)})
        snapshot = MultiHorizonTrend(("A",), (9, 12, 15), 1.0).snapshot(data, AS_OF)
        record = json.loads(json_text(snapshot_record(snapshot)))
        self.assertIsNone(record["cash_return"])
        self.assertEqual(record["asset_returns"], {})
        self.assertEqual(record["horizon_evidence"][0]["anchor_date"], "2024-04-30")
        self.assertEqual(record["horizon_evidence"][0]["horizon_months"], 9)

    def test_invalid_horizons_and_warmup_are_refused(self):
        for horizons in ((), (9, 9), (0, 12), (-1, 12), (9.0, 12), (True, 12), ("9", 12)):
            with self.subTest(horizons=horizons), self.assertRaises(ValueError):
                MultiHorizonTrend(("A",), horizons, 1.0)
        for warmup in (12, 15.0, True, 0):
            with self.subTest(warmup=warmup), self.assertRaises(ValueError):
                MultiHorizonTrend(("A",), (9, 12, 15), 1.0, warmup)

    def test_horizon_order_is_canonical(self):
        policy = MultiHorizonTrend(("A",), (15, 9, 12), 1.0)
        self.assertEqual(policy.horizons, (9, 12, 15))
