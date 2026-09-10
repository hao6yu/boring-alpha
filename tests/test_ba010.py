"""Offline, synthetic BA-010 causality, fill, ledger, halt and chronology tests."""
from __future__ import annotations

from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ba010


def session(day="2021-01-04", *, direction=1):
    bars = [[minute, 10020, 10040, 10000, 10020, 10] for minute in range(570, 600)]
    bars += [[minute, 10050, 10055, 10045, 10050, 10] for minute in range(600, 960)]
    result = {"date": day, "symbol": "MESH1", "instrument_id": 123, "bars": bars}
    set_bar(result, 600, 10040, 10043, 10035, 10041)
    set_bar(result, 601, 10042, 10044, 10035, 10042)
    set_bar(result, 602, 10042, 10044, 10035, 10042)
    set_bar(result, 955, 10070, 10075, 10065, 10070)
    if direction == -1:
        result["bars"] = [[m, 20040-o, 20040-l, 20040-h, 20040-c, v]
                          for m, o, h, l, c, v in result["bars"]]
    return result


def set_bar(row, minute, opening, high, low, close):
    row["bars"] = [bar if bar[0] != minute else [minute, opening, high, low, close, 10]
                   for bar in row["bars"]]


def remove(row, *minutes):
    row["bars"] = [bar for bar in row["bars"] if bar[0] not in minutes]


def manifest_fixture(root, *, profitable=True):
    calendar = root / "calendar.json"
    calendar.write_text(json.dumps([{"date": f"{year}-01-04", "full_session": True}
                                    for year in range(2021, 2026)]))
    years = {}
    for year in (2021, 2022, 2023):
        row = session(f"{year}-01-04")
        if not profitable:
            set_bar(row, 602, 10042, 10044, 10019, 10030)
        source = root / f"sessions-{year}.jsonl.gz"
        with gzip.open(source, "wt") as handle:
            handle.write(json.dumps(row) + "\n")
        years[str(year)] = {"file": source.name, "sha256": ba010.sha256(source), "full_sessions": 1}
    # Intentionally absent holdout files: even hash verification must wait for OOS permission.
    for year in (2024, 2025):
        years[str(year)] = {"file": f"DO-NOT-OPEN-{year}.jsonl.gz", "sha256": "0" * 64, "full_sessions": 1}
    manifest = {"schema": "ba010-inputs-v1", "years": years,
                "audit": {"reconciled": True}, "calendar": {"schedule_file": calendar.name,
                    "sha256": ba010.sha256(calendar), "exchange_calendars_version": "synthetic"}}
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


class SignalAndCausality(unittest.TestCase):
    def test_first_close_and_two_minute_entry(self):
        result = ba010.run_account([session()])
        trade = result["trades"][0]
        self.assertEqual((trade["signal_minute"], trade["entry_minute"]), (600, 602))
        self.assertEqual(trade["entry_raw_ticks"], 10042)
        self.assertEqual(trade["planned_loss_cents"], 2997)

    def test_wick_outside_is_not_a_close_breakout(self):
        row = session()
        set_bar(row, 600, 10020, 10100, 10010, 10040)
        order, _ = ba010.candidate_order(row)
        self.assertEqual(order["signal_minute"], 601)
        self.assertEqual(order["entry_minute"], 603)

    def test_latest_signal_1128_and_entry_1130(self):
        row = session()
        for minute in range(600, 688):
            set_bar(row, minute, 10020, 10040, 10000, 10020)
        order, _ = ba010.candidate_order(row)
        self.assertEqual((order["signal_minute"], order["entry_minute"]), (688, 690))
        set_bar(row, 688, 10020, 10040, 10000, 10020)
        self.assertEqual(ba010.candidate_order(row), (None, "no_breakout"))

    def test_ineligible_first_breakout_consumes_day(self):
        row = session()
        set_bar(row, 600, 10040, 10120, 10035, 10110)
        self.assertEqual(ba010.candidate_order(row), (None, "first_breakout_outside_risk_budget"))
        self.assertEqual(ba010.run_account([row])["summary"]["trades"], 0)

    def test_risk_filter_cent_boundaries_use_base_friction(self):
        for high, expected in ((10032, False), (10034, True), (10112, True), (10114, False)):
            row = session()
            for minute in range(570, 600):
                set_bar(row, minute, 10010, high, 10000, 10010)
            set_bar(row, 600, high, high+2, high-1, high+1)
            order, _ = ba010.candidate_order(row)
            self.assertEqual(order is not None, expected)
            # A stress friction calculation must not change eligibility.
            self.assertEqual(bool(ba010.run_account([row], slippage_ticks=2)["trades"]), expected)

    def test_midpoint_rounds_adversely_for_both_directions(self):
        long = session()
        for minute in range(570, 600):
            set_bar(long, minute, 10020, 10041, 10000, 10020)
        set_bar(long, 600, 10040, 10043, 10035, 10042)
        short = deepcopy(long)
        set_bar(short, 600, 10000, 10005, 9998, 9999)
        self.assertEqual(ba010.candidate_order(long)[0]["stop_ticks"], 10020)
        self.assertEqual(ba010.candidate_order(short)[0]["stop_ticks"], 10021)

    def test_preentry_missing_minutes_abstain_causally(self):
        for minute, reason in ((580, "missing_opening_range"), (600, "missing_signal_history"),
                               (601, "missing_preentry_minute")):
            row = session()
            remove(row, minute)
            self.assertEqual(ba010.run_account([row])["days"][0]["abstention_reason"], reason)

    def test_committed_entry_and_held_gaps_refuse(self):
        for minute in (602, 603, 900, 955):
            row = session()
            remove(row, minute)
            with self.assertRaises(ba010.Refusal):
                ba010.run_account([row])

    def test_missing_future_after_exit_cannot_erase_trade(self):
        row = session()
        set_bar(row, 602, 10042, 10044, 10019, 10030)
        full = ba010.run_account([row])
        remove(row, *range(603, 960))
        self.assertEqual(ba010.run_account([row]), full)


class ExecutionAndAccounting(unittest.TestCase):
    def test_exact_long_short_ticks_fees_and_overhead(self):
        for direction in (1, -1):
            result = ba010.run_account([session(direction=direction)])
            trade = result["trades"][0]
            self.assertEqual(trade["gross_cents"], 3500)
            self.assertEqual(trade["fees_cents"], 122)
            self.assertEqual(trade["slippage_cents"], 250)
            self.assertEqual(trade["net_cents"], 3128)
            self.assertEqual(result["summary"]["net_cents"], 2973)
            self.assertEqual(result["summary"]["ending_equity_cents"], 502973)

    def test_stress_preserves_orders_and_adds_two_ticks_total(self):
        rows = [session(), session("2021-01-05", direction=-1)]
        base = ba010.run_account(rows)
        stress = ba010.run_account(rows, slippage_ticks=2)
        self.assertEqual([(t["date"], t["entry_minute"], t["exit_minute"]) for t in base["trades"]],
                         [(t["date"], t["entry_minute"], t["exit_minute"]) for t in stress["trades"]])
        self.assertEqual(base["summary"]["net_cents"] - stress["summary"]["net_cents"], 500)

    def test_entry_bar_touch_and_adverse_stop_gap(self):
        for direction in (1, -1):
            row = session(direction=direction)
            if direction == 1:
                set_bar(row, 602, 10042, 10044, 10020, 10030)
                expected_fill = 10019
            else:
                set_bar(row, 602, 9998, 10020, 9996, 10010)
                expected_fill = 10021
            trade = ba010.run_account([row])["trades"][0]
            self.assertEqual(trade["exit_reason"], "stop_touch")
            self.assertEqual(trade["exit_minute"], 602)
            self.assertEqual(trade["exit_fill_ticks"], expected_fill)
            row = session(direction=direction)
            if direction == 1:
                set_bar(row, 603, 10000, 10010, 9990, 10000)
                expected_fill = 9999
            else:
                set_bar(row, 603, 10040, 10050, 10030, 10040)
                expected_fill = 10041
            trade = ba010.run_account([row])["trades"][0]
            self.assertEqual(trade["exit_reason"], "stop_gap")
            self.assertEqual(trade["exit_fill_ticks"], expected_fill)

    def test_entry_gap_overrun_is_retained(self):
        row = session()
        set_bar(row, 602, 10100, 10110, 10020, 10030)
        trade = ba010.run_account([row])["trades"][0]
        self.assertEqual(trade["planned_loss_cents"], 2997)
        self.assertEqual(trade["entry_planned_loss_cents"], 10372)
        self.assertEqual(trade["risk_overrun_cents"], 2872)
        self.assertEqual(trade["net_cents"], -10372)

    def test_entry_through_stop_flattens_at_open_with_both_frictions(self):
        row = session()
        set_bar(row, 602, 9900, 10000, 9800, 9950)
        trade = ba010.run_account([row])["trades"][0]
        self.assertEqual(trade["exit_reason"], "entry_through_stop")
        self.assertEqual(trade["exit_raw_ticks"], trade["entry_raw_ticks"])
        self.assertEqual(trade["net_cents"], -372)

    def test_time_exit_precedes_later_stop_and_range(self):
        row = session()
        set_bar(row, 955, 10070, 20000, 5000, 6000)
        result = ba010.run_account([row])
        self.assertEqual(result["trades"][0]["exit_reason"], "time_exit")
        self.assertEqual(result["trades"][0]["net_cents"], 3128)
        self.assertLess(result["summary"]["intrabar_conservative_drawdown_upper_bound_cents"], 10000)

    def test_monthly_fees_once_and_annual_equity_carries(self):
        result = ba010.run_account([session(), session("2021-01-05"), session("2021-02-01"), session("2022-01-04")])
        self.assertEqual(result["summary"]["operating_fees_cents"], 465)
        self.assertEqual(result["days"][3]["equity_start_cents"], result["days"][2]["equity_end_cents"])
        self.assertEqual(result["summary"]["net_cents"], 4*3128-465)


class CapitalAndDrawdown(unittest.TestCase):
    def test_floor_permanently_idles_and_monthly_charges_continue(self):
        row = session()
        set_bar(row, 602, 10700, 10710, 10020, 10030)
        rows = [row, session("2021-02-01"), session("2022-01-04")]
        pilot = ba010.run_account(rows)
        self.assertEqual(pilot["summary"]["halt"]["reason"], "capital_floor")
        self.assertEqual(pilot["summary"]["trades"], 1)
        self.assertEqual(pilot["summary"]["operating_fees_cents"], 465)
        self.assertEqual(pilot["summary"]["yearly"]["2022"]["net_cents"], -155)
        diagnostic = ba010.run_account(rows, constrained=False)
        self.assertEqual(diagnostic["summary"]["trades"], 3)
        self.assertIsNone(diagnostic["summary"]["halt"])

    def test_minute_close_drawdown_exits_next_open_and_halts(self):
        row = session()
        set_bar(row, 603, 11000, 11010, 10990, 11000)
        set_bar(row, 604, 10040, 10060, 10030, 10040)
        set_bar(row, 605, 10039, 10100, 9990, 10020)
        result = ba010.run_account([row, session("2022-01-04")])
        trade = result["trades"][0]
        self.assertEqual((trade["exit_minute"], trade["exit_raw_ticks"], trade["exit_reason"]),
                         (605, 10039, "drawdown_next_open"))
        self.assertEqual(result["summary"]["halt"]["minute"], 604)
        self.assertEqual(result["summary"]["trades"], 1)
        self.assertGreaterEqual(result["summary"]["observed_liquidation_drawdown_cents"], 120000)
        self.assertLess(result["summary"]["closed_equity_drawdown_cents"], 10000)

    def test_stop_precedes_minute_close_drawdown_and_flat_loss_still_halts(self):
        row = session()
        set_bar(row, 603, 11000, 11010, 10990, 11000)
        set_bar(row, 604, 10040, 10060, 10019, 10040)
        result = ba010.run_account([row])
        self.assertEqual(result["trades"][0]["exit_reason"], "stop_touch")
        self.assertEqual(result["summary"]["halt"]["reason"], "drawdown")

    def test_intrabar_high_is_bound_not_an_observed_close_or_halt(self):
        row = session()
        set_bar(row, 603, 10050, 12000, 10030, 10050)
        result = ba010.run_account([row])
        summary = result["summary"]
        self.assertIsNone(summary["halt"])
        self.assertLess(summary["observed_liquidation_drawdown_cents"], 10000)
        self.assertGreater(summary["intrabar_conservative_drawdown_upper_bound_cents"], 200000)
        self.assertIs(summary["intrabar_bound_is_exact"], False)

    def test_stress_can_halt_earlier_without_changing_candidate(self):
        rows = []
        for day in range(4, 17):
            row = session(f"2021-01-{day:02d}")
            set_bar(row, 602, 10066, 10067, 10020, 10030)
            rows.append(row)
        base = ba010.run_account(rows)
        stress = ba010.run_account(rows, slippage_ticks=2)
        self.assertGreater(base["summary"]["trades"], stress["summary"]["trades"])
        self.assertLess(stress["summary"]["halt"]["date"], base["summary"]["halt"]["date"])


class AuditAndEvaluationOrder(unittest.TestCase):
    def test_invalid_ticks_ohlc_ids_and_duplicate_minutes_refuse(self):
        for mutation in (lambda r: r["bars"][0].__setitem__(1, 10020.0),
                         lambda r: r["bars"][0].__setitem__(2, 9999),
                         lambda r: r["bars"][0].__setitem__(5, 0),
                         lambda r: r.__setitem__("symbol", "MES.fake"),
                         lambda r: r.__setitem__("instrument_id", "123"),
                         lambda r: r["bars"].insert(1, r["bars"][0])):
            row = session()
            mutation(row)
            with self.assertRaises(ba010.Refusal):
                ba010.run_account([row])

    def test_development_never_opens_holdout_and_reconciles_ledgers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = manifest_fixture(root)
            with patch.object(ba010, "stationary_bootstrap", side_effect=AssertionError("No development bootstrap")):
                report = ba010.run_stage(path, output_root=root / "output")
            self.assertTrue(report["development_passed"])
            self.assertEqual(report["years"], [2021, 2022, 2023])
            self.assertEqual(set(report["models"]), {"base_pilot", "stress_pilot", "base_unconstrained", "stress_unconstrained"})
            ledger = root / "output/development/day-ledger.jsonl"
            days = [json.loads(line) for line in ledger.read_text().splitlines()]
            for model, summary in report["models"].items():
                self.assertEqual(sum(day["net_cents"] for day in days if day["model"] == model), summary["net_cents"])
            with self.assertRaisesRegex(ba010.Refusal, "overwrite"):
                ba010.run_stage(path, output_root=root / "output")

    def test_failed_development_blocks_oos_before_missing_holdout_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = manifest_fixture(root, profitable=False)
            report = ba010.run_stage(path, output_root=root / "output")
            self.assertFalse(report["development_passed"])
            self.assertEqual(report["status"], "DEVELOPMENT_FAIL")
            with self.assertRaisesRegex(ba010.Refusal, "Development did not pass"):
                ba010.run_stage(path, stage="oos", output_root=root / "output",
                                development_report=root / "output/development/report.json")

    def test_oos_requires_passed_unchanged_development_freeze(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = manifest_fixture(root)
            with self.assertRaisesRegex(ba010.Refusal, "prior passed"):
                ba010.run_stage(path, stage="oos", output_root=root / "output")
            report = ba010.run_stage(path, output_root=root / "output")
            report["freeze"]["engine_sha256"] = "wrong"
            prior = root / "changed-development.json"
            prior.write_text(json.dumps(report))
            with self.assertRaisesRegex(ba010.Refusal, "changed since development"):
                ba010.run_stage(path, stage="oos", output_root=root / "output", development_report=prior)

    def test_hash_mismatch_and_unreconciled_audit_refuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = manifest_fixture(root)
            with (root / "sessions-2021.jsonl.gz").open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(ba010.Refusal, "hash mismatch"):
                ba010.run_stage(path, output_root=root / "output")
            manifest = json.loads(path.read_text())
            manifest["audit"]["reconciled"] = False
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ba010.Refusal, "not fully reconciled"):
                ba010.run_stage(path, output_root=root / "output")

    def test_hashed_calendar_dates_must_match_not_just_session_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = manifest_fixture(root)
            calendar_path = root / "calendar.json"
            calendar = json.loads(calendar_path.read_text())
            calendar[0]["date"] = "2021-01-05"
            calendar_path.write_text(json.dumps(calendar))
            manifest = json.loads(path.read_text())
            manifest["calendar"]["sha256"] = ba010.sha256(calendar_path)
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ba010.Refusal, "hashed full-session calendar"):
                ba010.run_stage(path, output_root=root / "output")

    def test_oos_halt_carries_into_2025_and_runs_prespecified_bootstraps(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = manifest_fixture(root)
            manifest = json.loads(path.read_text())
            manifest["source_quote_usd"] = "6.45"
            for year in (2024, 2025):
                row = session(f"{year}-01-04")
                if year == 2024:
                    set_bar(row, 602, 10700, 10710, 10020, 10030)
                source = root / f"sessions-{year}.jsonl.gz"
                with gzip.open(source, "wt") as handle:
                    handle.write(json.dumps(row) + "\n")
                manifest["years"][str(year)] = {"file": source.name,
                    "sha256": ba010.sha256(source), "full_sessions": 1}
            path.write_text(json.dumps(manifest))
            ba010.run_stage(path, output_root=root / "output")
            report = ba010.run_stage(path, stage="oos", output_root=root / "output",
                                    development_report=root / "output/development/report.json")
            self.assertEqual(report["status"], "OOS_FAIL")
            self.assertEqual(report["models"]["base_pilot"]["trades"], 1)
            self.assertEqual(report["models"]["base_pilot"]["yearly"]["2025"]["net_cents"], -155)
            self.assertEqual(report["models"]["base_unconstrained"]["trades"], 2)
            self.assertEqual(set(report["bootstrap"]), {"5", "10", "20"})
            self.assertEqual(report["bootstrap"]["10"]["draws"], 10000)
            self.assertEqual(report["bootstrap"]["10"]["seed"], 1010)
            self.assertEqual(report["research_acquisition"]["source_quote_usd"], "6.45")

    def test_stationary_bootstrap_uses_daily_dollars_and_repeats(self):
        first = ba010.stationary_bootstrap([100, -155, 0, 300], block_length=10,
                                           cash_gain_cents=40, draws=1000, annual_sessions=2)
        second = ba010.stationary_bootstrap([100, -155, 0, 300], block_length=10,
                                            cash_gain_cents=40, draws=1000, annual_sessions=2)
        self.assertEqual(first, second)
        self.assertEqual(first["mean_daily_pnl_dollars"], 0.6125)
        self.assertEqual(first["cash_6pct_gain_per_session_dollars"], 0.1)
        constant = ba010.stationary_bootstrap([100] * 10, block_length=5, cash_gain_cents=0, draws=100)
        self.assertEqual(constant["mean_daily_95pct_dollars"], [1.0, 1.0])
        self.assertEqual(constant["annualized_arithmetic_pnl_95pct_dollars"], [5.0, 5.0])


if __name__ == "__main__":
    unittest.main()
