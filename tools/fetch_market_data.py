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

Distributions: the same payload carries dividend and split events. v2 writes
`distributions_daily.csv` with the UNADJUSTED close and the cash dividend per
share on its ex-date (0 otherwise), one row per session and symbol, aligned
with the price file. The tax overlay uses these to separate the income the
adjusted series silently reinvests from the capital gain it reports; nothing
else reads them. Checked on 2026-09-04: the endpoint's close does not jump
across EEM's 3:1 split of 2008-07-24 (43.92 → 42.30), and its June 2008
dividend (0.517333) equals the issuer's own split-restated figure to the
cent, so close and dividend are both in split-adjusted units; see
docs/decisions/2026-09-04-distributions-v2.md. Split events are recorded in
the manifest so a reader can see them; no arithmetic is applied to them.

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

Atomicity: prices and cash must move together. Renaming two files separately
still leaves a window where a crash pairs new prices with old cash, so a run is
written into its own timestamped snapshot directory and `manifest.json` is
written LAST. A directory without a manifest is an incomplete download and must
not be used. `data/current` is repointed at the finished snapshot only after
the manifest lands.

Methodology: the identifier below travels into the snapshot manifest and must
be repeated in a run configuration's `data.methodology`. It is part of a run's
identity because this script is not covered by the code fingerprint, so a
change of price adjustment or cash series would otherwise be invisible.

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
METHODOLOGY = "yahoo-adjusted-v2+dgs3mo-v1"
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


def _local_date(stamp: int, offset_seconds: int) -> date:
    """The exchange's local calendar date for a timestamp, not UTC's."""

    return (datetime.fromtimestamp(stamp, tz=timezone.utc) + timedelta(seconds=offset_seconds)).date()


def _sessions(result: dict, today: date):
    """(day, open, close, adjclose) for every complete, usable session.

    One filter for prices and distributions, so the two files are aligned
    row for row by construction rather than by luck.
    """

    offset = result["meta"].get("gmtoffset", 0)
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    for index, stamp in enumerate(result["timestamp"]):
        open_, close, adjclose = quote["open"][index], quote["close"][index], adjusted[index]
        if None in (open_, close, adjclose):
            continue
        if not all(math.isfinite(v) for v in (open_, close, adjclose)):
            continue
        if close <= 0.0 or open_ <= 0.0 or adjclose <= 0.0:
            continue
        day = _local_date(stamp, offset)
        if day >= today:
            continue
        yield day, open_, close, adjclose


def rows_from_chart(result: dict, today: date) -> list[tuple[date, float, float]]:
    """Adjusted (date, tr_open, tr_close) rows from one parsed chart response.

    Pure, so the adjustment and the incomplete-session rule can be tested
    without a network call.
    """

    return [
        (day, open_ * (adjclose / close), adjclose)
        for day, open_, close, adjclose in _sessions(result, today)
    ]


def distribution_rows_from_chart(result: dict, today: date) -> list[tuple[date, float, float]]:
    """(date, unadjusted close, dividend per share) for every session kept by rows_from_chart.

    The dividend is the cash amount on its ex-date and 0.0 otherwise. Amounts
    and closes are in the endpoint's split-adjusted units, which match each
    other and the adjusted series (checked against EEM's 2008 split). A
    dividend dated on a session that was dropped as incomplete is an error:
    it would otherwise vanish silently. Dividends dated today or later are
    declared, not yet paid, and are ignored.
    """

    offset = result["meta"].get("gmtoffset", 0)
    dividends: dict[date, float] = {}
    for event in result.get("events", {}).get("dividends", {}).values():
        amount = float(event["amount"])
        if not math.isfinite(amount) or amount < 0.0:
            raise ValueError(f"invalid dividend event: {event!r}")
        day = _local_date(int(event["date"]), offset)
        dividends[day] = dividends.get(day, 0.0) + amount
    rows = [
        (day, close, dividends.pop(day, 0.0))
        for day, _, close, _ in _sessions(result, today)
    ]
    unmatched = sorted(day for day in dividends if day < today)
    if unmatched:
        raise ValueError(
            f"dividend ex-dates fall on no complete session: {[d.isoformat() for d in unmatched]}"
        )
    return rows


def splits_from_chart(result: dict) -> list[dict[str, str]]:
    """Split events in date order, as recorded in the snapshot manifest.

    Nothing downstream adjusts for these — the endpoint's closes and
    dividends are already split-adjusted — but a reader must be able to see
    that a split happened.
    """

    offset = result["meta"].get("gmtoffset", 0)
    events = sorted(
        result.get("events", {}).get("splits", {}).values(), key=lambda event: int(event["date"])
    )
    return [
        {"date": _local_date(int(event["date"]), offset).isoformat(), "ratio": str(event.get("splitRatio", ""))}
        for event in events
    ]


def exchange_today(offset_seconds: int) -> date:
    """The exchange's current calendar date; anything on it is still trading."""

    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).date()


def fetch_chart(symbol: str) -> dict:
    """The parsed chart result for one symbol: quotes, adjusted closes and events."""

    payload = json.loads(_get(CHART_URL.format(symbol=symbol)))
    return payload["chart"]["result"][0]


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


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)


def write_snapshot(
    out: Path,
    price_rows: list[list[str]],
    cash_rows: list[list[str]],
    distribution_rows: list[list[str]],
    coverage: dict[str, dict[str, str]],
    splits: dict[str, list[dict[str, str]]],
) -> Path:
    """Write one snapshot directory, manifest last, then repoint `current`.

    The manifest is the completion marker: its absence means the download did
    not finish, so prices, cash and distributions can never be read as a
    mismatched set.
    """

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = out / "snapshots" / stamp
    snapshot.mkdir(parents=True, exist_ok=False)

    _write_csv(snapshot / "market_daily.csv", price_rows)
    _write_csv(snapshot / "cash_daily.csv", cash_rows)
    _write_csv(snapshot / "distributions_daily.csv", distribution_rows)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "methodology": METHODOLOGY,
        "price_source": "yahoo-finance-chart-v8",
        "price_adjustment": "tr_open = open * adjclose / close; tr_close = adjclose",
        "distribution_source": "yahoo-finance-chart-v8 events=div",
        "distribution_units": (
            "split-adjusted, matching close; dividend is cash per share on its "
            "ex-date and 0 otherwise"
        ),
        "cash_series": FRED_SERIES,
        "cash_basis": "investment (constant maturity), not bank discount",
        "cash_convention": "(1 + prior_session_rate / 100) ** (1 / 252)",
        "sessions_per_year": SESSIONS_PER_YEAR,
        "price_rows": len(price_rows) - 1,
        "cash_rows": len(cash_rows) - 1,
        "distribution_rows": len(distribution_rows) - 1,
        "coverage": coverage,
        "splits": splits,
    }
    # Last: everything above must already be on disk for this to mean anything.
    (snapshot / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    current = out / "current"
    pointer = out / "current.tmp"
    if pointer.is_symlink() or pointer.exists():
        pointer.unlink()
    pointer.symlink_to(Path("snapshots") / stamp, target_is_directory=True)
    pointer.replace(current)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data"), help="output directory")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    bars: list[tuple[date, str, float, float]] = []
    distributions: list[tuple[date, str, float, float]] = []
    coverage: dict[str, dict[str, str]] = {}
    splits: dict[str, list[dict[str, str]]] = {}
    for symbol in SYMBOLS:
        try:
            result = fetch_chart(symbol)
            today = exchange_today(result["meta"].get("gmtoffset", 0))
            rows = rows_from_chart(result, today)
            distribution_rows = distribution_rows_from_chart(result, today)
            splits[symbol] = splits_from_chart(result)
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
            print(f"error: {symbol}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        if not rows:
            print(f"error: {symbol}: no usable rows returned", file=sys.stderr)
            return 2
        paid = sum(1 for _, _, dividend in distribution_rows if dividend > 0.0)
        print(
            f"{symbol:4} {rows[0][0]} .. {rows[-1][0]}  {len(rows):5} rows  "
            f"{paid:4} ex-dates  {len(splits[symbol])} splits"
        )
        coverage[symbol] = {
            "first": str(rows[0][0]), "last": str(rows[-1][0]), "rows": str(len(rows))
        }
        bars.extend((day, symbol, tr_open, tr_close) for day, tr_open, tr_close in rows)
        distributions.extend(
            (day, symbol, close, dividend) for day, close, dividend in distribution_rows
        )

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
    distributions.sort(key=lambda row: (row[0], row[1]))
    sessions = sorted({day for day, _, _, _ in bars})
    factors = cash_factors(sessions, rates)

    price_rows = [["date", "symbol", "tr_open", "tr_close"]]
    price_rows += [
        [str(day), symbol, f"{tr_open:.10f}", f"{tr_close:.10f}"]
        for day, symbol, tr_open, tr_close in bars
    ]
    cash_rows = [["date", "cash_factor"]]
    cash_rows += [[str(s), f"{factors[s]:.12f}"] for s in sessions]
    distribution_rows_out = [["date", "symbol", "close", "dividend"]]
    distribution_rows_out += [
        [str(day), symbol, f"{close:.10f}", f"{dividend:.10f}"]
        for day, symbol, close, dividend in distributions
    ]

    snapshot = write_snapshot(
        args.out, price_rows, cash_rows, distribution_rows_out, coverage, splits
    )
    print(f"\nwrote {snapshot}")
    print(f"  {len(bars)} bars through {sessions[-1]}, {len(sessions)} cash sessions")
    print(f"  {len(distributions)} distribution rows")
    for symbol, records in splits.items():
        if records:
            print(f"  {symbol} splits: " + ", ".join(f"{r['date']} {r['ratio']}" for r in records))
    print(f"  methodology: {METHODOLOGY}")
    print(f"  {args.out / 'current'} -> snapshots/{snapshot.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
