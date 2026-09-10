"""Offline protocol, archive integrity, and exact spending-gate regressions."""
import base64
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest


SPEC = importlib.util.spec_from_file_location("fetch_mes_history", Path(__file__).parents[1] / "tools/fetch_mes_history.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
KEY = "db-synthetic-test-key-never-use-for-network"
PRIVATE = "synthetic-account-details-never-persist"


@pytest.fixture(autouse=True)
def forbid_real_http(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Archive tests must never perform network I/O")
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)


def mapping(query):
    symbols = query["symbols"].split(",")
    return {name: query[name] for name in ("stype_in", "stype_out", "start_date", "end_date")} | {
        "symbols": symbols, "status": 0, "partial": [], "not_found": [], "message": "OK",
        "result": {symbol: [{"d0": m.START, "d1": m.END,
                    "s": "12345" if query["stype_out"] == "instrument_id" else "MESH1"}] for symbol in symbols},
        "private_account_extra": PRIVATE,
    }


def bars(query, count=2):
    return b"".join(json.dumps({"hd": {"ts_event": str(m.stamp_ns(query["start"]) + minute * m.MINUTE_NS),
        "rtype": 33, "publisher_id": 1, "instrument_id": 12345}, "open": "6000250000000",
        "high": "6001000000000", "low": "6000000000000", "close": "6000750000000", "volume": "7"}).encode() + b"\n" for minute in range(count))


class Response(io.BytesIO):
    def __init__(self, raw, headers=None):
        super().__init__(raw)
        self.headers = {} if headers is None else headers
        self.code = 200


class FakeClient(m.Client):
    def __init__(self, *, cost=b"1", fresh=b"1", count=b"2", data=None, mutate_mapping=None):
        super().__init__(KEY)
        self.cost, self.fresh, self.count, self.data = cost, fresh, count, data
        self.mutate_mapping = mutate_mapping

    def open(self, method, params):
        assert self.allowed(method, params)
        meta = {"method": method, "query": copy.deepcopy(params), "result": "attempting", "http_status": 200}
        self.requests.append(meta)
        if method == "symbology.resolve":
            payload = mapping(params)
            if self.mutate_mapping:
                self.mutate_mapping(payload)
            raw = json.dumps(payload).encode()
        elif method == "metadata.get_record_count":
            raw = self.count
        elif method == "metadata.get_cost":
            raw = self.fresh if "limit" in params else self.cost
        else:
            raw = self.data(params) if self.data else bars(params)
        return meta, Response(raw)


def paid_requests(client):
    return [row for row in client.requests if row["method"] == "timeseries.get_range"]


def test_complete_archive_preserves_raw_bytes_counts_hashes_and_fixed_queries(tmp_path):
    client = FakeClient()
    folder, report = m.run_archive(client, tmp_path)
    assert report["status"] == "complete"
    assert report["quote_attempted_total_usd"] == "5"
    assert len(paid_requests(client)) == 5
    first_paid = next(index for index, request in enumerate(client.requests) if request["method"] == "timeseries.get_range")
    assert first_paid == 13  # Two symbology, five count/quote pairs, one fresh quote.
    for row, query in zip(report["partitions"], m.ANNUAL):
        raw = bars(query)
        path = folder / row["file"]
        assert gzip.decompress(path.read_bytes()) == raw
        assert row["downloaded_records"] == row["expected_records"] == 2
        assert row["raw_sha256"] == hashlib.sha256(raw).hexdigest()
        assert row["gzip_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert row["request"] == query | {"limit": 3} | m.ENCODING
        assert path.stat().st_mode & 0o222 == 0
    assert json.loads((folder / "manifest.json").read_text()) == report
    assert KEY not in json.dumps(report) and PRIVATE not in json.dumps(report)
    assert not (tmp_path / ".download.lock").exists()


@pytest.mark.parametrize("raw", [b"", b"true", b"false", b"null", b"[]", b"{}", b'"1"', b"NaN",
    b"Infinity", b"-Infinity", b"-0.1", b"1e999", b"1e-999", b"9" * 129])
def test_invalid_cost_is_rejected(raw):
    with pytest.raises(m.ArchiveError, match="invalid_quote"):
        m.decimal_cost(raw)


@pytest.mark.parametrize("cost,fresh,failure", [
    (b"2.000000000000000000000000000001", b"1", "preflight_budget_exceeded"),
    (b"2", b"2.000000000000000000000000000001", "fresh_quote_budget_exceeded"),
    (b"1", b"7", "fresh_quote_budget_exceeded"),
    (b"1", b"NaN", "invalid_quote"),
])
def test_quotes_over_exact_aggregate_ceiling_block_all_paid_access(tmp_path, cost, fresh, failure):
    client = FakeClient(cost=cost, fresh=fresh)
    _, report = m.run_archive(client, tmp_path)
    assert report["failure"] == failure
    assert report["quote_attempted_total_usd"] == "0"
    assert not paid_requests(client)


def test_exact_ten_dollar_quote_is_allowed(tmp_path):
    _, report = m.run_archive(FakeClient(cost=b"2", fresh=b"2"), tmp_path)
    assert report["status"] == "complete"
    assert report["quote_attempted_total_usd"] == "10"


def test_failed_attempt_reserved_before_request_and_counted_on_next_run(tmp_path):
    def truncated(query):
        manifests = list(tmp_path.glob("*/manifest.json"))
        report = json.loads(manifests[0].read_text())
        assert report["quote_attempted_total_usd"] == "2"
        assert report["partitions"][0]["status"] == "attempting"
        return bars(query, 1)
    client = FakeClient(cost=b"2", fresh=b"2", data=truncated)
    folder, report = m.run_archive(client, tmp_path)
    assert report["failure"] == "record_count_mismatch"
    assert report["quote_attempted_total_usd"] == "2"
    assert len(paid_requests(client)) == 1
    assert not list(folder.glob("*.gz*"))
    subsequent = FakeClient(cost=b"2", fresh=b"2")
    _, second = m.run_archive(subsequent, tmp_path)
    assert second["prior_attempted_total_usd"] == "2"
    assert second["failure"] == "preflight_budget_exceeded"
    assert not paid_requests(subsequent)


@pytest.mark.parametrize("count", [b"0", b"-1", b"true", b"1.5", b"999999999"])
def test_bad_or_unbounded_record_count_prevents_data(tmp_path, count):
    client = FakeClient(count=count)
    _, report = m.run_archive(client, tmp_path)
    assert report["status"] == "failed"
    assert not paid_requests(client)


@pytest.mark.parametrize("kind", ["extra", "duplicate", "oversized", "secret", "wrong_instrument", "outside_time", "tick"])
def test_invalid_stream_never_publishes_archive_or_retries(tmp_path, kind):
    def corrupt(query):
        raw = bars(query)
        if kind == "extra":
            return bars(query, 3)
        if kind == "duplicate":
            return bars(query, 1) * 2
        if kind == "oversized":
            return b" " * (m.MAX_LINE_BYTES + 1)
        if kind == "secret":
            return KEY.encode() + b"\n"
        item = json.loads(raw.splitlines()[0])
        if kind == "wrong_instrument":
            item["hd"]["instrument_id"] = 876
        if kind == "outside_time":
            item["hd"]["ts_event"] = str(m.stamp_ns(query["end"]))
        if kind == "tick":
            item["open"] = "6000250000001"
        return json.dumps(item).encode() + b"\n" + raw.splitlines(keepends=True)[1]
    client = FakeClient(data=corrupt)
    folder, report = m.run_archive(client, tmp_path)
    assert report["status"] == "failed"
    assert report["quote_attempted_total_usd"] == "1"
    assert len(paid_requests(client)) == 1
    assert not list(folder.glob("*.gz*"))
    assert KEY not in (folder / "manifest.json").read_text()


def test_mapping_gaps_block_data_and_reverse_requests_are_bound_to_mes_ids(tmp_path):
    def gap(payload):
        payload["result"][payload["symbols"][0]][0]["d0"] = "2021-01-02"
    client = FakeClient(mutate_mapping=gap)
    _, report = m.run_archive(client, tmp_path)
    assert report["failure"] == "invalid_symbology"
    assert len(client.requests) == 1
    assert client.reverse_query is None
    assert not paid_requests(client)


def test_wrong_raw_symbol_mapping_blocks_paid_data(tmp_path):
    def non_mes(payload):
        if payload["stype_out"] == "raw_symbol":
            payload["result"][payload["symbols"][0]][0]["s"] = "ESH1"
    client = FakeClient(mutate_mapping=non_mes)
    _, report = m.run_archive(client, tmp_path)
    assert report["failure"] == "incomplete_mes_contract_mapping"
    assert not paid_requests(client)


def test_allowlist_rejects_host_symbol_range_schema_account_and_unbound_count():
    client = m.Client(KEY)
    assert client.allowed("symbology.resolve", m.FORWARD)
    assert client.allowed("metadata.get_cost", m.ANNUAL[0])
    assert not client.allowed("timeseries.get_range", m.ANNUAL[0] | {"limit": 3} | m.ENCODING)
    client.bind_count(m.ANNUAL[0], 2)
    allowed = m.ANNUAL[0] | {"limit": 3} | m.ENCODING
    assert client.allowed("timeseries.get_range", allowed)
    for changes in ({"symbols": "ALL_SYMBOLS"}, {"symbols": "ES.v.0"}, {"schema": "mbo"},
                    {"limit": 4}, {"limit": True}, {"end": "2027-01-01"}, {"extra": 1}):
        assert not client.allowed("timeseries.get_range", allowed | changes)
    for method in ("account.get_balance", "batch.submit_job", "https://example.invalid", "live"):
        with pytest.raises(m.ArchiveError, match="request_outside_fixed_archive"):
            client.open(method, allowed)


def test_http_errors_never_read_or_persist_body(monkeypatch):
    body = Response((KEY + PRIVATE).encode())
    def unexpected_read(*args):
        pytest.fail("HTTP error bodies must not be read")
    body.read = unexpected_read
    def failed(request, timeout):
        assert request.full_url == m.HOST + "metadata.get_cost"
        assert request.get_method() == "POST"
        assert request.get_header("Authorization") == "Basic " + base64.b64encode((KEY + ":").encode()).decode()
        raise urllib.error.HTTPError(request.full_url, 403, PRIVATE, {}, body)
    monkeypatch.setattr(m.urllib.request, "build_opener", lambda *args: SimpleNamespace(open=failed))
    client = m.Client(KEY)
    with pytest.raises(m.ArchiveError, match="http_error"):
        client.metadata("metadata.get_cost", m.ANNUAL[0])
    assert KEY not in json.dumps(client.requests) and PRIVATE not in json.dumps(client.requests)
    assert client.requests[0]["http_status"] == 403


def test_oversized_response_header_blocks_before_reading(tmp_path):
    client = FakeClient()
    original = client.open
    def opening(method, params):
        meta, response = original(method, params)
        if method == "timeseries.get_range":
            response.headers["Content-Length"] = str(m.MAX_ANNUAL_BYTES + 1)
        return meta, response
    client.open = opening
    folder, report = m.run_archive(client, tmp_path)
    assert report["failure"] == "oversized_data_response"
    assert not list(folder.glob("*.gz*"))


def test_lock_or_unverifiable_prior_archive_stops_before_network(tmp_path):
    lock = tmp_path / ".download.lock"
    lock.touch()
    client = FakeClient()
    with pytest.raises(m.ArchiveError, match="archive_already_locked"):
        m.run_archive(client, tmp_path)
    lock.unlink()
    (tmp_path / "incomplete").mkdir()
    with pytest.raises(m.ArchiveError, match="unverifiable_prior_archive_budget"):
        m.run_archive(client, tmp_path)
    assert not client.requests
    assert not lock.exists()


def test_redirects_are_disabled():
    assert m.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid") is None
