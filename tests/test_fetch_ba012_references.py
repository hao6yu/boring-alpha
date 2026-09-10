"""Offline checks for fixed query boundaries, credential handling and spending gates."""
import copy
from decimal import Decimal
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

SPEC = importlib.util.spec_from_file_location("fetch_ba012_references", Path(__file__).parents[1] / "tools/fetch_ba012_references.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
KEY = "db-offline-synthetic-key-never-send-to-network"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Collector tests must not access a provider")
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(m, "METADATA_LIMITER", SimpleNamespace(wait=lambda: None, defer=lambda seconds: None))


def quote_document():
    return {"schema": "ba012-input-metadata-quote-v1", "protocol_sha256": m.PROTOCOL_SHA256,
        "complete_quote": True, "data_downloads": 0, "strategy_returns_calculated": False,
        "expected_requests": len(m.REFERENCES), "successful_quotes": len(m.REFERENCES),
        "successful_quote_sum_usd": str(Decimal("0.2") * len(m.REFERENCES)),
        "requests": [{"query": dict(query), "method": "metadata.get_cost", "status": "ok",
            "http_status": 200, "value": "0.2", "response_sha256": "1" * 64} for query in m.REFERENCES]}


@pytest.fixture
def small_plan(monkeypatch):
    monkeypatch.setattr(m, "REFERENCES", m.REFERENCES[:2])
    return {"sha256": "2" * 64, "costs": (Decimal("0.2"), Decimal("0.2"))}


def bar(query, instrument=123, **changes):
    item = {"hd": {"ts_event": str(m.stamp_ns(query["start"])), "rtype": 33,
        "publisher_id": 1, "instrument_id": instrument}, "open": "120000000000",
        "high": "121000000000", "low": "119000000000", "close": "120500000000", "volume": "5"}
    item.update(changes)
    return json.dumps(item).encode() + b"\n"


class Response(io.BytesIO):
    def __init__(self, raw, headers=None):
        super().__init__(raw)
        self.code = 200
        self.headers = headers or {}


class FakeClient(m.Client):
    def __init__(self, *, cost=b"0.2", count=b"2", data=None):
        super().__init__(KEY)
        self.cost, self.count, self.data = cost, count, data

    def open(self, method, params):
        assert self.allowed(method, params)
        meta = {"method": method, "query": dict(params), "result": "attempting", "http_status": 200}
        self.requests.append(meta)
        if method == "metadata.get_cost":
            raw = self.cost
        elif method == "metadata.get_record_count":
            raw = self.count
        else:
            raw = self.data(params) if self.data else bar(params)
        return meta, Response(raw)


def paid(client):
    return [row for row in client.requests if row["method"] == "timeseries.get_range"]


def test_reference_queries_are_only_weekday_minutes_before_holdout_and_handle_dst():
    assert len(m.REFERENCES) == 2080
    local = [m.datetime.fromisoformat(q["start"]).astimezone(__import__("zoneinfo").ZoneInfo("America/Chicago")) for q in m.REFERENCES]
    assert local[0].isoformat() == "2016-01-11T09:59:00-06:00"
    assert local[-1].date().isoformat() == "2023-12-29"
    assert all(day.weekday() < 5 and (day.hour, day.minute) == (9, 59) for day in local)
    starts = {q["start"] for q in m.REFERENCES}
    assert "2016-03-11T15:59:00+00:00" in starts
    assert "2016-03-14T14:59:00+00:00" in starts


@pytest.mark.parametrize("mutation", [
    lambda doc: doc.update(complete_quote=False),
    lambda doc: doc["requests"].pop(),
    lambda doc: doc["requests"].__setitem__(0, copy.deepcopy(doc["requests"][1])),
    lambda doc: doc["requests"][0]["query"].update(end="2026-01-01"),
    lambda doc: doc["requests"][0]["query"].update(symbols="ES.FUT"),
    lambda doc: doc["requests"][0].update(status="http_error"),
    lambda doc: doc.update(successful_quote_sum_usd="0"),
    lambda doc: doc["requests"][0].update(value="NaN"),
])
def test_saved_quote_requires_exact_full_coverage(tmp_path, mutation):
    document = quote_document()
    mutation(document)
    path = tmp_path / "quote.json"
    path.write_text(json.dumps(document))
    with pytest.raises(m.ArchiveError, match="incomplete_or_invalid_exact_quote"):
        m.load_quote(path)


def test_valid_complete_quote_and_default_cli_are_offline(tmp_path, monkeypatch, capsys):
    path = tmp_path / "quote.json"
    raw = json.dumps(quote_document()).encode()
    path.write_bytes(raw)
    quote = m.load_quote(path)
    assert quote["sha256"] == hashlib.sha256(raw).hexdigest()
    assert len(quote["costs"]) == 2080
    # CLI defaults point at the real archive root; isolate its ledger lookup too.
    monkeypatch.setattr(m, "prior_state", lambda output_root: (Decimal(0), set()))
    monkeypatch.setattr(m.sys, "argv", ["collector", "--quote", str(path), "--max-estimate-usd", "500"])
    monkeypatch.setattr(m.getpass, "getpass", lambda *args: pytest.fail("Offline preflight must not ask for credentials"))
    assert m.main() == 0
    assert json.loads(capsys.readouterr().out)["data_downloads"] == 0


def test_success_archive_preserves_raw_ids_and_bytes_and_resume_does_not_repurchase(tmp_path, small_plan):
    client = FakeClient()
    folder, report = m.run_archive(client, small_plan, Decimal("0.4"), tmp_path)
    assert report["status"] == "complete"
    assert report["quote_attempted_total_usd"] == "0.4"
    assert len(paid(client)) == 2
    for partition, query in zip(report["partitions"], m.REFERENCES):
        archive = folder / partition["file"]
        assert gzip.decompress(archive.read_bytes()) == bar(query)
        assert partition["records"] == 1 < partition["record_count_upper_bound"] == 2
        assert partition["raw_sha256"] == hashlib.sha256(bar(query)).hexdigest()
        assert partition["instrument_ids"] == [123]
    resumed = FakeClient()
    _, second = m.run_archive(resumed, small_plan, Decimal("0.4"), tmp_path)
    assert second["status"] == "complete" and second["quote_attempted_total_usd"] == "0"
    assert resumed.requests == []
    assert m.prior_state(tmp_path)[0] == Decimal("0.4")


def test_reservation_exists_before_data_failure_and_next_run_counts_it(tmp_path, small_plan):
    def fail_data(params):
        reports = [json.loads(path.read_bytes()) for path in tmp_path.glob("*/manifest.json")]
        assert len(reports) == 1
        assert reports[0]["quote_attempted_total_usd"] == "0.2"
        assert reports[0]["reservations"][0]["query"] == m.REFERENCES[0]
        raise RuntimeError("provider-private-details-should-never-appear")
    first = FakeClient(data=fail_data)
    folder, report = m.run_archive(first, small_plan, Decimal("0.4"), tmp_path)
    assert report["status"] == "failed" and len(paid(first)) == 1
    assert "provider-private" not in (folder / "manifest.json").read_text()
    second = FakeClient()
    with pytest.raises(m.ArchiveError, match="budget_exceeded"):
        m.run_archive(second, small_plan, Decimal("0.4"), tmp_path)
    assert second.requests == [] and m.prior_state(tmp_path)[0] == Decimal("0.2")


def test_resume_skips_successful_date_but_counts_later_failed_attempt(tmp_path, small_plan):
    def fail_second(params):
        if params["start"] == m.REFERENCES[1]["start"]:
            raise RuntimeError("synthetic failure")
        return bar(params)
    _, first = m.run_archive(FakeClient(data=fail_second), small_plan, Decimal("0.4"), tmp_path)
    assert first["status"] == "failed"
    resumed = FakeClient()
    _, second = m.run_archive(resumed, small_plan, Decimal("0.6"), tmp_path)
    assert second["status"] == "complete"
    assert len(paid(resumed)) == 1 and paid(resumed)[0]["query"]["start"] == m.REFERENCES[1]["start"]
    assert m.prior_state(tmp_path)[0] == Decimal("0.6")


@pytest.mark.parametrize("cost", [b"0.200000000000000000000000000000000001", b"NaN", b"-1", b"{\"private\":1}"])
def test_fresh_cost_or_invalid_metadata_stops_before_data(tmp_path, small_plan, cost):
    client = FakeClient(cost=cost)
    _, report = m.run_archive(client, small_plan, Decimal("0.4"), tmp_path)
    assert report["status"] == "failed" and paid(client) == []
    assert report["quote_attempted_total_usd"] == "0"


@pytest.mark.parametrize("change", [
    {"volume": "0"}, {"open": "120.5"}, {"close": True}, {"high": str(2**63 - 1)},
    {"low": str(-(2**63) - 1)}, {"low": "122000000000"}, {"private": KEY},
])
def test_invalid_raw_record_rejected_without_archive(tmp_path, small_plan, change):
    client = FakeClient(data=lambda query: bar(query, **change))
    folder, report = m.run_archive(client, small_plan, Decimal("0.4"), tmp_path)
    assert report["status"] == "failed" and len(paid(client)) == 1
    assert not list(folder.glob("*.gz")) and not list(folder.glob("*.partial"))
    assert KEY not in (folder / "manifest.json").read_text()


def test_negative_zero_spread_prices_valid_and_empty_response_does_not_claim_coverage(tmp_path, small_plan):
    client = FakeClient(data=lambda q: bar(q, open="-10", high="0", low="-20", close="0"))
    _, report = m.run_archive(client, small_plan, Decimal("0.4"), tmp_path)
    assert report["status"] == "complete"
    empty_root = tmp_path / "separate-empty-test"
    _, empty = m.run_archive(FakeClient(data=lambda q: b""), small_plan, Decimal("0.4"), empty_root)
    assert empty["status"] == "complete"
    assert all(p["records"] == 0 and p["instrument_ids"] == [] for p in empty["partitions"])


@pytest.mark.parametrize("kind", ["wrong_minute", "duplicate_id", "too_many"])
def test_wrong_timestamp_duplicate_or_excess_records_fail(tmp_path, small_plan, kind):
    def payload(query):
        if kind == "wrong_minute":
            item = json.loads(bar(query))
            item["hd"]["ts_event"] = str(m.stamp_ns(query["start"]) + 60 * 10**9)
            return json.dumps(item).encode()
        if kind == "duplicate_id":
            return bar(query) * 2
        return b"".join(bar(query, instrument=n) for n in (1, 2, 3))
    _, report = m.run_archive(FakeClient(data=payload), small_plan, Decimal("0.4"), tmp_path)
    assert report["status"] == "failed"


@pytest.mark.parametrize("tamper", ["hash", "orphan", "ledger", "missing_reservation", "duplicate_attempt"])
def test_bad_prior_archive_blocks_all_further_requests(tmp_path, small_plan, tamper):
    folder, report = m.run_archive(FakeClient(), small_plan, Decimal("0.4"), tmp_path)
    if tamper == "hash":
        path = folder / report["partitions"][0]["file"]
        path.chmod(0o644)
        path.write_bytes(b"bad archive")
    elif tamper == "orphan":
        (folder / "orphan.jsonl.gz").write_bytes(b"unaccounted")
    elif tamper == "ledger":
        report["quote_attempted_total_usd"] = "0"
        m.persist(folder, report)
    elif tamper == "missing_reservation":
        report["reservations"] = []
        report["quote_attempted_total_usd"] = "0"
        m.persist(folder, report)
    else:
        report["requests"].append(copy.deepcopy(next(r for r in report["requests"] if r["method"] == "timeseries.get_range")))
        m.persist(folder, report)
    client = FakeClient()
    with pytest.raises(m.ArchiveError, match="unverifiable_prior_reference_budget"):
        m.run_archive(client, small_plan, Decimal("5"), tmp_path)
    assert client.requests == []


def test_attempting_partition_without_reservation_is_not_zero_cost(tmp_path, small_plan):
    def fail(params):
        raise RuntimeError("uncertain request")
    folder, report = m.run_archive(FakeClient(data=fail), small_plan, Decimal("0.4"), tmp_path)
    report["requests"] = []
    report["reservations"] = []
    report["quote_attempted_total_usd"] = "0"
    m.persist(folder, report)
    with pytest.raises(m.ArchiveError, match="unverifiable_prior_reference_budget"):
        m.preflight(small_plan, Decimal("5"), tmp_path)


def test_lock_and_fixed_allowlist_prevent_concurrent_or_expanded_requests(tmp_path, small_plan):
    (tmp_path / ".download.lock").touch()
    client = FakeClient()
    with pytest.raises(m.ArchiveError, match="reference_archive_locked"):
        m.run_archive(client, small_plan, Decimal("5"), tmp_path)
    assert client.requests == []
    real = m.Client(KEY)
    for method in ("account.list", "live.subscribe", "symbology.resolve", "timeseries.get_range"):
        assert not real.allowed(method, m.REFERENCES[0])
    for mutation in ({"end": "2025-01-01"}, {"schema": "mbp-1"}, {"symbols": "MES.FUT"}, {"limit": 1}):
        assert not real.allowed("timeseries.get_range", m.REFERENCES[0] | m.ENCODING | mutation)


def test_http_error_body_not_read_and_redirects_disabled(monkeypatch, small_plan):
    import fetch_mes_history as transport
    class PrivateBody(io.BytesIO):
        def read(self, *args):
            pytest.fail("HTTP error bodies must not be read")
    def fail(request, **kwargs):
        assert request.full_url == "https://hist.databento.com/v0/metadata.get_cost?" + urllib.parse.urlencode(m.REFERENCES[0])
        assert request.get_method() == "GET" and request.data is None
        assert kwargs["timeout"] == 20
        raise urllib.error.HTTPError(request.full_url, 401, "private response", {}, PrivateBody(b"private"))
    def opener(*handlers):
        assert any(isinstance(h, transport.NoRedirect) for h in handlers)
        assert any(isinstance(h, urllib.request.HTTPSHandler) and h._context is transport._CONTEXT for h in handlers)
        return SimpleNamespace(open=fail)
    monkeypatch.setattr(urllib.request, "build_opener", opener)
    client = m.Client(KEY)
    with pytest.raises(m.ArchiveError, match="http_error"):
        client.metadata("metadata.get_cost", m.REFERENCES[0])
    assert "private" not in json.dumps(client.requests) and KEY not in json.dumps(client.requests)
    assert transport.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.org") is None


def test_parallel_reserves_before_dispatch_and_resumes_without_repurchase(tmp_path, small_plan):
    clients = []
    def payload(query):
        manifest = json.loads(next(tmp_path.glob("*/manifest.json")).read_bytes())
        assert any(row["query"] == {k: query[k] for k in m.REFERENCES[0]} for row in manifest["reservations"])
        assert Decimal(manifest["quote_attempted_total_usd"]) <= Decimal("0.4")
        return bar(query)
    def factory():
        client = FakeClient(data=payload)
        clients.append(client)
        return client
    _, report = m.run_parallel_archive(factory, small_plan, Decimal("0.4"), tmp_path, workers=2)
    assert report["status"] == "complete"
    assert len([r for r in report["requests"] if r["method"] == "timeseries.get_range"]) == 2
    assert m.prior_state(tmp_path)[0] == Decimal("0.4")
    count = len(clients)
    _, resumed = m.run_parallel_archive(factory, small_plan, Decimal("0.4"), tmp_path, workers=2)
    assert resumed["status"] == "complete" and len(clients) == count


def test_parallel_failure_drains_inflight_and_preserves_all_reservations(tmp_path, small_plan):
    def payload(query):
        if query["start"] == m.REFERENCES[0]["start"]:
            raise RuntimeError("private error must not be recorded")
        return bar(query)
    _, report = m.run_parallel_archive(lambda: FakeClient(data=payload), small_plan, Decimal("0.4"), tmp_path, workers=2)
    assert report["status"] == "failed"
    assert "private" not in json.dumps(report)
    paid_count = len([r for r in report["requests"] if r["method"] == "timeseries.get_range"])
    assert Decimal(report["quote_attempted_total_usd"]) == Decimal("0.2") * paid_count
    total, done = m.prior_state(tmp_path)
    assert total == Decimal(report["quote_attempted_total_usd"])
    _, resumed = m.run_parallel_archive(lambda: FakeClient(), small_plan, Decimal("1"), tmp_path, workers=2)
    assert resumed["status"] == "complete"
    assert len(m.prior_state(tmp_path)[1]) == 2


def test_parallel_requote_excess_blocks_data(tmp_path, small_plan):
    _, report = m.run_parallel_archive(lambda: FakeClient(cost=b"0.200000000000000000000000000000000001"),
                                     small_plan, Decimal("0.4"), tmp_path, workers=2)
    assert report["status"] == "failed"
    assert not [r for r in report["requests"] if r["method"] == "timeseries.get_range"]
    assert report["quote_attempted_total_usd"] == "0"


def test_free_metadata_retries_transient_failure_only(monkeypatch, small_plan):
    monkeypatch.setattr(m.time, "sleep", lambda seconds: None)
    class Flaky(FakeClient):
        failures = 0
        def open(self, method, params):
            if self.failures < 2:
                self.failures += 1
                self.requests.append({"method": method, "query": dict(params), "result": "transport_error"})
                raise m.ArchiveError("transport_error")
            return super().open(method, params)
    client = Flaky()
    assert client.metadata("metadata.get_cost", m.REFERENCES[0]) == b"0.2"
    assert len(client.requests) == 3 and paid(client) == []


def test_metadata_get_and_data_post_keep_distinct_transport(monkeypatch, small_plan):
    calls = []
    client = m.Client(KEY)
    def open_request(request, **kwargs):
        calls.append((request, kwargs["timeout"]))
        assert request.headers["Authorization"] == client._auth
        return Response(b"0.2" if request.get_method() == "GET" else bar(m.REFERENCES[0]))
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: SimpleNamespace(open=open_request))
    assert client.metadata("metadata.get_cost", m.REFERENCES[0]) == b"0.2"
    _, response = client.open("timeseries.get_range", m.REFERENCES[0] | m.ENCODING)
    response.close()
    get, post = calls
    assert get[0].get_method() == "GET" and get[0].data is None and get[1] == 20
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(get[0].full_url).query) == {k: [v] for k, v in m.REFERENCES[0].items()}
    assert post[0].get_method() == "POST" and post[1] == 60
    assert post[0].full_url == "https://hist.databento.com/v0/timeseries.get_range"
    assert urllib.parse.parse_qs(post[0].data.decode()) == {k: [v] for k, v in (m.REFERENCES[0] | m.ENCODING).items()}
    assert KEY not in json.dumps(client.requests) and client._auth not in json.dumps(client.requests)


@pytest.mark.parametrize("status, expected_attempts", [(401, 1), (400, 1), (302, 1), (429, 3), (500, 3), (503, 3), (None, 3)])
def test_get_metadata_failure_has_fixed_retry_bound_and_sanitized_errors(monkeypatch, small_plan, status, expected_attempts):
    sleeps, attempts = [], []
    monkeypatch.setattr(m.time, "sleep", sleeps.append)
    class PrivateBody(io.BytesIO):
        def read(self, *args):
            pytest.fail("Never read error bodies")
    def fail(request, **kwargs):
        attempts.append((request.get_method(), kwargs["timeout"]))
        if status is None:
            raise TimeoutError("private-transport-details")
        raise urllib.error.HTTPError(request.full_url, status, "private-error-details", {}, PrivateBody(b"private-body"))
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: SimpleNamespace(open=fail))
    client = m.Client(KEY)
    with pytest.raises(m.ArchiveError, match="http_error|transport_error"):
        client.metadata("metadata.get_cost", m.REFERENCES[0])
    assert attempts == [("GET", 20)] * expected_attempts
    assert sleeps == ([1, 2] if expected_attempts == 3 else [])
    assert len(client.requests) == expected_attempts
    assert "private" not in json.dumps(client.requests) and KEY not in json.dumps(client.requests)


def test_data_cannot_enter_metadata_retry_path(monkeypatch, small_plan):
    client = m.Client(KEY)
    with pytest.raises(m.ArchiveError, match="request_outside_fixed_metadata"):
        client.metadata("timeseries.get_range", m.REFERENCES[0] | m.ENCODING)
    assert client.requests == []


def test_bounded_resume_reuses_success_and_counts_failed_paid_reservation(tmp_path, small_plan, monkeypatch):
    monkeypatch.setattr(m.time, "sleep", lambda seconds: None)
    attempts = []
    class Flaky(FakeClient):
        def open(self, method, params):
            if method == "timeseries.get_range":
                attempts.append(params["start"])
                if params["start"] == m.REFERENCES[1]["start"] and len(attempts) == 2:
                    self.requests.append({"method": method, "query": dict(params), "result": "transport_error"})
                    raise m.ArchiveError("transport_error")
            return super().open(method, params)
    _, report = m.run_with_resumes(Flaky, small_plan, Decimal("0.6"), tmp_path, attempts=3)
    assert report["status"] == "complete" and report["resume"]["attempt"] == 2
    assert attempts == [m.REFERENCES[0]["start"], m.REFERENCES[1]["start"], m.REFERENCES[1]["start"]]
    assert m.prior_state(tmp_path)[0] == Decimal("0.6")
    assert len(list(tmp_path.glob("*/manifest.json"))) == 2


def test_resume_limit_and_same_aggregate_budget_both_stop_purchases(tmp_path, small_plan, monkeypatch):
    monkeypatch.setattr(m.time, "sleep", lambda seconds: None)
    class AlwaysFails(FakeClient):
        paid_count = 0
        def open(self, method, params):
            if method == "timeseries.get_range":
                AlwaysFails.paid_count += 1
                self.requests.append({"method": method, "query": dict(params), "result": "transport_error"})
                raise m.ArchiveError("transport_error")
            return super().open(method, params)
    _, report = m.run_with_resumes(AlwaysFails, small_plan, Decimal("1"), tmp_path / "bounded", attempts=3)
    assert report["status"] == "failed" and AlwaysFails.paid_count == 3
    assert m.prior_state(tmp_path / "bounded")[0] == Decimal("0.6")
    with pytest.raises(m.ArchiveError, match="budget_exceeded"):
        m.run_with_resumes(AlwaysFails, small_plan, Decimal("0.4"), tmp_path / "budget", attempts=3)
    assert AlwaysFails.paid_count == 4
    assert m.prior_state(tmp_path / "budget")[0] == Decimal("0.2")


def test_mixed_or_terminal_failures_never_auto_resume():
    report = {"status": "failed", "failure": "transport_error",
              "requests": [{"result": "transport_error"}, {"result": "ok"}],
              "task_failures": ["transport_error", "invalid_reference_record_count"]}
    assert not m.resumable_failure(report)
    report["task_failures"] = ["transport_error"]
    assert m.resumable_failure(report)
    for result, status in (("invalid_reference_bar", None), ("http_error", 401), ("reference_download_failed", None)):
        report["requests"].append({"result": result, "http_status": status})
        assert not m.resumable_failure(report)
        report["requests"].pop()
    report["requests"].append({"method": "timeseries.get_range", "result": "http_error", "http_status": 429})
    assert not m.resumable_failure(report)
    report["requests"][-1]["retry_after_seconds"] = 3
    assert m.resumable_failure(report)


def test_parallel_retains_metadata_validation_failure_even_after_transient(tmp_path, small_plan):
    class Mixed(FakeClient):
        def metadata(self, method, params):
            if params == m.REFERENCES[0]:
                self.requests.append({"method": method, "query": dict(params), "result": "transport_error"})
                raise m.ArchiveError("transport_error")
            self.requests.append({"method": method, "query": dict(params), "result": "ok"})
            return b"10001"
    _, report = m.run_parallel_archive(Mixed, small_plan, Decimal("0.4"), tmp_path, workers=2)
    assert set(report["task_failures"]) == {"transport_error", "invalid_reference_record_count"}
    assert not m.resumable_failure(report)


def test_global_metadata_limiter_is_nonbursting_and_shared_by_clients(monkeypatch, small_plan):
    class Clock:
        now = 0.0
        def read(self):
            return self.now
        def sleep(self, seconds):
            self.now += seconds
    clock = Clock()
    limiter = m.RequestStartLimiter(clock.read, clock.sleep)
    monkeypatch.setattr(m, "METADATA_LIMITER", limiter)
    starts = []
    def respond(request, **kwargs):
        starts.append(clock.now)
        return Response(b"0.2")
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: SimpleNamespace(open=respond))
    clients = [m.Client(KEY) for _ in range(16)]
    for index in range(32):
        clients[index % 16].metadata("metadata.get_cost", m.REFERENCES[0])
    assert len(starts) == 32 and starts[-1] >= 3.099999
    assert all(right - left >= .099999 for left, right in zip(starts, starts[1:]))


@pytest.mark.parametrize("header, expected_calls", [("3", 3), ("61", 1), ("bad-value", 1)])
def test_retry_after_is_respected_or_stops_bounded_retry(monkeypatch, small_plan, header, expected_calls):
    waits, calls = [], []
    monkeypatch.setattr(m.time, "sleep", waits.append)
    def fail(request, **kwargs):
        calls.append(request.get_method())
        raise urllib.error.HTTPError(request.full_url, 429, "private", {"Retry-After": header}, io.BytesIO(b"private"))
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: SimpleNamespace(open=fail))
    client = m.Client(KEY)
    with pytest.raises(m.ArchiveError, match="http_error"):
        client.metadata("metadata.get_cost", m.REFERENCES[0])
    assert len(calls) == expected_calls
    assert waits == ([3, 3] if header == "3" else [])
    if expected_calls == 1:
        assert not m.resumable_failure({"status": "failed", "failure": "http_error", "requests": client.requests})


def test_sixteen_workers_allowed_and_invalid_resume_ranges_reject(tmp_path, small_plan):
    _, report = m.run_parallel_archive(FakeClient, small_plan, Decimal("0.4"), tmp_path, workers=16)
    assert report["status"] == "complete"
    for workers in (0, 17, True):
        with pytest.raises(m.ArchiveError, match="invalid_reference_workers"):
            m.run_with_resumes(FakeClient, small_plan, Decimal("5"), tmp_path, workers=workers)
    for attempts in (0, 21, True):
        with pytest.raises(m.ArchiveError, match="invalid_resume_attempts"):
            m.run_with_resumes(FakeClient, small_plan, Decimal("5"), tmp_path, attempts=attempts)
