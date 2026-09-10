"""Reproduce the frozen covered-window, zero-position account diagnostic.

This is a cash/expense ledger proved by the existing infeasibility results.
It is not a trading execution engine or the full 2018–2023 Stage B study.
"""
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import ba012_sizing as sizing

HERE = Path(__file__).resolve().parent
PLAN_HASH = "b242f605a1c4325080b06e43e8ca23de68eca8bb888ca3a74769551308602bde"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def next_month(month):
    year, number = map(int, month.split("-"))
    return f"{year + (number == 12):04d}-{number % 12 + 1:02d}"


def previous_month(month):
    year, number = map(int, month.split("-"))
    return f"{year - (number == 1):04d}-{(number - 2) % 12 + 1:02d}"


def money(value):
    return str(value.quantize(Decimal("0.01")))


def eligible_groups(case, equity, drawdown):
    """Independent one-unit necessary bound using actual cash-ledger equity."""
    sigma = sizing.estimate_covariance(case["dollar_movements"])
    vols = [float(sigma[i, i] ** 0.5) for i in range(5)]
    remaining_loss = int((Decimal("1000") - drawdown) * sizing.MONEY_SCALE)
    remaining_funding = int((equity - Decimal("100")) * sizing.MONEY_SCALE)
    groups, markets = set(), []
    for i, sign in enumerate(case["signs"]):
        initial = (sizing.INITIAL_LONG if sign >= 0 else sizing.INITIAL_SHORT)[i]
        maintenance = (sizing.MAINTENANCE_LONG if sign >= 0 else sizing.MAINTENANCE_SHORT)[i]
        assert initial >= maintenance
        unit_risk = vols[i] + 0.08 * sizing.EXECUTION[i] / sizing.MONEY_SCALE
        if (sign and unit_risk <= 0.08 * float(equity) * (1 + sizing.FEASIBILITY_ATOL)
                and sizing.CHARGE[i] <= remaining_loss
                and sizing.CHARGE[i] + 2 * initial <= remaining_funding):
            groups.add(sizing.GROUPS[i])
            markets.append(sizing.SYMBOLS[i])
    return sorted(groups), markets


def run():
    plan_path = HERE / "covered-cash-plan-v1.json"
    assert digest(plan_path) == PLAN_HASH
    plan = json.loads(plan_path.read_text())
    for source in plan["inputs"]:
        assert digest(ROOT / source["path"]) == source["sha256"], source["path"]
    sizing.verify_frozen_protocol()
    inputs = json.loads((ROOT / "research/ba012-stage-a/settlement-inputs-v2-continuation.json").read_text())
    calendar = json.loads((ROOT / "research/ba012-stage-a/calendar-v1.json").read_text())["joint_sessions"]
    cases = {x["decision_date_chicago"]: x for x in inputs["monthly_cases"]}
    proofs = {x["decision_date_chicago"]: x["sizing"] for x in inputs["pilot_sizing"]["per_date"]}
    month_ends = {day[:7]: day for day in calendar}
    intervals = inputs["interval_provenance"]
    start, end = plan["start_inclusive"], plan["end_exclusive"]
    days = [day for day in calendar if start <= day < end]
    assert days[0] == "2022-07-01" and days[-1] == "2023-12-29" and len(days) == 377
    for day in days:
        index = calendar.index(day)
        for endpoint in (index - 1, index):
            window = intervals[endpoint - 252:endpoint]
            assert len(window) == 252 and all(x["status"] == "READY" for x in window), day

    equity = initial = high_water = Decimal(plan["initial_equity_usd"])
    fee = Decimal(plan["monthly_data_fee_usd"])
    months, ledger, instructions = {}, [], []
    for day in days:
        month = day[:7]
        before, expense = equity, Decimal(0)
        if month not in months:
            signal_day = month_ends[previous_month(month)]
            case, proof = cases[signal_day], proofs[signal_day]
            assert signal_day < day and case["status"] == "READY"
            assert proof["optimum_verified"] and proof["nonzero_feasibility"] == "PROVED_INFEASIBLE"
            assert proof["quantities"] == [0] * 5
            assert "fewer_than_three_groups_with_one_contract_within_singleton_risk_and_money_caps" in proof["necessary_failures"]
            initial_groups, _ = eligible_groups(case, initial, Decimal(0))
            before_groups, _ = eligible_groups(case, equity, high_water - equity)
            assert len(initial_groups) < 3 and set(before_groups) <= set(initial_groups)
            months[month] = {"month": month, "start_equity_usd": money(equity), "fee_date": day}
            expense = fee
            equity -= expense
            after_groups, markets = eligible_groups(case, equity, high_water - equity)
            assert set(after_groups) <= set(before_groups) and len(after_groups) < 3
            instructions.append({"execution_month": month, "signal_date": signal_day,
                "equity_after_fee_usd": money(equity), "eligible_markets_after_fee": markets,
                "eligible_groups_after_fee": after_groups, "planned_quantities": [0] * 5})
            months[month].update(end_equity_usd=money(equity), net_pnl_usd=money(-fee),
                return_fraction=float(-fee / before))
        drawdown = high_water - equity
        assert Decimal(0) < equity <= initial and drawdown < Decimal(1000)
        ledger.append({"date_chicago": day, "equity_before_usd": money(before),
            "data_fee_usd": money(expense), "gross_trading_pnl_usd": "0.00",
            "trade_cost_usd": "0.00", "equity_after_usd": money(equity),
            "high_water_usd": money(high_water), "drawdown_usd": money(drawdown),
            "quantities": [0] * 5})
    assert instructions[0]["signal_date"] == plan["seed_signal_date_chicago"]
    assert instructions[-1]["signal_date"] == plan["last_used_signal_date_chicago"]
    assert len(months) == 18 and equity == initial - fee * len(months)
    calendar_days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    with localcontext() as context:
        context.prec = 50
        years = Decimal(calendar_days) / Decimal(plan["benchmark_day_basis"])
        cagr = (equity / initial) ** (Decimal(1) / years) - 1
        benchmarks = [{"annual_rate": rate,
            "ending_equity_usd": money(initial * (1 + Decimal(rate)) ** years),
            "strategy_minus_benchmark_usd": money(equity - initial * (1 + Decimal(rate)) ** years)}
            for rate in plan["benchmark_annual_rates"]]
    annual = []
    for year in sorted({month[:4] for month in months}):
        rows = [x for month, x in months.items() if month.startswith(year)]
        opening, closing = Decimal(rows[0]["start_equity_usd"]), Decimal(rows[-1]["end_equity_usd"])
        annual.append({"year": int(year), "covered_months": len(rows), "full_calendar_year": len(rows) == 12,
            "start_equity_usd": money(opening), "end_equity_usd": money(closing),
            "net_pnl_usd": money(closing - opening), "period_return_fraction": float(closing / opening - 1)})
    return {"schema": "ba012-covered-cash-profitability-result-v1", "status": "COMPLETE_DIAGNOSTIC",
        "label": plan["label"], "plan_sha256": PLAN_HASH, "script_sha256": digest(Path(__file__)),
        "start_inclusive": start, "end_exclusive": end, "calendar_days": calendar_days,
        "joint_sessions_verified": len(days), "months": len(months), "initial_equity_usd": money(initial),
        "ending_equity_usd": money(equity), "gross_trading_pnl_usd": "0.00", "trades": 0,
        "total_data_fees_usd": money(fee * len(months)), "net_pnl_usd": money(equity - initial),
        "total_return_fraction": float(equity / initial - 1), "calendar_cagr": float(cagr),
        "maximum_marked_drawdown_usd": money(high_water - equity),
        "maximum_marked_drawdown_fraction": float((high_water - equity) / high_water), "halted": False,
        "base_and_stress_equal": True, "cash_scenarios": benchmarks,
        "profitability_verdict": "DOES_NOT_BEAT_EITHER_CASH_SCENARIO_IN_COVERED_WINDOW",
        "full_2018_2023_stage_b_status": "UNRESOLVED_NOT_RUN", "trading_edge_established": False,
        "larger_capital_tested": False, "holdout_prices_read": False,
        "annual_periods": annual, "monthly_returns": list(months.values()),
        "monthly_instruction_proofs": instructions, "daily_cash_ledger": ledger,
        "limitations": plan["limitations"]}


if __name__ == "__main__":
    result = run()
    output = HERE / "covered-cash-result-v1.json"
    with output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    output.with_suffix(".json.sha256").write_text(digest(output) + "  " + output.name + "\n")
    print(json.dumps({key: result[key] for key in ("status", "ending_equity_usd", "net_pnl_usd",
        "calendar_cagr", "maximum_marked_drawdown_usd", "trades", "cash_scenarios")}))
