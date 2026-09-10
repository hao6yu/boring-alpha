"""Offline regressions for draining the full date plan after transient failures."""
from decimal import Decimal
import importlib.util
import io
import json
from pathlib import Path
import urllib.request

import pytest

SPEC = importlib.util.spec_from_file_location("ba012_next", Path(__file__).parents[1] / "tools/fetch_ba012_references.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


@pytest.fixture
def plan(monkeypatch):
    monkeypatch.setattr(m, "REFERENCES", m.REFERENCES[:4])
    monkeypatch.setattr(m.time, "sleep", lambda seconds: None)
    def forbidden(*args, **kwargs):
        pytest.fail("No external requests allowed")
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    return {"sha256": "1" * 64, "costs": (Decimal("0.2"),) * 4}


class Response(io.BytesIO):
    headers = {}
    code = 200


class OfflineClient:
    def __init__(self, paid, errors):
        self.requests = []
        self.paid, self.errors = paid, errors
        self._key = self._auth = "synthetic-no-network"

    def metadata(self, method, query):
        self.requests.append({"method": method, "query": dict(query), "result": "ok"})
        return b"1" if method == "metadata.get_record_count" else b"0.2"

    def open(self, method, params):
        assert method == "timeseries.get_range"
        assert any(params == query | m.ENCODING for query in m.REFERENCES)
        entry = {"method": method, "query": dict(params), "result": "attempting"}
        self.requests.append(entry)
        day = params["start"]
        self.paid.append(day)
        failure = self.errors.pop(day, None)
        if failure:
            entry["result"] = failure
            raise m.ArchiveError(failure)
        raw = json.dumps({"hd": {"ts_event": str(m.stamp_ns(day)), "rtype": 33,
            "publisher_id": 1, "instrument_id": 123}, "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}).encode() + b"\n"
        return entry, Response(raw)

    def contains_secret(self, raw):
        return False


def test_transient_paid_failure_does_not_discard_other_dates_and_resume_only_failed(tmp_path, plan):
    paid = []
    failed_day = m.REFERENCES[0]["start"]
    errors = {failed_day: "transport_error"}
    factory = lambda: OfflineClient(paid, errors)
    _, first = m.run_parallel_archive(factory, plan, Decimal("1"), tmp_path, workers=1)
    assert first["status"] == "failed" and first["task_failures"] == ["transport_error"]
    assert paid == [query["start"] for query in m.REFERENCES]
    assert sum(row["status"] == "complete" for row in first["partitions"]) == 3
    assert m.prior_state(tmp_path)[0] == Decimal("0.8")
    _, second = m.run_with_resumes(factory, plan, Decimal("1"), tmp_path, workers=2, attempts=2)
    assert second["status"] == "complete" and paid[-1] == failed_day and len(paid) == 5
    total, completed = m.prior_state(tmp_path)
    assert total == Decimal("1.0") and len(completed) == 4


def test_mixed_terminal_failure_stops_new_submissions_and_blocks_resume(tmp_path, plan):
    paid = []
    errors = {m.REFERENCES[0]["start"]: "transport_error", m.REFERENCES[1]["start"]: "invalid_reference_bar"}
    _, report = m.run_parallel_archive(lambda: OfflineClient(paid, errors), plan, Decimal("1"), tmp_path, workers=1)
    assert report["status"] == "failed"
    assert report["task_failures"] == ["transport_error", "invalid_reference_bar"]
    assert paid == [query["start"] for query in m.REFERENCES[:2]]
    assert not m.resumable_failure(report)
    assert m.prior_state(tmp_path)[0] == Decimal("0.4")


def test_automatic_resume_has_one_paid_attempt_per_date_per_run(tmp_path, plan):
    paid = []
    errors = {m.REFERENCES[0]["start"]: "transport_error"}
    _, report = m.run_with_resumes(lambda: OfflineClient(paid, errors), plan, Decimal("1"), tmp_path, workers=2, attempts=2)
    assert report["status"] == "complete" and report["resume"]["attempt"] == 2
    assert len(paid) == 5
    assert paid.count(m.REFERENCES[0]["start"]) == 2
    for query in m.REFERENCES[1:]:
        assert paid.count(query["start"]) == 1
    assert m.prior_state(tmp_path)[0] == Decimal("1.0")
