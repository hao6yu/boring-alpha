"""Offline, fictional checks for the Tiingo seen-history diagnostic."""

from datetime import date
import json
from types import SimpleNamespace

import pytest

from tools import check_ba002_tiingo as diagnostic


def test_split_divisors_exclude_own_ex_date_and_include_later_reverse_split():
    days = [date(2010, 1, day) for day in (4, 5, 6, 7)]
    # Deliberately unsorted input. Three new shares followed by a 1-for-2 split.
    rows = {days[2]: {"splitFactor": 0.5}, days[0]: {"splitFactor": 1},
            days[3]: {"splitFactor": 1}, days[1]: {"splitFactor": 3}}
    assert diagnostic.split_divisors(rows) == {
        days[0]: 1.5, days[1]: 0.5, days[2]: 1, days[3]: 1,
    }


def test_split_divisors_do_not_leak_between_symbols_or_mutate_rows():
    before, ex_date = date(2010, 1, 4), date(2010, 1, 5)
    splitting = {before: {"splitFactor": 1}, ex_date: {"splitFactor": 3}}
    other = {before: {"splitFactor": 1}, ex_date: {"splitFactor": 1}}
    assert diagnostic.split_divisors(splitting) == {before: 3, ex_date: 1}
    assert diagnostic.split_divisors(other) == {before: 1, ex_date: 1}
    assert splitting == {before: {"splitFactor": 1}, ex_date: {"splitFactor": 3}}


@pytest.mark.parametrize("reference,yahoo,exceeds", [
    (10, 10.02, False), (10, 9.98, False),
    (10, 10.0201, True), (10, 9.9799, True),
    (100, 100.05, False), (100, 99.95, False),
    (100, 100.0501, True), (100, 99.9499, True),
])
def test_fixed_tolerance_boundary(reference, yahoo, exceeds):
    row = diagnostic.compare(date(2010, 1, 4), yahoo, reference)
    assert row["exceeds_tolerance"] is exceeds
    assert row["difference_dollars"] == pytest.approx(yahoo - reference)
    assert row["difference_bps"] == pytest.approx((yahoo - reference) / reference * 10000)


def test_summary_counts_and_signed_extremes_are_independent():
    rows = [diagnostic.compare(date(2010, 1, 4), 9.9, 10),
            diagnostic.compare(date(2010, 1, 5), 100.2, 100),
            diagnostic.compare(date(2010, 1, 6), 10.01, 10)]
    result = diagnostic.summary(rows)
    assert result["comparisons"] == 3
    assert result["exceeds_tolerance"] == 2
    assert result["largest_absolute_bps"] == rows[0]
    assert result["largest_absolute_dollars"] == rows[1]


@pytest.mark.parametrize("yahoo_end,tiingo_end,expected", [
    (101, 102, (False, True)),  # Equality with cash means cash, not a risk vote.
    (102, 101, (True, False)),
    (100, 102, (False, True)),  # Intentionally cross zero in each direction.
    (102, 100, (True, False)),
    (101, 101, (False, False)),
])
def test_vote_check_uses_strict_cash_relative_sign(yahoo_end, tiingo_end, expected):
    result = diagnostic.vote_check(100, yahoo_end, 100, tiingo_end, 1.01)
    assert (result["yahoo_vote"], result["tiingo_vote"]) == expected
    assert result["changed"] is (expected[0] != expected[1])
    assert result["yahoo_excess_bps"] == pytest.approx((yahoo_end / 100 - 1.01) * 10000)
    assert result["tiingo_excess_bps"] == pytest.approx((tiingo_end / 100 - 1.01) * 10000)
    assert result["return_difference_bps"] == pytest.approx((yahoo_end - tiingo_end) * 100)


@pytest.mark.parametrize("yahoo_scale,tiingo_scale", [(0.001, 1e6), (1e6, 0.001), (3, 7)])
def test_vote_check_ignores_independent_adjusted_level_scales(yahoo_scale, tiingo_scale):
    result = diagnostic.vote_check(100 * yahoo_scale, 105 * yahoo_scale,
                                   20 * tiingo_scale, 20.4 * tiingo_scale, 1.03)
    assert result["yahoo_vote"] is True
    assert result["tiingo_vote"] is False
    assert result["changed"] is True
    assert result["yahoo_excess_bps"] == pytest.approx(200)
    assert result["tiingo_excess_bps"] == pytest.approx(-100)
    assert result["return_difference_bps"] == pytest.approx(300)


@pytest.fixture
def fictional_run(tmp_path, monkeypatch):
    """Tiny fake calendar/feeds exercise orchestration, not calendar generation."""
    anchors1 = {15: date(2016, 2, 29), 12: date(2016, 5, 31), 9: date(2016, 8, 31)}
    decision1, execution = date(2017, 5, 31), date(2017, 6, 1)
    anchors2 = {15: date(2020, 9, 30), 12: date(2020, 12, 31), 9: date(2021, 3, 31)}
    decision2, forbidden = diagnostic.END, date(2022, 1, 3)
    expected = set(anchors1.values()) | set(anchors2.values()) | {decision1, execution, decision2}
    symbols = ("ALFA", "BETA")
    requirement_calls, bar_calls, loader_calls = [], [], []

    def requirements(start, end, horizons, *, warmup_months):
        requirement_calls.append((start, end, horizons, warmup_months))
        anchors = {decision1: anchors1} if end.year == 2017 else {decision2: anchors2}
        return SimpleNamespace(anchors=anchors)

    calendar = SimpleNamespace(synthetic=False, sha256="fictional-calendar",
                               sessions=tuple(sorted(expected | {forbidden})), requirements=requirements)

    def expected_sessions(start, end):
        assert (start, end) == (diagnostic.START, diagnostic.END)
        return tuple(sorted(expected))

    calendar.expected_sessions = expected_sessions
    monkeypatch.setattr(diagnostic, "SessionCalendar", SimpleNamespace(load=lambda path: calendar))
    monkeypatch.setattr(diagnostic, "SYMBOLS", symbols)
    cash_index = {day: 1.0 if day < decision1 else 1.0001 for day in expected}

    def local_bar(day, symbol):
        assert day in expected, "must not inspect the next open beyond the seen cap"
        bar_calls.append((day, symbol))
        close = 100.02 if symbol == "ALFA" and day == decision1 else 100.0
        opening = 105.0 if symbol == "ALFA" and day == execution else close
        return SimpleNamespace(open=opening, close=close)

    market = SimpleNamespace(symbol_dates={symbol: tuple(sorted(expected)) for symbol in symbols},
                             bar=local_bar, cash_index=cash_index)
    distributions = SimpleNamespace(
        symbol_dates={symbol: tuple(sorted(expected)) for symbol in symbols},
        close=lambda day, symbol: local_bar(day, symbol).close,
        dividend=lambda day, symbol: 1.0 if symbol == "ALFA" and day == anchors1[15] else 0.0,
    )
    tiingo = {}
    for symbol in symbols:
        tiingo[symbol] = {}
        for day in sorted(expected):
            raw_price = 300.0 if symbol == "ALFA" and day < execution else 100.0
            tiingo[symbol][day] = {
                "open": raw_price, "close": raw_price, "adjOpen": 200.0, "adjClose": 200.0,
                "splitFactor": 3.0 if symbol == "ALFA" and day == execution else 1.0,
                "divCash": 3.0 if symbol == "ALFA" and day == anchors1[15] else 0.0,
            }

    def load_capture(path, requested):
        assert requested == expected
        return tiingo, {"symbols": {symbol: {"fixture": True} for symbol in symbols}}

    monkeypatch.setattr(diagnostic, "load_capture", load_capture)

    def load_market(prices, cash, *, end):
        assert end == diagnostic.END
        assert b"FORBIDDEN_FUTURE" not in prices + cash
        loader_calls.append("market")
        return market

    def load_distributions(rows, *, manifest_block, end):
        assert end == diagnostic.END
        assert b"FORBIDDEN_FUTURE" not in rows
        assert manifest_block["methodology"] == "yahoo-adjusted-v2+dgs3mo-v1"
        loader_calls.append("distributions")
        return distributions

    monkeypatch.setattr(diagnostic, "load_csv_market_data_bytes", load_market)
    monkeypatch.setattr(diagnostic, "load_distributions_bytes", load_distributions)
    snapshot, reference = tmp_path / "fictional-snapshot", tmp_path / "fictional-reference"
    snapshot.mkdir()
    reference.mkdir()
    (snapshot / "manifest.json").write_text(json.dumps({"methodology": "yahoo-adjusted-v2+dgs3mo-v1"}))
    (reference / "manifest.json").write_text('{"fictional":true}')
    for name, header, retained, poison in [
        ("market_daily.csv", "date,symbol,tr_open,tr_close", "ALFA,100,100", "ALFA,FORBIDDEN_FUTURE,FORBIDDEN_FUTURE"),
        ("cash_daily.csv", "date,cash_factor", "1", "FORBIDDEN_FUTURE"),
        ("distributions_daily.csv", "date,symbol,close,dividend", "ALFA,100,0", "ALFA,FORBIDDEN_FUTURE,FORBIDDEN_FUTURE"),
    ]:
        (snapshot / name).write_text(f"{header}\n2017-05-31,{retained}\n2022-01-03,{poison}\n")
    return SimpleNamespace(snapshot=snapshot, reference=reference, calendar=calendar,
                           market=market, distributions=distributions, tiingo=tiingo,
                           expected=expected, requirement_calls=requirement_calls,
                           bar_calls=bar_calls, loader_calls=loader_calls, execution=execution,
                           decision1=decision1)


def test_fictional_full_run_checks_all_horizons_split_units_and_next_open_cap(fictional_run):
    fixture = fictional_run
    report = diagnostic.run(fixture.snapshot, fixture.reference, "fictional-calendar.json")
    assert report["not_strategy_evaluation"] is True
    assert report["source_replaced"] is False
    assert report["internal_use_only"] is True
    assert fixture.loader_calls == ["market", "distributions"]
    assert fixture.requirement_calls == [
        (date(2007, 6, 1), date(2017, 12, 31), (9, 12, 15), 15),
        (date(2018, 1, 1), diagnostic.END, (9, 12, 15), 15),
    ]
    alfa, beta = report["symbols"]["ALFA"], report["symbols"]["BETA"]
    assert alfa["sessions"] == beta["sessions"] == len(fixture.expected)
    assert alfa["splits"] == [{"date": str(fixture.execution), "factor": 3.0}]
    assert beta["splits"] == []
    assert alfa["daily_close"]["exceeds_tolerance"] == beta["daily_close"]["exceeds_tolerance"] == 0
    assert alfa["monthly_next_open"]["comparisons"] == beta["monthly_next_open"]["comparisons"] == 1
    discrepancy, = alfa["monthly_next_open_discrepancies"]
    assert discrepancy["date"] == str(fixture.execution)
    assert discrepancy["decision_date"] == str(fixture.decision1)
    assert discrepancy["difference_dollars"] == pytest.approx(5)
    assert beta["monthly_next_open_discrepancies"] == []
    assert alfa["max_relative_nonuniform_adjustment"] == pytest.approx(0)
    assert alfa["votes"]["comparisons"] == beta["votes"]["comparisons"] == 6
    assert alfa["votes"]["changed"] == 3
    assert beta["votes"]["changed"] == 0
    assert {row["horizon"] for row in alfa["votes"]["changes"]} == {9, 12, 15}
    assert {row["date"] for row in alfa["votes"]["changes"]} == {str(fixture.decision1)}
    assert all(row["yahoo_vote"] and not row["tiingo_vote"] for row in alfa["votes"]["changes"])
    assert alfa["distributions"]["reported_outside_rounding"] == 1
    assert alfa["distributions"]["split_aligned_outside_rounding"] == 0
    assert alfa["distributions"]["rows"][0]["tiingo_divided_by_later_seen_splits"] == 1
    assert max(day for day, _ in fixture.bar_calls) == diagnostic.END
    for symbol, result in (("ALFA", alfa), ("BETA", beta)):
        assert result["by_period"] == {
            "development": {
                "first_decision": str(fixture.decision1),
                "last_decision": str(fixture.decision1),
                "vote_comparisons": 3,
                "changed_votes": 3 if symbol == "ALFA" else 0,
                "next_open_comparisons": 1,
                "next_open_flags": 1 if symbol == "ALFA" else 0,
            },
            "validation": {
                "first_decision": str(diagnostic.END),
                "last_decision": str(diagnostic.END),
                "vote_comparisons": 3,
                "changed_votes": 0,
                "next_open_comparisons": 0,
                "next_open_flags": 0,
            },
        }

    # Deliberately swap this mock's membership maps. Attribution must follow
    # requirements, not a guessed decision-year cutoff. This is not a claim
    # that the real calendar would return these intentionally inverted maps.
    original_requirements = fixture.calendar.requirements

    def swapped_requirements(start, end, horizons, *, warmup_months):
        other_start, other_end = (
            (date(2018, 1, 1), diagnostic.END) if end.year == 2017
            else (date(2007, 6, 1), date(2017, 12, 31))
        )
        return original_requirements(other_start, other_end, horizons, warmup_months=warmup_months)

    fixture.calendar.requirements = swapped_requirements
    swapped = diagnostic.run(fixture.snapshot, fixture.reference, "fictional-calendar.json")
    for symbol in ("ALFA", "BETA"):
        assert swapped["symbols"][symbol]["by_period"] == {
            "development": report["symbols"][symbol]["by_period"]["validation"],
            "validation": report["symbols"][symbol]["by_period"]["development"],
        }


@pytest.mark.parametrize("missing_from", ["market", "distributions"])
def test_fictional_run_rejects_missing_symbol_session(fictional_run, missing_from):
    fixture = fictional_run
    target = getattr(fixture, missing_from)
    target.symbol_dates["BETA"] = tuple(sorted(fixture.expected - {fixture.execution}))
    with pytest.raises(ValueError, match="session coverage mismatch"):
        diagnostic.run(fixture.snapshot, fixture.reference, "fictional-calendar.json")


def test_fictional_calendar_cannot_authorize_real_source_diagnostic(fictional_run):
    fixture = fictional_run
    fixture.calendar.synthetic = True
    with pytest.raises(ValueError, match="non-synthetic calendar"):
        diagnostic.run(fixture.snapshot, fixture.reference, "fictional-calendar.json")
    assert fixture.loader_calls == []
