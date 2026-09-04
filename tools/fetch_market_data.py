#!/usr/bin/env python3
"""Build BoringAlpha's CSV inputs from public sources.

This script is provenance, not plumbing: the choices it makes are the ones the
charter's "data provenance and adjustment methodology reviewed" checklist item
is about, so each is stated here rather than buried.

Prices: Yahoo Finance's chart endpoint. It is free, unofficial, and has no
support or SLA; its back-adjusted history is revised from time to time. That is
tolerable here only because a revised download changes the data hash, which
produces a different run identifier instead of silently altering an existing
result. It is not a research-grade source, and a strategy that ever advanced
toward real money would need a proper vendor.

Adjustment: the endpoint adjusts only the close. Both series must share one
basis or the return series mixes units, so the open is put on the adjusted
basis with the close's own factor:

    factor    = adjclose / close
    tr_open   = open * factor
    tr_close  = adjclose

This assumes the adjustment applies uniformly within the session. That is the
usual convention and it is an assumption; the open-gap plausibility check
exists to catch it failing.

Cash: FRED series DTB3, the 3-month Treasury bill secondary market rate,
annualised in percent. Converted to a one-session growth factor as

    cash_factor[t] = (1 + rate[t-1] / 100) ** (1 / 252)

using the most recent observation STRICTLY BEFORE session t. Cash carried
overnight into t earns a rate that was known before t opened; using the
same-day rate would be a small lookahead. 252 is the conventional session count
and is an approximation, not a calendar.

Usage:  python tools/fetch_market_data.py [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
import json
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.request

SYMBOLS = ("SPY", "IWM", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC")
CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?period1=0&period2=9999999999&interval=1d&events=div%2Csplit"
)
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"
SESSIONS_PER_YEAR = 252
USER_AGENT = "Mozilla/5.0 (compatible; BoringAlpha research)"


# python.org builds on macOS ship without a CA bundle, so the default context
# can end up with an empty trust store. Falling back to the operating system's
# bundle keeps verification on. Turning verification off would make a silent
# man-in-the-middle indistinguishable from a good download, which is not a
# trade a lab about trustworthy data should make for convenience.
_CA_BUNDLES = (
    "/etc/ssl/cert.pem",
    "/usr/local/etc/ca-certificates/cert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
)


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"] > 0:
        return context
    for candidate in _CA_BUNDLES:
        if Path(candidate).is_file():
            return ssl.create_default_context(cafile=candidate)
    raise RuntimeError(
        "no certificate authority bundle found; refusing to fetch without "
        "TLS verification. Install certificates (on macOS, run the "
        "'Install Certificates.command' shipped with Python) and retry."
    )


_CONTEXT = _ssl_context()


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60, context=_CONTEXT) as response:
        return response.read()


def fetch_prices(symbol: str) -> list[tuple[date, float, float]]:
    """Adjusted (date, tr_open, tr_close) rows for one symbol."""

    payload = json.loads(_get(CHART_URL.format(symbol=symbol)))
    result = payload["chart"]["result"][0]
    offset = result["meta"].get("gmtoffset", 0)
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]

    rows: list[tuple[date, float, float]] = []
    for index, stamp in enumerate(result["timestamp"]):
        open_, close, adjclose = quote["open"][index], quote["close"][index], adjusted[index]
        if None in (open_, close, adjclose) or close <= 0.0:
            continue
        # The exchange's local calendar date, not UTC's.
        day = date.fromtimestamp(stamp + offset)
        factor = adjclose / close
        rows.append((day, open_ * factor, adjclose))
    return rows


def fetch_cash_rates() -> list[tuple[date, float]]:
    """(date, annualised percent) observations, missing values dropped."""

    text = _get(FRED_URL).decode("utf-8")
    rows: list[tuple[date, float]] = []
    for row in csv.DictReader(text.splitlines()):
        raw = (row.get("DTB3") or "").strip()
        if raw in ("", "."):
            continue
        rows.append((date.fromisoformat(row["observation_date"]), float(raw)))
    return sorted(rows)


def cash_factors(sessions: list[date], rates: list[tuple[date, float]]) -> dict[date, float]:
    """One growth factor per session, from the last rate known before it."""

    factors: dict[date, float] = {}
    index = 0
    latest: float | None = None
    for session in sessions:
        while index < len(rates) and rates[index][0] < session:
            latest = rates[index][1]
            index += 1
        if latest is None:
            # Before the first observation: fall back to the earliest rate
            # rather than inventing a zero.
            latest = rates[0][1]
        factors[session] = (1.0 + latest / 100.0) ** (1.0 / SESSIONS_PER_YEAR)
    return factors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data"), help="output directory")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    bars: list[tuple[date, str, float, float]] = []
    for symbol in SYMBOLS:
        try:
            rows = fetch_prices(symbol)
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
            print(f"error: {symbol}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        if not rows:
            print(f"error: {symbol}: no usable rows returned", file=sys.stderr)
            return 2
        print(f"{symbol:4} {rows[0][0]} .. {rows[-1][0]}  {len(rows):5} rows")
        bars.extend((day, symbol, tr_open, tr_close) for day, tr_open, tr_close in rows)

    bars.sort(key=lambda row: (row[0], row[1]))
    prices_path = args.out / "market_daily.csv"
    with prices_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["date", "symbol", "tr_open", "tr_close"])
        for day, symbol, tr_open, tr_close in bars:
            writer.writerow([day, symbol, f"{tr_open:.10f}", f"{tr_close:.10f}"])

    rates = fetch_cash_rates()
    print(f"DTB3 {rates[0][0]} .. {rates[-1][0]}  {len(rates):5} observations")
    sessions = sorted({day for day, _, _, _ in bars})
    factors = cash_factors(sessions, rates)
    cash_path = args.out / "cash_daily.csv"
    with cash_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["date", "cash_factor"])
        for session in sessions:
            writer.writerow([session, f"{factors[session]:.12f}"])

    print(f"\nwrote {prices_path} ({len(bars)} bars)")
    print(f"wrote {cash_path} ({len(sessions)} sessions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
