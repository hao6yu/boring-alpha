"""Offline fictional fixtures only: no credentials, provider, or market files."""

import csv
from datetime import date
import hashlib
import io
import json
from types import SimpleNamespace
import traceback
from urllib.error import HTTPError, URLError

import pytest

from tools import tiingo_seen_reference as reference


SECRET = "fake_tiingo_credential_DO_NOT_DISCLOSE_4321"
EXPECTED = (date(2006, 2, 28), date(2021, 12, 31))


def row(day="2006-02-28", **changes):
    result = dict(zip(reference.FIELDS, (
        day, "40", "42", "39", "41", "100", "32", "33.6", "31.2",
        "32.8", "125", "0", "1",
    )))
    result.update(changes)
    return result


def csv_bytes(rows, fields=reference.FIELDS):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def assert_secret_free(error):
    assert SECRET not in str(error)
    assert SECRET not in "".join(traceback.format_exception(error))


def test_date_first_filter_ignores_malformed_numeric_fields_outside_both_bounds():
    raw = csv_bytes([
        row("2006-02-27", open=SECRET, close="1e99999", splitFactor="invalid"),
        row("2006-02-28"), row("2021-12-31"),
        row("2022-01-03", open=SECRET, close="nan", splitFactor="invalid"),
    ])
    parsed, bounded, outside = reference.parse_csv(raw)
    assert tuple(parsed) == EXPECTED
    assert outside == 2
    assert SECRET.encode() not in bounded
    assert b"2006-02-27" not in bounded and b"2022-01-03" not in bounded
    assert b"2006-02-28" in bounded and b"2021-12-31" in bounded


@pytest.mark.parametrize("label", [
    "2006-02-28", "2006-02-28T00:00:00Z", "2006-02-28T00:00:00.000Z",
    "2006-02-28T00:00:00+00:00", "2006-02-28T00:00:00.000+00:00",
])
def test_utc_daily_label_retains_the_same_session_date(label):
    parsed, bounded, outside = reference.parse_csv(csv_bytes([row(label)]))
    assert list(parsed) == [EXPECTED[0]]
    assert bounded == csv_bytes([row("2006-02-28")])
    assert outside == 0


@pytest.mark.parametrize("changes", [
    {"date": SECRET}, {"date": "2021-02-29"},
    {"date": "2006-02-28T01:00:00Z"}, {"date": "2006-02-28T00:00:00-06:00"},
    {"open": SECRET}, {"close": "nan"}, {"adjClose": "inf"},
    {"adjVolume": "-inf"}, {"volume": "1e99999"}, {"open": "True"},
    {"low": "0"}, {"open": "43"}, {"adjClose": "34"},
    {"volume": "-1"}, {"adjVolume": "-1"}, {"divCash": "-1"},
    {"splitFactor": "0"},
])
def test_invalid_retained_rows_refuse_without_exposing_field_contents(changes):
    with pytest.raises(ValueError) as caught:
        reference.parse_csv(csv_bytes([row(**changes)]))
    assert_secret_free(caught.value)


@pytest.mark.parametrize("kind", ["missing_header", "duplicate_header", "extra_field", "missing_field", "duplicate_date", "unsorted", "empty", "encoding"])
def test_invalid_schema_layout_and_date_order_refuse(kind):
    valid = csv_bytes([row()])
    if kind == "missing_header":
        raw = valid.replace(b"splitFactor", b"unexpected", 1)
    elif kind == "duplicate_header":
        raw = valid.replace(b"splitFactor", b"open", 1)
    elif kind == "extra_field":
        raw = valid.rstrip() + b",extra\n"
    elif kind == "missing_field":
        raw = valid.rsplit(b",", 1)[0] + b"\n"
    elif kind == "duplicate_date":
        raw = csv_bytes([row(), row()])
    elif kind == "unsorted":
        raw = csv_bytes([row("2006-03-01"), row()])
    elif kind == "empty":
        raw = csv_bytes([])
    else:
        raw = b"\xff" + SECRET.encode()
    with pytest.raises(ValueError) as caught:
        reference.parse_csv(raw)
    assert_secret_free(caught.value)


def test_coverage_is_exact_not_an_intersection():
    reference.require_coverage(dict.fromkeys(EXPECTED), EXPECTED)
    for dates in (EXPECTED[:1], (*EXPECTED, date(2010, 1, 4))):
        with pytest.raises(ValueError, match="coverage mismatch"):
            reference.require_coverage(dict.fromkeys(dates), EXPECTED)


@pytest.mark.parametrize("symbol", reference.SYMBOLS)
def test_request_url_has_exact_symbol_fixed_bounds_and_no_credential(symbol):
    assert reference.request_url(symbol) == (
        f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices"
        "?startDate=2006-02-28&endDate=2021-12-31&resampleFreq=daily&format=csv"
    )
    assert SECRET not in reference.request_url(symbol)


@pytest.mark.parametrize("symbol", ["FREE", "spy", "../SPY", "SPY?token=" + SECRET])
def test_unregistered_symbols_refuse_without_echoing_them(symbol):
    with pytest.raises(ValueError, match="authorized eight-ETF") as caught:
        reference.request_url(symbol)
    assert_secret_free(caught.value)


class Response(io.BytesIO):
    def __init__(self, raw, url, status=200):
        super().__init__(raw)
        self.url, self.status = url, status

    def geturl(self):
        return self.url


def test_fetch_uses_authorization_header_and_redirect_blocker(monkeypatch):
    raw = csv_bytes([row()])
    calls = []
    monkeypatch.setattr(reference, "tls_context", lambda: object())

    def open_request(request, timeout):
        calls.append(request.full_url)
        assert request.get_header("Authorization") == f"Token {SECRET}"
        assert SECRET not in request.full_url
        assert timeout == 45
        return Response(raw, request.full_url)

    def opener(*handlers):
        assert any(isinstance(handler, reference.NoRedirect) for handler in handlers)
        return SimpleNamespace(open=open_request)

    monkeypatch.setattr(reference, "build_opener", opener)
    assert reference.fetch_bytes("SPY", SECRET) == raw
    assert calls == [reference.request_url("SPY")]


@pytest.mark.parametrize("failure", ["http", "transport", "redirect", "response_url", "status", "oversized", "reflection"])
def test_fetch_errors_suppress_secrets_in_output_and_formatted_tracebacks(monkeypatch, capsys, failure):
    monkeypatch.setattr(reference, "tls_context", lambda: object())

    def open_request(request, timeout):
        if failure == "http":
            raise HTTPError("https://example.invalid/?token=" + SECRET, 401, SECRET, {}, io.BytesIO(SECRET.encode()))
        if failure == "transport":
            raise URLError(SECRET)
        if failure == "redirect":
            reference.NoRedirect().redirect_request(request, None, 302, SECRET, {}, "https://example.invalid/" + SECRET)
        if failure == "response_url":
            return Response(b"ignored", "https://example.invalid/" + SECRET)
        if failure == "status":
            return Response(SECRET.encode(), request.full_url, 503)
        if failure == "oversized":
            monkeypatch.setattr(reference, "MAX_BYTES", 4)
            return Response(b"12345", request.full_url)
        return Response(SECRET.encode(), request.full_url)

    monkeypatch.setattr(reference, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    with pytest.raises(ValueError, match="Tiingo request") as caught:
        reference.fetch_bytes("SPY", SECRET)
    assert_secret_free(caught.value)
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err


@pytest.mark.parametrize("template", [
    "TIINGO_API_KEY={key}\n", "TIINGO_API_KEY='{key}'\n", 'TIINGO_API_KEY="{key}"\n',
    "  export TIINGO_API_KEY = '{key}'  \n",
])
def test_local_credential_assignment_quotes_and_export(tmp_path, template):
    path = tmp_path / "fictional-credentials.txt"
    path.write_text("IGNORED=unrelated\n" + template.format(key=SECRET))
    assert reference.read_key(path) == SECRET


@pytest.mark.parametrize("contents", [
    "OTHER=ignored\n", "TIINGO_API_KEY=\n", "TIINGO_API_KEY=''\n",
    "TIINGO_API_KEY={key}\nexport TIINGO_API_KEY={key}\n",
    'TIINGO_API_KEY="{key}\n', "TIINGO_API_KEY=$(not-executed)\n",
])
def test_missing_duplicate_or_invalid_assignment_fails_without_secret(tmp_path, contents):
    path = tmp_path / "fictional-credentials.txt"
    path.write_text(contents.format(key=SECRET))
    with pytest.raises(ValueError) as caught:
        reference.read_key(path)
    assert_secret_free(caught.value)


def test_missing_credential_file_has_sanitized_failure(tmp_path):
    with pytest.raises(ValueError, match="cannot read local") as caught:
        reference.read_key(tmp_path / SECRET)
    assert_secret_free(caught.value)


@pytest.fixture
def captured(tmp_path, monkeypatch):
    destination = tmp_path / "reference"
    key_path = tmp_path / "fictional-credentials.txt"
    key_path.write_text(f"TIINGO_API_KEY={SECRET}\n")
    raw = csv_bytes([row(str(day)) for day in EXPECTED])
    calls = []

    def fetch(symbol, key):
        assert key == SECRET
        assert not (destination / "manifest.json").exists()
        calls.append(symbol)
        return raw

    monkeypatch.setattr(reference, "fetch_bytes", fetch)
    manifest = reference.capture(destination, key_path, EXPECTED)
    assert calls == list(reference.SYMBOLS)
    return destination, manifest, raw


def test_capture_and_load_preserve_checked_bytes_and_all_eight_symbols(captured, capsys):
    destination, manifest, raw = captured
    rows, loaded_manifest = reference.load_capture(destination, EXPECTED)
    assert loaded_manifest == manifest
    assert set(rows) == set(reference.SYMBOLS)
    assert all(tuple(value) == EXPECTED for value in rows.values())
    assert manifest["internal_use_only"] is True
    for symbol in reference.SYMBOLS:
        entry = manifest["symbols"][symbol]
        assert entry["rows"] == 2
        assert entry["request_url"] == reference.request_url(symbol)
        assert entry["response_sha256"] == hashlib.sha256(raw).hexdigest()
        assert (destination / entry["response_file"]).read_bytes() == raw
    assert SECRET not in (destination / "manifest.json").read_text()
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err


@pytest.mark.parametrize("kind", ["response", "bounded"])
def test_capture_loader_refuses_changed_source_bytes(captured, kind):
    destination, manifest, _ = captured
    path = destination / manifest["symbols"]["SPY"][f"{kind}_file"]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        reference.load_capture(destination, EXPECTED)


@pytest.mark.parametrize("change", ["provider", "end", "symbols", "filename", "rows", "request_url"])
def test_capture_loader_refuses_incompatible_manifest(captured, change):
    destination, manifest, _ = captured
    if change == "provider":
        manifest["provider"] = "different-provider"
    elif change == "end":
        manifest["end"] = "2022-12-31"
    elif change == "symbols":
        del manifest["symbols"]["DBC"]
    elif change == "filename":
        manifest["symbols"]["SPY"]["response_file"] = "../unexpected.csv"
    elif change == "rows":
        manifest["symbols"]["SPY"]["rows"] = 1
    else:
        manifest["symbols"]["SPY"]["request_url"] = reference.request_url("IWM")
    (destination / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        reference.load_capture(destination, EXPECTED)


def test_partial_capture_failure_never_publishes_manifest(tmp_path, monkeypatch):
    destination = tmp_path / "reference"
    monkeypatch.setattr(reference, "read_key", lambda path: SECRET)

    def fetch(symbol, key):
        days = EXPECTED if symbol == "SPY" else EXPECTED[:1]
        return csv_bytes([row(str(day)) for day in days])

    monkeypatch.setattr(reference, "fetch_bytes", fetch)
    with pytest.raises(ValueError, match="coverage mismatch"):
        reference.capture(destination, "not-read", EXPECTED)
    assert (destination / "SPY.csv").is_file()
    assert not (destination / "manifest.json").exists()


def test_outside_response_rows_refuse_capture_before_archiving_them(tmp_path, monkeypatch):
    destination = tmp_path / "reference"
    monkeypatch.setattr(reference, "read_key", lambda path: SECRET)
    raw = csv_bytes([row(str(day)) for day in EXPECTED] + [row("2022-01-03", open="invalid")])
    monkeypatch.setattr(reference, "fetch_bytes", lambda symbol, key: raw)
    with pytest.raises(ValueError, match="out-of-range"):
        reference.capture(destination, "not-read", EXPECTED)
    assert list(destination.iterdir()) == []


def test_existing_capture_directory_is_not_overwritten(tmp_path, monkeypatch):
    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("preserve")
    monkeypatch.setattr(reference, "read_key", lambda path: SECRET)
    monkeypatch.setattr(reference, "fetch_bytes", lambda *args: pytest.fail("network must not be reached"))
    with pytest.raises(FileExistsError):
        reference.capture(destination, "not-read", EXPECTED)
    assert marker.read_text() == "preserve"
