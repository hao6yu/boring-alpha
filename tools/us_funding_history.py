#!/usr/bin/env python3
"""Validate and summarize public CDE funding exports; never label rates P&L.

Input: a directory containing a provenance manifest and untouched portal CSVs.
Funding percentages are rounded by the portal; event marks are not included.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import statistics

HEADER = ["Date", "Funding Rate (%)", "Annualized Rate (%)"]
HOUR = timedelta(hours=1)


def read_history(path: Path) -> dict:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != HEADER:
            raise ValueError("unexpected funding CSV columns or units")
        observations = []
        for row in reader:
            stamp = datetime.fromisoformat(row["Date"].replace("Z", "+00:00"))
            if stamp.utcoffset() != timedelta(0) or (stamp.minute, stamp.second, stamp.microsecond) != (0, 0, 0):
                raise ValueError("funding timestamps must be UTC hour boundaries")
            rate = float(row["Funding Rate (%)"]) / 100
            annual_pct = float(row["Annualized Rate (%)"])
            if not math.isfinite(rate) or not math.isfinite(annual_pct):
                raise ValueError("nonfinite funding value")
            # CSV APR is rounded to two decimals. This checks the hourly unit;
            # it does not establish that the displayed rate was settled.
            if abs(rate * 8760 * 100 - annual_pct) > 0.0051:
                raise ValueError("funding/APR unit or rounding mismatch")
            if observations and stamp <= observations[-1][0]:
                raise ValueError("duplicate or unordered funding timestamps")
            observations.append((stamp, rate))
    if not observations:
        raise ValueError("empty funding history")
    gaps = []
    for (a, _), (b, _) in zip(observations, observations[1:]):
        if b - a != HOUR:
            gaps.append({"after": a.isoformat(), "before": b.isoformat(),
                         "missing_hours": int((b - a) / HOUR) - 1})
    rates = [r for _, r in observations]
    rolling = {}
    for days in (7, 30, 90):
        hours = days * 24
        sums = []
        # Each window must have every hour; no zero fill across gaps.
        cumulative = [0.0]
        for rate in rates:
            cumulative.append(cumulative[-1] + rate)
        for end in range(hours, len(observations) + 1):
            if observations[end - 1][0] - observations[end - hours][0] == HOUR * (hours - 1):
                sums.append(cumulative[end] - cumulative[end - hours])
        rolling[str(days)] = {"complete_overlapping_windows": len(sums)}
        if sums:
            rolling[str(days)].update({"min_rate_sum": min(sums), "median_rate_sum": statistics.median(sums),
                                      "max_rate_sum": max(sums),
                                      "median_simple_annual_rate_on_constant_notional": statistics.median(sums) * 365 / days})
    return {"rows": len(rates), "first": observations[0][0].isoformat(), "last": observations[-1][0].isoformat(),
            "missing_hours": sum(g["missing_hours"] for g in gaps), "gaps": gaps,
            "mean_hourly_rate": statistics.fmean(rates),
            "mean_simple_annual_rate_on_constant_notional": statistics.fmean(rates) * 8760,
            "positive_hour_fraction": sum(r > 0 for r in rates) / len(rates),
            "negative_hour_fraction": sum(r < 0 for r in rates) / len(rates),
            "sum_of_reported_hourly_rates": sum(rates), "rolling": rolling}


def analyze(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["venue"] != "Coinbase Derivatives (CDE)":
        raise ValueError("this analyzer requires the U.S. CDE venue")
    assets = {}
    for contract, source in manifest["sources"].items():
        name = source["filename"]
        if Path(name).name != name:
            raise ValueError("invalid history filename")
        path = directory / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("history checksum mismatch")
        assets[contract] = read_history(path)
    return {"status": "EXPLORATORY_RATE_STATISTICS_ONLY", "source": manifest["url"], "assets": assets,
            "limitations": ["reported portal rates are rounded; settlement reconciliation not available",
                            "no event marks, historical basis, executable spreads, or margin path",
                            "rate sums describe constant dollar notional, not fixed-quantity strategy P&L",
                            "overlapping windows are not independent trials; no predictive rule tested"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.directory), indent=2, allow_nan=False))
