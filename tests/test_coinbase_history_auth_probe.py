"""Offline auth/sanitization checks: synthetic keys and mocked HTTP only."""
import base64
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

SPEC = importlib.util.spec_from_file_location(
    "coinbase_history_auth_probe", Path(__file__).parents[1] / "tools/coinbase_history_auth_probe.py"
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
NAME = "organizations/synthetic-org/apiKeys/synthetic-key"
SENSITIVE = "synthetic-account-id-and-secret-never-in-report"


@pytest.fixture(autouse=True)
def forbid_real_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("This test must never make a network request")
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)


def synthetic_key(kind):
    if kind == "es256":
        key = ec.generate_private_key(ec.SECP256R1())
        encoded = key.private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.TraditionalOpenSSL,
                                    serialization.NoEncryption()).decode()
        return key, encoded.replace("\n", "\\n"), "ES256"
    key = ed25519.Ed25519PrivateKey.generate()
    if kind == "ed-pem":
        encoded = key.private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()).decode()
    else:
        raw = key.private_bytes_raw()
        if kind == "ed64":
            raw += key.public_key().public_bytes_raw()
        encoded = " \n" + base64.b64encode(raw).decode() + "\n "
    return key, encoded, "EdDSA"


@pytest.mark.parametrize("kind", ["es256", "ed32", "ed64", "ed-pem"])
@pytest.mark.parametrize("path", [m.PERMISSIONS, m.PATHS[m.PRODUCTS[0]]])
def test_signatures_and_request_binding(kind, path):
    key, encoded, expected_algorithm = synthetic_key(kind)
    signer = m.load_signer(encoded)
    token = m.make_token(NAME, signer, path)
    claims = jwt.decode(token, key.public_key(), algorithms=[expected_algorithm], issuer="cdp")
    headers = jwt.get_unverified_header(token)
    assert headers["alg"] == expected_algorithm
    assert headers["kid"] == claims["sub"] == NAME
    assert headers["nonce"]
    assert claims["exp"] - claims["nbf"] == 120
    assert claims["uri"] == "GET api.coinbase.com" + path.split("?", 1)[0]
    assert "?" not in claims["uri"]
    second = jwt.get_unverified_header(m.make_token(NAME, signer, path))
    assert second["nonce"] != headers["nonce"]


@pytest.mark.parametrize("path", [
    "/api/v3/brokerage/accounts", "/api/v3/brokerage/orders",
    "https://example.invalid/api/v3/brokerage/key_permissions",
    m.PERMISSIONS + "?extra=1", m.PATHS[m.PRODUCTS[0]] + "&limit=500",
    "/api/v3/brokerage/products/BTC-USD/candles",
])
def test_non_allowlisted_paths_rejected_before_signing_or_io(path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Rejected endpoint reached signing or HTTP setup")
    monkeypatch.setattr(m.jwt, "encode", unexpected)
    monkeypatch.setattr(m.urllib.request, "build_opener", unexpected)
    with pytest.raises(ValueError, match="outside fixed"):
        m.fetch(NAME, None, path)


def test_rejects_invalid_keys_without_revealing_input():
    key = ed25519.Ed25519PrivateKey.generate()
    other = ed25519.Ed25519PrivateKey.generate()
    mismatched = base64.b64encode(key.private_bytes_raw() + other.public_key().public_bytes_raw()).decode()
    wrong_curve = ec.generate_private_key(ec.SECP384R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    for encoded in [SENSITIVE, base64.b64encode(b"x" * 63).decode(), mismatched, wrong_curve]:
        with pytest.raises(ValueError) as exc:
            m.load_signer(encoded)
        assert encoded not in str(exc.value)
        assert SENSITIVE not in str(exc.value)


class Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.code = status


def mock_open(monkeypatch, body, status=200, *, raise_transport=False):
    captured = {}
    def opening(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        if raise_transport:
            raise OSError(SENSITIVE)
        if status != 200:
            raise urllib.error.HTTPError(request.full_url, status, SENSITIVE,
                                         {"Location": "https://example.invalid/" + SENSITIVE},
                                         io.BytesIO(body))
        return Response(body, status)
    def build(*handlers):
        captured["handlers"] = handlers
        return SimpleNamespace(open=opening)
    monkeypatch.setattr(m.urllib.request, "build_opener", build)
    return captured


def test_fetch_fixed_get_and_no_redirect_handler(monkeypatch):
    captured = mock_open(monkeypatch, b'{"can_view":true}')
    key, encoded, algorithm = synthetic_key("ed64")
    path = m.PATHS[m.PRODUCTS[0]]
    meta, payload = m.fetch(NAME, m.load_signer(encoded), path)
    request = captured["request"]
    assert request.method == "GET"
    assert request.full_url == "https://api.coinbase.com" + path
    token = request.get_header("Authorization").removeprefix("Bearer ")
    claims = jwt.decode(token, key.public_key(), algorithms=[algorithm])
    assert claims["uri"] == "GET api.coinbase.com" + path.split("?", 1)[0]
    assert any(isinstance(h, m.NoRedirect) for h in captured["handlers"])
    assert captured["timeout"] == 20
    assert meta["result"] == "ok" and payload == {"can_view": True}
    assert NAME not in json.dumps(meta) and token not in json.dumps(meta)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_response_cannot_forward_authorization(status):
    request = urllib.request.Request("https://api.coinbase.com" + m.PERMISSIONS,
                                     headers={"Authorization": "Bearer " + SENSITIVE})
    opener = urllib.request.build_opener(m.NoRedirect())
    with pytest.raises(urllib.error.HTTPError) as exc:
        opener.error("http", request, io.BytesIO(b""), status, "redirect",
                     {"location": "https://example.invalid/capture"})
    assert exc.value.code == status


@pytest.mark.parametrize("body,status,expected", [
    (json.dumps({"error": "NOT_FOUND", "message": SENSITIVE + " invalid product_id"}).encode(), 404, "http_error"),
    (json.dumps({"error": SENSITIVE, "message": SENSITIVE}).encode(), 401, "http_error"),
    (SENSITIVE.encode(), 302, "non_json_response"),
    (b"[]", 200, "unexpected_response"),
    (b"x" * 2_000_001, 200, "oversized_response"),
])
def test_failed_fetch_sanitizes_response_and_does_not_return_payload(monkeypatch, body, status, expected):
    mock_open(monkeypatch, body, status)
    _, encoded, _ = synthetic_key("ed32")
    meta, payload = m.fetch(NAME, m.load_signer(encoded), m.PERMISSIONS)
    assert meta["result"] == expected
    assert payload is None
    saved = json.dumps(meta)
    assert SENSITIVE not in saved and NAME not in saved and encoded not in saved
    if status == 404:
        assert meta["api_error"] == "NOT_FOUND"
        assert meta["invalid_product_message"] is True
    if status == 401:
        assert meta["api_error"] == "OTHER"


def test_transport_exception_text_is_not_reported(monkeypatch):
    mock_open(monkeypatch, b"", raise_transport=True)
    _, encoded, _ = synthetic_key("ed32")
    meta, payload = m.fetch(NAME, m.load_signer(encoded), m.PERMISSIONS)
    assert meta["result"] == "transport_error" and payload is None
    assert SENSITIVE not in json.dumps(meta)


@pytest.mark.parametrize("payload", [None, {}, {"can_view": False}, {"can_view": 1},
                                     {"can_view": "true"}, {"can_view": None}])
def test_unverified_view_stops_before_candle_requests(payload):
    calls = []
    def fetching(name, signer, path):
        calls.append(path)
        return {"result": "ok" if payload is not None else "http_error"}, payload
    report = m.run_probe(NAME, None, fetcher=fetching)
    assert calls == [m.PERMISSIONS]
    assert report["status"] == "AUTH_OR_VIEW_UNVERIFIED"
    assert report["products"] == {}


def test_report_keeps_failed_unknown_distinct_from_empty_and_invalid():
    responses = iter([
        ({"result": "ok"}, {"can_view": True, "can_trade": False, "can_transfer": "false",
                              "account_id": SENSITIVE, "organization_id": SENSITIVE}),
        ({"result": "http_error", "http_status": 404}, None),
        ({"result": "ok"}, {"candles": []}),
        ({"result": "ok"}, {"candles": [{"start": SENSITIVE}]}),
    ])
    report = m.run_probe(NAME, None, fetcher=lambda *args: next(responses))
    assert report["permissions"] == {"can_view": True, "can_trade": False, "can_transfer": None}
    products = list(report["products"].values())
    assert [(p["result"], p["bars"]) for p in products] == [
        ("http_error", None), ("empty_candles", 0), ("invalid_candles", None)]
    assert SENSITIVE not in json.dumps(report) and NAME not in json.dumps(report)


def test_valid_candles_only_retain_normalized_fields():
    candle = {"start": str(m.START), "open": "100", "high": "102", "low": "99",
              "close": "101", "volume": "2", "account_id": SENSITIVE}
    calls = []
    def fetching(name, signer, path):
        calls.append(path)
        payload = {"can_view": True, "account_id": SENSITIVE} if path == m.PERMISSIONS else {
            "candles": [candle], "account_id": SENSITIVE, "error": SENSITIVE}
        return {"result": "ok"}, payload
    report = m.run_probe(NAME, None, fetcher=fetching)
    assert calls == [m.PERMISSIONS, *m.PATHS.values()]
    for result in report["products"].values():
        assert result["result"] == "valid_candles" and result["bars"] == 1
        assert set(result["normalized_candles"][0]) == {"start", "open", "high", "low", "close", "volume"}
    assert SENSITIVE not in json.dumps(report) and NAME not in json.dumps(report)
