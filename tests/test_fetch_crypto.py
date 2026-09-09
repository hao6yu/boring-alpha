"""Offline tests for the crypto fetcher: no request leaves the process, and the fake source is the only exchange these tests know.

The interesting cases are the ones the endpoint taught this round: a window too wide answers 400, a date before the record is not a hole,
a day missing *after* the first candle is a hole, and the candle for a day still in progress is not a session.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import fetch_crypto as fc                                                    # noqa: E402


class FakeExchange:
    """A source with a floor, an optional hole, and a memory of every URL it was asked for."""

    def __init__(self, floor: date, today: date, holes=(), poison: date | None = None, serves_today=True):
        self.floor, self.today = floor, today
        self.holes, self.poison, self.serves_today = set(holes), poison, serves_today
        self.urls: list[str] = []
        self.widths: list[int] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        start = datetime.strptime(q["start"][0], "%Y-%m-%dT%H:%M:%SZ").date()
        end = datetime.strptime(q["end"][0], "%Y-%m-%dT%H:%M:%SZ").date()
        self.widths.append((end - start).days)
        rows = []
        day = max(start, self.floor)
        while day < min(end, self.today + timedelta(days=1)):
            if day >= self.floor and day not in self.holes and (day < self.today or self.serves_today):
                price = 100.0 + (day - self.floor).days
                row = [int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp()),
                       price - 1.0, price + 1.0, price, price + 0.5, 10.0]
                if day == self.poison:
                    row[2] = row[1] - 5.0                       # a high below the low: not a candle
                rows.append(row)
            day += timedelta(days=1)
        return json.dumps(sorted(rows, key=lambda r: -r[0])).encode()


class AFakeSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "crypto"
        self._swap = (fc.CRYPTO, fc.SNAPSHOTS, fc.CURRENT)
        fc.CRYPTO = root
        fc.SNAPSHOTS = root / "snapshots"
        fc.CURRENT = root / "current"
        self.addCleanup(lambda: setattr(fc, "CRYPTO", self._swap[0]) or setattr(fc, "SNAPSHOTS", self._swap[1])
                        or setattr(fc, "CURRENT", self._swap[2]))

    def serve(self, source: FakeExchange):
        self._get = fc._get
        fc._get = source
        self.addCleanup(setattr, fc, "_get", self._get)
        return source


class TheFloorIsProbed(AFakeSource):
    def test_the_record_starts_where_the_source_says_it_starts(self):
        """The floor the manifest reports is a fact about this endpoint, discovered by asking, not a date from a press release."""

        floor, today = date(2015, 7, 20), date(2015, 9, 1)
        src = self.serve(FakeExchange(floor, today))
        rows, manifest = fc.fetch(("BTC-USD",), today=today)
        self.assertEqual(manifest["pairs"]["BTC-USD"]["first_candle"], floor.isoformat())
        self.assertEqual(manifest["holes"], {}, "a source that serves every day after its floor has no holes")
        self.assertEqual(manifest["rows"], len(rows))

    def test_no_probe_window_is_wider_than_the_source_will_answer(self):
        """Coinbase answers 400 Bad Request for a page wider than ~300 daily candles. Every probe here stays under a month."""

        src = self.serve(FakeExchange(date(2019, 1, 1), date(2019, 3, 1)))
        fc.fetch(("BTC-USD",), today=date(2019, 3, 1))
        self.assertLessEqual(max(src.widths), 30, f"the widest request was {max(src.widths)} days")

    def test_a_source_that_serves_nothing_at_all_is_a_refusal_not_an_empty_archive(self):
        src = self.serve(FakeExchange(date(2099, 1, 1), date(2019, 3, 1)))
        with self.assertRaises(SystemExit) as caught:
            fc.fetch(("BTC-USD",), today=date(2019, 3, 1))
        self.assertIn("refusing to archive an empty record", str(caught.exception))

    def test_the_probed_floor_is_not_the_floor_the_record_gets(self):
        """The probe can land a day early. The record is dated from the first candle served, so the manifest cannot claim a hole that
        is really the start of the file."""

        floor, today = date(2017, 6, 12), date(2017, 7, 5)
        self.serve(FakeExchange(floor, today))
        _, manifest = fc.fetch(("BTC-USD",), today=today)
        self.assertLessEqual(manifest["pairs"]["BTC-USD"]["probed"], floor.isoformat())
        self.assertEqual(manifest["pairs"]["BTC-USD"]["first_candle"], floor.isoformat())
        self.assertEqual(manifest["holes"], {})


class ValidationRefuses(AFakeSource):
    def test_a_candle_that_is_not_a_candle_refuses_the_fetch_and_names_the_day(self):
        poison = date(2018, 3, 4)
        self.serve(FakeExchange(date(2018, 1, 1), date(2018, 4, 1), poison=poison))
        with self.assertRaises(SystemExit) as caught:
            fc.fetch(("BTC-USD",), today=date(2018, 4, 1))
        self.assertIn(poison.isoformat(), str(caught.exception))

    def test_the_day_still_in_progress_is_never_archived(self):
        today = date(2020, 5, 5)
        self.serve(FakeExchange(date(2020, 4, 1), today))
        rows, _ = fc.fetch(("BTC-USD",), today=today)
        self.assertNotIn(today, {r["date"] for r in rows}, "a fetch may not freeze an unfinished day")
        self.assertEqual(max(r["date"] for r in rows), today - timedelta(days=1))

    def test_a_day_missing_after_the_first_candle_is_reported_as_a_hole_not_stitched(self):
        today = date(2021, 2, 10)
        self.serve(FakeExchange(date(2021, 1, 2), today, holes=[date(2021, 1, 21), date(2021, 1, 22)]))
        rows, manifest = fc.fetch(("BTC-USD",), today=today)
        self.assertEqual(manifest["holes"]["BTC-USD"]["holes"], 2)
        self.assertNotIn(date(2021, 1, 21), {r["date"] for r in rows})


class TheSnapshotIsImmutable(AFakeSource):
    def test_the_manifest_seals_the_bytes_it_ships(self):
        today = date(2022, 6, 20)
        self.serve(FakeExchange(date(2022, 5, 1), today))
        rows, manifest = fc.fetch(("BTC-USD",), today=today)
        target = fc.write_snapshot(rows, manifest, "20220620T000000Z")
        self.assertEqual(manifest["sha256"], hashlib.sha256((target / fc.PRICES).read_bytes()).hexdigest())
        self.assertTrue((target / "manifest.json").is_file())
        self.assertEqual(fc.CURRENT.readlink(), Path("snapshots") / "20220620T000000Z")

    def test_a_second_fetch_at_the_same_stamp_refuses_rather_than_rewriting_history(self):
        today = date(2022, 6, 20)
        self.serve(FakeExchange(date(2022, 5, 1), today))
        rows, manifest = fc.fetch(("BTC-USD",), today=today)
        fc.write_snapshot(rows, manifest, "20220620T000000Z")
        with self.assertRaises(SystemExit) as caught:
            fc.write_snapshot(rows, manifest, "20220620T000000Z")
        self.assertIn("immutable", str(caught.exception))


class TheArchivedRecordHolds(AFakeSource):
    """The live artifact, checked against itself: no network, but a real invariant on real bytes."""

    def setUp(self):
        super().setUp()
        self.manifest = json.loads((ROOT / "data/crypto/current/manifest.json").read_text())
        self.rows = [l.split(",") for l in
                     (ROOT / "data/crypto/current" / fc.PRICES).read_text().splitlines()[1:]]

    def test_every_pair_dates_its_record_from_a_candle_that_is_actually_in_the_file(self):
        for pair, facts in self.manifest["pairs"].items():
            dates = sorted(r[0] for r in self.rows if r[1] == pair)
            self.assertTrue(dates, f"{pair} archived no candles")
            self.assertEqual(dates[0], facts["first_candle"], f"{pair}: manifest first_candle disagrees with the file")
            self.assertLessEqual(facts["probed"], facts["first_candle"], "the probe may precede the data, never follow it")

    def test_the_reported_holes_are_the_holes_a_reader_finds_in_the_file(self):
        """Not a transcription: recomputed from the CSV, day by day, crypto having no weekend to hide behind."""

        for pair, hole in self.manifest.get("holes", {}).items():
            have = {r[0] for r in self.rows if r[1] == pair}
            first = date.fromisoformat(self.manifest["pairs"][pair]["first_candle"])
            last = max(date.fromisoformat(r[0]) for r in self.rows if r[1] == pair)
            missing = [first + timedelta(days=n) for n in range((last - first).days + 1)
                       if (first + timedelta(days=n)).isoformat() not in have]
            self.assertEqual(len(missing), hole["holes"], f"{pair}: the manifest's hole count is not the file's")
            self.assertEqual(missing[0].isoformat(), hole["first"])


class TheFiguresInBA005(unittest.TestCase):
    """A figure in a pre-registration is a figure no test runs (rule 100). These three are recomputed from the archived candles.

    They matter because BA-005's pass rule is decided by the ruin promise, so the depth of the worst fall is load-bearing prose: if a
    later fetch quietly changes the record, the spec's own failure condition has to be seen to move with it.
    """

    SPEC = (ROOT / "docs/strategies/BA-005.md").read_text()

    def setUp(self):
        self.px = []
        with (ROOT / "data/crypto/current" / fc.PRICES).open() as handle:
            for row in csv.DictReader(handle):
                if row["pair"] == "BTC-USD":
                    self.px.append((row["date"], float(row["close"])))

    def drawdown(self, first: str, last: str) -> float:
        peak, worst = -1.0, 0.0
        for day, price in self.px:
            if first <= day <= last:
                peak = max(peak, price)
                worst = min(worst, (price - peak) / peak)
        return -worst

    def test_the_three_depths_the_spec_quotes_are_the_depths_the_data_holds(self):
        self.assertAlmostEqual(self.drawdown("2015-01-01", "2026-12-31"), 0.838, places=3)
        self.assertAlmostEqual(self.drawdown("2021-11-08", "2022-12-31"), 0.767, places=3)
        self.assertAlmostEqual(self.drawdown("2024-01-01", "2026-09-07"), 0.531, places=3)

    def test_the_spec_prints_the_same_three_numbers_it_is_underwritten_by(self):
        for figure in ("83.8%", "76.7%", "53.1%"):
            self.assertIn(figure, self.SPEC, f"{figure} is computed but not published")

    def test_the_worst_fall_is_dated_not_mere_depth(self):
        peak, at = -1.0, None
        trough, from_day, to_day = 0.0, None, None
        for day, price in self.px:
            if price > peak:
                peak, at = price, day
            if (price - peak) / peak < trough:
                trough, from_day, to_day = (price - peak) / peak, at, day
        self.assertEqual((from_day, to_day), ("2017-12-16", "2018-12-15"))


if __name__ == "__main__":
    unittest.main()
