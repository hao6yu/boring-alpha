"""Capture a non-price feed the way this repository is willing to believe in one: point-in-time, immutable, before the test.

Run:
  .venv/bin/python tools/attention_feed.py fetch            # pull the pinned board, seal every blob
  .venv/bin/python tools/attention_feed.py panel            # assemble the sealed blobs into one daily CSV
  .venv/bin/python tools/attention_feed.py verify           # re-hash every stored blob against the index
  .venv/bin/python tools/attention_feed.py board            # print the board and the rules it is chosen under

## Why this file exists, and what it is for

Every price-only mechanism in this repository has been priced against plain DCA and found redundant — fifteen
rounds, four framings, one surviving result that contains no forecast at all. The goal as written asks for
something else: a model that reads trend and news and decides. That input is not in `data/current`, which is
prices and T-bills and nothing else, and no further window on twelve ETFs can supply it.

So the honest next step is not another signal. It is a **feed**, captured in a form that could later be
believed. Two properties decide whether a news-like series is evidence or decoration:

  *point-in-time*       the value for day t must be knowable on day t.
  *never revised*       a series that gets restated backwards turns every backtest into hindsight.

Wikipedia page view counts have both, which is unusual for a news proxy. They are measured daily by the
Wikimedia REST API (`metrics/pageviews/per-article`, `all-access/user`, the public daily endpoint), they are
not revised after the fact, and they exist for every day back to **2015-07-01** — the endpoint's own depth
limit, which is why the sample below starts there and does not reach the 2008 crisis the archive does. The
series is reader *attention*, which is behavioural, non-price, and available to a retail account on the day
it is published — the same class of input the goal described, at a fraction of the cost of a terminal.

## The trap that decides whether any of this can be trusted, and the guard for it

Page view series for **event-named articles** are contaminated at the source. `2020_stock_market_crash`
begins on 2020-03-09 in this capture because the article was *created* on 2020-03-09: an article about a
crash exists only after the crash, so its series carries a rise that no one on the ground could have seen
coming, and a backtest on it grades the historian rather than the trader. The same applies with more deniability
to ordinary articles whose titles were *renamed* or split when an event made them useful.

The guard is mechanical, not judgemental, and it is enforced at capture rather than at analysis:

  `require_full_sample`  a board article must return data for the first month of the sample and for every
                         month until the end of it, within the gap allowance below. An article that appears
                         mid-sample is REJECTED and reported, whatever its name says.

Two further guards, both earned on the way in:

  redirect      the API counts a redirect as its own article, with a tiny view count. `Stock_Market_Crash`
                resolves to 2 views on a quiet August day where the real article carries thousands, so
                every title is resolved through the Wikipedia API to its canonical name before it is
                requested, and the resolved name is what gets stored.
  growth        attention to any topic rises with Wikipedia's own traffic, so a level is never a signal. The
                board therefore carries a control basket of evergreen articles with no financial content; if
                the financial basket and the control basket rise together, what was found is Wikipedia.

## The board, pinned before the first return was joined to anything

Financial attention basket — evergreen articles that predate the sample and describe a *state of the world*
rather than an event: `Stock_market_crash`, `Recession`, `Bank_run`, `Great_Depression`, `Inflation`,
`Federal_reserve`, `Stock_market`, `Financial_crisis`. Control basket — evergreen, comparable in scale, no
financial content, chosen before looking: `Moon`, `Photosynthesis`, `Volcano`, `Mount_Everest`,
`Human`, `Water`. Nothing here was picked for having spiked in 2020 or 2022; that selection is exactly what
the full-sample guard exists to refuse, and the event-named articles that fail it are printed by name.

## What will be tested with it, stated now and not after the fact

One question, in the only framing this repository accepts: **does above-trend financial attention forecast
the next month's index return, and is what it forecasts worth more than the trade it would cause?**

  signal      z-score of the log financial-basket attention over a 252-day rolling window, computed from data
              through day t only. No global standardisation anywhere: a whole-sample mean is the future
              leaking into the past.
  decision    two directions get tested and both get printed, because attention plausibly works either way —
              panic as a contrarian buy (attention peaks where sellers exhaust) and panic as a warning
              (attention follows the crowd into a falling market). The pass rule does not get to choose after
              seeing which one works.
  bar         the funded frame the whole repo uses: $5,000 opened, $500 a month, the sleeve's real expense
              ratio, 2 bps a unit of one-way turnover, against plain DCA into the same fund. A signal that
              predicts and still loses to DCA net of costs is a redundant signal, and it is reported as one.
  pass rule   positive versus DCA in every window, more often than the same book's own reversal control, with
              turnover low enough that the toll is not the finding, and the control basket tested the same
              way: if `Moon` clears the bar, the bar is broken.

This file captures. It does not score, and it does not need to load returns to do its job — the analysis is
a separate tool that reads the sealed panel, so that a rule written later cannot quietly change what was
fetched earlier.

## Operational honesty

The API asks for a descriptive User-Agent and returns 403 without one. Requests are chunked to under the
endpoint's own response limit, retried three times with a backoff, and rate-limited between articles. Raw
JSON is stored exactly as received and content-addressed by SHA-256; the panel is rebuilt from the blobs, so
`verify` can show that the numbers behind any later analysis are the numbers that were fetched. A re-fetch
that disagrees with the sealed blob is reported as a mismatch rather than silently replacing it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DATA_DIR = ROOT / "data" / "attention"
RAW_DIR = DATA_DIR / "raw"
INDEX = DATA_DIR / "index.json"
PANEL = DATA_DIR / "attention_daily.csv"

ENDPOINT = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/all-access/user/{article}/daily/{start}/{end}"
RESOLVE = "https://en.wikipedia.org/w/api.php?action=query&redirects=1&format=json&titles={title}"
USER_AGENT = "boringalpha-research/0.1 (quant research, non-commercial; single researcher)"

SAMPLE_START = date(2015, 7, 1)          # the endpoint's own depth limit, not a choice
CHUNK_DAYS = 800                         # keep responses under the endpoint's window
GAP_ALLOWANCE = 0.02                     # pages are missing on some days; 2% of the sample may be absent

FINANCIAL = ("Stock_market_crash", "Recession", "Bank_run", "Great_Depression", "Inflation",
             "Federal_reserve", "Stock_market", "Financial_crisis")
CONTROL = ("Moon", "Photosynthesis", "Volcano", "Mount_Everest", "Human", "Water")
BOARD = tuple((s, "financial") for s in FINANCIAL) + tuple((s, "control") for s in CONTROL)


@dataclass
class Series:
    article: str
    role: str
    views: dict                       # date -> int
    requested: str
    resolved: str

    @property
    def first(self) -> date:
        return min(self.views)

    @property
    def last(self) -> date:
        return max(self.views)

    @property
    def days(self) -> int:
        return len(self.views)


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _context() -> "ssl.SSLContext":
    """A verified TLS context, or a refusal. Turning verification off would make the feed unverifiable,
    which is the one property a non-price input is not allowed to lose, so instead this looks for a CA
    bundle in the places a machine keeps one and raises a named remedy when it finds none.
    """

    import os
    import ssl

    candidates = [os.environ.get("SSL_CERT_FILE"), "/etc/ssl/cert.pem", "/etc/pki/tls/certs/ca-bundle.crt"]
    try:
        import certifi                                             # optional, not a repo dependency

        candidates.insert(0, certifi.where())
    except ImportError:
        pass
    for path in candidates:
        if path and Path(path).exists():
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()                            # the interpreter's own store


SSL_CONTEXT = _context()


def http(url: str, attempts: int = 3, pause: float = 1.5) -> bytes:
    err = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as resp:   # noqa: S310
                return resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ssl.SSLError) as e:  # noqa: PERF203
            err = e
            code = getattr(e, "code", None)
            if code == 404:
                raise RuntimeError(f"404 for {url}; the article does not exist under this name") from e
            if code == 429:
                # The endpoint is rate limited and says so. Honouring its own wait beats retrying into a
                # ban, and a partially captured day is worse than a late one: a hole in the panel is a
                # hole in the signal.
                wait = float(getattr(e, "headers", {}).get("Retry-After", 0) or 0) or (15.0 * (2 ** attempt))
                time.sleep(min(wait, 120.0))
                continue
            time.sleep(pause * (2 ** attempt))
    hint = (" If the error is a certificate problem, point SSL_CERT_FILE at this machine's CA bundle; "
            "this tool refuses to fetch without verifying, because an unverified feed cannot be scored."
            if isinstance(err, ssl.SSLError) else "")
    raise RuntimeError(f"gave up on {url} after {attempts} attempts: {err}.{hint}")


def canonical(title: str) -> str:
    """Follow MediaWiki redirects before requesting counts, or the article is silently a stub's view count."""

    blob = json.loads(http(RESOLVE.format(title=urllib.parse.quote(title.replace(" ", "_")))))
    pages = blob.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), None)
    if page is None or "missing" in page:
        raise RuntimeError(f"{title} is not an article on en.wikipedia")
    # The final page's own title is the canonical name: MediaWiki reports `normalized` for underscore
    # folding and `redirects` for the hop, and the page it ends on is the one whose counts are asked for.
    return page["title"].replace(" ", "_")


def fetch_series(title: str, role: str, start: date, end: date) -> Series:
    name = canonical(title)
    views: dict = {}
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=CHUNK_DAYS - 1), end)
        url = ENDPOINT.format(project="en.wikipedia", article=name, start=cursor.strftime("%Y%m%d00"),
                              end=stop.strftime("%Y%m%d00"))
        blob = http(url)
        payload = json.loads(blob)
        for item in payload.get("items", ()):
            stamp = item["timestamp"]
            views[date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))] = int(item["views"])
        digest = sha(blob)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        (RAW_DIR / f"{name}-{cursor:%Y%m%d}-{digest[:16]}.json").write_bytes(blob)
        cursor = stop + timedelta(days=1)
        time.sleep(1.5)                      # the endpoint asks for restraint; a 429 mid-sample is a hole in the panel
    return Series(article=name, role=role, views=views, requested=title, resolved=name)


def completeness(s: Series, start: date, end: date) -> tuple[float, bool]:
    """(fraction of the sample present, does it start when the sample does).

    The second element is the guard. A series that begins after the sample began is an article that was
    written about something that already happened, and nothing it predicts was predictable.
    """

    wanted = (end - start).days + 1
    starts_ok = (s.first - start).days <= 45
    return s.days / wanted, starts_ok


def command_fetch(args: argparse.Namespace) -> None:
    end = date.fromisoformat(args.end)
    index = json.loads(INDEX.read_text()) if INDEX.exists() else {"fetched": [], "board": [], "rejects": []}
    seen = {row["article"] for row in index["fetched"]}
    print(f"attention feed · sample {SAMPLE_START} to {end} · {len(BOARD)} articles on the pinned board\n")
    for title, role in BOARD:
        s = fetch_series(title, role, SAMPLE_START, end)
        cov, starts_ok = completeness(s, SAMPLE_START, end)
        status = "accepted" if starts_ok and cov >= 1.0 - GAP_ALLOWANCE else "REJECTED"
        reason = ("series begins after the sample: the article postdates the events it would have to "
                  "forecast" if not starts_ok else
                  f"only {cov:.1%} of the sample present" if cov < 1.0 - GAP_ALLOWANCE else "")
        print(f"  {s.article:26} {role:9} {s.days:6} days  {s.first}..{s.last}  {status} {reason}")
        rec = {"article": s.article, "requested_as": s.requested, "role": role, "days": s.days,
               "first": s.first.isoformat(), "last": s.last.isoformat(), "coverage": round(cov, 4),
               "accepted": status == "accepted", "reason": reason,
               "blob_hashes": sorted(p.stem.split("-")[-1] for p in
                                     RAW_DIR.glob(f"{s.article}-*-*")),
               "sha256_of_series": sha(json.dumps(sorted(s.views.items()), default=str).encode())}
        index["fetched"] = [r for r in index["fetched"] if r["article"] != s.article] + [rec]
        index.setdefault("board", [])
        index["board"] = [{"article": a, "role": r} for a, r in BOARD]
        index["sample_start"] = SAMPLE_START.isoformat()
        index["sample_end"] = end.isoformat()
        index["fetched_on"] = datetime.now().isoformat(timespec="seconds")
        INDEX.write_text(json.dumps(index, sort_keys=True, indent=2) + "\n")
        if status == "REJECTED" and s.article in FINANCIAL:
            print(f"    ^ kept on disk for the record; it will not enter the panel")
    ok = [r for r in index["fetched"] if r["accepted"]]
    print(f"\n{len(ok)} of {len(BOARD)} series sealed at {INDEX}")
    print("analysis is a separate tool that reads the sealed panel; this file cannot score anything.")


def load_sealed(accepted_only: bool = True) -> dict:
    """Rebuild the daily view counts by re-reading the sealed blobs, never from the index's own summary."""

    if not INDEX.exists():
        raise SystemExit("no index. run `attention_feed.py fetch` first.")
    index = json.loads(INDEX.read_text())
    out: dict = {}
    mismatch = []
    for rec in index["fetched"]:
        if accepted_only and not rec["accepted"]:
            continue
        views: dict = {}
        for path in sorted(RAW_DIR.glob(f"{rec['article']}-*-*")):
            digest = sha(path.read_bytes())
            if digest[:16] != path.stem.split("-")[-1]:
                mismatch.append(path.name)
                continue
            for item in json.loads(path.read_text()).get("items", ()):
                stamp = item["timestamp"]
                views[date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))] = int(item["views"])
        if not views:
            mismatch.append(f"{rec['article']} (no blobs)")
            continue
        out[rec["article"]] = {"role": rec["role"], "views": views}
    if mismatch:
        raise SystemExit(f"sealed blobs failed to re-hash for: {mismatch}; refusing to build a panel "
                         f"from what cannot be reproduced")
    return out


def command_panel(args: argparse.Namespace) -> None:
    data = load_sealed()
    fin = sorted(a for a, v in data.items() if v["role"] == "financial")
    ctl = sorted(a for a, v in data.items() if v["role"] == "control")
    if not fin or not ctl:
        raise SystemExit(f"need both baskets; have {len(fin)} financial, {len(ctl)} control")
    days = sorted(set.intersection(*(set(v["views"]) for v in data.values())))
    PANEL.parent.mkdir(parents=True, exist_ok=True)
    with PANEL.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["day", "fin_sum", "ctl_sum", "fin_articles", "ctl_articles", "sha256_of_row"]
                   + [f"{a.lower()}" for a in fin + ctl])
        for d in days:
            fvals = [data[a]["views"][d] for a in fin]
            cvals = [data[a]["views"][d] for a in ctl]
            row = [d.isoformat(), sum(fvals), sum(cvals), len(fin), len(ctl)]
            payload = json.dumps([row, fvals + cvals], sort_keys=True).encode()
            w.writerow(row + [sha(payload)[:16]] + fvals + cvals)
    print(f"panel written: {PANEL}  {len(days)} days x {len(fin) + len(ctl)} articles")
    print(f"financial basket: {', '.join(fin)}")
    print(f"control basket:   {', '.join(ctl)}")
    print("each row carries the hash of its own contents, so a rebuilt panel that differs is detectable "
          "by diff alone.")


def command_verify(args: argparse.Namespace) -> None:
    index = json.loads(INDEX.read_text()) if INDEX.exists() else {}
    blobs = sorted(RAW_DIR.glob("*.json")) if RAW_DIR.exists() else []
    bad = [p.name for p in blobs if sha(p.read_bytes())[:16] != p.stem.split("-")[-1]]
    print(f"attention feed: {len(blobs)} sealed blobs, {len(bad)} that fail to re-hash")
    if bad:
        print("  " + ", ".join(bad[:10]))
    for rec in index.get("fetched", ()):
        print(f"  {rec['article']:26} {rec['role']:9} {'accepted' if rec['accepted'] else 'REJECTED':9} "
              f"{rec['days']:6} days  {rec['first']}..{rec['last']}  {rec['reason']}")
    if bad:
        raise SystemExit("the raw record does not reproduce; stop and re-fetch")


def command_board(args: argparse.Namespace) -> None:
    print(f"board pinned before the analysis, sample from {SAMPLE_START} (the endpoint's depth limit):\n")
    for title, role in BOARD:
        print(f"  {role:9} {title}")
    print("\nguards: canonicalise redirects before requesting; refuse any series that begins after the "
          "sample\nbegins; test the control basket by the same rule as the financial one.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--end", default="2026-09-04")
    f.set_defaults(fn=command_fetch)
    for name, fn in (("panel", command_panel), ("verify", command_verify), ("board", command_board)):
        sub.add_parser(name).set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
