"""The whole monthly loop, offline: fetch a corpus, then seal a book against it.

`tools/rehearse_forward.py` manufactures month-end bars by hand and discovered that the engine will not seal a date the bill
curve does not cover. That is the right refusal, and it moves the risk one step earlier: on 2026-09-30 the operator types a
fetch and then a seal, and the fetch is the step that has never been run end to end. `tests/test_fetcher.py` tests the
parsing functions — adjustment, the incomplete-session rule, dividend alignment — with real skill, but no test has ever run
`main()`, written a snapshot, loaded the result through the same loader the engine uses, and sealed an entry on it.

So this file stubs the fetcher's one transport seam (`_get`, a single function, so a stub cannot drift from the real path)
with hand-built Yahoo charts and a hand-built FRED CSV, and drives the monthly routine twice: fetch, anchor, fetch again with
one more month, seal. Round 87's rule applies — a procedure that has never run against its real input is untested — and the
input here is a network response, which is the least tested thing in the repository.

`exchange_today` is stood forward for the seal test, because the fetcher correctly drops any session dated today or later and
a 2026-09-30 bar cannot exist before 2026-09-30 has been traded. The clock is stood forward; the prices are still the ones the
fetcher would have written.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import io
import json
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import fetch_market_data as fm                                   # noqa: E402
import paper                                                     # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

REAL = ROOT / "data" / "current"
SYMBOLS = ("SPY", "QQQ", "VOO")
START = dt.date(2026, 6, 2)
PRICES = {"SPY": 600.0, "QQQ": 550.0, "VOO": 540.0}


def _sessions(through: dt.date) -> list[dt.date]:
    """Every weekday from `START` to `through`, which is enough of a calendar for a rehearsal."""

    days, day = [], START
    while day <= through:
        if day.weekday() < 5:
            days.append(day)
        day += dt.timedelta(days=1)
    return days


def _chart(symbol: str, days: list[dt.date], today: dt.date, dividend_on: dt.date | None = None) -> dict:
    """A Yahoo chart payload: five sessions' worth is enough to exercise every filter that matters."""

    keep = [d for d in days if d < today][-60:]
    stamps = [int(dt.datetime.combine(d, dt.time(21, 0), tzinfo=dt.timezone.utc).timestamp()) for d in keep]
    price = PRICES[symbol]
    closes = [round(price * (1.0 + 0.001 * i), 6) for i in range(len(keep))]
    events: dict = {"dividends": {}, "splits": {}}
    if dividend_on is not None and dividend_on in keep:
        events["dividends"]["1"] = {"date": stamps[keep.index(dividend_on)], "amount": 1.85}
    inner = {"meta": {"gmtoffset": -18000, "symbol": symbol}, "timestamp": stamps,
            "indicators": {"quote": [{"open": closes, "close": closes, "high": closes, "low": closes,
                                      "volume": [1_000_000] * len(closes)}],
                           "adjclose": [{"adjclose": closes}]},
            "events": events}
    return {"chart": {"result": [inner], "error": None}}


def _last_weekday(day: dt.date) -> dt.date:
    while day.weekday() > 4:
        day -= dt.timedelta(days=1)
    return day


def _fred(days: list[dt.date], rate: float = 4.0) -> str:
    lines = ["observation_date,DGS3MO"]
    for day in days:
        lines.append(f"{day.isoformat()},{rate}")
    return "\n".join(lines) + "\n"


class Stub:
    """A stand-in for the internet, and for the clock, and for nothing else.

    `through` moves between fetches exactly the way reality moves it: the second call sees one more month of sessions.
    """

    def __init__(self, through: dt.date, clock: dt.date | None = None, fail: str | None = None, empty: str | None = None):
        self.through = through
        self.clock = clock or (through + dt.timedelta(days=1))
        self.fail, self.empty, self.calls = fail, empty, []
        self._saved_get, self._saved_today, self._saved_symbols = fm._get, fm.exchange_today, fm.SYMBOLS

    def __enter__(self):
        fm._get = self._get
        fm.exchange_today = lambda offset: self.clock
        fm.SYMBOLS = SYMBOLS
        return self

    def __exit__(self, *exc):
        fm._get, fm.exchange_today, fm.SYMBOLS = self._saved_get, self._saved_today, self._saved_symbols
        return False

    def _get(self, url: str) -> bytes:
        self.calls.append(url)
        if "fredgraph" in url:
            return _fred(_sessions(self.through)).encode()
        symbol = url.split("/chart/")[1].split("?")[0]
        if symbol == self.fail:
            raise urllib.error.URLError("stub: the endpoint refused")
        if symbol == self.empty:
            return json.dumps({"chart": {"result": [{"meta": {"gmtoffset": -18000}, "timestamp": [],
                                                      "indicators": {"quote": [{"open": [], "close": [], "high": [],
                                                                                "low": [], "volume": []}],
                                                                     "adjclose": [{"adjclose": []}]},
                                                      "events": {}}], "error": None}}).encode()
        return json.dumps(_chart(symbol, _sessions(self.through), self.clock,
                                 dividend_on=_last_weekday(self.through - dt.timedelta(days=4))
                                 if symbol == "SPY" else None)).encode()


def _hash_tree(directory: Path) -> dict:
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file() and "snapshots" not in p.parts}


class TheFetchedCorpus(unittest.TestCase):
    """One fetch, run once, inspected from six directions."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="ba-pipeline-"))
        cls.real_before = _hash_tree(REAL.parent)
        cls.stub = Stub(through=dt.date(2026, 9, 30))
        with cls.stub:
            saved, sys.argv = sys.argv, ["fetch_market_data.py", "--out", str(cls.dir / "data")]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    cls.code = fm.main()
            finally:
                sys.argv = saved
        cls.current = cls.dir / "data" / "current"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def rows(self, name: str) -> list[dict]:
        import csv
        with (self.current / name).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_the_command_succeeded_and_asked_for_every_symbol_once_and_the_bill_curve_once(self):
        """Exactly one request per sleeve plus one for FRED: a fetch that quietly asked twice for one symbol and skipped
        another would still write a corpus, and the missing sleeve would only surface as a book that cannot be priced."""

        self.assertEqual(self.code, 0)
        charts = [u.split("/chart/")[1].split("?")[0] for u in self.stub.calls if "/chart/" in u]
        self.assertEqual(sorted(charts), sorted(SYMBOLS),
                         "the fetcher asked for something other than the sleeves it declares")
        self.assertEqual([u for u in self.stub.calls if "fredgraph" in u], [fm.FRED_URL])
        self.assertEqual(len(self.stub.calls), len(SYMBOLS) + 1, self.stub.calls)

    def test_the_current_files_and_the_snapshot_are_the_same_bytes_because_a_run_is_atomic(self):
        snapshots = sorted((self.dir / "data" / "snapshots").iterdir())
        self.assertEqual(len(snapshots), 1, "a successful run leaves exactly one snapshot")
        for name in ("market_daily.csv", "cash_daily.csv", "distributions_daily.csv", "manifest.json"):
            self.assertEqual((self.current / name).read_bytes(), (snapshots[0] / name).read_bytes(),
                             f"`current/{name}` is not a byte copy of the named snapshot it claims to be")

    def test_the_manifest_counts_agree_with_the_files_it_describes(self):
        manifest = json.loads((self.current / "manifest.json").read_text())
        self.assertEqual(manifest["price_rows"], len(self.rows("market_daily.csv")))
        self.assertEqual(manifest["cash_rows"], len(self.rows("cash_daily.csv")))
        self.assertEqual(manifest["distribution_rows"], len(self.rows("distributions_daily.csv")))
        self.assertEqual(manifest["cash_series"], "DGS3MO")

    def test_the_engine_loads_the_fetched_corpus_without_the_error_round_eighty_seven_found(self):
        """Round 87's refusal, asserted against real fetcher output rather than a hand-appended bar: every price date must
        carry a cash factor, which is why prices and cash must always be written together."""

        data = load_csv_market_data(self.current / "market_daily.csv", self.current / "cash_daily.csv")
        self.assertEqual(len(data.dates), len(self.rows("cash_daily.csv")))
        self.assertEqual(max(data.dates), dt.date(2026, 9, 30))

    def test_the_distribution_file_is_aligned_row_for_row_with_the_price_file(self):
        prices, distributions = self.rows("market_daily.csv"), self.rows("distributions_daily.csv")
        self.assertEqual(len(prices), len(distributions))
        self.assertEqual({(r["date"], r["symbol"]) for r in prices},
                         {(r["date"], r["symbol"]) for r in distributions},
                         "one row per session and symbol in both files, aligned by construction")
        self.assertEqual(sum(1 for r in distributions if float(r["dividend"]) > 0), 1,
                         "the stub pays one dividend on one sleeve, and exactly that many must survive")

    def test_a_session_dated_after_the_clock_never_lands_in_the_corpus(self):
        """The reason the first seal cannot be pulled forward: the fetcher drops what the exchange has not finished trading,
        so on 2026-09-07 no fetch can produce a 2026-09-30 bar and no book can be sealed for it."""

        with Stub(through=dt.date(2026, 9, 30), clock=dt.date(2026, 9, 7)) as stub:
            saved, sys.argv = sys.argv, ["fetch_market_data.py", "--out", str(self.dir / "guard" / "data")]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = fm.main()
            finally:
                sys.argv = saved
        self.assertEqual(code, 0)
        dates = {r["date"] for r in self.rows_of(self.dir / "guard" / "data" / "current", "market_daily.csv")}
        self.assertLessEqual(max(dt.date.fromisoformat(d) for d in dates), dt.date(2026, 9, 4),
                             f"the clock said {stub.clock} and the corpus reaches {max(dates)}")

    def rows_of(self, directory: Path, name: str) -> list[dict]:
        import csv
        with (directory / name).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_the_real_corpus_was_not_touched_by_any_of_this(self):
        self.assertEqual(_hash_tree(REAL.parent), self.real_before)


class AFailedFetchChangesNothing(unittest.TestCase):
    """The docstring claims a run is atomic. Claimed atomicity is worth less than measured atomicity."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="ba-pipeline-fail-"))
        with Stub(through=dt.date(2026, 9, 30)):
            saved, sys.argv = sys.argv, ["fetch_market_data.py", "--out", str(cls.dir / "data")]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    fm.main()
            finally:
                sys.argv = saved
        cls.before = _hash_tree(cls.dir / "data")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_fetch(self, **kwargs) -> tuple[int, str]:
        with Stub(through=dt.date(2026, 10, 30), **kwargs):
            saved, sys.argv = sys.argv, ["fetch_market_data.py", "--out", str(self.dir / "data")]
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    code = fm.main()
            finally:
                sys.argv = saved
        return code, err.getvalue()

    def test_a_refused_endpoint_exits_nonzero_and_leaves_the_previous_corpus_byte_identical(self):
        code, err = self.run_fetch(fail="QQQ")
        self.assertEqual(code, 2)
        self.assertIn("QQQ", err)
        self.assertEqual(_hash_tree(self.dir / "data"), self.before)

    def test_an_empty_payload_is_an_error_rather_than_an_empty_corpus(self):
        code, err = self.run_fetch(empty="VOO")
        self.assertEqual(code, 2)
        self.assertIn("no usable rows", err)
        self.assertEqual(_hash_tree(self.dir / "data"), self.before,
                         "a corpus that quietly lost a sleeve is worse than a fetch that failed loudly")


class TheMonthlyLoop(unittest.TestCase):
    """Fetch, anchor, fetch again a month later, seal. The four commands in the order a person will type them."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="ba-loop-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def fetch(self, through: dt.date) -> None:
        """One run of the fetcher, with the one courtesy its own contract demands.

        Snapshots are named to the second and `mkdir(exist_ok=False)`, so two runs inside one second collide — and that is the
        design, not an oversight: the name is the identity and the manifest inside it is the completion marker. Round 88 tried
        to make the tool invent a suffixed name instead, `tests/test_fetcher.py` refused, and the tool was put back. The
        rehearsal waits rather than arguing, because in production the two fetches are a month apart.
        """

        for attempt in (1, 2):
            try:
                with Stub(through=through):
                    saved, sys.argv = sys.argv, ["fetch_market_data.py", "--out", str(self.dir / "data")]
                    try:
                        with contextlib.redirect_stdout(io.StringIO()):
                            code = fm.main()
                    finally:
                        sys.argv = saved
                break
            except FileExistsError:
                self.assertEqual(attempt, 1, "two attempts inside two seconds still collided")
                time.sleep(1.1)
        self.assertEqual(code, 0, f"the fetch through {through} failed")

    def paper_(self, command, **kwargs) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            command(Namespace(**{"book": "loop", **kwargs}))
        return out.getvalue()

    def test_a_seal_lands_on_the_second_fetch_with_one_deposit_and_no_loan(self):
        self.fetch(dt.date(2026, 9, 30))
        data_dir = self.dir / "data"
        saved = (paper.DATA, paper.SNAPSHOT, paper.CASH_FILE, paper.PAPER_DIR)
        paper.DATA = data_dir
        paper.SNAPSHOT = data_dir / "current" / "market_daily.csv"
        paper.CASH_FILE = data_dir / "current" / "cash_daily.csv"
        (data_dir / "paper").mkdir(parents=True, exist_ok=True)
        paper.PAPER_DIR = data_dir / "paper"
        try:
            anchored = self.paper_(paper.command_init, model="tilt_band", asof=None, comparator=None, tilt=None,
                                   band=None)
            self.assertIn("anchored loop", anchored)
            self.assertEqual(len(paper.read(paper.PAPER_DIR / "books" / "loop" / "ledger.jsonl")), 1)
            self.fetch(dt.date(2026, 10, 30))
            self.paper_(paper.command_step)
            chain = paper.read(paper.PAPER_DIR / "books" / "loop" / "ledger.jsonl")
            self.assertEqual(len(chain), 2, "the second fetch produced no sealable interval")
            head = chain[-1]
            self.assertEqual(head.asof, dt.date(2026, 10, 30))
            self.assertAlmostEqual(head.closing_value, sum(
                h.units * {q.symbol: q.close for q in head.quotes}[h.symbol] for h in head.holdings) +
                paper.recover_cash(head, {q.symbol: q.close for q in head.quotes}, 0.0,
                                   {h.symbol: h.units for h in head.holdings}), delta=0.01)
            self.assertGreaterEqual(head.closing_value, 0.0)
            prices = {q.symbol: q.close for q in head.quotes}
            self.assertGreaterEqual(paper.recover_cash(head, prices, 0.0, {h.symbol: h.units for h in head.holdings}),
                                    -0.005, "a plan that never borrows ended the interval owing money")
            self.assertTrue(bool(paper.verify(paper.PAPER_DIR / "books" / "loop" / "ledger.jsonl")))
            self.assertTrue(bool(paper.verify(paper.PAPER_DIR / "books" / "loop" / "shadow.jsonl")))
            self.assertEqual(head.violations, ())
        finally:
            (paper.DATA, paper.SNAPSHOT, paper.CASH_FILE, paper.PAPER_DIR) = saved


if __name__ == "__main__":
    unittest.main()
