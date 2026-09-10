#!/usr/bin/env python3
"""Frozen BA-011 late-day sign simulation. Network-free; prices are integer MES ticks.

Only the explicitly selected stage's files are opened. Development failure never
opens holdout bars. A missing executable/held minute refuses the entire verdict.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import gzip
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

try:
    from .ba010 import stationary_bootstrap
except ImportError:
    from ba010 import stationary_bootstrap

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/strategies/BA-011.md"
ADAPTER = ROOT / "tools/prepare_ba011_inputs.py"
DEPENDENCY_FILES = (ROOT / "tools/ba010.py", ROOT / "tools/audit_mes_history.py", ROOT / "pyproject.toml")
INITIAL_CENTS = 500_000
ENTRY_FLOOR_CENTS = 424_000
DRAWDOWN_LIMIT_CENTS = 100_000
TICK_CENTS = 125
FEE_SIDE_CENTS = 61
MONTHLY_CENTS = 155
YEARS = {"development": (2021, 2022, 2023), "oos": (2024, 2025)}


class Refusal(RuntimeError):
    """Unresolved inputs or an invalid chronology prevent a performance verdict."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_session(session: dict) -> None:
    try:
        session_date = date.fromisoformat(session["date"])
    except (KeyError, ValueError, TypeError) as exc:
        raise Refusal("Invalid session date") from exc
    if session_date.isoformat() != session["date"]:
        raise Refusal("Session date is not canonical ISO format")
    symbol = session.get("symbol")
    if not isinstance(symbol, str) or re.fullmatch(r"MES[HMUZ][0-9]{1,2}", symbol) is None:
        raise Refusal(f"{session_date}: expected mapped raw MES contract symbol")
    if not _integer(session.get("instrument_id")) or session["instrument_id"] <= 0:
        raise Refusal(f"{session_date}: invalid mapped instrument ID")
    previous_fields = ("previous_session_date", "previous_session_full", "previous_close_ticks",
                       "previous_symbol", "previous_instrument_id")
    if any(field not in session for field in previous_fields):
        raise Refusal(f"{session_date}: missing previous-session audit fields")
    previous_date = session["previous_session_date"]
    if previous_date is not None:
        try:
            parsed_previous = date.fromisoformat(previous_date)
        except (ValueError, TypeError) as exc:
            raise Refusal(f"{session_date}: invalid previous session date") from exc
        if parsed_previous.isoformat() != previous_date or parsed_previous >= session_date:
            raise Refusal(f"{session_date}: previous session must precede current session")
    if session["previous_session_full"] is not None and type(session["previous_session_full"]) is not bool:
        raise Refusal(f"{session_date}: invalid previous full-session flag")
    previous_close = session["previous_close_ticks"]
    if previous_close is not None and (not _integer(previous_close) or previous_close <= 0):
        raise Refusal(f"{session_date}: invalid previous close ticks")
    previous_symbol = session["previous_symbol"]
    if previous_symbol is not None and (not isinstance(previous_symbol, str) or
            re.fullmatch(r"MES[HMUZ][0-9]{1,2}", previous_symbol) is None):
        raise Refusal(f"{session_date}: invalid previous mapped raw symbol")
    previous_id = session["previous_instrument_id"]
    if previous_id is not None and (not _integer(previous_id) or previous_id <= 0):
        raise Refusal(f"{session_date}: invalid previous instrument ID")
    if previous_close is not None and any(session[field] is None for field in
            ("previous_session_date", "previous_session_full", "previous_symbol", "previous_instrument_id")):
        raise Refusal(f"{session_date}: previous close lacks auditable session/contract metadata")
    bars = session.get("bars")
    if not isinstance(bars, list):
        raise Refusal(f"{session_date}: bars must be a list")
    previous = 569
    for bar in bars:
        if not isinstance(bar, list) or len(bar) != 6 or not all(_integer(x) for x in bar):
            raise Refusal(f"{session_date}: bars must contain six integer fields")
        minute, opening, high, low, close, volume = bar
        if not 570 <= minute <= 960 or minute <= previous:
            raise Refusal(f"{session_date}: duplicate, unordered, or out-of-session minute {minute}")
        if min(opening, high, low, close) <= 0 or volume <= 0:
            raise Refusal(f"{session_date}: invalid price or volume at {minute}")
        if not low <= min(opening, close) <= max(opening, close) <= high:
            raise Refusal(f"{session_date}: invalid OHLC at {minute}")
        previous = minute


def candidate_order(session: dict) -> tuple[dict | None, str | None]:
    """Use only information available before entry; never scan future completeness."""
    if session["previous_session_date"] is None or session["previous_session_full"] is None:
        return None, "missing_previous_session"
    if not session["previous_session_full"]:
        return None, "previous_session_not_full"
    if session["previous_close_ticks"] is None:
        return None, "missing_previous_close"
    # Identity must match in both namespaces. Never calculate a return across a roll.
    if (session["previous_symbol"] != session["symbol"] or
            session["previous_instrument_id"] != session["instrument_id"]):
        return None, "previous_contract_mismatch"
    bars = {bar[0]: bar for bar in session["bars"]}
    if 929 not in bars:
        return None, "missing_signal_minute"
    if 930 not in bars:
        return None, "missing_preentry_minute"
    change = bars[929][4] - session["previous_close_ticks"]
    order = {"signal_minute": 929, "entry_minute": 931,
             "direction": 1 if change > 0 else -1,
             "signal_close_ticks": bars[929][4], "signal_change_ticks": change,
             "previous_session_date": session["previous_session_date"],
             "previous_close_ticks": session["previous_close_ticks"],
             "previous_symbol": session["previous_symbol"],
             "previous_instrument_id": session["previous_instrument_id"]}
    # A committed order cannot disappear because its execution bar is absent.
    if 931 not in bars:
        raise Refusal(f"{session['date']}: missing committed entry minute 931")
    return order, None


def run_account(sessions: Iterable[dict], *, slippage_ticks: int = 1,
                constrained: bool = True) -> dict:
    """Run one continuous, independent $5,000 fixed-one-contract account."""
    if slippage_ticks not in (1, 2):
        raise ValueError("BA-011 permits only base (1 tick) and stress (2 tick) fills")
    equity = INITIAL_CENTS
    observed_high = closed_high = upper_high = equity
    observed_dd = closed_dd = intrabar_dd = 0
    halt: dict | None = None
    trades: list[dict] = []
    days: list[dict] = []
    charged_months: set[str] = set()
    previous_date = ""
    annual: dict[str, dict] = {}
    current_annual: dict = {}

    def observe(value: int, *, flat: bool = False) -> None:
        nonlocal observed_high, observed_dd, closed_high, closed_dd, upper_high, intrabar_dd
        observed_high = max(observed_high, value)
        observed_dd = max(observed_dd, observed_high - value)
        upper_high = max(upper_high, value)
        intrabar_dd = max(intrabar_dd, upper_high - value)
        if flat:
            closed_high = max(closed_high, value)
            closed_dd = max(closed_dd, closed_high - value)
        for peak, drawdown in (("observed_high", "observed_dd"), ("upper_high", "intrabar_dd")):
            current_annual[peak] = max(current_annual[peak], value)
            current_annual[drawdown] = max(current_annual[drawdown], current_annual[peak] - value)
        if flat:
            current_annual["closed_high"] = max(current_annual["closed_high"], value)
            current_annual["closed_dd"] = max(current_annual["closed_dd"], current_annual["closed_high"] - value)

    def flat_halt(day: str, minute: int | None) -> None:
        nonlocal halt
        if not constrained or halt is not None:
            return
        if observed_high - equity >= DRAWDOWN_LIMIT_CENTS:
            halt = {"date": day, "minute": minute, "reason": "drawdown",
                    "equity_cents": equity, "high_water_cents": observed_high}
        elif equity < ENTRY_FLOOR_CENTS:
            halt = {"date": day, "minute": minute, "reason": "capital_floor",
                    "equity_cents": equity, "high_water_cents": observed_high}

    for session in sessions:
        validate_session(session)
        day = session["date"]
        if day <= previous_date:
            raise Refusal("Sessions must be unique and chronological")
        previous_date = day
        day_start = equity
        current_annual = annual.setdefault(day[:4], {
            "initial_equity_cents": equity, "observed_high": equity, "upper_high": equity,
            "closed_high": equity, "observed_dd": 0, "intrabar_dd": 0, "closed_dd": 0})
        month = day[:7]
        operating_fee = 0
        if month not in charged_months:
            operating_fee = MONTHLY_CENTS
            charged_months.add(month)
            equity -= operating_fee
            observe(equity, flat=True)
            flat_halt(day, 570)
        reason = "account_halted" if halt is not None else None
        order = None
        trade = None
        if halt is None:
            order, reason = candidate_order(session)
        if order is not None:
            flat_halt(day, order["entry_minute"])
            if halt is not None:
                order, reason = None, "account_halted"
        if order is not None:
            bars = {bar[0]: bar for bar in session["bars"]}
            direction = order["direction"]
            entry_minute = order["entry_minute"]
            entry_raw = bars[entry_minute][1]
            entry_fill = entry_raw + direction * slippage_ticks
            balance_before_entry = equity
            equity -= FEE_SIDE_CENTS
            pending_risk_exit = False
            trigger_minute = None
            raw_exit = exit_minute = exit_reason = None

            def liquidation(price: int) -> int:
                return (balance_before_entry + direction * (price - entry_fill) * TICK_CENTS
                        - slippage_ticks * TICK_CENTS - 2 * FEE_SIDE_CENTS)

            for minute in range(entry_minute, 961):
                if minute not in bars:
                    raise Refusal(f"{day}: unresolved held position at missing minute {minute}; "
                                  f"entry={entry_minute}, direction={direction}")
                _, opening, high, low, close, _ = bars[minute]
                # Open-price exits precede the remainder of this minute's range.
                if pending_risk_exit:
                    raw_exit, exit_reason = opening, "drawdown_next_open"
                elif minute == 960:
                    raw_exit, exit_reason = opening, "time_exit"
                else:
                    # This is a deliberately loose OHLC envelope. Favorable-before-adverse
                    # ordering is assumed only for this labelled bound, never executions.
                    favorable = high if direction == 1 else low
                    adverse = low if direction == 1 else high
                    upper_high = max(upper_high, liquidation(favorable))
                    intrabar_dd = max(intrabar_dd, upper_high - liquidation(adverse))
                    current_annual["upper_high"] = max(current_annual["upper_high"], liquidation(favorable))
                    current_annual["intrabar_dd"] = max(current_annual["intrabar_dd"],
                        current_annual["upper_high"] - liquidation(adverse))
                if raw_exit is not None:
                    exit_minute = minute
                    break
                mark_equity = liquidation(close)
                observe(mark_equity)
                if constrained and observed_high - mark_equity >= DRAWDOWN_LIMIT_CENTS:
                    pending_risk_exit = True
                    trigger_minute = minute
            if raw_exit is None:
                raise Refusal(f"{day}: no resolved exit")
            exit_fill = raw_exit - direction * slippage_ticks
            gross = direction * (raw_exit - entry_raw) * TICK_CENTS
            slippage = 2 * slippage_ticks * TICK_CENTS
            fees = 2 * FEE_SIDE_CENTS
            net = gross - slippage - fees
            equity = balance_before_entry + net
            observe(equity, flat=True)
            if trigger_minute is not None:
                halt = {"date": day, "minute": trigger_minute, "exit_minute": exit_minute,
                        "reason": "drawdown", "equity_cents": equity,
                        "high_water_cents": observed_high}
            flat_halt(day, exit_minute)
            trade = {"date": day, "symbol": session["symbol"],
                     "instrument_id": session["instrument_id"], **order,
                     "entry_raw_ticks": entry_raw, "entry_fill_ticks": entry_fill,
                     "exit_minute": exit_minute, "exit_raw_ticks": raw_exit,
                     "exit_fill_ticks": exit_fill, "exit_reason": exit_reason,
                     "gross_cents": gross, "fees_cents": fees, "slippage_cents": slippage,
                     "friction_cents": fees + slippage, "net_cents": net,
                     "equity_after_cents": equity}
            trades.append(trade)
        days.append({"date": day, "equity_start_cents": day_start,
                     "equity_end_cents": equity, "net_cents": equity - day_start,
                     "gross_cents": trade["gross_cents"] if trade else 0,
                     "trading_friction_cents": trade["friction_cents"] if trade else 0,
                     "operating_fee_cents": operating_fee, "traded": trade is not None,
                     "abstention_reason": reason, "halted": halt is not None})
    if not days:
        raise Refusal("No eligible sessions")
    positive = sorted((trade["net_cents"] for trade in trades if trade["net_cents"] > 0), reverse=True)
    top_five = sum(positive[:5])
    yearly = {}
    for year in sorted({day["date"][:4] for day in days}):
        year_days = [day for day in days if day["date"].startswith(year)]
        year_trades = [trade for trade in trades if trade["date"].startswith(year)]
        yearly[year] = {"net_cents": sum(day["net_cents"] for day in year_days),
                        "initial_equity_cents": annual[year]["initial_equity_cents"],
                        "ending_equity_cents": year_days[-1]["equity_end_cents"],
                        "gross_cents": sum(trade["gross_cents"] for trade in year_trades),
                        "trading_friction_cents": sum(trade["friction_cents"] for trade in year_trades),
                        "operating_fees_cents": sum(day["operating_fee_cents"] for day in year_days),
                        "trades": len(year_trades), "eligible_sessions": len(year_days),
                        "abstentions": dict(Counter(day["abstention_reason"] for day in year_days if not day["traded"])),
                        "halted_at_year_end": year_days[-1]["halted"],
                        "closed_equity_drawdown_cents": annual[year]["closed_dd"],
                        "observed_liquidation_drawdown_cents": annual[year]["observed_dd"],
                        "intrabar_conservative_drawdown_upper_bound_cents": max(annual[year]["intrabar_dd"], annual[year]["observed_dd"]),
                        "drawdown_basis": "year-start equity and within-year peaks; account limits retain all-time peaks",
                        "worst_trade": min(year_trades, key=lambda trade: trade["net_cents"], default=None)}
    summary = {"initial_equity_cents": INITIAL_CENTS, "ending_equity_cents": equity,
               "net_cents": equity - INITIAL_CENTS,
               "gross_cents": sum(trade["gross_cents"] for trade in trades),
               "trading_friction_cents": sum(trade["friction_cents"] for trade in trades),
               "operating_fees_cents": sum(day["operating_fee_cents"] for day in days),
               "trades": len(trades), "eligible_sessions": len(days), "yearly": yearly,
               "abstentions": dict(Counter(day["abstention_reason"] for day in days if not day["traded"])),
               "slippage_ticks_per_side": slippage_ticks, "constrained": constrained,
               "halt": halt, "closed_equity_drawdown_cents": closed_dd,
               "observed_liquidation_drawdown_cents": observed_dd,
               "intrabar_conservative_drawdown_upper_bound_cents": max(intrabar_dd, observed_dd),
               "intrabar_bound_is_exact": False,
               "intrabar_bound_method": "OHLC favorable before adverse envelope for held minutes; exit-open minute extrema excluded; not an executable or ordered tick path",
               "worst_trade": min(trades, key=lambda trade: trade["net_cents"], default=None),
               "top_five_winners_cents": top_five,
               "top_five_share_positive_trade_pnl": top_five / sum(positive) if positive else None,
               "top_five_share_total_net_pnl": top_five / (equity - INITIAL_CENTS) if equity > INITIAL_CENTS else None}
    assert summary["gross_cents"] - summary["trading_friction_cents"] - summary["operating_fees_cents"] == summary["net_cents"]
    return {"summary": summary, "days": days, "trades": trades}


def read_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise Refusal(f"Cannot read input manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != "ba011-inputs-v1":
        raise Refusal("Unsupported input manifest schema")
    if manifest.get("stage") not in YEARS:
        raise Refusal("Input manifest must declare development or oos stage")
    if not isinstance(manifest.get("audit"), dict) or manifest["audit"].get("reconciled") is not True:
        raise Refusal("Input audit is not fully reconciled")
    if not isinstance(manifest.get("source_manifest_sha256"), str) or re.fullmatch(
            r"[0-9a-f]{64}", manifest["source_manifest_sha256"]) is None:
        raise Refusal("Immutable source archive manifest hash required")
    calendar = manifest.get("calendar", {})
    if not isinstance(calendar, dict) or not isinstance(calendar.get("sha256"), str) or not isinstance(calendar.get("schedule_file"), str):
        raise Refusal("Versioned calendar schedule/hash required")
    calendar_path = path.parent / calendar["schedule_file"]
    if not calendar_path.is_file() or sha256(calendar_path) != calendar["sha256"]:
        raise Refusal("Calendar schedule hash mismatch")
    return manifest


def _calendar(path: Path, manifest: dict) -> list[dict]:
    try:
        rows = json.loads((path.parent / manifest["calendar"]["schedule_file"]).read_text())
        if not isinstance(rows, list) or not rows:
            raise ValueError("expected a nonempty ordered session list")
        previous = ""
        for row in rows:
            day = row["date"]
            if date.fromisoformat(day).isoformat() != day or day <= previous:
                raise ValueError("noncanonical, duplicate or unordered calendar date")
            if type(row["full_session"]) is not bool:
                raise ValueError("full_session must be boolean")
            previous = day
        return rows
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise Refusal(f"Invalid calendar schedule: {exc}") from exc


def read_sessions(path: Path, manifest: dict, years: tuple[int, ...], *,
                  boundary_reference: dict | None = None) -> list[dict]:
    sessions: list[dict] = []
    calendar = _calendar(path, manifest)
    expected_dates = [row["date"] for row in calendar
                      if row["full_session"] is True and int(row["date"][:4]) in years]
    predecessors = {row["date"]: calendar[index - 1] if index else None
                    for index, row in enumerate(calendar)}
    for year in years:
        entry = manifest.get("years", {}).get(str(year))
        if not isinstance(entry, dict):
            raise Refusal(f"Missing manifest entry for requested year {year}")
        if not isinstance(entry.get("file"), str) or not _integer(entry.get("full_sessions")):
            raise Refusal(f"Invalid session file/count metadata for {year}")
        source = path.parent / entry["file"]
        if not source.is_file() or sha256(source) != entry.get("sha256"):
            raise Refusal(f"Session file hash mismatch for {year}")
        year_sessions = []
        try:
            with gzip.open(source, "rt") as handle:
                for line in handle:
                    row = json.loads(line)
                    validate_session(row)
                    if not row["date"].startswith(f"{year}-"):
                        raise Refusal(f"Wrong year in {source.name}")
                    predecessor = predecessors.get(row["date"])
                    if predecessor is None:
                        raise Refusal(f"{row['date']}: calendar must identify the previous actual scheduled session")
                    if (row["previous_session_date"] != predecessor["date"] or
                            row["previous_session_full"] is not predecessor["full_session"]):
                        raise Refusal(f"{row['date']}: previous-session metadata skips or misstates the actual scheduled predecessor")
                    year_sessions.append(row)
        except (OSError, ValueError) as exc:
            raise Refusal(f"Unreadable session file for {year}: {exc}") from exc
        if not year_sessions or len(year_sessions) != entry.get("full_sessions"):
            raise Refusal(f"Full session count does not reconcile for {year}")
        sessions.extend(year_sessions)
    dates = [session["date"] for session in sessions]
    if dates != sorted(set(dates)):
        raise Refusal("Duplicate or unordered eligible sessions")
    if dates != sorted(expected_dates):
        raise Refusal("Eligible session dates do not match the hashed full-session calendar")
    by_date = {row["date"]: row for row in sessions}

    def reference(calendar_row: dict) -> dict:
        row = by_date.get(calendar_row["date"])
        close = next((bar[4] for bar in row["bars"] if bar[0] == 959), None) if row else None
        return {"date": calendar_row["date"], "full_session": calendar_row["full_session"],
                "close_ticks": close, "symbol": row["symbol"] if row else None,
                "instrument_id": row["instrument_id"] if row else None}

    for row in sessions:
        predecessor = predecessors[row["date"]]
        expected = reference(predecessor)
        if boundary_reference is not None and predecessor["date"] == boundary_reference.get("date"):
            if (predecessor["date"] in by_date or
                    boundary_reference.get("full_session") is not predecessor["full_session"]):
                raise Refusal("Invalid external development boundary reference")
            expected = boundary_reference
        for row_field, ref_field in (("previous_close_ticks", "close_ticks"),
                                     ("previous_symbol", "symbol"),
                                     ("previous_instrument_id", "instrument_id")):
            if row[row_field] != expected.get(ref_field):
                raise Refusal(f"{row['date']}: previous close/contract does not reconcile to the actual predecessor data")
    final_calendar_row = next((row for row in reversed(calendar) if int(row["date"][:4]) in years), None)
    if final_calendar_row is None or manifest.get("boundary_reference") != reference(final_calendar_row):
        raise Refusal("Final boundary reference does not reconcile to the stage's last scheduled session")
    return sessions


def freeze_record(path: Path, manifest: dict) -> dict:
    """Stage-independent freeze: development and OOS have distinct input manifests."""
    del path  # Retain the BA-010 helper signature for the stage-gated adapter.
    try:
        package_versions = {}
        for package in ("numpy", "exchange-calendars", "pandas", "tzdata"):
            try:
                package_versions[package] = version(package)
            except PackageNotFoundError:
                package_versions[package] = "NOT_INSTALLED"
        return {"engine_sha256": sha256(Path(__file__).resolve()),
                "protocol_sha256": sha256(PROTOCOL), "adapter_sha256": sha256(ADAPTER),
                "dependency_files_sha256": {str(item.relative_to(ROOT)): sha256(item) for item in DEPENDENCY_FILES},
                "dependency_versions": package_versions,
                "python_version": sys.version.split()[0],
                "source_manifest_sha256": manifest["source_manifest_sha256"],
                "calendar_sha256": manifest["calendar"]["sha256"],
                "calendar_metadata_sha256": canonical_hash(manifest["calendar"])}
    except (OSError, KeyError, TypeError) as exc:
        raise Refusal(f"Cannot freeze engine/protocol/adapter/dependencies/source/calendar: {exc}") from exc


def validate_development(development_report: Path | str | None,
                         development_manifest: Path | str | None,
                         expected_freeze: dict | None = None) -> dict:
    """Validate the exact passed development before an adapter opens holdout bars."""
    if development_report is None or development_manifest is None:
        raise Refusal("OOS requires a prior passed --development-report and exact --development-manifest; holdout files remain unopened")
    report_path, manifest_path = Path(development_report).resolve(), Path(development_manifest).resolve()
    try:
        prior = json.loads(report_path.read_text())
    except (OSError, ValueError) as exc:
        raise Refusal(f"Cannot read development report: {exc}; holdout files remain unopened") from exc
    if (not isinstance(prior, dict) or prior.get("schema") != "ba011-results-v1" or
            prior.get("stage") != "development" or prior.get("years") != list(YEARS["development"]) or
            prior.get("status") != "DEVELOPMENT_PASS" or prior.get("development_passed") is not True or
            prior.get("data_reconciled") is not True or prior.get("held_positions_resolved") is not True):
        raise Refusal("Development did not pass with resolved data; holdout files remain unopened")
    base = prior.get("models", {}).get("base_pilot", {})
    if not isinstance(base.get("net_cents"), (int, float)) or base["net_cents"] <= 0 or base.get("halt", "missing") is not None:
        raise Refusal("Development base account did not pass; holdout files remain unopened")
    manifest = read_manifest(manifest_path)
    if manifest["stage"] != "development":
        raise Refusal("Expected the exact development manifest; holdout files remain unopened")
    if prior.get("input_manifest_sha256") != sha256(manifest_path):
        raise Refusal("Development inputs changed; holdout files remain unopened")
    if not isinstance(prior.get("boundary_reference"), dict) or prior["boundary_reference"] != manifest.get("boundary_reference"):
        raise Refusal("Verified development boundary changed; holdout files remain unopened")
    current = freeze_record(manifest_path, manifest)
    if prior.get("freeze") != current or (expected_freeze is not None and current != expected_freeze):
        raise Refusal("Engine, protocol, adapter, dependencies, source archive or calendar changed since development; holdout files remain unopened")
    return prior


def _write_json(path: Path, value: Any) -> None:
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def run_stage(input_path: Path | str, *, stage: str = "development",
              output_root: Path | str = ROOT / "experiments/BA-011",
              development_report: Path | str | None = None,
              development_manifest: Path | str | None = None) -> dict:
    if stage not in YEARS:
        raise Refusal("Invalid evaluation stage")
    input_path = Path(input_path).resolve()
    output_dir = Path(output_root).resolve() / stage
    if output_dir.exists() and any(output_dir.iterdir()):
        raise Refusal(f"Refusing to overwrite existing stage artifacts: {output_dir}")
    prior = validate_development(development_report, development_manifest) if stage == "oos" else None
    manifest = read_manifest(input_path)
    if manifest["stage"] != stage:
        raise Refusal("Selected stage does not match the input manifest")
    freeze = freeze_record(input_path, manifest)
    if stage == "oos":
        validate_development(development_report, development_manifest, expected_freeze=freeze)
        if manifest.get("development_input", {}).get("sha256") != prior["input_manifest_sha256"]:
            raise Refusal("OOS inputs do not reference the exact passed development manifest")
    # The year selection is intentionally inaccessible through a CLI override.
    sessions = read_sessions(input_path, manifest, YEARS[stage],
                             boundary_reference=prior["boundary_reference"] if prior else None)
    models = {}
    for name, slippage, constrained in (("base_pilot", 1, True), ("stress_pilot", 2, True),
                                         ("base_unconstrained", 1, False), ("stress_unconstrained", 2, False)):
        models[name] = run_account(sessions, slippage_ticks=slippage, constrained=constrained)
    base = models["base_pilot"]["summary"]
    stress = models["stress_pilot"]["summary"]
    report = {"schema": "ba011-results-v1", "stage": stage, "years": list(YEARS[stage]),
              "input_manifest": str(input_path), "input_manifest_sha256": sha256(input_path), "freeze": freeze,
              "boundary_reference": manifest["boundary_reference"],
              "audit": manifest["audit"], "calendar": manifest["calendar"],
              "models": {name: result["summary"] for name, result in models.items()},
              "data_reconciled": True, "held_positions_resolved": True,
              "account_policy": "Independent $5000 account per model, one contract, no annual reset; monthly fees continue after halt",
              "research_acquisition": {"source_quote_usd": manifest.get("source_quote_usd"),
                  "details": manifest.get("research_acquisition", manifest.get("acquisition", {})),
                  "included_in_strategy_net": False}}
    period_years = len(YEARS[stage])
    report["cash_comparators"] = {str(rate): {"initial_cents": INITIAL_CENTS,
        "ending_cents": INITIAL_CENTS * (1 + rate) ** period_years,
        "total_gain_cents": INITIAL_CENTS * ((1 + rate) ** period_years - 1),
        "yearly_gain_cents": {str(year): INITIAL_CENTS * (1 + rate) ** index * rate
                              for index, year in enumerate(YEARS[stage])}}
        for rate in (0.04, 0.06)}
    if stage == "development":
        passed = base["net_cents"] > 0 and base["halt"] is None
        report["development_passed"] = passed
        report["status"] = "DEVELOPMENT_PASS" if passed else "DEVELOPMENT_FAIL"
        report["holdout_permitted"] = passed
        report["failure_reasons"] = ([] if base["net_cents"] > 0 else ["base_net_pnl_not_positive"]) + ([] if base["halt"] is None else ["base_pilot_halted"])
        report["verdict"] = "Proceed to frozen chronological OOS evaluation" if passed else "Park BA-011 version 1; do not evaluate 2024/2025"
    else:
        cagr = (base["ending_equity_cents"] / INITIAL_CENTS) ** (1 / 2) - 1 if base["ending_equity_cents"] > 0 else -1.0
        gates = {"data_reconciled": True,
                 "positive_2024_net": base["yearly"]["2024"]["net_cents"] > 0,
                 "positive_2025_net": base["yearly"]["2025"]["net_cents"] > 0,
                 "combined_cagr_above_6pct": cagr > 0.06,
                 "base_pilot_no_halt": base["halt"] is None,
                 "positive_stressed_oos_net": stress["net_cents"] > 0}
        cash_gain = report["cash_comparators"]["0.06"]["total_gain_cents"]
        report["bootstrap"] = {str(block): stationary_bootstrap(
            [day["net_cents"] for day in models["base_pilot"]["days"]],
            block_length=block, cash_gain_cents=cash_gain) for block in (10, 5, 20)}
        report["hard_gates"] = gates
        report["combined_cagr"] = cagr
        report["hard_gates_passed"] = all(gates.values())
        report["statistical_gate_passed"] = report["bootstrap"]["10"]["evidence_of_beating_cash"]
        passed = all(gates.values()) and report["statistical_gate_passed"]
        report["status"] = ("HISTORICAL_SCREEN_PASS" if passed else
                            "OOS_FAIL" if not all(gates.values()) else "OOS_INCONCLUSIVE")
        report["verdict"] = "Historical screen passes; quote/fill audit and prospective paper test only" if passed else "No promotion; failed hard gates or inconclusive evidence of beating cash"
        report["development_report"] = {"path": str(Path(development_report).resolve()),
                                          "sha256": sha256(Path(development_report))}
        report["development_manifest"] = {"path": str(Path(development_manifest).resolve()),
                                            "sha256": sha256(Path(development_manifest))}
    output_dir.mkdir(parents=True, exist_ok=True)
    for ledger, field in (("day-ledger.jsonl", "days"), ("trade-ledger.jsonl", "trades")):
        with (output_dir / ledger).open("x") as handle:
            for model, result in models.items():
                for row in result[field]:
                    handle.write(json.dumps({"model": model, **row}, sort_keys=True) + "\n")
    report["artifacts"] = {name: {"file": name, "sha256": sha256(output_dir / name)}
                           for name in ("day-ledger.jsonl", "trade-ledger.jsonl")}
    _write_json(output_dir / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Audited immutable BA-011 input manifest")
    parser.add_argument("--stage", choices=tuple(YEARS), default="development")
    parser.add_argument("--output-root", type=Path, default=ROOT / "experiments/BA-011")
    parser.add_argument("--development-report", type=Path)
    parser.add_argument("--development-manifest", type=Path)
    args = parser.parse_args()
    try:
        report = run_stage(args.input, stage=args.stage, output_root=args.output_root,
                           development_report=args.development_report,
                           development_manifest=args.development_manifest)
    except Refusal as exc:
        print(json.dumps({"status": "REFUSED", "stage": args.stage, "reason": str(exc)}), file=sys.stderr)
        return 3
    print(json.dumps({"status": report["status"], "report": str(args.output_root.resolve() / args.stage / "report.json"),
                      "base_net_cents": report["models"]["base_pilot"]["net_cents"]}, indent=2))
    return 0 if report["status"] in ("DEVELOPMENT_PASS", "HISTORICAL_SCREEN_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
