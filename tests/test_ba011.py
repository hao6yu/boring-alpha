"""Offline synthetic BA-011 timing, roll, account, provenance and stage tests."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ba011


def session(day="2021-01-04", *, direction=1):
    row = {"date": day, "symbol": "MESH1", "instrument_id": 123,
           "previous_session_date": (date.fromisoformat(day) - timedelta(days=1)).isoformat(),
           "previous_session_full": True, "previous_close_ticks": 10000,
           "previous_symbol": "MESH1", "previous_instrument_id": 123,
           "bars": [[minute, 10050, 10055, 10045, 10050, 10] for minute in range(570, 961)]}
    set_bar(row, 960, 10080, 10085, 10075, 10080)
    if direction == -1:
        row["bars"] = [[m, 20000-o, 20000-l, 20000-h, 20000-c, v]
                       for m, o, h, l, c, v in row["bars"]]
    return row


def set_bar(row, minute, opening, high, low, close):
    row["bars"] = [bar if bar[0] != minute else [minute, opening, high, low, close, 10]
                   for bar in row["bars"]]


def remove(row, *minutes):
    row["bars"] = [bar for bar in row["bars"] if bar[0] not in minutes]


def manifest_fixture(root, *, profitable=True, stage="development", dev_manifest=None):
    """Five-year calendar metadata, but create price files for only one stage."""
    root.mkdir(parents=True, exist_ok=True)
    calendar = [{"date": "2020-12-31", "full_session": True}]
    for year in range(2021, 2026):
        calendar += [{"date": f"{year}-01-04", "full_session": True},
                     {"date": f"{year}-01-05", "full_session": True}]
    calendar_path = root / "calendar.json"
    calendar_path.write_text(json.dumps(calendar))
    predecessors = {row["date"]: calendar[index - 1] for index, row in enumerate(calendar) if index}
    years = {}
    rows = {}
    warmup = json.loads(dev_manifest.read_text())["boundary_reference"] if dev_manifest else None
    for year in ba011.YEARS[stage]:
        for day in (f"{year}-01-04", f"{year}-01-05"):
            row = session(day)
            if not profitable:
                set_bar(row, 960, 10020, 10025, 10015, 10020)
            previous = predecessors[day]
            prior_row = rows.get(previous["date"])
            reference = {"close_ticks": 10050 if prior_row else None,
                         "symbol": "MESH1" if prior_row else None,
                         "instrument_id": 123 if prior_row else None}
            if warmup and previous["date"] == warmup["date"]:
                reference = warmup
            row.update({"previous_session_date": previous["date"],
                        "previous_session_full": previous["full_session"],
                        "previous_close_ticks": reference["close_ticks"],
                        "previous_symbol": reference["symbol"],
                        "previous_instrument_id": reference["instrument_id"]})
            # Each available reference is 10050; keep the signal strictly positive.
            set_bar(row, 929, 10060, 10065, 10055, 10060)
            rows[day] = row
        source = root / f"sessions-{year}.jsonl.gz"
        with gzip.open(source, "wt") as handle:
            for day in (f"{year}-01-04", f"{year}-01-05"):
                handle.write(json.dumps(rows[day]) + "\n")
        years[str(year)] = {"file": source.name, "sha256": ba011.sha256(source), "full_sessions": 2}
    last = rows[max(rows)]
    manifest = {"schema": "ba011-inputs-v1", "stage": stage, "years": years,
                "source_manifest_sha256": "a" * 64, "source_quote_usd": 149.38,
                "audit": {"reconciled": True}, "calendar": {"schedule_file": calendar_path.name,
                    "sha256": ba011.sha256(calendar_path), "exchange_calendars_version": "synthetic"},
                "boundary_reference": {"date": last["date"], "full_session": True,
                    "symbol": last["symbol"], "instrument_id": last["instrument_id"], "close_ticks": 10050}}
    if dev_manifest:
        manifest["development_input"] = {"file": str(dev_manifest), "sha256": ba011.sha256(dev_manifest)}
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def rewrite_year(path, year, mutate):
    manifest = json.loads(path.read_text())
    entry = manifest["years"][str(year)]
    source = path.parent / entry["file"]
    with gzip.open(source, "rt") as handle:
        rows = [json.loads(line) for line in handle]
    mutate(rows)
    with gzip.open(source, "wt") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    entry["sha256"] = ba011.sha256(source)
    path.write_text(json.dumps(manifest))


class TimingAndSignal(unittest.TestCase):
    def test_positive_long_negative_and_equal_short(self):
        for close, direction in ((10001, 1), (9999, -1), (10000, -1)):
            row = session()
            set_bar(row, 929, close, close+5, close-5, close)
            order, reason = ba011.candidate_order(row)
            self.assertIsNone(reason)
            self.assertEqual(order["direction"], direction)
            self.assertEqual(order["signal_change_ticks"], close-10000)
            self.assertEqual((order["signal_minute"], order["entry_minute"]), (929, 931))

    def test_delay_and_exit_use_exact_opens(self):
        row = session()
        set_bar(row, 930, 12000, 12050, 11900, 12020)
        set_bar(row, 931, 10040, 10055, 10030, 10050)
        set_bar(row, 959, 10050, 11000, 10045, 10070)
        trade = ba011.run_account([row])["trades"][0]
        self.assertEqual((trade["entry_raw_ticks"], trade["exit_raw_ticks"], trade["exit_minute"]), (10040, 10080, 960))

    def test_no_technical_stop_or_signal_magnitude_filter(self):
        row = session()
        row["previous_close_ticks"] = 1
        set_bar(row, 932, 10050, 15000, 5000, 10050)
        result = ba011.run_account([row])
        self.assertEqual(result["trades"][0]["exit_reason"], "time_exit")
        self.assertIsNone(result["summary"]["halt"])
        self.assertNotIn("stop_ticks", result["trades"][0])

    def test_missing_unneeded_early_history_does_not_change_trade(self):
        row = session()
        full = ba011.run_account([row])
        remove(row, *range(570, 929))
        self.assertEqual(ba011.run_account([row]), full)

    def test_missing_signal_and_preentry_abstain_causally(self):
        for minute, reason in ((929, "missing_signal_minute"), (930, "missing_preentry_minute")):
            row = session()
            remove(row, minute, *range(931, 961))
            self.assertEqual(ba011.run_account([row])["days"][0]["abstention_reason"], reason)

    def test_missing_entry_and_every_held_minute_refuse(self):
        for minute in range(931, 961):
            with self.subTest(minute=minute):
                row = session()
                remove(row, minute)
                with self.assertRaises(ba011.Refusal):
                    ba011.run_account([row])

    def test_missing_nonfull_and_both_roll_identifiers_abstain(self):
        for field, value, reason in (("previous_close_ticks", None, "missing_previous_close"),
                ("previous_session_full", False, "previous_session_not_full"),
                ("previous_symbol", "MESM1", "previous_contract_mismatch"),
                ("previous_instrument_id", 456, "previous_contract_mismatch")):
            row = session()
            row[field] = value
            remove(row, *range(931, 961))
            result = ba011.run_account([row])
            self.assertEqual(result["days"][0]["abstention_reason"], reason)
            self.assertEqual(result["trades"], [])


class FillsAndAccount(unittest.TestCase):
    def test_exact_long_short_friction_and_monthly_fee(self):
        for direction in (1, -1):
            result = ba011.run_account([session(direction=direction)])
            trade = result["trades"][0]
            self.assertEqual((trade["gross_cents"], trade["fees_cents"], trade["slippage_cents"], trade["net_cents"]), (3750, 122, 250, 3378))
            self.assertEqual(result["summary"]["net_cents"], 3223)
            self.assertEqual(result["summary"]["ending_equity_cents"], 503223)

    def test_stress_adds_exactly_two_ticks_total_without_signal_change(self):
        rows = [session(), session("2021-01-05", direction=-1)]
        base = ba011.run_account(rows)
        stress = ba011.run_account(rows, slippage_ticks=2)
        self.assertEqual([t["direction"] for t in base["trades"]], [t["direction"] for t in stress["trades"]])
        self.assertEqual(base["summary"]["net_cents"]-stress["summary"]["net_cents"], 500)

    def test_fees_once_each_observed_month_and_no_annual_reset(self):
        result = ba011.run_account([session(), session("2021-01-05"), session("2021-02-01"), session("2022-01-04")])
        self.assertEqual(result["summary"]["operating_fees_cents"], 465)
        self.assertEqual(result["days"][3]["equity_start_cents"], result["days"][2]["equity_end_cents"])
        self.assertEqual(result["summary"]["net_cents"], 4*3378-465)
        self.assertEqual(result["summary"]["yearly"]["2022"]["initial_equity_cents"], result["days"][3]["equity_start_cents"])

    def test_time_exit_excludes_exit_bar_range_and_close(self):
        row = session()
        original = ba011.run_account([row])
        set_bar(row, 960, 10080, 50000, 100, 200)
        self.assertEqual(ba011.run_account([row]), original)

    def test_capital_floor_permanent_halt_and_fees_continue(self):
        row = session()
        set_bar(row, 960, 9426, 9430, 9420, 9426)
        rows = [row, session("2021-02-01"), session("2022-01-04")]
        pilot = ba011.run_account(rows)
        self.assertEqual(pilot["summary"]["halt"]["reason"], "capital_floor")
        self.assertEqual(pilot["summary"]["trades"], 1)
        self.assertEqual(pilot["summary"]["operating_fees_cents"], 465)
        self.assertEqual(pilot["summary"]["yearly"]["2022"]["net_cents"], -155)
        unrestricted = ba011.run_account(rows, constrained=False)
        self.assertEqual(unrestricted["summary"]["trades"], 3)
        self.assertIsNone(unrestricted["summary"]["halt"])

    def test_account_drawdown_triggers_at_exact_threshold_next_open(self):
        row = session()
        set_bar(row, 932, 10850, 10855, 10845, 10850)
        set_bar(row, 933, 10050, 10055, 10045, 10050)
        set_bar(row, 934, 10049, 30000, 100, 10050)
        result = ba011.run_account([row, session("2022-01-04")])
        trade = result["trades"][0]
        self.assertEqual((trade["exit_minute"], trade["exit_raw_ticks"], trade["exit_reason"]), (934, 10049, "drawdown_next_open"))
        self.assertEqual(result["summary"]["halt"]["minute"], 933)
        self.assertEqual(result["summary"]["trades"], 1)
        self.assertGreaterEqual(result["summary"]["observed_liquidation_drawdown_cents"], 100000)
        self.assertLess(result["summary"]["closed_equity_drawdown_cents"], 1000)
        self.assertLess(result["summary"]["intrabar_conservative_drawdown_upper_bound_cents"], 200000)

    def test_missing_future_after_risk_exit_is_irrelevant_only_when_flat(self):
        row = session()
        set_bar(row, 932, 10850, 10855, 10845, 10850)
        set_bar(row, 933, 10050, 10055, 10045, 10050)
        full = ba011.run_account([row])
        remove(row, *range(935, 961))
        self.assertEqual(ba011.run_account([row]), full)
        with self.assertRaises(ba011.Refusal):
            ba011.run_account([row], constrained=False)
        remove(row, 934)
        with self.assertRaises(ba011.Refusal):
            ba011.run_account([row])

    def test_intrabar_extrema_are_loose_bound_not_halt_observations(self):
        row = session()
        set_bar(row, 932, 10050, 13000, 9000, 10050)
        summary = ba011.run_account([row])["summary"]
        self.assertIsNone(summary["halt"])
        self.assertLess(summary["observed_liquidation_drawdown_cents"], 1000)
        self.assertGreater(summary["intrabar_conservative_drawdown_upper_bound_cents"], 400000)
        self.assertIs(summary["intrabar_bound_is_exact"], False)

    def test_flat_liquidation_gap_checks_drawdown_and_halts(self):
        row = session()
        set_bar(row, 960, 9000, 9005, 8995, 9000)
        summary = ba011.run_account([row])["summary"]
        self.assertEqual(summary["halt"]["reason"], "drawdown")
        self.assertEqual(summary["halt"]["minute"], 960)

    def test_worst_trade_concentration_and_ledger_reconcile(self):
        rows = [session(), session("2021-01-05"), session("2022-01-04")]
        set_bar(rows[1], 960, 10040, 10045, 10035, 10040)
        result = ba011.run_account(rows)
        summary = result["summary"]
        self.assertEqual(summary["worst_trade"]["date"], "2021-01-05")
        self.assertEqual(summary["top_five_share_positive_trade_pnl"], 1)
        self.assertEqual(summary["gross_cents"]-summary["trading_friction_cents"]-summary["operating_fees_cents"], summary["net_cents"])
        self.assertEqual(sum(day["net_cents"] for day in result["days"]), summary["net_cents"])


class Validation(unittest.TestCase):
    def test_invalid_structural_values_refuse(self):
        for mutate in (lambda r: r["bars"][0].__setitem__(1, 10050.0),
                       lambda r: r["bars"][0].__setitem__(2, 9999),
                       lambda r: r["bars"][0].__setitem__(5, 0),
                       lambda r: r.__setitem__("symbol", "MES.v.0"),
                       lambda r: r.__setitem__("instrument_id", True),
                       lambda r: r.__setitem__("previous_close_ticks", 10000.0),
                       lambda r: r.__setitem__("previous_session_date", r["date"]),
                       lambda r: r.__setitem__("previous_session_full", 1),
                       lambda r: r["bars"].append([961, 10050, 10055, 10045, 10050, 10]),
                       lambda r: r["bars"].insert(1, r["bars"][0])):
            row = session()
            mutate(row)
            with self.assertRaises(ba011.Refusal):
                ba011.run_account([row])

    def test_duplicate_sessions_refuse(self):
        with self.assertRaises(ba011.Refusal):
            ba011.run_account([session(), session()])

    def test_calendar_coverage_counts_and_true_predecessor_required(self):
        for mutate in (lambda rows: rows.pop(),
                       lambda rows: rows[1].__setitem__("previous_session_date", "2020-12-31"),
                       lambda rows: rows[1].__setitem__("previous_session_full", False),
                       lambda rows: rows[1].__setitem__("previous_close_ticks", 10049),
                       lambda rows: rows[1].__setitem__("previous_close_ticks", None),
                       lambda rows: rows[1].__setitem__("previous_symbol", "MESM1")):
            with tempfile.TemporaryDirectory() as tmp:
                path = manifest_fixture(Path(tmp))
                rewrite_year(path, 2021, mutate)
                with self.assertRaises(ba011.Refusal):
                    ba011.read_sessions(path, ba011.read_manifest(path), ba011.YEARS["development"])

    def test_skip_over_half_day_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = manifest_fixture(Path(tmp))
            manifest = json.loads(path.read_text())
            calendar = path.parent / manifest["calendar"]["schedule_file"]
            rows = json.loads(calendar.read_text())
            rows.insert(1, {"date": "2021-01-01", "full_session": False})
            calendar.write_text(json.dumps(rows))
            manifest["calendar"]["sha256"] = ba011.sha256(calendar)
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ba011.Refusal, "predecessor"):
                ba011.read_sessions(path, manifest, ba011.YEARS["development"])

    def test_final_boundary_must_match_last_session_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = manifest_fixture(Path(tmp))
            manifest = ba011.read_manifest(path)
            manifest["boundary_reference"]["close_ticks"] += 1
            with self.assertRaisesRegex(ba011.Refusal, "boundary"):
                ba011.read_sessions(path, manifest, ba011.YEARS["development"])


class FrozenEvaluation(unittest.TestCase):
    def test_development_failure_keeps_holdout_unopened_and_output_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = manifest_fixture(root / "inputs", profitable=False)
            output = root / "out"
            report = ba011.run_stage(path, output_root=output)
            self.assertEqual(report["status"], "DEVELOPMENT_FAIL")
            self.assertFalse(report["holdout_permitted"])
            self.assertEqual(set(report["models"]), {"base_pilot", "stress_pilot", "base_unconstrained", "stress_unconstrained"})
            with self.assertRaisesRegex(ba011.Refusal, "overwrite"):
                ba011.run_stage(path, output_root=output)
            with patch.object(ba011, "read_sessions", side_effect=AssertionError("holdout opened")):
                with self.assertRaisesRegex(ba011.Refusal, "did not pass"):
                    ba011.run_stage(root / "DO-NOT-OPEN-oos-manifest.json", stage="oos", output_root=output,
                                    development_report=output / "development/report.json", development_manifest=path)

    def test_development_pass_uses_only_2021_through_2023(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = manifest_fixture(root / "inputs")
            report = ba011.run_stage(path, output_root=root / "out")
            self.assertEqual(report["status"], "DEVELOPMENT_PASS")
            self.assertEqual(report["years"], [2021, 2022, 2023])
            self.assertEqual(report["models"]["base_pilot"]["trades"], 5)
            self.assertNotIn("bootstrap", report)
            for artifact in report["artifacts"].values():
                self.assertEqual(artifact["sha256"], ba011.sha256(root / "out/development" / artifact["file"]))

    def test_freeze_detects_changed_adapter_protocol_dependencies_and_dev_inputs(self):
        for changed in ("adapter", "protocol", "dependencies", "manifest"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = manifest_fixture(root / "inputs")
                adapter, protocol = root / "adapter.py", root / "protocol.md"
                adapter.write_text("synthetic adapter v1")
                protocol.write_text("synthetic protocol v1")
                with patch.object(ba011, "ADAPTER", adapter), patch.object(ba011, "PROTOCOL", protocol):
                    ba011.run_stage(path, output_root=root / "out")
                    report = root / "out/development/report.json"
                    self.assertEqual(ba011.validate_development(report, path)["status"], "DEVELOPMENT_PASS")
                    if changed == "adapter":
                        adapter.write_text("synthetic adapter v2")
                    elif changed == "protocol":
                        protocol.write_text("synthetic protocol v2")
                    elif changed == "manifest":
                        path.write_text(path.read_text() + "\n")
                    if changed == "dependencies":
                        with patch.object(ba011, "version", return_value="changed"):
                            with self.assertRaisesRegex(ba011.Refusal, "changed"):
                                ba011.validate_development(report, path)
                    else:
                        with self.assertRaisesRegex(ba011.Refusal, "changed"):
                            ba011.validate_development(report, path)

    def test_oos_accepts_distinct_manifest_but_checks_source_and_calendar_before_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dev = manifest_fixture(root / "dev-inputs")
            ba011.run_stage(dev, output_root=root / "out")
            report_path = root / "out/development/report.json"
            oos = manifest_fixture(root / "oos-inputs", stage="oos", dev_manifest=dev)
            report = ba011.run_stage(oos, stage="oos", output_root=root / "out",
                                     development_report=report_path, development_manifest=dev)
            self.assertEqual(report["years"], [2024, 2025])
            self.assertEqual(report["status"], "OOS_FAIL")
            self.assertEqual(report["models"]["base_pilot"]["trades"], 4)
            self.assertEqual(report["models"]["base_pilot"]["initial_equity_cents"], 500000)
            self.assertEqual(list(report["bootstrap"]), ["10", "5", "20"])
            self.assertEqual(report["bootstrap"]["10"]["draws"], 10000)
            self.assertEqual(report["bootstrap"]["10"]["seed"], 1010)
            self.assertAlmostEqual(report["cash_comparators"]["0.06"]["total_gain_cents"], 61800)
            changed = json.loads(oos.read_text())
            changed["source_manifest_sha256"] = "b" * 64
            oos.write_text(json.dumps(changed))
            with patch.object(ba011, "read_sessions", side_effect=AssertionError("holdout opened")):
                with self.assertRaisesRegex(ba011.Refusal, "changed"):
                    ba011.run_stage(oos, stage="oos", output_root=root / "other-out",
                                    development_report=report_path, development_manifest=dev)

    def test_oos_missing_gate_or_wrong_stage_refuses_before_price_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = manifest_fixture(root / "dev-inputs")
            with patch.object(ba011, "read_sessions", side_effect=AssertionError("holdout opened")):
                with self.assertRaisesRegex(ba011.Refusal, "requires"):
                    ba011.run_stage(path, stage="oos", output_root=root / "out")
            manifest = json.loads(path.read_text())
            manifest["stage"] = "oos"
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ba011.Refusal, "stage"):
                ba011.run_stage(path, output_root=root / "out")

    def test_oos_boundary_reference_cannot_be_forged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dev = manifest_fixture(root / "dev-inputs")
            ba011.run_stage(dev, output_root=root / "out")
            oos = manifest_fixture(root / "oos-inputs", stage="oos", dev_manifest=dev)
            rewrite_year(oos, 2024, lambda rows: rows[0].__setitem__("previous_close_ticks", 9999))
            with self.assertRaisesRegex(ba011.Refusal, "actual predecessor data"):
                ba011.run_stage(oos, stage="oos", output_root=root / "out",
                                development_report=root / "out/development/report.json", development_manifest=dev)


if __name__ == "__main__":
    unittest.main()
