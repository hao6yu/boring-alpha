#!/usr/bin/env python3
"""Archive exact U.S. futures hourly candles for BA-009B, without credentials.

Candles are descriptive price proxies, never executable paired fills or
clearing/funding marks. Missing bars remain missing. No trading rules or P&L.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from fetch_market_data import _CONTEXT  # noqa: E402; verified OS CA fallback

API = "https://api.coinbase.com/api/v3/brokerage/market/"
SCHEMA = "us-futures-paired-hourly-history-v2"
HOUR = 3600
LIMIT = 350
# Public docs say 350, but a 2026-09-10 FCM probe returned only 300 per call.
# Keep windows at that observed ceiling; preserve the first probe as evidence.
PAGE_HOURS = 300
PAIRS = {"BTC": ("BIP-20DEC30-CDE", "BIT-25SEP26-CDE"),
         "ETH": ("ETP-20DEC30-CDE", "ET-25SEP26-CDE")}
REFERENCE = "https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-candles"


def iso(stamp: int) -> str:
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str) -> int:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None or stamp.timestamp() % HOUR:
        raise ValueError("time must be an explicit timezone-aware whole hour")
    return int(stamp.timestamp())


def windows(start: int, end: int) -> list[tuple[int, int]]:
    """Half-open windows; end-1 is sent to avoid API endpoint inclusivity."""
    if start % HOUR or end % HOUR or not 0 < end - start <= 90 * 24 * HOUR:
        raise ValueError("require whole-hour interval of at most 90 days")
    return [(a, min(a + PAGE_HOURS * HOUR, end)) for a in range(start, end, PAGE_HOURS * HOUR)]


def fetch(path: str) -> tuple[bytes, dict]:
    url, started = API + path, utcnow()
    request = urllib.request.Request(url, headers={"User-Agent": "BoringAlpha-Research/0.1",
                                                   "Accept": "application/json"})
    with urllib.request.urlopen(request, context=_CONTEXT, timeout=20) as response:
        raw, date = response.read(), response.headers.get("Date")
    json.loads(raw)
    return raw, {"url": url, "started_at": started, "received_at": utcnow(),
                 "http_date": date, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def normalize_candles(payload: dict, start: int, end: int) -> list[dict]:
    if not isinstance(payload.get("candles"), list) or len(payload["candles"]) > LIMIT:
        raise ValueError("missing candle array or more than 350 buckets")
    rows, seen = [], set()
    for item in payload["candles"]:
        try:
            stamp = int(item["start"])
            if str(stamp) != str(item["start"]) or stamp % HOUR or not start <= stamp < end:
                raise ValueError("candle outside requested whole-hour interval")
            if stamp in seen:
                raise ValueError("duplicate candle timestamp")
            row = {"start": stamp, **{key: float(item[key]) for key in ("open", "high", "low", "close", "volume")}}
            if not all(math.isfinite(row[k]) and row[k] > 0 for k in ("open", "high", "low", "close")):
                raise ValueError("nonfinite or nonpositive candle price")
            if not math.isfinite(row["volume"]) or row["volume"] < 0:
                raise ValueError("invalid candle volume")
            if not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
                raise ValueError("inconsistent OHLC range")
        except (KeyError, TypeError, OverflowError) as exc:
            raise ValueError("malformed candle") from exc
        seen.add(stamp)
        rows.append(row)
    return sorted(rows, key=lambda row: row["start"])


def missing_ranges(expected: set[int], present: set[int]) -> list[dict]:
    missing = sorted(expected - present)
    spans = []
    for stamp in missing:
        if spans and stamp == spans[-1]["end_exclusive"]:
            spans[-1]["end_exclusive"] += HOUR
            spans[-1]["hours"] += 1
        else:
            spans.append({"start": stamp, "end_exclusive": stamp + HOUR, "hours": 1})
    return [{"start": iso(row["start"]), "end_exclusive": iso(row["end_exclusive"]),
             "hours": row["hours"]} for row in spans]


def distribution(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"count": len(values), "min": min(values), "median": statistics.median(values),
            "max": max(values)}


def paired_rows(perp: list[dict], dated: list[dict]) -> list[dict]:
    """Exact bucket join; both closes occur sometime inside their own hour."""
    a, b = ({row["start"]: row for row in series} for series in (perp, dated))
    return [{"start": stamp, "bucket_end": stamp + HOUR,
             "perp_close": a[stamp]["close"], "dated_close": b[stamp]["close"],
             "gap_usd_per_underlying": b[stamp]["close"] - a[stamp]["close"],
             "gap_bps_of_perp": (b[stamp]["close"] / a[stamp]["close"] - 1) * 10000,
             "both_have_reported_volume": a[stamp]["volume"] > 0 and b[stamp]["volume"] > 0}
            for stamp in sorted(a.keys() & b.keys())]


def describe_pair(perp: list[dict], dated: list[dict], start: int, end: int) -> dict:
    rows = paired_rows(perp, dated)
    by_time = {row["start"]: row for row in rows}
    expected = set(range(start, end, HOUR))
    changes = {}
    for hours in (1, 24, 168):
        values = []
        for row in rows:
            stamp = row["start"]
            if all(t in by_time and by_time[t]["both_have_reported_volume"]
                   for t in range(stamp - hours * HOUR, stamp + HOUR, HOUR)):
                values.append(row["gap_usd_per_underlying"] - by_time[stamp - hours * HOUR]["gap_usd_per_underlying"])
        changes[str(hours)] = distribution(values)
    active = [row for row in rows if row["both_have_reported_volume"]]
    return {"paired_buckets": len(rows), "expected_calendar_buckets": len(expected),
            "paired_calendar_coverage": len(rows) / len(expected),
            "first_bucket_start": iso(rows[0]["start"]) if rows else None,
            "last_bucket_start": iso(rows[-1]["start"]) if rows else None,
            "missing_paired_ranges": missing_ranges(expected, set(by_time)),
            "both_have_reported_volume_buckets": len(active),
            "gap_usd_per_underlying_on_positive_volume_buckets": distribution([r["gap_usd_per_underlying"] for r in active]),
            "gap_bps_on_positive_volume_buckets": distribution([r["gap_bps_of_perp"] for r in active]),
            "gap_changes_usd_per_underlying_contiguous_positive_volume_hours": changes,
            "gap_change_sign": "exit gap minus entry gap; negative is narrowing; not strategy P&L"}


def load_snapshot(snapshot: Path) -> tuple[dict, dict[str, list[dict]], dict[str, dict]]:
    """Return (manifest, candles_by_exact_product_id, metadata_by_product_id)."""
    manifest = json.loads((snapshot / "manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or manifest.get("pairs") != {k: list(v) for k, v in PAIRS.items()}:
        raise ValueError("wrong history schema or contracts")
    start, end = manifest["start"], manifest["end_exclusive"]
    requested = windows(start, end)
    rows, products = {}, {}
    for pid in [pid for pair in PAIRS.values() for pid in pair]:
        rows[pid] = []
        names = [(f"{pid}-product.json", None)] + [(f"{pid}-{a}-{b}.json", (a, b)) for a, b in requested]
        for name, window in names:
            source = manifest["sources"].get(name)
            if source is None:
                raise ValueError(f"missing required raw source {name}")
            expected_path = f"products/{pid}"
            if window:
                a, b = window
                expected_path += "/candles?" + urllib.parse.urlencode({"start": a, "end": b - 1,
                                                                       "granularity": "ONE_HOUR", "limit": LIMIT})
            if source["url"] != API + expected_path:
                raise ValueError("raw source URL does not match exact requested product/window")
            raw = (snapshot / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != source["sha256"]:
                raise ValueError(f"raw checksum mismatch: {name}")
            payload = json.loads(raw)
            if window:
                rows[pid].extend(normalize_candles(payload, *window))
            else:
                details = payload.get("future_product_details") or {}
                expected_root = next(root for root, pair in PAIRS.items() if pid in pair)
                if (payload.get("product_id") != pid or payload.get("product_venue") != "FCM"
                        or payload.get("product_type") != "FUTURE" or details.get("contract_root_unit") != expected_root):
                    raise ValueError("exact U.S. futures product identity mismatch")
                products[pid] = payload
    return manifest, rows, products


def analyze(snapshot: Path) -> dict:
    manifest, candles, products = load_snapshot(snapshot)
    start, end = manifest["start"], manifest["end_exclusive"]
    expected = set(range(start, end, HOUR))
    summary = {}
    for pid, rows in candles.items():
        times = {row["start"] for row in rows}
        summary[pid] = {"bars": len(rows), "zero_reported_volume_bars": sum(row["volume"] == 0 for row in rows),
                        "calendar_coverage": len(rows) / len(expected),
                        "first_bucket_start": iso(rows[0]["start"]) if rows else None,
                        "last_bucket_start": iso(rows[-1]["start"]) if rows else None,
                        "missing_ranges": missing_ranges(expected, times),
                        "current_metadata_settlement_price": products[pid]["future_product_details"].get("settlement_price"),
                        "settlement_price_is_historical_event_series": False}
    return {"schema": SCHEMA, "status": "DESCRIPTIVE_CANDLES_ONLY_NO_BACKTEST",
            "start": iso(start), "end_exclusive": iso(end), "expected_calendar_hours": len(expected),
            "manifest_sha256": hashlib.sha256((snapshot / "manifest.json").read_bytes()).hexdigest(),
            "analysis_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "products": summary,
            "pairs": {root: describe_pair(candles[a], candles[b], start, end) for root, (a, b) in PAIRS.items()},
            "limitations": ["Hourly closes are not synchronized executions, bids/asks, or event-time funding marks.",
                            "Missing hours remain missing; calendar gaps can include closures or untraded periods, not necessarily ingestion faults.",
                            "Reported positive volume only establishes some activity within the hour, not liquid paired fills.",
                            "No funding cash flow, commission, margin, tax, profitability, or fitted strategy calculation.",
                            "Contract metadata is current at collection, not historical tradability or margin evidence."]}


def write_new(path: Path, value: dict) -> None:
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def collect(start: int, end: int, base: Path) -> Path:
    spans = windows(start, end)
    if end > int(datetime.now(timezone.utc).timestamp()) // HOUR * HOUR:
        raise ValueError("end would include an incomplete or future hourly bucket")
    snapshot = base / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": SCHEMA, "started_at": utcnow(), "start": start, "end_exclusive": end,
                "granularity": "ONE_HOUR", "documented_max_buckets_per_request": LIMIT,
                "request_window_hours": PAGE_HOURS,
                "pairs": PAIRS, "reference": REFERENCE, "sources": {},
                "collector_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        for pid in [pid for pair in PAIRS.values() for pid in pair]:
            requests = [(f"{pid}-product.json", f"products/{pid}")]
            for a, b in spans:
                query = urllib.parse.urlencode({"start": a, "end": b - 1, "granularity": "ONE_HOUR", "limit": LIMIT})
                requests.append((f"{pid}-{a}-{b}.json", f"products/{pid}/candles?{query}"))
            for name, path in requests:
                raw, source = fetch(path)
                with (snapshot / name).open("xb") as handle:
                    handle.write(raw)
                manifest["sources"][name] = source
            print(f"Archived {pid}: {len(spans)} hourly pages", flush=True)
        manifest["completed_at"] = utcnow()
        write_new(snapshot / "manifest.json", manifest)
        write_new(snapshot / "report.json", analyze(snapshot))
    except Exception as exc:
        write_new(snapshot / "failure.json", {"error": str(exc), "partial_manifest": manifest})
        raise
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="reproduce saved history offline")
    parser.add_argument("--start", default="2026-06-12T00:00:00Z")
    parser.add_argument("--end", default="2026-09-10T00:00:00Z", help="exclusive end, complete hours only")
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/us_crypto/futures-history")
    args = parser.parse_args()
    try:
        snapshot = args.snapshot or collect(parse_time(args.start), parse_time(args.end), args.output_root)
        print(f"Snapshot: {snapshot}")
        print(json.dumps(analyze(snapshot), indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"HISTORY DATA ERROR: {exc}; no performance result issued", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
