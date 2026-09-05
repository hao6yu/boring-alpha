"""Build two seen-only inputs for an explicitly non-gating source experiment.

Offline; original snapshots, mutable pointers, formal charters and freeze/journal
state are never changed. Both output directories must be new and Git-ignored.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path

from boring_alpha.data.calendar import SessionCalendar
from boring_alpha.data.csv_loader import load_csv_market_data_bytes
from boring_alpha.data.distributions import load_distributions_bytes
from tools.check_ba002_seen_prices import START, END, ROOT, bounded_local_bytes
from tools.check_ba002_tiingo import split_divisors
from tools.tiingo_seen_reference import SYMBOLS, load_capture

YAHOO_METHOD = "yahoo-adjusted-v3-tlt-20121101+dgs3mo-v1"
TIINGO_METHOD = "tiingo-adjusted-v1-seen-splits+dgs3mo-v1"
EX_DATE = date(2012, 11, 1)
DIVIDEND = 0.269553
COLUMNS = {
    "market_daily.csv": ["date", "symbol", "tr_open", "tr_close"],
    "cash_daily.csv": ["date", "cash_factor"],
    "distributions_daily.csv": ["date", "symbol", "close", "dividend"],
}
ORIGINAL_SHA256 = {
    "market_daily.csv": "750f4344d2138b8d1a2b191c05a595fff8566f434d242d3cb85a6e30ea579279",
    "cash_daily.csv": "963bf17ca515014328370d1ecf58f972a22d17472254c322352e6f7f6537c13c",
    "distributions_daily.csv": "cf5f53e96d1b28aa849a578dcef512aae75fd48b2f35a52dabbf31e8ef0fa141",
    "manifest.json": "0c3d0a4ee554a5641eb1d4e1a5318f42028839efb53792a5887eb9b9ff4aefe5",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def csv_bytes(columns, rows):
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue().encode()


def numeric(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("invalid numeric input") from None
    if not math.isfinite(result):
        raise ValueError("non-finite numeric input")
    return result


def repair_yahoo(prices_raw, distributions_raw, *, symbol="TLT", ex_date=EX_DATE, dividend=DIVIDEND):
    """Insert a wholly absent cash dividend; do not generalize to price repair.

    Yahoo's documented backward convention is m=1-D/previous_close. It applies
    to BOTH adjusted OHLC strictly before ex-date. It is not D/ex_date_close.
    The ex-date's open and close, raw prices, and all other symbols are retained.
    """
    dividend = numeric(dividend)
    if symbol not in SYMBOLS or not START < ex_date <= END or dividend <= 0:
        raise ValueError("repair is outside the authorized symbol/date/amount scope")
    prices = list(csv.DictReader(io.StringIO(bounded_local_bytes(prices_raw, COLUMNS["market_daily.csv"]).decode())))
    distributions = list(csv.DictReader(io.StringIO(bounded_local_bytes(distributions_raw, COLUMNS["distributions_daily.csv"]).decode())))
    pmap, dmap = {}, {}
    for rows, target, fields in ((prices, pmap, ("tr_open", "tr_close")),
                                 (distributions, dmap, ("close", "dividend"))):
        for row in rows:
            key = (date.fromisoformat(row["date"]), row["symbol"])
            if key in target:
                raise ValueError("duplicate repair input row")
            values = {field: numeric(row[field]) for field in fields}
            if any(value <= 0 for field, value in values.items() if field != "dividend") or values.get("dividend", 0) < 0:
                raise ValueError("invalid repair price or dividend")
            target[key] = values
    if set(pmap) != set(dmap):
        raise ValueError("repair price and distribution dates/symbols differ")
    days = sorted(day for day, ticker in dmap if ticker == symbol)
    if ex_date not in days or days.index(ex_date) == 0:
        raise ValueError("repair needs the ex-date and a preceding session")
    previous = days[days.index(ex_date) - 1]
    if dmap[ex_date, symbol]["dividend"] != 0:
        raise ValueError("repair refuses a dividend already present")
    previous_close = dmap[previous, symbol]["close"]
    factor = 1 - dividend / previous_close
    if not 0 < factor < 1:
        raise ValueError("repair dividend must be smaller than prior close")
    prior_adjustment = pmap[previous, symbol]["tr_close"] / previous_close
    ex_adjustment = pmap[ex_date, symbol]["tr_close"] / dmap[ex_date, symbol]["close"]
    observed_step = ex_adjustment / prior_adjustment
    # Fixed 1ppm permits archived Yahoo float rounding, but an existing
    # adjustment step must not be double-applied merely because an event is absent.
    if abs(observed_step - 1) > 1e-6:
        raise ValueError("repair requires an absent adjusted-price step as well as an absent event")
    changed = 0
    for row in prices:
        if row["symbol"] == symbol and date.fromisoformat(row["date"]) < ex_date:
            for field in ("tr_open", "tr_close"):
                row[field] = repr(numeric(row[field]) * factor)
            changed += 1
    for row in distributions:
        if row["symbol"] == symbol and date.fromisoformat(row["date"]) == ex_date:
            row["dividend"] = repr(dividend)
    output = lambda rows, name: csv_bytes(COLUMNS[name], ([row[field] for field in COLUMNS[name]] for row in rows))
    return output(prices, "market_daily.csv"), output(distributions, "distributions_daily.csv"), {
        "symbol": symbol, "ex_date": str(ex_date), "dividend": dividend,
        "previous_session": str(previous), "previous_raw_close": previous_close,
        "pre_ex_price_multiplier": factor, "observed_original_adjustment_step": observed_step,
        "adjusted_price_rows_changed": changed, "distribution_rows_changed": 1,
        "formula": "tr_open/tr_close for dates < ex_date multiply by 1 - dividend/previous_session_raw_close",
        "raw_prices_unchanged": True, "ex_date_and_later_adjusted_prices_unchanged": True,
        "other_symbols_unchanged": True, "not_ex_close_reinvestment": True,
    }


def normalize_tiingo(reference):
    prices, distributions = [], []
    splits = {}
    for symbol in SYMBOLS:
        rows = reference[symbol]
        if any(not START <= day <= END for day in rows):
            raise ValueError("normalization requires a date-bounded reference")
        divisors = split_divisors(rows)
        splits[symbol] = [{"date": str(day), "ratio": repr(row["splitFactor"]) + ":1"}
                          for day, row in sorted(rows.items()) if row["splitFactor"] != 1]
        for day, row in sorted(rows.items()):
            prices.append((str(day), symbol, repr(row["adjOpen"]), repr(row["adjClose"])))
            distributions.append((str(day), symbol, repr(row["close"] / divisors[day]),
                                  repr(row["divCash"] / divisors[day])))
    return (csv_bytes(COLUMNS["market_daily.csv"], sorted(prices)),
            csv_bytes(COLUMNS["distributions_daily.csv"], sorted(distributions)), splits)


def publish(directory, payloads, manifest, calendar):
    """Validate the bounded complete triple before publishing a new local copy."""
    data = load_csv_market_data_bytes(payloads["market_daily.csv"], payloads["cash_daily.csv"], end=END)
    table = load_distributions_bytes(payloads["distributions_daily.csv"], manifest_block=manifest, end=END)
    expected = set(calendar.expected_sessions(START, END))
    if data.dates[0] != START or data.dates[-1] != END:
        raise ValueError("source snapshot does not cover the complete fixed seen range")
    for symbol in SYMBOLS:
        if set(data.symbol_dates[symbol]) != expected or set(table.symbol_dates[symbol]) != expected:
            raise ValueError("source snapshot lacks exact expected coverage")
    for start, end in ((date(2007, 6, 1), date(2017, 12, 31)), (date(2018, 1, 1), END)):
        calendar.validate_inputs(data.through(end), table.through(end), SYMBOLS, start, end, (9, 12, 15), warmup_months=15)
    directory.mkdir(parents=True, exist_ok=False)
    for name, raw in payloads.items():
        with (directory / name).open("xb") as stream:
            stream.write(raw)
    manifest = {**manifest, "sha256": {name: digest(raw) for name, raw in payloads.items()},
                "rows_per_symbol": len(expected), "complete": True}
    with (directory / "manifest.json").open("x") as stream:
        stream.write(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return manifest


def build(original, reference_dir, issuer_path, yahoo_output, tiingo_output, calendar_path):
    for destination in (yahoo_output, tiingo_output):
        if destination.exists() or not destination.resolve().is_relative_to((ROOT / "data/snapshots").resolve()):
            raise ValueError("output must be a new directory under ignored data/snapshots")
    if yahoo_output.resolve() == tiingo_output.resolve():
        raise ValueError("the two output paths must differ")
    original_raw = {name: (original / name).read_bytes() for name in ORIGINAL_SHA256}
    if any(digest(raw) != ORIGINAL_SHA256[name] for name, raw in original_raw.items()):
        raise ValueError("original snapshot differs from the reviewed Yahoo bytes")
    original_manifest = json.loads(original_raw["manifest.json"])
    issuer_raw = issuer_path.read_bytes()
    issuer = json.loads(issuer_raw)
    if (issuer.get("content_disposition") != "attachment; filename=iShares-20-Year-Treasury-Bond-ETF_fund.xls"
            or issuer.get("source_utf8_sha256") != "d1d3f37beb296153ab64ed8853b09e19320767fd93e0d60016f7157b3f3e50a1"
            or len(issuer.get("rows", [])) != 1 or issuer["rows"][0]["ex_date"] != str(EX_DATE)
            or numeric(issuer["rows"][0]["total_distribution_per_share"]) != DIVIDEND):
        raise ValueError("issuer correction evidence differs from the reviewed TLT event")
    calendar = SessionCalendar.load(calendar_path)
    if calendar.synthetic:
        raise ValueError("real source snapshots require the archived exchange calendar")
    reference, ref_manifest = load_capture(reference_dir, calendar.expected_sessions(START, END))
    bounded = {name: bounded_local_bytes(original_raw[name], columns) for name, columns in COLUMNS.items()}
    repaired_prices, repaired_distributions, correction = repair_yahoo(
        bounded["market_daily.csv"], bounded["distributions_daily.csv"])
    tiingo_prices, tiingo_distributions, splits = normalize_tiingo(reference)
    common = {"synthetic": False, "start": str(START), "end": str(END),
              "created_at": datetime.now(timezone.utc).isoformat(), "internal_use_only": True,
              "purpose": "authorized seen-only source sensitivity, not formal BA-002 advancement evidence",
              "calendar_sha256": calendar.sha256, "builder_sha256": digest(Path(__file__).read_bytes()),
              "cash_source": "same bounded Yahoo-snapshot DGS3MO cash bytes in both feeds",
              "original_source_sha256": ORIGINAL_SHA256}
    yahoo_manifest = {**common, "methodology": YAHOO_METHOD, "source": "Yahoo with issuer-supported TLT dividend repair",
                      "splits": {symbol: [row for row in records if date.fromisoformat(row["date"]) <= END]
                                 for symbol, records in original_manifest["splits"].items()},
                      "correction": correction, "issuer_evidence_sha256": digest(issuer_raw),
                      "adjustment_method_source": "https://help.yahoo.com/kb/SLN28256.html"}
    tiingo_manifest = {**common, "methodology": TIINGO_METHOD, "source": "Tiingo archived EOD seen reference",
                       "splits": splits, "tiingo_capture_manifest_sha256": digest((reference_dir / "manifest.json").read_bytes()),
                       "tiingo_sources": ref_manifest["symbols"],
                       "adjustment_convention": "provider adjusted OHLC unchanged; raw close and dividend divided by product of subsequent split factors through 2021-12-31; split ex-date excluded from own divisor"}
    publish(yahoo_output, {"market_daily.csv": repaired_prices, "cash_daily.csv": bounded["cash_daily.csv"],
                           "distributions_daily.csv": repaired_distributions, "issuer_evidence.json": issuer_raw}, yahoo_manifest, calendar)
    publish(tiingo_output, {"market_daily.csv": tiingo_prices, "cash_daily.csv": bounded["cash_daily.csv"],
                            "distributions_daily.csv": tiingo_distributions}, tiingo_manifest, calendar)
    return correction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--issuer", type=Path, required=True)
    parser.add_argument("--yahoo-output", type=Path, required=True)
    parser.add_argument("--tiingo-output", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, default=ROOT / "data/calendars/nyse-2006-2026-v1.json")
    args = parser.parse_args()
    build(args.original, args.reference, args.issuer, args.yahoo_output, args.tiingo_output, args.calendar)
    print("Two new seen-only source snapshots published; original inputs and formal research state unchanged.")


if __name__ == "__main__":
    main()
