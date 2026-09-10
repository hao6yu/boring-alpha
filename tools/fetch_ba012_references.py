#!/usr/bin/env python3
"""Preflight or archive the frozen BA-012 parent reference minutes only.

Default operation is offline. --acquire additionally requires a complete saved
quote, an explicit aggregate estimate ceiling, and hidden terminal key entry.
Data gets one attempt per run. Explicit --resume-attempts enables bounded new
runs after reconciled transient failures; all prior reservations stay charged.
Free metadata may retry transient failures up to three attempts. Estimates include prior failed/uncertain data attempts;
they are not a provider-enforced billing cap. No account or live APIs are used.
Raw instrument IDs do not establish contract mapping or five-market coverage.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
import getpass
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_mes_history import (ArchiveError, Client as HistoricalClient, ENCODING, HOST, NoRedirect,
                               add_cost, decimal_cost, strict_integer, utcnow)
from fetch_market_data import _CONTEXT
from quote_ba012_inputs import REFERENCES

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "data/futures/ba012-reference-history"
PROTOCOL_SHA256 = "095fa832c82645a6f570668813b59b08afa4a21c93466980703ff78c46eec67f"
SCHEMA = "ba012-reference-archive-v1"
MAX_QUOTE_BYTES = 8_000_000
MAX_RECORDS = 10_000  # Fail closed on an unexpectedly large one-minute response.
MAX_LINE_BYTES = 2048
METADATA_TIMEOUT_SECONDS = 20
METADATA_ATTEMPTS = 3
MAX_WORKERS = 16
MAX_RESUME_ATTEMPTS = 20
MAX_RETRY_WAIT_SECONDS = 60
TRANSIENT_HTTP = (429, 500, 502, 503, 504)


class RequestStartLimiter:
    """One process-wide, non-bursting limit shared by every metadata client."""

    def __init__(self, clock=None, sleep=None):
        self.clock, self.sleep = clock or time.monotonic, sleep or time.sleep
        self.lock, self.next_start = threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            delay = max(0.0, self.next_start - self.clock())
            if delay:
                self.sleep(delay)
            started = self.clock()
            self.next_start = max(started, self.next_start) + 0.1
            return started

    def defer(self, seconds):
        with self.lock:
            self.next_start = max(self.next_start, self.clock() + seconds)


METADATA_LIMITER = RequestStartLimiter()


def retry_after_seconds(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError
    if re.fullmatch(r"[0-9]{1,9}", value.strip()):
        return int(value.strip())
    stamp = parsedate_to_datetime(value)
    if stamp.tzinfo is None:
        raise ValueError
    return max(0, math.ceil((stamp.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()))


def query_key(query):
    return json.dumps(query, sort_keys=True, separators=(",", ":"))


def plan_sha256():
    return hashlib.sha256("\n".join(map(query_key, REFERENCES)).encode()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def load_json(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def checked_protocol():
    try:
        freeze = load_json((ROOT / "research/ba012-protocol-v1-freeze.json").read_bytes())
        canonical = freeze["canonical_protocol"]
        if canonical["path"] != "docs/strategies/BA-012.md" or canonical["sha256"] != PROTOCOL_SHA256:
            raise ValueError
        if hashlib.sha256((ROOT / canonical["path"]).read_bytes()).hexdigest() != PROTOCOL_SHA256:
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        raise ArchiveError("frozen_protocol_mismatch") from None


def cost_string(value):
    if not isinstance(value, str):
        raise ArchiveError("invalid_quote")
    return decimal_cost(value.encode())


def load_quote(path):
    """Accept exactly one successful cost quote per frozen query, with no extras."""
    checked_protocol()
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_QUOTE_BYTES + 1)
        if len(raw) > MAX_QUOTE_BYTES:
            raise ValueError
        report = load_json(raw)
        if (report["schema"] != "ba012-input-metadata-quote-v1"
                or report["protocol_sha256"] != PROTOCOL_SHA256
                or report["complete_quote"] is not True
                or report["data_downloads"] != 0
                or report["strategy_returns_calculated"] is not False
                or report["expected_requests"] != len(REFERENCES)
                or report["successful_quotes"] != len(REFERENCES)
                or len(report["requests"]) != len(REFERENCES)):
            raise ValueError
        expected = {query_key(query) for query in REFERENCES}
        costs = {}
        for row in report["requests"]:
            key = query_key(row["query"])
            if (key not in expected or key in costs or row["method"] != "metadata.get_cost"
                    or row["status"] != "ok" or row["http_status"] != 200
                    or not re.fullmatch(r"[0-9a-f]{64}", row["response_sha256"])):
                raise ValueError
            costs[key] = cost_string(row["value"])
        ordered = tuple(costs[query_key(query)] for query in REFERENCES)
        if add_cost(*ordered) != cost_string(report["successful_quote_sum_usd"]):
            raise ValueError
        return {"sha256": hashlib.sha256(raw).hexdigest(), "costs": ordered}
    except (OSError, ValueError, KeyError, TypeError, ArchiveError):
        raise ArchiveError("incomplete_or_invalid_exact_quote") from None


class Client(HistoricalClient):
    """Reuse verified TLS, no-redirect and sanitized transport; narrow its allowlist."""

    def allowed(self, method, params):
        if method in ("metadata.get_cost", "metadata.get_record_count"):
            return params in REFERENCES
        return method == "timeseries.get_range" and any(params == query | ENCODING for query in REFERENCES)

    def open(self, method, params):
        if method not in ("metadata.get_cost", "metadata.get_record_count"):
            # Paid transport remains unchanged. In particular, a paid HTTP 429
            # without a captured Retry-After is not eligible for automatic resume.
            return super().open(method, params)
        if not self.allowed(method, params):
            raise ArchiveError("request_outside_fixed_archive")
        meta = {"method": method, "query": dict(params), "requested_at": utcnow(),
                "result": "attempting", "http_method": "GET", "timeout_seconds": METADATA_TIMEOUT_SECONDS}
        self.requests.append(meta)
        headers = {"Authorization": self._auth, "Accept": "application/json", "Accept-Encoding": "identity",
                   "User-Agent": "BoringAlpha-BA012References/1"}
        request = urllib.request.Request(HOST + method + "?" + urllib.parse.urlencode(params), method="GET", headers=headers)
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=_CONTEXT))
        try:
            METADATA_LIMITER.wait()
            meta["request_started_at"] = utcnow()
            response = opener.open(request, timeout=METADATA_TIMEOUT_SECONDS)
            meta["http_status"] = response.code
            if response.code != 200:
                response.close()
                raise ArchiveError("http_error")
            if response.headers.get("Content-Encoding", "identity").lower() not in ("identity", ""):
                response.close()
                raise ArchiveError("unexpected_http_compression")
            return meta, response
        except urllib.error.HTTPError as exc:
            # Never inspect or persist arbitrary authentication/account/error bodies.
            meta.update(http_status=exc.code, result="http_error", received_at=utcnow())
            try:
                delay = retry_after_seconds(exc.headers.get("Retry-After") if exc.headers else None)
                if delay is not None:
                    meta["retry_after_seconds"] = delay
            except (ValueError, TypeError, OverflowError):
                meta["invalid_retry_after"] = True
            exc.close()
            raise ArchiveError("http_error") from None
        except ArchiveError as exc:
            meta.update(result=str(exc), received_at=utcnow())
            raise
        except Exception:
            meta.update(result="transport_error", received_at=utcnow())
            raise ArchiveError("transport_error") from None

    def metadata(self, method, params):
        if method not in ("metadata.get_cost", "metadata.get_record_count") or not self.allowed(method, params):
            raise ArchiveError("request_outside_fixed_metadata")
        for attempt in range(METADATA_ATTEMPTS):
            try:
                return super().metadata(method, params)
            except ArchiveError as exc:
                request = self.requests[-1] if self.requests else {}
                status = request.get("http_status")
                delay = request.get("retry_after_seconds", 0)
                transient = str(exc) == "transport_error" or str(exc) == "http_error" and status in TRANSIENT_HTTP
                if request.get("invalid_retry_after") or delay > MAX_RETRY_WAIT_SECONDS:
                    raise
                if not transient or attempt == METADATA_ATTEMPTS - 1:
                    raise
                delay = max(attempt + 1, delay)
                if status == 429:
                    METADATA_LIMITER.defer(delay)
                time.sleep(delay)


def stamp_ns(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.microsecond:
        raise ArchiveError("invalid_reference_timestamp")
    delta = stamp.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 10**9


def price_integer(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]{1,20}", value):
        return int(value)
    raise ArchiveError("invalid_fixed_point_price")


def validate_bar(raw, query, seen):
    try:
        item = load_json(raw)
        if set(item) != {"hd", "open", "high", "low", "close", "volume"}:
            raise ValueError
        hd = item["hd"]
        if set(hd) != {"ts_event", "rtype", "publisher_id", "instrument_id"}:
            raise ValueError
        instrument = strict_integer(hd["instrument_id"])
        if (strict_integer(hd["ts_event"]) != stamp_ns(query["start"])
                or stamp_ns(query["end"]) - stamp_ns(query["start"]) != 60 * 10**9
                or strict_integer(hd["rtype"]) != 33
                or not 0 < strict_integer(hd["publisher_id"]) < 2**16
                or not 0 < instrument < 2**32 or instrument in seen):
            raise ValueError
        opening, high, low, close = [price_integer(item[field]) for field in ("open", "high", "low", "close")]
        # Databento .FUT parents include spreads. Signed/zero raw prices are
        # legitimate; positivity is a later test of mapped selected outrights.
        if (not -(2**63) <= low <= min(opening, close) <= max(opening, close) <= high < 2**63 - 1
                or not 0 < strict_integer(item["volume"]) < 2**64):
            raise ValueError
        seen.add(instrument)
    except (ValueError, TypeError, KeyError, OverflowError, ArchiveError):
        raise ArchiveError("invalid_reference_bar") from None


def download_partition(client, query, upper_bound, destination):
    """Count metadata is an upper bound for sub-ten-minute requests, not equality."""
    partial = destination.with_suffix(destination.suffix + ".partial")
    meta, response = client.open("timeseries.get_range", query | ENCODING)
    count, size, seen = 0, 0, set()
    digest = hashlib.sha256()
    try:
        with response, partial.open("xb") as output:
            length = response.headers.get("Content-Length")
            if length is not None and (not re.fullmatch(r"[0-9]{1,12}", length) or int(length) > upper_bound * MAX_LINE_BYTES):
                raise ArchiveError("oversized_reference_response")
            with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as compressed:
                while raw := response.readline(MAX_LINE_BYTES + 1):
                    count += 1
                    size += len(raw)
                    if count > upper_bound or len(raw) > MAX_LINE_BYTES:
                        raise ArchiveError("reference_response_exceeds_count")
                    if client.contains_secret(raw):
                        raise ArchiveError("unsafe_reference_response")
                    validate_bar(raw, query, seen)
                    digest.update(raw)
                    compressed.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.link(partial, destination)
        partial.unlink()
        destination.chmod(0o444)
        meta.update(result="ok", received_at=utcnow(), response_bytes=size, response_sha256=digest.hexdigest())
        return {"file": destination.name, "records": count, "raw_bytes": size,
                "raw_sha256": digest.hexdigest(), "gzip_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "instrument_ids": sorted(seen)}
    except BaseException as exc:
        partial.unlink(missing_ok=True)
        code = str(exc) if isinstance(exc, ArchiveError) else "reference_download_failed"
        meta.update(result=code, received_at=utcnow(), observed_records=count)
        raise ArchiveError(code) from None


def persist(folder, manifest):
    temporary = folder / "manifest.json.tmp"
    with temporary.open("w") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(folder / "manifest.json")
    for directory in (folder, folder.parent):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def prior_state(output_root):
    """Reconcile reservations, not successful downloads or the latest run alone."""
    total, completed = Decimal(0), set()
    if not output_root.exists():
        return total, completed
    try:
        for folder in output_root.iterdir():
            if folder.name == ".download.lock":
                continue
            if folder.is_symlink() or not folder.is_dir():
                raise ValueError
            report = load_json((folder / "manifest.json").read_bytes())
            if (report["schema"] != SCHEMA or report["protocol_sha256"] != PROTOCOL_SHA256
                    or report["query_plan_sha256"] != plan_sha256()):
                raise ValueError
            reservations, seen = [], set()
            for row in report["reservations"]:
                key = query_key(row["query"])
                if row["query"] not in REFERENCES or key in seen:
                    raise ValueError
                seen.add(key)
                reservations.append(cost_string(row["quote_usd"]))
            subtotal = add_cost(*reservations)
            if subtotal != cost_string(report["quote_attempted_total_usd"]):
                raise ValueError
            total = add_cost(total, subtotal)
            data_queries = {query_key(query | ENCODING): query_key(query) for query in REFERENCES}
            recorded_attempts = set()
            for request in report["requests"]:
                if request["method"] in ("metadata.get_cost", "metadata.get_record_count"):
                    if request["query"] not in REFERENCES:
                        raise ValueError
                elif request["method"] == "timeseries.get_range":
                    key = data_queries[query_key(request["query"])]
                    if key not in seen or key in recorded_attempts:
                        raise ValueError
                    recorded_attempts.add(key)
                else:
                    raise ValueError
            files = {"manifest.json"}
            partition_keys = set()
            for partition in report["partitions"]:
                key = query_key(partition["query"])
                if (partition["query"] not in REFERENCES or key in partition_keys
                        or partition["status"] not in ("counted", "attempting", "complete")
                        or partition["status"] in ("attempting", "complete") and key not in seen):
                    raise ValueError
                partition_keys.add(key)
                if partition["status"] != "complete":
                    continue
                query = partition["query"]
                filename = query["start"][:10] + "-parent-references.jsonl.gz"
                if (query not in REFERENCES or key not in seen or key in completed
                        or partition["file"] != filename
                        or type(partition["records"]) is not int or type(partition["record_count_upper_bound"]) is not int
                        or not 0 <= partition["records"] <= partition["record_count_upper_bound"] <= MAX_RECORDS):
                    raise ValueError
                archive = folder / filename
                if archive.is_symlink() or hashlib.sha256(archive.read_bytes()).hexdigest() != partition["gzip_sha256"]:
                    raise ValueError
                completed.add(key)
                files.add(filename)
            # A crash between archive publication and manifest update must be
            # reconciled before another request, not silently purchased again.
            if {path.name for path in folder.iterdir()} != files:
                raise ValueError
        return total, completed
    except (OSError, ValueError, KeyError, TypeError, ArchiveError):
        raise ArchiveError("unverifiable_prior_reference_budget") from None


def preflight(quote, ceiling, output_root=OUTPUT_ROOT):
    checked_protocol()
    prior, completed = prior_state(Path(output_root))
    remaining = tuple(cost for query, cost in zip(REFERENCES, quote["costs"])
                      if query_key(query) not in completed)
    projected = add_cost(prior, *remaining)
    if ceiling <= 0 or projected > ceiling:
        raise ArchiveError("reference_estimate_budget_exceeded")
    return {"queries": len(REFERENCES), "remaining_queries": len(remaining),
            "verified_completed_queries": len(completed), "prior_attempted_estimate_usd": str(prior),
            "saved_quote_total_usd": str(add_cost(*quote["costs"])),
            "remaining_saved_quote_usd": str(add_cost(*remaining)),
            "projected_aggregate_estimate_usd": str(projected), "estimate_ceiling_usd": str(ceiling),
            "quote_sha256": quote["sha256"], "data_downloads": 0}


def run_archive(client, quote, ceiling, output_root=OUTPUT_ROOT):
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    lock = output_root / ".download.lock"
    try:
        lock.open("x").close()
    except FileExistsError:
        raise ArchiveError("reference_archive_locked") from None
    folder = manifest = None
    try:
        summary = preflight(quote, ceiling, output_root)
        prior = cost_string(summary["prior_attempted_estimate_usd"])
        _, completed = prior_state(output_root)
        folder = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder.mkdir(exist_ok=False)
        manifest = {"schema": SCHEMA, "status": "acquiring", "started_at": utcnow(),
            "protocol_sha256": PROTOCOL_SHA256, "query_plan_sha256": plan_sha256(),
            "preflight": summary, "quote_attempted_total_usd": "0", "reservations": [],
            "partitions": [], "requests": client.requests, "strategy_returns_calculated": False,
            "raw_encoding": "JSON lines; timestamps in nanoseconds; integer prices scaled by 1e-9; instrument IDs retained",
            "limitations": ["Estimates are not a hard billing cap; no account balance was queried.",
                "No retry occurs within a run; subsequent explicit invocations reuse verified complete archives and count all prior reservations.",
                "Weekdays are an acquisition superset, not the joint trading calendar.",
                "Sub-ten-minute count metadata is an upper bound; no count-equality or completeness claim is made.",
                "Parent .FUT includes spreads: signed/zero raw prices are allowed. Positivity is required later for mapped selected outright references.",
                "No raw-symbol mapping, selected contract, required-market coverage or executable child prices established."]}
        persist(folder, manifest)
        attempted = Decimal(0)
        remaining = [(query, cost) for query, cost in zip(REFERENCES, quote["costs"])
                     if query_key(query) not in completed]
        for index, (query, _) in enumerate(remaining):
            count = strict_integer(load_json(client.metadata("metadata.get_record_count", query)))
            if not 0 <= count <= MAX_RECORDS:
                raise ArchiveError("invalid_reference_record_count")
            partition = {"query": dict(query), "record_count_upper_bound": count, "status": "counted"}
            manifest["partitions"].append(partition)
            # This exact unbounded query is also the one in the saved quote.
            fresh = decimal_cost(client.metadata("metadata.get_cost", query))
            if add_cost(prior, attempted, fresh, *(cost for _, cost in remaining[index + 1:])) > ceiling:
                raise ArchiveError("fresh_reference_estimate_budget_exceeded")
            attempted = add_cost(attempted, fresh)
            manifest["reservations"].append({"query": dict(query), "quote_usd": str(fresh), "reserved_at": utcnow()})
            manifest["quote_attempted_total_usd"] = str(attempted)
            partition["status"] = "attempting"
            # Persist even a failed or uncertain attempt's estimate before opening data.
            persist(folder, manifest)
            partition.update(download_partition(client, query, count,
                folder / (query["start"][:10] + "-parent-references.jsonl.gz")), status="complete")
            persist(folder, manifest)
            if (index + 1) % 100 == 0:
                print(json.dumps({"complete_queries": index + 1, "attempted_estimate_usd": str(attempted)}), flush=True)
        manifest["status"] = "complete"
    except BaseException as exc:
        if manifest is None:
            raise ArchiveError(str(exc) if isinstance(exc, ArchiveError) else "reference_archive_setup_failed") from None
        manifest["status"] = "failed"
        manifest["failure"] = str(exc) if isinstance(exc, ArchiveError) else "reference_archive_failed"
    finally:
        if manifest is not None:
            manifest["completed_at"] = utcnow()
            # If this write fails, retain the lock: uncertain budget state needs review.
            persist(folder, manifest)
        lock.unlink()
    return folder, manifest


def run_parallel_archive(factory, quote, ceiling, output_root=OUTPUT_ROOT, workers=6):
    """Parallel network I/O; one supervisor owns every reservation and manifest.

    A data task cannot be submitted until its estimate and request marker have
    been durably recorded. Eligible transient failures leave that date unfinished
    while other dates continue once each. Terminal failures stop new work; all
    submitted tasks are reconciled before releasing the archive lock.
    """
    if type(workers) is not int or not 1 <= workers <= MAX_WORKERS:
        raise ArchiveError("invalid_reference_workers")
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    lock = output_root / ".download.lock"
    try:
        lock.open("x").close()
    except FileExistsError:
        raise ArchiveError("reference_archive_locked") from None
    folder = manifest = None
    pending = {}
    failure = None
    halt_submissions = False

    def prepare(query):
        local = factory()
        try:
            count = strict_integer(load_json(local.metadata("metadata.get_record_count", query)))
            if not 0 <= count <= MAX_RECORDS:
                raise ArchiveError("invalid_reference_record_count")
            cost = decimal_cost(local.metadata("metadata.get_cost", query))
            return local, count, cost, None
        except BaseException as exc:
            return local, None, None, str(exc) if isinstance(exc, ArchiveError) else "reference_metadata_failed"

    def acquire(local, query, count, destination):
        before = len(local.requests)
        try:
            result = download_partition(local, query, count, destination)
            return result, local.requests[before:], None
        except BaseException as exc:
            return None, local.requests[before:], str(exc) if isinstance(exc, ArchiveError) else "reference_download_failed"
        finally:
            local._key = local._auth = ""

    def note_failure(error, requests):
        nonlocal failure, halt_submissions
        manifest["task_failures"].append(error)
        failure = failure or error
        eligible = resumable_failure({"status": "failed", "failure": error,
                                      "task_failures": [error], "requests": requests})
        halt_submissions = halt_submissions or not eligible

    try:
        summary = preflight(quote, ceiling, output_root)
        prior = cost_string(summary["prior_attempted_estimate_usd"])
        _, completed = prior_state(output_root)
        remaining = [(q, c) for q, c in zip(REFERENCES, quote["costs"]) if query_key(q) not in completed]
        remaining_saved = add_cost(*(c for _, c in remaining))
        attempted = Decimal(0)
        folder = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder.mkdir(exist_ok=False)
        manifest = {"schema": SCHEMA, "status": "acquiring", "started_at": utcnow(),
            "protocol_sha256": PROTOCOL_SHA256, "query_plan_sha256": plan_sha256(),
            "collector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "workers": workers, "preflight": summary, "quote_attempted_total_usd": "0",
            "reservations": [], "partitions": [], "requests": [], "task_failures": [], "strategy_returns_calculated": False,
            "limitations": ["Cost estimates are not a provider-enforced billing cap.",
                "All previous failed/uncertain attempts remain charged to the estimate budget.",
                "One data attempt per run; optional bounded new runs reuse completed dates and charge all prior reservations.",
                "Raw parent superset includes spreads and missing minutes; no selected-out-right coverage claim.",
                "Sub-ten-minute record counts are upper bounds, not expected equalities."]}
        persist(folder, manifest)
        next_index = done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            while pending or next_index < len(remaining) and not halt_submissions:
                while not halt_submissions and len(pending) < workers and next_index < len(remaining):
                    query, saved_cost = remaining[next_index]
                    next_index += 1
                    pending[pool.submit(prepare, query)] = ("metadata", query, saved_cost)
                ready, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in ready:
                    phase, query, context = pending.pop(future)
                    if phase == "metadata":
                        local, count, fresh, error = future.result()
                        manifest["requests"].extend(local.requests)
                        if error:
                            note_failure(error, local.requests)
                        if error or halt_submissions:
                            local._key = local._auth = ""
                            persist(folder, manifest)
                            continue
                        remaining_saved = add_cost(remaining_saved, -context)
                        if add_cost(prior, attempted, fresh, remaining_saved) > ceiling:
                            note_failure("fresh_reference_estimate_budget_exceeded", local.requests)
                            local._key = local._auth = ""
                            persist(folder, manifest)
                            continue
                        attempted = add_cost(attempted, fresh)
                        manifest["reservations"].append({"query": dict(query), "quote_usd": str(fresh), "reserved_at": utcnow()})
                        manifest["quote_attempted_total_usd"] = str(attempted)
                        partition = {"query": dict(query), "record_count_upper_bound": count, "status": "attempting"}
                        manifest["partitions"].append(partition)
                        marker = len(manifest["requests"])
                        manifest["requests"].append({"method": "timeseries.get_range", "query": query | ENCODING,
                                                     "requested_at": utcnow(), "result": "attempting"})
                        persist(folder, manifest)
                        destination = folder / (query["start"][:10] + "-parent-references.jsonl.gz")
                        pending[pool.submit(acquire, local, query, count, destination)] = ("data", query, (partition, marker))
                    else:
                        result, requests, error = future.result()
                        partition, marker = context
                        if len(requests) == 1 and requests[0]["method"] == "timeseries.get_range" and requests[0]["query"] == query | ENCODING:
                            manifest["requests"][marker] = requests[0]
                        else:
                            error = "unreconciled_data_request"
                        if error:
                            note_failure(error, requests)
                        else:
                            partition.update(result, status="complete")
                            done += 1
                        persist(folder, manifest)
                        if done and done % 100 == 0:
                            print(json.dumps({"complete_this_run": done, "previously_complete": len(completed),
                                              "aggregate_attempted_estimate_usd": str(add_cost(prior, attempted))}), flush=True)
            manifest["status"] = "failed" if failure else "complete"
            if failure:
                manifest["failure"] = failure
    except BaseException as exc:
        if manifest is None:
            raise ArchiveError(str(exc) if isinstance(exc, ArchiveError) else "reference_archive_setup_failed") from None
        manifest["status"] = "failed"
        manifest["failure"] = str(exc) if isinstance(exc, ArchiveError) else "reference_archive_interrupted"
        manifest["task_failures"].append(manifest["failure"])
        # The executor drains already dispatched requests on exit. If an abrupt
        # interruption bypassed result processing, prior_state fails closed on
        # unrecorded published files. Reservations remain durable regardless.
    finally:
        if manifest is not None:
            manifest["completed_at"] = utcnow()
            persist(folder, manifest)
        lock.unlink()
    return folder, manifest


def resumable_failure(manifest):
    """Every observed failure must be transient; generic/validation errors stop."""
    if manifest.get("status") != "failed" or manifest.get("failure") not in ("transport_error", "http_error"):
        return False
    if any(error not in ("transport_error", "http_error") for error in manifest.get("task_failures", [manifest["failure"]])):
        return False
    failures = [row for row in manifest["requests"] if row.get("result") != "ok"]
    if not failures:
        return False
    return all((row.get("result") == "transport_error"
                or row.get("result") == "http_error" and row.get("http_status") in TRANSIENT_HTTP)
               and not (row.get("method") == "timeseries.get_range" and row.get("http_status") == 429
                        and "retry_after_seconds" not in row)
               and not row.get("invalid_retry_after")
               and row.get("retry_after_seconds", 0) <= MAX_RETRY_WAIT_SECONDS for row in failures)


def run_with_resumes(factory, quote, ceiling, output_root=OUTPUT_ROOT, *, workers=1, attempts=1):
    """Opt-in bounded runs. Each run reacquires the lock and rechecks all costs."""
    if type(attempts) is not int or not 1 <= attempts <= MAX_RESUME_ATTEMPTS:
        raise ArchiveError("invalid_resume_attempts")
    if type(workers) is not int or not 1 <= workers <= MAX_WORKERS:
        raise ArchiveError("invalid_reference_workers")
    previous_manifest = None
    for attempt in range(1, attempts + 1):
        if workers == 1:
            local = factory()
            try:
                folder, manifest = run_archive(local, quote, ceiling, output_root)
            finally:
                local._key = local._auth = ""
        else:
            folder, manifest = run_parallel_archive(factory, quote, ceiling, output_root, workers=workers)
        # Reconciliation is mandatory before considering a retry; orphan output,
        # uncertain publication or a corrupt ledger must never trigger purchase.
        aggregate, complete = prior_state(Path(output_root))
        eligible = resumable_failure(manifest)
        manifest["resume"] = {"attempt": attempt, "maximum_runs_including_initial": attempts,
            "previous_manifest": previous_manifest, "transient_failure_eligible": eligible}
        persist(folder, manifest)
        print(json.dumps({"event": "acquisition_run_completed", "attempt": attempt, "maximum_runs": attempts,
            "status": manifest["status"], "failure": manifest.get("failure"), "manifest": str(folder / "manifest.json"),
            "verified_complete_dates": len(complete), "aggregate_attempted_estimate_usd": str(aggregate)}), flush=True)
        if manifest["status"] == "complete" or not eligible or attempt == attempts:
            return folder, manifest
        previous_manifest = str(folder / "manifest.json")
        delay = max(1, *(row.get("retry_after_seconds", 0) for row in manifest["requests"]))
        time.sleep(delay)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid collector arguments; run --help.\n")


def main():
    parser = SafeParser(description=__doc__)
    parser.add_argument("--quote", type=Path, required=True)
    parser.add_argument("--max-estimate-usd", required=True, help="Aggregate estimate ceiling including all prior attempts")
    parser.add_argument("--acquire", action="store_true", help="Enable historical data requests after hidden key entry")
    parser.add_argument("--workers", type=int, default=1, choices=range(1, MAX_WORKERS + 1))
    parser.add_argument("--resume-attempts", type=int, default=1, choices=range(1, MAX_RESUME_ATTEMPTS + 1),
        help="Maximum runs including the initial run; default 1 disables automatic resume. Each run counts prior reservations.")
    args = parser.parse_args()
    client = None
    key = ""
    try:
        quote = load_quote(args.quote)
        ceiling = cost_string(args.max_estimate_usd)
        summary = preflight(quote, ceiling)
        if not args.acquire:
            print(json.dumps({"status": "offline_preflight_passed", **summary}), flush=True)
            return 0
        if not sys.stdin.isatty():
            raise ArchiveError("interactive_hidden_credential_required")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("Databento API key (hidden): ").strip()
        if not re.fullmatch(r"db-[A-Za-z0-9_-]{20,80}", key):
            raise ArchiveError("invalid_credential_format")
        client = Client(key)
        key = ""
        folder, manifest = run_with_resumes(lambda: Client(client._key), quote, ceiling,
                                           workers=args.workers, attempts=args.resume_attempts)
        print(json.dumps({"status": manifest["status"], "manifest": str(folder / "manifest.json"),
            "attempted_estimate_usd": manifest["quote_attempted_total_usd"], "failure": manifest.get("failure")}), flush=True)
        return 0 if manifest["status"] == "complete" else 1
    except BaseException as exc:
        code = str(exc) if isinstance(exc, ArchiveError) else "reference_collector_stopped"
        print(json.dumps({"status": "failed", "failure": code}), file=sys.stderr)
        return 1
    finally:
        key = ""
        if client is not None:
            client._key = client._auth = ""


if __name__ == "__main__":
    raise SystemExit(main())
