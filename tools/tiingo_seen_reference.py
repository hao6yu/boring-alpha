"""Local-only Tiingo reference capture, hard-bounded to BA-002's seen history.

Not a replacement data feed or strategy runner. Never log credentials, response
bodies, or upstream exception text. Raw/row-level outputs belong in ignored
data/snapshots or experiments, not the public repository.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from tools.check_ba002_seen_prices import END, START, tls_context

SYMBOLS = ("SPY", "IWM", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC")
FIELDS = ("date", "open", "high", "low", "close", "volume", "adjOpen",
          "adjHigh", "adjLow", "adjClose", "adjVolume", "divCash", "splitFactor")
MAX_BYTES = 10_000_000


def read_key(path):
    """Read just TIINGO_API_KEY, without executing a shell or dotenv expansion."""
    values = []
    try:
        lines = Path(path).read_text().splitlines()
    except (OSError, UnicodeError):
        raise ValueError("cannot read local Tiingo credential file") from None
    for line in lines:
        match = re.fullmatch(r"\s*(?:export\s+)?TIINGO_API_KEY\s*=\s*(.*?)\s*", line)
        if match:
            value = match.group(1)
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            values.append(value)
    if len(values) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]+", values[0]):
        raise ValueError("one nonempty valid TIINGO_API_KEY assignment is required")
    return values[0]


def request_url(symbol):
    if symbol not in SYMBOLS:
        raise ValueError("symbol is outside the authorized eight-ETF universe")
    return (f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices"
            f"?startDate={START}&endDate={END}&resampleFreq=daily&format=csv")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Tiingo redirect refused") from None


def fetch_bytes(symbol, key):
    url = request_url(symbol)
    request = Request(url, headers={"Authorization": f"Token {key}",
                                   "Accept": "text/csv", "User-Agent": "BoringAlpha seen-only audit"})
    try:
        opener = build_opener(HTTPSHandler(context=tls_context()), NoRedirect())
        with opener.open(request, timeout=45) as response:
            if response.geturl() != url or response.status != 200:
                raise ValueError("unexpected response")
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("oversized response")
        if key.encode() in raw:
            raise ValueError("credential reflection")
    except HTTPError as error:
        raise ValueError(f"Tiingo request refused (HTTP {error.code}); response content suppressed") from None
    except Exception:
        raise ValueError("Tiingo request failed; upstream details suppressed") from None
    return raw


def parse_csv(raw):
    """Filter text by session date BEFORE any numeric interpretation or output."""
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        if reader.fieldnames is None or set(reader.fieldnames) != set(FIELDS) or len(reader.fieldnames) != len(FIELDS):
            raise ValueError("Tiingo response has an unexpected CSV schema")
        rows, retained, outside = {}, [], 0
        for line, row in enumerate(reader, 2):
            label = row.get("date")
            if not isinstance(label, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T00:00:00(?:\.000)?(?:Z|\+00:00))?", label):
                raise ValueError(f"Tiingo row {line}: invalid session date")
            try:
                day = date.fromisoformat(label[:10])
            except ValueError:
                raise ValueError(f"Tiingo row {line}: invalid session date") from None
            if not START <= day <= END:
                outside += 1
                continue
            if None in row or any(value is None for value in row.values()) or day in rows:
                raise ValueError(f"Tiingo row {line}: invalid layout or duplicate session")
            try:
                values = {key: float(row[key]) for key in FIELDS if key != "date"}
            except (TypeError, ValueError, OverflowError):
                raise ValueError(f"Tiingo row {line}: invalid numeric field") from None
            if any(not math.isfinite(value) for value in values.values()):
                raise ValueError(f"Tiingo row {line}: non-finite numeric field")
            for prefix in ("", "adj"):
                keys = ("open", "high", "low", "close") if not prefix else ("adjOpen", "adjHigh", "adjLow", "adjClose")
                opening, high, low, close = (values[key] for key in keys)
                if not 0 < low <= min(opening, close) <= max(opening, close) <= high:
                    raise ValueError(f"Tiingo row {line}: impossible OHLC")
            if values["volume"] < 0 or values["adjVolume"] < 0 or values["divCash"] < 0 or values["splitFactor"] <= 0:
                raise ValueError(f"Tiingo row {line}: invalid volume or corporate action")
            rows[day] = values
            retained.append([row[key] if key != "date" else str(day) for key in FIELDS])
        if not rows or list(rows) != sorted(rows):
            raise ValueError("Tiingo response is empty or not chronological")
    except (UnicodeError, csv.Error):
        raise ValueError("Tiingo response is not valid CSV text") from None
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FIELDS)
    writer.writerows(retained)
    return rows, output.getvalue().encode(), outside


def require_coverage(rows, expected):
    if set(rows) != set(expected):
        raise ValueError(f"Tiingo session coverage mismatch: {len(set(expected) - set(rows))} missing, "
                         f"{len(set(rows) - set(expected))} unexpected")


def capture(destination, key_path, expected):
    """Write to a new directory only; completion manifest last; no pointer swap."""
    key = read_key(key_path)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {"provider": "Tiingo", "purpose": "BA-002 seen-only independent reference; not primary data",
                "start": str(START), "end": str(END), "internal_use_only": True,
                "created_utc": datetime.now(timezone.utc).isoformat(), "symbols": {}}
    for symbol in SYMBOLS:
        raw = fetch_bytes(symbol, key)
        rows, bounded, outside = parse_csv(raw)
        require_coverage(rows, expected)
        # Unexpected dates were never numerically inspected, but an endpoint
        # ignoring its bounds is not admitted as a successful bounded capture.
        if outside:
            raise ValueError("Tiingo returned out-of-range rows; bounded capture refused")
        raw_name, bounded_name = f"{symbol}.response.csv", f"{symbol}.csv"
        (destination / raw_name).write_bytes(raw)
        (destination / bounded_name).write_bytes(bounded)
        manifest["symbols"][symbol] = {
            "request_url": request_url(symbol), "response_file": raw_name,
            "response_sha256": hashlib.sha256(raw).hexdigest(), "bounded_file": bounded_name,
            "bounded_sha256": hashlib.sha256(bounded).hexdigest(), "rows": len(rows),
        }
        print(f"{symbol}: archived {len(rows)} seen sessions", flush=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    (destination / "manifest.json").write_bytes(payload)
    return manifest


def load_capture(directory, expected):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if (manifest.get("provider") != "Tiingo" or manifest.get("start") != str(START)
            or manifest.get("end") != str(END) or set(manifest.get("symbols", {})) != set(SYMBOLS)):
        raise ValueError("Tiingo reference manifest does not match the bounded request")
    result = {}
    for symbol in SYMBOLS:
        entry = manifest["symbols"][symbol]
        if entry.get("request_url") != request_url(symbol):
            raise ValueError("Tiingo reference request URL mismatch")
        for kind, filename in (("response", f"{symbol}.response.csv"), ("bounded", f"{symbol}.csv")):
            if entry[f"{kind}_file"] != filename:
                raise ValueError("Tiingo reference manifest has an unexpected filename")
            raw = (directory / filename).read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry[f"{kind}_sha256"]:
                raise ValueError("Tiingo reference checksum mismatch")
            rows, bounded, outside = parse_csv(raw)
            require_coverage(rows, expected)
            if outside or len(rows) != entry["rows"] or hashlib.sha256(bounded).hexdigest() != entry["bounded_sha256"]:
                raise ValueError("Tiingo reference content does not match the bounded capture")
        result[symbol] = rows
    return result, manifest
