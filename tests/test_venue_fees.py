"""Tests for the Coinbase cost stack: measured where it can be measured, ingested where it cannot, and never priced on a guess.

The important test in this file is the one where there is no fee record at all: the tool must refuse, name what it tried, and leave the
caller unable to run. A quiet default of 60 bps would be the same mistake the equity book made with a loan quote it never re-priced.
"""

from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import contextlib
import re
import sys
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stdout, redirect_stderr
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import venue_fees as vf                                                        # noqa: E402

TODAY = date(2026, 9, 8)


class FakeVenue:
    """The public endpoints this tool uses, answering with fixed numbers so the arithmetic and the refusals can be asserted offline.

    The answers reproduce what the venue actually said on 2026-09-08: a one-cent BTC book, no `USDC-USD` product at all (404), a USDC-USD
    quote of exactly 1, and the USDC-quoted coin books delisted.
    """

    def __init__(self, bid=78_576.96, ask=78_576.97, retail_buy=78_624.895, usdc_quote="1",
                 usdc_book_status=404, usdc_quoted=("BTC-USDC", "ETH-USDC")):
        self.books = {"BTC-USD": (bid, ask), "ETH-USD": (2_491.09, 2_491.10)}
        self.retail_buy = retail_buy
        self.usdc_quote = usdc_quote
        self.usdc_book_status = usdc_book_status
        self.products = [{"id": "BTC-USD", "quote_currency": "USD", "status": "online", "trading_disabled": False}]
        self.products += [{"id": pid, "quote_currency": "USDC", "status": "delisted", "trading_disabled": True}
                          for pid in usdc_quoted]
        self.products.append({"id": "USDT-USDC", "quote_currency": "USDC", "status": "online", "trading_disabled": False})
        self.widths = []

    def __call__(self, url: str) -> bytes:
        if url.endswith("/products"):
            return json.dumps(self.products).encode()
        if "/book" in url:
            pair = url.split("/products/")[1].split("/book")[0]
            self.widths.append(pair)
            if pair == "USDC-USD":
                if self.usdc_book_status == 404:
                    raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
                bid, ask = 0.99995, 1.00005
                return json.dumps({"bids": [[str(bid), "1", 1]], "asks": [[str(ask), "1", 1]]}).encode()
            bid, ask = self.books[pair]
            return json.dumps({"bids": [[str(bid), "1", 1]], "asks": [[str(ask), "1", 1]]}).encode()
        if "/buy" in url and "USDC-USD" in url:
            return json.dumps({"data": {"amount": self.usdc_quote, "base": "USDC", "currency": "USD"}}).encode()
        if "/buy" in url:
            return json.dumps({"data": {"amount": str(self.retail_buy)}}).encode()
        raise AssertionError(f"unexpected url {url}")


class TheConversionLine(unittest.TestCase):
    """Step 1's second clause. The objective asked for the conversion line; the venue's answer is that there is no market to price."""

    def test_the_probe_records_that_there_is_no_usdc_usd_market_and_no_executable_usdc_coin_book(self):
        with _patched(FakeVenue()):
            facts = vf.measure()["conversion"]["USDC-USD"]
        self.assertFalse(facts["product_listed"], "the venue lists no USDC-USD product; a test that assumed one would be fiction")
        self.assertIn("404", facts["book"]["error"])
        self.assertEqual(facts["public_quote"], "1", "the public quote is exact parity: both legs are dollars")
        self.assertFalse(facts["usdc_quoted_coins"]["BTC-USDC"]["tradable"], "BTC-USDC is delisted, so that route is not executable")
        self.assertEqual(facts["online_usdc_quoted"], ["USDT-USDC"])

    def test_the_report_prints_the_answers_and_uses_the_word_that_is_actually_true(self):
        with _patched(FakeVenue()):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertRaises(SystemExit, vf.report)                              # no fee record yet: the report must refuse
        joined = out.getvalue()
        self.assertIn("listed on the exchange: False", joined)
        self.assertIn("BTC-USDC NOT executable", joined)
        self.assertIn("unpriced", joined, "'free' and 'unpriced' are different claims and the tool may only make the second")
        self.assertIn("idle USD", joined, "the open question — what idle cash earns — has to be named, not smoothed over")

    def test_the_tool_invents_no_conversion_cost_of_its_own(self):
        """A conversion line with no market is exactly the place a plausible number would sneak in."""

        source = (ROOT / "tools" / "venue_fees.py").read_text()
        self.assertEqual(re.findall(r"(?m)^[A-Z][A-Z_0-9]*(CONVERSION|PEG|USDC)[A-Z_0-9]*\s*=\s*[\d.]+", source), [])
        self.assertNotIn("conversion_bps", source)


@contextlib.contextmanager
def _patched(venue):
    original = vf._get
    vf._get = venue
    try:
        yield venue
    finally:
        vf._get = original


class AFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "venues"
        self._saved = (vf.VENUE_DIR, vf.RECORD, vf.MEASURES)
        vf.VENUE_DIR, vf.RECORD = root, root / "coinbase-us-spot-v1.json"
        vf.MEASURES = root / "measures.jsonl"
        self.addCleanup(setattr, vf, "VENUE_DIR", self._saved[0])
        self.addCleanup(setattr, vf, "RECORD", self._saved[1])
        self.addCleanup(setattr, vf, "MEASURES", self._saved[2])
        self._get = vf._get
        vf._get = FakeVenue()
        self.addCleanup(setattr, vf, "_get", self._get)

    def record(self, as_of: str = "2026-09-08") -> dict:
        return vf.ingest("advanced-trade", 60.0, 40.0, "test tier", as_of, "fixture numbers, not a real schedule", None)


class MeasuredParts(AFixture):
    def test_the_touch_is_read_from_the_price_not_the_size(self):
        """The first implementation read Coinbase's book rows backwards (they are [price, size, fills]) and reported a 18,879 bps
        spread, which is the shape of error that survives because it looks like a finding."""

        facts = vf.measure()["books"]["BTC-USD"]
        self.assertAlmostEqual(facts["bid"], 78_576.96)
        self.assertAlmostEqual(facts["touch_bps"], 0.001, places=3)
        self.assertLess(facts["touch_bps"], 1.0, "a one-cent-wide book on a $78k asset is not a 100 bps cost")

    def test_the_retail_quote_line_is_reported_as_a_markup_not_a_fee(self):
        facts = vf.measure()["retail_quote"]["BTC-USD"]
        self.assertAlmostEqual(facts["markup_bps_vs_mid"], 6.1, places=1)


class TheFeeIsIngested(AFixture):
    def test_a_run_refuses_without_a_record_and_names_what_it_could_not_reach(self):
        err = io.StringIO()
        with self.assertRaises(SystemExit) as caught, redirect_stderr(err):
            vf.taker_bps("BA-005")
        message = str(caught.exception) + err.getvalue()
        for fragment in ("will not guess", "help.coinbase.com", "403", "web.archive.org", "ingest"):
            self.assertIn(fragment, message, f"the refusal is missing {fragment!r}")

    def test_ingesting_records_the_date_which_is_the_whole_point_of_the_record(self):
        facts = self.record()
        self.assertEqual(facts["as_of"], "2026-09-08")
        self.assertEqual(vf.taker_bps("BA-005", today=TODAY), 60.0)
        self.assertEqual(json.loads(vf.RECORD.read_text())["taker_bps"], 60.0)

    def test_a_stale_record_refuses_rather_than_pricing_on_a_number_it_cannot_see(self):
        self.record(as_of=(TODAY - timedelta(days=vf.MAX_AGE_DAYS + 1)).isoformat())
        with self.assertRaises(SystemExit) as caught:
            vf.taker_bps("BA-005", today=TODAY)
        self.assertIn("days old", str(caught.exception))

    def test_the_ages_just_inside_and_just_outside_the_limit_are_different_answers(self):
        """The limit is a line, so the two sides of it have to be tested separately (rule 105's 'immaterial' lesson)."""

        self.record(as_of=(TODAY - timedelta(days=vf.MAX_AGE_DAYS)).isoformat())
        self.assertEqual(vf.taker_bps("BA-005", today=TODAY), 60.0)
        self.record(as_of=(TODAY - timedelta(days=vf.MAX_AGE_DAYS + 1)).isoformat())
        with self.assertRaises(SystemExit):
            vf.taker_bps("BA-005", today=TODAY)

    def test_an_ingested_text_is_hashed_and_not_trusted(self):
        tmp = Path(self.tmp.name) / "page.txt"
        text = "taker 0.60% maker 0.40%"
        tmp.write_text(text)
        facts = vf.ingest("exchange", 50.0, 0.0, "intro", "2026-09-08", "operator copy", tmp)
        self.assertEqual(facts["supplied_bytes"], len(text))
        self.assertEqual(len(facts["supplied_text_sha256"]), 64)

    def test_a_previous_record_is_kept_when_a_new_tier_is_ingested(self):
        self.record(as_of="2026-08-01")
        first = json.loads(vf.RECORD.read_text())["as_of"]
        vf.RECORD.write_text(json.dumps({"recorded_at": "20260801T000000Z", "as_of": first}))
        self.record(as_of="2026-09-08")
        archived = [p for p in vf.VENUE_DIR.glob("coinbase-us-spot-*.json") if p.stem != "coinbase-us-spot-v1"]
        self.assertEqual(len(archived), 1, "the superseded record should survive as a file, not vanish")

    def test_an_unrecognised_product_is_refused_rather_than_defaulted(self):
        with self.assertRaises(SystemExit):
            vf.ingest("robinhood", 60.0, 40.0, "t", "2026-09-08", "", None)
        with self.assertRaises(SystemExit):
            vf.ingest("exchange", 60.0, 40.0, "t", "8 Sep 2026", "", None)


class ThereIsNoFeeDefault(unittest.TestCase):
    def test_the_module_holds_no_fee_number_of_its_own(self):
        """Rule 103: an unreachable fallback must be unreachable by construction, not by careful reading.

        No module constant may carry a fee. The only numbers in the file are the ones the fixture injects and the ones the operator
        ingests, so there is nothing for a run to fall back to.
        """

        source = (ROOT / "tools" / "venue_fees.py").read_text()
        self.assertNotIn("GUESS", source, "this file may not own a guess")
        offenders = re.findall(r"(?m)^[A-Z][A-Z_0-9]*(FEE|BPS|TAKER|MAKER)[A-Z_0-9]*\s*=\s*[\d.]+", source)
        self.assertEqual(offenders, [], f"a fee constant crept in: {offenders}")

    def test_the_probe_log_is_carried_by_the_refusal_not_only_by_the_docstring(self):
        self.assertGreaterEqual(len(vf.PROBE_LOG), 3)
        for probe in vf.PROBE_LOG:
            self.assertTrue(probe.get("outcome"), "a probe without an outcome is decoration")
            self.assertTrue(probe.get("note"), "an outcome without a meaning is decoration")


class TheMeasurementArchive(AFixture):
    """`snapshot` is step 1's `dated, sourced, hashed` applied to the half of the stack that can be fetched.

    It must stay hermetic — the first version of this class forgot to inherit the fixture and appended six real probe runs to the real
    archive, which is exactly how an append-only file learns to lie — and it must never become a licence.
    """

    def test_the_fixture_moves_the_archive_off_the_real_tree(self):
        self.assertIn("tmp", str(vf.MEASURES.parent).lower(), f"a test aimed at {vf.MEASURES} would write the artifact it is testing")

    def test_every_url_that_was_read_is_archived_with_its_own_hash(self):
        self.assertEqual(vf.snapshot(), 0)
        line = json.loads(vf.MEASURES.read_text().splitlines()[0])
        recorded = {probe["url"]: probe for probe in line["probes"]}
        venue = FakeVenue()
        for url in (vf.BOOK.format(pair="BTC-USD"), vf.BOOK.format(pair="ETH-USD"),
                    vf.QUOTE.format(pair="BTC-USD", side="buy"), vf.CONVERSION_QUOTE, vf.PRODUCT_LIST):
            self.assertIn(url, recorded, f"{url} was read by the tool and not recorded")
            expected = hashlib.sha256(venue(url)).hexdigest()
            self.assertEqual(recorded[url]["sha256"], expected, f"the archived hash for {url} is not the hash of what was fetched")
            self.assertEqual(recorded[url]["bytes"], len(venue(url)))

    def test_an_archived_measurement_still_does_not_license_a_price(self):
        """The one failure mode worth programming against: a fresh spread measurement read as permission to trade."""

        vf.snapshot()
        with self.assertRaises(SystemExit):
            vf.taker_bps("ba006")

    def test_the_archive_appends_and_never_rewrites_what_is_already_there(self):
        vf.snapshot()
        first = vf.MEASURES.read_bytes()
        vf.snapshot()
        after = vf.MEASURES.read_bytes()
        self.assertTrue(after.startswith(first), "an append-only archive that rewrites its first line is not append-only")
        self.assertEqual(len(after.splitlines()), 2)

    def test_the_archive_records_that_the_fee_record_is_absent_rather_than_omitting_the_question(self):
        vf.snapshot()
        line = json.loads(vf.MEASURES.read_text().splitlines()[0])
        self.assertFalse(line["fee_record_present"])
        self.assertIsNone(line["fee_record"])
        record = self.record()
        vf.snapshot()
        line = json.loads(vf.MEASURES.read_text().splitlines()[-1])
        self.assertTrue(line["fee_record_present"])
        self.assertEqual(line["fee_record"]["as_of"], record["as_of"])
        self.assertEqual(len(line["fee_record"]["file_sha256"]), 64, "the fee record gets the same hash treatment as a fetched page")

    def test_report_names_the_archive_so_its_age_is_visible_before_a_run(self):
        vf.snapshot()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertRaises(SystemExit, vf.report)                        # still no fee record: report still refuses
        self.assertIn("measured archive", out.getvalue())



if __name__ == "__main__":
    unittest.main()
