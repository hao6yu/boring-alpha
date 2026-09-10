#!/usr/bin/env python3
"""Fixed-sample BA-009B timing audit: minute closes are not paired executions."""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
# fetch uses the verified OS CA context from fetch_market_data; no credentials.
import us_futures_history as hourly  # noqa: E402

SCHEMA = "us-futures-minute-timing-audit-v1"
MINUTE, HOUR, PAGE_MINUTES = 60, 3600, 300
PAIRS = hourly.PAIRS
START = hourly.parse_time("2026-09-08T00:00:00Z")
END = hourly.parse_time("2026-09-10T00:00:00Z")
HOURLY_ARCHIVE = ROOT / "data/us_crypto/futures-history/20260910T000515491884Z"
MAX_REQUESTS = 44


def windows(start: int, end: int) -> list[tuple[int, int]]:
    if start % MINUTE or end % MINUTE or not 0 < end - start <= 48 * HOUR:
        raise ValueError("require minute boundaries and a maximum 48-hour sample")
    return [(a, min(a + PAGE_MINUTES * MINUTE, end))
            for a in range(start, end, PAGE_MINUTES * MINUTE)]


def minute_path(pid: str, a: int, b: int) -> str:
    query = urllib.parse.urlencode({"start": a, "end": b - 1, "granularity": "ONE_MINUTE", "limit": PAGE_MINUTES})
    return f"products/{pid}/candles?{query}"


def normalize_minutes(payload: dict, start: int, end: int) -> list[dict]:
    if not isinstance(payload.get("candles"), list) or len(payload["candles"]) > PAGE_MINUTES:
        raise ValueError("missing minute candles or oversized page")
    seen, out = set(), []
    for item in payload["candles"]:
        try:
            stamp = int(item["start"])
            if str(stamp) != str(item["start"]) or stamp % MINUTE or not start <= stamp < end:
                raise ValueError("minute candle outside request or off boundary")
            if stamp in seen:
                raise ValueError("duplicate minute candle")
            row = {"start": stamp, **{k: float(item[k]) for k in ("open", "high", "low", "close", "volume")}}
            if not all(math.isfinite(row[k]) and row[k] > 0 for k in ("open", "high", "low", "close")):
                raise ValueError("nonfinite or nonpositive minute price")
            if not math.isfinite(row["volume"]) or row["volume"] < 0:
                raise ValueError("invalid minute volume")
            if not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
                raise ValueError("inconsistent minute OHLC")
        except (KeyError, TypeError, OverflowError) as exc:
            raise ValueError("malformed minute candle") from exc
        seen.add(stamp)
        out.append(row)
    return sorted(out, key=lambda row: row["start"])


def stats(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"count": len(values), "min": min(values), "median": statistics.median(values),
            "mean": statistics.fmean(values), "max": max(values)}


def audit_pair(perp_minutes: list[dict], dated_minutes: list[dict],
               perp_hourly: list[dict], dated_hourly: list[dict], start: int, end: int) -> dict:
    """No carrying prices forward: match only reported positive-volume minutes."""
    minutes = [{r["start"]: r for r in series if r["volume"] > 0}
               for series in (perp_minutes, dated_minutes)]
    hours = [{r["start"]: r for r in series} for series in (perp_hourly, dated_hourly)]
    rows = []
    for stamp in range(start, end, HOUR):
        row = {"hour_start": hourly.iso(stamp), "hour_start_unix": stamp,
               "both_hourly_closes": stamp in hours[0] and stamp in hours[1]}
        for i, label in enumerate(("perp", "dated")):
            active = [t for t in range(stamp, stamp + HOUR, MINUTE) if t in minutes[i]]
            last = max(active) if active else None
            row[f"{label}_active_minutes"] = len(active)
            row[f"{label}_last_trade_minute"] = hourly.iso(last) if last is not None else None
            # 0 means a trade in xx:59, 59 means the latest trade was in xx:00.
            row[f"{label}_last_trade_minute_lag_from_hour_end"] = (stamp + HOUR - MINUTE - last) // MINUTE if last is not None else None
            row[f"{label}_last_minute_close"] = minutes[i][last]["close"] if last is not None else None
            row[f"{label}_hourly_close"] = hours[i][stamp]["close"] if stamp in hours[i] else None
            row[f"{label}_hourly_matches_last_minute"] = (
                math.isclose(hours[i][stamp]["close"], minutes[i][last]["close"], rel_tol=0, abs_tol=1e-8)
                if stamp in hours[i] and last is not None else None)
        common = sorted(t for t in range(stamp, stamp + HOUR, MINUTE) if t in minutes[0] and t in minutes[1])
        latest = common[-1] if common else None
        row["common_active_minutes"] = len(common)
        row["last_common_trade_minute"] = hourly.iso(latest) if latest is not None else None
        row["last_common_minute_lag_from_hour_end"] = (stamp + HOUR - MINUTE - latest) // MINUTE if latest is not None else None
        lags = [row[f"{label}_last_trade_minute_lag_from_hour_end"] for label in ("perp", "dated")]
        row["last_trade_minute_separation"] = abs(lags[0] - lags[1]) if all(x is not None for x in lags) else None
        row["hourly_gap_usd_per_underlying"] = hours[1][stamp]["close"] - hours[0][stamp]["close"] if row["both_hourly_closes"] else None
        row["last_common_minute_gap_usd_per_underlying"] = minutes[1][latest]["close"] - minutes[0][latest]["close"] if latest is not None else None
        row["hourly_closes_reconcile_to_minutes"] = all(row[f"{label}_hourly_matches_last_minute"] is True for label in ("perp", "dated"))
        row["timing_comparison_valid"] = row["hourly_closes_reconcile_to_minutes"] and latest is not None
        comparable = row["both_hourly_closes"] and latest is not None
        hgap, mgap = row["hourly_gap_usd_per_underlying"], row["last_common_minute_gap_usd_per_underlying"]
        row["hourly_gap_minus_common_minute_gap_usd"] = hgap - mgap if comparable else None
        row["absolute_gap_reduction_at_common_minute_usd"] = abs(hgap) - abs(mgap) if comparable else None
        row["gap_sign_changed"] = hgap * mgap < 0 if comparable else None
        rows.append(row)
    valid = [r for r in rows if r["timing_comparison_valid"]]
    hrows = [r for r in rows if r["both_hourly_closes"]]
    return {"sample_hours": len(rows), "hours_with_both_hourly_closes": len(hrows),
            "hours_with_common_active_minute": sum(r["common_active_minutes"] > 0 for r in rows),
            "hours_with_reconciled_closes_and_common_minute": len(valid),
            "perp_hourly_close_mismatches": sum(r["perp_hourly_matches_last_minute"] is False for r in rows),
            "dated_hourly_close_mismatches": sum(r["dated_hourly_matches_last_minute"] is False for r in rows),
            "perp_last_trade_minute_lag": stats([r["perp_last_trade_minute_lag_from_hour_end"] for r in rows if r["perp_last_trade_minute_lag_from_hour_end"] is not None]),
            "dated_last_trade_minute_lag": stats([r["dated_last_trade_minute_lag_from_hour_end"] for r in rows if r["dated_last_trade_minute_lag_from_hour_end"] is not None]),
            "last_trade_minute_separation": stats([r["last_trade_minute_separation"] for r in rows if r["last_trade_minute_separation"] is not None]),
            "common_minute_lag": stats([r["last_common_minute_lag_from_hour_end"] for r in rows if r["last_common_minute_lag_from_hour_end"] is not None]),
            "matched_hours_hourly_gap_usd": stats([r["hourly_gap_usd_per_underlying"] for r in valid]),
            "matched_hours_common_minute_gap_usd": stats([r["last_common_minute_gap_usd_per_underlying"] for r in valid]),
            "matched_hours_absolute_gap_difference_usd": stats([abs(r["hourly_gap_minus_common_minute_gap_usd"]) for r in valid]),
            "matched_hours_sign_changes": sum(r["gap_sign_changed"] for r in valid),
            "five_largest_absolute_hourly_gaps": sorted(hrows, key=lambda r: (-abs(r["hourly_gap_usd_per_underlying"]), r["hour_start_unix"]))[:5],
            "hours": rows}


def checked_bytes(folder: Path, name: str, source: dict) -> bytes:
    if Path(name).name != name:
        raise ValueError("unsafe archive filename")
    raw = (folder / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError(f"archive checksum mismatch: {name}")
    return raw


def reference_sources(manifest: dict, start: int, end: int) -> dict[str, list[tuple[str, int, int]]]:
    if manifest.get("schema") != hourly.SCHEMA or manifest.get("pairs") != {k: list(v) for k, v in PAIRS.items()}:
        raise ValueError("wrong hourly reference schema or exact products")
    if not manifest["start"] <= start < end <= manifest["end_exclusive"]:
        raise ValueError("hourly archive does not cover audit sample")
    return {pid: [(f"{pid}-{a}-{b}.json", a, b) for a, b in hourly.windows(manifest["start"], manifest["end_exclusive"])
                  if a < end and b > start]
            for pair in PAIRS.values() for pid in pair}


def load_snapshot(folder: Path) -> tuple[dict, dict, dict, dict]:
    """Return manifest, minute candles by ID, hourly candles by ID, current metadata."""
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or (manifest.get("start"), manifest.get("end_exclusive")) != (START, END):
        raise ValueError("wrong audit schema or fixed sample")
    if manifest.get("pairs") != {k: list(v) for k, v in PAIRS.items()}:
        raise ValueError("wrong exact audit products")
    ref_name = "hourly-reference-manifest.json"
    reference = json.loads(checked_bytes(folder, ref_name, manifest["local_references"][ref_name]))
    copies = reference_sources(reference, START, END)
    minutes, hours, products = {}, {}, {}
    for root, pair in PAIRS.items():
        for pid in pair:
            minutes[pid], hours[pid] = [], []
            for name, a, b in copies[pid]:
                source = manifest["local_references"]["hourly-" + name]
                if source != reference["sources"][name]:
                    raise ValueError("copied hourly provenance mismatch")
                raw = checked_bytes(folder, "hourly-" + name, source)
                rows = hourly.normalize_candles(json.loads(raw), a, b)
                hours[pid].extend(row for row in rows if START <= row["start"] < END)
            name = f"{pid}-product.json"
            source = manifest["sources"][name]
            if source["url"] != hourly.API + f"products/{pid}":
                raise ValueError("product source URL mismatch")
            product = json.loads(checked_bytes(folder, name, source))
            if (product.get("product_id") != pid or product.get("product_venue") != "FCM"
                    or product.get("product_type") != "FUTURE"
                    or product.get("future_product_details", {}).get("contract_root_unit") != root):
                raise ValueError("U.S. product identity mismatch")
            products[pid] = product
            for a, b in windows(START, END):
                name = f"{pid}-{a}-{b}.json"
                source = manifest["sources"][name]
                if source["url"] != hourly.API + minute_path(pid, a, b):
                    raise ValueError("minute source URL mismatch")
                minutes[pid].extend(normalize_minutes(json.loads(checked_bytes(folder, name, source)), a, b))
    return manifest, minutes, hours, products


def analyze(folder: Path) -> dict:
    manifest, minutes, hours, _ = load_snapshot(folder)
    total_minutes = (END - START) // MINUTE
    return {"schema": SCHEMA, "status": "FIXED_SAMPLE_TIMING_DIAGNOSTIC_NO_STRATEGY",
            "start": hourly.iso(START), "end_exclusive": hourly.iso(END),
            "network_requests": manifest["network_requests"],
            "manifest_sha256": hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest(),
            "analysis_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "helper_code_sha256": hashlib.sha256(Path(hourly.__file__).read_bytes()).hexdigest(),
            "products": {pid: {"minute_bars": len(rows), "positive_volume_minutes": sum(r["volume"] > 0 for r in rows),
                               "missing_calendar_minutes": total_minutes - len(rows),
                               "minute_calendar_coverage": len(rows) / total_minutes,
                               "hourly_reference_bars": len(hours[pid])} for pid, rows in minutes.items()},
            "pairs": {root: audit_pair(minutes[p], minutes[d], hours[p], hours[d], START, END) for root, (p, d) in PAIRS.items()},
            "limitations": ["Fixed 48-hour sample selected before collection; it cannot resolve older 90-day extrema or establish a persistent edge.",
                            "Same-minute trades may occur at different seconds; closes are not executable bid/ask fills or funding marks.",
                            "Last reported trade minute lags are bucket bounds, not exact last-trade timestamps.",
                            "A common minute may be earlier than each leg's final trade minute; gap differences mix timing and genuine spread movement.",
                            "No missing minute is filled; zero-volume minutes are excluded from trade alignment.",
                            "Only hours whose prior hourly closes reconcile to minute closes enter timing-only aggregate comparisons.",
                            "No model fitting, forecast, trading rule, fees, funding cash flows, or P&L is calculated."]}


def collect(base: Path, reference_folder: Path = HOURLY_ARCHIVE) -> Path:
    if END > int(datetime.now(timezone.utc).timestamp()) // HOUR * HOUR:
        raise ValueError("fixed sample includes an unfinished hourly bucket")
    reference, _, _ = hourly.load_snapshot(reference_folder)
    expected_requests = 4 * (1 + len(windows(START, END)))
    if expected_requests > MAX_REQUESTS:
        raise ValueError("network budget exceeded before collection")
    folder = base / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": SCHEMA, "start": START, "end_exclusive": END, "pairs": PAIRS,
                "started_at": hourly.utcnow(), "granularity": "ONE_MINUTE", "request_window_minutes": PAGE_MINUTES,
                "fixed_sample_declared_before_collection": True, "network_request_budget": MAX_REQUESTS,
                "network_requests": 0, "sources": {}, "local_references": {},
                "hourly_reference_original_path": str(reference_folder.resolve()),
                "collector_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        ref_raw = (reference_folder / "manifest.json").read_bytes()
        with (folder / "hourly-reference-manifest.json").open("xb") as handle:
            handle.write(ref_raw)
        manifest["local_references"]["hourly-reference-manifest.json"] = {"sha256": hashlib.sha256(ref_raw).hexdigest()}
        for names in reference_sources(reference, START, END).values():
            for name, _, _ in names:
                raw = checked_bytes(reference_folder, name, reference["sources"][name])
                with (folder / ("hourly-" + name)).open("xb") as handle:
                    handle.write(raw)
                manifest["local_references"]["hourly-" + name] = reference["sources"][name]
        for pair in PAIRS.values():
            for pid in pair:
                requests = [(f"{pid}-product.json", f"products/{pid}")]
                requests += [(f"{pid}-{a}-{b}.json", minute_path(pid, a, b)) for a, b in windows(START, END)]
                for name, path in requests:
                    if manifest["network_requests"] >= MAX_REQUESTS:
                        raise ValueError("network request budget exhausted")
                    manifest["network_requests"] += 1
                    raw, source = hourly.fetch(path)
                    with (folder / name).open("xb") as handle:
                        handle.write(raw)
                    manifest["sources"][name] = source
                print(f"Archived {pid}: 10 minute pages and product metadata", flush=True)
        manifest["completed_at"] = hourly.utcnow()
        hourly.write_new(folder / "manifest.json", manifest)
        hourly.write_new(folder / "report.json", analyze(folder))
    except Exception as exc:
        hourly.write_new(folder / "failure.json", {"error": str(exc), "partial_manifest": manifest})
        raise
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="offline analysis of archived inputs")
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/us_crypto/minute-audits")
    args = parser.parse_args()
    try:
        folder = args.snapshot or collect(args.output_root)
        print(f"Snapshot: {folder}")
        print(json.dumps(analyze(folder), indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"MINUTE AUDIT ERROR: {exc}; no performance result issued", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
