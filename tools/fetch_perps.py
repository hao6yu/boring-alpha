#!/usr/bin/env python3
"""Fetch the Binance USDT-M perpetual cross-section into a content-addressed snapshot: prices and funding, one venue, delisted symbols included.

Why this file exists: BA-007 ranks many crypto perps against each other, so its data spine needs three things no single live API offered
this machine on 2026-09-08 — a survivorship-bias-free symbol universe (today's listings only would inherit the bias before the first rank),
funding-rate history deep enough to score a carry signal (OKX serves three months), and an answer at all (Binance `fapi` answers 451,
Bybit 403). The public archive `data.binance.vision` answered 200 to all three questions, including the histories of delisted symbols
(`FTTUSDT` still serves its full record), and its decision record is `docs/decisions/2026-09-08-ba007-crypto-data-source.md`.

The rules it inherits from the equity and Coinbase fetchers are not decorative:

  * immutable snapshots under `data/perps/snapshots/<STAMP>/`, and `data/perps/current` repointed only after a complete write;
  * a manifest naming the endpoints, the request count, every symbol's floor, and the sha256 of each archived CSV;
  * a poisoned row — a non-numeric price, a high below the low, a non-positive price, an absurd funding rate — refuses the whole fetch,
    naming the symbol and the day. Half a record is worse than no record;
  * the session still in progress is dropped: a daily zip published for the running day, or any event dated today, is not an observation;
  * the record's floor is the first month the archive actually serves — and it is discovered by listing the archive's own keys, not by
    walking absent months. A delisted symbol's trailing months are simply not in its key listing, so no walk can stop early and no
    press-release date is ever believed.

Declared mechanics, both in the decision record: each symbol's served months are enumerated from the archive's key listing (which also
makes month gaps between the first and last served month visible and countable), the running month's prices come from the archive's daily
zips (monthly zips exist only for complete months), funding exists only as monthly zips through the last complete month, and transport
integrity is carried by the zip's own CRC plus the manifest's sha256 of each extracted CSV (the archive's `.CHECKSUM` sidecars are not
fetched, which halves the request count for the same guarantee).
"""

from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import http.client
import io
import json
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PERPS = ROOT / "data" / "perps"
SNAPSHOTS = PERPS / "snapshots"
CURRENT = PERPS / "current"
PRICES = "perps_daily.csv"
FUNDING = "funding_events.csv"

S3_BASE = "https://s3.ap-northeast-1.amazonaws.com/data.binance.vision"
KLINE_LIST_PREFIX = "data/futures/um/daily/klines/"
FUNDING_LIST_PREFIX = "data/futures/um/monthly/fundingRate/"
KLINE_MONTHLY_URL = S3_BASE + "/data/futures/um/monthly/klines/{sym}/1d/{sym}-1d-{ym}.zip"
KLINE_DAILY_URL = S3_BASE + "/data/futures/um/daily/klines/{sym}/1d/{sym}-1d-{ymd}.zip"
KLINE_MONTHLY_KEYS = "data/futures/um/monthly/klines/{sym}/1d/"
KLINE_DAILY_KEYS = "data/futures/um/daily/klines/{sym}/1d/{sym}-1d-{ym}-"
FUNDING_MONTHLY_URL = S3_BASE + "/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip"
FUNDING_KEYS = "data/futures/um/monthly/fundingRate/{sym}/"

#: Funding intervals this archive ships: 8h historically, 4h on many symbols, 1h on the newest listings (measured 2026-09-08 across a
#: 30-symbol sample: 2,451 rows at 4h, 1,402 at 8h, 6 at 1h). 2h is accepted as declared-but-unobserved; anything else is not a rate cadence.
FUNDING_INTERVALS = (1.0, 2.0, 4.0, 8.0)
#: A funding rate beyond ±5% per event is not a rate, it is a broken row.
MAX_FUNDING_RATE = 0.05
MIN_REQUEST_INTERVAL = 0.03
USER_AGENT = "boring-alpha/1.0 (research; stdlib urllib)"

_NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}


def _sym_url(sym: str) -> str:
    """The symbol as it belongs in a URL: percent-encoded. The archive's universe contains symbols whose names are not ASCII
    (five Chinese-named listings as of 2026-09-08), and an archive that lists them is a fact the fetch must survive, not filter."""

    return urllib.parse.quote(sym, safe="")


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"] > 0:
        return context
    import fetch_market_data as fm                                          # noqa: PLC0415  the equity fetcher already solved TLS
    return fm._ssl_context()                                                # noqa: SLF001  one answer to "where are the CAs", in one file


_CONTEXT = _ssl_context()
_PACE_LOCK = threading.Lock()
_PACE_LAST = 0.0
_STAT_LOCK = threading.Lock()


def _pace() -> None:
    global _PACE_LAST
    with _PACE_LOCK:
        now = time.monotonic()
        wait = _PACE_LAST + MIN_REQUEST_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _PACE_LAST = now


_THREAD_LOCAL = threading.local()


def _get(url: str) -> bytes | None:
    """One paced GET on a persistent per-thread connection. 404 is a normal answer here — an absent file — so it returns None.

    The endpoint throttles by dropping new handshakes (observed 2026-09-08: a connection parked in SYN_SENT for minutes while
    established ones kept serving), and a per-request connection pays that drop on every single file. A keep-alive connection per
    worker thread pays it once and then keeps serving — the same request stream, a fraction of the handshakes.
    """

    parsed = urllib.parse.urlsplit(url)
    target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    last_error: Exception | None = None
    for attempt in range(5):
        _pace()
        conn = getattr(_THREAD_LOCAL, "conn", None)
        if conn is None:
            conn = http.client.HTTPSConnection(parsed.hostname, timeout=60, context=_CONTEXT)
            _THREAD_LOCAL.conn = conn
        try:
            conn.request("GET", target, headers={"User-Agent": USER_AGENT})
            response = conn.getresponse()
            body = response.read()
            if response.status == 404:
                return None
            if response.status >= 500:
                last_error = urllib.error.HTTPError(url, response.status, response.reason, None, None)
                _THREAD_LOCAL.conn = None
                conn.close()
                time.sleep(1.0 + attempt)
                continue
            return body
        except (OSError, http.client.HTTPException) as error:
            # A dead or half-dead keep-alive socket: the raw socket failures surface while reading the body, past the point where
            # urllib would wrap them. Drop the connection and retry on a fresh one — at this volume the archive does reset.
            last_error = error
            _THREAD_LOCAL.conn = None
            try:
                conn.close()
            except OSError:
                pass
            time.sleep(1.0 + attempt)
    raise SystemExit(f"{url}: unreachable after 5 attempts ({last_error}); refusing to archive a half-fetched symbol") from None


def _listed_names(prefix: str, counter: dict, expect: bool = True, delimiter: bool = False) -> list[str]:
    """The names an S3 listing serves — symbol prefixes under a delimiter listing, keys under a flat one."""

    names: list[str] = []
    marker = ""
    base = f"{S3_BASE}?prefix={urllib.parse.quote(prefix)}&max-keys=1000" + ("&delimiter=/" if delimiter else "")
    while True:
        page_url = base + (f"&marker={urllib.parse.quote(marker)}" if marker else "")
        blob = _get(page_url)
        with _STAT_LOCK:
            counter["requests"] += 1
        if blob is None:
            if expect:
                raise SystemExit(f"listing {prefix}: the archive answered 404 for a listing that must exist")
            return names
        root = ET.fromstring(blob)
        names += [node.text for node in root.findall("s:Contents/s:Key", _NS)]
        names += [node.text for node in root.findall("s:CommonPrefixes/s:Prefix", _NS)]
        if root.findtext("s:IsTruncated", "false", _NS) != "true":
            return names
        next_marker = root.findtext("s:NextMarker", None, _NS) or (names[-1] if names else None)
        if next_marker is None:
            raise SystemExit(f"listing {prefix}: truncated without a NextMarker; refusing to enumerate a partial universe")
        marker = next_marker


def list_symbols(prefix: str) -> list[str]:
    """Symbol directories under one archive prefix, from the S3 XML listing itself — including delisted symbols."""

    return sorted(name[len(prefix):].strip("/") for name in
                  _listed_names(prefix, {"requests": 0}, delimiter=True))


def _ym_of(key: str, sym: str, kind: str) -> str:
    """The YYYY-MM a zip key carries, or a refusal: a key this archive served must name a month this lab can parse."""

    tail = key.rsplit("/", 1)[-1]
    stem = tail.replace(".zip", "")
    tag = f"{sym}-1d-" if kind == "kline" else f"{sym}-fundingRate-"
    ym = stem.replace(tag, "")
    if len(ym) != 7 or ym[4] != "-" or not ym[:4].isdigit() or not ym[5:7].isdigit():
        raise SystemExit(f"{sym}: a {kind} key this lab cannot read as a month ({key!r})")
    return ym


def last_complete_month(today: date) -> str:
    """The newest month whose monthly zips can exist: they are published at month end, so the running month is never served."""

    first_of_month = today.replace(day=1)
    december = first_of_month - timedelta(days=1)
    return f"{december.year:04d}-{december.month:02d}"


def _day_of(ms: int, sym: str, column: str) -> date:
    """A millisecond UTC stamp to a date, with the microsecond defence: some archives ship µs where ms is promised."""

    if ms >= 10**14:
        ms //= 1000
    try:
        return datetime.fromtimestamp(ms / 1000, timezone.utc).date()
    except (ValueError, OverflowError, OSError):
        raise SystemExit(f"{sym}: a {column} that is not a plausible timestamp ({ms})") from None


def _float(value: str, sym: str, day, column: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise SystemExit(f"{sym} {day}: a {column} that is not numeric ({value!r})") from None


def parse_kline_csv(blob: bytes, sym: str, today: date) -> list[dict]:
    """Daily rows from one kline zip, validated. The session in progress is not a session."""

    rows = []
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:                       # a corrupted zip fails CRC here: transport integrity
        text = archive.read(archive.namelist()[0]).decode()
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) < 12:
            raise SystemExit(f"{sym}: a kline row with {len(parts)} columns, expected 12 ({line[:80]!r})")
        open_ms = int(_float(parts[0], sym, None, "open_time"))
        day = _day_of(open_ms, sym, "open_time")
        if open_ms % 86_400_000 != 0:
            raise SystemExit(f"{sym} {day}: a daily bar that does not open at 00:00 UTC ({open_ms})")
        if day >= today:
            continue                                                        # the session still in progress is not a session
        o, h, low, c = (_float(parts[i], sym, day, name)
                        for i, name in ((1, "open"), (2, "high"), (3, "low"), (4, "close")))
        volume = _float(parts[5], sym, day, "volume")
        quote_volume = _float(parts[7], sym, day, "quote_volume")
        if min(o, h, low, c) <= 0.0 or h < low:
            raise SystemExit(f"{sym} {day}: an impossible candle (o {o}, h {h}, l {low}, c {c})")
        rows.append({"date": day, "symbol": sym, "open": o, "high": h, "low": low,
                     "close": c, "base_volume": volume, "quote_volume": quote_volume})
    return rows


def parse_funding_csv(blob: bytes, sym: str) -> list[dict]:
    """Funding events from one monthly zip, validated: a numeric rate inside the plausible band, on a unique timestamp."""

    events = []
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        text = archive.read(archive.namelist()[0]).decode()
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) < 3:
            raise SystemExit(f"{sym}: a funding row with {len(parts)} columns, expected 3 ({line[:80]!r})")
        stamp_ms = int(_float(parts[0], sym, None, "calc_time"))
        interval = _float(parts[1], sym, None, "funding_interval_hours")
        rate = _float(parts[2], sym, None, "last_funding_rate")
        if interval not in FUNDING_INTERVALS:
            raise SystemExit(f"{sym}: a funding interval this archive has not declared ({interval}h)")
        if abs(rate) > MAX_FUNDING_RATE:
            raise SystemExit(f"{sym}: a funding rate outside the plausible band ({rate} at {stamp_ms})")
        events.append({"ts_ms": stamp_ms, "symbol": sym, "interval_hours": interval, "rate": rate})
    return events


def _zip_bytes(url: str, counter: dict) -> bytes | None:
    blob = _get(url)
    with _STAT_LOCK:
        counter["requests"] += 1
        if blob is None:
            counter["absent"] += 1
    return blob


def symbol_klines(sym: str, today: date, counter: dict) -> tuple[list[dict], dict]:
    """Every kline this archive serves for one symbol — months enumerated from the archive's own keys — plus the facts about the record."""

    months = sorted({_ym_of(key, sym, "kline") for key in
                     _listed_names(KLINE_MONTHLY_KEYS.format(sym=sym), counter, expect=False)
                     if key.endswith(".zip")})
    if not months:
        return [], {"rows": 0, "first_month": None, "last_month": None, "note": "no monthly kline keys served"}

    # The current (incomplete) month arrives as daily zips; its keys are listed with the month as a prefix.
    daily_keys = [key for key in _listed_names(KLINE_DAILY_KEYS.format(sym=sym, ym=today.strftime("%Y-%m")),
                                               counter, expect=False)
                  if key.endswith(".zip")]
    daily_rows: list[dict] = []
    for key in sorted(daily_keys):
        ymd = key.rsplit("/", 1)[-1].replace(f"{sym}-1d-", "").replace(".zip", "")
        if date.fromisoformat(ymd) >= today:
            continue
        blob = _zip_bytes(KLINE_DAILY_URL.format(sym=_sym_url(sym), ymd=ymd), counter)
        if blob is not None:
            daily_rows += parse_kline_csv(blob, sym, today)

    rows: list[dict] = []
    listed_but_absent = 0
    for ym in months:
        blob = _zip_bytes(KLINE_MONTHLY_URL.format(sym=_sym_url(sym), ym=ym), counter)
        if blob is None:
            listed_but_absent += 1                                          # the listing promised it; the archive did not serve it
            continue
        rows += parse_kline_csv(blob, sym, today)
    rows += daily_rows                                                      # the running month's completed days are part of the record
    rows.sort(key=lambda r: r["date"])

    # Holes are judged inside the observed span only: between the first and last candle the archive actually served. A record that ends
    # mid-month (a delisting day) is indistinguishable in this archive from a truncated month, so trailing silence after the last candle
    # is the record's end, not a hole — the manifest's last_candle is what a later round judges. Calendar months between the first and
    # last served month that the listing does not contain are month gaps, counted as such.
    served = {ym for ym in months}
    expected_months = []
    year, month = int(months[0][:4]), int(months[0][5:7])
    while f"{year:04d}-{month:02d}" <= months[-1]:
        expected_months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    month_gaps = [ym for ym in expected_months if ym not in served]

    holes: list[str] = []
    by_month: dict[str, set[date]] = {}
    for row in rows:
        by_month.setdefault(row["date"].strftime("%Y-%m"), set()).add(row["date"])
    first_candle, last_candle = rows[0]["date"], rows[-1]["date"]
    for ym in sorted(by_month):
        year, month = int(ym[:4]), int(ym[5:7])
        month_start = date(year, month, 1)
        month_end = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
        day = max(month_start, first_candle)
        while day <= min(month_end, last_candle):
            if day not in by_month[ym]:
                holes.append(day.isoformat())
            day += timedelta(days=1)
    holes.sort()

    stats = {"rows": len(rows), "first_month": months[0], "last_month": months[-1],
             "month_gaps": len(month_gaps), "listed_but_absent": listed_but_absent}
    if rows:
        stats |= {"first_candle": rows[0]["date"].isoformat(), "last_candle": rows[-1]["date"].isoformat(),
                  "day_holes": holes}
    return rows, stats


def symbol_funding(sym: str, floor_ym: str | None, today: date, counter: dict) -> tuple[list[dict], dict]:
    """Funding events for one symbol: exactly the months its own key listing contains, never the running month, never before its listing."""

    ceiling = last_complete_month(today)
    months = sorted({_ym_of(key, sym, "funding") for key in
                     _listed_names(FUNDING_KEYS.format(sym=sym), counter, expect=False)
                     if key.endswith(".zip")})
    months = [ym for ym in months if ym <= ceiling and (floor_ym is None or ym >= floor_ym)]
    events: list[dict] = []
    for ym in months:
        blob = _zip_bytes(FUNDING_MONTHLY_URL.format(sym=_sym_url(sym), ym=ym), counter)
        if blob is not None:
            events += parse_funding_csv(blob, sym)
    events.sort(key=lambda e: (e["ts_ms"], e["symbol"]))
    stats = {"events": len(events), "months": len(months),
             "first_month": months[0] if months else None}
    return events, stats


def fetch_symbol_with_funding(sym: str, funding_symbols: set[str], today: date,
                              counter: dict) -> tuple[list[dict], list[dict], dict, dict]:
    """One symbol's whole record: klines, funding (when the archive has a directory for it), and both stats dicts."""

    rows, stats = symbol_klines(sym, today, counter)
    if sym in funding_symbols:
        events, fstats = symbol_funding(sym, stats.get("first_month"), today, counter)
    else:
        events, fstats = [], {"events": 0, "first_month": None, "note": "no funding directory in this archive"}
    return rows, events, stats, fstats


def fetch(today: date | None = None) -> tuple[list[dict], list[dict], dict]:
    """The whole cross-section in memory: every symbol's klines, every funding event, and the manifest that says how it was obtained.

    This is the tested in-memory shape. The production entry point is the resumable workspace below — an archive that takes hours must not
    lose its work because a laptop slept.
    """

    now = datetime.now(timezone.utc)
    today = today or now.date()
    counter = {"requests": 0, "absent": 0}

    kline_symbols = list_symbols(KLINE_LIST_PREFIX)
    funding_symbols = set(list_symbols(FUNDING_LIST_PREFIX))

    all_rows: list[dict] = []
    all_events: list[dict] = []
    manifest: dict = {
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoints": {"kline_monthly": KLINE_MONTHLY_URL, "kline_daily": KLINE_DAILY_URL,
                      "funding_monthly": FUNDING_MONTHLY_URL, "listing": S3_BASE},
        "universe": {"kline_symbols": len(kline_symbols), "funding_symbols": len(funding_symbols),
                     "note": "the kline listing includes delisted symbols; funding exists for a subset"},
        "requests": 0, "absent_requests": 0, "rows": 0, "events": 0,
        "per_symbol": {}, "funding_per_symbol": {}, "synthetic": False,
    }

    def work(sym: str) -> None:
        rows, events, stats, fstats = fetch_symbol_with_funding(sym, funding_symbols, today, counter)
        all_rows.extend(rows)
        all_events.extend(events)
        manifest["per_symbol"][sym] = stats
        manifest["funding_per_symbol"][sym] = fstats

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(work, kline_symbols))

    all_rows.sort(key=lambda r: (r["date"], r["symbol"]))
    all_events.sort(key=lambda e: (e["ts_ms"], e["symbol"]))
    manifest["requests"] = counter["requests"]
    manifest["absent_requests"] = counter["absent"]
    manifest["rows"] = len(all_rows)
    manifest["events"] = len(all_events)
    manifest["symbols_with_rows"] = sum(1 for s in manifest["per_symbol"].values() if s["rows"])
    manifest["day_holes"] = sum(len(s.get("day_holes", [])) for s in manifest["per_symbol"].values())
    return all_rows, all_events, manifest


# ---------------------------------------------------------------- the resumable workspace --------------------------------------------------------

WORKSPACE_SUFFIX = ".partial"
PROGRESS = "progress.json"


def _atomic_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def open_workspace(today: date) -> tuple[Path, dict]:
    """Create or resume this run's workspace: a .partial snapshot directory whose progress ledger makes every finished symbol permanent."""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    existing = sorted(SNAPSHOTS.glob(f"*{WORKSPACE_SUFFIX}"))
    if existing:
        workspace = existing[-1]                                            # resume the newest partial; one bootstrap at a time
    else:
        workspace = SNAPSHOTS / f"{stamp}{WORKSPACE_SUFFIX}"
        workspace.mkdir()
        (workspace / "parts").mkdir()
    progress_path = workspace / PROGRESS
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {"done": {}}
    progress.setdefault("done", {})
    progress["today"] = today.isoformat()
    return workspace, progress


def mark_done(workspace: Path, progress: dict, sym: str) -> None:
    progress["done"][sym] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _atomic_json(workspace / PROGRESS, progress)


def fetch_into_workspace(workspace: Path, progress: dict, today: date | None = None) -> tuple[dict, dict, int]:
    """One pass over every symbol the ledger does not already account for, persisting each to its own part files as it lands."""

    now = datetime.now(timezone.utc)
    today = today or now.date()
    counter = {"requests": 0, "absent": 0}
    kline_symbols = list_symbols(KLINE_LIST_PREFIX)
    funding_symbols = set(list_symbols(FUNDING_LIST_PREFIX))
    remaining = [s for s in kline_symbols if s not in progress["done"]]
    manifest = {
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoints": {"kline_monthly": KLINE_MONTHLY_URL, "kline_daily": KLINE_DAILY_URL,
                      "funding_monthly": FUNDING_MONTHLY_URL, "listing": S3_BASE},
        "universe": {"kline_symbols": len(kline_symbols), "funding_symbols": len(funding_symbols),
                     "note": "the kline listing includes delisted symbols; funding exists for a subset"},
        "synthetic": False, "today": today.isoformat(),
    }

    def work(sym: str) -> None:
        rows, events, stats, fstats = fetch_symbol_with_funding(sym, funding_symbols, today, counter)
        with (workspace / "parts" / f"{sym}.prices.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", "symbol", "open", "high", "low", "close", "base_volume", "quote_volume"])
            for row in rows:
                writer.writerow([row["date"].isoformat(), row["symbol"], f"{row['open']:.8g}", f"{row['high']:.8g}",
                                 f"{row['low']:.8g}", f"{row['close']:.8g}", f"{row['base_volume']:.10g}",
                                 f"{row['quote_volume']:.10g}"])
        with (workspace / "parts" / f"{sym}.funding.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ts_utc", "symbol", "interval_hours", "rate"])
            for event in events:
                stamp_utc = datetime.fromtimestamp(event["ts_ms"] / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                writer.writerow([stamp_utc, event["symbol"], f"{event['interval_hours']:g}", f"{event['rate']:.12g}"])
        _atomic_json(workspace / "parts" / f"{sym}.stats.json",
                     {"prices": stats, "funding": fstats})
        mark_done(workspace, progress, sym)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(work, remaining))
    still_remaining = [s for s in kline_symbols if s not in progress["done"]]
    return manifest, counter, still_remaining


def finalize_workspace(workspace: Path, progress: dict, manifest: dict, counter: dict) -> Path:
    """Concatenate every part into the two archive CSVs, pin their sha256, seal the manifest, and only then claim the snapshot name.

    The immutability guard is the first statement, not a formality before the rename: a finalized workspace is gone (renamed), and a
    second attempt must refuse before it touches anything, not fail mid-write on a directory that no longer exists.
    """

    stamp = workspace.name[:-len(WORKSPACE_SUFFIX)]
    final = SNAPSHOTS / stamp
    if final.exists():
        raise SystemExit(f"{final} already exists; snapshots are immutable")
    done = sorted(progress["done"])
    prices_tmp, funding_tmp = workspace / f"{PRICES}.tmp", workspace / f"{FUNDING}.tmp"
    rows = events = 0
    with prices_tmp.open("w", newline="") as prices_handle, funding_tmp.open("w", newline="") as funding_handle:
        prices_writer = csv.writer(prices_handle)
        funding_writer = csv.writer(funding_handle)
        prices_writer.writerow(["date", "symbol", "open", "high", "low", "close", "base_volume", "quote_volume"])
        funding_writer.writerow(["ts_utc", "symbol", "interval_hours", "rate"])
        per_symbol, funding_per_symbol = {}, {}
        day_holes = 0
        for sym in done:
            stats = json.loads((workspace / "parts" / f"{sym}.stats.json").read_text())
            per_symbol[sym] = stats["prices"]
            funding_per_symbol[sym] = stats["funding"]
            day_holes += len(stats["prices"].get("day_holes", []))
            with (workspace / "parts" / f"{sym}.prices.csv").open(newline="") as handle:
                for row in csv.reader(handle):
                    if row[0] == "date":
                        continue
                    prices_writer.writerow(row)
                    rows += 1
            with (workspace / "parts" / f"{sym}.funding.csv").open(newline="") as handle:
                for row in csv.reader(handle):
                    if row[0] == "ts_utc":
                        continue
                    funding_writer.writerow(row)
                    events += 1
        manifest["per_symbol"] = per_symbol
        manifest["funding_per_symbol"] = funding_per_symbol
        manifest["day_holes"] = day_holes
        manifest["symbols_with_rows"] = sum(1 for s in per_symbol.values() if s["rows"])
    prices_tmp.replace(workspace / PRICES)
    funding_tmp.replace(workspace / FUNDING)
    manifest["requests"] = counter["requests"]
    manifest["absent_requests"] = counter["absent"]
    manifest["rows"] = rows
    manifest["events"] = events
    manifest["sha256"] = {PRICES: hashlib.sha256((workspace / PRICES).read_bytes()).hexdigest(),
                          FUNDING: hashlib.sha256((workspace / FUNDING).read_bytes()).hexdigest()}
    (workspace / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    workspace.rename(final)
    pointer = CURRENT
    if pointer.is_symlink() or pointer.exists():
        pointer.unlink()
    pointer.symlink_to(Path("snapshots") / stamp, target_is_directory=True)
    return final


def main() -> int:
    started = time.monotonic()
    today = datetime.now(timezone.utc).date()
    workspace, progress = open_workspace(today)
    done_before = len(progress["done"])
    print(f"  workspace {workspace.name}: {done_before} symbol(s) already done, resuming" if done_before
          else f"  workspace {workspace.name}: fresh", flush=True)
    stall = 0
    while True:
        manifest, counter, remaining = fetch_into_workspace(workspace, progress, today)
        total_done = len(progress["done"])
        print(f"  pass done: {total_done} symbol(s) recorded ({remaining} were remaining this pass, "
              f"{counter['requests']:,} requests, {counter['absent']:,} absent)", flush=True)
        if not remaining:
            break
        stall = stall + 1 if total_done == done_before else 0
        done_before = total_done
        if stall >= 3:
            raise SystemExit("three consecutive passes with no progress: the archive is not answering; the workspace is kept for resume")
    final = finalize_workspace(workspace, progress, manifest, counter)
    print(f"  {PRICES}: {manifest['rows']:,} rows over {manifest['symbols_with_rows']} symbol(s), "
          f"sha256 {manifest['sha256'][PRICES][:12]}")
    print(f"  {FUNDING}: {manifest['events']:,} events, sha256 {manifest['sha256'][FUNDING][:12]}")
    print(f"  day holes inside served spans: {manifest['day_holes']}; wall time {time.monotonic() - started:,.0f}s")
    print(f"  data/perps/current -> snapshots/{final.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
