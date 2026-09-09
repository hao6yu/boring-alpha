#!/usr/bin/env python3
"""Fetch daily crypto candles into a content-addressed snapshot. Same discipline as the equity fetcher.

Why this file exists: every strategy in this repository has been priced on one asset class, and the answer it keeps producing — the index
is very hard to beat — was never tested on the classes the objective actually gestures at ("short term", "trending", new things). Round
109 probed what is reachable without paying for it: Coinbase and Kraken daily candles, Yahoo continuous futures and `^VIX`, and hourly
equities. Crypto dailies are the only new class with enough history to *test* rather than merely collect, so this tool fetches those, and
everything else waits until there is a pre-registered question worth its storage.

The rules it inherits from the equity fetcher are not decorative:

  * immutable snapshots under `data/crypto/snapshots/<STAMP>/`, and `data/crypto/current` repointed only after a complete write;
  * a manifest that names the endpoint, the window, the request count and the file's sha256 — a source URL alone is not an archive;
  * a poisoned row refuses the whole fetch. Half a candle is worse than no candle, because it prices a bar that never happened;
  * the session still in progress is dropped. A fetch is not allowed to freeze an unfinished day;
  * a hole inside a pair's known-listing window is reported as a hole, and counted in the manifest, never quietly stitched.

Nothing here is advice, and nothing here has graded a strategy yet: the pass rule for the first crypto question is written down in
`docs/notes/` before the first return is computed, which is the only reason a new asset class deserves the same scepticism as an old one.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

CRYPTO = ROOT / "data" / "crypto"
SNAPSHOTS = CRYPTO / "snapshots"
CURRENT = CRYPTO / "current"
PRICES = "crypto_daily.csv"

#: One year of Coinbase history per request would be over its 300-row cap; a month is comfortably under it.
CHUNK_SECONDS = 29 * 86400
CANDLE_URL = "https://api.exchange.coinbase.com/products/{pair}/candles"

#: The pairs to fetch. There are deliberately no listing dates here.
#:
#: The first version carried `BTC-USD: 2011-08-17`, which is when Coinbase the company started quoting bitcoin, not when this endpoint
#: started serving candles (2015-07-20). The tool reported the difference honestly as 1,433 missing sessions — and the honest report was
#: still wrong about what the hole meant, because an endpoint that never served a day is not a hole in a record. So the floor is probed
#: (`probed_floor`) and recorded per fetch. What an endpoint will give you is a fact about the endpoint; a date from a press release is a
#: fact about a press release.
PAIRS = ("BTC-USD", "ETH-USD")
PROBE_LOOKBACK_YEARS = (1, 2, 4, 8, 16, 24, 32)   # how far back to knock before concluding the record starts beyond the probe
USER_AGENT = "boring-alpha/1.0 (research; stdlib urllib)"


def _ssl_context() -> ssl.SSLContext:
    """The same certificate question the equity fetcher answers: verify, or refuse."""

    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"] > 0:
        return context
    import fetch_market_data as fm                                          # noqa: PLC0415  the equity fetcher already solved TLS
    return fm._ssl_context()                                                # noqa: SLF001  one answer to "where are the CAs", in one file


_CONTEXT = _ssl_context()


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60, context=_CONTEXT) as response:
        return response.read()


def probed_floor(pair: str, today: date, probe=None) -> date:
    """Where this endpoint's own record for `pair` begins, found by knocking, to within a day.

    Knock back by doubling years until a window comes back empty, then bisect between that empty date and today on the predicate "this
    window has candles". Twelve requests, and it buys the only floor date this repository may assert: the one the endpoint demonstrates.
    Every probe stays under a month wide, because the exchange answers 400 Bad Request for a page wider than ~300 daily candles — a limit
    that is itself a fact about the source. A source that serves nothing at all is a refusal, not an empty archive.
    """

    probe = probe or candles
    width = timedelta(days=20)

    def served(day: date) -> bool:
        return bool(probe(pair, day, min(day + width, today + timedelta(days=1))))

    empty = None
    for years in PROBE_LOOKBACK_YEARS:
        back = date(today.year - years, today.month, min(today.day, 28))
        if back < today and not served(back):
            empty = back
            break
    if empty is None:
        raise SystemExit(f"{pair}: candles come back {PROBE_LOOKBACK_YEARS[-1]} years back; this probe cannot find the start")
    if not served(today):
        raise SystemExit(f"{pair}: no candles at all before {today}; refusing to archive an empty record")

    lo, hi = empty, today
    while (hi - lo).days > 1:
        mid = lo + (hi - lo) / 2
        if probe(pair, mid, mid + timedelta(days=1)):
            hi = mid
        else:
            lo = mid
    return hi


def windows(until: datetime, since: date) -> list[tuple[str, str]]:
    """(start, end) ISO windows, newest first, each small enough for one page of candles."""

    out, end = [], until
    while end.date() > since:
        start = max(datetime.combine(since, datetime.min.time()).replace(tzinfo=timezone.utc),
                    end - timedelta(seconds=CHUNK_SECONDS))
        out.append((start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")))
        end = start
    return out


def candles(pair: str, start, end) -> list[dict]:
    """One page of daily candles for one pair, normalised and validated, oldest first."""

    def stamp_of(v):
        return v.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(v, (date, datetime)) else v
    url = (CANDLE_URL.format(pair=urllib.parse.quote(pair))
           + f"?granularity=86400&start={stamp_of(start)}&end={stamp_of(end)}")
    payload = json.loads(_get(url))
    if isinstance(payload, dict) and payload.get("message"):
        raise SystemExit(f"{pair}: the exchange answered {payload['message']!r} for {start}..{end}; refusing to invent the window")
    rows = []
    for stamp, low, high, open_, close, volume in payload:
        day = datetime.fromtimestamp(stamp, timezone.utc).date()
        try:
            values = [float(x) for x in (open_, high, low, close, volume)]
        except (TypeError, ValueError):
            raise SystemExit(f"{pair} {day}: a candle that is not numeric ({low!r}, {high!r}, {open_!r}, {close!r})") from None
        if min(values[:5]) <= 0.0 or values[1] < values[2]:
            raise SystemExit(f"{pair} {day}: an impossible candle (o {values[0]}, h {values[1]}, l {values[2]}, c {values[3]})")
        rows.append({"date": day, "open": values[0], "high": values[1], "low": values[2],
                     "close": values[3], "volume": values[4]})
    return sorted(rows, key=lambda r: r["date"])


def fetch(pairs=PAIRS, today: date | None = None) -> tuple[list[dict], dict]:
    """Every candle this repository may quote, plus the manifest that says how it was obtained."""

    now = datetime.now(timezone.utc)
    today = today or now.date()
    rows, requests, gaps, floors = [], 0, {}, {}
    for pair in pairs:
        # The probe bounds the search; the first candle actually served is the floor. Believing the probe over the data
        # would manufacture a one-day hole at the start of every record, which is the sort of precision that is simply wrong.
        probed = probed_floor(pair, today)
        listed = probed                              # the chunked walk starts at the probe; holes are judged from the first candle
        seen: set[date] = set()
        for start, end in windows(now, listed):
            page = candles(pair, start, end)
            for row in page:
                row["pair"] = pair
            requests += 1
            page = [r for r in page if r["date"] < today]                 # the session still in progress is not a session
            new = [r for r in page if r["date"] not in seen]
            seen |= {r["date"] for r in page}
            rows += new
        first = min(seen) if seen else probed
        floors[pair] = {"probed": probed.isoformat(), "first_candle": first.isoformat()}
        # Crypto has no weekend, so every calendar day between listing and today is expected. That is what makes a hole a hole.
        expected = [first + timedelta(days=n) for n in range((today - first).days)]
        missing = [d.isoformat() for d in expected if d not in seen and d < today]
        if missing:
            gaps[pair] = {"holes": len(missing), "first": missing[0], "last": missing[-1],
                          "note": "days inside the record, after the first candle, that the endpoint did not serve"}
    rows.sort(key=lambda r: (r["date"], r["pair"]))
    manifest = {
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoint": CANDLE_URL.format(pair="{pair}") + "?granularity=86400",
        "granularity_seconds": 86400,
        "pairs": {p: {**floors[p], "floor_method": "lookback probe bisected to the day, floor taken from the first candle"} for p in pairs},
        "requests": requests,
        "rows": len(rows),
        "per_pair": {},
        "holes": gaps,
        "synthetic": False,
    }
    return rows, manifest


def write_snapshot(rows: list[dict], manifest: dict, stamp: str) -> Path:
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    target = SNAPSHOTS / stamp
    if target.exists():
        raise SystemExit(f"{target} already exists; snapshots are immutable, so this fetch would have to be a new stamp")
    target.mkdir(parents=True)

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["pair"], []).append(row)
    with (target / PRICES).open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "pair", "open", "high", "low", "close", "volume"])
        for row in rows:
            writer.writerow([row["date"].isoformat(), row["pair"], f"{row['open']:.8g}", f"{row['high']:.8g}",
                             f"{row['low']:.8g}", f"{row['close']:.8g}", f"{row['volume']:.10g}"])
    for pair, group in sorted(grouped.items()):
        manifest["per_pair"][pair] = {"rows": len(group), "first": group[0]["date"].isoformat(),
                                      "last": group[-1]["date"].isoformat()}
    blob = (target / PRICES).read_bytes()
    manifest["sha256"] = hashlib.sha256(blob).hexdigest()
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    pointer = CRYPTO / "current"
    if pointer.is_symlink() or pointer.exists():
        pointer.unlink()
    pointer.symlink_to(Path("snapshots") / stamp, target_is_directory=True)
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pairs", default=",".join(PAIRS), help="comma-separated Coinbase pairs")
    args = ap.parse_args()

    wanted = [x.strip() for x in args.pairs.split(",") if x.strip()]
    unknown = [x for x in wanted if x not in PAIRS]
    if unknown:
        raise SystemExit(f"unknown pair(s) {', '.join(unknown)}; this file knows {', '.join(PAIRS)}")
    pairs = tuple(wanted)

    rows, manifest = fetch(pairs)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = write_snapshot(rows, manifest, stamp)
    print(f"  {PRICES}: {manifest['rows']:,} rows, {len(manifest['pairs'])} pair(s), sha256 {manifest['sha256'][:12]}")
    for pair, facts in sorted(manifest["per_pair"].items()):
        print(f"    {pair:<9} {facts['rows']:>6,} sessions  {facts['first']} to {facts['last']}")
    for pair, facts in sorted(manifest["pairs"].items()):
        print(f"    {pair:<9} first candle {facts['first_candle']} (probe landed on {facts['probed']})")
    for pair, hole in sorted(manifest["holes"].items()):
        print(f"    {pair:<9} {hole['holes']} day(s) inside the record, after its first candle, that the endpoint did not serve, {hole['first']} to {hole['last']}")
    print(f"  data/crypto/current -> snapshots/{stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
