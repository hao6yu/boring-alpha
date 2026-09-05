#!/usr/bin/env python3
"""Conditional, bounded price-component diagnostic; never a strategy evaluation.

Fetch only three pinned QuantConnect/Lean repository sample ZIPs. Compare their
same-session cash-price components with the selected Yahoo snapshot, then count
monthly cash-relative vote differences while RETAINING Yahoo's corporate-action
adjustment factors. This is NOT independent total-return validation, an approved
replacement feed, or evidence of strategy performance. QC sample provenance has
not been independently established; notably its EEM archive includes pre-launch
dates outside this diagnostic's authorized numeric range.

All CSV dates are parsed before numerical fields. Numeric interpretation is
hard-bounded to 2006-02-28..2021-12-31; there is no override. No files, research
freeze, journal, or portfolio-performance artifacts are written.

Usage: .venv/bin/python tools/check_ba002_seen_prices.py --snapshot PATH
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
import csv
from datetime import date, datetime
import hashlib
import io
import json
import math
from pathlib import Path
import ssl
from urllib.request import Request, urlopen
import zipfile

from boring_alpha.data.calendar import SessionCalendar
from boring_alpha.data.csv_loader import load_csv_market_data_bytes
from boring_alpha.data.distributions import load_distributions_bytes


ROOT = Path(__file__).resolve().parents[1]
START, END = date(2006, 2, 28), date(2021, 12, 31)
COMMIT = "23b735d99a357807dc0df9f4c51d30f05fe0d277"
SYMBOLS = ("SPY", "IWM", "EEM")
EXPECTED_ZIP_SHA256 = {
    "SPY": "aaa1febad0cb8f91011212c92ff7caac6d4d6415a3b7f73c4b98c438db4274ad",
    "IWM": "bf0b841f74504c9bbd346076f3ab3d8b28cdb82815d6cc6e8acc6307b87d77c5",
    "EEM": "080c4172c03343788fa40555b18ef7f9707dbe5b36dc69863d026e792e956a13",
}
# Fixed before this diagnostic's local comparison. Neither threshold is tuned.
DOLLAR_TOLERANCE, BPS_TOLERANCE = 0.02, 5.0
ORIGINAL_SPY_SAMPLE = tuple(map(date.fromisoformat, (
    "2008-07-23", "2008-07-24", "2008-09-15", "2009-03-09", "2010-03-31",
    "2011-12-30", "2013-03-28", "2015-03-31", "2019-12-31", "2020-12-31",
)))
ACTION_SAMPLES = {
    "EEM": tuple(map(date.fromisoformat, ("2008-07-23", "2008-07-24", "2008-07-25"))),
    "SPY": tuple(map(date.fromisoformat, ("2019-03-14", "2019-03-15", "2019-04-01"))),
    "IWM": tuple(map(date.fromisoformat, ("2019-03-14", "2019-03-15", "2019-04-01"))),
}


def tls_context():
    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"]:
        return context
    for path in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
                 "/usr/local/etc/ca-certificates/cert.pem", "/etc/pki/tls/certs/ca-bundle.crt"):
        if Path(path).is_file():
            return ssl.create_default_context(cafile=path)
    raise ValueError("no CA bundle available; TLS verification will not be disabled")


def fetch_qc(symbol):
    url = f"https://raw.githubusercontent.com/QuantConnect/Lean/{COMMIT}/Data/equity/usa/daily/{symbol.lower()}.zip"
    request = Request(url, headers={"User-Agent": "BoringAlpha bounded source diagnostic"})
    with urlopen(request, timeout=45, context=tls_context()) as response:
        raw = response.read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ZIP_SHA256[symbol]:
        raise ValueError(f"{symbol} pinned ZIP hash mismatch; stop source interpretation")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        expected_member = f"{symbol.lower()}.csv"
        if archive.namelist() != [expected_member]:
            raise ValueError(f"{symbol} unexpected ZIP members; stop source interpretation")
        csv_bytes = archive.read(expected_member)
    rows, all_dates = {}, []
    for row_number, fields in enumerate(csv.reader(io.StringIO(csv_bytes.decode("utf-8"))), 1):
        try:
            day = datetime.strptime(fields[0], "%Y%m%d %H:%M").date()
        except (ValueError, IndexError):
            raise ValueError(f"{symbol} QC row {row_number}: invalid date") from None
        all_dates.append(day)
        if not START <= day <= END:
            continue
        if len(fields) != 6 or fields[0] != day.strftime("%Y%m%d 00:00") or day in rows:
            raise ValueError(f"{symbol} QC row {row_number}: unexpected layout, timestamp, or duplicate date")
        try:
            opening, high, low, close = [float(value) / 10000 for value in fields[1:5]]
        except (ValueError, OverflowError):
            raise ValueError(f"{symbol} QC row {row_number}: invalid OHLC") from None
        if any(not math.isfinite(value) or value <= 0 for value in (opening, high, low, close)) or not low <= min(opening, close) <= max(opening, close) <= high:
            raise ValueError(f"{symbol} QC row {row_number}: impossible OHLC; stop source interpretation")
        # Raw QC units versus Yahoo's already split-restated historical units.
        divisor = 3 if symbol == "EEM" and day < date(2008, 7, 24) else 1
        rows[day] = {"open": opening / divisor, "close": close / divisor}
    if all_dates != sorted(set(all_dates)) or not rows:
        raise ValueError(f"{symbol} QC dates are nonchronological/duplicated or have no bounded coverage")
    return rows, {
        "url": url, "zip_sha256": digest, "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "archive_date_only_first": str(min(all_dates)), "archive_date_only_last": str(max(all_dates)),
        "archive_date_only_rows": len(all_dates),
        "interpreted_first": str(min(rows)), "interpreted_last": str(max(rows)), "interpreted_rows": len(rows),
        "alignment": "OHLC / 10000; EEM dates before 2008-07-24 additionally / 3; otherwise unchanged",
    }


def compare(day, symbol, component, qc_value, yahoo_value):
    difference = yahoo_value - qc_value
    tolerance = max(DOLLAR_TOLERANCE, qc_value * BPS_TOLERANCE / 10000)
    return {
        "date": str(day), "symbol": symbol, "component": component,
        "yahoo": yahoo_value, "qc_aligned": qc_value,
        "yahoo_minus_qc_dollars": difference,
        "yahoo_minus_qc_bps": difference / qc_value * 10000,
        "allowed_difference_dollars": tolerance,
        "exceeds_tolerance": abs(difference) > tolerance + 1e-10,
    }


def summarize(rows):
    if not rows:
        return {"comparisons": 0, "exceeds_tolerance": 0, "max_absolute_dollar_difference": None,
                "max_absolute_bps_difference": None}
    return {
        "comparisons": len(rows), "exceeds_tolerance": sum(row["exceeds_tolerance"] for row in rows),
        "max_absolute_dollar_difference": max(abs(row["yahoo_minus_qc_dollars"]) for row in rows),
        "max_absolute_bps_difference": max(abs(row["yahoo_minus_qc_bps"]) for row in rows),
        "largest_dollar_row": max(rows, key=lambda row: abs(row["yahoo_minus_qc_dollars"])),
        "largest_bps_row": max(rows, key=lambda row: abs(row["yahoo_minus_qc_bps"])),
    }


def bounded_local_bytes(raw, columns):
    """Date-first lower and upper bound before handing bytes to numeric loaders."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
    if reader.fieldnames != columns:
        raise ValueError("local snapshot has an unexpected CSV layout")
    for row_number, row in enumerate(reader, 2):
        try:
            day = date.fromisoformat(row["date"])
        except (ValueError, TypeError, KeyError):
            raise ValueError(f"local row {row_number}: invalid date") from None
        if START <= day <= END:
            if None in row:
                raise ValueError(f"local row {row_number}: unexpected columns")
            writer.writerow([row[key] for key in columns])
    return output.getvalue().encode()


def run(snapshot, calendar_path):
    paths = {"prices": snapshot / "market_daily.csv", "cash": snapshot / "cash_daily.csv",
             "distributions": snapshot / "distributions_daily.csv", "manifest": snapshot / "manifest.json"}
    raw = {key: path.read_bytes() for key, path in paths.items()}
    manifest = json.loads(raw["manifest"])
    if manifest.get("methodology") != "yahoo-adjusted-v2+dgs3mo-v1" or manifest.get("synthetic") is True:
        raise ValueError("local snapshot is not the selected non-synthetic v2 methodology")
    bounded = {
        "prices": bounded_local_bytes(raw["prices"], ["date", "symbol", "tr_open", "tr_close"]),
        "cash": bounded_local_bytes(raw["cash"], ["date", "cash_factor"]),
        "distributions": bounded_local_bytes(raw["distributions"], ["date", "symbol", "close", "dividend"]),
    }
    market = load_csv_market_data_bytes(bounded["prices"], bounded["cash"], end=END)
    distributions = load_distributions_bytes(bounded["distributions"], manifest_block=manifest, end=END)
    calendar = SessionCalendar.load(calendar_path)
    if calendar.synthetic:
        raise ValueError("fictional calendar cannot align real source dates")
    expected = set(calendar.expected_sessions(START, END))
    decisions = {}
    for start, end in ((date(2007, 6, 1), date(2017, 12, 31)), (date(2018, 1, 1), END)):
        decisions.update(calendar.requirements(start, end, (9, 12, 15), warmup_months=15).anchors)
    report = {
        "diagnostic": "BA-002 conditional seen-only price-component sensitivity v1",
        "not_strategy_evaluation": True, "not_independent_total_return_validation": True,
        "source_provenance_unresolved": True, "end_cap": str(END), "start_cap": str(START),
        "source_commit": COMMIT,
        "limits": ["QC repository samples are not established independent research-grade market truth.",
                   "EEM sample includes pre-launch dates outside the interpreted range; provenance requires review.",
                   "Price substitution retains Yahoo corporate-action adjustment factors, dividends, and cash inputs.",
                   "No strategy return, drawdown, tax result, sweep, or performance selection is computed.",
                   "No source replacement, journal, freeze, or data-file write occurs.",
                   "QC sample ends 2021-03-31; later seen history is untested, not silently filled."],
        "tolerance": {"rule": "absolute difference <= max(0.02 dollars, 5 bps of QC aligned price)",
                      "fixed_before_comparison": True, "dollar": DOLLAR_TOLERANCE, "bps": BPS_TOLERANCE},
        "local_source_sha256": {key: hashlib.sha256(value).hexdigest() for key, value in raw.items()},
        "bounded_local_csv_sha256": {key: hashlib.sha256(value).hexdigest() for key, value in bounded.items()},
        "snapshot": str(snapshot.resolve()), "calendar_sha256": calendar.sha256,
        "expected_seen_sessions_including_warmup": len(expected),
        "monthly_decisions": len(decisions), "symbols": {},
    }
    for symbol in SYMBOLS:
        qc, source = fetch_qc(symbol)
        unexpected = set(qc) - expected
        if unexpected:
            raise ValueError(f"{symbol} has unexpected QC sessions in the bounded window; stop source interpretation")
        local_dates = set(market.symbol_dates.get(symbol, ())) & set(distributions.symbol_dates.get(symbol, ()))
        if local_dates != expected:
            raise ValueError(f"{symbol} local price/distribution coverage incomplete; stop source interpretation")
        comparable = sorted(set(qc) & local_dates)
        prices = {}
        for day in comparable:
            bar, cash_close = market.bar(day, symbol), distributions.close(day, symbol)
            yahoo_open = bar.open * cash_close / bar.close
            prices[day] = {
                "close": compare(day, symbol, "close", qc[day]["close"], cash_close),
                "open": compare(day, symbol, "open", qc[day]["open"], yahoo_open),
            }
        checks, skipped, changes, next_opens = [], [], [], []
        for decision, anchors in sorted(decisions.items()):
            execution = calendar.sessions[bisect_right(calendar.sessions, decision)]
            if execution in prices and execution <= END:
                next_opens.append({**prices[execution]["open"], "decision_date": str(decision)})
            for horizon, anchor in anchors.items():
                identity = {"date": str(decision), "symbol": symbol, "horizon_months": horizon, "anchor": str(anchor)}
                if decision not in qc or anchor not in qc:
                    skipped.append(identity)
                    continue
                yahoo_end, yahoo_start = market.bar(decision, symbol).close, market.bar(anchor, symbol).close
                factor_end = yahoo_end / distributions.close(decision, symbol)
                factor_start = yahoo_start / distributions.close(anchor, symbol)
                cash_ratio = market.cash_index[decision] / market.cash_index[anchor]
                yahoo_margin = yahoo_end / yahoo_start - cash_ratio
                qc_margin = (qc[decision]["close"] * factor_end) / (qc[anchor]["close"] * factor_start) - cash_ratio
                changed = (yahoo_margin > 0) != (qc_margin > 0)
                checks.append(changed)
                if changed:
                    changes.append({**identity, "yahoo_vote": yahoo_margin > 0, "qc_price_component_vote": qc_margin > 0,
                                    "yahoo_excess_return_bps": yahoo_margin * 10000,
                                    "qc_price_component_excess_return_bps": qc_margin * 10000})
        samples = sorted(set(ACTION_SAMPLES[symbol]) | (set(ORIGINAL_SPY_SAMPLE) if symbol == "SPY" else set()))
        report["symbols"][symbol] = {
            "source": source,
            "coverage": {"same_date_comparisons": len(comparable), "first": str(min(comparable)), "last": str(max(comparable)),
                         "missing_qc_expected_sessions": len(expected - set(qc)),
                         "missing_qc_first": str(min(expected - set(qc))) if expected - set(qc) else None,
                         "missing_qc_last": str(max(expected - set(qc))) if expected - set(qc) else None},
            "daily_close": summarize([prices[day]["close"] for day in comparable]),
            "daily_open": summarize([prices[day]["open"] for day in comparable]),
            "monthly_next_open": summarize(next_opens),
            "monthly_next_open_discrepancies": [row for row in next_opens if row["exceeds_tolerance"]],
            "votes": {"compared": len(checks), "changed": sum(checks), "missing_endpoint_checks": len(skipped),
                      "first_compared_decision": str(min(day for day in decisions if day in qc)),
                      "last_compared_decision": str(max(day for day in decisions if day in qc)),
                      "changes": changes, "skipped_checks": skipped},
            "fixed_illustrative_samples": [prices[day] if day in prices else {"date": str(day), "unavailable": True} for day in samples],
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, default=ROOT / "data/calendars/nyse-2006-2026-v1.json")
    args = parser.parse_args()
    try:
        report = run(args.snapshot, args.calendar)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "refused", "not_strategy_evaluation": True, "reason": str(error)}, indent=2))
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
