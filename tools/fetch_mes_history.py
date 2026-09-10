#!/usr/bin/env python3
"""Archive only MES.v.0 one-minute bars for calendar 2021 through 2025.

Run interactively; the API key is accepted only through a hidden prompt. Every
annual request is counted and quoted before data access, then quoted again just
before its sole attempt. The $10 exact-decimal estimate budget includes failed
attempts and previous runs in this archive root. Quotes are estimates, not a
provider-enforced billing limit. There is no retry, live endpoint, or account API.

Protocol references (reviewed 2026-09-09):
https://databento.com/docs/standards-and-conventions/symbology
https://databento.com/docs/api-reference-historical/basics/authentication?historical=http
https://raw.githubusercontent.com/databento/databento-python/main/databento/historical/api/metadata.py
https://raw.githubusercontent.com/databento/databento-python/main/databento/historical/api/symbology.py
https://raw.githubusercontent.com/databento/dbn/main/rust/dbn/src/enums.rs
"""
from __future__ import annotations

import argparse
import base64
from bisect import bisect_right
from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException, localcontext
import getpass
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_market_data import _CONTEXT

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "data/futures/databento-history"
HOST = "https://hist.databento.com/v0/"
SCHEMA = "databento-mes-history-archive-v1"
CEILING = Decimal("10")
DATASET, SYMBOL = "GLBX.MDP3", "MES.v.0"
START, END = "2021-01-01", "2026-01-01"
MINUTE_NS = 60 * 10**9
MAX_METADATA_BYTES = 2_000_000
MAX_LINE_BYTES = 2048
MAX_ANNUAL_BYTES = 400_000_000
MAX_INSTRUMENTS = 512
BASE = {"dataset": DATASET, "symbols": SYMBOL, "stype_in": "continuous", "schema": "ohlcv-1m"}
ANNUAL = tuple(BASE | {"start": f"{year}-01-01", "end": f"{year+1}-01-01"} for year in range(2021, 2026))
FORWARD = {"dataset": DATASET, "symbols": SYMBOL, "stype_in": "continuous",
           "stype_out": "instrument_id", "start_date": START, "end_date": END}
ENCODING = {"stype_out": "instrument_id", "encoding": "json", "compression": "none",
            "pretty_px": "false", "pretty_ts": "false", "map_symbols": "false"}


class ArchiveError(Exception):
    """Only fixed, non-sensitive codes may be used as error messages."""


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def stamp_ns(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()) * 10**9


def strict_integer(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,20}", value):
        return int(value)
    raise ArchiveError("invalid_integer")


def decimal_cost(raw):
    try:
        if not isinstance(raw, bytes) or len(raw) > 128:
            raise ValueError
        value = json.loads(raw, parse_int=Decimal, parse_float=Decimal)
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError
        if not -100 <= value.as_tuple().exponent <= 100:
            raise ValueError
        return value
    except (ValueError, TypeError, DecimalException):
        raise ArchiveError("invalid_quote") from None


def add_cost(*values):
    # Avoid rounding a quote infinitesimally above the ceiling down to $10.
    with localcontext() as context:
        context.prec = 256
        return sum(values, Decimal("0"))


def annual_max_records(query):
    return (date.fromisoformat(query["end"]) - date.fromisoformat(query["start"])).days * 1440


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    """A finite request allowlist, extended only by validated MES metadata."""

    def __init__(self, key):
        self._key = key
        self._auth = "Basic " + base64.b64encode((key + ":").encode()).decode()
        self.requests = []
        self.bounds = {}
        self.reverse_query = None

    def bind_count(self, query, count):
        if query not in ANNUAL or type(count) is not int or not 0 < count <= annual_max_records(query):
            raise ArchiveError("invalid_record_count")
        self.bounds[query["start"]] = count

    def bind_reverse(self, mapping):
        ids = sorted({row["s"] for row in mapping["result"][SYMBOL]}, key=int)
        if not 0 < len(ids) <= MAX_INSTRUMENTS:
            raise ArchiveError("invalid_instrument_count")
        self.reverse_query = FORWARD | {"symbols": ",".join(ids), "stype_in": "instrument_id", "stype_out": "raw_symbol"}
        return self.reverse_query

    def allowed(self, method, params):
        if method == "symbology.resolve":
            return params == FORWARD or self.reverse_query is not None and params == self.reverse_query
        if method in ("metadata.get_cost", "metadata.get_record_count") and params in ANNUAL:
            return True
        for query in ANNUAL:
            count = self.bounds.get(query["start"])
            if count is None:
                continue
            bounded = query | {"limit": count + 1}
            if method == "metadata.get_cost" and params == bounded:
                return True
            if method == "timeseries.get_range" and params == bounded | ENCODING:
                return True
        return False

    def open(self, method, params):
        if not self.allowed(method, params):
            raise ArchiveError("request_outside_fixed_archive")
        meta = {"method": method, "query": dict(params), "requested_at": utcnow(), "result": "attempting"}
        self.requests.append(meta)
        request = urllib.request.Request(HOST + method, method="POST",
            data=urllib.parse.urlencode(params).encode(), headers={"Authorization": self._auth,
            "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
            "Accept-Encoding": "identity", "User-Agent": "BoringAlpha-MESArchive/1"})
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=_CONTEXT))
        try:
            response = opener.open(request, timeout=60)
            meta["http_status"] = response.code
            if response.code != 200:
                response.close()
                raise ArchiveError("http_error")
            encoding = response.headers.get("Content-Encoding", "identity").lower()
            if encoding not in ("identity", ""):
                response.close()
                raise ArchiveError("unexpected_http_compression")
            return meta, response
        except urllib.error.HTTPError as exc:
            # Never read, print, or archive arbitrary error/account response bodies.
            meta.update(http_status=exc.code, result="http_error", received_at=utcnow())
            exc.close()
            raise ArchiveError("http_error") from None
        except ArchiveError as exc:
            meta.update(result=str(exc), received_at=utcnow())
            raise
        except Exception:
            meta.update(result="transport_error", received_at=utcnow())
            raise ArchiveError("transport_error") from None

    def contains_secret(self, raw):
        return self._key.encode() in raw or self._auth.encode() in raw

    def metadata(self, method, params):
        meta, response = self.open(method, params)
        try:
            with response:
                raw = response.read(MAX_METADATA_BYTES + 1)
            if len(raw) > MAX_METADATA_BYTES or self.contains_secret(raw):
                raise ArchiveError("unsafe_or_oversized_metadata")
            meta.update(result="ok", received_at=utcnow(), response_bytes=len(raw),
                        response_sha256=hashlib.sha256(raw).hexdigest())
            return raw
        except ArchiveError as exc:
            meta.update(result=str(exc), received_at=utcnow())
            raise
        except Exception:
            meta.update(result="transport_error", received_at=utcnow())
            raise ArchiveError("transport_error") from None


def validate_mapping(raw, query):
    """Retain only the documented schema; provider extras never enter manifests."""
    try:
        payload = json.loads(raw)
        symbols = query["symbols"].split(",")
        result = payload["result"]
        if not isinstance(result, dict) or set(result) != set(symbols):
            raise ValueError
        clean = {name: payload[name] for name in ("stype_in", "stype_out", "start_date", "end_date")}
        if clean != {name: query[name] for name in clean} or payload["symbols"] != symbols:
            raise ValueError
        if type(payload["status"]) is not int or payload["status"] not in (0, 1):
            raise ValueError
        if payload["not_found"] or not isinstance(payload["partial"], list) or not set(payload["partial"]) <= set(symbols):
            raise ValueError
        clean.update(symbols=symbols, status=payload["status"], partial=payload["partial"], not_found=[], result={})
        for symbol in symbols:
            intervals = result[symbol]
            if not isinstance(intervals, list) or not 0 < len(intervals) <= 5000:
                raise ValueError
            rows = []
            previous = START
            for row in intervals:
                d0, d1, output = row["d0"], row["d1"], row["s"]
                if date.fromisoformat(d0).isoformat() != d0 or date.fromisoformat(d1).isoformat() != d1:
                    raise ValueError
                if not START <= d0 < d1 <= END or d0 < previous:
                    raise ValueError
                if query["stype_out"] == "instrument_id":
                    if not isinstance(output, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", output):
                        raise ValueError
                    if strict_integer(output) >= 2**32 or d0 != previous:
                        raise ValueError
                elif not isinstance(output, str) or not re.fullmatch(r"[A-Za-z0-9 ./_:+-]{1,80}", output):
                    raise ValueError
                rows.append({"d0": d0, "d1": d1, "s": output})
                previous = d1
            if query["stype_out"] == "instrument_id" and previous != END:
                raise ValueError
            clean["result"][symbol] = rows
        return clean
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ArchiveError("invalid_symbology") from None


def resolve_intervals(forward, reverse):
    """Check raw MES contract coverage over every selected continuous interval."""
    resolved = []
    for row in forward["result"][SYMBOL]:
        cursor = row["d0"]
        for native in reverse["result"][row["s"]]:
            left, right = max(row["d0"], native["d0"]), min(row["d1"], native["d1"])
            if left >= right:
                continue
            if left != cursor or not re.fullmatch(r"MES[HMUZ][0-9]{1,2}", native["s"]):
                raise ArchiveError("incomplete_mes_contract_mapping")
            resolved.append({"d0": left, "d1": right, "instrument_id": int(row["s"]), "raw_symbol": native["s"]})
            cursor = right
        if cursor != row["d1"]:
            raise ArchiveError("incomplete_mes_contract_mapping")
    return resolved


def validate_bar(raw, query, intervals, starts, previous):
    try:
        item = json.loads(raw)
        if set(item) != {"hd", "open", "high", "low", "close", "volume"}:
            raise ValueError
        hd = item["hd"]
        if set(hd) != {"ts_event", "rtype", "publisher_id", "instrument_id"}:
            raise ValueError
        stamp, instrument = strict_integer(hd["ts_event"]), strict_integer(hd["instrument_id"])
        if strict_integer(hd["rtype"]) != 33 or not 0 < strict_integer(hd["publisher_id"]) < 65536:
            raise ValueError
        if not stamp_ns(query["start"]) <= stamp < stamp_ns(query["end"]) or stamp % MINUTE_NS or stamp <= previous:
            raise ValueError
        index = bisect_right(starts, stamp) - 1
        if index < 0 or stamp >= stamp_ns(intervals[index]["d1"]) or instrument != intervals[index]["instrument_id"]:
            raise ValueError
        prices = [strict_integer(item[field]) for field in ("open", "high", "low", "close")]
        opening, high, low, close = prices
        if any(price <= 0 or price >= 2**63 or price % 250_000_000 for price in prices):
            raise ValueError
        if not low <= min(opening, close) <= max(opening, close) <= high or not 0 < strict_integer(item["volume"]) < 2**64:
            raise ValueError
        return stamp
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ArchiveError("invalid_bar_record") from None


def download_partition(client, query, expected, destination, intervals):
    params = query | {"limit": expected + 1} | ENCODING
    maximum = min(MAX_ANNUAL_BYTES, expected * MAX_LINE_BYTES)
    starts = [stamp_ns(row["d0"]) for row in intervals]
    partial = destination.with_suffix(destination.suffix + ".partial")
    meta, response = client.open("timeseries.get_range", params)
    count, size, previous = 0, 0, -1
    digest = hashlib.sha256()
    try:
        with response, partial.open("xb") as output:
            length = response.headers.get("Content-Length")
            if length is not None and (not re.fullmatch(r"[0-9]{1,12}", length) or int(length) > maximum):
                raise ArchiveError("oversized_data_response")
            with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as compressed:
                while True:
                    raw = response.readline(MAX_LINE_BYTES + 1)
                    if not raw:
                        break
                    size += len(raw)
                    count += 1
                    if size > maximum or len(raw) > MAX_LINE_BYTES or count > expected:
                        raise ArchiveError("data_exceeds_expected_bounds")
                    if client.contains_secret(raw):
                        raise ArchiveError("unsafe_data_response")
                    previous = validate_bar(raw, query, intervals, starts, previous)
                    digest.update(raw)
                    compressed.write(raw)
                    if count % 100_000 == 0:
                        print(json.dumps({"year": query["start"][:4], "records": count, "bytes": size}), flush=True)
            output.flush()
            os.fsync(output.fileno())
        if count != expected:
            raise ArchiveError("record_count_mismatch")
        # Link, then unlink, provides no-overwrite publication on the same disk.
        os.link(partial, destination)
        partial.unlink()
        destination.chmod(0o444)
        gzip_digest = hashlib.sha256()
        with destination.open("rb") as archived:
            for chunk in iter(lambda: archived.read(1024 * 1024), b""):
                gzip_digest.update(chunk)
        meta.update(result="ok", received_at=utcnow(), response_bytes=size, response_sha256=digest.hexdigest())
        return {"file": destination.name, "downloaded_records": count, "raw_bytes": size,
                "raw_sha256": digest.hexdigest(), "gzip_bytes": destination.stat().st_size,
                "gzip_sha256": gzip_digest.hexdigest(), "request": params}
    except BaseException as exc:
        partial.unlink(missing_ok=True)
        code = str(exc) if isinstance(exc, ArchiveError) else "download_interrupted" if isinstance(exc, KeyboardInterrupt) else "download_error"
        meta.update(result=code, received_at=utcnow(), response_bytes=size, observed_records=count)
        raise ArchiveError(code) from None


def save_manifest(folder, manifest, final=False):
    temporary = folder / "manifest.json.tmp"
    with temporary.open("w") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(folder / "manifest.json")
    if final:
        (folder / "manifest.json").chmod(0o444)


def previous_attempt_cost(output_root):
    total = Decimal("0")
    for folder in output_root.iterdir():
        if not folder.is_dir():
            continue
        try:
            manifest = json.loads((folder / "manifest.json").read_bytes())
            if manifest["schema"] != SCHEMA:
                raise ValueError
            value = manifest["quote_attempted_total_usd"]
            if not isinstance(value, str):
                raise ValueError
            total = add_cost(total, decimal_cost(value.encode()))
        except (OSError, ValueError, KeyError, TypeError, ArchiveError):
            raise ArchiveError("unverifiable_prior_archive_budget") from None
    return total


def run_archive(client, output_root=OUTPUT_ROOT):
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    lock = output_root / ".download.lock"
    try:
        lock.open("x").close()
    except FileExistsError:
        raise ArchiveError("archive_already_locked") from None
    folder = None
    manifest = None
    try:
        prior = previous_attempt_cost(output_root)
        folder = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder.mkdir(exist_ok=False)
        manifest = {"schema": SCHEMA, "status": "preflight", "started_at": utcnow(),
                    "dataset": DATASET, "symbol": SYMBOL, "bar_schema": "ohlcv-1m", "start": START, "end": END,
                    "quote_ceiling_usd": str(CEILING), "prior_attempted_total_usd": str(prior),
                    "quote_attempted_total_usd": "0", "requests": client.requests, "partitions": [],
                    "pricing_note": "Quotes are estimates; actual account billing was not queried.",
                    "raw_encoding": "JSON lines; integer nanosecond timestamps and prices scaled by 1e-9; instrument IDs retained"}
        save_manifest(folder, manifest)
        forward = validate_mapping(client.metadata("symbology.resolve", FORWARD), FORWARD)
        reverse_query = client.bind_reverse(forward)
        reverse = validate_mapping(client.metadata("symbology.resolve", reverse_query), reverse_query)
        intervals = resolve_intervals(forward, reverse)
        manifest["symbology"] = {"continuous_to_instrument_id": forward, "instrument_id_to_raw_symbol": reverse,
                                 "resolved_contract_intervals": intervals}
        quotes = []
        for query in ANNUAL:
            count = strict_integer(json.loads(client.metadata("metadata.get_record_count", query)))
            client.bind_count(query, count)
            quote = decimal_cost(client.metadata("metadata.get_cost", query))
            quotes.append(quote)
            manifest["partitions"].append({"year": int(query["start"][:4]), "query": query,
                "expected_records": count, "preflight_quote_usd": str(quote), "status": "quoted"})
            print(json.dumps({"year": query["start"][:4], "expected_records": count, "quote_usd": str(quote)}), flush=True)
        initial_total = add_cost(*quotes)
        manifest["preflight_total_usd"] = str(initial_total)
        save_manifest(folder, manifest)
        if add_cost(prior, initial_total) > CEILING:
            raise ArchiveError("preflight_budget_exceeded")
        manifest["status"] = "downloading"
        attempted = Decimal("0")
        for index, partition in enumerate(manifest["partitions"]):
            query, expected = partition["query"], partition["expected_records"]
            fresh = decimal_cost(client.metadata("metadata.get_cost", query | {"limit": expected + 1}))
            partition["fresh_quote_usd"] = str(fresh)
            # Include quoted remaining work so price changes cannot create a partial
            # archive when the revised projected aggregate already exceeds the cap.
            projected = add_cost(prior, attempted, fresh, *quotes[index + 1:])
            if projected > CEILING:
                raise ArchiveError("fresh_quote_budget_exceeded")
            attempted = add_cost(attempted, fresh)
            partition["status"] = "attempting"
            manifest["quote_attempted_total_usd"] = str(attempted)
            manifest["aggregate_attempted_total_usd"] = str(add_cost(prior, attempted))
            # Reserve the entire quote durably BEFORE the potentially paid request.
            save_manifest(folder, manifest)
            destination = folder / f"mes-v0-{partition['year']}-ohlcv-1m.jsonl.gz"
            partition.update(download_partition(client, query, expected, destination, intervals), status="complete")
            save_manifest(folder, manifest)
            print(json.dumps({"year": partition["year"], "records": partition["downloaded_records"],
                  "bytes": partition["raw_bytes"], "attempted_quote_total_usd": str(attempted)}), flush=True)
        manifest["status"] = "complete"
    except BaseException as exc:
        if manifest is None:
            if isinstance(exc, ArchiveError):
                raise
            raise ArchiveError("archive_setup_error") from None
        manifest["status"] = "failed"
        manifest["failure"] = str(exc) if isinstance(exc, ArchiveError) else "interrupted" if isinstance(exc, KeyboardInterrupt) else "archive_error"
    finally:
        if manifest is not None:
            manifest["completed_at"] = utcnow()
            save_manifest(folder, manifest, final=True)
        lock.unlink()
    return folder, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Use an interactive terminal for hidden credential entry")
    key = getpass.getpass("Databento API key (hidden): ").strip()
    if not re.fullmatch(r"db-[A-Za-z0-9_-]{20,80}", key):
        parser.error("Unexpected key format; contents omitted")
    client = Client(key)
    key = ""
    try:
        folder, manifest = run_archive(client)
        print(json.dumps({"status": manifest["status"], "manifest": str(folder / "manifest.json"),
                          "attempted_quote_total_usd": manifest["quote_attempted_total_usd"],
                          "failure": manifest.get("failure")}), flush=True)
        return 0 if manifest["status"] == "complete" else 1
    except ArchiveError as exc:
        print(json.dumps({"status": "failed", "failure": str(exc)}), file=sys.stderr)
        return 1
    finally:
        client._key = client._auth = ""


if __name__ == "__main__":
    raise SystemExit(main())
