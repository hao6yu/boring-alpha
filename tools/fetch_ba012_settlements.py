#!/usr/bin/env python3
"""Quote first; optionally archive exact BA-012 statistics queries under $1 total.

Default quotes only. --active-intervals is the sole narrower plan. --acquire
requires an affordable complete quote in this run and requotes each paid query.
No automatic paid retry, account API, strategy calculation or settlement filter.
The original attempt stopped at 2026-09-10 16:42:18 UTC. The separately
authorized --continue-download removes that elapsed time gate, retaining $1.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
import getpass
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_ba012_references as a
import fetch_mes_history as transport
from prepare_ba012_inputs import load_design, frozen_json, PARENTS, STAGE

OUTPUT_ROOT = a.ROOT / "data/futures/ba012-settlements"
SCHEMA = "ba012-statistics-archive-v1"
CEILING = Decimal("1")
DEADLINE = datetime(2026, 9, 10, 16, 42, 18, tzinfo=timezone.utc)
CONTINUATION = STAGE / "download-continuation-20260910.json"
MAX_METADATA = 1_000_000
transport.MAX_METADATA_BYTES = MAX_METADATA  # This helper process only; retain the existing retry/secret checks.
MAX_LINE = 8192
MAX_DATA = 256_000_000  # Per exact query; stream and stop before exceeding it.
DATA_TIMEOUT_SECONDS = 60


def check_time(minimum_seconds=0):
    if DEADLINE is not None and (DEADLINE - datetime.now(timezone.utc)).total_seconds() <= minimum_seconds:
        raise a.ArchiveError("experiment_deadline_reached")


def deadline_iso():
    return DEADLINE.isoformat() if DEADLINE is not None else None


class DeadlineLimiter:
    def __init__(self, base):
        self.base = base

    def wait(self):
        result = self.base.wait()
        check_time(20)
        return result

    def defer(self, seconds):
        self.base.defer(seconds)


def make_plan(design, active=False):
    required = {}
    for row in design["rolls"]["rows"]:
        for market in row["markets"]:
            for raw_symbol in market["required_parent_raw_symbols"]:
                symbol = re.sub(r"^GCV([0-9]{1,2})$", r"GCZ\1", raw_symbol)
                required.setdefault(symbol, []).append(row["date_chicago"])
    base = {"dataset": "GLBX.MDP3", "schema": "statistics", "stype_in": "raw_symbol"}
    if active:
        queries = tuple(base | {"symbols": symbol, "start": min(days),
            "end": (date.fromisoformat(max(days)) + timedelta(days=1)).isoformat()}
            for symbol, days in sorted(required.items()))
    else:
        queries = tuple(base | {"symbols": ",".join(sorted(s for s in required if s.startswith(parent))),
            "start": "2016-01-11", "end": "2024-01-01"} for parent in PARENTS)
    return {"schema": "ba012-statistics-plan-v1", "mode": "active_intervals" if active else "five_parent_groups",
        "rolls_sha256": design["rolls_sha256"], "calendar_sha256": design["calendar_sha256"],
        "amendment_sha256": design["rolls"].get("amendment_sha256"),
        "gold_change": "GCV replaced by same-year GCZ; all other frozen required symbols retained.",
        "deadline_utc": deadline_iso(), "queries": queries}


class Client(a.Client):
    def __init__(self, key, queries):
        super().__init__(key)
        self.queries = queries

    def allowed(self, method, params):
        return (method == "metadata.get_cost" and params in self.queries
                or method == "timeseries.get_range" and any(params == q | a.ENCODING for q in self.queries))

    def quote(self, query):
        check_time(20)
        return a.decimal_cost(self.metadata("metadata.get_cost", query))

    def open(self, method, params):
        if method != "timeseries.get_range":
            return super().open(method, params)
        if not self.allowed(method, params):
            raise a.ArchiveError("request_outside_fixed_statistics")
        check_time(DATA_TIMEOUT_SECONDS + 1)
        meta = {"method": method, "query": dict(params), "requested_at": a.utcnow(), "result": "attempting",
                "timeout_seconds": DATA_TIMEOUT_SECONDS}
        self.requests.append(meta)
        request = urllib.request.Request(a.HOST + method, method="POST", data=urllib.parse.urlencode(params).encode(),
            headers={"Authorization": self._auth, "Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json", "Accept-Encoding": "identity"})
        opener = urllib.request.build_opener(a.NoRedirect(), urllib.request.HTTPSHandler(context=a._CONTEXT))
        try:
            response = opener.open(request, timeout=DATA_TIMEOUT_SECONDS)
            meta["http_status"] = response.code
            if response.code not in (200, 206):
                response.close()
                raise a.ArchiveError("http_error")
            if response.headers.get("Content-Encoding", "identity").lower() not in ("identity", ""):
                response.close()
                raise a.ArchiveError("unexpected_http_compression")
            meta["partial_symbol_resolution"] = response.code == 206
            # 206 denotes partial symbol resolution, not a truncated byte stream.
            # Preserve warning hashes without exposing arbitrary header text.
            meta["warning_headers"] = [{"name": name, "bytes": len(value.encode()),
                "sha256": hashlib.sha256(value.encode()).hexdigest()} for name, value in response.headers.items()
                if "warning" in name.lower()]
            return meta, response
        except urllib.error.HTTPError as exc:
            meta.update(http_status=exc.code, result="http_error", received_at=a.utcnow())
            exc.close()
            raise a.ArchiveError("http_error") from None
        except a.ArchiveError as exc:
            meta.update(result=str(exc), received_at=a.utcnow())
            raise
        except Exception as exc:
            meta.update(result="transport_error", received_at=a.utcnow(),
                        transport_exception_type=type(exc).__name__,
                        transport_reason_type=type(getattr(exc, "reason", None)).__name__)
            raise a.ArchiveError("transport_error") from None


def query_id(query):
    return hashlib.sha256(a.query_key(query).encode()).hexdigest()


def statistics_prior(root):
    total, completed = Decimal(0), set()
    try:
        for folder in root.iterdir():
            if folder.name == ".download.lock":
                continue
            if not folder.is_dir() or folder.is_symlink():
                raise ValueError
            report = a.load_json((folder / "manifest.json").read_bytes())
            if report["schema"] != SCHEMA:
                raise ValueError
            reservations = {query_id(row["query"]): a.cost_string(row["quote_usd"]) for row in report["reservations"]}
            if len(reservations) != len(report["reservations"]):
                raise ValueError
            subtotal = a.add_cost(*reservations.values())
            if subtotal != a.cost_string(report["quote_attempted_total_usd"]):
                raise ValueError
            total = a.add_cost(total, subtotal)
            attempts = set()
            for request in report["requests"]:
                if request["method"] == "timeseries.get_range":
                    original = {k: v for k, v in request["query"].items() if k not in a.ENCODING}
                    identity = query_id(original)
                    if identity not in reservations or identity in attempts or request["query"] != original | a.ENCODING:
                        raise ValueError
                    attempts.add(identity)
                elif request["method"] != "metadata.get_cost":
                    raise ValueError
            files = {"manifest.json", "query-plan.json"}
            for partition in report["partitions"]:
                identity = query_id(partition["query"])
                if partition["status"] == "attempting" and identity not in reservations:
                    raise ValueError
                if partition["status"] == "complete":
                    if identity not in reservations or identity in completed or partition["file"] != identity + ".jsonl.gz":
                        raise ValueError
                    path = folder / partition["file"]
                    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != partition["gzip_sha256"]:
                        raise ValueError
                    completed.add(identity)
                    files.add(path.name)
            if {p.name for p in folder.iterdir()} != files:
                raise ValueError
        return total, completed
    except (OSError, ValueError, KeyError, TypeError, a.ArchiveError):
        raise a.ArchiveError("unverifiable_statistics_budget") from None


def download(client, query, destination):
    check_time(DATA_TIMEOUT_SECONDS + 1)
    meta, response = client.open("timeseries.get_range", query | a.ENCODING)
    partial = destination.with_suffix(destination.suffix + ".partial")
    count, size, digest = 0, 0, hashlib.sha256()
    try:
        length = response.headers.get("Content-Length")
        if length is not None and (not re.fullmatch(r"[0-9]{1,12}", length) or int(length) > MAX_DATA):
            raise a.ArchiveError("invalid_statistics_content_length")
        with response, partial.open("xb") as output, gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as gz:
            while True:
                check_time(DATA_TIMEOUT_SECONDS)
                line = response.readline(MAX_LINE + 1)
                if not line:
                    break
                size += len(line)
                if len(line) > MAX_LINE or size > MAX_DATA or client.contains_secret(line):
                    raise a.ArchiveError("unsafe_or_oversized_statistics_stream")
                item = a.load_json(line)
                if (not isinstance(item, dict) or not isinstance(item.get("hd"), dict)
                        or not 0 < a.strict_integer(item["hd"]["instrument_id"]) < 2**32
                        or not 0 <= a.strict_integer(item["hd"]["ts_event"]) < 2**64
                        or "stat_type" not in item):
                    raise a.ArchiveError("invalid_statistics_record")
                # Preserve every type, action, flag, undefined field and update.
                # Event/reference-time interpretation belongs to the adapter.
                gz.write(line)
                digest.update(line)
                count += 1
        if length is not None and size != int(length):
            raise a.ArchiveError("statistics_content_length_mismatch")
        with partial.open("rb") as stream:
            os.fsync(stream.fileno())
        os.link(partial, destination)
        partial.unlink()
        destination.chmod(0o444)
        meta.update(result="ok", received_at=a.utcnow(), response_sha256=digest.hexdigest(), response_bytes=size)
        return {"file": destination.name, "records": count, "raw_bytes": size, "raw_sha256": digest.hexdigest(),
                "partial_symbol_resolution": meta.get("partial_symbol_resolution", False),
                "gzip_sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}
    except BaseException as exc:
        partial.unlink(missing_ok=True)
        code = str(exc) if isinstance(exc, a.ArchiveError) else "statistics_download_failed"
        meta.update(result=code, received_at=a.utcnow(), observed_records=count)
        raise a.ArchiveError(code) from None


def run(client, plan, acquire=False, output_root=OUTPUT_ROOT, original_root=a.OUTPUT_ROOT, quote_workers=1, download_workers=1, continue_transport_errors=False):
    if type(download_workers) is not int or not 1 <= download_workers <= 4:
        raise a.ArchiveError("invalid_statistics_download_workers")
    if type(continue_transport_errors) is not bool:
        raise a.ArchiveError("invalid_statistics_transport_policy")
    if len({query_id(query) for query in plan["queries"]}) != len(plan["queries"]):
        raise a.ArchiveError("duplicate_statistics_query")
    output_root, original_root = Path(output_root), Path(original_root)
    output_root.mkdir(parents=True, exist_ok=True)
    locks, folder, manifest = [], None, None
    try:
        # Prevent a concurrent original collector from changing the shared budget.
        for root in (original_root, output_root):
            lock = root / ".download.lock"
            lock.open("x").close()
            locks.append(lock)
        old_cost, _ = a.prior_state(original_root)
        new_cost, completed = statistics_prior(output_root)
        prior = a.add_cost(old_cost, new_cost)
        folder = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder.mkdir(exist_ok=False)
        plan_raw = (json.dumps(plan, sort_keys=True, indent=2) + "\n").encode()
        (folder / "query-plan.json").write_bytes(plan_raw)
        manifest = {"schema": SCHEMA, "status": "quoting", "started_at": a.utcnow(),
            "plan_sha256": hashlib.sha256(plan_raw).hexdigest(), "deadline_utc": deadline_iso(),
            "download_workers": download_workers, "data_timeout_seconds": DATA_TIMEOUT_SECONDS,
            "continuation_authorization": plan.get("continuation_authorization"),
            "continue_transport_errors": continue_transport_errors,
            "amendment_sha256": plan.get("amendment_sha256"), "rolls_sha256": plan.get("rolls_sha256"),
            "original_archive_root": str(original_root), "original_attempted_estimate_usd": str(old_cost),
            "prior_statistics_estimate_usd": str(new_cost), "aggregate_prior_estimate_usd": str(prior),
            "estimate_ceiling_usd": "1", "quote_attempted_total_usd": "0", "reservations": [], "partitions": [],
            "requests": client.requests, "strategy_returns_calculated": False,
            "limitations": ["All statistics types/updates preserved; no settlement selection or coverage claim.",
                "Quotes are estimates, not a provider billing cap. Prior failed/uncertain reservations remain charged.",
                "No automatic paid retry. Stream bound256MB per query; midnight date boundaries are UTC."]}
        a.persist(folder, manifest)
        pending = [q for q in plan["queries"] if query_id(q) not in completed]
        quotes = [None] * len(pending)
        manifest["partitions"] = [{"query": query, "status": "unquoted"} for query in pending]
        def quote_one(query):
            local = Client(client._key, client.queries)
            try:
                return local.quote(query), local.requests, None
            except BaseException as exc:
                return None, local.requests, str(exc) if isinstance(exc, a.ArchiveError) else "statistics_quote_failed"
            finally:
                local._key = local._auth = ""
        errors = []
        if quote_workers == 1:
            for index, query in enumerate(pending):
                quotes[index] = client.quote(query)
                manifest["partitions"][index].update(quote_usd=str(quotes[index]), status="quoted")
                a.persist(folder, manifest)
                print(json.dumps({"event": "statistics_quote", "query": index + 1, "queries": len(pending), "quote_usd": str(quotes[index])}), flush=True)
        else:
            if not 1 <= quote_workers <= 6:
                raise a.ArchiveError("invalid_statistics_quote_workers")
            with ThreadPoolExecutor(max_workers=quote_workers) as pool:
                jobs = {pool.submit(quote_one, query): index for index, query in enumerate(pending)}
                for done, future in enumerate(as_completed(jobs), 1):
                    index = jobs[future]
                    quote, requests, error = future.result()
                    manifest["requests"].extend(requests)
                    if error:
                        errors.append(error)
                        manifest["partitions"][index].update(status="quote_failed", failure=error)
                    else:
                        quotes[index] = quote
                        manifest["partitions"][index].update(status="quoted", quote_usd=str(quote))
                    a.persist(folder, manifest)
                    if done % 20 == 0 or done == len(pending):
                        print(json.dumps({"event": "statistics_quotes", "completed": done, "queries": len(pending), "failed": len(errors)}), flush=True)
            if errors:
                raise a.ArchiveError(errors[0])
        projected = a.add_cost(prior, *quotes)
        manifest.update(complete_quote=True, remaining_quote_usd=str(a.add_cost(*quotes)), aggregate_projected_estimate_usd=str(projected))
        if projected > CEILING:
            manifest["status"] = "quote_over_budget"
        elif not acquire:
            manifest["status"] = "quoted_affordable"
        elif download_workers == 1 and not continue_transport_errors:
            attempted = Decimal(0)
            for index, partition in enumerate(manifest["partitions"]):
                query = partition["query"]
                fresh = client.quote(query)
                if a.add_cost(prior, attempted, fresh, *quotes[index + 1:]) > CEILING:
                    raise a.ArchiveError("statistics_requote_budget_exceeded")
                attempted = a.add_cost(attempted, fresh)
                manifest["reservations"].append({"query": query, "quote_usd": str(fresh), "reserved_at": a.utcnow()})
                manifest["quote_attempted_total_usd"] = str(attempted)
                partition["status"] = "attempting"
                a.persist(folder, manifest)
                partition.update(download(client, query, folder / (query_id(query) + ".jsonl.gz")), status="complete")
                a.persist(folder, manifest)
                print(json.dumps({"event": "statistics_archived", "query": index + 1, "records": partition["records"],
                                  "aggregate_attempted_estimate_usd": str(a.add_cost(prior, attempted))}), flush=True)
            manifest["status"] = "complete"
        else:
            from concurrent.futures import wait, FIRST_COMPLETED
            attempted, next_index, completed_count = Decimal(0), 0, 0
            jobs, download_errors = {}, []
            halt_downloads = False
            manifest["download_errors"] = download_errors

            def acquire_one(query, destination):
                local = None
                try:
                    local = Client(client._key, client.queries)
                    return download(local, query, destination), local.requests, None
                except BaseException as exc:
                    code = str(exc) if isinstance(exc, a.ArchiveError) else "statistics_download_failed"
                    return None, [] if local is None else local.requests, code
                finally:
                    if local is not None:
                        local._key = local._auth = ""

            def record_result(future):
                nonlocal completed_count, halt_downloads
                index, marker = jobs.pop(future)
                partition = manifest["partitions"][index]
                result, requests, error = future.result()
                if (len(requests) == 1 and requests[0]["method"] == "timeseries.get_range"
                        and requests[0]["query"] == partition["query"] | a.ENCODING):
                    manifest["requests"][marker] = requests[0]
                else:
                    # Preserve unexpected attempts too, so the existing ledger
                    # audit rejects duplicate/unreserved requests on resume.
                    manifest["requests"].extend(requests)
                    error = "unreconciled_statistics_request"
                if error:
                    download_errors.append(error)
                    partition["failure"] = error
                    # Only a reconciled paid transport failure may leave other
                    # dates running; quote/budget exceptions still exit the loop.
                    halt_downloads = halt_downloads or not (continue_transport_errors and error == "transport_error")
                else:
                    partition.update(result, status="complete")
                    completed_count += 1
                a.persist(folder, manifest)
                print(json.dumps({"event": "statistics_result", "query": index + 1,
                    "status": partition["status"], "failure": error, "completed_this_run": completed_count,
                    "aggregate_attempted_estimate_usd": str(a.add_cost(prior, attempted))}), flush=True)

            with ThreadPoolExecutor(max_workers=download_workers) as pool:
                try:
                    while jobs or next_index < len(pending) and not halt_downloads:
                        while not halt_downloads and len(jobs) < download_workers and next_index < len(pending):
                            index = next_index
                            partition = manifest["partitions"][index]
                            query = partition["query"]
                            fresh = client.quote(query)
                            # A failure may have arrived during this free quote;
                            # reconcile it before reserving another paid request.
                            for finished in [future for future in jobs if future.done()]:
                                record_result(finished)
                            if halt_downloads:
                                break
                            if a.add_cost(prior, attempted, fresh, *quotes[index + 1:]) > CEILING:
                                raise a.ArchiveError("statistics_requote_budget_exceeded")
                            attempted = a.add_cost(attempted, fresh)
                            manifest["reservations"].append({"query": query, "quote_usd": str(fresh), "reserved_at": a.utcnow()})
                            manifest["quote_attempted_total_usd"] = str(attempted)
                            partition["status"] = "attempting"
                            marker = len(manifest["requests"])
                            manifest["requests"].append({"method": "timeseries.get_range", "query": query | a.ENCODING,
                                "requested_at": a.utcnow(), "result": "attempting"})
                            a.persist(folder, manifest)
                            # Both reservation and request marker are durable
                            # before the isolated worker is allowed to start.
                            future = pool.submit(acquire_one, query, folder / (query_id(query) + ".jsonl.gz"))
                            jobs[future] = (index, marker)
                            next_index += 1
                        if jobs:
                            finished, _ = wait(jobs, return_when=FIRST_COMPLETED)
                            for future in finished:
                                record_result(future)
                except BaseException as exc:
                    download_errors.append(str(exc) if isinstance(exc, a.ArchiveError) else "statistics_parallel_stopped")
                finally:
                    # No cancellation or hidden retry: reconcile every already
                    # dispatched request before releasing either budget lock.
                    for future in as_completed(tuple(jobs)):
                        record_result(future)
            if download_errors:
                manifest.update(status="failed", failure=download_errors[0])
            else:
                manifest["status"] = "complete"
    except BaseException as exc:
        code = str(exc) if isinstance(exc, a.ArchiveError) else "statistics_collection_stopped"
        if manifest is None:
            raise a.ArchiveError(code) from None
        manifest.update(status="failed", failure=code)
    finally:
        if manifest is not None:
            manifest["completed_at"] = a.utcnow()
            a.persist(folder, manifest)
        for lock in reversed(locks):
            lock.unlink()
    return folder, manifest


def main():
    global DEADLINE, DATA_TIMEOUT_SECONDS
    parser = a.SafeParser(description=__doc__)
    parser.add_argument("--active-intervals", action="store_true")
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--continue-download", action="store_true", help="Use the recorded user extension of download time; the $1 ceiling remains.")
    parser.add_argument("--download-workers", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--data-timeout-seconds", type=int, choices=(60, 180), default=60)
    parser.add_argument("--continue-transport-errors", action="store_true",
                        help="Finish other planned downloads after an isolated transport error; do not retry the failed request.")
    args = parser.parse_args()
    key, client = "", None
    try:
        DATA_TIMEOUT_SECONDS = args.data_timeout_seconds
        continuation = None
        if args.continue_download:
            raw = CONTINUATION.read_bytes()
            record = a.load_json(raw)
            if (record["schema"] != "ba012-download-continuation-authorization-v1"
                    or record["prior_deadline_superseded"] is not True
                    or record["maximum_total_provider_estimate_usd"] != "1"
                    or not args.active_intervals):
                raise a.ArchiveError("invalid_download_continuation_record")
            continuation = {"path": str(CONTINUATION), "sha256": hashlib.sha256(raw).hexdigest()}
            DEADLINE = None
        check_time()
        def deadline_handler(signum, frame):
            raise a.ArchiveError("experiment_deadline_reached")
        signal.signal(signal.SIGALRM, deadline_handler)
        if DEADLINE is not None:
            signal.setitimer(signal.ITIMER_REAL, (DEADLINE - datetime.now(timezone.utc)).total_seconds())
        design = load_design(STAGE / "rolls-v2.json")
        _, amendment_sha = frozen_json(STAGE / "settlement-amendment-v2.json")
        if design["rolls"]["amendment_sha256"] != amendment_sha:
            raise a.ArchiveError("settlement_amendment_mismatch")
        plan = make_plan(design, args.active_intervals)
        if continuation is not None:
            plan["continuation_authorization"] = continuation
        a.METADATA_LIMITER = DeadlineLimiter(a.METADATA_LIMITER)
        if not sys.stdin.isatty():
            raise a.ArchiveError("interactive_hidden_credential_required")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("Databento key (hidden; quote only unless --acquire): ").strip()
        if not re.fullmatch(r"db-[A-Za-z0-9_-]{20,80}", key):
            raise a.ArchiveError("invalid_credential_format")
        client = Client(key, plan["queries"])
        key = ""
        folder, manifest = run(client, plan, args.acquire, quote_workers=6 if args.active_intervals else 1,
                               download_workers=args.download_workers,
                               continue_transport_errors=args.continue_transport_errors)
        print(json.dumps({"status": manifest["status"], "manifest": str(folder / "manifest.json"),
            "aggregate_prior_estimate_usd": manifest["aggregate_prior_estimate_usd"],
            "remaining_quote_usd": manifest.get("remaining_quote_usd"), "failure": manifest.get("failure")}))
        return 0 if manifest["status"] in ("complete", "quoted_affordable") else 1
    except BaseException as exc:
        print(json.dumps({"status": "failed", "failure": str(exc) if isinstance(exc, a.ArchiveError) else "statistics_helper_stopped"}), file=sys.stderr)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        key = ""
        if client is not None:
            client._key = client._auth = ""


if __name__ == "__main__":
    raise SystemExit(main())
