"""Synthetic-only checks of the exact execution-panel decoding boundary."""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("profit_inputs", Path(__file__).parents[1] / "tools/prepare_ba012_profitability.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def archive(tmp_path, rows):
    query = {"dataset": "GLBX.MDP3", "schema": "ohlcv-1m", "stype_in": "parent",
             "symbols": "ES.FUT,TN.FUT,6E.FUT,GC.FUT,ZC.FUT",
             "start": "2022-07-01T15:00:00+00:00", "end": "2022-07-01T15:06:00+00:00"}
    raw = b"".join((json.dumps(row) + "\n").encode() for row in rows)
    path = tmp_path / "bars.gz"
    path.write_bytes(gzip.compress(raw))
    partition = {"query": query, "records": len(rows), "raw_bytes": len(raw),
                 "raw_sha256": hashlib.sha256(raw).hexdigest()}
    return path, partition


def bar(minute, identity=123, price=123456789000):
    # Fixed synthetic values; no archive or external price inputs.
    return {"hd": {"rtype": 33, "ts_event": str(m.ns_at("2022-07-01", 10, minute)),
                   "instrument_id": identity, "publisher_id": 1},
            "open": str(price), "high": str(price), "low": str(price),
            "close": str(price), "volume": 5}


def test_exact_units_missing_minutes_and_spreads(tmp_path):
    path, part = archive(tmp_path, [bar(0), bar(1, identity=456, price=-1), bar(5)])
    values, invalid = m.decode_execution_file(path, part, {"TNM2": 123})
    assert invalid == []
    assert values["TNM2"]["10:00"]["close"] == "123.456789"
    assert values["TNM2"]["10:01"] is None
    assert values["TNM2"]["10:05"]["bar_end_utc_ns"] == m.ns_at("2022-07-01", 10, 6)


def test_nonpositive_exact_contract_is_null(tmp_path):
    path, part = archive(tmp_path, [bar(1, price=0)])
    values, invalid = m.decode_execution_file(path, part, {"TNM2": 123})
    assert values["TNM2"]["10:01"] is None
    assert invalid == [{"symbol": "TNM2", "minute": "10:01", "reason": "NONPOSITIVE_EXACT_OUTRIGHT_BAR"}]


def test_window_duplicates_and_integrity_fail_closed(tmp_path):
    path, part = archive(tmp_path, [bar(6)])
    with pytest.raises(m.BundleError, match="outside_exact_window"):
        m.decode_execution_file(path, part, {"TNM2": 123})
    path, part = archive(tmp_path, [bar(0), bar(0)])
    with pytest.raises(m.reference.archive.ArchiveError):
        m.decode_execution_file(path, part, {"TNM2": 123})
    path, part = archive(tmp_path, [bar(0)])
    bad = deepcopy(part)
    bad["raw_sha256"] = "0" * 64
    with pytest.raises(m.BundleError, match="raw_integrity"):
        m.decode_execution_file(path, bad, {"TNM2": 123})
