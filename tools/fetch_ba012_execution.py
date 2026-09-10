#!/usr/bin/env python3
"""Quote fixed BA-012 execution minutes, then optionally archive them.

Separate immutable archive; no P&L, fills or selection. Aggregate incremental
attempt estimates cannot exceed $0.38; original plus settlement plus execution
attempts cannot exceed $1. Paid retries require a new explicit invocation.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
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
from prepare_ba012_inputs import load_design, frozen_json, PARENTS, STAGE, mapping_index, resolve_identity
import fetch_ba012_settlements as settlement_archive

OUTPUT_ROOT = a.ROOT / "data/futures/ba012-execution"
SETTLEMENT_ROOT = settlement_archive.OUTPUT_ROOT
INCREMENTAL_CEILING = Decimal("0.38")
SCHEMA = "ba012-execution-archive-v1"
CEILING = Decimal("1")
DEADLINE = None
CONTINUATION = STAGE / "download-continuation-20260910.json"
MAX_METADATA = 1_000_000
transport.MAX_METADATA_BYTES = MAX_METADATA  # This helper process only; retain the existing retry/secret checks.
MAX_LINE = 8192
MAX_DATA = 16_000_000  # Per exact query; stream and stop before exceeding it.
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


def make_plan(design, mapping):
    original = load_design()
    forward, reverse = mapping_index(mapping, original)
    if not set(design["symbols"]) <= set(original["symbols"]):
        raise a.ArchiveError("execution_identity_outside_original_mapping")
    rows = [r for r in design["rolls"]["rows"] if "2022-07-01" <= r["date_chicago"] < "2024-01-01"]
    if len(rows) != 377:
        raise a.ArchiveError("execution_calendar_mismatch")
    queries, required = [], []
    for row in rows:
        day = row["date_chicago"]
        start = datetime.combine(date.fromisoformat(day), time(10), ZoneInfo("America/Chicago")).astimezone(timezone.utc)
        queries.append({"dataset": "GLBX.MDP3", "schema": "ohlcv-1m", "stype_in": "parent",
            "symbols": "ES.FUT,TN.FUT,6E.FUT,GC.FUT,ZC.FUT", "start": start.isoformat(),
            "end": (start + timedelta(minutes=6)).isoformat()})
        exact = []
        for market in row["markets"]:
            for symbol in market["required_parent_raw_symbols"]:
                instrument = resolve_identity(symbol, day, forward, reverse)
                if instrument is None:
                    raise a.ArchiveError("execution_identity_unresolved")
                exact.append({"parent_root": market["parent_root"], "raw_symbol": symbol, "instrument_id": instrument})
        required.append({"date_chicago": day, "contracts": exact})
    return {"schema": "ba012-execution-plan-v1", "queries": queries, "required_contracts": required,
        "rolls_sha256": design["rolls_sha256"], "calendar_sha256": design["calendar_sha256"],
        "amendment_sha256": design["rolls"]["amendment_sha256"], "start_inclusive": "2022-07-01",
        "end_exclusive": "2024-01-01", "chicago_window": "10:00 inclusive to 10:06 exclusive",
        "authorization": "User approved $25k/$100k profitability test; necessary execution data. Root capped incremental estimates at0.38 and aggregate at1.",
        "incremental_estimate_ceiling_usd": "0.38", "aggregate_estimate_ceiling_usd": "1",
        "limitations": ["Parent query includes all maturities and spreads; exact dated outright selection occurs offline.",
            "Existing09:59 bars remain the only10:00 reference; missing TNH4 on2023-11-24 is not repaired here.",
            "Prices are hypothetical parent execution inputs, not native child fills; no P&L computed."]}


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
            raise a.ArchiveError("request_outside_fixed_execution")
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


def execution_prior(root):
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
        raise a.ArchiveError("unverifiable_execution_budget") from None


def download(client, query, destination):
    check_time(DATA_TIMEOUT_SECONDS + 1)
    meta, response = client.open("timeseries.get_range", query | a.ENCODING)
    partial = destination.with_suffix(destination.suffix + ".partial")
    count, size, digest = 0, 0, hashlib.sha256()
    seen = {}
    try:
        length = response.headers.get("Content-Length")
        if length is not None and (not re.fullmatch(r"[0-9]{1,12}", length) or int(length) > MAX_DATA):
            raise a.ArchiveError("invalid_execution_content_length")
        with response, partial.open("xb") as output, gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as gz:
            while True:
                check_time(DATA_TIMEOUT_SECONDS)
                line = response.readline(MAX_LINE + 1)
                if not line:
                    break
                size += len(line)
                if len(line) > MAX_LINE or size > MAX_DATA or client.contains_secret(line):
                    raise a.ArchiveError("unsafe_or_oversized_execution_stream")
                item = a.load_json(line)
                if not isinstance(item, dict) or not isinstance(item.get("hd"), dict):
                    raise a.ArchiveError("invalid_execution_bar")
                stamp = a.strict_integer(item["hd"]["ts_event"])
                if not a.stamp_ns(query["start"]) <= stamp < a.stamp_ns(query["end"]) or stamp % (60 * 10**9):
                    raise a.ArchiveError("execution_bar_outside_exact_window")
                minute = datetime.fromtimestamp(stamp // 10**9, timezone.utc)
                one_minute = query | {"start": minute.isoformat(), "end": (minute + timedelta(minutes=1)).isoformat()}
                a.validate_bar(line, one_minute, seen.setdefault(stamp, set()))
                if count >= 60_000:
                    raise a.ArchiveError("execution_record_bound_exceeded")
                # Parent.FUT includes signed/zero-price spreads. Preserve them;
                # later exact dated outright selection requires positive prices.
                gz.write(line)
                digest.update(line)
                count += 1
        if length is not None and size != int(length):
            raise a.ArchiveError("execution_content_length_mismatch")
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
        code = str(exc) if isinstance(exc, a.ArchiveError) else "execution_download_failed"
        meta.update(result=code, received_at=a.utcnow(), observed_records=count)
        raise a.ArchiveError(code) from None


def run(client, plan, acquire=False, output_root=OUTPUT_ROOT, original_root=a.OUTPUT_ROOT, quote_workers=1, download_workers=1, continue_transport_errors=False):
    if type(download_workers) is not int or not 1 <= download_workers <= 4:
        raise a.ArchiveError("invalid_execution_download_workers")
    if type(continue_transport_errors) is not bool:
        raise a.ArchiveError("invalid_execution_transport_policy")
    if len({query_id(query) for query in plan["queries"]}) != len(plan["queries"]):
        raise a.ArchiveError("duplicate_execution_query")
    output_root, original_root = Path(output_root), Path(original_root)
    output_root.mkdir(parents=True, exist_ok=True)
    locks, folder, manifest = [], None, None
    try:
        # Prevent a concurrent original collector from changing the shared budget.
        for root in (original_root, SETTLEMENT_ROOT, output_root):
            lock = root / ".download.lock"
            lock.open("x").close()
            locks.append(lock)
        reference_cost, _ = a.prior_state(original_root)
        settlement_cost, _ = settlement_archive.statistics_prior(SETTLEMENT_ROOT)
        old_cost = a.add_cost(reference_cost, settlement_cost)
        ceiling = min(CEILING, a.add_cost(old_cost, INCREMENTAL_CEILING))
        new_cost, completed = execution_prior(output_root)
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
            "prior_execution_estimate_usd": str(new_cost), "aggregate_prior_estimate_usd": str(prior),
            "estimate_ceiling_usd": str(ceiling), "incremental_estimate_ceiling_usd": "0.38",
            "reference_prior_estimate_usd": str(reference_cost), "settlement_prior_estimate_usd": str(settlement_cost), "quote_attempted_total_usd": "0", "reservations": [], "partitions": [],
            "requests": client.requests, "strategy_returns_calculated": False,
            "limitations": ["All raw parent bars preserved; no outright coverage or execution claim.",
                "Quotes are estimates, not a provider billing cap. Prior failed/uncertain reservations remain charged.",
                "No automatic paid retry. Stream bound16MB per exact6-minute query; Chicago window converted toUTC withDST."]}
        a.persist(folder, manifest)
        pending = [q for q in plan["queries"] if query_id(q) not in completed]
        quotes = [None] * len(pending)
        manifest["partitions"] = [{"query": query, "status": "unquoted"} for query in pending]
        def quote_one(query):
            local = Client(client._key, client.queries)
            try:
                return local.quote(query), local.requests, None
            except BaseException as exc:
                return None, local.requests, str(exc) if isinstance(exc, a.ArchiveError) else "execution_quote_failed"
            finally:
                local._key = local._auth = ""
        errors = []
        if quote_workers == 1:
            for index, query in enumerate(pending):
                quotes[index] = client.quote(query)
                manifest["partitions"][index].update(quote_usd=str(quotes[index]), status="quoted")
                a.persist(folder, manifest)
                print(json.dumps({"event": "execution_quote", "query": index + 1, "queries": len(pending), "quote_usd": str(quotes[index])}), flush=True)
        else:
            if not 1 <= quote_workers <= 6:
                raise a.ArchiveError("invalid_execution_quote_workers")
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
                        print(json.dumps({"event": "execution_quotes", "completed": done, "queries": len(pending), "failed": len(errors)}), flush=True)
            if errors:
                raise a.ArchiveError(errors[0])
        projected = a.add_cost(prior, *quotes)
        manifest.update(complete_quote=True, remaining_quote_usd=str(a.add_cost(*quotes)), aggregate_projected_estimate_usd=str(projected))
        if projected > ceiling:
            manifest["status"] = "quote_over_budget"
        elif not acquire:
            manifest["status"] = "quoted_affordable"
        elif download_workers == 1 and not continue_transport_errors:
            attempted = Decimal(0)
            for index, partition in enumerate(manifest["partitions"]):
                query = partition["query"]
                fresh = client.quote(query)
                if a.add_cost(prior, attempted, fresh, *quotes[index + 1:]) > ceiling:
                    raise a.ArchiveError("execution_requote_budget_exceeded")
                attempted = a.add_cost(attempted, fresh)
                manifest["reservations"].append({"query": query, "quote_usd": str(fresh), "reserved_at": a.utcnow()})
                manifest["quote_attempted_total_usd"] = str(attempted)
                partition["status"] = "attempting"
                a.persist(folder, manifest)
                partition.update(download(client, query, folder / (query_id(query) + ".jsonl.gz")), status="complete")
                a.persist(folder, manifest)
                print(json.dumps({"event": "execution_archived", "query": index + 1, "records": partition["records"],
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
                    code = str(exc) if isinstance(exc, a.ArchiveError) else "execution_download_failed"
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
                    error = "unreconciled_execution_request"
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
                print(json.dumps({"event": "execution_result", "query": index + 1,
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
                            if a.add_cost(prior, attempted, fresh, *quotes[index + 1:]) > ceiling:
                                raise a.ArchiveError("execution_requote_budget_exceeded")
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
                    download_errors.append(str(exc) if isinstance(exc, a.ArchiveError) else "execution_parallel_stopped")
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
        code = str(exc) if isinstance(exc, a.ArchiveError) else "execution_collection_stopped"
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
    global DATA_TIMEOUT_SECONDS
    parser = a.SafeParser(description=__doc__)
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--download-workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--data-timeout-seconds", type=int, choices=(60, 180), default=180)
    parser.add_argument("--continue-transport-errors", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    key, client = "", None
    try:
        DATA_TIMEOUT_SECONDS = args.data_timeout_seconds
        design = load_design(STAGE / "rolls-v2.json")
        _, amendment_sha = frozen_json(STAGE / "settlement-amendment-v2.json")
        if design["rolls"]["amendment_sha256"] != amendment_sha:
            raise a.ArchiveError("execution_amendment_mismatch")
        mapping_path = STAGE / "symbology/20260910T130820097627Z/mapping.json"
        mapping_raw = mapping_path.read_bytes()
        plan = make_plan(design, a.load_json(mapping_raw))
        plan["mapping"] = {"path": str(mapping_path), "sha256": hashlib.sha256(mapping_raw).hexdigest()}
        plan_path = a.ROOT / "research/ba012-profitability/execution-query-plan-v1.json"
        plan_raw = (json.dumps(plan, sort_keys=True, indent=2) + "\n").encode()
        if plan_path.exists():
            if plan_path.read_bytes() != plan_raw:
                raise a.ArchiveError("execution_plan_changed")
        else:
            with plan_path.open("xb") as out:
                out.write(plan_raw)
            plan_path.chmod(0o444)
        print(json.dumps({"plan": str(plan_path), "sha256": hashlib.sha256(plan_raw).hexdigest(), "queries": len(plan["queries"])}), flush=True)
        if args.plan_only:
            return 0
        if not sys.stdin.isatty():
            raise a.ArchiveError("interactive_hidden_credential_required")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("Databento key (hidden; quote only unless --acquire): ").strip()
        if not re.fullmatch(r"db-[A-Za-z0-9_-]{20,80}", key):
            raise a.ArchiveError("invalid_credential_format")
        client = Client(key, plan["queries"])
        key = ""
        folder, manifest = run(client, plan, args.acquire, quote_workers=6,
            download_workers=args.download_workers, continue_transport_errors=args.continue_transport_errors)
        print(json.dumps({"status": manifest["status"], "manifest": str(folder / "manifest.json"),
            "aggregate_prior_estimate_usd": manifest["aggregate_prior_estimate_usd"],
            "remaining_quote_usd": manifest.get("remaining_quote_usd"), "failure": manifest.get("failure")}))
        return 0 if manifest["status"] in ("complete", "quoted_affordable") else 1
    except BaseException as exc:
        print(json.dumps({"status": "failed", "failure": str(exc) if isinstance(exc, a.ArchiveError) else "execution_helper_stopped"}), file=sys.stderr)
        return 1
    finally:
        key = ""
        if client is not None:
            client._key = client._auth = ""


if __name__ == "__main__":
    raise SystemExit(main())
