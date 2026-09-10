"""Offline spend-gate, normalization, and credential-containment regressions."""
import base64
import copy
from datetime import datetime
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest


SPEC = importlib.util.spec_from_file_location(
    "databento_history_probe", Path(__file__).parents[1] / "tools/databento_history_probe.py"
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
KEY = "db-synthetic-test-key-never-use-for-network"
PRIVATE = "synthetic-account-information-do-not-persist"
MINUTE_NS = 60 * 10**9
START_NS = int(datetime.fromisoformat(m.SAMPLE["start"]).timestamp()) * 10**9
RANGE = json.dumps({"start": "2010-06-06T00:00:00Z", "end": "2026-09-08T00:00:00Z"}).encode()


@pytest.fixture(autouse=True)
def forbid_real_http(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Offline probe tests must never perform network I/O")
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)


def bar(minute=0):
    return {
        "hd": {"ts_event": str(START_NS + minute * MINUTE_NS), "instrument_id": 12345},
        "open": "6000250000000", "high": "6001000000000",
        "low": "6000000000000", "close": "6000750000000", "volume": 7,
    }


def encode_bars(*bars):
    return b"\n".join(json.dumps(item).encode() for item in bars) + b"\n"


def fake_probe(*, fresh_quote=b"0.01", sample=None, metadata=RANGE, sample_result="ok"):
    calls = []
    sample_quotes = 0
    if sample is None:
        sample = encode_bars(bar())

    def fetching(key, method, params):
        nonlocal sample_quotes
        assert key == KEY
        calls.append((method, copy.deepcopy(params)))
        assert m.allowed_request(method, params)
        result, raw = "ok", b"0.01"
        if method == "metadata.get_dataset_range":
            raw = metadata
        elif method == "metadata.get_cost" and params == m.SAMPLE:
            sample_quotes += 1
            if sample_quotes == 2:
                raw = fresh_quote
        elif method == "timeseries.get_range":
            result, raw = sample_result, sample if sample_result == "ok" else None
        return {"result": result, "http_status": 200 if raw is not None else 403}, raw

    return fetching, calls


@pytest.mark.parametrize("raw", [
    None, b"", b"not-json", b"null", b"true", b"false", b"{}", b"[]", b'"0.01"',
    b"NaN", b"Infinity", b"-Infinity", b"-0.01", b"1e999", b"9" * 400,
    b"1e999999999999999999999999999999999", b"1e-999999999999999999999999999999999",
])
def test_invalid_quotes_are_unavailable(raw):
    assert m.quote_value(raw) is None


@pytest.mark.parametrize("fresh_quote", [
    None, b"not-json", b"true", b'"0.01"', b"NaN", b"Infinity", b"-0.01",
    b"1.01", b"1.0000000000000000001", b"9" * 400,
    b"1e999999999999999999999999999999999",
])
def test_fresh_invalid_or_over_ceiling_quote_prevents_any_download(fresh_quote):
    fetching, calls = fake_probe(fresh_quote=fresh_quote)
    report, raw = m.run_probe(KEY, download_sample=True, fetcher=fetching)
    assert raw is None
    assert report["sample"]["status"] == "quote_refused"
    assert len(calls) == 5  # range, three research quotes, mandatory fresh quote
    assert calls[-1] == ("metadata.get_cost", m.SAMPLE)
    assert all(method != "timeseries.get_range" for method, _ in calls)


@pytest.mark.parametrize("fresh_quote", [b"0", b"0.0001", b"1.0"])
def test_finite_quote_at_or_below_ceiling_permits_exactly_one_fixed_sample(fresh_quote):
    fetching, calls = fake_probe(fresh_quote=fresh_quote)
    report, raw = m.run_probe(KEY, download_sample=True, fetcher=fetching)
    assert raw == encode_bars(bar())
    assert report["sample"]["status"] == "valid_bars"
    assert calls[-2:] == [
        ("metadata.get_cost", m.SAMPLE),
        ("timeseries.get_range", m.SAMPLE | {"encoding": "json", "compression": "none"}),
    ]
    assert sum(method == "timeseries.get_range" for method, _ in calls) == 1


def test_default_probe_only_quotes_and_retains_no_metadata_extras():
    metadata = json.dumps(json.loads(RANGE) | {"account_id": PRIVATE}).encode()
    fetching, calls = fake_probe(metadata=metadata)
    report, raw = m.run_probe(KEY, fetcher=fetching)
    assert raw is None
    assert report["sample"]["status"] == "not_requested"
    assert calls == [("metadata.get_dataset_range", {"dataset": m.DATASET})] + [
        ("metadata.get_cost", query) for query in m.QUOTES.values()
    ]
    assert report["dataset_range"] == json.loads(RANGE)
    assert PRIVATE not in json.dumps(report) and KEY not in json.dumps(report)


@pytest.mark.parametrize("metadata", [
    None, b"not-json", b"[]", b"null", b"true", b"{}",
    b'{"start":null,"end":"2026-01-01T00:00:00Z"}',
    b'{"start":"2026-01-02T00:00:00Z","end":"2026-01-01T00:00:00Z"}',
    b'{"start":"2026-01-01T00:00:00Z","end":"2026-01-01T00:00:00Z"}',
    b'{"start":"2025-01-01","end":"2026-01-01T00:00:00Z"}',
    b'{"start":"invalid-date","end":"2026-01-01T00:00:00Z"}',
])
def test_missing_or_malformed_metadata_stops_with_report(metadata):
    fetching, calls = fake_probe(metadata=metadata)
    report, raw = m.run_probe(KEY, download_sample=True, fetcher=fetching)
    assert isinstance(report, dict)
    assert raw is None
    assert len(calls) == 1
    assert report["sample"]["status"] != "valid_bars"


@pytest.mark.parametrize("method,params", [
    ("metadata.get_dataset_range", {"dataset": m.DATASET}),
    *[("metadata.get_cost", query) for query in m.QUOTES.values()],
    ("timeseries.get_range", m.SAMPLE | {"encoding": "json", "compression": "none"}),
])
def test_allowlist_accepts_only_declared_requests(method, params):
    assert m.allowed_request(method, dict(params))
    assert not m.allowed_request(method + "/extra", params)
    assert not m.allowed_request(method, params | {"extra": "1"})
    for field in params:
        assert not m.allowed_request(method, {k: v for k, v in params.items() if k != field})


@pytest.mark.parametrize("method,params", [
    ("account.get_balance", {}),
    ("https://example.invalid/capture", {"dataset": m.DATASET}),
    ("metadata.get_dataset_range", {"dataset": "XNAS.ITCH"}),
    ("timeseries.get_range", m.QUOTES["mes_2025_minutes"]),
    ("timeseries.get_range", m.SAMPLE | {"encoding": "json", "compression": "none", "limit": 391}),
    ("timeseries.get_range", m.SAMPLE | {"encoding": "json", "compression": "none", "symbols": "MES.v.0"}),
    ("timeseries.get_range", m.SAMPLE | {"encoding": "json", "compression": "none", "end": "2026-01-01"}),
])
def test_rejected_requests_never_reach_http_setup(method, params, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Rejected request reached HTTP setup")
    monkeypatch.setattr(m.urllib.request, "build_opener", unexpected)
    with pytest.raises(ValueError, match="outside fixed"):
        m.fetch(KEY, method, params)


def test_fixed_point_prices_and_nanosecond_timestamps_are_preserved():
    rows = m.normalize_sample(encode_bars(bar(), bar(1)))
    assert rows == [
        {"ts_event_ns": START_NS + i * MINUTE_NS, "instrument_id": 12345,
         "open": "6000.25", "high": "6001", "low": "6000", "close": "6000.75", "volume": 7}
        for i in range(2)
    ]


@pytest.mark.parametrize("field,value", [
    ("open", "6000100000000"), ("high", "6000500000000"), ("low", "6001000000000"),
    ("close", "0"), ("close", "-250000000"), ("close", "NaN"), ("close", "Infinity"),
    ("volume", 0), ("volume", -1), ("volume", 1.5), ("volume", True),
    ("ts_event", str(START_NS - MINUTE_NS)), ("ts_event", str(START_NS + 390 * MINUTE_NS)),
    ("ts_event", str(START_NS + 1)), ("ts_event", float(START_NS)),
    ("instrument_id", 12345.5), ("instrument_id", True), ("instrument_id", 0), ("instrument_id", -1),
])
def test_invalid_price_timestamp_or_nonintegral_field_rejected(field, value):
    item = bar()
    (item["hd"] if field in ("ts_event", "instrument_id") else item)[field] = value
    with pytest.raises((ValueError, TypeError, ArithmeticError)):
        m.normalize_sample(encode_bars(item))


@pytest.mark.parametrize("raw", [
    b"", b"not-json", b"{}", b"[]", encode_bars(bar(), bar()), encode_bars(bar(1), bar()),
    encode_bars(bar(), bar(1) | {"hd": {"ts_event": str(START_NS + MINUTE_NS), "instrument_id": 67890}}),
])
def test_empty_malformed_duplicate_unsorted_or_mixed_instrument_sample_rejected(raw):
    with pytest.raises((ValueError, TypeError, KeyError)):
        m.normalize_sample(raw)


@pytest.mark.parametrize("minute_indices,expected_missing", [(range(390), 0), ([0, 2, 389], 387)])
def test_missing_minutes_reported_without_fabricating_bars(minute_indices, expected_missing):
    sample = encode_bars(*(bar(i) for i in minute_indices))
    fetching, calls = fake_probe(sample=sample)
    report, raw = m.run_probe(KEY, download_sample=True, fetcher=fetching)
    assert raw == sample
    assert report["sample"]["status"] == "valid_bars"
    assert report["sample"]["bars"] == 390 - expected_missing
    assert report["sample"]["missing_minutes"] == expected_missing


@pytest.mark.parametrize("sample,result,expected", [
    (b"not-json", "ok", "invalid_bar_response"),
    (encode_bars(bar(), bar()), "ok", "invalid_bar_response"),
    (b"", "http_error", "http_error"),
    (b"", "transport_error", "transport_error"),
])
def test_failed_download_never_produces_sample_artifact(sample, result, expected):
    fetching, calls = fake_probe(sample=sample, sample_result=result)
    report, raw = m.run_probe(KEY, download_sample=True, fetcher=fetching)
    assert raw is None
    assert report["sample"]["status"] == expected
    assert "normalized_bars" not in report["sample"]


class Response(io.BytesIO):
    def __init__(self, body):
        super().__init__(body)
        self.code = 200


def mock_open(monkeypatch, body, status=200, *, transport=False):
    captured = {}
    def opening(request, timeout):
        captured.update(request=request, timeout=timeout)
        if transport:
            raise OSError(PRIVATE + KEY)
        if status != 200:
            raise urllib.error.HTTPError(request.full_url, status, PRIVATE,
                                         {"Location": "https://example.invalid/" + PRIVATE}, io.BytesIO(body))
        return Response(body)
    def build(*handlers):
        captured["handlers"] = handlers
        return SimpleNamespace(open=opening)
    monkeypatch.setattr(m.urllib.request, "build_opener", build)
    return captured


def test_fetch_uses_fixed_https_get_and_keeps_authorization_out_of_report(monkeypatch):
    captured = mock_open(monkeypatch, RANGE)
    meta, raw = m.fetch(KEY, "metadata.get_dataset_range", {"dataset": m.DATASET})
    request = captured["request"]
    assert request.get_method() == "GET"
    assert request.full_url == m.HOST + "metadata.get_dataset_range?dataset=GLBX.MDP3"
    assert request.get_header("Authorization") == "Basic " + base64.b64encode((KEY + ":").encode()).decode()
    assert captured["timeout"] == 40
    assert any(isinstance(h, m.NoRedirect) for h in captured["handlers"])
    assert meta["result"] == "ok" and raw == RANGE
    assert KEY not in json.dumps(meta) and "Authorization" not in json.dumps(meta)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_handler_cannot_forward_authorization(status):
    request = urllib.request.Request(m.HOST + "metadata.get_dataset_range", headers={"Authorization": KEY})
    opener = urllib.request.build_opener(m.NoRedirect())
    with pytest.raises(urllib.error.HTTPError) as exc:
        opener.error("http", request, io.BytesIO(b""), status, "redirect",
                     {"location": "https://example.invalid/capture"})
    assert exc.value.code == status


@pytest.mark.parametrize("body,status,expected", [
    (b"license agreement auth api key credits balance " + PRIVATE.encode(), 403, "http_error"),
    (PRIVATE.encode(), 302, "http_error"),
    (b"x" * 2_000_001, 200, "unsafe_or_oversized_response"),
    (KEY.encode(), 200, "unsafe_or_oversized_response"),
    (("Basic " + base64.b64encode((KEY + ":").encode()).decode()).encode(), 200, "unsafe_or_oversized_response"),
])
def test_failed_or_secret_echo_response_is_not_returned_or_reported(monkeypatch, body, status, expected):
    mock_open(monkeypatch, body, status)
    meta, raw = m.fetch(KEY, "metadata.get_dataset_range", {"dataset": m.DATASET})
    assert meta["result"] == expected and raw is None
    assert PRIVATE not in json.dumps(meta) and KEY not in json.dumps(meta)
    if status == 403:
        assert meta["mentions_license"] and meta["mentions_auth"] and meta["mentions_credits"]


def test_transport_error_does_not_reveal_exception_details(monkeypatch):
    mock_open(monkeypatch, b"", transport=True)
    meta, raw = m.fetch(KEY, "metadata.get_dataset_range", {"dataset": m.DATASET})
    assert meta["result"] == "transport_error" and raw is None
    assert PRIVATE not in json.dumps(meta) and KEY not in json.dumps(meta)
