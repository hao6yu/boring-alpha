"""Offline tests for the perp cross-section fetcher: no request leaves the process, and the fake archive is the only exchange these tests know.

The interesting cases are the ones the decision record declares: the record's floor is what the archive serves (not the class book's launch
month), and it is discovered by listing keys, so a delisted symbol keeps its whole history; months before the floor are expected absences
and not holes; a day missing inside a served month *is* a hole; the session still in progress is not a session; funding never reaches into
the running month or before its instrument's own listing; and a poisoned row refuses the whole fetch.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
import urllib.parse
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import fetch_perps as fp                                                        # noqa: E402

S3 = fp.S3_BASE
TODAY = date(2026, 9, 9)
LAST_COMPLETE = "2026-08"
_NO_POISON = object()


def make_zip(name: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, text)
    return buffer.getvalue()


def kline_csv(days, poison=None, holes=()):
    """One month of daily rows from an iterable of date objects; 12 columns, ms stamps, like the archive ships."""

    lines = ["open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore"]
    for day in days:
        if day in holes:
            continue
        open_ms = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
        price = 100.0 + day.toordinal() % 50
        close_ms = open_ms + 86_399_999
        high, low = price + 1.0, price - 1.0
        if day == poison:
            high, low = low - 5.0, low                                          # a high below the low: not a candle
        lines.append(f"{open_ms},{price:.2f},{high:.2f},{low:.2f},{price:.2f},10.0,{close_ms},1000.0,5,500.0,500.0,0")
    return "\n".join(lines) + "\n"


def funding_csv(days, rate="0.0001", poison_rate=_NO_POISON, interval="8"):
    """Funding events for each date given at a declared cadence; one poisoned rate breaks the band."""

    lines = ["calc_time,funding_interval_hours,last_funding_rate"]
    for day in days:
        for hour in range(0, 24, int(interval)):
            ms = int(datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc).timestamp() * 1000)
            value = rate if poison_rate is _NO_POISON or hour != int(interval) else poison_rate
            lines.append(f"{ms},{interval},{value}")
    return "\n".join(lines) + "\n"


def prefix_listing_xml(prefix, symbols):
    entries = "".join(f"<CommonPrefixes><Prefix>{prefix}{s}/</Prefix></CommonPrefixes>" for s in sorted(symbols))
    return (f'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<Prefix>{prefix}</Prefix><IsTruncated>false</IsTruncated>{entries}</ListBucketResult>").encode()


def key_listing_xml(keys):
    entries = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
    return (f'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<IsTruncated>false</IsTruncated>{entries}</ListBucketResult>").encode()


class FakeArchive:
    """An S3 archive with a floor date, an optional delisting date, holes, and a memory of every URL it was asked for."""

    def __init__(self, kline_symbols=("BTCUSDT",), funding_symbols=("BTCUSDT",),
                 floor=date(2021, 6, 1), dead_after=None, holes=(), poison=None, poison_rate=None):
        self.kline_symbols, self.funding_symbols = set(kline_symbols), set(funding_symbols)
        self.floor, self.dead_after = floor, dead_after
        self.holes, self.poison, self.poison_rate = set(holes), poison, poison_rate
        self.urls: list[str] = []

    # -- model helpers ----------------------------------------------------------------
    def floor_month(self) -> str:
        return f"{self.floor.year:04d}-{self.floor.month:02d}"

    def dead_month(self) -> str:
        if self.dead_after is None:
            return LAST_COMPLETE
        return f"{self.dead_after.year:04d}-{self.dead_after.month:02d}"

    def months(self) -> list[str]:
        first, last = self.floor_month(), self.dead_month()
        year, month = int(first[:4]), int(first[5:7])
        out = []
        while (year, month) <= (int(last[:4]), int(last[5:7])):
            out.append(f"{year:04d}-{month:02d}")
            month += 1
            if month == 13:
                year, month = year + 1, 1
        return out

    def days_of(self, ym: str, upto: date | None = None) -> list[date]:
        year, month = int(ym[:4]), int(ym[5:7])
        nxt = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
        day, out = max(date(year, month, 1), self.floor), []
        while day <= nxt:
            if day < (upto or date(9999, 12, 31)) and day not in self.holes and \
                    (self.dead_after is None or day <= self.dead_after):
                out.append(day)
            day += timedelta(days=1)
        return out

    # -- the archive -------------------------------------------------------------------
    def __call__(self, url: str) -> bytes | None:
        self.urls.append(url)
        parsed = urllib.parse.urlparse(url)
        path = urllib.parse.unquote(parsed.path.lstrip("/"))                    # the fetcher percent-encodes symbols; the model speaks raw
        if path.startswith("data.binance.vision/"):
            path = path[len("data.binance.vision/"):]                            # the bucket name rides in the path; drop it
        query = urllib.parse.parse_qs(parsed.query)
        if "prefix=" in parsed.query:
            prefix = query["prefix"][0]
            if "delimiter=/" in parsed.query:
                symbols = self.kline_symbols if prefix.startswith("data/futures/um/daily/klines") else self.funding_symbols
                return prefix_listing_xml(prefix, symbols)
            parts = prefix.rstrip("/").split("/")
            if "/monthly/klines/" in prefix:
                sym = parts[-2]
                keys = [f"data/futures/um/monthly/klines/{sym}/1d/{sym}-1d-{ym}.zip" for ym in self.months()]
                return key_listing_xml(keys)
            if "/daily/klines/" in prefix:
                sym = parts[-3]
                tail = parts[-1].replace(f"{sym}-1d-", "")                  # the current month, as YYYY-MM-
                ym = tail[:7]
                keys = [f"data/futures/um/daily/klines/{sym}/1d/{sym}-1d-{d.isoformat()}.zip"
                        for d in self.days_of(ym, upto=TODAY)]
                return key_listing_xml(keys)
            if "/monthly/fundingRate/" in prefix:
                sym = parts[-1]
                keys = [f"data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip" for ym in self.months()]
                return key_listing_xml(keys)
            raise AssertionError(f"fake archive does not know the listing {url}")
        if path.startswith("data/futures/um/monthly/klines/"):
            parts = path.split("/")
            sym, ym = parts[5], parts[7].replace(f"{parts[5]}-1d-", "").replace(".zip", "")
            days = self.days_of(ym, upto=TODAY)
            if ym > LAST_COMPLETE or not days:
                return None
            return make_zip(f"{sym}-1d-{ym}.zip", kline_csv(days, poison=self.poison, holes=self.holes))
        if path.startswith("data/futures/um/daily/klines/"):
            parts = path.split("/")
            sym, ymd = parts[5], parts[7].replace(f"{parts[5]}-1d-", "").replace(".zip", "")
            day = date.fromisoformat(ymd)
            if day < self.floor or day >= TODAY or day in self.holes or (self.dead_after and day > self.dead_after):
                return None
            return make_zip(f"{sym}-1d-{ymd}.zip", kline_csv([day], poison=self.poison))
        if path.startswith("data/futures/um/monthly/fundingRate/"):
            parts = path.split("/")
            sym, ym = parts[5], parts[6].replace(f"{parts[5]}-fundingRate-", "").replace(".zip", "")
            if ym > LAST_COMPLETE:
                return None
            days = self.days_of(ym)
            if not days:
                return None
            return make_zip(f"{sym}-fundingRate-{ym}.zip",
                            funding_csv(days, poison_rate=self.poison_rate if self.poison_rate else _NO_POISON))
        raise AssertionError(f"fake archive does not know {url}")


class AFakeArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "perps"
        self._swap = (fp.PERPS, fp.SNAPSHOTS, fp.CURRENT)
        fp.PERPS, fp.SNAPSHOTS, fp.CURRENT = root, root / "snapshots", root / "current"
        self.addCleanup(lambda: (setattr(fp, "PERPS", self._swap[0]), setattr(fp, "SNAPSHOTS", self._swap[1]),
                                 setattr(fp, "CURRENT", self._swap[2])))

    def serve(self, archive: FakeArchive):
        self._get = fp._get
        fp._get = archive
        self.addCleanup(setattr, fp, "_get", self._get)
        return archive


class TheFloorIsServed(AFakeArchive):
    def test_the_record_starts_where_the_archive_starts_not_where_the_class_book_says(self):
        """A symbol whose served months begin 2021-06 has that month as its floor, and the manifest says so."""

        self.serve(FakeArchive(floor=date(2021, 6, 1)))
        rows, events, manifest = fp.fetch(today=TODAY)
        facts = manifest["per_symbol"]["BTCUSDT"]
        self.assertEqual(facts["first_month"], "2021-06")
        self.assertEqual(facts["first_candle"], "2021-06-01")

    def test_absent_months_before_the_floor_are_never_requested_and_never_holes(self):
        """The walk is a listing: months the archive never served for this symbol are not even asked for, and are not holes."""

        archive = self.serve(FakeArchive(floor=date(2021, 6, 1)))
        rows, events, manifest = fp.fetch(today=TODAY)
        self.assertEqual(manifest["per_symbol"]["BTCUSDT"].get("day_holes", []), [])
        self.assertNotIn(fp.KLINE_MONTHLY_URL.format(sym="BTCUSDT", ym="2020-01"), archive.urls)

    def test_the_universe_is_enumerated_and_counted(self):
        self.serve(FakeArchive(kline_symbols=("AAAUSDT", "BTCUSDT"), funding_symbols=("BTCUSDT",)))
        rows, events, manifest = fp.fetch(today=TODAY)
        self.assertEqual(manifest["universe"]["kline_symbols"], 2)
        self.assertEqual(manifest["universe"]["funding_symbols"], 1)
        self.assertEqual(manifest["funding_per_symbol"]["AAAUSDT"].get("note"), "no funding directory in this archive")


class TheSessionInProgressIsNotASession(AFakeArchive):
    def test_today_is_dropped_everywhere(self):
        """A daily zip for the running day is served by the fake and still never reaches the archive."""

        self.serve(FakeArchive(floor=date(2021, 6, 1)))
        rows, events, manifest = fp.fetch(today=TODAY)
        self.assertEqual(manifest["per_symbol"]["BTCUSDT"]["last_candle"], (TODAY - timedelta(days=1)).isoformat())
        self.assertTrue(all(r["date"] < TODAY for r in rows))
        stamps = [datetime.fromtimestamp(e["ts_ms"] / 1000, timezone.utc).date() for e in events]
        self.assertTrue(all(stamp < TODAY for stamp in stamps))


class HolesAreReported(AFakeArchive):
    def test_a_hole_inside_a_served_month_is_reported_never_stitched(self):
        hole = date(2023, 3, 14)
        self.serve(FakeArchive(floor=date(2021, 6, 1), holes={hole}))
        rows, events, manifest = fp.fetch(today=TODAY)
        self.assertIn(hole.isoformat(), manifest["per_symbol"]["BTCUSDT"]["day_holes"])

    def test_a_delisted_symbol_keeps_its_whole_history_and_reports_no_holes(self):
        """FTTUSDT-style death: the key listing ends at the delisting month, no walk stops early, and trailing absences are not holes."""

        self.serve(FakeArchive(floor=date(2021, 6, 1), dead_after=date(2023, 4, 18)))
        rows, events, manifest = fp.fetch(today=TODAY)
        facts = manifest["per_symbol"]["BTCUSDT"]
        self.assertEqual(facts["last_month"], "2023-04")
        self.assertEqual(facts.get("day_holes", []), [])
        self.assertTrue(all(r["date"] <= date(2023, 4, 18) for r in rows))

    def test_a_month_gap_between_first_and_last_served_month_is_counted(self):
        """A symbol the archive served, stopped serving, and served again shows the gap as a count, not as silence."""

        archive = FakeArchive(floor=date(2021, 6, 1))
        original = archive.months

        def months_with_gap():
            return [ym for ym in original() if not ym.startswith("2022")]   # the whole of 2022 vanishes from the listing

        archive.months = months_with_gap
        self.serve(archive)
        rows, events, manifest = fp.fetch(today=TODAY)
        facts = manifest["per_symbol"]["BTCUSDT"]
        self.assertEqual(facts["month_gaps"], 12)
        self.assertEqual(facts["first_month"], "2021-06")
        self.assertEqual(facts["last_month"], "2026-08")


class PoisonRefusesTheWholeFetch(AFakeArchive):
    def test_an_impossible_candle_refuses_the_fetch(self):
        poison = date(2023, 3, 14)
        self.serve(FakeArchive(floor=date(2021, 6, 1), poison=poison))
        with self.assertRaises(SystemExit):
            fp.fetch(today=TODAY)

    def test_a_funding_rate_outside_the_band_refuses_the_fetch(self):
        self.serve(FakeArchive(floor=date(2021, 6, 1), poison_rate="0.5"))
        with self.assertRaises(SystemExit):
            fp.fetch(today=TODAY)


class FundingDiscipline(AFakeArchive):
    def test_funding_never_requests_the_running_month(self):
        archive = self.serve(FakeArchive(floor=date(2021, 6, 1)))
        fp.fetch(today=TODAY)
        current = fp.FUNDING_MONTHLY_URL.format(sym="BTCUSDT", ym=TODAY.strftime("%Y-%m"))
        self.assertNotIn(current, archive.urls)

    def test_funding_cannot_precede_the_instrument_listing(self):
        """A symbol listed 2021-06 never has a funding request earlier than its own floor month."""

        archive = self.serve(FakeArchive(floor=date(2021, 6, 1)))
        fp.fetch(today=TODAY)
        asked = [u for u in archive.urls if "fundingRate" in u and u.endswith(".zip")]
        self.assertTrue(asked)
        for url in asked:
            ym = url.split("fundingRate-")[1][:7]
            self.assertGreaterEqual(ym, "2021-06", url)

    def test_funding_events_arrive_sorted_and_parsed(self):
        self.serve(FakeArchive(floor=date(2021, 6, 1)))
        rows, events, manifest = fp.fetch(today=TODAY)
        self.assertEqual(manifest["funding_per_symbol"]["BTCUSDT"]["first_month"], "2021-06")
        self.assertEqual([e["ts_ms"] for e in events], sorted(e["ts_ms"] for e in events))
        self.assertTrue(all(e["interval_hours"] == 8.0 for e in events))

    def test_the_declared_cadence_family_is_accepted_and_the_undeclared_refused(self):
        """1h, 2h, 4h, 8h are the archive's declared cadences (1h measured on the newest listings); 3h is not a rate cadence."""

        self.serve(FakeArchive(floor=date(2021, 6, 1)))
        for interval in ("1", "2", "4", "8"):
            blob = make_zip("f.zip", funding_csv([date(2023, 3, 14)], interval=interval))
            events = fp.parse_funding_csv(blob, "BTCUSDT")
            self.assertTrue(all(e["interval_hours"] == float(interval) for e in events), interval)
        with self.assertRaises(SystemExit):
            fp.parse_funding_csv(make_zip("f.zip", funding_csv([date(2023, 3, 14)], interval="3")), "BTCUSDT")


class TheWorkspaceIsResumable(AFakeArchive):
    def workspace_pass(self):
        workspace, progress = fp.open_workspace(TODAY)
        manifest, counter, remaining = fp.fetch_into_workspace(workspace, progress, TODAY)
        return workspace, progress, manifest, counter, remaining

    def test_the_manifest_pins_the_sha256_of_every_csv(self):
        self.serve(FakeArchive(floor=date(2021, 6, 1)))
        workspace, progress, manifest, counter, remaining = self.workspace_pass()
        self.assertEqual(remaining, [])
        target = fp.finalize_workspace(workspace, progress, manifest, counter)
        self.assertEqual(manifest["sha256"][fp.PRICES],
                         hashlib.sha256((target / fp.PRICES).read_bytes()).hexdigest())
        self.assertEqual(manifest["sha256"][fp.FUNDING],
                         hashlib.sha256((target / fp.FUNDING).read_bytes()).hexdigest())
        self.assertTrue(json.loads((target / "manifest.json").read_text())["synthetic"] is False)

    def test_the_current_pointer_moves_and_finalized_snapshots_are_immutable(self):
        self.serve(FakeArchive(floor=date(2021, 6, 1)))
        workspace, progress, manifest, counter, remaining = self.workspace_pass()
        target = fp.finalize_workspace(workspace, progress, manifest, counter)
        self.assertTrue(fp.CURRENT.is_symlink())
        with self.assertRaises(SystemExit):
            fp.finalize_workspace(workspace, progress, manifest, counter)

    def test_an_interrupted_pass_resumes_and_the_result_matches_a_single_pass(self):
        """The whole point of the workspace: a killed fetch loses nothing but the symbol in flight, and the parts reassemble identically."""

        archive = FakeArchive(floor=date(2021, 6, 1), kline_symbols=("AAAUSDT", "BTCUSDT"), funding_symbols=("BTCUSDT",))
        self.serve(archive)

        workspace, progress = fp.open_workspace(TODAY)
        symbols = sorted(archive.kline_symbols)
        first, second = symbols[0], symbols[1]
        # a "crash": symbol one completes fully (parts and ledger), then the process dies before the next symbol begins
        counter = {"requests": 0, "absent": 0}
        rows, events, stats, fstats = fp.fetch_symbol_with_funding(first, archive.funding_symbols, TODAY, counter)
        with (workspace / "parts" / f"{first}.prices.csv").open("w", newline="") as handle:
            handle.write("date,symbol,open,high,low,close,base_volume,quote_volume\n")
            for row in rows:
                handle.write(f"{row['date'].isoformat()},{first},{row['open']:.8g},{row['high']:.8g},{row['low']:.8g},"
                             f"{row['close']:.8g},{row['base_volume']:.10g},{row['quote_volume']:.10g}\n")
        with (workspace / "parts" / f"{first}.funding.csv").open("w", newline="") as handle:
            handle.write("ts_utc,symbol,interval_hours,rate\n")
        fp._atomic_json(workspace / "parts" / f"{first}.stats.json", {"prices": stats, "funding": fstats})
        fp.mark_done(workspace, progress, first)
        self.assertIn(first, progress["done"])
        archive.urls.clear()                                                 # the crash boundary: the resumed process remembers nothing

        # resume: the ledger skips the finished symbol — not one request asks the archive for it again — and the rest complete
        manifest, counter, remaining = fp.fetch_into_workspace(workspace, progress, TODAY)
        self.assertEqual(remaining, [])
        self.assertTrue(all(first not in url for url in archive.urls),
                        "the resume refetched a symbol the ledger had finished")
        target = fp.finalize_workspace(workspace, progress, manifest, counter)

        # the reference: one clean pass into a fresh workspace, same archive, identical bytes
        workspace2, progress2 = fp.open_workspace(TODAY)
        progress2["done"] = {}
        manifest2, _, remaining2 = fp.fetch_into_workspace(workspace2, progress2, TODAY)
        fp.finalize_workspace(workspace2, progress2, manifest2, {"requests": 0, "absent": 0})
        reference = sorted(fp.SNAPSHOTS.glob("*"))[-1]
        self.assertEqual((target / fp.PRICES).read_text(), (reference / fp.PRICES).read_text())
        self.assertEqual((target / fp.FUNDING).read_text(), (reference / fp.FUNDING).read_text())


if __name__ == "__main__":
    unittest.main()


class TheUniverseIsTheArchiveS(AFakeArchive):
    def test_a_symbol_whose_name_is_not_ascii_is_fetched_not_filtered(self):
        """The archive lists Chinese-named symbols; the fetch percent-encodes the request and archives the raw name."""

        archive = self.serve(FakeArchive(kline_symbols=("哈基米USDT",), funding_symbols=("哈基米USDT",)))
        rows, events, manifest = fp.fetch(today=TODAY)
        self.assertIn("哈基米USDT", manifest["per_symbol"])
        encoded = urllib.parse.quote("哈基米USDT", safe="")
        self.assertTrue(any(encoded in u for u in archive.urls))

    def test_the_non_ascii_symbols_the_probe_found_are_in_this_universe_model(self):
        """Pins the fact that motivated the encoding: five Chinese-named listings exist in the real archive's symbol listing."""

        self.serve(FakeArchive(kline_symbols=("哈基米USDT", "币安人生USDT", "我踏马来了USDT", "牛来USDT", "龙虾USDT")))
        rows, events, manifest = fp.fetch(today=TODAY)
        self.assertEqual(len(manifest["per_symbol"]), 5)


class TheArchiveMustExist(AFakeArchive):
    def test_a_listing_that_answers_404_is_a_refusal_not_an_empty_universe(self):
        archive = self.serve(FakeArchive())

        def gone(url):
            return None if "prefix=" in url else archive(url)
        fp._get = gone
        with self.assertRaises(SystemExit):
            fp.fetch(today=TODAY)


if __name__ == "__main__":
    unittest.main()
