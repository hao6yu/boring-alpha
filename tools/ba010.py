#!/usr/bin/env python3
"""Frozen BA-010 minute-bar simulation. Network-free; prices are integer MES ticks.

Only the explicitly selected stage's files are opened. Development failure never
opens holdout bars. A missing executable/held minute refuses the entire verdict.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/strategies/BA-010.md"
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
    bars = session.get("bars")
    if not isinstance(bars, list):
        raise Refusal(f"{session_date}: bars must be a list")
    previous = 569
    for bar in bars:
        if not isinstance(bar, list) or len(bar) != 6 or not all(_integer(x) for x in bar):
            raise Refusal(f"{session_date}: bars must contain six integer fields")
        minute, opening, high, low, close, volume = bar
        if not 570 <= minute < 960 or minute <= previous:
            raise Refusal(f"{session_date}: duplicate, unordered, or out-of-session minute {minute}")
        if min(opening, high, low, close) <= 0 or volume <= 0:
            raise Refusal(f"{session_date}: invalid price or volume at {minute}")
        if not low <= min(opening, close) <= max(opening, close) <= high:
            raise Refusal(f"{session_date}: invalid OHLC at {minute}")
        previous = minute


def candidate_order(session: dict) -> tuple[dict | None, str | None]:
    """Use only information available before entry; never scan future completeness."""
    bars = {bar[0]: bar for bar in session["bars"]}
    if any(minute not in bars for minute in range(570, 600)):
        return None, "missing_opening_range"
    high = max(bars[minute][2] for minute in range(570, 600))
    low = min(bars[minute][3] for minute in range(570, 600))
    for minute in range(600, 689):
        if minute not in bars:
            return None, "missing_signal_history"
        close = bars[minute][4]
        direction = 1 if close >= high + 1 else -1 if close <= low - 1 else 0
        if not direction:
            continue
        stop = (high + low) // 2 if direction == 1 else (high + low + 1) // 2
        planned_loss = (direction * (close - stop) + 2) * TICK_CENTS + 2 * FEE_SIDE_CENTS
        order = {"signal_minute": minute, "entry_minute": minute + 2,
                 "direction": direction, "stop_ticks": stop, "signal_close_ticks": close,
                 "opening_high_ticks": high, "opening_low_ticks": low,
                 "planned_loss_cents": planned_loss}
        if not 2500 <= planned_loss <= 7500:
            return None, "first_breakout_outside_risk_budget"
        if minute + 1 not in bars:
            return None, "missing_preentry_minute"
        # An already submitted order cannot disappear because its execution bar is absent.
        if minute + 2 not in bars:
            raise Refusal(f"{session['date']}: missing committed entry minute {minute + 2}")
        return order, None
    return None, "no_breakout"


def run_account(sessions: Iterable[dict], *, slippage_ticks: int = 1,
                constrained: bool = True) -> dict:
    """Run one continuous, independent $5,000 fixed-one-contract account."""
    if slippage_ticks not in (1, 2):
        raise ValueError("BA-010 permits only base (1 tick) and stress (2 tick) fills")
    equity = INITIAL_CENTS
    observed_high = closed_high = upper_high = equity
    observed_dd = closed_dd = intrabar_dd = 0
    halt: dict | None = None
    trades: list[dict] = []
    days: list[dict] = []
    charged_months: set[str] = set()
    previous_date = ""

    def observe(value: int, *, flat: bool = False) -> None:
        nonlocal observed_high, observed_dd, closed_high, closed_dd, upper_high, intrabar_dd
        observed_high = max(observed_high, value)
        observed_dd = max(observed_dd, observed_high - value)
        upper_high = max(upper_high, value)
        intrabar_dd = max(intrabar_dd, upper_high - value)
        if flat:
            closed_high = max(closed_high, value)
            closed_dd = max(closed_dd, closed_high - value)

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
            stop = order["stop_ticks"]
            entry_minute = order["entry_minute"]
            entry_raw = bars[entry_minute][1]
            entry_fill = entry_raw + direction * slippage_ticks
            balance_before_entry = equity
            entry_loss = (direction * (entry_fill - stop) + slippage_ticks) * TICK_CENTS + 2 * FEE_SIDE_CENTS
            equity -= FEE_SIDE_CENTS
            pending_risk_exit = False
            trigger_minute = None
            raw_exit = exit_minute = exit_reason = None

            def liquidation(price: int) -> int:
                return (balance_before_entry + direction * (price - entry_fill) * TICK_CENTS
                        - slippage_ticks * TICK_CENTS - 2 * FEE_SIDE_CENTS)

            for minute in range(entry_minute, 956):
                if minute not in bars:
                    raise Refusal(f"{day}: unresolved held position at missing minute {minute}; "
                                  f"entry={entry_minute}, direction={direction}, stop_ticks={stop}")
                _, opening, high, low, close, _ = bars[minute]
                # Open-price exits precede the remainder of this minute's range.
                if minute == entry_minute and direction * (opening - stop) <= 0:
                    raw_exit, exit_reason = opening, "entry_through_stop"
                elif pending_risk_exit:
                    raw_exit, exit_reason = opening, "drawdown_next_open"
                elif minute == 955:
                    raw_exit, exit_reason = opening, "time_exit"
                elif direction * (opening - stop) <= 0:
                    raw_exit, exit_reason = opening, "stop_gap"
                else:
                    # This is a deliberately loose OHLC envelope. Favorable-before-adverse
                    # ordering is assumed only for this labelled bound, never executions.
                    favorable = high if direction == 1 else low
                    adverse = low if direction == 1 else high
                    upper_high = max(upper_high, liquidation(favorable))
                    intrabar_dd = max(intrabar_dd, upper_high - liquidation(adverse))
                    if (direction == 1 and low <= stop) or (direction == -1 and high >= stop):
                        raw_exit, exit_reason = stop, "stop_touch"
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
                     "entry_planned_loss_cents": entry_loss,
                     "risk_overrun_cents": max(0, entry_loss - 7500),
                     "realized_loss_over_budget_cents": max(0, -net - 7500),
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
                        "gross_cents": sum(trade["gross_cents"] for trade in year_trades),
                        "trading_friction_cents": sum(trade["friction_cents"] for trade in year_trades),
                        "operating_fees_cents": sum(day["operating_fee_cents"] for day in year_days),
                        "trades": len(year_trades), "eligible_sessions": len(year_days),
                        "abstentions": dict(Counter(day["abstention_reason"] for day in year_days if not day["traded"]))}
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
               "intrabar_bound_method": "OHLC favorable before adverse envelope, including full stop-bar extrema; not an executable or ordered tick path",
               "risk_overrun_count": sum(trade["risk_overrun_cents"] > 0 for trade in trades),
               "max_entry_risk_overrun_cents": max((trade["risk_overrun_cents"] for trade in trades), default=0),
               "realized_loss_over_budget_count": sum(trade["realized_loss_over_budget_cents"] > 0 for trade in trades),
               "worst_trade": min(trades, key=lambda trade: trade["net_cents"], default=None),
               "top_five_winners_cents": top_five,
               "top_five_share_positive_trade_pnl": top_five / sum(positive) if positive else None,
               "top_five_share_total_net_pnl": top_five / (equity - INITIAL_CENTS) if equity > INITIAL_CENTS else None}
    assert summary["gross_cents"] - summary["trading_friction_cents"] - summary["operating_fees_cents"] == summary["net_cents"]
    return {"summary": summary, "days": days, "trades": trades}


def stationary_bootstrap(daily_cents: list[int], *, block_length: int,
                         cash_gain_cents: float, draws: int = 10_000, seed: int = 1010,
                         annual_sessions: float | None = None) -> dict:
    """Stationary circular blocks of dollar P&L, including zero/operating-fee days."""
    import numpy as np
    if not daily_cents or block_length <= 0 or draws <= 0:
        raise ValueError("Nonempty daily P&L, positive block length and draws required")
    values = np.asarray(daily_cents, dtype=np.float64) / 100.0
    rng = np.random.default_rng(seed)
    count = len(values)
    indices = rng.integers(0, count, size=draws)
    totals = values[indices].copy()
    for _ in range(1, count):
        restart = rng.random(draws) < 1.0 / block_length
        indices = np.where(restart, rng.integers(0, count, size=draws), (indices + 1) % count)
        totals += values[indices]
    means = totals / count
    low, high = (float(value) for value in np.quantile(means, [0.025, 0.975]))
    sessions_per_year = annual_sessions if annual_sessions is not None else count / 2.0
    cash_daily = cash_gain_cents / 100.0 / count
    return {"method": "stationary circular block bootstrap of daily dollar P&L",
            "draws": draws, "seed": seed, "mean_block_length_sessions": block_length,
            "mean_daily_pnl_dollars": float(values.mean()), "mean_daily_95pct_dollars": [low, high],
            "annualization_sessions_per_year": sessions_per_year,
            "annualized_arithmetic_pnl_95pct_dollars": [low * sessions_per_year, high * sessions_per_year],
            "cash_6pct_gain_per_session_dollars": cash_daily,
            "mean_excess_over_cash_95pct_dollars": [low - cash_daily, high - cash_daily],
            "evidence_of_beating_cash": low - cash_daily > 0}


def read_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise Refusal(f"Cannot read input manifest: {exc}") from exc
    if manifest.get("schema") != "ba010-inputs-v1":
        raise Refusal("Unsupported input manifest schema")
    if manifest.get("audit", {}).get("reconciled") is not True:
        raise Refusal("Input audit is not fully reconciled")
    calendar = manifest.get("calendar", {})
    if not calendar.get("sha256") or not calendar.get("schedule_file"):
        raise Refusal("Versioned calendar schedule/hash required")
    calendar_path = path.parent / calendar["schedule_file"]
    if not calendar_path.is_file() or sha256(calendar_path) != calendar["sha256"]:
        raise Refusal("Calendar schedule hash mismatch")
    return manifest


def read_sessions(path: Path, manifest: dict, years: tuple[int, ...]) -> list[dict]:
    sessions: list[dict] = []
    try:
        calendar = json.loads((path.parent / manifest["calendar"]["schedule_file"]).read_text())
        expected_dates = [row["date"] for row in calendar
                          if row["full_session"] is True and int(row["date"][:4]) in years]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise Refusal(f"Invalid calendar schedule: {exc}") from exc
    for year in years:
        entry = manifest.get("years", {}).get(str(year))
        if not isinstance(entry, dict):
            raise Refusal(f"Missing manifest entry for requested year {year}")
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
    return sessions


def freeze_record(path: Path, manifest: dict) -> dict:
    return {"engine_sha256": sha256(Path(__file__).resolve()),
            "protocol_sha256": sha256(PROTOCOL), "manifest_sha256": sha256(path),
            "calendar_sha256": manifest["calendar"]["sha256"],
            "calendar_metadata_sha256": canonical_hash(manifest["calendar"])}


def _write_json(path: Path, value: Any) -> None:
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def run_stage(input_path: Path | str, *, stage: str = "development",
              output_root: Path | str = ROOT / "experiments/BA-010",
              development_report: Path | str | None = None) -> dict:
    if stage not in YEARS:
        raise Refusal("Invalid evaluation stage")
    input_path = Path(input_path).resolve()
    output_dir = Path(output_root).resolve() / stage
    if output_dir.exists() and any(output_dir.iterdir()):
        raise Refusal(f"Refusing to overwrite existing stage artifacts: {output_dir}")
    manifest = read_manifest(input_path)
    freeze = freeze_record(input_path, manifest)
    prior = None
    if stage == "oos":
        if development_report is None:
            raise Refusal("OOS requires a prior passed --development-report")
        try:
            prior = json.loads(Path(development_report).read_text())
        except (OSError, ValueError) as exc:
            raise Refusal(f"Cannot read development report: {exc}") from exc
        if prior.get("stage") != "development" or prior.get("development_passed") is not True:
            raise Refusal("Development did not pass; holdout files remain unopened")
        if prior.get("freeze") != freeze:
            raise Refusal("Code, protocol, calendar or immutable inputs changed since development; holdout files remain unopened")
    # The year selection is intentionally inaccessible through a CLI override.
    sessions = read_sessions(input_path, manifest, YEARS[stage])
    models = {}
    for name, slippage, constrained in (("base_pilot", 1, True), ("stress_pilot", 2, True),
                                         ("base_unconstrained", 1, False), ("stress_unconstrained", 2, False)):
        models[name] = run_account(sessions, slippage_ticks=slippage, constrained=constrained)
    base = models["base_pilot"]["summary"]
    stress = models["stress_pilot"]["summary"]
    report = {"schema": "ba010-results-v1", "stage": stage, "years": list(YEARS[stage]),
              "input_manifest": str(input_path), "freeze": freeze,
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
        report["verdict"] = "Proceed to frozen chronological OOS evaluation" if passed else "Park BA-010 version 1; do not evaluate 2024/2025"
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
    parser.add_argument("--input", required=True, type=Path, help="Audited immutable BA-010 input manifest")
    parser.add_argument("--stage", choices=tuple(YEARS), default="development")
    parser.add_argument("--output-root", type=Path, default=ROOT / "experiments/BA-010")
    parser.add_argument("--development-report", type=Path)
    args = parser.parse_args()
    try:
        report = run_stage(args.input, stage=args.stage, output_root=args.output_root,
                           development_report=args.development_report)
    except Refusal as exc:
        print(json.dumps({"status": "REFUSED", "stage": args.stage, "reason": str(exc)}), file=sys.stderr)
        return 3
    print(json.dumps({"status": report["status"], "report": str(args.output_root.resolve() / args.stage / "report.json"),
                      "base_net_cents": report["models"]["base_pilot"]["net_cents"]}, indent=2))
    return 0 if report["status"] in ("DEVELOPMENT_PASS", "HISTORICAL_SCREEN_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
