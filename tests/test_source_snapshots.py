"""Offline, constructed source normalization; no market files or network calls."""

from copy import deepcopy
import csv
from datetime import date
import io
import unittest
from unittest.mock import patch

from tools import build_ba002_source_snapshots as snapshots
from tools import tiingo_seen_reference as tiingo


def _rows(raw):
    return {(row["date"], row["symbol"]): row
            for row in csv.DictReader(io.StringIO(raw.decode()))}


def _yahoo():
    days = ["2012-09-28", "2012-10-31", "2012-11-01", "2012-11-02"]
    prices, distributions = [], []
    for day, raw, adjusted, opening in zip(days, (90., 100., 80., 82.),
                                           (45., 50., 40., 41.), (44., 49., 39., 40.5)):
        prices.extend([(day, "TLT", opening, adjusted), (day, "SPY", 15.5, 16.)])
        distributions.extend([(day, "TLT", raw, 0.), (day, "SPY", 20., 0.)])
    return (snapshots.csv_bytes(snapshots.COLUMNS["market_daily.csv"], prices),
            snapshots.csv_bytes(snapshots.COLUMNS["distributions_daily.csv"], distributions))


def _tiingo_row(close, dividend=0., split=1., adjusted_open=30., adjusted_close=31.):
    return {"open": close, "high": close + 1., "low": close - 1., "close": close,
            "volume": 100., "adjOpen": adjusted_open, "adjHigh": max(adjusted_open, adjusted_close) + 1.,
            "adjLow": min(adjusted_open, adjusted_close) - 1., "adjClose": adjusted_close,
            "adjVolume": 100., "divCash": dividend, "splitFactor": split}


def _tiingo_csv(entries):
    return snapshots.csv_bytes(tiingo.FIELDS, ([str(day), *(row[key] for key in tiingo.FIELDS[1:])]
                                              for day, row in entries))


class YahooRepairTests(unittest.TestCase):
    def test_both_adjusted_prices_change_only_strictly_before_the_ex_date(self):
        prices, distributions = _yahoo()
        repaired_prices, repaired_distributions, proof = snapshots.repair_yahoo(
            prices, distributions, dividend=2.)
        old_p, old_d, new_p, new_d = map(_rows, (prices, distributions, repaired_prices, repaired_distributions))
        self.assertEqual(set(old_p), set(new_p))
        self.assertEqual(set(old_d), set(new_d))
        for key, original in old_p.items():
            with self.subTest(key=key):
                if key[1] == "TLT" and key[0] < "2012-11-01":
                    self.assertAlmostEqual(float(new_p[key]["tr_open"]), float(original["tr_open"]) * .98)
                    self.assertAlmostEqual(float(new_p[key]["tr_close"]), float(original["tr_close"]) * .98)
                    self.assertNotEqual(new_p[key]["tr_open"], original["tr_open"])
                    self.assertNotEqual(new_p[key]["tr_close"], original["tr_close"])
                else:
                    self.assertEqual(new_p[key], original)
        for key, original in old_d.items():
            with self.subTest(distribution=key):
                self.assertEqual(new_d[key]["close"], original["close"])
                expected = "2.0" if key == ("2012-11-01", "TLT") else original["dividend"]
                self.assertEqual(new_d[key]["dividend"], expected)
        self.assertEqual(proof["pre_ex_price_multiplier"], .98)
        self.assertEqual(proof["previous_session"], "2012-10-31")
        self.assertEqual(proof["previous_raw_close"], 100.)
        self.assertEqual(proof["adjusted_price_rows_changed"], 2)
        self.assertEqual(proof["distribution_rows_changed"], 1)

    def test_backward_adjustment_uses_prior_raw_close_not_ex_date_price(self):
        prices, distributions = _yahoo()
        repaired, _, proof = snapshots.repair_yahoo(prices, distributions, dividend=2.)
        multiplier = proof["pre_ex_price_multiplier"]
        self.assertEqual(multiplier, 1. - 2. / 100.)
        self.assertNotEqual(multiplier, 1. - 2. / 80.)
        self.assertNotEqual(multiplier, 80. / 82.)
        self.assertEqual(float(_rows(repaired)["2012-10-31", "TLT"]["tr_close"]), 49.)

    def test_reapplying_the_correction_is_refused(self):
        prices, distributions = _yahoo()
        repaired_prices, repaired_distributions, _ = snapshots.repair_yahoo(prices, distributions, dividend=2.)
        with self.assertRaisesRegex(ValueError, "already present"):
            snapshots.repair_yahoo(repaired_prices, repaired_distributions, dividend=2.)

    def test_existing_adjusted_price_step_cannot_be_repaired_again(self):
        prices, distributions = _yahoo()
        prices = prices.replace(b"2012-11-01,TLT,39.0,40.0", b"2012-11-01,TLT,39.0,40.04")
        with self.assertRaisesRegex(ValueError, "absent adjusted-price step"):
            snapshots.repair_yahoo(prices, distributions, dividend=2.)

    def test_existing_dividend_is_not_silently_overwritten(self):
        prices, distributions = _yahoo()
        distributions = distributions.replace(b"2012-11-01,TLT,80.0,0.0", b"2012-11-01,TLT,80.0,1.0")
        with self.assertRaisesRegex(ValueError, "already present"):
            snapshots.repair_yahoo(prices, distributions, dividend=2.)

    def test_duplicate_prices_or_distributions_are_refused(self):
        prices, distributions = _yahoo()
        for altered_p, altered_d in ((prices + prices.splitlines(keepends=True)[1], distributions),
                                     (prices, distributions + distributions.splitlines(keepends=True)[1])):
            with self.subTest(price_duplicate=altered_p != prices), self.assertRaisesRegex(ValueError, "duplicate"):
                snapshots.repair_yahoo(altered_p, altered_d, dividend=2.)

    def test_missing_paired_session_is_refused(self):
        prices, distributions = _yahoo()
        prices = b"\n".join(line for line in prices.splitlines() if not line.startswith(b"2012-11-01,SPY")) + b"\n"
        with self.assertRaisesRegex(ValueError, "dates/symbols differ"):
            snapshots.repair_yahoo(prices, distributions, dividend=2.)

    def test_repair_requires_an_ex_date_and_an_earlier_session(self):
        prices, distributions = _yahoo()
        for day in (date(2012, 9, 28), date(2012, 10, 1)):
            with self.subTest(day=day), self.assertRaisesRegex(ValueError, "ex-date and a preceding session"):
                snapshots.repair_yahoo(prices, distributions, ex_date=day, dividend=2.)

    def test_out_of_bounds_dates_and_invalid_dividends_are_refused(self):
        prices, distributions = _yahoo()
        for options in ({"ex_date": snapshots.START}, {"ex_date": date(2022, 1, 3)},
                        {"symbol": "UNKNOWN"}, {"dividend": 0.}, {"dividend": -1.},
                        {"dividend": float("nan")}, {"dividend": float("inf")}, {"dividend": 100.}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                snapshots.repair_yahoo(prices, distributions, **options)

    def test_dates_bound_numeric_interpretation_and_output(self):
        prices, distributions = _yahoo()
        expected = snapshots.repair_yahoo(prices, distributions, dividend=2.)
        for day in ("2005-12-30", "2022-01-03"):
            prices += f"{day},TLT,DO_NOT_PARSE_PRICE,NaN\n".encode()
            distributions += f"{day},TLT,DO_NOT_PARSE_CLOSE,inf\n".encode()
        self.assertEqual(snapshots.repair_yahoo(prices, distributions, dividend=2.), expected)


class TiingoNormalizationTests(unittest.TestCase):
    def test_successive_splits_restate_raw_close_and_dividend_on_the_same_basis(self):
        d0, d1, d2 = date(2008, 1, 2), date(2008, 2, 1), date(2008, 3, 3)
        source = {"FAKE": {d0: _tiingo_row(150., 6., 1., 10., 11.),
                           d1: _tiingo_row(75., 3., 2., 12., 13.),
                           d2: _tiingo_row(25., 1., 3., 14., 15.)}}
        original = deepcopy(source)
        with patch.object(snapshots, "SYMBOLS", ("FAKE",)):
            prices, distributions, splits = snapshots.normalize_tiingo(source)
        mapped_p, mapped_d = _rows(prices), _rows(distributions)
        for day in (d0, d1, d2):
            key = (str(day), "FAKE")
            self.assertEqual(float(mapped_d[key]["close"]), 25.)
            self.assertEqual(float(mapped_d[key]["dividend"]), 1.)
            self.assertEqual(float(mapped_p[key]["tr_open"]), original["FAKE"][day]["adjOpen"])
            self.assertEqual(float(mapped_p[key]["tr_close"]), original["FAKE"][day]["adjClose"])
        self.assertEqual(splits, {"FAKE": [{"date": str(d1), "ratio": "2.0:1"},
                                          {"date": str(d2), "ratio": "3.0:1"}]})
        self.assertEqual(source, original)

    def test_split_on_end_date_applies_only_to_strictly_earlier_rows(self):
        previous, last = date(2021, 12, 30), snapshots.END
        source = {"FAKE": {previous: _tiingo_row(200., 4.), last: _tiingo_row(100., 2., 2.)}}
        with patch.object(snapshots, "SYMBOLS", ("FAKE",)):
            _, distributions, _ = snapshots.normalize_tiingo(source)
        for row in _rows(distributions).values():
            self.assertEqual(float(row["close"]), 100.)
            self.assertEqual(float(row["dividend"]), 2.)

    def test_reverse_and_fractional_split_ratios_are_not_rounded_to_integers(self):
        d0, d1, d2 = date(2008, 1, 2), date(2008, 2, 1), date(2008, 3, 3)
        source = {"FAKE": {d0: _tiingo_row(62.5, 1.25), d1: _tiingo_row(125., 2.5, .5),
                           d2: _tiingo_row(100., 2., 1.25)}}
        with patch.object(snapshots, "SYMBOLS", ("FAKE",)):
            _, distributions, splits = snapshots.normalize_tiingo(source)
        self.assertEqual([record["ratio"] for record in splits["FAKE"]], ["0.5:1", "1.25:1"])
        for row in _rows(distributions).values():
            self.assertEqual(float(row["close"]), 100.)
            self.assertEqual(float(row["dividend"]), 2.)

    def test_normalization_refuses_unbounded_reference_before_split_arithmetic(self):
        class ForbiddenNumeric:
            def __mul__(self, other):
                raise AssertionError("protected split was interpreted")
            __rmul__ = __mul__
        source = {"FAKE": {date(2012, 1, 3): _tiingo_row(100.),
                           date(2022, 1, 3): {"splitFactor": ForbiddenNumeric()}}}
        with patch.object(snapshots, "SYMBOLS", ("FAKE",)), self.assertRaisesRegex(ValueError, "date-bounded"):
            snapshots.normalize_tiingo(source)

    def test_csv_parser_excludes_future_split_and_bad_numbers_before_normalization(self):
        known = [(date(2021, 12, 30), _tiingo_row(100., 2.)),
                 (snapshots.END, _tiingo_row(100., 2.))]
        raw = _tiingo_csv(known)
        row = {key: "DO_NOT_PARSE" for key in tiingo.FIELDS[1:]}
        row["splitFactor"] = "1000000"
        raw += _tiingo_csv([(date(2022, 1, 3), row)]).split(b"\n", 1)[1]
        parsed, bounded, outside = tiingo.parse_csv(raw)
        self.assertEqual(outside, 1)
        self.assertNotIn(b"DO_NOT_PARSE", bounded)
        with patch.object(snapshots, "SYMBOLS", ("FAKE",)):
            _, distributions, splits = snapshots.normalize_tiingo({"FAKE": parsed})
        self.assertEqual(splits, {"FAKE": []})
        self.assertTrue(all(float(row["close"]) == 100. for row in _rows(distributions).values()))

    def test_duplicate_source_dates_are_refused_before_the_dictionary_can_hide_them(self):
        day = date(2012, 1, 3)
        with self.assertRaisesRegex(ValueError, "duplicate session"):
            tiingo.parse_csv(_tiingo_csv([(day, _tiingo_row(100.)), (day, _tiingo_row(200.))]))

    def test_output_is_deterministically_sorted_without_mutating_source_order(self):
        d0, d1 = date(2008, 1, 2), date(2008, 2, 1)
        source = {"ZZ": {d1: _tiingo_row(100.), d0: _tiingo_row(100.)},
                  "AA": {d1: _tiingo_row(100.), d0: _tiingo_row(100.)}}
        original = deepcopy(source)
        with patch.object(snapshots, "SYMBOLS", ("ZZ", "AA")):
            prices, distributions, _ = snapshots.normalize_tiingo(source)
        for raw in (prices, distributions):
            self.assertEqual(list(_rows(raw)), [(str(d0), "AA"), (str(d0), "ZZ"),
                                              (str(d1), "AA"), (str(d1), "ZZ")])
        self.assertEqual(source, original)
