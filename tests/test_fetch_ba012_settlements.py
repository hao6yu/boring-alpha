"""Minimal offline checks of the bounded statistics helper."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import gzip
import importlib.util
import io
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import urllib.request

import pytest

SPEC = importlib.util.spec_from_file_location("ba012_settlements", Path(__file__).parents[1] / "tools/fetch_ba012_settlements.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "DEADLINE", datetime(2099, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(m.a, "prior_state", lambda root: (Decimal("0.8"), set()))
    def forbidden(*args, **kwargs):
        pytest.fail("No external requests allowed")
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    original = tmp_path / "original"
    original.mkdir()
    queries = tuple({"dataset": "GLBX.MDP3", "schema": "statistics", "stype_in": "raw_symbol",
        "symbols": symbol, "start": "2016-01-11", "end": "2024-01-01"} for symbol in ("ESH6", "TNH6"))
    return original, tmp_path / "stats", {"queries": queries}


class Response(io.BytesIO):
    headers = {}
    code = 200


RAW = b'{"hd":{"ts_event":"1","instrument_id":123},"stat_type":3,"update_action":1,"stat_flags":8,"price":"9223372036854775807"}\n'


class Fake(m.Client):
    def __init__(self, plan, cost="0.1", fail=None):
        super().__init__("db-synthetic-no-network-key", plan["queries"])
        self.cost, self.fail = Decimal(cost), fail

    def quote(self, query):
        self.requests.append({"method": "metadata.get_cost", "query": query, "result": "ok"})
        return self.cost

    def open(self, method, params):
        assert self.allowed(method, params)
        meta = {"method": method, "query": dict(params), "result": "attempting"}
        self.requests.append(meta)
        if self.fail:
            self.fail()
            meta["result"] = "transport_error"
            raise m.a.ArchiveError("transport_error")
        return meta, Response(RAW)


def test_quote_only_and_over_budget_never_download(setup):
    old, root, plan = setup
    for index, cost in enumerate(("0.1", "0.10000000000000000000000000001")):
        client = Fake(plan, cost)
        _, report = m.run(client, plan, False, root / str(index), old)
        assert report["status"] == ("quoted_affordable" if index == 0 else "quote_over_budget")
        assert not any(row["method"] == "timeseries.get_range" for row in client.requests)
        assert report["original_attempted_estimate_usd"] == "0.8"


def test_all_raw_statistics_preserved_and_reservation_precedes_failed_attempt(setup):
    old, root, plan = setup
    client = Fake(plan)
    folder, report = m.run(client, plan, True, root, old)
    assert report["status"] == "complete" and report["quote_attempted_total_usd"] == "0.2"
    assert all(gzip.decompress((folder / p["file"]).read_bytes()) == RAW for p in report["partitions"])
    assert m.statistics_prior(root)[0] == Decimal("0.2")
    resumed = Fake(plan)
    _, second = m.run(resumed, plan, True, root, old)
    assert second["status"] == "complete" and resumed.requests == []


def test_failed_data_cost_stays_charged_and_blocks_unaffordable_retry(setup):
    old, root, plan = setup
    def assert_reserved():
        saved = json.loads(next(root.glob("*/manifest.json")).read_bytes())
        assert saved["quote_attempted_total_usd"] == "0.1" and len(saved["reservations"]) == 1
    _, report = m.run(Fake(plan, fail=assert_reserved), plan, True, root, old)
    assert report["status"] == "failed"
    retry = Fake(plan)
    _, second = m.run(retry, plan, True, root, old)
    assert second["status"] == "quote_over_budget"
    assert m.statistics_prior(root)[0] == Decimal("0.1")
    assert all(row["method"] == "metadata.get_cost" for row in retry.requests)


def test_deadline_and_fixed_query_allowlist_block_network(setup, monkeypatch, tmp_path):
    _, _, plan = setup
    client = Fake(plan)
    monkeypatch.setattr(m, "DEADLINE", datetime(2000, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(m.a.ArchiveError, match="deadline"):
        m.download(client, plan["queries"][0], tmp_path / "never.gz")
    assert client.requests == []
    assert not client.allowed("account.list", plan["queries"][0])
    assert not client.allowed("timeseries.get_range", plan["queries"][0] | m.a.ENCODING | {"end": "2025-01-01"})


def test_full_timeout_margin_and_content_length_are_required(setup, monkeypatch, tmp_path):
    _, _, plan = setup
    client = Fake(plan)
    monkeypatch.setattr(m, "DEADLINE", datetime.now(timezone.utc) + timedelta(seconds=59))
    with pytest.raises(m.a.ArchiveError, match="deadline"):
        m.download(client, plan["queries"][0], tmp_path / "late.gz")
    assert client.requests == []
    monkeypatch.setattr(m, "DEADLINE", datetime(2099, 1, 1, tzinfo=timezone.utc))
    class Truncated(Fake):
        def open(self, method, params):
            meta, response = super().open(method, params)
            response.headers = {"Content-Length": str(len(RAW) + 100)}
            return meta, response
    with pytest.raises(m.a.ArchiveError, match="content_length_mismatch"):
        m.download(Truncated(plan), plan["queries"][0], tmp_path / "truncated.gz")
    assert not (tmp_path / "truncated.gz").exists()


def test_statistics_206_preserves_bytes_and_marks_partial_but_metadata_rejects_it(setup, monkeypatch, tmp_path):
    _, _, plan = setup
    client = m.Client("db-synthetic-no-network-key", plan["queries"])
    def respond(request, **kwargs):
        response = Response(RAW)
        response.code = 206
        response.headers = {"Content-Length": str(len(RAW)), "X-DB-Warnings": "partially resolved"}
        return response
    def opener(*handlers):
        assert any(isinstance(h, m.a.NoRedirect) for h in handlers)
        assert any(isinstance(h, urllib.request.HTTPSHandler) and h._context is m.a._CONTEXT for h in handlers)
        return SimpleNamespace(open=respond)
    monkeypatch.setattr(urllib.request, "build_opener", opener)
    result = m.download(client, plan["queries"][0], tmp_path / "partial-symbols.gz")
    assert result["partial_symbol_resolution"] is True
    assert gzip.decompress((tmp_path / "partial-symbols.gz").read_bytes()) == RAW
    assert client.requests[-1]["http_status"] == 206 and client.requests[-1]["result"] == "ok"
    with pytest.raises(m.a.ArchiveError, match="http_error"):
        client.quote(plan["queries"][0])


def test_parallel_quotes_merge_only_finished_client_records(setup, monkeypatch):
    old, root, plan = setup
    parent = Fake(plan)
    monkeypatch.setattr(m, "Client", lambda key, queries: Fake(plan))
    _, report = m.run(parent, plan, False, root, old, quote_workers=6)
    assert report["status"] == "quoted_affordable" and report["complete_quote"] is True
    assert len(report["requests"]) == 2
    assert all(row["status"] == "quoted" for row in report["partitions"])
    assert report["quote_attempted_total_usd"] == "0"


def test_parallel_downloads_reserve_before_dispatch_and_use_isolated_clients(setup, monkeypatch):
    old, root, plan = setup
    barrier, workers = threading.Barrier(2), []
    class Worker(Fake):
        def open(self, method, params):
            saved = json.loads(next(root.glob("*/manifest.json")).read_bytes())
            query = {k: v for k, v in params.items() if k not in m.a.ENCODING}
            assert any(row["query"] == query for row in saved["reservations"])
            assert any(row["method"] == "timeseries.get_range" and row["query"] == params for row in saved["requests"])
            barrier.wait(timeout=2)
            return super().open(method, params)
    def factory(key, queries):
        worker = Worker(plan)
        workers.append(worker)
        return worker
    monkeypatch.setattr(m, "Client", factory)
    plan["continuation_authorization"] = {"sha256": "synthetic-authorization"}
    _, report = m.run(Fake(plan), plan, True, root, old, download_workers=4)
    assert report["status"] == "complete" and report["download_workers"] == 4
    assert report["continuation_authorization"] == plan["continuation_authorization"]
    assert len(workers) == 2 and all(worker._key == worker._auth == "" for worker in workers)
    assert m.statistics_prior(root)[0] == Decimal("0.2")


def test_parallel_failure_drains_success_and_resume_counts_failed_reservation(setup, monkeypatch):
    old, root, basic = setup
    monkeypatch.setattr(m.a, "prior_state", lambda path: (Decimal("0.4"), set()))
    plan = {"queries": tuple(basic["queries"][0] | {"symbols": symbol} for symbol in ("ESH6", "ESM6", "ESU6", "ESZ6", "ESH7"))}
    barrier, release, paid = threading.Barrier(2), threading.Event(), []
    class Mixed(Fake):
        def open(self, method, params):
            meta, response = super().open(method, params)
            paid.append(params["symbols"])
            barrier.wait(timeout=2)
            if params["symbols"] == "ESH6":
                meta["result"] = "transport_error"
                release.set()
                raise m.a.ArchiveError("transport_error")
            release.wait(timeout=2)
            threading.Event().wait(.03)
            return meta, response
    monkeypatch.setattr(m, "Client", lambda key, queries: Mixed(plan))
    _, first = m.run(Fake(plan), plan, True, root, old, download_workers=2)
    assert first["status"] == "failed" and len(paid) == 2
    assert sum(row["status"] == "complete" for row in first["partitions"]) == 1
    assert m.statistics_prior(root)[0] == Decimal("0.2")
    class Success(Fake):
        def open(self, method, params):
            paid.append(params["symbols"])
            return super().open(method, params)
    monkeypatch.setattr(m, "Client", lambda key, queries: Success(plan))
    _, resumed = m.run(Fake(plan), plan, True, root, old, download_workers=4)
    assert resumed["status"] == "complete" and len(paid) == 6
    assert paid.count("ESM6") == 1 and paid.count("ESH6") == 2
    total, complete = m.statistics_prior(root)
    assert total == Decimal("0.6") and len(complete) == 5


def test_parallel_fresh_budget_rejection_drains_existing_job_without_dispatching_another(setup, monkeypatch):
    old, root, plan = setup
    started, release, paid = threading.Event(), threading.Event(), []
    class Worker(Fake):
        def open(self, method, params):
            paid.append(params["symbols"])
            started.set()
            assert release.wait(timeout=2)
            return super().open(method, params)
    class Supervisor(Fake):
        calls = 0
        def quote(self, query):
            self.calls += 1
            result = super().quote(query)
            if self.calls == 4:
                assert started.wait(timeout=2)
                release.set()
                return Decimal("0.10000000000000000000000000001")
            return result
    monkeypatch.setattr(m, "Client", lambda key, queries: Worker(plan))
    _, report = m.run(Supervisor(plan), plan, True, root, old, download_workers=2)
    assert report["status"] == "failed" and report["failure"] == "statistics_requote_budget_exceeded"
    assert paid == ["ESH6"] and report["partitions"][0]["status"] == "complete"
    assert m.statistics_prior(root)[0] == Decimal("0.1")


def test_continuation_without_deadline_keeps_budget_and_allowlist(setup, monkeypatch):
    old, root, plan = setup
    monkeypatch.setattr(m, "DEADLINE", None)
    m.check_time(61)
    client = Fake(plan, cost="0.11")
    _, report = m.run(client, plan, True, root, old, download_workers=4)
    assert report["status"] == "quote_over_budget" and report["deadline_utc"] is None
    assert not any(row["method"] == "timeseries.get_range" for row in client.requests)
    assert not client.allowed("account.list", plan["queries"][0])
    for workers in (0, 5, True):
        with pytest.raises(m.a.ArchiveError, match="invalid_statistics_download_workers"):
            m.run(client, plan, True, root, old, download_workers=workers)


def test_opt_in_transport_failure_stays_charged_without_retry_while_other_queries_finish(setup, monkeypatch):
    old, root, basic = setup
    monkeypatch.setattr(m.a, "prior_state", lambda path: (Decimal("0.4"), set()))
    plan = {"queries": tuple(basic["queries"][0] | {"symbols": symbol} for symbol in ("ESH6", "ESM6", "ESU6", "ESZ6", "ESH7"))}
    paid = []
    class Worker(Fake):
        def open(self, method, params):
            meta, response = super().open(method, params)
            paid.append(params["symbols"])
            if params["symbols"] == "ESH6":
                meta["result"] = "transport_error"
                raise m.a.ArchiveError("transport_error")
            return meta, response
    monkeypatch.setattr(m, "Client", lambda key, queries: Worker(plan))
    _, report = m.run(Fake(plan), plan, True, root, old, download_workers=4, continue_transport_errors=True)
    assert report["status"] == "failed" and report["failure"] == "transport_error"
    assert report["download_errors"] == ["transport_error"]
    assert sorted(paid) == sorted(query["symbols"] for query in plan["queries"])
    assert sum(row["status"] == "complete" for row in report["partitions"]) == 4
    total, complete = m.statistics_prior(root)
    assert total == Decimal("0.5") and len(complete) == 4
    assert report["continue_transport_errors"] is True
