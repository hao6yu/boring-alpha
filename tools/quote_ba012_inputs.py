#!/usr/bin/env python3
"""Quote BA-012 parent inputs. Metadata only: no data downloads or purchases.

Credentials enter through a hidden terminal prompt and are not saved.
The only endpoints are metadata.get_cost and metadata.get_record_count.
"""
from __future__ import annotations

import base64
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import getpass
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from fetch_market_data import _CONTEXT
from databento_history_probe import NoRedirect

ROOT = Path(__file__).resolve().parents[1]
BASE = {"dataset": "GLBX.MDP3", "stype_in": "parent",
        "start": "2016-01-11", "end": "2024-01-01"}
QUERIES = tuple(BASE | {"symbols": root + ".FUT", "schema": "ohlcv-1m"}
                for root in ("ES", "TN", "6E", "GC", "ZC"))
DEFINITIONS = BASE | {"symbols": "ES.FUT,TN.FUT,6E.FUT,GC.FUT,ZC.FUT", "schema": "definition"}


def reference_queries():
    """Calendar-neutral acquisition superset; not the strategy's joint calendar."""
    day, end = date(2016, 1, 11), date(2024, 1, 1)
    queries = []
    while day < end:
        if day.weekday() < 5:
            start = datetime.combine(day, time(9, 59), ZoneInfo("America/Chicago")).astimezone(timezone.utc)
            queries.append(BASE | {"symbols": DEFINITIONS["symbols"], "schema": "ohlcv-1m",
                                  "start": start.isoformat(), "end": (start + timedelta(minutes=1)).isoformat()})
        day += timedelta(days=1)
    return tuple(queries)


REFERENCES = reference_queries()


def now():
    return datetime.now(timezone.utc).isoformat()


def request(key, method, query):
    if method not in ("metadata.get_cost", "metadata.get_record_count") or query not in (*QUERIES, DEFINITIONS, *REFERENCES):
        raise ValueError("Outside fixed metadata allowlist")
    url = "https://hist.databento.com/v0/" + method + "?" + urllib.parse.urlencode(query)
    auth = "Basic " + base64.b64encode((key + ":").encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": auth, "Accept": "application/json"})
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=_CONTEXT))
    record = {"method": method, "query": query, "requested_at": now()}
    try:
        try:
            response = opener.open(req, timeout=40)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(4097)
            record["http_status"] = response.code
        if response.code != 200:
            return record | {"status": "http_error"}
        if len(raw) > 4096 or key.encode() in raw or auth.encode() in raw:
            return record | {"status": "unsafe_response"}
        value = json.loads(raw, parse_int=Decimal, parse_float=Decimal)
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            return record | {"status": "invalid_value"}
        if method.endswith("get_record_count") and value != value.to_integral_value():
            return record | {"status": "invalid_count"}
        return record | {"status": "ok", "value": str(value), "response_sha256": hashlib.sha256(raw).hexdigest()}
    except Exception as exc:
        return record | {"status": "transport_or_parse_error", "error_type": type(exc).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-reference-quotes", action="store_true")
    parser.add_argument("--retry-failures-of", type=Path, help="Retry only failed metadata in an exact daily quote")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        raise SystemExit("Interactive terminal required for hidden credential input")
    freeze = json.loads((ROOT / "research/ba012-protocol-v1-freeze.json").read_text())
    protocol = freeze["canonical_protocol"]
    if hashlib.sha256((ROOT / protocol["path"]).read_bytes()).hexdigest() != protocol["sha256"]:
        raise SystemExit("Frozen protocol checksum mismatch")
    key = getpass.getpass("Databento API key (hidden): ").strip()
    if not re.fullmatch(r"db-[A-Za-z0-9_-]{20,80}", key):
        raise SystemExit("Invalid credential format; contents omitted")
    folder = ROOT / "research/ba012-stage-a" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True, exist_ok=False)
    report = {"schema": "ba012-input-metadata-quote-v1", "started_at": now(),
              "protocol_sha256": protocol["sha256"], "data_downloads": 0,
              "strategy_returns_calculated": False, "requests": [],
              "limitations": ["Broad all-maturity quotes, not a selected contract/time acquisition plan.",
                              "Positive record counts do not establish required minute coverage.",
                              "Quotes do not verify account credit balance or billing."]}
    if args.daily_reference_quotes or args.retry_failures_of:
        report["limitations"] = [
            "All weekdays and all parent maturities are an acquisition superset, not the strategy calendar.",
            "Databento warns sub-10-minute cost estimates may overestimate actual usage.",
            "No data download; no prices, sizing or strategy returns measured.",
            "Quote does not verify remaining credits or billing; not a hard provider spending cap."]
        pending = REFERENCES
        if args.retry_failures_of:
            prior_raw = args.retry_failures_of.read_bytes()
            previous = json.loads(prior_raw)
            ordered = previous["requests"]
            if ([row["query"] for row in ordered] != list(REFERENCES)
                    or any(row["method"] != "metadata.get_cost" for row in ordered)
                    or previous["protocol_sha256"] != protocol["sha256"]):
                raise SystemExit("Previous quote does not match fixed daily requests")
            report["previous_quote"] = {"path": str(args.retry_failures_of),
                                         "sha256": hashlib.sha256(prior_raw).hexdigest()}
            report["requests"] = [row for row in ordered if row["status"] == "ok"]
            pending = tuple(row["query"] for row in ordered if row["status"] != "ok")
            print(json.dumps({"retrying_metadata_queries": len(pending)}), flush=True)
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = [pool.submit(request, key, "metadata.get_cost", query) for query in pending]
            for job in as_completed(jobs):
                report["requests"].append(job.result())
                if len(report["requests"]) % 200 == 0:
                    print(json.dumps({"quoted": len(report["requests"]), "total": len(REFERENCES)}), flush=True)
        report["requests"].sort(key=lambda row: row["query"]["start"])
        report["expected_requests"] = len(REFERENCES)
        report["successful_quotes"] = sum(row["status"] == "ok" for row in report["requests"])
        report["successful_quote_sum_usd"] = str(sum(
            (Decimal(row["value"]) for row in report["requests"] if row["status"] == "ok"), Decimal(0)))
        report["complete_quote"] = report["successful_quotes"] == len(REFERENCES)
        report["completed_at"] = now()
        key = ""
        (folder / "quote.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k != "requests"}), flush=True)
        print(str(folder / "quote.json"), flush=True)
        return
    for query in (*QUERIES, DEFINITIONS):
        for method in ("metadata.get_cost", "metadata.get_record_count"):
            result = request(key, method, query)
            report["requests"].append(result)
            (folder / "quote.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(result), flush=True)
            if result.get("http_status") in (401, 403):
                key = ""
                print("Authentication/access stopped further requests.", flush=True)
                return
    key = ""
    report["completed_at"] = now()
    (folder / "quote.json").write_text(json.dumps(report, indent=2) + "\n")
    print(str(folder / "quote.json"), flush=True)


if __name__ == "__main__":
    main()
