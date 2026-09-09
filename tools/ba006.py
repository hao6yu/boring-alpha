#!/usr/bin/env python3
"""BA-006: a *sized* Coinbase BTC sleeve against the P0 blend — the only form BA-005's failure left open.

BA-005 held 100% of the account in one asset and failed its drawdown and ruin gates while its terminal was 17x the index's. Its own verdict
said a Coinbase candidate has to hold the volatile asset at a fractional weight and be graded against a blend, so that is what this prices:
same asset, same locked signal, same frequency, same window, same gate — only the size differs, and size is what an *income* objective is
about. The weights are a fixed ladder parsed out of the spec, and the deliverable is the affordable monthly bill, not the terminal.

    weight   sleeve's bill   vs P0     P(erase) at P0's bill   max DD    seatbelt (signal vs plain hold)

Four legs at every weight: the signal blend (candidate), the plain-hold blend (the seatbelt test — a model that cannot beat owning the asset
with no model is a seatbelt), P0 (100% VOO, the objective's own bar, priced before evidence), and QQQ (the archive's standing empirical bar,
which owns the drawdown gate).

Exit codes carry the fee logic rather than hiding it: 0 = PASS at some weight (only ever printable with a current fee record, rule 103),
1 = failure at every weight, 3 = a weight cleared every gate that a fee *could* matter to, and the record is missing. A FAIL is publishable
without the record — it needs no cost assumption to be true.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import ba005                                                                   # noqa: E402  the locked signal, grid, and ruin conventions
import fund_fees                                                               # noqa: E402  expense ratios, so none is typed here
import monthly_income_race as mir                                              # noqa: E402  the archive's definition of an affordable bill
import venue_fees                                                              # noqa: E402  the fee, or the refusal
import withdrawal_capacity as wc                                              # noqa: E402  corpus paths
from boring_alpha.data.csv_loader import load_csv_market_data                   # noqa: E402

SPEC = ROOT / "docs" / "strategies" / "BA-006.md"
SPEC_TEXT = SPEC.read_text()

#: The locked ladder and margin, parsed out of the spec so the two cannot drift apart (the practice `ba005.py` established).
_raw_weights = re.search(r"\*\*Weights:\*\*\s*the fixed set\s*\*\*\{([^}]*)\}", SPEC_TEXT)
WEIGHTS = tuple(float(x.strip().rstrip("%")) / 100.0 for x in _raw_weights.group(1).split(","))
BILL_MARGIN = float(re.search(r"by at least\s+(\d+)\s*%\s*relative", SPEC_TEXT).group(1)) / 100.0
GATE = ba005.DD_LIMIT
YEARS = ba005.RUIN_YEARS
BUDGET = ba005.P_FAIL_MAX
SLEEVE_SYMBOL, BASE_SYMBOL = "BTC-USD", "VOO"


def blend(strat: list[float], base: list[float], w: float) -> list[float]:
    """Monthly-rebalanced blend: the account earns w of the sleeve's monthly return and 1-w of the base's."""

    return [w * s + (1.0 - w) * b for s, b in zip(strat, base)]


def drawdown(returns: list[float]) -> float:
    wealth = peak = worst = 1.0
    for r in returns:
        wealth *= 1.0 + r
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1.0)
    return -worst


def median_multiple(returns: list[float]) -> float:
    wealth = 1.0
    for r in returns:
        wealth *= 1.0 + r
    return wealth


#: The disclosure ladder: the same test re-started whole years later. All rolls reported, chosen before looking, because the only honest
#: answer to "how much of this is the start date?" is every start date at once, and a reader shown only the agreeing roll saw a selection.
ROLL_YEARS = (0, 2, 4)


def price_legs(md, start: date | None = None) -> dict:
    """Every monthly return series the four legs need, on the archive's grid, from `start` (the locked start by default)."""

    months, qqq_returns, cash_rates = ba005.grid(md, start or ba005.WINDOW_START)
    btc = ba005.crypto_closes(ba005.PAIR)
    voo = [md.bar(months[i], BASE_SYMBOL).close / md.bar(months[i - 1], BASE_SYMBOL).close - 1.0
           for i in range(1, len(months))]
    hold = [btc[months[i]] / btc[months[i - 1]] - 1.0 for i in range(1, len(months))]
    return {"months": months, "qqq": qqq_returns, "cash": cash_rates, "btc": btc, "voo": voo, "hold": hold}


def sleeve_returns(legs: dict, fee_bps: float, cash: list[float] | None = None) -> list[float]:
    """The sleeve's monthly returns. `cash` lets the caller price the below-the-line months at some other yield — which is what the
    venue's own conversion probe forces: the specs credit a T-bill, and a T-bill is not something this venue holds."""

    return ba005.run(legs["months"][1:], legs["btc"], cash if cash is not None else legs["cash"], fee_bps, [])["returns"]


def bill_of(returns: list[float]) -> float | None:
    return mir.safe_amount(returns, ba005.CAPITAL, YEARS, BUDGET, floor=1.0)


def gates(legs: dict, costed: list[float], w: float, p0_bill: float, p0_stats: dict, qqq_dd: float) -> dict:
    """Conditions 1 to 4, computed once for the table, the roll ladder, and the summary alike.

    One implementation on purpose: a roll ladder judged by a looser rule than the table would report "survives" on a roll that fails the
    seatbelt, and the whole point of the ladder is to not mislead about where the result lives.
    """

    cand = blend(costed, legs["voo"], w)
    bill = bill_of(cand)
    hold_bill = bill_of(blend(legs["hold"], legs["voo"], w))
    stats = mir.plan_stats(cand, ba005.CAPITAL, p0_bill, YEARS, floor=1.0)
    dd = drawdown(cand)
    ok = {"bill": bill is not None and bill > p0_bill * (1.0 + BILL_MARGIN),
          "erase": stats["p_erase"] <= p0_stats["p_erase"],
          "drawdown": dd <= GATE * qqq_dd,
          "seatbelt": bill is not None and hold_bill is not None and bill > hold_bill}
    return {"bill": bill, "hold_bill": hold_bill, "stats": stats, "dd": dd, "ok": ok,
            "clears": all(ok.values()), "median": median_multiple(cand)}


def roll_lines(md, fee: float | None) -> list[str]:
    """How much of the result is the choice of start date. Every roll, every weight, no suppression.

    A disclosure, not a re-cut: the graded verdict stays at the locked window and no roll can change it.
    """

    out: list[str] = []
    p = out.append
    p("")
    p("    sensitivity to where the window starts — every roll at every weight, the verdict unchanged by any of them:")
    p(f"    {'start':<12}{'months':>7}{'P0 bill':>9}  " + "  |  ".join(f"{w:.0%} sleeve" for w in WEIGHTS))
    for years in ROLL_YEARS:
        start = date(ba005.WINDOW_START.year + years, ba005.WINDOW_START.month, ba005.WINDOW_START.day)
        legs = price_legs(md, start)
        if len(legs["voo"]) < YEARS * 12 + 12:
            p(f"    {start.isoformat():<12}{len(legs['voo']):>7}   too few months left to hold {YEARS}-year windows and any windows")
            continue
        p0_bill = bill_of(legs["voo"])
        p0_stats = mir.plan_stats(legs["voo"], ba005.CAPITAL, p0_bill, YEARS, floor=1.0)
        costed = sleeve_returns(legs, fee if fee is not None else 0.0)
        cells = []
        for w in WEIGHTS:
            g = gates(legs, costed, w, p0_bill, p0_stats, drawdown(legs["qqq"]))
            failed = ",".join(k for k, v in g["ok"].items() if not v) or "none"
            cells.append(f"${g['bill']:,.0f} ({g['bill'] / p0_bill - 1.0:+.0%}, {'clears' if g['clears'] else 'fails ' + failed})")
        p(f"    {start.isoformat():<12}{len(legs['voo']):>7}{p0_bill:>8,.0f}  " + "  |  ".join(cells))
    p("    read this as the sample shrinking, not as a menu: a later start has fewer windows and fewer crash cycles in it.")
    return out


def roll_summary(md, fee: float | None) -> str:
    """One line for the verdict block: where in the roll ladder the result lives, and where it does not."""

    held = []
    for years in ROLL_YEARS:
        start = date(ba005.WINDOW_START.year + years, ba005.WINDOW_START.month, ba005.WINDOW_START.day)
        legs = price_legs(md, start)
        if len(legs["voo"]) < YEARS * 12 + 12:
            continue
        p0_bill = bill_of(legs["voo"])
        p0_stats = mir.plan_stats(legs["voo"], ba005.CAPITAL, p0_bill, YEARS, floor=1.0)
        costed = sleeve_returns(legs, fee if fee is not None else 0.0)
        best = max(gates(legs, costed, w, p0_bill, p0_stats, drawdown(legs["qqq"]))["bill"] / p0_bill - 1.0 for w in WEIGHTS)
        clears = any(gates(legs, costed, w, p0_bill, p0_stats, drawdown(legs["qqq"]))["clears"] for w in WEIGHTS)
        held.append((start, best, clears))
    if not held:
        return ""
    clear = [s for s, gain, ok in held if ok]
    if len(clear) == len(held):
        return "    every start on the ladder reproduces a clearing weight; this is not a start-date artefact."
    if not clear:
        return ("    no start on the ladder reproduces a clearing weight: the graded window is the only one where it appears, and a result "
                "carried by one start date is that date's result, not a property of the rule.")
    return ("    a clearing weight appears at " + ", ".join(s.isoformat() for s in clear) + " and nowhere at "
            + ", ".join(s.isoformat() for s, gain, ok in held if not ok)
            + "; a decision made today sits closer to the later starts than the earlier ones.")


def report_lines(md, fee: float | None, record: dict | None, quiet: bool = False) -> tuple[list[str], int]:
    legs = price_legs(md)
    months = legs["months"]
    out: list[str] = []
    p = out.append
    p(f"  BA-006 · a sized {SLEEVE_SYMBOL} sleeve on BA-005's signal, the rest in {BASE_SYMBOL} · {months[1]} to {months[-1]}")
    p(f"    inputs: crypto {ba005.sha(ba005.CRYPTO_FILE)} · equity {ba005.sha(wc.SNAPSHOT)} · spec {ba005.sha(SPEC)}")
    windows = len(legs["voo"]) - YEARS * 12 + 1
    p(f"    {len(legs['voo'])} months · {windows} {YEARS}-year windows, one window {100.0 / windows:.1f} points of failure rate · "
      f"failure budget {BUDGET:.0%} · promise: ends whole")
    looks = max(1, len(legs["voo"]) // (YEARS * 12))
    p(f"    the windows overlap month by month: {windows} of them are {looks} non-overlapping looks at one decade, so read every rate below"
      f" as a sample of {looks}, not of {windows}")
    p(f"    the base leg is {BASE_SYMBOL} at {fund_fees.fee_for(BASE_SYMBOL) * 10_000:g} bps and the bar {ba005.BARS[0]} at "
      f"{fund_fees.fee_for(ba005.BARS[0]) * 10_000:g} bps, both already inside the total-return series")

    p0_bill = bill_of(legs["voo"])
    p0_erase = mir.plan_stats(legs["voo"], ba005.CAPITAL, p0_bill, YEARS, floor=1.0)
    p0_dd = drawdown(legs["voo"])
    qqq_dd = drawdown(legs["qqq"])
    p(f"    P0 ({BASE_SYMBOL}, held): affordable bill ${p0_bill:,.0f}/mo · P(erase) at its own bill {p0_erase['p_erase']:.0%} · median "
      f"{p0_erase['median_mult']:.2f}x · max DD {p0_dd:.1%} · the drawdown gate is {GATE:g}x {ba005.BARS[0]}'s {qqq_dd:.1%} = "
      f"{GATE * qqq_dd:.1%}")
    p(f"    sleeve costed at {'the recorded ' + format(fee, '.0f') + ' bps' if fee is not None else '0 bps (no fee record; a PASS still requires one)'}")
    p("")
    p(f"    {'weight':<8}{'bill/mo':>9}{'vs P0':>8}{'P(erase)':>10}{'max DD':>8}{'median':>8}{'seatbelt':>11}   gate")

    gross_sleeve = sleeve_returns(legs, 0.0)
    any_clear, any_pass, clear_margin = False, False, None
    for w in WEIGHTS:
        costed = sleeve_returns(legs, fee if fee is not None else 0.0)
        cand = blend(costed, legs["voo"], w)
        held = blend(legs["hold"], legs["voo"], w)
        bill, bill_hold = bill_of(cand), bill_of(held)
        stats = mir.plan_stats(cand, ba005.CAPITAL, p0_bill, YEARS, floor=1.0)
        dd = drawdown(cand)
        c1 = bill is not None and bill > p0_bill * (1.0 + BILL_MARGIN)
        c2 = stats["p_erase"] <= p0_erase["p_erase"]
        c3 = dd <= GATE * qqq_dd
        c4 = bill is not None and bill_hold is not None and bill > bill_hold
        gates = "".join("1234"[i] for i, ok in enumerate((c1, c2, c3, c4)) if not ok)
        note = "clears 1-4" if not gates else f"fails {gates}"
        if not gates:
            any_clear = True
            clear_margin = bill - bill_hold if clear_margin is None else max(clear_margin, bill - bill_hold)
            if fee is not None:
                any_pass = True
                note += " · PASS"
        p(f"    {w:>7.0%} {bill:>8,.0f} {bill / p0_bill - 1.0:+7.1%} {stats['p_erase']:>9.0%} {dd:>7.1%} "
          f"{median_multiple(cand):>7.2f}x{(bill - bill_hold):>+9,.0f}   {note}")

    if not quiet:
        p("")
        p("    does the fee decide anything? the most fee-exposed weight on the grid `ba005` already publishes:")
        top = max(WEIGHTS)
        for bps in ba005.FEE_GRID_BPS:
            costed = sleeve_returns(legs, bps)
            bill = bill_of(blend(costed, legs["voo"], top))
            p(f"      {bps:>6.0f} bps → ${bill:,.0f}/mo at {top:.0%} sleeve ({bill / p0_bill - 1.0:+.1%} vs P0)"
              + ("  <- the fee on record" if fee is not None and abs(bps - fee) < 1e-9 else ""))

    for line in roll_lines(md, fee):
        p(line)

    summary = roll_summary(md, fee)
    if summary:
        p("")
        p(summary)

    zero = [0.0] * len(legs["cash"])
    # Named rather than reusing `costed`: the fee grid above rebinds that name on every rung, and a stale binding here once made the
    # T-bill column print the 240 bps bills — a wrong number that looked entirely plausible, which is the worst kind.
    costed_fee = sleeve_returns(legs, fee if fee is not None else 0.0)
    costed_zero = sleeve_returns(legs, fee if fee is not None else 0.0, zero)
    p("")
    p("    the cash leg, both ways it could actually be held — the specs credit T-bills, and the conversion probe says this venue has no")
    p("    such product for an account that never leaves it (no USDC-USD book; BTC-USDC delisted), and what idle USD earns there is a")
    p("    product fact behind the same 403 wall:")
    p(f"    {'weight':<8}{'bill, T-bill cash':>18}{'bill, zero-yield cash':>22}{'the yield was worth':>20}")
    worst_gap = 0.0
    for w in WEIGHTS:
        b_tre = bill_of(blend(costed_fee, legs["voo"], w))
        b_zero = bill_of(blend(costed_zero, legs["voo"], w))
        worst_gap = max(worst_gap, (b_tre - b_zero) / p0_bill)
        p(f"    {w:>7.0%}{b_tre:>17,.0f}{b_zero:>22,.0f}{b_tre - b_zero:>19,.0f}")
    p(f"    at most {worst_gap:.1%} of P0's bill turns on which cash the account actually holds, so the T-bill assumption is"
      + (" load-bearing: a venue that pays nothing on idle balances would take the result away on its own."
         if worst_gap > BILL_MARGIN else " not load-bearing: the clearing row survives a cash leg that earns nothing."))

    if any_pass:
        p(f"\n    PASS — a sized sleeve clears all four gates at a recorded fee of {fee:.0f} bps.")
        if clear_margin is not None:
            p(f"    Condition 4 passed by ${clear_margin:,.0f}/mo, which is a hair: the signal is not what makes this work, the sleeve is,")
            p("    and the honest reading of this table is 'a small slice of bitcoin raises the affordable bill' rather than 'a model beat the index'.")
        p("    What that licenses is one thing: a fifth forward book at the largest passing weight, sealed by the existing monthly loop, with")
        p("    the same 24-entry bar before any claim of skill. Not more weight, not a second asset, not a higher frequency.")
        return out, 0
    if any_clear:
        p("\n    NO VERDICT — a weight cleared all four risk gates, and the spec's fifth condition is a fee record this lab does not have.")
        p("    Costs almost certainly do not decide it (see the grid above), which is exactly why the licence condition exists: a pass is a")
        p("    trade permission, and this repository does not issue trade permissions against costs it cannot see. `tools/venue_fees.py ingest`")
        return out, 3
    p("\n    FAIL at every weight on the ladder, so the Coinbase line ends here as BA-005 said it would: no weight of this signal on this")
    p("    asset beats P0's monthly-income promise on this record. The spec locked that sentence before the numbers existed, and the numbers")
    p("    did not move it. No re-cut weights, no different signal, no longer window, no second asset.")
    return out, 1


def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    md = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    record = venue_fees.load()
    fee = None
    if record is not None and venue_fees.age_days(record) <= venue_fees.MAX_AGE_DAYS:
        fee = float(record["taker_bps"])
    lines, code = report_lines(md, fee, record)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
