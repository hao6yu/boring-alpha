"""What the mixes cost once rebalancing is charged for the trades it makes.

Run: .venv/bin/python tools/rebalance_cost.py [--json]

Every capacity figure in this repository — round 73's by fund, round 78's by mix, round 80's by schedule — comes from an
engine that holds a constant weight vector. A constant weight vector has no turnover, so it is charged nothing, yet it is
being rebalanced *continuously*: the moment QQQ outruns SPY the book is implicitly selling QQQ and buying SPY, every day,
for free. Round 82 put a dollar figure on the same effect in an account that trades: the tilt, rebalanced monthly against its
own witness over sixteen years, ended $2.5M behind the growth sleeve it keeps selling. The archive's tables never saw that
because the archive's tables do not trade.

This tool charges it. Same loader, same month-ends, same spread, each fund's own posted fee — one construction moved from
"rebalanced free" to "rebalanced and billed", plus the versions an investor would actually run: drift bands of five and ten
points, and an annual decision with the deposit going in monthly. Three questions, scored at the bottom rather than asserted:
does the *ranking* of the mixes survive being billed; what does the idealisation cost per $100,000 paid in on the
construction the live book runs; and how much of it a five-point band gives back.

Two things this does not do. It does not re-derive withdrawal capacity, so it cannot overturn round 78's failure-budget
result — that is a different question, asked of a lump sum under a budget, and the answer here is only about the order and the
cost of trades. And it does not include the brake constructions: their flat months park cash, and an account that parks cash
needs a bill curve this file does not model. Silently borrowing the backtest's cash rate here would make the comparison a
different one on two axes at once, so the brake rows are deferred and the deferral is printed, not left to be noticed later.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import paper                                                 # noqa: E402
import power_horizon as ph                                   # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402

SCALE = 100_000.0
TICKET_SCALES = (5_000.0, 250_000.0)
TICKET = 9.95

CONSTRUCTIONS = (
    ("plain VOO", {"VOO": 1.0}, "the witness"),
    ("plain SPY", {"SPY": 1.0}, "what the root book holds"),
    ("25% QQQ", {"SPY": 0.75, "QQQ": 0.25}, "mix_25"),
    ("50% QQQ", {"SPY": 0.50, "QQQ": 0.50}, "the live income book"),
    ("75% QQQ", {"SPY": 0.25, "QQQ": 0.75}, "mix_75"),
    ("100% QQQ", {"QQQ": 1.0}, "mix_100, round 79's income position"),
)

FREE = "no trading cost"
PLAIN = "deposit only"
MONTHLY = f"monthly, {paper.SPREAD_BPS:.0f} bps"   # the label carries the convention it names

REGIMES = (
    (FREE, 0.0, 1, 0.0, 0.0, "rebalancing free, and so are the buys: an upper bound, not a choice"),
    (PLAIN, 100.0, 1, 3.0, 0.0, "buys charged, nothing rebalanced: the archive's premise, billed honestly"),
    (MONTHLY, 0.0, 1, 3.0, 0.0, "the live book's policy, charged"),
    ("band 5 pts", 5.0, 1, 3.0, 0.0, "five points of drift before anything is sold"),
    ("band 10 pts", 10.0, 1, 3.0, 0.0, "ten points of drift"),
    ("annual decision", 0.0, 12, 3.0, 0.0, "one decision a year, deposit invested monthly"),
)
CHARGED = (PLAIN, MONTHLY, "band 5 pts", "band 10 pts", "annual decision")


def fees() -> dict:
    return {s: paper.fee_for(s) for s in ("SPY", "QQQ", "VOO")}


def grid(closes: list, label: str, months: int) -> list:
    rows = []
    for name, weights, note in CONSTRUCTIONS:
        paid = SCALE + SCALE * ph.SCALE_RATIO * (months - 1)
        for regime, band, every, spread, commission, why in REGIMES:
            stats: dict = {}
            value = ph.simulate(closes, SCALE, SCALE * 0.10, weights, spread, commission, fees(),
                                band=band, every=every, stats=stats)[-1]
            rows.append({"window": label, "construction": name, "note": note, "regime": regime, "why": why,
                         "value": value, "paid_in": paid, "tickets": stats.get("tickets", 0),
                         "sell_months": stats.get("sells", 0), "spread_paid": stats.get("spread", 0.0),
                         "months": months, "per_year": stats.get("tickets", 0) * 12.0 / max(months - 1, 1)})
    return rows


def by(rows: list, **want) -> list:
    return [r for r in rows if all(r[k] == v for k, v in want.items())]


def idealisation_tax(rows: list, window: str, construction: str) -> dict:
    """The two ways to state the answer, kept apart on purpose.

    `spread_cost` is the bill the idealisation never charged: what the rebalancing months paid in spread that the same account,
    left to drift, would not have. It is a cost, and its sign is not in doubt. `value_gap` is what the choice did to the
    account, which is that cost *and* the drift the drifted book was allowed to keep, and its sign depends entirely on which
    sleeve ran. Adding the two together and calling the total a cost would be the oldest trick in this repository's list of
    things not to do.
    """

    free = by(rows, window=window, construction=construction, regime=FREE)[0]
    plain = by(rows, window=window, construction=construction, regime=PLAIN)[0]
    monthly = by(rows, window=window, construction=construction, regime=MONTHLY)[0]
    band5 = by(rows, window=window, construction=construction, regime="band 5 pts")[0]
    annual = by(rows, window=window, construction=construction, regime="annual decision")[0]
    voo_plain = by(rows, window=window, construction="plain VOO", regime=PLAIN)[0]
    return {"construction": construction, "window": window,
            "upper_bound": free["value"], "plain": plain["value"], "monthly": monthly["value"],
            "spread_cost": monthly["spread_paid"] - plain["spread_paid"],
            "spread_paid_monthly": monthly["spread_paid"], "spread_paid_plain": plain["spread_paid"],
            "spread_cost_pct_paid_in": (monthly["spread_paid"] - plain["spread_paid"]) / monthly["paid_in"],
            "value_gap": monthly["value"] - plain["value"],
            "value_gap_pct_paid_in": (monthly["value"] - plain["value"]) / monthly["paid_in"],
            "monthly_vs_voo": monthly["value"] - voo_plain["value"],
            "band5_value": band5["value"], "annual_value": annual["value"],
            "band5_vs_monthly": band5["value"] - monthly["value"], "annual_vs_monthly": annual["value"] - monthly["value"],
            "sell_months": monthly["sell_months"], "sell_months_band5": band5["sell_months"],
            "months": monthly["months"], "tickets": monthly["tickets"], "tickets_band5": band5["tickets"]}


def tickets(rows_note: str = "") -> list:
    """The same construction at two sizes, because a flat ticket is the only cost here that is not a proportion."""

    out = []
    closes = ph.month_closes(None)
    for scale in TICKET_SCALES:
        # A fund count, not a rebalancing policy, is what moves the ticket count in a book that adds money every month: the
        # deposit has to be bought in each sleeve whatever the band allows, so the only way to pay one ticket is to hold one
        # fund. Round 82's reader would expect the band to help here; it does not.
        for label, weights, band in (("two funds, monthly", ph.TILT, 0.0), ("two funds, band 5", ph.TILT, 5.0),
                                     ("one fund, monthly", {"QQQ": 1.0}, 0.0), ("one fund, band 5", {"QQQ": 1.0}, 5.0)):
            stats: dict = {}
            value = ph.simulate(closes, scale, scale * 0.10, weights, 3.0, TICKET, fees(), band=band,
                                stats=stats)[-1]
            paid = scale + scale * ph.SCALE_RATIO * (len(closes) - 1)
            out.append({"scale": scale, "regime": label, "value": value, "paid_in": paid,
                        "tickets": stats.get("tickets", 0), "share_of_deposit": TICKET * stats.get("tickets", 0) / paid,
                        "sell_months": stats.get("sells", 0)})
    return out


def order(rows: list, window: str, regime: str) -> list:
    got = by(rows, window=window, regime=regime)
    return sorted(got, key=lambda r: -r["value"])


CAPITAL_LADDER = (1_000.0, 2_500.0, 5_000.0, 10_000.0, 25_000.0, 50_000.0, 100_000.0, 250_000.0, 1_000_000.0)
# The three horizons the dominance question is actually asked at. The record answers the question "was it ever worth it"; the
# two-year row answers the question a person adding money every month actually has, and it is the row where a $9.95 ticket can
# turn the sign, because the edge it is being paid for is twenty years' divergence rather than two years' worth.
HORIZONS = (("two years", 2), ("five years", 5), ("the record", None))
COMMISSIONS = (0.0, 4.95, 9.95)
SPREAD = paper.SPREAD_BPS


def dominance(closes: list, capital: float, commission: float, band: float = 5.0) -> dict:
    """The P0 dominance rule, priced at one specific account size and one specific broker.

    Every other number in this file is a proportion, so it is scale-free and therefore quietly assumes the account is large
    enough that flat charges do not matter. A ticket is not a proportion: it is $9.95 whether the account is $2,500 or
    $1,000,000, and a two-sleeve book pays two of them a month. This function asks the only question that matters at the
    bottom of that range — after every ticket and every spread, does the tilt still end ahead of plain VOO, which is charged
    one ticket a month for the same discipline — and answers it with the sealed month-ends rather than with an opinion.

    The witness is given the same commission, the same spread and the same deposit schedule, because a benchmark charged a
    guessed fee is how round 81's rule exists.
    """

    deposit = capital * ph.SCALE_RATIO
    paid_in = capital + deposit * (len(closes) - 1)
    stats_tilt: dict = {}
    stats_voo: dict = {}
    tilt = ph.simulate(closes, capital, deposit, ph.TILT, SPREAD, commission, fees(), band=band,
                       stats=stats_tilt)[-1]
    witness = ph.simulate(closes, capital, deposit, {"VOO": 1.0}, SPREAD, commission, fees(),
                          stats=stats_voo)[-1]
    return {"capital": capital, "commission": commission, "band": band, "months": len(closes),
            "paid_in": paid_in, "tilt": tilt, "witness": witness, "gap": tilt - witness,
            "tilt_tickets": stats_tilt.get("tickets", 0), "witness_tickets": stats_voo.get("tickets", 0),
            "tilt_ticket_share": commission * stats_tilt.get("tickets", 0) / paid_in,
            "witness_ticket_share": commission * stats_voo.get("tickets", 0) / paid_in,
            "dominates": tilt > witness}


def scan(capital: float, commission: float, band: float = 5.0) -> list:
    """Dominance for one account size and one broker, at each horizon in `HORIZONS`."""

    out = []
    for label, years in HORIZONS:
        since = None if years is None else ph.last_date() - dt.timedelta(days=int(365.25 * years))
        closes = ph.month_closes(since)
        cell = dominance(closes, capital, commission, band)
        cell["horizon"] = label
        out.append(cell)
    return out


def crossover(commission: float, band: float = 5.0, closes: list | None = None) -> dict:
    """The smallest account at which the tilt still dominates, and the honest statement that the answer is a bracket.

    The ladder is coarse on purpose: the interesting claim is not a dollar figure precise to the cent — it is that the sign of
    the comparison turns with size, and where it turns. Reporting a single crossover dollar would imply the function is smooth
    and monotone in capital, which it is not: the deposit is a fixed proportion, so the ticket share falls as a clean power of
    size, but the gap the tickets are eating is itself a path-dependent number.
    """

    closes = ph.month_closes(None) if closes is None else closes
    cells = [dominance(closes, cap, commission, band) for cap in CAPITAL_LADDER]
    firsts = [c["capital"] for c in cells if c["dominates"]]
    below = [c for c in cells if not c["dominates"]]
    return {"commission": commission, "band": band, "cells": cells,
            "dominates_at_every_size": not below, "fails_at_every_size": not firsts,
            "first_capital_dominating": min(firsts) if firsts else None,
            "last_capital_failing": max(c["capital"] for c in below) if below else None,
            "smallest_ticket_share": cells[-1]["tilt_ticket_share"], "largest_ticket_share": cells[0]["tilt_ticket_share"]}


def report(rows: list, ticket_rows: list) -> None:
    windows = sorted({r["window"] for r in rows})
    for window in windows:
        months = by(rows, window=window)[0]["months"]
        print(f"\n  {window}: {months} month-ends, ${SCALE:,.0f} opening and ${SCALE * 0.10:,.0f} a month, every fund"
              " charged its own posted fee")
        print("  " + "-" * 100)
        print(f"     construction      no trading cost      deposit only      monthly, {SPREAD:.0f} bps"
              "        band 5 pts        annual    spread paid    sold, monthly / band 5")
        for name, _, note in CONSTRUCTIONS:
            line = f"  {name:<18}"
            for regime in (FREE, PLAIN, MONTHLY, "band 5 pts", "annual decision"):
                line += f" {by(rows, window=window, construction=name, regime=regime)[0]['value']:>15,.0f}"
            m = by(rows, window=window, construction=name, regime=MONTHLY)[0]
            b5 = by(rows, window=window, construction=name, regime="band 5 pts")[0]
            line += (f" {m['spread_paid']:>11,.0f}    {m['sell_months']:>3} / {b5['sell_months']:<3} months")
            print(line)
        print("     (band 10 pts is in the data and in the JSON; the columns are the five a reader would choose between)")
        tax = idealisation_tax(rows, window, "50% QQQ")
        print(f"     the 50/50 book sold in {tax['sell_months']} of {tax['months']} months and paid ${tax['spread_paid_monthly']:,.0f}"
              f" of spread against ${tax['spread_paid_plain']:,.0f} for the drifted twin:"
              f" **the rebalancing itself cost ${tax['spread_cost']:,.0f}**,"
              f" {100 * tax['spread_cost_pct_paid_in']:.3f}% of everything paid in")
        print(f"     and the account ended ${abs(tax['value_gap']):,.0f}"
              f" {'behind' if tax['value_gap'] < 0 else 'ahead of'} that twin — a number that mixes the spread above with"
              f" the drift the other book was allowed to keep, so its sign is a fact about the tape"
              f" ({100 * tax['value_gap_pct_paid_in']:.2f}% of paid-in)")
        print(f"     versus plain VOO on identical charges: the 50/50 book is ${tax['monthly_vs_voo']:,.0f} ahead;"
              f" a 5-point band is ${tax['band5_vs_monthly']:+,.0f} against monthly rebalancing and an annual decision"
              f" ${tax['annual_vs_monthly']:+,.0f}")

    print("\n  the ticket, which is the only cost here that does not scale:")
    for t in ticket_rows:
        print(f"     ${t['scale']:>9,.0f} account, {t['regime']:<8} ${t['value']:>12,.0f} on ${t['paid_in']:,.0f} paid in,"
              f" {t['tickets']:>4} tickets = {100 * t['share_of_deposit']:.2f}% of every dollar,"
              f" sold in {t['sell_months']} months")

    print("\n  dominance at account size, after every ticket is paid (the P0 rule, priced):")
    print("     broker   horizon        " + "".join(f"{c / 1000.0:>9,.1f}k" for c in CAPITAL_LADDER)
          + "     gap per dollar paid in, and the sign of the comparison")
    for commission in COMMISSIONS:
        for label, years in HORIZONS:
            since = None if years is None else ph.last_date() - dt.timedelta(days=int(365.25 * years))
            closes = ph.month_closes(since)
            cells = [dominance(closes, cap, commission) for cap in CAPITAL_LADDER]
            line = f"     ${commission:>5.2f} {label:<12}"
            for cell in cells:
                line += f"{cell['gap'] / cell['paid_in'] * 100:>+8.1f}"
            print(line)
            failing = [c["capital"] for c in cells if not c["dominates"]]
            if failing:
                print(f"        on this broker the tilt loses to plain VOO up to ${max(failing):,.0f} of capital at this"
                      " horizon — the two-sleeve form is not the buy there, and one fund is")

    print("\n  scored, against what this file claimed before it was run:")
    for window in windows:
        ranks = {r: [x["construction"] for x in order(rows, window, r)] for r in (PLAIN, MONTHLY, "band 5 pts")}
        same = ranks[PLAIN] == ranks[MONTHLY] == ranks["band 5 pts"]
        tax = idealisation_tax(rows, window, "50% QQQ")
        print(f"     ranking survives being charged: {'yes — identical under all three charged regimes' if same else 'NO,'
              + ' billing reordered the mixes'} ({window}); the 50/50 book is ${tax['monthly_vs_voo']:,.0f} ahead of plain"
              f" VOO on identical charges")
    taxes = [idealisation_tax(rows, w, "50% QQQ") for w in windows]
    print(f"     the bill the idealisation never charged is"
          f" {100 * min(t['spread_cost_pct_paid_in'] for t in taxes):.3f}-{100 * max(t['spread_cost_pct_paid_in'] for t in taxes):.3f}%"
          " of paid-in, and it is a cost in every window. The end-value effect of the same choice is"
          f" {'one-signed' if len({1 if t['value_gap'] > 0 else -1 for t in taxes}) == 1 else 'NOT one-signed'},"
          " so it is reported per window and never averaged.")
    print("     deferred on purpose: the brake constructions park cash in their flat months and need a bill curve this file"
          " does not model.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows, ticket_rows = [], []
    for label, since in (("every month the witness has existed", None), ("last five years", 5)):
        closes = ph.month_closes(None if since is None else ph.last_date() - dt.timedelta(days=int(365.25 * since)))
        rows += grid(closes, label, len(closes))
    ticket_rows = tickets()
    if args.json:
        print(json.dumps({"rows": rows, "taxes": [idealisation_tax(rows, w, "50% QQQ") for w in
                                                  sorted({r["window"] for r in rows})], "tickets": ticket_rows}, indent=2))
    else:
        report(rows, ticket_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
