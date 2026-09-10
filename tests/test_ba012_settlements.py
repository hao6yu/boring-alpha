"""Offline synthetic tests for the separately frozen v2 settlement adapter."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import prepare_ba012_settlements as adapter


def fixture(day="2020-06-01"):
    design = {"rolls": {"rows": [{"date_chicago": day, "markets": [
        {"required_parent_raw_symbols": ["ESM0"]}]}]}}
    forward = {"ESM0": [{"d0": "2016-01-01", "d1": "2024-01-01", "s": "1"}]}
    reverse = {"1": [{"d0": "2016-01-01", "d1": "2024-01-01", "s": "ESM0"}]}
    reference = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) * 10**9
    event = adapter.cutoff_ns(day) - 60 * 10**9
    record = {"hd": {"rtype": 24, "instrument_id": 1, "publisher_id": 1, "ts_event": str(event)},
              "ts_ref": str(reference), "ts_recv": str(event + 1), "stat_type": 3, "stat_flags": 2,
              "update_action": 1, "channel_id": 0, "sequence": 1, "price": "100000000000"}
    return design, forward, reverse, record


def choose(records, day="2020-06-01"):
    design, forward, reverse, _ = fixture(day)
    return adapter.select_settlements(records, design, forward, reverse)


def test_literal_utc_reference_day_is_not_previous_chicago_day():
    _, _, _, record = fixture()
    selected, audit = choose([record])
    assert selected == {"2020-06-01": {1: 100000000000}}
    assert audit["selected_references"][0]["availability_basis"] == "capture_receive_time"


def test_after_cutoff_final_cannot_replace_pre_cutoff_actual():
    _, _, _, record = fixture()
    later = copy.deepcopy(record)
    later.update(stat_flags=3, price="999000000000", ts_recv=str(adapter.cutoff_ns("2020-06-01") + 1))
    later["hd"]["ts_event"] = str(adapter.cutoff_ns("2020-06-01") + 1)
    selected, _ = choose([later, record])
    assert selected["2020-06-01"][1] == 100000000000


def test_revision_order_is_chronological_and_sequence_only_within_channel():
    _, _, _, record = fixture()
    revised = copy.deepcopy(record)
    revised.update(sequence=2, price="101000000000")
    selected, _ = choose([revised, record])
    assert selected["2020-06-01"][1] == 101000000000
    revised["channel_id"] = 1
    selected, audit = choose([revised, record])
    assert not selected
    assert "AMBIGUOUS_CROSS_CHANNEL_ORDER" in audit["reference_issues"][0]["reasons"]


def test_delete_is_conservative_even_if_later_add_exists():
    _, _, _, record = fixture()
    deleted = copy.deepcopy(record)
    deleted.update(update_action=2, stat_flags=0, price=str(2**63 - 1))
    selected, audit = choose([deleted, record])
    assert not selected
    assert "PRE_CUTOFF_SETTLEMENT_DELETE" in audit["reference_issues"][0]["reasons"]


def test_frozen_precision_preference_only_at_final_ordering_tie():
    _, _, _, clearing = fixture()
    trading = clearing | {"stat_flags": 6, "price": "100100000000"}
    selected, _ = choose([trading, clearing])
    assert selected["2020-06-01"][1] == int(clearing["price"])
    trading["sequence"] = 2
    selected, _ = choose([trading, clearing])
    assert selected["2020-06-01"][1] == int(trading["price"])
    conflicting = clearing | {"price": "999000000000"}
    selected, audit = choose([clearing, conflicting])
    assert not selected
    assert "CONFLICTING_SAME_ORDER_SETTLEMENTS" in audit["reference_issues"][0]["reasons"]


@pytest.mark.parametrize("change", [{"ts_recv": None}, {"ts_recv": str(2**64 - 1)},
                                    {"ts_recv": "1"}, {"stat_flags": 16}, {"update_action": 9}])
def test_missing_or_invalid_candidate_fields_remain_unresolved(change):
    _, _, _, record = fixture()
    record.update(change)
    selected, audit = choose([record])
    assert not selected and audit["reference_issues"]


def test_legacy_without_capture_is_explicit_event_proxy():
    _, _, _, record = fixture("2016-06-01")
    record["ts_recv"] = str(2**64 - 1)
    selected, audit = choose([record], "2016-06-01")
    assert selected
    assert audit["selected_references"][0]["availability_basis"] == "event_time_proxy"


def test_no_intraday_or_nonactual_fallback_and_no_nonmidnight_reference():
    _, _, _, record = fixture()
    for flags in (1, 10):
        candidate = record | {"stat_flags": flags}
        assert choose([candidate])[0] == {}
    record["ts_ref"] = str(int(record["ts_ref"]) + 1)
    with pytest.raises(adapter.SettlementError):
        choose([record])


def test_roll_basis_never_enters_changes_and_missing_endpoint_blocks_window():
    design = adapter.original.load_design()  # Frozen rules only.
    names = design["symbols"]
    ids = {symbol: i + 1 for i, symbol in enumerate(names)}
    forward = {symbol: [{"d0": "2016-01-11", "d1": "2024-01-01", "s": str(instrument)}]
               for symbol, instrument in ids.items()}
    reverse = {str(instrument): [{"d0": "2016-01-11", "d1": "2024-01-01", "s": symbol}]
               for symbol, instrument in ids.items()}
    selected = {row["date_chicago"]: {ids[symbol]: (1000 + ids[symbol] + i) * 10**9
                for market in row["markets"] for symbol in market["required_parent_raw_symbols"]}
                for i, row in enumerate(design["rolls"]["rows"])}
    cases, missing, _ = adapter.build_monthly_cases(design, selected, forward, reverse)
    assert len(cases) == 72 and not missing
    assert all(c["signs"] == [1] * 5 for c in cases)
    assert all(v == ["0.5", "100", "12500", "1", "5"] for c in cases for v in c["dollar_movements"])
    row = next(r for r in design["rolls"]["rows"] if r["date_chicago"] >= "2018-01-01" and r["markets"][0]["is_roll"])
    del selected[row["date_chicago"]][ids[row["markets"][0]["active_parent_raw_symbol"]]]
    cases, missing, _ = adapter.build_monthly_cases(design, selected, forward, reverse)
    failed = next(c for c in cases if c["decision_date_chicago"] >= row["date_chicago"])
    assert failed["status"] == "DATA_INCOMPLETE" and "dollar_movements" not in failed


def test_missing_cases_never_call_sizing_or_reject_capital(monkeypatch):
    monkeypatch.setattr(adapter.sizing, "size_stage_a", lambda *a, **k: pytest.fail("Missing case reached sizing"))
    cases = [{"decision_date_chicago": "2020-01-31", "status": "DATA_INCOMPLETE"}]
    report = adapter.size_pilot_cases(cases)
    assert report["verdict"] == "INCOMPLETE_STUDY_NO_CAPITAL_VERDICT"
    assert report["unresolved_cases"] == 1 and report["cash_cases"] == 0
