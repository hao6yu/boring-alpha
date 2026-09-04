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

Cash: FRED series DGS3MO, the 3-month Treasury constant maturity rate, quoted
on an INVESTMENT basis. An earlier version of this script used DTB3, which is
quoted on a bank DISCOUNT basis: it is computed against par value on a 360-day
year and is therefore not a rate of return on the money invested. Treating a
discount quote as an investment return understates cash, which flatters any
strategy measured against it. The two differ by roughly 0.1 to 0.2 percentage
points at current levels — small, but wrong in the direction that matters for a
rule whose whole signal is "does this beat cash".

Converted to a one-session growth factor as

    cash_factor[t] = (1 + rate[t-1] / 100) ** (1 / 252)

using the most recent observation STRICTLY BEFORE session t. Cash carried
overnight into t earns a rate that was known before t opened; using the
same-day rate would be a small lookahead. This treats the quoted yield as an
effective annual rate, which is a convention: a bond-equivalent yield is a
simple annualisation, so compounding it this way slightly understates cash.
That error is conservative for a strategy that must beat cash. 252 is the
conventional session count and is an approximation, not a calendar.

Incomplete sessions: a session dated today is still trading, so its close is
provisional and will change. Such rows are dropped. Without this a run made
during market hours would embed a price that no longer exists tomorrow, and the
data hash would silently disagree with itself.

Both files are written only after every download succeeds, and via a temporary
file that is renamed into place. A failure part-way through therefore leaves
the previous pair intact rather than pairing new prices with stale cash.

Usage:  python tools/fetch_market_data.py [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
import math
from datetime import date, datetime, timedelta, timezone
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
FRED_SERIES = "DGS3MO"
FRED_URL = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={FRED_SERIES}"
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


def rows_from_chart(result: dict, today: date) -> list[tuple[date, float, float]]:
    """Adjusted (date, tr_open, tr_close) rows from one parsed chart response.

    Pure, so the adjustment and the incomplete-session rule can be tested
    without a network call.
    """

    offset = result["meta"].get("gmtoffset", 0)
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]

    rows: list[tuple[date, float, float]] = []
    for index, stamp in enumerate(result["timestamp"]):
        open_, close, adjclose = quote["open"][index], quote["close"][index], adjusted[index]
        if None in (open_, close, adjclose):
            continue
        if not all(math.isfinite(v) for v in (open_, close, adjclose)):
            continue
        if close <= 0.0 or open_ <= 0.0 or adjclose <= 0.0:
            continue
        # The exchange's local calendar date, not UTC's.
        day = (datetime.fromtimestamp(stamp, tz=timezone.utc) + timedelta(seconds=offset)).date()
        if day >= today:
            continue
        factor = adjclose / close
        rows.append((day, open_ * factor, adjclose))
    return rows


def exchange_today(offset_seconds: int) -> date:
    """The exchange's current calendar date; anything on it is still trading."""

    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).date()


def fetch_prices(symbol: str) -> list[tuple[date, float, float]]:
    """Adjusted (date, tr_open, tr_close) rows for one symbol."""

    payload = json.loads(_get(CHART_URL.format(symbol=symbol)))
    result = payload["chart"]["result"][0]
    return rows_from_chart(result, exchange_today(result["meta"].get("gmtoffset", 0)))


def fetch_cash_rates() -> list[tuple[date, float]]:
    """(date, annualised percent) observations, missing values dropped."""

    text = _get(FRED_URL).decode("utf-8")
    rows: list[tuple[date, float]] = []
    for row in csv.DictReader(text.splitlines()):
        raw = (row.get(FRED_SERIES) or "").strip()
        if raw in ("", "."):
            continue
        rate = float(raw)
        if not math.isfinite(rate):
            continue
        rows.append((date.fromisoformat(row["observation_date"]), rate))
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


def _write_atomically(path: Path, rows: list[list[str]]) -> Path:
    """Write via a temporary file and rename, so a crash cannot truncate the old one."""

    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)
    temporary.replace(path)
    return path


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

    # Everything is fetched before anything is written, so a failure here cannot
    # leave fresh prices paired with a stale cash file.
    try:
        rates = fetch_cash_rates()
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        print(f"error: {FRED_SERIES}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not rates:
        print(f"error: {FRED_SERIES}: no usable observations", file=sys.stderr)
        return 2
    print(f"{FRED_SERIES} {rates[0][0]} .. {rates[-1][0]}  {len(rates):5} observations")

    bars.sort(key=lambda row: (row[0], row[1]))
    sessions = sorted({day for day, _, _, _ in bars})
    factors = cash_factors(sessions, rates)

    price_rows = [["date", "symbol", "tr_open", "tr_close"]]
    price_rows += [
        [str(day), symbol, f"{tr_open:.10f}", f"{tr_close:.10f}"]
        for day, symbol, tr_open, tr_close in bars
    ]
    cash_rows = [["date", "cash_factor"]]
    cash_rows += [[str(s), f"{factors[s]:.12f}"] for s in sessions]

    prices_path = _write_atomically(args.out / "market_daily.csv", price_rows)
    cash_path = _write_atomically(args.out / "cash_daily.csv", cash_rows)
    print(f"\nwrote {prices_path} ({len(bars)} bars, through {sessions[-1]})")
    print(f"wrote {cash_path} ({len(sessions)} sessions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
