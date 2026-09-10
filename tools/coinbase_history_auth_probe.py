#!/usr/bin/env python3
"""Bounded read-only Coinbase probe; credentials are entered without terminal echo.

Only GET key_permissions and three fixed historical candle requests are possible.
Reports contain validated market bars, permission booleans and response hashes;
never credentials, JWTs, account identifiers or arbitrary error response text.
Install the optional coinbase-research dependency before running.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

sys.path.insert(0, str(Path(__file__).resolve().parent))
from us_futures_history import ROOT, _CONTEXT, normalize_candles, parse_time, utcnow

HOST = "api.coinbase.com"
PREFIX = "/api/v3/brokerage/"
PERMISSIONS = PREFIX + "key_permissions"
PRODUCTS = ("BIP-20DEC30-CDE", "BIT-28AUG26-CDE", "ET-28AUG26-CDE")
START = parse_time("2026-08-24T00:00:00Z")
END = parse_time("2026-08-25T00:00:00Z")
QUERY = urllib.parse.urlencode({"start": START, "end": END - 1,
                               "granularity": "ONE_HOUR", "limit": 300})
PATHS = {pid: PREFIX + "products/" + pid + "/candles?" + QUERY for pid in PRODUCTS}
ALLOWED = {PERMISSIONS, *PATHS.values()}


def load_signer(secret: str):
    """Support Coinbase's documented ECDSA PEM and Ed25519 seed formats."""
    try:
        if secret.lstrip().startswith("-----BEGIN"):
            key = serialization.load_pem_private_key(secret.replace("\\n", "\n").encode(), password=None)
        else:
            raw = base64.b64decode("".join(secret.split()), validate=True)
            if len(raw) not in (32, 64):
                raise ValueError
            key = ed25519.Ed25519PrivateKey.from_private_bytes(raw[:32])
            if len(raw) == 64 and key.public_key().public_bytes_raw() != raw[32:]:
                raise ValueError
        if isinstance(key, ed25519.Ed25519PrivateKey):
            return key, "EdDSA"
        if isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(key.curve, ec.SECP256R1):
            return key, "ES256"
    except Exception:
        raise ValueError("Invalid private key format; credential contents omitted") from None
    raise ValueError("Expected Ed25519 or ECDSA P-256 private key")


def make_token(name: str, signer, path: str) -> str:
    if path not in ALLOWED:
        raise ValueError("Request outside fixed read-only probe")
    key, algorithm = signer
    now = int(time.time())
    return jwt.encode({"sub": name, "iss": "cdp", "nbf": now, "exp": now + 120,
                       "uri": "GET " + HOST + path.split("?", 1)[0]}, key,
                      algorithm=algorithm, headers={"kid": name, "nonce": secrets.token_hex()})


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(name: str, signer, path: str) -> tuple[dict, dict | None]:
    token = make_token(name, signer, path)
    request = urllib.request.Request("https://" + HOST + path, method="GET", headers={
        "Authorization": "Bearer " + token, "Accept": "application/json",
        "User-Agent": "BoringAlpha-ReadOnly-Research/0.1"})
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=_CONTEXT))
    meta = {"url": request.full_url, "requested_at": utcnow()}
    try:
        try:
            response = opener.open(request, timeout=20)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(2_000_001)
            meta.update(http_status=response.code, received_at=utcnow())
        if len(raw) > 2_000_000:
            return meta | {"result": "oversized_response"}, None
        meta.update(response_bytes=len(raw), response_sha256=hashlib.sha256(raw).hexdigest())
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            return meta | {"result": "non_json_response"}, None
        if not isinstance(payload, dict):
            return meta | {"result": "unexpected_response"}, None
        if meta["http_status"] != 200:
            # Categorize known errors; arbitrary server text is never archived.
            known = {"INVALID_ARGUMENT", "UNAUTHENTICATED", "PERMISSION_DENIED", "NOT_FOUND",
                     "RESOURCE_EXHAUSTED", "INTERNAL", "UNAVAILABLE"}
            code = payload.get("error")
            meta["api_error"] = code if isinstance(code, str) and code in known else "OTHER"
            meta["invalid_product_message"] = "product_id" in str(payload.get("message", "")).lower() and "invalid" in str(payload.get("message", "")).lower()
            return meta | {"result": "http_error"}, None
        return meta | {"result": "ok"}, payload
    except Exception:
        # Exception messages may include headers, identifiers or response data.
        return meta | {"result": "transport_error", "received_at": utcnow()}, None


def run_probe(name: str, signer, fetcher=fetch) -> dict:
    report = {"schema": "coinbase-authenticated-expired-history-probe-v1",
              "started_at": utcnow(), "start": START, "end_exclusive": END,
              "status": "AUTH_OR_VIEW_UNVERIFIED", "requests": [], "products": {}}
    meta, payload = fetcher(name, signer, PERMISSIONS)
    report["requests"].append(meta)
    if payload is None:
        return report
    permissions = {k: payload.get(k) if type(payload.get(k)) is bool else None
                   for k in ("can_view", "can_trade", "can_transfer")}
    report["permissions"] = permissions
    if permissions["can_view"] is not True:
        return report
    report["status"] = "AUTHENTICATED_DATA_PROBE_COMPLETED"
    for pid, path in PATHS.items():
        meta, payload = fetcher(name, signer, path)
        report["requests"].append(meta)
        result = {"result": meta["result"], "bars": None}
        if payload is not None:
            try:
                rows = normalize_candles(payload, START, END)
                result.update(result="valid_candles" if rows else "empty_candles",
                              bars=len(rows), normalized_candles=rows)
            except Exception:
                result["result"] = "invalid_candles"
        report["products"][pid] = result
    report["completed_at"] = utcnow()
    report["limitations"] = ["Availability probe, not a backtest or profitability result.",
                             "Hourly candles do not establish synchronized executable prices.",
                             "Failed requests have unknown bar counts, never zero-filled bars.",
                             "Raw bodies are hashed, not saved; only validated fields retained."]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/us_crypto/authenticated-history-probes")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Use an interactive terminal for hidden credential entry")
    try:
        name = getpass.getpass("API key name (hidden): ").strip()
        signer = load_signer(getpass.getpass("Private key (hidden; PEM may use escaped newlines): "))
        report = run_probe(name, signer)
        folder = args.output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder.mkdir(parents=True, exist_ok=False)
        with (folder / "report.json").open("x") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(json.dumps({"status": report["status"], "permissions": report.get("permissions"),
                          "products": {pid: {k: v for k, v in r.items() if k != "normalized_candles"}
                                       for pid, r in report["products"].items()},
                          "requests": report["requests"], "report": str(folder / "report.json")}, indent=2))
        return 0 if report["status"] == "AUTHENTICATED_DATA_PROBE_COMPLETED" else 1
    except (Exception, KeyboardInterrupt):
        print("Probe stopped; error and credential contents omitted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
