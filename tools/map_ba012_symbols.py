#!/usr/bin/env python3
"""Resolve only frozen BA-012 parent symbols and their dated reverse identities.

Offline plan by default. --resolve uses a hidden credential for the free
historical symbology.resolve metadata endpoint only. No prices, cost requests,
account APIs, retries, redirects, live data or data downloads are available.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path
import re
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_ba012_references as archive
from fetch_mes_history import Client as HistoricalClient
from prepare_ba012_inputs import InputError, START, END, STAGE, load_design

CHUNK = 128
BASE = {"dataset": "GLBX.MDP3", "start_date": START, "end_date": END}


def queries_for(symbols, reverse=False):
    return tuple(BASE | {"symbols": ",".join(symbols[index:index + CHUNK]),
        "stype_in": "instrument_id" if reverse else "raw_symbol",
        "stype_out": "raw_symbol" if reverse else "instrument_id"}
        for index in range(0, len(symbols), CHUNK))


class Client(HistoricalClient):
    def __init__(self, key, design):
        super().__init__(key)
        self.forward = queries_for(design["symbols"])
        self.reverse = ()

    def allowed(self, method, params):
        return method == "symbology.resolve" and params in (*self.forward, *self.reverse)

    def bind_reverse(self, forward):
        ids = sorted({row["s"] for partition in forward for intervals in partition["mapping"]["result"].values()
                      for row in intervals}, key=int)
        if len(ids) > 10_000:
            raise archive.ArchiveError("unexpected_mapping_size")
        self.reverse = queries_for(ids, reverse=True)


def validate_mapping(raw, query):
    """Retain normalized dated intervals, excluding arbitrary response extras."""
    try:
        payload = archive.load_json(raw)
        symbols = query["symbols"].split(",")
        for key in ("stype_in", "stype_out", "start_date", "end_date"):
            if payload[key] != query[key]:
                raise ValueError
        if payload["symbols"] != symbols or type(payload["status"]) is not int or payload["status"] not in (0, 1):
            raise ValueError
        for key in ("partial", "not_found"):
            if not isinstance(payload[key], list) or not set(payload[key]) <= set(symbols):
                raise ValueError
        result = payload["result"]
        if not isinstance(result, dict) or not set(result) <= set(symbols):
            raise ValueError
        clean = {"result": {}, "partial": list(payload["partial"]), "not_found": list(payload["not_found"])}
        for symbol in symbols:
            if symbol not in result and symbol not in payload["not_found"] and symbol not in payload["partial"]:
                raise ValueError
            intervals = result.get(symbol, [])
            if not isinstance(intervals, list) or len(intervals) > 5000:
                raise ValueError
            previous, rows = START, []
            for row in intervals:
                left, right, output = row["d0"], row["d1"], row["s"]
                if (date.fromisoformat(left).isoformat() != left or date.fromisoformat(right).isoformat() != right
                        or not START <= left < right <= END or left < previous):
                    raise ValueError
                if query["stype_out"] == "instrument_id":
                    value = archive.strict_integer(output)
                    if not 0 < value < 2**32:
                        raise ValueError
                    output = str(value)
                elif not isinstance(output, str) or not re.fullmatch(r"[ -~]{1,160}", output):
                    raise ValueError
                rows.append({"d0": left, "d1": right, "s": output})
                previous = right
            clean["result"][symbol] = rows
        return clean
    except (ValueError, TypeError, KeyError, archive.ArchiveError):
        raise archive.ArchiveError("invalid_dated_mapping_response") from None


def run_mapping(client, design, output_root=STAGE / "symbology"):
    folder = Path(output_root) / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True, exist_ok=False)
    report = {"schema": "ba012-dated-symbology-v1", "status": "resolving", "started_at": archive.utcnow(),
        "protocol_sha256": archive.PROTOCOL_SHA256, "calendar_sha256": design["calendar_sha256"],
        "rolls_sha256": design["rolls_sha256"], "data_downloads": 0, "strategy_returns_calculated": False,
        "requests": client.requests, "forward": [], "reverse": [],
        "limitations": ["Instrument IDs may be reused; join both directions on the exact reference date.",
            "Metadata completeness does not establish reference-bar availability or child executability.",
            "Missing or partial symbol intervals remain missing; no alternative contract is substituted."]}
    try:
        for query in client.forward:
            raw = client.metadata("symbology.resolve", query)
            report["forward"].append({"query": query, "mapping": validate_mapping(raw, query),
                                      "response_sha256": hashlib.sha256(raw).hexdigest()})
        client.bind_reverse(report["forward"])
        for query in client.reverse:
            raw = client.metadata("symbology.resolve", query)
            report["reverse"].append({"query": query, "mapping": validate_mapping(raw, query),
                                      "response_sha256": hashlib.sha256(raw).hexdigest()})
        report["status"] = "complete"
    except BaseException as exc:
        report["status"] = "failed"
        report["failure"] = str(exc) if isinstance(exc, archive.ArchiveError) else "dated_mapping_stopped"
    finally:
        report["completed_at"] = archive.utcnow()
        target = folder / "mapping.json"
        with target.open("x") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        target.chmod(0o444)
    return target, report


def main():
    parser = archive.SafeParser(description=__doc__)
    parser.add_argument("--rolls", type=Path, default=STAGE / "rolls-v1.json")
    parser.add_argument("--calendar", type=Path, default=STAGE / "calendar-v1.json")
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args()
    client, key = None, ""
    try:
        design = load_design(args.rolls, args.calendar)
        if not args.resolve:
            print(json.dumps({"status": "offline_mapping_plan", "exact_raw_symbols": len(design["symbols"]),
                "forward_metadata_queries": len(queries_for(design["symbols"])), "data_downloads": 0,
                "rolls_sha256": design["rolls_sha256"], "calendar_sha256": design["calendar_sha256"]}))
            return 0
        if not sys.stdin.isatty():
            raise archive.ArchiveError("interactive_hidden_credential_required")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("Databento API key (hidden; metadata only): ").strip()
        if not re.fullmatch(r"db-[A-Za-z0-9_-]{20,80}", key):
            raise archive.ArchiveError("invalid_credential_format")
        client = Client(key, design)
        key = ""
        target, report = run_mapping(client, design)
        print(json.dumps({"status": report["status"], "mapping": str(target), "data_downloads": 0,
                          "failure": report.get("failure")}))
        return 0 if report["status"] == "complete" else 1
    except (InputError, archive.ArchiveError) as exc:
        print(json.dumps({"status": "failed", "failure": str(exc)}), file=sys.stderr)
        return 1
    except BaseException:
        print(json.dumps({"status": "failed", "failure": "mapping_tool_stopped"}), file=sys.stderr)
        return 1
    finally:
        key = ""
        if client is not None:
            client._key = client._auth = ""


if __name__ == "__main__":
    raise SystemExit(main())
