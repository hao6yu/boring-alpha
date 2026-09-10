#!/usr/bin/env python3
"""Verify Databento metadata and optionally fetch one small expired MES sample.

Credentials enter through a hidden terminal prompt and are never persisted.
Only fixed historical requests are supported. A fresh finite quote <= $1 is
required for the optional 390-minute sample; larger research ranges are quoted
only. A quote is an estimate, not a provider-enforced spending limit.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
import getpass
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_market_data import _CONTEXT

ROOT = Path(__file__).resolve().parents[1]
HOST = "https://hist.databento.com/v0/"
DATASET = "GLBX.MDP3"
SAMPLE = dict(dataset=DATASET, symbols="MESZ5", stype_in="raw_symbol",
              schema="ohlcv-1m", start="2025-11-03T14:30:00Z",
              end="2025-11-03T21:00:00Z", limit=390)
QUOTES = {
    "expired_mes_sample": SAMPLE,
    "mes_2025_minutes": dict(dataset=DATASET, symbols="MES.v.0", stype_in="continuous",
                             schema="ohlcv-1m", start="2025-01-01", end="2026-01-01"),
    "mes_2021_2025_minutes": dict(dataset=DATASET, symbols="MES.v.0", stype_in="continuous",
                                  schema="ohlcv-1m", start="2021-01-01", end="2026-01-01"),
}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def allowed_request(method, params):
    return (
        method == "metadata.get_dataset_range" and params == {"dataset": DATASET}
        or method == "metadata.get_cost" and params in QUOTES.values()
        or method == "timeseries.get_range" and params == SAMPLE | {"encoding": "json", "compression": "none"}
    )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(key, method, params):
    if not allowed_request(method, params):
        raise ValueError("Request outside fixed historical probe")
    url = HOST + method + "?" + urllib.parse.urlencode(params)
    auth = "Basic " + base64.b64encode((key + ":").encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": auth,
        "Accept": "application/json", "User-Agent": "BoringAlpha-HistoricalProbe/0.1"})
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=_CONTEXT))
    meta = {"url": url, "requested_at": utcnow()}
    try:
        try:
            response = opener.open(request, timeout=40)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(2_000_001)
            meta.update(http_status=response.code, received_at=utcnow())
        meta.update(response_bytes=len(raw), response_sha256=hashlib.sha256(raw).hexdigest())
        if len(raw) > 2_000_000 or key.encode() in raw or auth.encode() in raw:
            return meta | {"result": "unsafe_or_oversized_response"}, None
        if meta["http_status"] != 200:
            # Do not persist arbitrary provider errors or account information.
            lower = raw.lower()
            meta["mentions_license"] = b"licens" in lower or b"agreement" in lower
            meta["mentions_auth"] = b"auth" in lower or b"api key" in lower
            meta["mentions_credits"] = b"credit" in lower or b"balance" in lower
            return meta | {"result": "http_error"}, None
        return meta | {"result": "ok"}, raw
    except Exception:
        return meta | {"result": "transport_error", "received_at": utcnow()}, None


def quote_value(raw):
    if raw is None:
        return None
    try:
        value = json.loads(raw, parse_int=Decimal, parse_float=Decimal)
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError, OverflowError, DecimalException):
        return None


def sample_quote_allowed(raw):
    if quote_value(raw) is None:
        return False
    # Compare the original decimal quote, before float rounding for reporting.
    return json.loads(raw, parse_int=Decimal, parse_float=Decimal) <= Decimal("1")


def strict_integer(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    raise ValueError("Expected an integer without truncation")


def normalize_sample(raw):
    """JSON uses fixed-point prices (1e-9) and nanosecond timestamps by default."""
    rows = []
    start = int(datetime.fromisoformat(SAMPLE["start"]).timestamp()) * 10**9
    end = int(datetime.fromisoformat(SAMPLE["end"]).timestamp()) * 10**9
    for line in raw.splitlines():
        item = json.loads(line)
        hd = item["hd"]
        stamp = strict_integer(hd["ts_event"])
        prices = {name: Decimal(str(item[name])) / 10**9 for name in ("open", "high", "low", "close")}
        volume = strict_integer(item["volume"])
        instrument_id = strict_integer(hd["instrument_id"])
        if instrument_id <= 0:
            raise ValueError("Invalid instrument identifier")
        if not start <= stamp < end or stamp % (60 * 10**9) or volume <= 0:
            raise ValueError("Invalid sample timestamp or volume")
        if any(not v.is_finite() or v <= 0 or v % Decimal("0.25") for v in prices.values()):
            raise ValueError("Invalid MES sample price or tick")
        if not prices["low"] <= min(prices["open"], prices["close"]) <= max(prices["open"], prices["close"]) <= prices["high"]:
            raise ValueError("Impossible OHLC")
        rows.append({"ts_event_ns": stamp, "instrument_id": instrument_id,
                     **{k: str(v) for k, v in prices.items()}, "volume": volume})
    if not rows or len(rows) > SAMPLE["limit"] or len({r["instrument_id"] for r in rows}) != 1:
        raise ValueError("Unexpected sample size or instrument count")
    if any(a["ts_event_ns"] >= b["ts_event_ns"] for a, b in zip(rows, rows[1:])):
        raise ValueError("Duplicate or unsorted sample bars")
    return rows


def run_probe(key, download_sample=False, fetcher=fetch):
    report = {"schema": "databento-mes-history-probe-v1", "started_at": utcnow(),
              "requests": [], "quotes_usd": {}, "sample": {"status": "not_requested"}}
    meta, raw = fetcher(key, "metadata.get_dataset_range", {"dataset": DATASET})
    report["requests"].append(meta)
    report["metadata_request_succeeded"] = raw is not None
    if raw is None:
        return report, None
    try:
        payload = json.loads(raw)
        values = {k: payload[k] for k in ("start", "end")}
        dates = [datetime.fromisoformat(values[k]) for k in ("start", "end")]
        if any(d.tzinfo is None for d in dates) or dates[0] >= dates[1]:
            raise ValueError("Invalid dataset range")
        report["dataset_range"] = values
    except (ValueError, TypeError, KeyError, OverflowError):
        report.update(metadata_request_succeeded=False, metadata_validation_failed=True, completed_at=utcnow())
        return report, None
    for label, query in QUOTES.items():
        meta, raw = fetcher(key, "metadata.get_cost", query)
        report["requests"].append(meta)
        report["quotes_usd"][label] = quote_value(raw)
        print(json.dumps({"query": label, "quote_usd": report["quotes_usd"][label],
                          "http_status": meta.get("http_status")}), flush=True)
    sample_raw = None
    if download_sample:
        # Requote immediately before the only data download.
        meta, raw = fetcher(key, "metadata.get_cost", SAMPLE)
        report["requests"].append(meta)
        cost = quote_value(raw)
        report["sample"] = {"quote_usd": cost, "estimate_ceiling_usd": 1.0,
                             "status": "quote_refused"}
        if sample_quote_allowed(raw):
            meta, raw = fetcher(key, "timeseries.get_range", SAMPLE | {"encoding": "json", "compression": "none"})
            report["requests"].append(meta)
            report["sample"]["status"] = meta["result"]
            if raw is not None:
                try:
                    rows = normalize_sample(raw)
                    sample_raw = raw
                    report["sample"].update(status="valid_bars", bars=len(rows),
                        missing_minutes=390-len(rows), normalized_bars=rows)
                except Exception:
                    report["sample"]["status"] = "invalid_bar_response"
    report["completed_at"] = utcnow()
    report["limitations"] = ["Availability and cost check only; no strategy returns.",
        "Continuous-series quotes are not evidence of safe roll accounting.",
        "A 390-minute sample does not establish complete multi-year coverage.",
        "Quotes exclude verification of actual account billing and credit application."]
    return report, sample_raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-sample", action="store_true")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Use an interactive terminal for hidden credential entry")
    key = getpass.getpass("Databento API key (hidden): ").strip()
    if not re.fullmatch(r"db-[A-Za-z0-9_-]{20,80}", key):
        parser.error("Unexpected key format; contents omitted")
    report, raw = run_probe(key, args.download_sample)
    key = ""
    folder = ROOT / "data/futures/databento-probes" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if raw is not None:
        (folder / "mesz5-20251103-ohlcv-1m.jsonl").write_bytes(raw)
    summary = report | {"sample": {k:v for k,v in report["sample"].items() if k != "normalized_bars"},
                        "report_path": str(folder / "report.json")}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
