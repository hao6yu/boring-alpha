"""Synthetic-only identity, causal roll, missing-data and metadata security checks."""
import copy
import io
import json
from pathlib import Path
import sys
import urllib.request

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import prepare_ba012_inputs as p
import map_ba012_symbols as m

KEY = "db-synthetic-offline-key-do-not-transmit"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Synthetic input tests must not access a provider")
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)


@pytest.fixture
def design():
    # Reads frozen rules only. No actual price archive is ever opened in tests.
    return p.load_design()


class Response(io.BytesIO):
    code = 200
    headers = {}


class FakeMappingClient(m.Client):
    def __init__(self, design, mutate=None):
        super().__init__(KEY, design)
        self.ids = {name: str(index + 1) for index, name in enumerate(design["symbols"])}
        self.names = {value: key for key, value in self.ids.items()}
        self.mutate = mutate

    def open(self, method, query):
        assert self.allowed(method, query)
        meta = {"method": method, "query": dict(query), "result": "attempting"}
        self.requests.append(meta)
        symbols = query["symbols"].split(",")
        lookup = self.ids if query["stype_out"] == "instrument_id" else self.names
        payload = {key: query[key] for key in ("stype_in", "stype_out", "start_date", "end_date")}
        payload.update(symbols=symbols, status=0, partial=[], not_found=[],
            result={symbol: [{"d0": p.START, "d1": p.END, "s": lookup[symbol]}] for symbol in symbols},
            unrelated_extra="private-provider-extra-must-not-persist")
        if self.mutate:
            self.mutate(payload)
        return meta, Response(json.dumps(payload).encode())


@pytest.fixture
def mapped(tmp_path, design):
    client = FakeMappingClient(design)
    _, report = m.run_mapping(client, design, tmp_path)
    assert report["status"] == "complete"
    return report, client


def synthetic_bars(design, client, increment=10**9):
    return {row["date_chicago"]: {
        int(client.ids[symbol]): 1000 * 10**9 + int(client.ids[symbol]) * 10**9 + index * increment
        for market in row["markets"] for symbol in market["required_parent_raw_symbols"]}
        for index, row in enumerate(design["rolls"]["rows"])}


def test_frozen_exact_symbols_include_next_year_maturities(design):
    assert len(design["symbols"]) == 189
    assert {"ESH4", "TNH4", "6EH4", "GCG4", "ZCH4"} <= set(design["symbols"])
    assert all(".FUT" not in symbol and "-" not in symbol for symbol in design["symbols"])


def test_metadata_only_fixed_allowlist_and_sanitized_mapping(tmp_path, design):
    client = FakeMappingClient(design)
    target, report = m.run_mapping(client, design, tmp_path)
    assert report["status"] == "complete" and len(client.requests) == 4
    assert all(row["method"] == "symbology.resolve" for row in client.requests)
    assert "private-provider" not in target.read_text() and KEY not in target.read_text()
    for method in ("timeseries.get_range", "metadata.get_cost", "account.list", "live.subscribe"):
        assert not client.allowed(method, client.forward[0])
    for extra in ({"end_date": "2025-01-01"}, {"symbols": "MESZ6"}, {"dataset": "XNAS.ITCH"}):
        assert not client.allowed("symbology.resolve", client.forward[0] | extra)


@pytest.mark.parametrize("mutate", [
    lambda result: result.update(start_date="2015-01-01"),
    lambda result: result["result"][result["symbols"][0]][0].update(d1="2025-01-01"),
    lambda result: result["result"][result["symbols"][0]][0].update(s="invalid ID"),
    lambda result: result.update(unrelated_extra=KEY),
])
def test_invalid_or_unsafe_metadata_stops_without_further_requests(tmp_path, design, mutate):
    client = FakeMappingClient(design, mutate)
    target, report = m.run_mapping(client, design, tmp_path)
    assert report["status"] == "failed" and len(client.requests) == 1
    assert KEY not in target.read_text() and report["data_downloads"] == 0


def test_reused_instrument_id_requires_correct_reverse_identity_on_each_date():
    forward = {"ESH6": [{"d0": "2016-01-11", "d1": "2017-01-01", "s": "123"}],
               "TNH7": [{"d0": "2017-01-01", "d1": "2018-01-01", "s": "123"}]}
    reverse = {"123": [{"d0": "2016-01-11", "d1": "2017-01-01", "s": "ESH6"},
                       {"d0": "2017-01-01", "d1": "2018-01-01", "s": "TNH7"}]}
    assert p.resolve_identity("ESH6", "2016-03-01", forward, reverse) == 123
    assert p.resolve_identity("TNH7", "2017-03-01", forward, reverse) == 123
    assert p.resolve_identity("ESH6", "2017-03-01", forward, reverse) is None
    reverse["123"][0]["s"] = "ESM6"
    assert p.resolve_identity("ESH6", "2016-03-01", forward, reverse) is None


def test_same_contract_vectors_ignore_roll_basis_and_decode_child_units(design, mapped):
    report, client = mapped
    result = p.build_cases(design, report, synthetic_bars(design, client))
    assert result["status"] == "READY" and len(result["monthly_cases"]) == 72
    for case in result["monthly_cases"]:
        assert case["signs"] == [1] * 5
        assert len(case["dollar_movements"]) == 252
        assert all(vector == ["0.5", "100", "12500", "1", "5"] for vector in case["dollar_movements"])
    assert result["strategy_pnl_calculated"] is False


def test_exact_flat_sign_stays_zero_across_different_contract_price_levels(design, mapped):
    report, client = mapped
    result = p.build_cases(design, report, synthetic_bars(design, client, increment=0))
    assert all(case["signs"] == [0] * 5 for case in result["monthly_cases"])


def test_missing_roll_replacement_blocks_window_without_gap_compression(design, mapped):
    report, client = mapped
    bars = synthetic_bars(design, client)
    row = next(row for row in design["rolls"]["rows"] if row["date_chicago"] >= "2018-01-01" and row["markets"][0]["is_roll"])
    day = row["date_chicago"]
    del bars[day][int(client.ids[row["markets"][0]["active_parent_raw_symbol"]])]
    result = p.build_cases(design, report, bars)
    assert result["status"] == "DATA_INCOMPLETE"
    first = next(case for case in result["monthly_cases"] if case["decision_date_chicago"] >= day)
    assert first["status"] == "DATA_INCOMPLETE" and first["valid_intervals"] < 252
    assert day in first["missing_interval_dates"]
    assert "dollar_movements" not in first
    assert any(issue["date_chicago"] == day for issue in result["reference_issues"])


def test_nonpositive_selected_outright_remains_missing_not_capital_failure(design, mapped):
    report, client = mapped
    bars = synthetic_bars(design, client)
    bars["2018-01-02"][next(iter(bars["2018-01-02"]))] = 0
    result = p.build_cases(design, report, bars)
    assert result["monthly_cases"][0]["status"] == "DATA_INCOMPLETE"
    assert any(issue["reason"] == "NONPOSITIVE_SELECTED_OUTRIGHT_PRICE" for day in result["reference_issues"] for issue in day["issues"])


def test_design_checksum_failure_blocks_archive_price_access(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(p.sys, "argv", ["builder", "--rolls", str(tmp_path / "missing-rolls.json"),
        "--mapping", str(tmp_path / "mapping.json"), "--output", str(tmp_path / "result.json")])
    monkeypatch.setattr(p, "read_archives", lambda *args: pytest.fail("Price access must follow frozen design validation"))
    assert p.main() == 2
    assert json.loads(capsys.readouterr().err)["status"] == "DATA_INCOMPLETE"
