"""Score volatility-targeted SPY against doing nothing, in dollars.

Run: .venv/bin/python tools/run_voltarget_scan.py [--verbose]

The comparator is the point of the exercise, not a footnote. Plain dollar-cost
averaging into the same fund, same schedule, same prices, no model. Every row
carries its shortfall against that, because a strategy that only beats itself is
what BA-004 turned out to be and the repository is not doing that again.

Costs, all stated so they can be argued with:
  * expense ratio 9.45 bps/yr on the equity leg. Real SPY. The archive has no VOO
    or QQQ; SPY tracks the same index as VOO, so this is a fair VOO proxy and an
    unfair test of any claim about QQQ, which cannot be made from this data.
  * 2.0 bps per unit of one-way turnover. SPY is the liquidest ETF ever listed and
    a small marketable order crosses a penny-wide spread; 2 bps is ungenerous.
  * financing at the archive's own cash index plus 150 bps, charged daily on the
    borrowed portion only. Small-account retail margin, not an institution's.

The grid below was fixed before the first run: two volatility targets, three vol
windows, gate on or off, levered or not. Twenty-four configurations. Choosing the
best of twenty-four on the same data used to judge them is data mining and is
labelled as such in the output, not hidden.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                          # noqa: E402  the loan price lives in the forward engine, one fact one place

from boring_alpha.data.csv_loader import load_csv_market_data
from boring_alpha.metrics.cashflow import money_weighted_return
from boring_alpha.signals.voltarget import VolTargetPolicy

SNAPSHOT = ROOT / "data" / "snapshots" / "20260904T192633Z" / "market_daily.csv"
CASH_FILE = ROOT / "data" / "snapshots" / "20260904T192633Z" / "cash_daily.csv"
SYMBOL = "SPY"

import fund_fees                                        # noqa: E402  one expense table, and this line used to be a copy

EXPENSE = fund_fees.fee_for("SPY")   # the leg this runner sweeps
TURNOVER_COST = 0.0002
# The only load-bearing number in this file that was typed in rather than fetched, and the one
# the last surviving mechanism depends on. It is not a retail margin rate: base tiers in April
# 2026 ran 4.90% to 12.00% on identical collateral, i.e. 109 to 819 bps over the archive's own
# cash index, and the same levered book earns a median $206 a month at the cheap end and loses
# $12 a month at the expensive end. Read `tools/financing_break_even.py` before quoting anything
# that depends on this line, and `docs/notes/2026-09-06-financing-break-even.md` for why a
# spread is the wrong unit for a posted rate.
BORROW_SPREAD = paper.BORROW_SPREAD   # the posted desk quote, sourced in round 104; this file used to retype 0.015
# A broker stops lending before you stop owing. Expressed as an equity cushion, not
# as leverage, because the two are not interchangeable: a constant-leverage policy
# *adds* exposure as it falls, which is the opposite of what a lender permits once
# the cushion is thin. Below 30% equity the position is cut to 1x, which is roughly
# how a liquidation works — it is not a trim to the maintenance boundary.
# Without this the simulator reports a 3x book riding calmly through a -94%
# drawdown, which is a statement about arithmetic and not about an account.
MAINTENANCE_EQUITY = 0.30
OPENING = 5_000.0
MONTHLY = 500.0

WINDOWS = {
    "full 1993..2026": (date(1993, 1, 1), date(2026, 9, 30)),
    "seen A 2007-06..2017-12": (date(2007, 6, 1), date(2017, 12, 31)),
    "seen B 2018..2021": (date(2018, 1, 1), date(2021, 12, 31)),
    "recent 2022..2026": (date(2022, 1, 1), date(2026, 9, 30)),
}

# A control, not a candidate. target_vol of 100% means the policy is pinned to its
# cap every day, so these rows are plain levered buy-and-hold: they isolate what
# leverage alone is worth at retail financing, with no signal in it at all. If
# these do not beat doing nothing, no levered variant of anything will.
CONTROLS = tuple(
    VolTargetPolicy(target_vol=1.0, vol_window=20, trend_window=None,
                    max_weight=cap, rebalance_band=0.10)
    for cap in (1.25, 1.5, 2.0, 3.0)
)

# The one configuration this round is allowed to claim. Fixed before the run, on
# the reasoning that cadence is the binding cost (1.5%/yr for a nightly round trip
# even at 0.3 bps a leg), that leverage is the only mechanism measured so far that
# beats the comparator in every window, and that the previous round's gate lost
# money because it went all the way to cash and missed the recovery. So: weekly
# review, 1.3x cap, floor of 30% rather than zero, and the gate de-risks instead of
# exiting. Nothing here was chosen by looking at a result.
PRE_REGISTERED = VolTargetPolicy(
    target_vol=0.18, vol_window=30, trend_window=200,
    max_weight=1.3, min_weight=0.3, rebalance_band=0.10, review_every=5,
)

GRID = tuple(
    VolTargetPolicy(target_vol=t, vol_window=w, trend_window=g, max_weight=l,
                    rebalance_band=0.10)
    for t in (0.10, 0.15)
    for w in (20, 30, 60)
    for g in (None, 200)
    for l in (1.0, 1.5)
)


@dataclass(frozen=True, slots=True)
class Funded:
    ending: float
    irr: float
    paid_in: float
    cost_paid: float
    turns: int
    max_drawdown: float
    avg_weight: float
    worst_weight: float
    ruined: bool = False
    margin_calls: int = 0
    # Path and carry default so every existing caller keeps working. `path` is
    # the daily account value inside the funded window; without it a caller
    # wanting a worst-month figure has to re-implement the engine, and two
    # engines that drift apart is a worse failure than one that is verbose.
    path: tuple[tuple[date, float], ...] = ()
    carry_paid: float = 0.0


def funded(
    closes: list[float],
    returns: list[float],
    cash_factors: list[float],
    dates: list[date],
    targets: list[float | None],
    band: float,
    allow: set[int] | None = None,
    start: int = 0,
) -> Funded:
    """A monthly-funded account trading to a target weight inside a band.

    `allow` restricts trading to the sessions the policy itself decided to trade.
    Without it a caller passing `band=0` would rebalance every session and charge
    for the privilege, which is how the first run of the pre-registered candidate
    reported 8,427 trades for a model specified as a five-session review. The
    restriction is absolute — except for the opening fill, which is not a
    rebalance and has to happen somewhere — because a cadence rule that a drifting
    position can step around is not a cadence rule. `start` pins every
    configuration to the same first session, so a long warm-up cannot quietly
    shorten the measurement window and flatter the result.
    """

    eq = 0.0
    csh = OPENING
    ruin = False
    margin_calls = 0
    cost_paid = 0.0
    carry_paid = 0.0
    turns = 0
    peak = OPENING
    worst_dd = 0.0
    weights: list[float] = []
    path: list[tuple[date, float]] = []
    started = False
    flows: list[tuple[date, float]] = []
    first_month = None
    warmup = max(start, next(i for i, t in enumerate(targets) if t is not None))

    for position in range(warmup, len(dates)):
        target = targets[position]
        if target is None:
            continue
        month = (dates[position].year, dates[position].month)
        if first_month is None:
            first_month = month
        elif month != first_month:
            first_month = month
            csh += MONTHLY
            flows.append((dates[position], MONTHLY))

        value = eq + csh
        opening_fill = not started
        if not started:
            delta = target * value
            started = True
        else:
            delta = target * value - eq
            if abs(delta) < band * value:
                delta = 0.0
            elif allow is not None and position not in allow:
                # A session the policy did not review is not a session the account may trade
                # on, whatever the drift says. The first draft of this line only refused drift
                # under a dollar, which on a six-figure book refuses nothing.
                delta = 0.0
        if delta and (allow is None or opening_fill or position in allow):
            # Cash funds a buy and receives a sale. Getting this wrong does not
            # look wrong: it silently manufactures equity, and the first version
            # of this function turned $10,500 into $2.85m on flat prices.
            charge = abs(delta) * TURNOVER_COST
            csh -= delta + charge
            cost_paid += charge
            eq += delta
            turns += 1
        if eq + csh <= 0.0:
            ruin = True
            break

        # Day's carry: cash at the cash rate, debt at the cash rate plus spread,
        # equity at the index less its expense ratio.
        value = eq + csh
        weight = eq / value if value > 0 else 0.0
        if csh < 0:
            gross = -csh
            csh *= 1.0 + (cash_factors[position] - 1.0) + BORROW_SPREAD / 252.0
            # Only the spread is reported as carry. The debt also accrues at the
            # cash rate, but that leg is not a cost of leverage: the same money
            # sitting in cash would have earned it, so it nets out against the
            # unlevered comparator and charging it twice would make every row
            # look worse than the comparator by construction.
            carry_paid += gross * BORROW_SPREAD / 252.0
        else:
            csh *= cash_factors[position]
        eq *= (1.0 + returns[position]) * (1.0 - EXPENSE / 252.0)

        value = eq + csh
        if value <= 0.0:
            ruin = True
            break
        if value > 0.0 and value < MAINTENANCE_EQUITY * eq:
            forced = 1.0 * value - eq
            charge = abs(forced) * TURNOVER_COST
            csh -= forced + charge
            cost_paid += charge
            eq += forced
            margin_calls += 1
            value = eq + csh

        weights.append(weight)
        path.append((dates[position], value))
        peak = max(peak, value)
        if peak > 0:
            worst_dd = min(worst_dd, value / peak - 1.0)

    from boring_alpha.metrics.cashflow import CashFlow

    ending_value = max(0.0, eq + csh)
    total = OPENING + sum(a for _, a in flows)
    irr = money_weighted_return(
        dates[warmup], OPENING, dates[-1], ending_value,
        tuple(CashFlow(d, a) for d, a in flows),
    )
    return Funded(
        ending=ending_value, irr=irr, paid_in=total, cost_paid=cost_paid,
        turns=turns, ruined=ruin, margin_calls=margin_calls,
        max_drawdown=worst_dd, path=tuple(path), carry_paid=carry_paid,
        avg_weight=sum(weights) / len(weights) if weights else 0.0,
        worst_weight=min(weights) if weights else 0.0,
    )


def series(bounds: tuple[date, date]):
    data = load_csv_market_data(SNAPSHOT, CASH_FILE, end=bounds[1])
    dates = [d for d in data.dates if d >= bounds[0] and SYMBOL in data.by_date[d]]
    closes = [data.by_date[d][SYMBOL].close for d in dates]
    returns = [0.0] + [
        closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))
    ]
    missing = [d for d in dates if d not in data.cash_factors]
    if missing:
        raise SystemExit(f"cash factor missing for {len(missing)} sessions, first {missing[0]}")
    factors = [data.cash_factors[d] for d in dates]
    return dates, closes, returns, factors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--all", action="store_true", help="retired with the wide scan; --candidate is the only path")
    parser.add_argument("--candidate", action="store_true",
                        help="run only the one pre-registered configuration")
    args = parser.parse_args()
    if not args.candidate:
        # Round 104 found this path dead: it appended to a `rows` list whose policy grid had been deleted in an earlier round,
        # so running the file plain printed a DO NOTHING line, crashed, and left the controls unpriced. The wide scan is gone,
        # so the file now says so instead of half-running (r92: name the thing actually missing).
        raise SystemExit("the wide scan no longer exists here: the policy grid it swept was removed in an earlier round, and "
                         "what was left crashed on an empty list. This file prices one configuration — run it with "
                         " --candidate, or ask `frequency_cost.py`/`power_horizon.py` for the wide sweeps.")

    if args.candidate:
        print(f"pre-registered candidate: {PRE_REGISTERED.name}")
        print("bar: beat the comparator in all four windows, net of every cost shown\n")
    for label, bounds in WINDOWS.items():
        dates, closes, returns, factors = series(bounds)
        if len(closes) < 400:
            continue
        print(f"\n=== {label}  ({len(closes)} sessions, "
              f"${OPENING:,.0f} + ${MONTHLY:,.0f}/mo) ===")

        buy = funded(closes, returns, factors, dates, [1.0] * len(closes), band=0.0)
        print(f"  {'DO NOTHING: DCA into SPY':<58} ${buy.ending:>10,.0f}  "
              f"{buy.irr * 100:>6.2f}%  dd {buy.max_drawdown * 100:>5.1f}%  "
              f"cost ${buy.cost_paid:>7,.2f}")

        if args.candidate:
            path = PRE_REGISTERED.weights(closes, returns)
            targets = [w for w, _ in path]
            allowed = {i for i, (_, turn) in enumerate(path) if turn > 0.0}
            first_live = next(i for i, t in enumerate(targets) if t is not None)
            # Every configuration starts on the session the candidate can first
            # trade, so the comparator loses nothing to the model's warm-up.
            result = funded(closes, returns, factors, dates, targets,
                            PRE_REGISTERED.rebalance_band, allowed, start=first_live)
            baseline = funded(closes, returns, factors, dates, [1.0] * len(closes), 0.0,
                              None, start=first_live)
            buy = baseline
            gap = result.ending - buy.ending
            flag = "RUIN" if result.ruined else ("BEAT" if gap > 0 else "lose")
            if result.margin_calls:
                flag += f"/{result.margin_calls} calls"
            print(f"  {PRE_REGISTERED.name:<58} ${result.ending:>10,.0f}  {result.irr * 100:>6.2f}%  "
                  f"dd {result.max_drawdown * 100:>5.1f}%  cost ${result.cost_paid:>7,.2f}  "
                  f"{flag} ${gap:>+9,.0f}  {result.turns} trades   "
                  f"avg exposure {result.avg_weight * 100:.0f}%")
            print(f"  {'comparator, same first session':<58} ${buy.ending:>10,.0f}  {buy.irr * 100:>6.2f}%  "
                  f"dd {buy.max_drawdown * 100:>5.1f}%  cost ${buy.cost_paid:>7,.2f}")
            continue

        print(f"  --- controls: no signal, constant leverage, priced at cash + "
              f"{paper.BORROW_SPREAD * 10_000:.0f} bps ---")
        for control in CONTROLS:
            result = funded(closes, returns, factors, dates,
                            control.raw_weights(closes, returns), control.rebalance_band)
            gap = result.ending - buy.ending
            flag = "RUIN" if result.ruined else ("BEAT" if gap > 0 else "lose")
            if result.margin_calls:
                flag += f"/{result.margin_calls} calls"
            print(
                f"  {control.name:<58} ${result.ending:>10,.0f}  {result.irr * 100:>6.2f}%  "
                f"dd {result.max_drawdown * 100:>5.1f}%  cost ${result.cost_paid:>7,.2f}  "
                f"{flag} ${gap:>+9,.0f}  {result.turns} trades"
            )

        best = rows[0][0]
        print(f"  best of {len(GRID)} configs beats doing nothing by "
              f"${best.ending - buy.ending:+,.0f} on ${buy.paid_in:,.0f} paid in "
              f"(selection among {len(GRID)} on the same data is in-sample)")


if __name__ == "__main__":
    main()
