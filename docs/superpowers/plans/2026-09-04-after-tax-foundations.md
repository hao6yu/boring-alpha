# After-Tax Foundations Implementation Plan (plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put in place everything the tax overlay will stand on — a `hold` signal, a v2 data snapshot with distributions, a distributions reader, a target-exposure benchmark selectable from configuration, and a per-strategy evaluation registry — without changing any existing run's meaning.

**Architecture:** Every change is additive. The engine gains one branch (a hold snapshot places no orders once something has been bought). The fetcher writes one more file and records splits. A new reader loads that file for the overlay only; the engine never sees it. Configuration gains an optional `[benchmark]` table; a new `TargetExposureAllocation` policy consumes it. BA-001's grid, criteria and verdict move behind a `StrategyProfile` registry so a second strategy can define its own, and golden tests against BA-001's two real sweeps prove nothing moved. Plan 2 (the tax overlay, `tax.json`, the `aftertax` CLI, schema 6) builds on these interfaces.

**Tech Stack:** Python ≥ 3.11, standard library only (`pyproject.toml` declares `dependencies = []`), `unittest`-style tests run with pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-after-tax-evaluation-design.md` (revision 3). This plan implements spec §3, §5, §6, §6.1, and the engine and test items of §9 and §12 steps 1, 2, 4, 5. Spec §4, §7, §8 (the overlay, sweep tax wiring, `aftertax`, the BA-001 note) are plan 2.

## Global Constraints

- Python ≥ 3.11; no third-party dependencies may be added.
- Tests are `unittest.TestCase` classes in `tests/test_*.py`, run with `.venv/bin/python -m pytest -q`. The suite passes today: 272 executions. It must pass after every task.
- Existing behaviour is preserved: for any policy that never sets `hold`, the equity, trades and decisions files a run writes are byte-identical to today's; `manifest.json` differs only in `code_sha256` (any code change does that). `artifact_schema` stays `5` in this plan.
- Every existing BA-001 `strategy_spec_sha256` is unchanged: the `[benchmark]` table enters the hash only when present. The checked-in `configs/ba_001_development.toml` must keep hashing to `595a25e57ed68d4e863eeb69b40248345840b809b0f213609ddd14b4cd952110`.
- BA-001's criteria and verdict are behaviour-identical, proven by replaying the two real sweeps' `criteria.json` files (copied into `tests/fixtures/`).
- Exact strings, copied from the spec: methodology identifier `yahoo-adjusted-v2+dgs3mo-v1`; distributions file `distributions_daily.csv` with columns exactly `date, symbol, close, dividend`; benchmark policy name `Target-Exposure Benchmark (60%, annual)` (format `({exposure:.0%}, {rebalance})`); `[benchmark]` keys `exposure` in `(0, 1]` and `rebalance` in `annual | monthly`.
- Artifacts are write-once; nothing in `experiments/` is ever edited or deleted.
- Commit after every task. Messages are imperative, one line, in the repository's existing style, and end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Never run a sealed-period evaluation. Nothing in this plan touches `experiments/` except reading two `criteria.json` files.

---

## File structure

| Path | Responsibility | Task |
|---|---|---|
| `src/boring_alpha/domain.py` | `SignalSnapshot.hold` field | 2 |
| `src/boring_alpha/backtest/engine.py` | hold branch in `Backtester.run` | 2 |
| `src/boring_alpha/report.py` | `snapshot_record()` (omits a false hold); `READABLE_SCHEMAS` | 2, 9 |
| `tools/fetch_market_data.py` | methodology v2, `distribution_rows_from_chart`, `splits_from_chart`, `fetch_chart`, snapshot with distributions and splits | 3 |
| `src/boring_alpha/data/distributions.py` | `DistributionTable`, `load_distributions`, `split_records` — the only reader of the new file | 4 |
| `src/boring_alpha/config.py` | `BenchmarkConfig`, `[benchmark]` schema, spec-hash inclusion when present | 5 |
| `src/boring_alpha/signals/trend.py`, `signals/__init__.py` | `TargetExposureAllocation` | 6 |
| `src/boring_alpha/profiles.py` | `VariantSpec`, `StrategyProfile`, `BA001Profile`, `PROFILES`, `profile_for` | 7 |
| `src/boring_alpha/sweep.py` | `run_sweep` driven by a profile's grid | 8 |
| `src/boring_alpha/cli.py` | `run_classify` via profile, schema compatibility, tax-policy agreement | 9 |
| `tests/fixtures/ba001_development_criteria.json`, `tests/fixtures/ba001_validation_criteria.json` | golden data from the real sweeps | 7 |
| `docs/decisions/2026-MM-DD-distributions-v2.md` | the v2 snapshot and its hand checks | 10 |

---

### Task 1: Pin the engine's homogeneity

The after-tax NAV convention (spec §4.8) rests on one property: doubling the starting cash doubles every point of the equity curve. This task pins it. The test passes on today's code; it exists so plan 2 can rely on it and so any future engine change that breaks it fails loudly.

**Files:**
- Test: `tests/test_backtest.py` (append)

**Interfaces:**
- Consumes: `Backtester(data, symbols, *, initial_cash, cost_bps, start, end).run(policy) -> BacktestResult`; `generate_synthetic_market_data(symbols, start, end, *, seed, annual_cash_rate)`; `MultiAssetTrend(symbols, lookback_months, sleeve_weight)`.
- Produces: nothing; a characterization test.

- [ ] **Step 1: Append the test**

At the end of `tests/test_backtest.py` (before any `if __name__ == "__main__":` block if one exists; otherwise at the end), add:

```python
class HomogeneityTests(unittest.TestCase):
    """The after-tax NAV convention (spec §4.8) rests on this: every rule in the
    engine is proportional to account size, so doubling the cash doubles the curve."""

    def _run(self, initial_cash: float):
        symbols = ("A", "B", "C")
        data = generate_synthetic_market_data(
            symbols, date(2019, 10, 1), date(2022, 12, 31), seed=7, annual_cash_rate=0.02
        )
        engine = Backtester(
            data,
            symbols,
            initial_cash=initial_cash,
            cost_bps=10.0,
            start=date(2021, 1, 1),
            end=date(2022, 12, 31),
        )
        return engine.run(MultiAssetTrend(symbols, 12, 1.0 / 3.0))

    def test_doubling_initial_cash_doubles_the_equity_curve(self) -> None:
        small, large = self._run(10_000.0), self._run(20_000.0)
        self.assertEqual(len(small.equity_curve), len(large.equity_curve))
        self.assertGreater(len(small.fills), 0)
        self.assertEqual(len(small.fills), len(large.fills))
        for a, b in zip(small.equity_curve, large.equity_curve):
            self.assertEqual(a.date, b.date)
            self.assertAlmostEqual(b.equity / a.equity, 2.0, delta=1e-6)
            self.assertAlmostEqual(b.cash, 2.0 * a.cash, delta=1e-6 * max(1.0, abs(a.cash)))
```

`generate_synthetic_market_data`, `Backtester`, `MultiAssetTrend` and `date` are already imported at the top of this file.

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_backtest.py -q -k Homogeneity`
Expected: `1 passed`. If it fails, stop: the spec's §4.8 convention is unsound for this engine and the spec needs revisiting before plan 2.

- [ ] **Step 3: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `273 passed` (272 + 1).

```bash
git add tests/test_backtest.py
git commit -m "Pin the engine's proportionality to account size

The after-tax NAV convention rescales a pre-tax path at each year end,
which is exact only if doubling the cash doubles the curve. This test
makes that assumption fail loudly if the engine ever stops satisfying it.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Hold snapshots

A signal may say "keep the current allocation". The engine treats a hold as a normal rebalance when nothing has ever been bought (there is no allocation to keep), and otherwise records the decision and places no orders. The decisions writer omits a false hold so every existing decisions file is reproduced byte for byte.

**Files:**
- Modify: `src/boring_alpha/domain.py` (`SignalSnapshot`)
- Modify: `src/boring_alpha/backtest/engine.py` (the `if pending is not None:` block inside `Backtester.run`)
- Modify: `src/boring_alpha/report.py` (`decisions_json`, `write_report`; new `snapshot_record`)
- Test: `tests/test_backtest.py`, `tests/test_report.py`

**Interfaces:**
- Produces: `SignalSnapshot(..., hold: bool = False)`; `report.snapshot_record(snapshot: SignalSnapshot) -> dict[str, Any]`.
- Task 6 relies on the engine rule; plan 2 relies on `snapshot_record`.

- [ ] **Step 1: Write the failing engine tests**

Append to `tests/test_backtest.py`:

```python
from dataclasses import replace

from boring_alpha.domain import SignalSnapshot


class _AlwaysHold:
    """Half in A, then hold: what an annually rebalanced benchmark says between Januaries."""

    name = "Always Hold"

    def snapshot(self, data, as_of):
        return SignalSnapshot(
            as_of=as_of,
            target_weights={"A": 0.5},
            asset_returns={},
            cash_return=0.0,
            name=self.name,
            hold=True,
        )


class _NeverHold(_AlwaysHold):
    name = "Never Hold"

    def snapshot(self, data, as_of):
        return replace(super().snapshot(data, as_of), hold=False, name=self.name)


class HoldTests(unittest.TestCase):
    # Month-ends 2024-12-31, 2025-01-31, 2025-02-28; the price moves so that a
    # real rebalance to 50% would trade every month.
    DAYS = {
        date(2024, 12, 31): 100.0,
        date(2025, 1, 2): 100.0,
        date(2025, 1, 31): 150.0,
        date(2025, 2, 3): 150.0,
        date(2025, 2, 28): 75.0,
        date(2025, 3, 3): 75.0,
    }

    def _engine(self) -> Backtester:
        return Backtester(
            _flat_data("A", self.DAYS),
            ("A",),
            initial_cash=1_000.0,
            cost_bps=0.0,
            start=date(2025, 1, 2),
            end=date(2025, 3, 3),
        )

    def test_a_hold_on_an_empty_book_establishes_the_targets(self) -> None:
        result = self._engine().run(_AlwaysHold())
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.fills[0].date, date(2025, 1, 2))
        self.assertEqual(result.fills[0].side, "BUY")
        self.assertAlmostEqual(result.fills[0].notional, 500.0)

    def test_a_hold_on_a_held_book_places_no_orders_but_records_the_decision(self) -> None:
        result = self._engine().run(_AlwaysHold())
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(
            [decision.as_of for decision in result.decisions],
            [date(2024, 12, 31), date(2025, 1, 31), date(2025, 2, 28)],
        )
        self.assertTrue(all(decision.hold for decision in result.decisions))

    def test_without_hold_the_same_targets_rebalance_every_month(self) -> None:
        result = self._engine().run(_NeverHold())
        self.assertEqual(
            [fill.date for fill in result.fills],
            [date(2025, 1, 2), date(2025, 2, 3), date(2025, 3, 3)],
        )
```

`_flat_data` already exists at the top of this file.

- [ ] **Step 2: Write the failing serializer tests**

Append to `tests/test_report.py`:

```python
from boring_alpha.domain import SignalSnapshot
from boring_alpha.report import snapshot_record


class DecisionRecordTests(unittest.TestCase):
    """Files written before `hold` existed must be reproduced byte for byte."""

    def _snapshot(self, **overrides) -> SignalSnapshot:
        fields = dict(
            as_of=date(2024, 1, 31),
            target_weights={"A": 0.5},
            asset_returns={"A": 0.1},
            cash_return=0.01,
            name="P",
        )
        fields.update(overrides)
        return SignalSnapshot(**fields)

    def test_a_false_hold_is_omitted_from_the_record(self) -> None:
        record = snapshot_record(self._snapshot())
        self.assertNotIn("hold", record)
        self.assertEqual(
            record,
            {
                "as_of": date(2024, 1, 31),
                "target_weights": {"A": 0.5},
                "asset_returns": {"A": 0.1},
                "cash_return": 0.01,
                "name": "P",
            },
        )

    def test_a_true_hold_is_recorded(self) -> None:
        self.assertIs(snapshot_record(self._snapshot(hold=True))["hold"], True)

    def test_decisions_json_uses_the_record(self) -> None:
        result = _result_with_decisions(self._snapshot(), self._snapshot(hold=True))
        text = report.decisions_json(result)
        self.assertEqual(text.count('"hold"'), 1)
```

Also add this helper near the top of `tests/test_report.py`, after the imports:

```python
from boring_alpha.domain import BacktestResult


def _result_with_decisions(*decisions: SignalSnapshot) -> BacktestResult:
    return BacktestResult(
        name="P",
        initial_equity=1.0,
        equity_curve=(),
        fills=(),
        decisions=tuple(decisions),
    )
```

(`SignalSnapshot` must be imported before this helper; move the `from boring_alpha.domain import SignalSnapshot` line up with the other imports.)

- [ ] **Step 3: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_backtest.py tests/test_report.py -q -k "Hold or DecisionRecord"`
Expected: FAIL — `TypeError: SignalSnapshot.__init__() got an unexpected keyword argument 'hold'` and `ImportError: cannot import name 'snapshot_record'`.

- [ ] **Step 4: Add the field**

In `src/boring_alpha/domain.py`, change `SignalSnapshot` to:

```python
@dataclass(frozen=True, slots=True)
class SignalSnapshot:
    as_of: date
    target_weights: dict[str, float]
    asset_returns: dict[str, float]
    cash_return: float
    name: str
    # "Keep the current allocation." The engine treats a hold on an empty book
    # as a normal rebalance to `target_weights`, because there is nothing to
    # keep; otherwise it records the decision and places no orders.
    hold: bool = False
```

- [ ] **Step 5: Add the engine branch**

In `src/boring_alpha/backtest/engine.py`, inside `Backtester.run`, replace the block that begins `if pending is not None:` and ends `pending = None` with:

```python
            if pending is not None:
                if pending.hold and fills:
                    # Nothing has ever been bought while `fills` is empty, so a
                    # hold there has no allocation to keep and falls through to
                    # a normal rebalance. Once something is held, a hold is
                    # exactly that: the decision is recorded and no order is
                    # planned, so the allocation drifts until the next
                    # non-hold signal.
                    decisions.append(pending)
                    pending = None
                else:
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

Also extend the `SignalPolicy` protocol docstring in the same file with one sentence: `A snapshot with hold=True asks the engine to keep the current allocation; see SignalSnapshot.`

- [ ] **Step 6: Add the serializer**

In `src/boring_alpha/report.py`, add after `json_text`:

```python
def snapshot_record(snapshot: SignalSnapshot) -> dict[str, Any]:
    """A decision as written to artifacts.

    `hold` appears only when set. Decisions files written before the field
    existed are therefore reproduced byte for byte, and a reader sees the key
    only where it means something.
    """

    record = asdict(snapshot)
    if not record.get("hold"):
        record.pop("hold", None)
    return record
```

Add `SignalSnapshot` to the `from boring_alpha.domain import ...` line. Then change `decisions_json` to:

```python
def decisions_json(result: BacktestResult) -> str:
    return json_text([snapshot_record(snapshot) for snapshot in result.decisions])
```

and in `write_report` change `decisions = [asdict(snapshot) for snapshot in strategy.decisions]` to `decisions = [snapshot_record(snapshot) for snapshot in strategy.decisions]`.

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_backtest.py tests/test_report.py -q`
Expected: all pass, including the three `HoldTests` and three `DecisionRecordTests`.

- [ ] **Step 8: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `279 passed`.

```bash
git add src/boring_alpha/domain.py src/boring_alpha/backtest/engine.py src/boring_alpha/report.py tests/test_backtest.py tests/test_report.py
git commit -m "Let a signal hold the current allocation

A snapshot may set hold=True. On an empty book the engine rebalances to
the snapshot's targets, since there is nothing to keep; afterwards it
records the decision and places no orders. The decisions writer omits a
false hold, so every existing decisions file is reproduced byte for byte.
Needed by an annually rebalanced benchmark.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Fetcher v2 — distributions and split records

The chart payload the fetcher already requests carries dividend and split events; today it discards them. v2 writes `distributions_daily.csv` (unadjusted close and cash dividend per share, aligned row-for-row with the price file) and records splits in the manifest. Verified against the endpoint on 2026-09-04: `close` and `dividend` are already split-adjusted and consistent with the adjusted series, so no split arithmetic is needed anywhere.

**Files:**
- Modify: `tools/fetch_market_data.py`
- Test: `tests/test_fetcher.py`

**Interfaces:**
- Produces: `fetcher.distribution_rows_from_chart(result: dict, today: date) -> list[tuple[date, float, float]]` (date, unadjusted close, dividend); `fetcher.splits_from_chart(result: dict) -> list[dict[str, str]]` (`{"date": iso, "ratio": "3:1"}`); `fetcher.fetch_chart(symbol) -> dict`; `fetcher.write_snapshot(out, price_rows, cash_rows, distribution_rows, coverage, splits) -> Path`; `fetcher.METHODOLOGY == "yahoo-adjusted-v2+dgs3mo-v1"`; snapshot manifest keys `splits`, `distribution_rows`, `distribution_source`, `distribution_units`.
- Task 4 reads the file and the manifest's `splits`.

- [ ] **Step 1: Extend the test chart builder and write the failing tests**

In `tests/test_fetcher.py`, replace the `_chart` helper with:

```python
def _chart(stamps, opens, closes, adjcloses, offset=0, dividends=(), splits=()):
    chart = {
        "meta": {"gmtoffset": offset},
        "timestamp": list(stamps),
        "indicators": {
            "quote": [{"open": list(opens), "close": list(closes)}],
            "adjclose": [{"adjclose": list(adjcloses)}],
        },
    }
    events = {}
    if dividends:
        events["dividends"] = {
            str(stamp): {"amount": amount, "date": stamp} for stamp, amount in dividends
        }
    if splits:
        events["splits"] = {
            str(stamp): {
                "date": stamp,
                "numerator": numerator,
                "denominator": denominator,
                "splitRatio": f"{numerator}:{denominator}",
            }
            for stamp, numerator, denominator in splits
        }
    if events:
        chart["events"] = events
    return chart
```

Append these tests:

```python
class DistributionTests(unittest.TestCase):
    """Distributions must line up with the price rows, or the overlay taxes the wrong shares."""

    def test_rows_align_with_price_rows_and_carry_the_unadjusted_close(self) -> None:
        chart = _chart(
            [DAY1, DAY2], [100.0, 101.0], [110.0, 111.0], [55.0, 111.0],
            dividends=[(DAY2, 0.75)],
        )
        prices = fetcher.rows_from_chart(chart, date(2030, 1, 1))
        rows = fetcher.distribution_rows_from_chart(chart, date(2030, 1, 1))
        self.assertEqual([row[0] for row in rows], [row[0] for row in prices])
        self.assertEqual([row[1] for row in rows], [110.0, 111.0])
        self.assertEqual([row[2] for row in rows], [0.0, 0.75])

    def test_a_session_dropped_from_prices_is_dropped_from_distributions_too(self) -> None:
        chart = _chart([DAY1, DAY2], [1.0, None], [1.0, 2.0], [1.0, 2.0])
        rows = fetcher.distribution_rows_from_chart(chart, date(2030, 1, 1))
        self.assertEqual([row[0] for row in rows], [date(2023, 11, 14)])

    def test_a_dividend_on_no_complete_session_is_an_error(self) -> None:
        chart = _chart([DAY1], [1.0], [1.0], [1.0], dividends=[(DAY2, 0.5)])
        with self.assertRaisesRegex(ValueError, "no complete session"):
            fetcher.distribution_rows_from_chart(chart, date(2030, 1, 1))

    def test_a_dividend_dated_today_or_later_is_ignored(self) -> None:
        chart = _chart([DAY1, DAY2], [1.0, 2.0], [1.0, 2.0], [1.0, 2.0], dividends=[(DAY2, 0.5)])
        rows = fetcher.distribution_rows_from_chart(chart, date(2023, 11, 15))
        self.assertEqual(rows, [(date(2023, 11, 14), 1.0, 0.0)])

    def test_a_negative_dividend_is_an_error(self) -> None:
        chart = _chart([DAY1], [1.0], [1.0], [1.0], dividends=[(DAY1, -0.5)])
        with self.assertRaisesRegex(ValueError, "invalid dividend"):
            fetcher.distribution_rows_from_chart(chart, date(2030, 1, 1))

    def test_splits_are_reported_with_their_ratio_in_date_order(self) -> None:
        chart = _chart([DAY1], [1.0], [1.0], [1.0], splits=[(DAY2, 3, 1), (DAY1, 2, 1)])
        self.assertEqual(
            fetcher.splits_from_chart(chart),
            [{"date": "2023-11-14", "ratio": "2:1"}, {"date": "2023-11-15", "ratio": "3:1"}],
        )

    def test_no_events_means_no_splits_and_zero_dividends(self) -> None:
        chart = _chart([DAY1], [1.0], [1.0], [1.0])
        self.assertEqual(fetcher.splits_from_chart(chart), [])
        self.assertEqual(fetcher.distribution_rows_from_chart(chart, date(2030, 1, 1)), [(date(2023, 11, 14), 1.0, 0.0)])

    def test_the_methodology_identifier_names_v2(self) -> None:
        self.assertEqual(fetcher.METHODOLOGY, "yahoo-adjusted-v2+dgs3mo-v1")
```

Then update `SnapshotTests`: add two class constants and change `_write`, and add one test:

```python
    DISTRIBUTIONS = [["date", "symbol", "close", "dividend"], ["2024-01-02", "A", "1", "0"]]
    SPLITS = {"A": [{"date": "2005-06-09", "ratio": "2:1"}]}

    def _write(self, out):
        return fetcher.write_snapshot(
            out, self.PRICES, self.CASH, self.DISTRIBUTIONS, self.COVERAGE, self.SPLITS
        )

    def test_a_snapshot_holds_the_distributions_file_and_records_splits(self) -> None:
        import json, tempfile

        snapshot = self._write(Path(tempfile.mkdtemp()))
        self.assertTrue((snapshot / "distributions_daily.csv").is_file())
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["splits"], self.SPLITS)
        self.assertEqual(manifest["distribution_rows"], 1)
        self.assertIn("split-adjusted", manifest["distribution_units"])
```

Also change the existing `test_a_snapshot_holds_both_files_and_a_manifest` loop to include `"distributions_daily.csv"` in the tuple of expected names.

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_fetcher.py -q`
Expected: FAIL — `AttributeError: module 'fetch_market_data' has no attribute 'distribution_rows_from_chart'`, and `SnapshotTests` fail with a `TypeError` about positional arguments.

- [ ] **Step 3: Implement the parsing functions**

In `tools/fetch_market_data.py`:

Change `METHODOLOGY = "yahoo-adjusted-v1+dgs3mo-v1"` to `METHODOLOGY = "yahoo-adjusted-v2+dgs3mo-v1"`.

Replace `rows_from_chart` with these four functions:

```python
def _local_date(stamp: int, offset_seconds: int) -> date:
    """The exchange's local calendar date for a timestamp, not UTC's."""

    return (datetime.fromtimestamp(stamp, tz=timezone.utc) + timedelta(seconds=offset_seconds)).date()


def _sessions(result: dict, today: date):
    """(day, open, close, adjclose) for every complete, usable session.

    One filter for prices and distributions, so the two files are aligned
    row for row by construction rather than by luck.
    """

    offset = result["meta"].get("gmtoffset", 0)
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    for index, stamp in enumerate(result["timestamp"]):
        open_, close, adjclose = quote["open"][index], quote["close"][index], adjusted[index]
        if None in (open_, close, adjclose):
            continue
        if not all(math.isfinite(v) for v in (open_, close, adjclose)):
            continue
        if close <= 0.0 or open_ <= 0.0 or adjclose <= 0.0:
            continue
        day = _local_date(stamp, offset)
        if day >= today:
            continue
        yield day, open_, close, adjclose


def rows_from_chart(result: dict, today: date) -> list[tuple[date, float, float]]:
    """Adjusted (date, tr_open, tr_close) rows from one parsed chart response.

    Pure, so the adjustment and the incomplete-session rule can be tested
    without a network call.
    """

    return [
        (day, open_ * (adjclose / close), adjclose)
        for day, open_, close, adjclose in _sessions(result, today)
    ]


def distribution_rows_from_chart(result: dict, today: date) -> list[tuple[date, float, float]]:
    """(date, unadjusted close, dividend per share) for every session kept by rows_from_chart.

    The dividend is the cash amount on its ex-date and 0.0 otherwise. Amounts
    and closes are in the endpoint's split-adjusted units, which match each
    other and the adjusted series (checked against EEM's 2008 split). A
    dividend dated on a session that was dropped as incomplete is an error:
    it would otherwise vanish silently. Dividends dated today or later are
    declared, not yet paid, and are ignored.
    """

    offset = result["meta"].get("gmtoffset", 0)
    dividends: dict[date, float] = {}
    for event in result.get("events", {}).get("dividends", {}).values():
        amount = float(event["amount"])
        if not math.isfinite(amount) or amount < 0.0:
            raise ValueError(f"invalid dividend event: {event!r}")
        day = _local_date(int(event["date"]), offset)
        dividends[day] = dividends.get(day, 0.0) + amount
    rows = [
        (day, close, dividends.pop(day, 0.0))
        for day, _, close, _ in _sessions(result, today)
    ]
    unmatched = sorted(day for day in dividends if day < today)
    if unmatched:
        raise ValueError(
            f"dividend ex-dates fall on no complete session: {[d.isoformat() for d in unmatched]}"
        )
    return rows


def splits_from_chart(result: dict) -> list[dict[str, str]]:
    """Split events in date order, as recorded in the snapshot manifest.

    Nothing downstream adjusts for these — the endpoint's closes and
    dividends are already split-adjusted — but a reader must be able to see
    that a split happened.
    """

    offset = result["meta"].get("gmtoffset", 0)
    events = sorted(
        result.get("events", {}).get("splits", {}).values(), key=lambda event: int(event["date"])
    )
    return [
        {"date": _local_date(int(event["date"]), offset).isoformat(), "ratio": str(event.get("splitRatio", ""))}
        for event in events
    ]
```

Replace `fetch_prices` with:

```python
def fetch_chart(symbol: str) -> dict:
    """The parsed chart result for one symbol: quotes, adjusted closes and events."""

    payload = json.loads(_get(CHART_URL.format(symbol=symbol)))
    return payload["chart"]["result"][0]
```

Run `grep -rn "fetch_prices" tools tests src` and confirm no other caller remains.

- [ ] **Step 4: Implement the snapshot and main changes**

Replace `write_snapshot` with:

```python
def write_snapshot(
    out: Path,
    price_rows: list[list[str]],
    cash_rows: list[list[str]],
    distribution_rows: list[list[str]],
    coverage: dict[str, dict[str, str]],
    splits: dict[str, list[dict[str, str]]],
) -> Path:
    """Write one snapshot directory, manifest last, then repoint `current`.

    The manifest is the completion marker: its absence means the download did
    not finish, so prices, cash and distributions can never be read as a
    mismatched set.
    """

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = out / "snapshots" / stamp
    snapshot.mkdir(parents=True, exist_ok=False)

    _write_csv(snapshot / "market_daily.csv", price_rows)
    _write_csv(snapshot / "cash_daily.csv", cash_rows)
    _write_csv(snapshot / "distributions_daily.csv", distribution_rows)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "methodology": METHODOLOGY,
        "price_source": "yahoo-finance-chart-v8",
        "price_adjustment": "tr_open = open * adjclose / close; tr_close = adjclose",
        "distribution_source": "yahoo-finance-chart-v8 events=div",
        "distribution_units": (
            "split-adjusted, matching close; dividend is cash per share on its "
            "ex-date and 0 otherwise"
        ),
        "cash_series": FRED_SERIES,
        "cash_basis": "investment (constant maturity), not bank discount",
        "cash_convention": "(1 + prior_session_rate / 100) ** (1 / 252)",
        "sessions_per_year": SESSIONS_PER_YEAR,
        "price_rows": len(price_rows) - 1,
        "cash_rows": len(cash_rows) - 1,
        "distribution_rows": len(distribution_rows) - 1,
        "coverage": coverage,
        "splits": splits,
    }
    # Last: everything above must already be on disk for this to mean anything.
    (snapshot / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    current = out / "current"
    pointer = out / "current.tmp"
    if pointer.is_symlink() or pointer.exists():
        pointer.unlink()
    pointer.symlink_to(Path("snapshots") / stamp, target_is_directory=True)
    pointer.replace(current)
    return snapshot
```

Replace `main` with:

```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data"), help="output directory")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    bars: list[tuple[date, str, float, float]] = []
    distributions: list[tuple[date, str, float, float]] = []
    coverage: dict[str, dict[str, str]] = {}
    splits: dict[str, list[dict[str, str]]] = {}
    for symbol in SYMBOLS:
        try:
            result = fetch_chart(symbol)
            today = exchange_today(result["meta"].get("gmtoffset", 0))
            rows = rows_from_chart(result, today)
            distribution_rows = distribution_rows_from_chart(result, today)
            splits[symbol] = splits_from_chart(result)
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
            print(f"error: {symbol}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        if not rows:
            print(f"error: {symbol}: no usable rows returned", file=sys.stderr)
            return 2
        paid = sum(1 for _, _, dividend in distribution_rows if dividend > 0.0)
        print(
            f"{symbol:4} {rows[0][0]} .. {rows[-1][0]}  {len(rows):5} rows  "
            f"{paid:4} ex-dates  {len(splits[symbol])} splits"
        )
        coverage[symbol] = {
            "first": str(rows[0][0]), "last": str(rows[-1][0]), "rows": str(len(rows))
        }
        bars.extend((day, symbol, tr_open, tr_close) for day, tr_open, tr_close in rows)
        distributions.extend(
            (day, symbol, close, dividend) for day, close, dividend in distribution_rows
        )

    # Everything is fetched before anything is written, so a failure here cannot
    # leave fresh prices paired with a stale cash file.
    try:
        rates = fetch_cash_rates()
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        print(f"error: {FRED_SERIES}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not rates:
        print(f"error: {FRED_SERIES}: no usable observations", file=sys.stderr)
        return 2
    print(f"{FRED_SERIES} {rates[0][0]} .. {rates[-1][0]}  {len(rates):5} observations")

    bars.sort(key=lambda row: (row[0], row[1]))
    distributions.sort(key=lambda row: (row[0], row[1]))
    sessions = sorted({day for day, _, _, _ in bars})
    factors = cash_factors(sessions, rates)

    price_rows = [["date", "symbol", "tr_open", "tr_close"]]
    price_rows += [
        [str(day), symbol, f"{tr_open:.10f}", f"{tr_close:.10f}"]
        for day, symbol, tr_open, tr_close in bars
    ]
    cash_rows = [["date", "cash_factor"]]
    cash_rows += [[str(s), f"{factors[s]:.12f}"] for s in sessions]
    distribution_rows_out = [["date", "symbol", "close", "dividend"]]
    distribution_rows_out += [
        [str(day), symbol, f"{close:.10f}", f"{dividend:.10f}"]
        for day, symbol, close, dividend in distributions
    ]

    snapshot = write_snapshot(
        args.out, price_rows, cash_rows, distribution_rows_out, coverage, splits
    )
    print(f"\nwrote {snapshot}")
    print(f"  {len(bars)} bars through {sessions[-1]}, {len(sessions)} cash sessions")
    print(f"  {len(distributions)} distribution rows")
    for symbol, records in splits.items():
        if records:
            print(f"  {symbol} splits: " + ", ".join(f"{r['date']} {r['ratio']}" for r in records))
    print(f"  methodology: {METHODOLOGY}")
    print(f"  {args.out / 'current'} -> snapshots/{snapshot.name}")
    return 0
```

Finally, add this paragraph to the module docstring, after the "Adjustment:" paragraph:

```
Distributions: the same payload carries dividend and split events. v2 writes
`distributions_daily.csv` with the UNADJUSTED close and the cash dividend per
share on its ex-date (0 otherwise), one row per session and symbol, aligned
with the price file. The tax overlay uses these to separate the income the
adjusted series silently reinvests from the capital gain it reports; nothing
else reads them. Checked on 2026-09-04 against EEM's 3:1 split of 2008-07-24:
the endpoint's close does not jump across the split and the preceding
dividend is one third of the pre-split per-share amount, so close and
dividend are both already split-adjusted and consistent with the adjusted
series. Split events are recorded in the manifest so a reader can see them;
no arithmetic is applied to them.
```

- [ ] **Step 5: Run the fetcher tests**

Run: `.venv/bin/python -m pytest tests/test_fetcher.py -q`
Expected: all pass (the pre-existing adjustment, incomplete-session, bad-row, cash-factor, provenance and snapshot tests, plus the eight new `DistributionTests` and the new snapshot test).

- [ ] **Step 6: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `288 passed`.

```bash
git add tools/fetch_market_data.py tests/test_fetcher.py
git commit -m "Archive distributions and split records in a v2 snapshot

The chart payload already carries dividend and split events; the fetcher
now writes distributions_daily.csv (unadjusted close and cash dividend per
share, aligned row for row with the price file) and records splits in the
manifest. Both are in the endpoint's split-adjusted units, verified against
EEM's 2008 split. Methodology becomes yahoo-adjusted-v2+dgs3mo-v1; prices
and cash are unchanged.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Distributions reader

The only code that reads `distributions_daily.csv`. It enforces the column set, positive closes, finite non-negative dividends, requires split records from either a snapshot manifest or a sweep's embedded block, records the file's SHA-256, and can be truncated and checked for coverage against a `MarketData`.

**Files:**
- Create: `src/boring_alpha/data/distributions.py`
- Test: `tests/test_distributions.py`

**Interfaces:**
- Consumes: `MarketData.dates`, `MarketData.by_date`.
- Produces: `DistributionTable` with `.dates`, `.symbols`, `.symbol_dates`, `.splits`, `.sha256`, `.source`, `.close(day, symbol) -> float`, `.dividend(day, symbol) -> float`, `.ex_dates(symbol) -> tuple[date, ...]`, `.through(end) -> DistributionTable`, `.require_coverage(data, symbols) -> None`; `load_distributions(path, *, manifest_path=None, manifest_block=None) -> DistributionTable`; `split_records(manifest: dict) -> dict[str, list[dict[str, str]]]`. Plan 2's overlay consumes all of these.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_distributions.py`:

```python
"""The distributions file is read by the tax overlay alone; it must be strict."""

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.data.distributions import DistributionTable, load_distributions, split_records
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar

CSV = """date,symbol,close,dividend
2024-01-02,A,100.0,0.0
2024-01-02,B,50.0,0.0
2024-01-03,A,101.0,0.5
2024-01-03,B,51.0,0.0
2024-01-04,A,102.0,0.0
2024-01-04,B,52.0,0.25
"""
MANIFEST = {"splits": {"A": [{"date": "2005-06-09", "ratio": "2:1"}], "B": []}}


def _write(root: Path, csv_text: str = CSV, manifest: dict | None = MANIFEST) -> tuple[Path, Path | None]:
    csv_path = root / "distributions_daily.csv"
    csv_path.write_text(csv_text, encoding="utf-8")
    manifest_path = None
    if manifest is not None:
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return csv_path, manifest_path


class ReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_loads_close_and_dividend_by_session_and_symbol(self) -> None:
        csv_path, manifest_path = _write(self.root)
        table = load_distributions(csv_path, manifest_path=manifest_path)
        self.assertEqual(table.close(date(2024, 1, 3), "A"), 101.0)
        self.assertEqual(table.dividend(date(2024, 1, 3), "A"), 0.5)
        self.assertEqual(table.dividend(date(2024, 1, 3), "B"), 0.0)
        self.assertEqual(table.symbols, ("A", "B"))
        self.assertEqual(table.dates, (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)))
        self.assertEqual(table.splits, MANIFEST["splits"])
        self.assertEqual(len(table.sha256), 64)

    def test_ex_dates_list_only_sessions_with_a_dividend(self) -> None:
        csv_path, manifest_path = _write(self.root)
        table = load_distributions(csv_path, manifest_path=manifest_path)
        self.assertEqual(table.ex_dates("A"), (date(2024, 1, 3),))
        self.assertEqual(table.ex_dates("B"), (date(2024, 1, 4),))
        self.assertEqual(table.ex_dates("Z"), ())

    def test_exact_columns_are_required(self) -> None:
        csv_path, manifest_path = _write(self.root, "date,symbol,close\n2024-01-02,A,1\n")
        with self.assertRaisesRegex(ValueError, "columns must be exactly"):
            load_distributions(csv_path, manifest_path=manifest_path)

    def test_a_negative_dividend_is_refused(self) -> None:
        csv_path, manifest_path = _write(
            self.root, "date,symbol,close,dividend\n2024-01-02,A,1,-0.1\n"
        )
        with self.assertRaisesRegex(ValueError, "negative dividend"):
            load_distributions(csv_path, manifest_path=manifest_path)

    def test_a_non_positive_close_is_refused(self) -> None:
        csv_path, manifest_path = _write(self.root, "date,symbol,close,dividend\n2024-01-02,A,0,0\n")
        with self.assertRaisesRegex(ValueError, "non-positive close"):
            load_distributions(csv_path, manifest_path=manifest_path)

    def test_a_duplicate_row_is_refused(self) -> None:
        csv_path, manifest_path = _write(
            self.root, "date,symbol,close,dividend\n2024-01-02,A,1,0\n2024-01-02,A,1,0\n"
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_distributions(csv_path, manifest_path=manifest_path)

    def test_a_missing_lookup_is_a_value_error(self) -> None:
        csv_path, manifest_path = _write(self.root)
        table = load_distributions(csv_path, manifest_path=manifest_path)
        with self.assertRaisesRegex(ValueError, "no distribution row"):
            table.close(date(2024, 1, 5), "A")


class SplitRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_split_records_may_come_from_an_embedded_block(self) -> None:
        csv_path, _ = _write(self.root, manifest=None)
        table = load_distributions(csv_path, manifest_block=MANIFEST)
        self.assertEqual(table.splits, MANIFEST["splits"])

    def test_a_manifest_without_splits_is_refused(self) -> None:
        csv_path, manifest_path = _write(self.root, manifest={"methodology": "x"})
        with self.assertRaisesRegex(ValueError, "no 'splits' key"):
            load_distributions(csv_path, manifest_path=manifest_path)
        with self.assertRaisesRegex(ValueError, "no 'splits' key"):
            split_records({"methodology": "x"})

    def test_exactly_one_manifest_source_is_required(self) -> None:
        csv_path, manifest_path = _write(self.root)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            load_distributions(csv_path)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            load_distributions(csv_path, manifest_path=manifest_path, manifest_block=MANIFEST)


class TruncationAndCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp())
        csv_path, manifest_path = _write(root)
        self.table = load_distributions(csv_path, manifest_path=manifest_path)

    def _market(self, days) -> MarketData:
        bars = [PriceBar(day, symbol, 1.0, 1.0) for day in days for symbol in ("A", "B")]
        return MarketData(bars, {day: 1.0 for day in days}, source="test")

    def test_through_keeps_sessions_up_to_the_end_and_the_file_hash(self) -> None:
        truncated = self.table.through(date(2024, 1, 3))
        self.assertEqual(truncated.dates, (date(2024, 1, 2), date(2024, 1, 3)))
        self.assertEqual(truncated.sha256, self.table.sha256)
        self.assertEqual(truncated.splits, self.table.splits)
        self.assertIn("truncated=2024-01-03", truncated.source)
        with self.assertRaisesRegex(ValueError, "leaves no rows"):
            self.table.through(date(2023, 1, 1))

    def test_coverage_passes_when_every_priced_session_has_a_row(self) -> None:
        self.table.require_coverage(self._market([date(2024, 1, 2), date(2024, 1, 3)]), ("A", "B"))

    def test_coverage_fails_on_a_priced_session_without_a_row(self) -> None:
        with self.assertRaisesRegex(ValueError, "no distribution row for A on 2024-01-05"):
            self.table.require_coverage(self._market([date(2024, 1, 5)]), ("A", "B"))

    def test_coverage_ignores_symbols_not_asked_about(self) -> None:
        bars = [PriceBar(date(2024, 1, 2), "C", 1.0, 1.0)]
        data = MarketData(bars, {date(2024, 1, 2): 1.0}, source="test")
        self.table.require_coverage(data, ("A", "B"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_distributions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'boring_alpha.data.distributions'`.

- [ ] **Step 3: Implement the reader**

Create `src/boring_alpha/data/distributions.py`:

```python
"""Distributions for the tax overlay: unadjusted closes and cash dividends per share.

The engine never sees this table. It exists so that after-tax accounting can
separate the income the adjusted price series silently reinvests from the
capital gain it reports, and it is read only by the tax overlay.

Units are split-adjusted, matching the `close` column and the adjusted series
(see tools/fetch_market_data.py). A split is not a taxable event, so an
account kept in split-adjusted shares is equivalent to one kept in
certificate shares; the split records are required anyway so that a reader
can see them.
"""

from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Iterable

from boring_alpha.data.market import MarketData

REQUIRED_COLUMNS = frozenset({"date", "symbol", "close", "dividend"})

Row = tuple[date, str, float, float]


class DistributionTable:
    """Unadjusted close and cash dividend per share, by session and symbol."""

    def __init__(
        self,
        rows: Iterable[Row],
        *,
        splits: dict[str, list[dict[str, str]]],
        sha256: str,
        source: str,
    ) -> None:
        closes: dict[tuple[date, str], float] = {}
        dividends: dict[tuple[date, str], float] = {}
        symbol_dates: dict[str, list[date]] = defaultdict(list)
        for day, symbol, close, dividend in rows:
            if not (math.isfinite(close) and math.isfinite(dividend)):
                raise ValueError(f"distribution row for {symbol} on {day} is not finite")
            if close <= 0.0:
                raise ValueError(f"non-positive close for {symbol} on {day}")
            if dividend < 0.0:
                raise ValueError(f"negative dividend for {symbol} on {day}")
            key = (day, symbol)
            if key in closes:
                raise ValueError(f"duplicate distribution row for {symbol} on {day}")
            closes[key] = close
            dividends[key] = dividend
            symbol_dates[symbol].append(day)
        if not closes:
            raise ValueError("distribution table contains no rows")
        self._closes = closes
        self._dividends = dividends
        self.symbol_dates = {
            symbol: tuple(sorted(days)) for symbol, days in symbol_dates.items()
        }
        self.dates = tuple(sorted({day for day, _ in closes}))
        self.splits = {symbol: list(records) for symbol, records in splits.items()}
        self.sha256 = sha256
        self.source = source

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.symbol_dates))

    def close(self, day: date, symbol: str) -> float:
        try:
            return self._closes[(day, symbol)]
        except KeyError as exc:
            raise ValueError(f"no distribution row for {symbol} on {day}") from exc

    def dividend(self, day: date, symbol: str) -> float:
        try:
            return self._dividends[(day, symbol)]
        except KeyError as exc:
            raise ValueError(f"no distribution row for {symbol} on {day}") from exc

    def ex_dates(self, symbol: str) -> tuple[date, ...]:
        """Sessions on which the symbol paid a dividend."""

        return tuple(
            day
            for day in self.symbol_dates.get(symbol, ())
            if self._dividends[(day, symbol)] > 0.0
        )

    def through(self, end: date) -> "DistributionTable":
        """A copy holding only sessions on or before `end`, matching MarketData.through."""

        rows = [
            (day, symbol, self._closes[(day, symbol)], self._dividends[(day, symbol)])
            for day, symbol in sorted(self._closes)
            if day <= end
        ]
        if not rows:
            raise ValueError(f"truncating distributions at {end} leaves no rows")
        return DistributionTable(
            rows, splits=self.splits, sha256=self.sha256, source=f"{self.source}:truncated={end}"
        )

    def require_coverage(self, data: MarketData, symbols: tuple[str, ...]) -> None:
        """Every priced session for `symbols` must have a distribution row."""

        for day in data.dates:
            bars = data.by_date[day]
            for symbol in symbols:
                if symbol in bars and (day, symbol) not in self._closes:
                    raise ValueError(
                        f"no distribution row for {symbol} on {day}; the distributions "
                        "file must cover every priced session"
                    )


def split_records(manifest: dict) -> dict[str, list[dict[str, str]]]:
    """Split records from a v2 snapshot manifest or a sweep's embedded block."""

    if "splits" not in manifest:
        raise ValueError(
            "the distributions manifest records no 'splits' key; a v2 snapshot "
            "manifest or a sweep's embedded distributions_manifest block is required"
        )
    return {symbol: list(records) for symbol, records in manifest["splits"].items()}


def load_distributions(
    path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    manifest_block: dict | None = None,
) -> DistributionTable:
    """Read `distributions_daily.csv` and the split records that belong with it."""

    if (manifest_path is None) == (manifest_block is None):
        raise ValueError("exactly one of manifest_path or manifest_block is required")
    manifest = (
        manifest_block
        if manifest_block is not None
        else json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    )
    splits = split_records(manifest)

    raw = Path(path).read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if set(reader.fieldnames or ()) != REQUIRED_COLUMNS:
        raise ValueError(
            f"distribution CSV columns must be exactly {sorted(REQUIRED_COLUMNS)}, "
            f"got {reader.fieldnames}"
        )
    rows: list[Row] = []
    for row_number, row in enumerate(reader, start=2):
        try:
            rows.append(
                (
                    date.fromisoformat(row["date"]),
                    row["symbol"].strip().upper(),
                    float(row["close"]),
                    float(row["dividend"]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid distribution row {row_number}: {row}") from exc
    return DistributionTable(
        rows,
        splits=splits,
        sha256=hashlib.sha256(raw).hexdigest(),
        source=f"csv:{Path(path).name}",
    )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_distributions.py -q`
Expected: `14 passed`.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `302 passed`.

```bash
git add src/boring_alpha/data/distributions.py tests/test_distributions.py
git commit -m "Add a strict reader for the distributions file

Read only by the tax overlay: unadjusted close and cash dividend per share
by session and symbol, with the split records that belong beside them,
from a snapshot manifest or a sweep's embedded block. Records the file
hash, truncates like MarketData, and checks coverage against a dataset.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: The `[benchmark]` configuration table

Optional. When present it names the gating benchmark's target exposure and rebalancing schedule and enters the strategy spec hash; when absent nothing changes, and BA-001's hashes are proven unchanged against the real value.

**Files:**
- Modify: `src/boring_alpha/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `BenchmarkConfig(exposure: float, rebalance: str)`; `AppConfig.benchmark: BenchmarkConfig | None`; `REBALANCE_SCHEDULES = ("annual", "monthly")`. Tasks 6 and 7 consume `config.benchmark`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
BENCHMARK = VALID + """
[benchmark]
exposure = 0.6
rebalance = "annual"
"""

BA001_SPEC_HASH = "595a25e57ed68d4e863eeb69b40248345840b809b0f213609ddd14b4cd952110"


class BenchmarkConfigTests(unittest.TestCase):
    def test_an_absent_table_means_no_override(self) -> None:
        config, _ = _load(VALID)
        self.assertIsNone(config.benchmark)

    def test_the_table_is_parsed(self) -> None:
        config, _ = _load(BENCHMARK)
        assert config.benchmark is not None
        self.assertAlmostEqual(config.benchmark.exposure, 0.6)
        self.assertEqual(config.benchmark.rebalance, "annual")

    def test_the_table_enters_the_spec_hash_only_when_present(self) -> None:
        without, _ = _load(VALID)
        annual, _ = _load(BENCHMARK)
        monthly, _ = _load(BENCHMARK.replace('"annual"', '"monthly"'))
        half, _ = _load(BENCHMARK.replace("0.6", "0.5"))
        hashes = {without.strategy_spec_sha256, annual.strategy_spec_sha256,
                  monthly.strategy_spec_sha256, half.strategy_spec_sha256}
        self.assertEqual(len(hashes), 4)

    def test_ba_001_development_spec_hash_is_unchanged(self) -> None:
        # The value recorded in both real BA-001 sweeps. Adding an optional table
        # must not move it, or the archived record would no longer describe the
        # checked-in configuration.
        config = load_config(REPO_ROOT / "configs" / "ba_001_development.toml")
        self.assertEqual(config.strategy_spec_sha256, BA001_SPEC_HASH)

    def test_exposure_outside_the_unit_interval_is_refused(self) -> None:
        for bad in ("0.0", "1.5", "-0.2"):
            with self.assertRaisesRegex(ValueError, "benchmark.exposure"):
                _load(BENCHMARK.replace("0.6", bad))

    def test_an_unknown_schedule_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "benchmark.rebalance"):
            _load(BENCHMARK.replace('"annual"', '"weekly"'))

    def test_an_incomplete_table_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "benchmark.rebalance is required"):
            _load(VALID + "\n[benchmark]\nexposure = 0.6\n")
        with self.assertRaisesRegex(ValueError, "benchmark.exposure is required"):
            _load(VALID + '\n[benchmark]\nrebalance = "annual"\n')

    def test_an_unknown_key_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown key"):
            _load(BENCHMARK + "band = 0.02\n")
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -q -k Benchmark`
Expected: FAIL — `AttributeError: 'AppConfig' object has no attribute 'benchmark'` for the first test and `ValueError: unknown table(s) in configuration: benchmark` for the rest. (`test_ba_001_development_spec_hash_is_unchanged` passes already; that is the point.)

- [ ] **Step 3: Implement**

In `src/boring_alpha/config.py`:

After `ExecutionConfig`, add:

```python
@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """The gating benchmark's target exposure and rebalancing schedule.

    Optional. When present, the strategy is judged against static equal-weight
    scaled to `exposure` with the remainder in cash, rebalanced on `rebalance`,
    instead of the fully invested monthly static allocation. Both values are
    part of what is being tested, so both enter the strategy spec hash.
    """

    exposure: float
    rebalance: str


REBALANCE_SCHEDULES = ("annual", "monthly")
```

In `AppConfig`, add the field `benchmark: BenchmarkConfig | None` immediately after `clusters: dict[str, tuple[str, ...]]`.

In `_SCHEMA`, add the entry `"benchmark": frozenset({"exposure", "rebalance"}),` after the `"report"` entry.

Change `_strategy_spec_hash` to take and include the benchmark:

```python
def _strategy_spec_hash(
    strategy: StrategyConfig,
    portfolio: PortfolioConfig,
    execution: ExecutionConfig,
    data: DataConfig,
    benchmark: BenchmarkConfig | None,
) -> str:
    """Fingerprint of what the strategy IS, independent of the window it ran over.

    Two sweeps may only be combined into a verdict if this matches. The
    evaluation window is deliberately excluded — development and validation
    differ in exactly that and nothing else. Symbols are sorted because
    reordering the universe does not change the strategy. The benchmark table
    is included only when present, so configurations written before it existed
    keep the hash their archived runs recorded.
    """

    spec: dict[str, object] = {
        "strategy_id": strategy.strategy_id,
        "symbols": sorted(strategy.symbols),
        "lookback_months": strategy.lookback_months,
        "sleeve_weight": strategy.sleeve_weight,
        "initial_cash": portfolio.initial_cash,
        "cost_bps": execution.cost_bps,
        "data_source": data.source,
        # How the inputs were built is part of what was run. The fetcher lives
        # outside code_fingerprint(), so a change of price adjustment or cash
        # series would otherwise be invisible to the run's identity.
        "data_methodology": data.methodology,
    }
    if benchmark is not None:
        spec["benchmark"] = {"exposure": benchmark.exposure, "rebalance": benchmark.rebalance}
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Add the loader, after `_load_clusters`:

```python
def _load_benchmark(raw: dict[str, object] | None) -> BenchmarkConfig | None:
    if raw is None:
        return None
    exposure = _finite(
        float(_require(raw, "benchmark", "exposure")), "benchmark.exposure"
    )
    if not 0.0 < exposure <= 1.0:
        raise ValueError(f"benchmark.exposure must be in (0, 1], got {exposure!r}")
    rebalance = str(_require(raw, "benchmark", "rebalance")).lower()
    if rebalance not in REBALANCE_SCHEDULES:
        raise ValueError(
            f"benchmark.rebalance must be one of {', '.join(REBALANCE_SCHEDULES)}, got {rebalance!r}"
        )
    return BenchmarkConfig(exposure, rebalance)
```

In `load_config`, before `_validate(...)`, add `benchmark = _load_benchmark(raw.get("benchmark"))`, and in the `AppConfig(...)` construction add `benchmark=benchmark,` after `clusters=...` and change the hash call to `_strategy_spec_hash(strategy, portfolio, execution, data, benchmark)`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: all pass, including the eight `BenchmarkConfigTests`.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `310 passed`.

```bash
git add src/boring_alpha/config.py tests/test_config.py
git commit -m "Add an optional benchmark table naming target exposure and schedule

When present, the gating benchmark is static equal-weight scaled to a
target exposure fixed in advance, rebalanced annually or monthly, and both
values enter the strategy spec hash. When absent nothing changes; the
checked-in BA-001 configuration still hashes to the value both real
sweeps recorded, and a test pins that.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: The target-exposure benchmark policy

A static allocation at a target exposure fixed in advance, on a declared schedule. On `annual` every month-end but December is a hold; the engine's rule from Task 2 makes the first execution establish the allocation whatever month the run starts in.

**Files:**
- Modify: `src/boring_alpha/signals/trend.py`, `src/boring_alpha/signals/__init__.py`
- Test: `tests/test_signals.py`, `tests/test_backtest.py`

**Interfaces:**
- Consumes: `ScaledAllocation`, `SignalSnapshot.hold`, `REBALANCE_SCHEDULES`.
- Produces: `TargetExposureAllocation(symbols, lookback_months, sleeve_weight, exposure, rebalance)`, `.name == f"Target-Exposure Benchmark ({exposure:.0%}, {rebalance})"`. Task 7 constructs it from `config.benchmark`.

- [ ] **Step 1: Write the failing policy tests**

Append to `tests/test_signals.py`:

```python
from boring_alpha.data.synthetic import generate_synthetic_market_data
from boring_alpha.signals.trend import TargetExposureAllocation


def _two_symbol_data(days: list[date]) -> MarketData:
    bars = [
        PriceBar(day, symbol, 100.0 + index, 100.0 + index)
        for index, day in enumerate(days)
        for symbol in ("A", "B")
    ]
    return MarketData(bars, {day: 1.0 for day in days}, source="test")


class TargetExposureTests(unittest.TestCase):
    DAYS = [date(2023, 11, 30), date(2023, 12, 29), date(2024, 11, 29), date(2024, 12, 31)]

    def test_weights_sum_to_the_target_exposure(self) -> None:
        policy = TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "annual")
        snapshot = policy.snapshot(_two_symbol_data(self.DAYS), date(2024, 12, 31))
        assert snapshot is not None
        self.assertAlmostEqual(sum(snapshot.target_weights.values()), 0.6)
        self.assertAlmostEqual(snapshot.target_weights["A"], 0.3)

    def test_annual_holds_except_at_the_december_month_end(self) -> None:
        policy = TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "annual")
        data = _two_symbol_data(self.DAYS)
        november = policy.snapshot(data, date(2024, 11, 29))
        december = policy.snapshot(data, date(2024, 12, 31))
        assert november is not None and december is not None
        self.assertTrue(november.hold)
        self.assertFalse(december.hold)
        # A hold still carries the targets: the engine uses them on an empty book.
        self.assertAlmostEqual(sum(november.target_weights.values()), 0.6)

    def test_monthly_never_holds(self) -> None:
        policy = TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "monthly")
        snapshot = policy.snapshot(_two_symbol_data(self.DAYS), date(2024, 11, 29))
        assert snapshot is not None
        self.assertFalse(snapshot.hold)

    def test_the_name_states_exposure_and_schedule(self) -> None:
        self.assertEqual(
            TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "annual").name,
            "Target-Exposure Benchmark (60%, annual)",
        )

    def test_an_unknown_schedule_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "rebalance"):
            TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "weekly")

    def test_insufficient_history_still_yields_no_signal(self) -> None:
        policy = TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "annual")
        self.assertIsNone(policy.snapshot(_two_symbol_data(self.DAYS), date(2023, 11, 30)))
```

- [ ] **Step 2: Write the failing engine-level tests**

Append to `tests/test_backtest.py`:

```python
from boring_alpha.signals.trend import TargetExposureAllocation


class AnnualBenchmarkTests(unittest.TestCase):
    """An annual benchmark enters on the first session and trades again each January."""

    SYMBOLS = ("A", "B", "C")

    def _fill_months(self, start: date) -> set[tuple[int, int]]:
        data = generate_synthetic_market_data(
            self.SYMBOLS, date(2019, 10, 1), date(2022, 12, 31), seed=11, annual_cash_rate=0.02
        )
        engine = Backtester(
            data, self.SYMBOLS, initial_cash=10_000.0, cost_bps=10.0,
            start=start, end=date(2022, 12, 31),
        )
        result = engine.run(TargetExposureAllocation(self.SYMBOLS, 12, 1.0 / 3.0, 0.6, "annual"))
        self.assertGreater(len(result.fills), 0)
        return {(fill.date.year, fill.date.month) for fill in result.fills}

    def test_a_january_start_trades_at_entry_and_each_following_january(self) -> None:
        self.assertEqual(self._fill_months(date(2021, 1, 1)), {(2021, 1), (2022, 1)})

    def test_a_mid_year_start_still_enters_on_its_first_session(self) -> None:
        self.assertEqual(self._fill_months(date(2021, 7, 1)), {(2021, 7), (2022, 1)})
```

(2021-01-01 and 2021-07-01 are weekdays, so the synthetic calendar has sessions on them and they are the first sessions of their months.)

- [ ] **Step 3: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_signals.py tests/test_backtest.py -q -k "TargetExposure or AnnualBenchmark"`
Expected: FAIL — `ImportError: cannot import name 'TargetExposureAllocation'`.

- [ ] **Step 4: Implement the policy**

In `src/boring_alpha/signals/trend.py`, add after `ScaledAllocation`:

```python
class TargetExposureAllocation(ScaledAllocation):
    """Static weights at a target exposure fixed in advance, on a declared schedule.

    Unlike the exposure-matched diagnostic, nothing about a strategy's realized
    exposure feeds this: the number and the schedule come from the charter. On
    an annual schedule every month-end but December is a hold, so the
    allocation drifts between Januaries the way a passive holder's would. The
    engine treats a hold on an empty book as a normal rebalance, so a run that
    starts mid-year still enters on its first session.
    """

    SCHEDULES = ("annual", "monthly")

    def __init__(
        self,
        symbols: tuple[str, ...],
        lookback_months: int,
        sleeve_weight: float,
        exposure: float,
        rebalance: str,
    ) -> None:
        if rebalance not in self.SCHEDULES:
            raise ValueError(
                f"rebalance must be one of {', '.join(self.SCHEDULES)}, got {rebalance!r}"
            )
        super().__init__(symbols, lookback_months, sleeve_weight, exposure)
        self.rebalance = rebalance
        self.name = f"Target-Exposure Benchmark ({self.exposure:.0%}, {rebalance})"

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot | None:
        snapshot = super().snapshot(data, as_of)
        if snapshot is None:
            return None
        hold = self.rebalance == "annual" and as_of.month != 12
        return replace(snapshot, name=self.name, hold=hold)
```

In `src/boring_alpha/signals/__init__.py`, add `TargetExposureAllocation` to both the import list and `__all__`, keeping alphabetical order.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_signals.py tests/test_backtest.py -q`
Expected: all pass, including six `TargetExposureTests` and two `AnnualBenchmarkTests`.

- [ ] **Step 6: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `318 passed`.

```bash
git add src/boring_alpha/signals/trend.py src/boring_alpha/signals/__init__.py tests/test_signals.py tests/test_backtest.py
git commit -m "Add a target-exposure benchmark with a declared rebalancing schedule

Static equal-weight scaled to an exposure fixed in the charter, rebalanced
annually or monthly. On the annual schedule every month-end but December
is a hold, so the allocation drifts between Januaries as a passive
holder's would; the engine's empty-book rule means a mid-year start still
enters on its first session.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: The strategy profile registry, with BA-001 pinned by golden data

BA-001's grid, criteria and verdict move behind a `StrategyProfile`. Nothing in `criteria.py` changes; the profile delegates to it. The two real sweeps' `criteria.json` files become fixtures, and a test replays them.

**Files:**
- Create: `src/boring_alpha/profiles.py`
- Create: `tests/fixtures/ba001_development_criteria.json`, `tests/fixtures/ba001_validation_criteria.json` (copies)
- Test: `tests/test_profiles.py`

**Interfaces:**
- Consumes: `criteria.evaluate_period(variants) -> PeriodOutcome`, `criteria.classify(dev_variants, val_variants) -> Verdict`, the variant name constants, `MultiAssetTrend`, `FixedAllocation`, `ExcludingSleeve`, `TargetExposureAllocation`, `AppConfig.benchmark`.
- Produces:
  - `VariantSpec(description: str, cost_bps: float, strategy: Callable[[AppConfig, str | None], SignalPolicy], benchmark: Callable[[AppConfig], SignalPolicy], needs_top_sleeve: bool = False)`
  - `StrategyProfile` protocol: `strategy_id: str`; `grid(config) -> dict[str, VariantSpec]`; `evaluate_period(variants: dict, extras: dict[str, object]) -> PeriodOutcome`; `classify(development_variants: dict, validation_variants: dict) -> Verdict`
  - `BA001Profile`, `PROFILES: dict[str, StrategyProfile]`, `profile_for(strategy_id: str) -> StrategyProfile`
  - Tasks 8 and 9 consume `profile_for`.

- [ ] **Step 1: Copy the golden fixtures**

```bash
cp experiments/BA-001/sweeps/4b9d1479f811d108/criteria.json tests/fixtures/ba001_development_criteria.json
cp experiments/BA-001/sweeps/f0a36ea722ebefd4/criteria.json tests/fixtures/ba001_validation_criteria.json
python3 -c "import json; d=json.load(open('tests/fixtures/ba001_development_criteria.json')); v=json.load(open('tests/fixtures/ba001_validation_criteria.json')); print(d['evaluation_period'], d['passed'], v['evaluation_period'], v['passed'], d['strategy_spec_sha256']==v['strategy_spec_sha256'])"
```

Expected output: `development True validation False True`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_profiles.py`:

```python
"""A strategy's grid, criteria and verdict live in its profile; BA-001's must not move."""

import json
from pathlib import Path
import unittest

from boring_alpha.config import load_config
from boring_alpha.criteria import (
    BASE,
    DOUBLE_COST,
    DROP_TOP_SLEEVE,
    LOOKBACK_15,
    LOOKBACK_9,
    Verdict,
)
from boring_alpha.profiles import BA001Profile, PROFILES, VariantSpec, profile_for
from boring_alpha.signals.trend import (
    ExcludingSleeve,
    FixedAllocation,
    MultiAssetTrend,
    TargetExposureAllocation,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class RegistryTests(unittest.TestCase):
    def test_ba_001_is_registered(self) -> None:
        self.assertIsInstance(profile_for("BA-001"), BA001Profile)
        self.assertEqual(profile_for("BA-001").strategy_id, "BA-001")
        self.assertIn("BA-001", PROFILES)

    def test_an_unknown_strategy_is_refused_by_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "no evaluation profile.*X-999"):
            profile_for("X-999")


class GoldenReplayTests(unittest.TestCase):
    """The two real BA-001 sweeps, replayed through the profile, must reproduce
    their own criteria files exactly and classify Inconclusive."""

    def setUp(self) -> None:
        self.development = _fixture("ba001_development_criteria.json")
        self.validation = _fixture("ba001_validation_criteria.json")
        self.profile = BA001Profile()

    def _replay(self, fixture: dict) -> None:
        outcome = self.profile.evaluate_period(fixture["variants"], {})
        self.assertEqual(outcome.passed, fixture["passed"])
        produced = [
            {"name": c.name, "description": c.description, "passed": c.passed, "detail": c.detail}
            for c in outcome.criteria
        ]
        self.assertEqual(produced, fixture["criteria"])

    def test_development_criteria_are_reproduced_exactly(self) -> None:
        self._replay(self.development)

    def test_validation_criteria_are_reproduced_exactly(self) -> None:
        self._replay(self.validation)

    def test_the_pair_classifies_inconclusive(self) -> None:
        verdict = self.profile.classify(self.development["variants"], self.validation["variants"])
        self.assertIs(verdict, Verdict.INCONCLUSIVE)


class GridTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(REPO_ROOT / "configs" / "ba_001_development.toml")
        self.grid = BA001Profile().grid(self.config)

    def test_the_grid_has_the_charter_s_five_variants_in_order(self) -> None:
        self.assertEqual(
            list(self.grid), [BASE, DOUBLE_COST, LOOKBACK_9, LOOKBACK_15, DROP_TOP_SLEEVE]
        )
        self.assertTrue(all(isinstance(spec, VariantSpec) for spec in self.grid.values()))

    def test_descriptions_match_the_archived_sweep(self) -> None:
        # From experiments/BA-001/sweeps/4b9d1479f811d108/manifest.json "grid".
        self.assertEqual(
            {name: spec.description for name, spec in self.grid.items()},
            {
                BASE: "12-month lookback at 10 bps (pre-registered)",
                DOUBLE_COST: "12-month lookback at 20 bps",
                DROP_TOP_SLEEVE: "12-month lookback at 10 bps, top sleeve in cash",
                LOOKBACK_15: "15-month lookback at 10 bps",
                LOOKBACK_9: "9-month lookback at 10 bps",
            },
        )

    def test_costs_and_lookbacks_follow_the_charter(self) -> None:
        self.assertEqual(self.grid[BASE].cost_bps, 10.0)
        self.assertEqual(self.grid[DOUBLE_COST].cost_bps, 20.0)
        nine = self.grid[LOOKBACK_9].strategy(self.config, None)
        fifteen = self.grid[LOOKBACK_15].strategy(self.config, None)
        self.assertIsInstance(nine, MultiAssetTrend)
        self.assertEqual(nine.lookback_months, 9)
        self.assertEqual(fifteen.lookback_months, 15)
        # The benchmark takes the variant's own lookback so both series start together.
        self.assertEqual(self.grid[LOOKBACK_15].benchmark(self.config).lookback_months, 15)

    def test_only_the_drop_variant_needs_the_top_sleeve_and_excludes_it(self) -> None:
        self.assertEqual(
            [name for name, spec in self.grid.items() if spec.needs_top_sleeve],
            [DROP_TOP_SLEEVE],
        )
        policy = self.grid[DROP_TOP_SLEEVE].strategy(self.config, "SPY")
        self.assertIsInstance(policy, ExcludingSleeve)
        self.assertEqual(policy.symbol, "SPY")
        with self.assertRaisesRegex(ValueError, "top sleeve"):
            self.grid[DROP_TOP_SLEEVE].strategy(self.config, None)

    def test_the_benchmark_is_full_static_without_a_benchmark_table(self) -> None:
        benchmark = self.grid[BASE].benchmark(self.config)
        self.assertIsInstance(benchmark, FixedAllocation)
        self.assertNotIsInstance(benchmark, TargetExposureAllocation)

    def test_the_benchmark_follows_the_benchmark_table_when_present(self) -> None:
        import tempfile

        root = Path(tempfile.mkdtemp())
        (root / "configs").mkdir()
        periods = (REPO_ROOT / "configs" / "evaluation_periods.toml").read_text(encoding="utf-8")
        (root / "configs" / "evaluation_periods.toml").write_text(periods, encoding="utf-8")
        text = (REPO_ROOT / "configs" / "ba_001_development.toml").read_text(encoding="utf-8")
        text += '\n[benchmark]\nexposure = 0.6\nrebalance = "annual"\n'
        path = root / "configs" / "run.toml"
        path.write_text(text, encoding="utf-8")
        config = load_config(path)
        benchmark = BA001Profile().grid(config)[BASE].benchmark(config)
        self.assertIsInstance(benchmark, TargetExposureAllocation)
        self.assertEqual(benchmark.name, "Target-Exposure Benchmark (60%, annual)")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `.venv/bin/python -m pytest tests/test_profiles.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'boring_alpha.profiles'`.

- [ ] **Step 4: Implement the registry**

Create `src/boring_alpha/profiles.py`:

```python
"""Per-strategy evaluation profiles: what a sweep runs and how it is judged.

A charter fixes a grid of variants, the criteria applied to them, and the
advance / reject / inconclusive rule. Those belong to the strategy, not to the
laboratory, so each strategy registers a profile here and the sweep and
classify commands ask the profile rather than assuming BA-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from boring_alpha.backtest.engine import SignalPolicy
from boring_alpha.config import AppConfig
from boring_alpha.criteria import (
    BASE,
    DOUBLE_COST,
    DROP_TOP_SLEEVE,
    LOOKBACK_15,
    LOOKBACK_9,
    PeriodOutcome,
    Verdict,
)
from boring_alpha.criteria import classify as _classify_ba001
from boring_alpha.criteria import evaluate_period as _evaluate_period_ba001
from boring_alpha.signals import (
    ExcludingSleeve,
    FixedAllocation,
    MultiAssetTrend,
    TargetExposureAllocation,
)


@dataclass(frozen=True)
class VariantSpec:
    """One cell of a sweep grid.

    `strategy` receives the configuration and, when `needs_top_sleeve` is set,
    the base variant's largest-contributing sleeve; otherwise `None`.
    `benchmark` builds the gating benchmark the variant is judged against.
    """

    description: str
    cost_bps: float
    strategy: Callable[[AppConfig, str | None], SignalPolicy]
    benchmark: Callable[[AppConfig], SignalPolicy]
    needs_top_sleeve: bool = False


class StrategyProfile(Protocol):
    strategy_id: str

    def grid(self, config: AppConfig) -> dict[str, VariantSpec]: ...

    def evaluate_period(
        self, variants: dict[str, dict[str, dict[str, float]]], extras: dict[str, object]
    ) -> PeriodOutcome: ...

    def classify(self, development: dict, validation: dict) -> Verdict: ...


def gating_benchmark(config: AppConfig, lookback_months: int) -> SignalPolicy:
    """Full static equal-weight, or the configured target-exposure allocation.

    The benchmark takes the variant's own lookback so that strategy and
    benchmark series start on the same session.
    """

    symbols, weight = config.strategy.symbols, config.strategy.sleeve_weight
    if config.benchmark is not None:
        return TargetExposureAllocation(
            symbols, lookback_months, weight, config.benchmark.exposure, config.benchmark.rebalance
        )
    return FixedAllocation(symbols, lookback_months, weight)


class BA001Profile:
    """BA-001 Multi-Asset Trend: the charter's C1 to C5 on its five-variant grid."""

    strategy_id = "BA-001"

    def grid(self, config: AppConfig) -> dict[str, VariantSpec]:
        lookback = config.strategy.lookback_months
        cost = config.execution.cost_bps

        def trend(months: int) -> Callable[[AppConfig, str | None], SignalPolicy]:
            def build(config: AppConfig, top_sleeve: str | None) -> SignalPolicy:
                return MultiAssetTrend(
                    config.strategy.symbols, months, config.strategy.sleeve_weight
                )

            return build

        def trend_without_top_sleeve(months: int) -> Callable[[AppConfig, str | None], SignalPolicy]:
            def build(config: AppConfig, top_sleeve: str | None) -> SignalPolicy:
                if top_sleeve is None:
                    raise ValueError(
                        f"{DROP_TOP_SLEEVE} needs the base variant's top sleeve"
                    )
                return ExcludingSleeve(
                    MultiAssetTrend(config.strategy.symbols, months, config.strategy.sleeve_weight),
                    top_sleeve,
                )

            return build

        def static(months: int) -> Callable[[AppConfig], SignalPolicy]:
            return lambda config: gating_benchmark(config, months)

        return {
            BASE: VariantSpec(
                f"{lookback}-month lookback at {cost:g} bps (pre-registered)",
                cost, trend(lookback), static(lookback),
            ),
            DOUBLE_COST: VariantSpec(
                f"{lookback}-month lookback at {2 * cost:g} bps",
                2.0 * cost, trend(lookback), static(lookback),
            ),
            LOOKBACK_9: VariantSpec(
                f"9-month lookback at {cost:g} bps", cost, trend(9), static(9),
            ),
            LOOKBACK_15: VariantSpec(
                f"15-month lookback at {cost:g} bps", cost, trend(15), static(15),
            ),
            DROP_TOP_SLEEVE: VariantSpec(
                f"{lookback}-month lookback at {cost:g} bps, top sleeve in cash",
                cost, trend_without_top_sleeve(lookback), static(lookback),
                needs_top_sleeve=True,
            ),
        }

    def evaluate_period(
        self, variants: dict[str, dict[str, dict[str, float]]], extras: dict[str, object]
    ) -> PeriodOutcome:
        return _evaluate_period_ba001(variants)

    def classify(self, development: dict, validation: dict) -> Verdict:
        return _classify_ba001(development, validation)


PROFILES: dict[str, StrategyProfile] = {"BA-001": BA001Profile()}


def profile_for(strategy_id: str) -> StrategyProfile:
    try:
        return PROFILES[strategy_id]
    except KeyError:
        raise ValueError(
            f"no evaluation profile is registered for strategy {strategy_id!r}; "
            f"known profiles: {', '.join(sorted(PROFILES))}"
        ) from None
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_profiles.py -q`
Expected: `12 passed`.

- [ ] **Step 6: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `330 passed`.

```bash
git add src/boring_alpha/profiles.py tests/test_profiles.py tests/fixtures/ba001_development_criteria.json tests/fixtures/ba001_validation_criteria.json
git commit -m "Register per-strategy evaluation profiles, with BA-001 pinned

A profile owns a strategy's sweep grid, its period criteria and its
verdict rule. BA-001's profile delegates to the existing criteria module
and reproduces both real sweeps' criteria files exactly; those files are
now fixtures and the replay is a test. The gating benchmark follows the
optional benchmark table when one is configured.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: The sweep runs a profile's grid

`run_sweep` stops hard-coding BA-001's variants and asks the profile. Behaviour for BA-001 is unchanged; the tests that used made-up strategy ids move to `BA-001`, and a new test proves an unregistered id is refused before anything runs.

**Files:**
- Modify: `src/boring_alpha/sweep.py`
- Modify: `tests/test_sweep.py`, `tests/test_hardening.py` (strategy ids)

**Interfaces:**
- Consumes: `profile_for`, `VariantSpec`.
- Produces: `run_sweep(config, data) -> SweepResult` unchanged in shape; `SweepResult.grid` now comes from the profile. `GRID` remains exported as BA-001's variant order for existing callers.

- [ ] **Step 1: Retarget the existing tests and add the refusal test**

In `tests/test_sweep.py`:
- In `PERIODS`, change `[W-001.development]` to `[BA-001.development]`.
- In `CONFIG`, change `id = "W-001"` to `id = "BA-001"`.
- Change the assertion `self.assertEqual(criteria["strategy_id"], "W-001")` to `"BA-001"`.
- Append:

```python
class ProfileGateTests(unittest.TestCase):
    def test_an_unregistered_strategy_id_is_refused_before_any_run(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "configs").mkdir()
        (root / "configs" / "evaluation_periods.toml").write_text(
            PERIODS.replace("BA-001", "W-001"), encoding="utf-8"
        )
        path = root / "configs" / "run.toml"
        path.write_text(CONFIG.replace('id = "BA-001"', 'id = "W-001"'), encoding="utf-8")
        config = load_config(path)
        with self.assertRaisesRegex(ValueError, "no evaluation profile.*W-001"):
            run_sweep(config, load_market_data(config))
```

In `tests/test_hardening.py`, in the `_build` method around lines 283 to 289, change `"[T-900.development]\n...` to `"[BA-001.development]\n...` and `'\n[strategy]\nid = "T-900"\nname = "Ranking"\n'` to `'\n[strategy]\nid = "BA-001"\nname = "Ranking"\n'`. Run `grep -n "T-900" tests/test_hardening.py` afterwards and confirm nothing remains.

- [ ] **Step 2: Run the tests to see the new one fail**

Run: `.venv/bin/python -m pytest tests/test_sweep.py tests/test_hardening.py -q`
Expected: everything passes except `test_an_unregistered_strategy_id_is_refused_before_any_run`, which fails because `run_sweep` does not yet consult the registry.

- [ ] **Step 3: Rewire `run_sweep`**

In `src/boring_alpha/sweep.py`:

Replace the `from boring_alpha.signals import (...)` block with:

```python
from boring_alpha.profiles import VariantSpec, profile_for
from boring_alpha.signals import CashAllocation, ScaledAllocation
```

Delete the `_pair` function entirely. Replace `run_sweep` with:

```python
def run_sweep(config: AppConfig, data: MarketData) -> SweepResult:
    profile = profile_for(config.strategy.strategy_id)
    specs = profile.grid(config)
    if BASE not in specs:
        raise ValueError(f"{profile.strategy_id}'s grid defines no '{BASE}' variant")
    grid = {name: spec.description for name, spec in specs.items()}
    cost = config.execution.cost_bps
    lookback = config.strategy.lookback_months

    def run_variant(
        spec: VariantSpec, top_sleeve: str | None
    ) -> tuple[BacktestResult, BacktestResult]:
        engine = _engine(config, data, spec.cost_bps)
        strategy = engine.run(spec.strategy(config, top_sleeve))
        # Every variant is judged against the gating benchmark, including the
        # one without its best sleeve: the question is whether the strategy
        # clears the bar handicapped, not whether a handicapped benchmark is
        # easier to beat.
        benchmark = engine.run(spec.benchmark(config))
        return strategy, benchmark

    base_strategy, base_static = run_variant(specs[BASE], None)
    contributions = dict(base_strategy.contributions)
    # The charter ranks sleeves by share of excess return over cash, not by raw
    # profit: a sleeve held almost always at roughly the cash rate earns a large
    # raw number while contributing nothing the portfolio could not have had by
    # sitting in cash.
    excess_contributions = dict(base_strategy.excess_contributions)
    top_sleeve = max(excess_contributions, key=lambda symbol: excess_contributions[symbol])

    runs: dict[str, tuple[BacktestResult, BacktestResult]] = {BASE: (base_strategy, base_static)}
    for name, spec in specs.items():
        if name == BASE:
            continue
        runs[name] = run_variant(spec, top_sleeve if spec.needs_top_sleeve else None)
    variants = {
        name: {
            "strategy": calculate_metrics(strategy, data),
            "static": calculate_metrics(static, data),
        }
        for name, (strategy, static) in runs.items()
    }

    base_metrics = variants[BASE]["strategy"]
    matched = _engine(config, data, cost).run(
        ScaledAllocation(
            config.strategy.symbols,
            lookback,
            config.strategy.sleeve_weight,
            float(base_metrics["average_gross_exposure"]),
        )
    )
    cash = _engine(config, data, cost).run(CashAllocation(config.strategy.symbols))
    cash_metrics = calculate_metrics(cash, data)

    clusters = {
        name: sum(excess_contributions.get(symbol, 0.0) for symbol in symbols)
        for name, symbols in config.clusters.items()
    }
    # Variants warm up differently — the 15-month rule needs three more months
    # of anchor history than the base rule — so every variant's warnings are
    # recorded and tagged, not just the pre-registered one's.
    warnings = [
        f"{name}: {warning}"
        for name, (strategy, static) in runs.items()
        for warning in tuple(strategy.warnings) + tuple(static.warnings)
    ]
    covered = {symbol for symbols in config.clusters.values() for symbol in symbols}
    uncovered = sorted(set(config.strategy.symbols) - covered)
    if config.clusters and uncovered:
        warnings.append(f"sleeves outside every cluster: {', '.join(uncovered)}")

    return SweepResult(
        variants=variants,
        outcome=profile.evaluate_period(variants, {}),
        contributions=contributions,
        excess_contributions=excess_contributions,
        clusters=clusters,
        top_sleeve=top_sleeve,
        exposure_matched=calculate_metrics(matched, data),
        cash=cash_metrics,
        runs={**runs, "exposure_matched": (matched, cash)},
        sharpe_interval=sharpe_difference_interval(
            excess_return_series(base_strategy, data),
            excess_return_series(base_static, data),
            seed=BOOTSTRAP_SEED,
        ),
        warnings=tuple(warnings),
        grid=grid,
    )
```

Remove `evaluate_period` from the `from boring_alpha.criteria import (...)` block (it is now reached through the profile); keep `BASE`, the other variant names and `PeriodOutcome`.

In `_summary`, change `for name in GRID:` to `for name in sweep.grid:`.

In `write_sweep_report`, change `"|".join(GRID),` to `"|".join(sweep.grid),`. (For BA-001 this is the same string, so identities are unchanged.)

Leave `GRID = (BASE, DOUBLE_COST, LOOKBACK_9, LOOKBACK_15, DROP_TOP_SLEEVE)` in place with the comment `# BA-001's variant order; kept for callers that iterate it.`

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_sweep.py tests/test_hardening.py -q`
Expected: all pass.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `331 passed`.

```bash
git add src/boring_alpha/sweep.py tests/test_sweep.py tests/test_hardening.py
git commit -m "Drive the sweep from the strategy's profile

run_sweep asks the registered profile for its grid and its period
criteria instead of assuming BA-001's. Behaviour for BA-001 is unchanged;
tests that used made-up strategy ids now run as BA-001, and an
unregistered id is refused before anything runs.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: `classify` reads through the profile, tolerates listed schemas, and requires one tax policy

**Files:**
- Modify: `src/boring_alpha/report.py` (`READABLE_SCHEMAS`)
- Modify: `src/boring_alpha/cli.py` (`run_classify`)
- Modify: `tests/test_classify.py`

**Interfaces:**
- Consumes: `profile_for`.
- Produces: `report.READABLE_SCHEMAS: tuple[int, ...]` (plan 2 extends it to `(5, 6)`); `run_classify` refuses mismatched or one-sided `tax_policy_sha256` (plan 2 writes that key).

- [ ] **Step 1: Retarget the existing tests and add the new ones**

In `tests/test_classify.py`, change `"strategy_id": "X-001",` in `_criteria` to `"strategy_id": "BA-001",`. Leave `strategy_id="Y-002"` in the mismatch test as is. Append:

```python
class TaxPolicyAgreementTests(unittest.TestCase):
    """Two sweeps scored under different tax policies cannot share a verdict."""

    _dirs = ClassifyGuardTests._dirs

    def test_identical_tax_policies_classify(self) -> None:
        dev_dir, val_dir = self._dirs(
            _criteria("development", tax_policy_sha256="c" * 64),
            _criteria("validation", tax_policy_sha256="c" * 64),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_classify(dev_dir, val_dir), 0)

    def test_different_tax_policies_are_refused(self) -> None:
        dev_dir, val_dir = self._dirs(
            _criteria("development", tax_policy_sha256="c" * 64),
            _criteria("validation", tax_policy_sha256="d" * 64),
        )
        with self.assertRaisesRegex(ValueError, "different tax policies"):
            run_classify(dev_dir, val_dir)

    def test_a_policy_on_one_side_only_is_refused(self) -> None:
        dev_dir, val_dir = self._dirs(
            _criteria("development", tax_policy_sha256="c" * 64), _criteria("validation")
        )
        with self.assertRaisesRegex(ValueError, "different tax policies"):
            run_classify(dev_dir, val_dir)


class ProfileLookupTests(unittest.TestCase):
    _dirs = ClassifyGuardTests._dirs

    def test_an_unregistered_strategy_is_refused(self) -> None:
        dev_dir, val_dir = self._dirs(
            _criteria("development", strategy_id="X-001"),
            _criteria("validation", strategy_id="X-001"),
        )
        with self.assertRaisesRegex(ValueError, "no evaluation profile.*X-001"):
            run_classify(dev_dir, val_dir)

    def test_the_verdict_names_the_strategy(self) -> None:
        dev_dir, val_dir = self._dirs(_criteria("development"), _criteria("validation"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run_classify(dev_dir, val_dir)
        self.assertIn("BA-001 classification:", out.getvalue())


class SchemaCompatibilityTests(unittest.TestCase):
    _dirs = ClassifyGuardTests._dirs

    def test_every_readable_schema_classifies(self) -> None:
        from boring_alpha.report import READABLE_SCHEMAS

        for schema in READABLE_SCHEMAS:
            dev_dir, val_dir = self._dirs(
                _criteria("development", artifact_schema=schema),
                _criteria("validation", artifact_schema=schema),
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_classify(dev_dir, val_dir), 0)
```

- [ ] **Step 2: Run the tests to see the new ones fail**

Run: `.venv/bin/python -m pytest tests/test_classify.py -q`
Expected: the pre-existing tests pass; `test_a_policy_on_one_side_only_is_refused` and `test_different_tax_policies_are_refused` fail (no refusal yet); `test_an_unregistered_strategy_is_refused` fails (X-001 currently classifies); `SchemaCompatibilityTests` fails with `ImportError` for `READABLE_SCHEMAS`.

- [ ] **Step 3: Implement**

In `src/boring_alpha/report.py`, after `ARTIFACT_SCHEMA = 5`, add:

```python
# Schemas `classify` may read. A new schema that only adds fields is appended
# here so that artifacts written under the old one stay classifiable.
READABLE_SCHEMAS: tuple[int, ...] = (ARTIFACT_SCHEMA,)
```

In `src/boring_alpha/cli.py`:
- Change `from boring_alpha.report import ARTIFACT_SCHEMA, write_report` to `from boring_alpha.report import READABLE_SCHEMAS, write_report`.
- Change `from boring_alpha.criteria import Verdict, classify` to `from boring_alpha.criteria import Verdict`.
- Add `from boring_alpha.profiles import profile_for`.
- Replace `run_classify` with:

```python
def run_classify(development_dir: Path, validation_dir: Path) -> int:
    development = _read_criteria(development_dir, "development")
    validation = _read_criteria(validation_dir, "validation")

    # A verdict combining two unrelated sweeps would be confidently wrong. The
    # inputs must agree on everything except the window they cover, and a field
    # that is merely absent proves nothing — so absence is refused too, rather
    # than skipped.
    for field, message in (
        ("artifact_schema", "different artifact schemas"),
        ("strategy_id", "different strategies"),
        ("strategy_spec_sha256", "different strategy definitions"),
        ("code_sha256", "different code revisions"),
    ):
        for label, criteria in (("development", development), ("validation", validation)):
            if field not in criteria:
                raise ValueError(
                    f"the {label} sweep records no {field}; it predates the checks that "
                    "make a verdict trustworthy. Re-run the sweep on current code."
                )
        if development[field] != validation[field]:
            raise ValueError(
                f"refusing to classify {message}: "
                f"{field} is {development[field]!r} in the development sweep and "
                f"{validation[field]!r} in the validation sweep"
            )
    schema = development["artifact_schema"]
    if schema not in READABLE_SCHEMAS:
        readable = ", ".join(str(value) for value in READABLE_SCHEMAS)
        raise ValueError(
            f"these sweeps use artifact schema {schema}, but this code reads schemas "
            f"{readable}. Re-run them rather than comparing artifacts across schema versions."
        )
    # A tax policy is part of what was scored. Two sweeps scored under different
    # policies, or one scored and one not, cannot share a verdict.
    policies = (development.get("tax_policy_sha256"), validation.get("tax_policy_sha256"))
    if any(policies) and policies[0] != policies[1]:
        raise ValueError(
            "refusing to classify different tax policies: tax_policy_sha256 is "
            f"{policies[0]!r} in the development sweep and {policies[1]!r} in the "
            "validation sweep"
        )

    strategy_id = development["strategy_id"]
    profile = profile_for(strategy_id)
    verdict = profile.classify(development["variants"], validation["variants"])

    print(f"{strategy_id} classification: {verdict.value.upper()}")
    for label, criteria in (("development", development), ("validation", validation)):
        print(f"\n{label}:")
        for criterion in criteria["criteria"]:
            print(
                f"  {criterion['name']} {'pass' if criterion['passed'] else 'FAIL'}: "
                f"{criterion['detail']}"
            )
    if verdict is Verdict.INCONCLUSIVE:
        print(
            "\nInconclusive is a real outcome, not a failure to decide. "
            "Record it in the registry rather than searching for a variant that advances."
        )
    print("\nWrite the decision under docs/reviews/ without changing the charter retroactively.")
    return 0
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_classify.py -q`
Expected: all pass. The pre-existing `test_a_stale_artifact_schema_is_refused` still matches its regex `artifact schema 4`.

- [ ] **Step 5: Confirm the real sweeps still classify**

Run: `.venv/bin/boring-alpha classify experiments/BA-001/sweeps/4b9d1479f811d108 experiments/BA-001/sweeps/f0a36ea722ebefd4 | head -3`
Expected: first line `BA-001 classification: INCONCLUSIVE`. (Both sweeps are schema 5 and carry no tax policy.)

- [ ] **Step 6: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: `337 passed`.

```bash
git add src/boring_alpha/report.py src/boring_alpha/cli.py tests/test_classify.py
git commit -m "Classify through the profile, by listed schema, under one tax policy

The verdict comes from the strategy's registered profile and names the
strategy. Readable artifact schemas are an explicit list, so a future
schema that only adds fields can keep old sweeps classifiable. Two sweeps
must record the same tax policy hash, or none, to share a verdict.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Fetch a v2 snapshot and perform the hand checks

The overlay's numbers may not be cited until the endpoint's dividend convention has been checked by hand (spec §3.5). This task fetches the v2 snapshot, extracts the rows to check, and records the comparison in a decision record. The comparison against the issuers' published schedules needs a person with those documents; the record says what was checked and, if a figure could not be sourced, says so.

**Files:**
- Create: `docs/decisions/<today>-distributions-v2.md` (use the actual date)
- Reads: `data/current/`

**Interfaces:**
- Consumes: `tools/fetch_market_data.py` from Task 3.
- Produces: a v2 snapshot at `data/snapshots/<stamp>/` with `data/current` repointed; the decision record plan 2's note cites.

- [ ] **Step 1: Fetch**

Run: `.venv/bin/python tools/fetch_market_data.py`
Expected: eight symbol lines each ending with an ex-date count and a split count (IWM 1, EFA 1, EEM 2, others 0), a `DGS3MO` line, then `wrote data/snapshots/<stamp>`, a distribution-row count, split lines for IWM, EFA and EEM, `methodology: yahoo-adjusted-v2+dgs3mo-v1`, and the `current` pointer. The previous v1 snapshot directory is left in place; do not delete it.

- [ ] **Step 2: Confirm the snapshot's shape**

```bash
ls data/current/
python3 -c "
import json; m=json.load(open('data/current/manifest.json'))
print(m['methodology']); print(m['splits']); print(m['price_rows'], m['distribution_rows'])"
```

Expected: `cash_daily.csv distributions_daily.csv manifest.json market_daily.csv`; the methodology string; splits showing `IWM` 2005-06-09 `2:1`, `EFA` 2005-06-09 `3:1`, `EEM` 2005-06-09 `3:1` and 2008-07-24 `3:1`; equal price and distribution row counts.

- [ ] **Step 3: Extract the rows to check**

```bash
python3 - <<'EOF'
import csv
rows = list(csv.DictReader(open("data/current/distributions_daily.csv")))
def show(symbol, year):
    print(f"--- {symbol} {year}")
    for r in rows:
        if r["symbol"] == symbol and r["date"].startswith(str(year)) and float(r["dividend"]) > 0:
            print(f"  {r['date']}  close {float(r['close']):.2f}  dividend {float(r['dividend']):.6f}")
show("EEM", 2008)
show("SPY", 2019)
EOF
```

Expected: EEM 2008 shows ex-dates in June and December (the June amount near 0.5173 and the December amount near 0.34), and SPY 2019 shows four quarterly ex-dates.

- [ ] **Step 4: Write the decision record**

Create `docs/decisions/<today>-distributions-v2.md` with this content, filling every `<...>` from the issuer's published distribution schedule (iShares for EEM, State Street for SPY). If a figure cannot be sourced, write `not sourced` in that cell and leave the Status line as **open**:

```markdown
# Distributions snapshot v2: hand checks

Date: <today>
Snapshot: `data/snapshots/<stamp>`, methodology `yahoo-adjusted-v2+dgs3mo-v1`
Resolves: spec §3.5 of `docs/superpowers/specs/2026-09-04-after-tax-evaluation-design.md`
Status: **<verified | open>**

## What was checked

The chart endpoint's dividend amounts are in the same split-adjusted units
as its `close`. The tax overlay depends on that. Two symbol-years were
compared by hand against the issuer's published distribution schedule.

### EEM 2008 (3:1 split on 2008-07-24)

| Ex-date (archived) | Archived amount | Issuer amount per share | Issuer source | Relationship |
|---|---:|---:|---|---|
| <2008-06-xx> | <0.517333> | <issuer figure> | <document or page> | <one third, pre-split | equal, post-split | mismatch> |
| <2008-12-xx> | <0.34> | <issuer figure> | <document or page> | <equal, post-split | mismatch> |

### SPY 2019 (no splits)

| Ex-date (archived) | Archived amount | Issuer amount per share | Issuer source | Relationship |
|---|---:|---:|---|---|
| <date> | <amount> | <issuer figure> | <document or page> | <equal | mismatch> |
| <date> | <amount> | <issuer figure> | <document or page> | <equal | mismatch> |
| <date> | <amount> | <issuer figure> | <document or page> | <equal | mismatch> |
| <date> | <amount> | <issuer figure> | <document or page> | <equal | mismatch> |

## Conclusion

<One paragraph: whether the pre-split EEM amounts are one third of the
issuer's and the post-split and SPY amounts equal, to the cent; therefore
whether the split-adjusted-units assumption in the fetcher and the
distributions reader is confirmed. If any row is "not sourced" or
"mismatch", say what remains open and that the overlay's outputs may not
be cited until it is closed.>

## Consequences for existing configurations

BA-001's configurations declare `yahoo-adjusted-v1+dgs3mo-v1`. The loader
checks a run's declared methodology against the snapshot at `data/current`,
so they now refuse to run against it. That is by design: BA-001's runs are
archived under their own identity, and a rerun against a v2 snapshot would
be a different run. The v1 snapshot directory is kept.
```

- [ ] **Step 5: Commit**

```bash
git add docs/decisions/<today>-distributions-v2.md
git commit -m "Record the v2 distributions snapshot and its hand checks

<One line: verified against issuer schedules for EEM 2008 and SPY 2019 |
open: which rows could not be sourced.>

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review against the spec

**Spec coverage.** §3.1 methodology identifier: Task 3. §3.2 file and columns: Task 3. §3.3 splits recorded, units stated, reader requires records: Tasks 3 and 4. §3.4 loader and engine untouched, reader records hash: Task 4. §3.5 hand checks: Task 10. §5.1 configuration, hash inclusion only when present, naming: Tasks 5 and 6. §5.2 hold field, empty-book rule, serializer omission, precise preservation claim: Task 2 (the claim is pinned by the `snapshot_record` tests and the unchanged pre-existing artifact tests; a byte-level comparison of a full synthetic run against a pre-change checkout is not possible inside the suite because `code_sha256` changes, which is exactly the caveat the spec states). §5.3 secondary rows: unchanged today; plan 2 adds the target-exposure row to the summary when tax lands. §6 registry and golden replay: Task 7. §6.1 tax-policy agreement and schema list: Task 9 (the list is extended to `(5, 6)` in plan 2 when schema 6 exists). §9 engine homogeneity: Task 1; hold tests: Tasks 2 and 6; fetcher tests: Task 3; reader tests: Task 4; benchmark tests: Tasks 5 and 6; registry and CLI tests: Tasks 7 and 9. §12 steps 1, 2, 4, 5: Tasks 1–9; step 2's fetch and checks: Task 10. §4, §7, §8, §12 steps 3, 6, 7: plan 2, as stated in the header.

**Placeholder scan.** The only angle-bracket fields are in Task 10's decision-record template, which a person fills from issuer documents; the step says what to write when a figure cannot be sourced.

**Type consistency.** `VariantSpec.strategy: Callable[[AppConfig, str | None], SignalPolicy]` and `.benchmark: Callable[[AppConfig], SignalPolicy]` are used identically in Tasks 7 and 8. `profile_for(str) -> StrategyProfile` in Tasks 7, 8, 9. `TargetExposureAllocation(symbols, lookback_months, sleeve_weight, exposure, rebalance)` in Tasks 6 and 7. `write_snapshot(out, price_rows, cash_rows, distribution_rows, coverage, splits)` in Task 3 only. `load_distributions(path, *, manifest_path=None, manifest_block=None)` in Task 4 only; plan 2 consumes it. `READABLE_SCHEMAS` in Task 9; plan 2 extends it. Test counts assume each task adds exactly the tests listed; if a count differs, the number of tests in the file is what matters, not the arithmetic here.
