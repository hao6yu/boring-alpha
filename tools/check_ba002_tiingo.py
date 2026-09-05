#!/usr/bin/env python3
"""Bounded Tiingo-vs-Yahoo data diagnostic, not a strategy performance run.

Capture with --capture (reads only TIINGO_API_KEY from .env), or replay an
existing --reference directory offline. Reports/row-level data stay local.
No source replacement, freeze confirmation, research journal, or sweep.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import date
import hashlib
import json
from pathlib import Path

from boring_alpha.data.calendar import SessionCalendar
from boring_alpha.data.csv_loader import load_csv_market_data_bytes
from boring_alpha.data.distributions import load_distributions_bytes
from tools.check_ba002_seen_prices import START, END, ROOT, bounded_local_bytes
from tools.tiingo_seen_reference import SYMBOLS, capture, load_capture


def compare(day, yahoo, reference):
    difference = yahoo - reference
    tolerance = max(0.02, reference * 0.0005)
    return {"date": str(day), "yahoo": yahoo, "tiingo_aligned": reference,
            "difference_dollars": difference, "difference_bps": difference / reference * 10000,
            "exceeds_tolerance": abs(difference) > tolerance + 1e-10}


def summary(rows):
    return {"comparisons": len(rows), "exceeds_tolerance": sum(row["exceeds_tolerance"] for row in rows),
            "largest_absolute_bps": max(rows, key=lambda row: abs(row["difference_bps"])),
            "largest_absolute_dollars": max(rows, key=lambda row: abs(row["difference_dollars"]))}


def split_divisors(rows):
    """Align contemporary raw prices to END share units; never divide ex-date."""
    product, divisors = 1.0, {}
    for day in sorted(rows, reverse=True):
        divisors[day] = product
        product *= rows[day]["splitFactor"]
    return divisors


def vote_check(yahoo_start, yahoo_end, tiingo_start, tiingo_end, cash_ratio):
    yahoo_margin = yahoo_end / yahoo_start - cash_ratio
    tiingo_margin = tiingo_end / tiingo_start - cash_ratio
    return {"yahoo_vote": yahoo_margin > 0, "tiingo_vote": tiingo_margin > 0,
            "changed": (yahoo_margin > 0) != (tiingo_margin > 0),
            "yahoo_excess_bps": yahoo_margin * 10000, "tiingo_excess_bps": tiingo_margin * 10000,
            "return_difference_bps": (yahoo_margin - tiingo_margin) * 10000}


def run(snapshot, reference, calendar_path):
    calendar = SessionCalendar.load(calendar_path)
    if calendar.synthetic:
        raise ValueError("real source diagnostic requires an independent non-synthetic calendar")
    expected = set(calendar.expected_sessions(START, END))
    tiingo, reference_manifest = load_capture(reference, expected)
    source_paths = {"prices": "market_daily.csv", "cash": "cash_daily.csv", "distributions": "distributions_daily.csv",
                    "manifest": "manifest.json"}
    raw = {key: (snapshot / filename).read_bytes() for key, filename in source_paths.items()}
    manifest = json.loads(raw["manifest"])
    if manifest.get("methodology") != "yahoo-adjusted-v2+dgs3mo-v1" or manifest.get("synthetic") is True:
        raise ValueError("expected the selected real Yahoo v2 snapshot")
    columns = {"prices": ["date", "symbol", "tr_open", "tr_close"], "cash": ["date", "cash_factor"],
               "distributions": ["date", "symbol", "close", "dividend"]}
    bounded = {key: bounded_local_bytes(raw[key], fields) for key, fields in columns.items()}
    market = load_csv_market_data_bytes(bounded["prices"], bounded["cash"], end=END)
    distributions = load_distributions_bytes(bounded["distributions"], manifest_block=manifest, end=END)
    decisions, period_decisions = {}, {}
    for label, start, end in (("development", date(2007, 6, 1), date(2017, 12, 31)),
                              ("validation", date(2018, 1, 1), END)):
        anchors = calendar.requirements(start, end, (9, 12, 15), warmup_months=15).anchors
        period_decisions[label] = set(anchors)
        decisions.update(anchors)
    report = {"diagnostic": "BA-002 Tiingo seen-only reference v1", "not_strategy_evaluation": True,
              "start_cap": str(START), "end_cap": str(END), "internal_use_only": True,
              "source_replaced": False, "tolerance": "max($0.02, 5 bps of split-aligned reference price), unchanged",
              "dividend_tolerance": "0.00050001/share (Yahoo three-decimal rounding)",
              "limits": ["Neither vendor is automatically ground truth; disagreement needs interpretation.",
                         "Cash remains the existing DGS3MO input, not independently verified here.",
                         "Raw prices are restated by observed splits through END only.",
                         "Dividend raw-share and already-restated hypotheses are both reported; neither auto-selected.",
                         "Adjusted returns use each vendor's own adjusted series; constant level scaling cancels.",
                         "No performance metrics or strategy verdicts are calculated."],
              "local_source_sha256": {key: hashlib.sha256(value).hexdigest() for key, value in raw.items()},
              "bounded_local_csv_sha256": {key: hashlib.sha256(value).hexdigest() for key, value in bounded.items()},
              "reference_manifest_sha256": hashlib.sha256((reference / "manifest.json").read_bytes()).hexdigest(),
              "reference_sources": reference_manifest["symbols"], "calendar_sha256": calendar.sha256,
              "diagnostic_code_sha256": {name: hashlib.sha256((ROOT / "tools" / name).read_bytes()).hexdigest()
                                         for name in ("check_ba002_tiingo.py", "tiingo_seen_reference.py", "check_ba002_seen_prices.py")},
              "symbols": {}}
    for symbol in SYMBOLS:
        if set(market.symbol_dates[symbol]) != expected or set(distributions.symbol_dates[symbol]) != expected:
            raise ValueError("Yahoo price/distribution session coverage mismatch")
        ref = tiingo[symbol]
        divisors = split_divisors(ref)
        prices, dividends, uniform_errors, daily_returns = {}, [], [], []
        previous = None
        for day in sorted(expected):
            row = ref[day]
            local_bar = market.bar(day, symbol)
            local_close = distributions.close(day, symbol)
            prices[day] = {
                "open": compare(day, local_bar.open * local_close / local_bar.close, row["open"] / divisors[day]),
                "close": compare(day, local_close, row["close"] / divisors[day]),
            }
            uniform_errors.append(abs((row["adjOpen"] / row["open"]) / (row["adjClose"] / row["close"]) - 1))
            dividend = distributions.dividend(day, symbol)
            if dividend or row["divCash"]:
                dividends.append({"date": str(day), "yahoo": dividend, "tiingo_reported": row["divCash"],
                                  "tiingo_divided_by_later_seen_splits": row["divCash"] / divisors[day],
                                  "reported_difference": dividend - row["divCash"],
                                  "split_aligned_difference": dividend - row["divCash"] / divisors[day]})
            if previous is not None:
                difference = (local_bar.close / market.bar(previous, symbol).close
                              - row["adjClose"] / ref[previous]["adjClose"]) * 10000
                daily_returns.append({"date": str(day), "difference_bps": difference})
            previous = day
        votes, next_opens = [], []
        for decision, anchors in sorted(decisions.items()):
            execution = calendar.sessions[bisect_right(calendar.sessions, decision)]
            if execution <= END:
                next_opens.append({**prices[execution]["open"], "decision_date": str(decision)})
            for horizon, anchor in anchors.items():
                result = vote_check(market.bar(anchor, symbol).close, market.bar(decision, symbol).close,
                                    ref[anchor]["adjClose"], ref[decision]["adjClose"],
                                    market.cash_index[decision] / market.cash_index[anchor])
                votes.append({"date": str(decision), "anchor": str(anchor), "horizon": horizon, **result})
        report["symbols"][symbol] = {
            "sessions": len(ref), "first": str(min(ref)), "last": str(max(ref)),
            "splits": [{"date": str(day), "factor": row["splitFactor"]} for day, row in ref.items() if row["splitFactor"] != 1],
            "daily_close": summary([row["close"] for row in prices.values()]),
            "daily_open": summary([row["open"] for row in prices.values()]),
            "monthly_next_open": summary(next_opens),
            "monthly_next_open_discrepancies": [row for row in next_opens if row["exceeds_tolerance"]],
            "max_relative_nonuniform_adjustment": max(uniform_errors),
            "daily_adjusted_return": {"comparisons": len(daily_returns),
                                      "differences_above_5bps": sum(abs(row["difference_bps"]) > 5 for row in daily_returns),
                                      "largest_absolute_bps": max(daily_returns, key=lambda row: abs(row["difference_bps"]))},
            "votes": {"comparisons": len(votes), "changed": sum(row["changed"] for row in votes),
                      "changes": [row for row in votes if row["changed"]],
                      "max_return_difference": max(votes, key=lambda row: abs(row["return_difference_bps"]))},
            "distributions": {"comparisons": len(dividends),
                              "reported_outside_rounding": sum(abs(row["reported_difference"]) > 0.00050001 for row in dividends),
                              "split_aligned_outside_rounding": sum(abs(row["split_aligned_difference"]) > 0.00050001 for row in dividends),
                              "rows": dividends},
            "by_period": {label: {
                "first_decision": str(min(dates)), "last_decision": str(max(dates)),
                "vote_comparisons": sum(date.fromisoformat(row["date"]) in dates for row in votes),
                "changed_votes": sum(row["changed"] for row in votes if date.fromisoformat(row["date"]) in dates),
                "next_open_comparisons": sum(date.fromisoformat(row["decision_date"]) in dates for row in next_opens),
                "next_open_flags": sum(row["exceeds_tolerance"] for row in next_opens
                                       if date.fromisoformat(row["decision_date"]) in dates),
            } for label, dates in period_decisions.items()},
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, default=ROOT / "data/calendars/nyse-2006-2026-v1.json")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Licensed rows cannot be accidentally published via a caller-supplied path.
    local_data, local_reports = (ROOT / "data/snapshots").resolve(), (ROOT / "experiments").resolve()
    if not args.reference.resolve().is_relative_to(local_data) or not args.output.resolve().is_relative_to(local_reports):
        parser.error("reference must be inside data/snapshots; output inside experiments")
    if args.output.exists():
        parser.error("refusing to overwrite existing report")
    try:
        if args.capture:
            calendar = SessionCalendar.load(args.calendar)
            if calendar.synthetic:
                raise ValueError("reference capture requires the real archived calendar")
            capture(args.reference, ROOT / ".env", calendar.expected_sessions(START, END))
        report = run(args.snapshot, args.reference, args.calendar)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as output:
            output.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    except Exception:
        # Deliberately avoid values from data, credentials, filesystem paths and
        # upstream exception text. Diagnose offline with fictional tests first.
        print("Reference capture/audit refused; no performance run or source replacement. Details suppressed.")
        raise SystemExit(1) from None
    print("Local reference audit written. No performance run or source replacement.")


if __name__ == "__main__":
    main()
