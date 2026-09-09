"""This month's ticket for the construction the repository currently stands behind: a trend rule, sheltered.

Run: .venv/bin/python tools/shelter_ticket.py [--capital 100000] [--payout 567.22] [--record long] [--conv start]
         [--shelter IEF] [--asof YYYY-MM-DD] [--json]

The previous ticket, `monthly_ticket.py`, was written at round 12 for a 1.25x book and opened by calling that plan "the
only mechanism in this repository that beats plain DCA". Rounds 29 and 30 withdrew that claim, by charging the loan: with
financing priced at what a desk posts, the levered plan loses to holding the same fund. Round 61 found no configuration
that beats the index on return at all, and round 68 settled what the surviving construction is worth — not on return, on
**withdrawal capacity**, which is the axis a monthly income plan actually lives on. So this file replaces the claim, and
keeps the one feature the old ticket got right: **a ticket that cannot refuse is not advice, it is marketing.**

What the plan is, in one line: hold the equity sleeve while it is above its 200-day average, and when it is not, hold an
intermediate Treasury ETF instead of cash. Read on the first trading day of the month before the one it governs. Every
number below comes from the same two functions the forward book and the backtest use, so this sheet cannot quietly
disagree with the evidence it cites.

## The claim, stated before the arithmetic

  * The rule does not beat plain VOO on return. It has never done so in this archive (round 61, 0 of 26 configurations),
    and the ticket says so on every print, because the opposite belief is what costs people money.
  * What it beats plain VOO on is the amount a plan can pay every month and still keep its promise in 95 of 100 ten-year
    windows: on the long record, $567.22 against $436.76 per $100,000 — 30% more income for a lower failure rate, which
    is only possible because the rule removes the *order* of returns, not their average (round 68).
  * The shelter exists because the trend rule is in the safe asset a fifth of the time, and a fifth of a plan parked at
    zero earns nothing. IEF instead of cash is worth about $73 a month per $100,000 at a pessimal 0.60% fee and $63 at the
    flat 0.35% this repository charges unposted funds (rounds 64, 66).
  * The plan has a ceiling and it is not a soft one. Above roughly $775/mo per $100,000 the hedge stops covering
    failures and becomes pure cost; above it this ticket is not issued (rounds 65, 67).

## When this ticket refuses

  1. **No average, no ticket.** The rule needs 200 sessions. On a short record it does not degrade to "no trend": it
     refuses. A rule asked before it can answer has historically answered "sell", which is a data artefact with an order
     attached (rounds 45, 66).
  2. **A withdrawal above the capacity.** Past the ceiling the failure budget is met by luck rather than by the rule, and
     the ticket prints the ceiling it would need instead of the number it was given.
  3. **A withdrawal the plain index supports better.** If the plan cannot clear the comparator's own safe withdrawal by
     round 60's $25 bar per $100,000, the extra moving part is not earning its keep and the ticket says to buy the fund.
  4. **A shelter the file has no price for.** The off-equity leg must have a posted close; a fund the archive does not
     carry is not a shelter, it is a hope.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import correction_table as ct                                # noqa: E402
import paper                                                 # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import sleeve_table as sw                                    # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data       # noqa: E402

BAR = ct.BAR
YEARS = 10
P_MAX = 0.05


def plan_fees(shelter: str) -> tuple[float, float]:
    """(fee charged on the shelter, fee charged on the equity leg). Both are named on every print."""

    return (0.0 if shelter == sl.CASH else paper.fee_for(shelter)), paper.fee_for("SPY")


def windows_map() -> dict:
    """The three windows the sheet will quote, and the refusal boundary between them. `recent` is not this file's date to
    invent: it is the first session every swept fund can be scored on, owned by `sleeve_table` (round 71's rule that the
    sheet is generated from the tools that measured the claim, not restated beside them)."""

    d = sw.data()
    return {"long": ct.SINCE, "panel": ct.PANEL, "recent": sw.common_start(d)}


WINDOWS = windows_map()


def measure_all(record: str, conv: str, shelter: str, since: dt.date, years: int) -> dict:
    """The plan, the index and the cheapest alternative, all on one record and one convention.

    Always measured on a $100,000 basis and scaled by the caller. The measures are not linear in capital — the promise has
    an absolute floor in it — so a per-account measurement and a rescaling of a per-$100k one are different numbers, and
    every figure this repository quotes is quoted per $100,000. Scaling is a statement about proportionality, so it is
    done in one place where it can be seen.
    """

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    spy = sl.legs(data, "SPY")
    marks = {c: sl.month_signal(sorted(spy), spy, c) for c in ("start", "end")}
    plan = ct.measure(data, spy, "MA200", shelter, since, marks, conv, 100_000.0, ct.PUBLISHED_PAYOUT, years, P_MAX)
    index = ct.measure(data, spy, "index", sl.CASH, since, marks, conv, 100_000.0, ct.PUBLISHED_PAYOUT, years, P_MAX)
    static = ct.measure(data, spy, "static 60/40", shelter, since, marks, conv, 100_000.0, ct.PUBLISHED_PAYOUT,
                        years, P_MAX)
    return {"data": data, "spy": spy, "plan": plan, "index": index, "static": static}


def decide(data, asof: dt.date | None) -> dict:
    """The month's decision, from the same function the forward book trades. Not reimplemented here, deliberately."""

    d = asof or max(data.dates)
    weights, _last, read_on, want_spy = paper.shelter_weights(data, d)
    return {"asof": d, "weights": weights, "read_on": read_on, "in_equities": bool(want_spy)}


def issue(capital: float, payout: float | None, record: str, conv: str, shelter: str, asof: dt.date | None,
          years: int = YEARS) -> dict:
    """Work out whether a ticket may be printed at all, and what it would say."""

    since = WINDOWS[record]
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    spy = sl.legs(data, "SPY")
    m = measure_all(record, conv, shelter, since, years)
    plan, index, static = m["plan"], m["index"], m["static"]
    sh_fee, eq_fee = plan_fees(shelter)
    sig = decide(m["data"], asof)

    scaled = capital / 100_000.0
    # An explicit --payout is an absolute dollar ask and stays one. The default has to be this account's own safe
    # withdrawal, which is the measured figure scaled — comparing a per-$100,000 payout against a $50,000 account's
    # ceiling made the sheet refuse itself out of existence at half capital.
    want = payout if payout is not None else plan["safe"] * scaled
    refusals: list[str] = []

    if shelter != sl.CASH and shelter not in data.by_date[max(data.dates)]:
        refusals.append(f"the file carries no price for {shelter}: a shelter nobody quotes is not a shelter")
    if sig["read_on"] is None or (not sig["weights"]):
        refusals.append("the 200-day average does not exist yet on this record; the rule declines rather than guessing")
    if want > (plan["cap"] or 0.0) * scaled + 0.005:
        refusals.append(f"{want:,.2f}/mo is past this plan's capacity of {(plan['cap'] or 0) * scaled:,.2f}/mo at "
                        f"{capital:,.0f}; above the ceiling the hedge covers nothing and is charged anyway")
    if plan["safe"] * scaled - index["safe"] * scaled < BAR * scaled:
        gap = (plan["safe"] - index["safe"]) * scaled
        if gap < 0:
            refusals.append(f"loses to holding the fund itself by {abs(gap):,.2f}/mo on the {record} record from "
                            f"{since}; the sheet will not print a premium that is not there")
        else:
            refusals.append(f"the plan clears the index by only {gap:,.2f}/mo, under the ${BAR:.0f} materiality bar; "
                            f"buy the fund and skip the moving part")

    companions = []
    for other, other_since in sorted(WINDOWS.items()):
        if other == record:
            continue
        o = measure_all(other, conv, shelter, other_since, years)
        companions.append({"record": other, "since": o["plan"]["since"], "n": o["plan"]["n"],
                           "safe": o["plan"]["safe"] * scaled, "index": o["index"]["safe"] * scaled,
                           "delta": (o["plan"]["safe"] - o["index"]["safe"]) * scaled,
                           "p_fail_index": o["index"]["p_fail"]})

    return {"data": m["data"], "spy": m["spy"], "companions": companions,
            "capital": capital, "payout_asked": want, "payout": want, "record": record, "conv": conv,
            "years": years, "shelter": shelter, "shelter_fee": sh_fee, "equity_fee": eq_fee,
            "signal": sig, "plan": plan, "index": index, "static": static, "scale": scaled,
            "safe": plan["safe"] * scaled, "safe_index": index["safe"] * scaled,
            "delta": (plan["safe"] - index["safe"]) * scaled,
            "cap": (plan["cap"] or 0.0) * scaled, "refusals": refusals, "issued": not refusals}


def render(t: dict) -> str:
    """The sheet itself. Numbers are read from `t`, never typed."""

    s = t["scale"]
    out = [f"  sheltered-trend ticket · {t['record']} record from {t['plan']['since']} · "
           f"{t['conv']}-of-month reading · {t['years']}-year promise at a {P_MAX:.0%} failure budget"]
    if not t["issued"]:
        out.append("\n  NOT ISSUED. The plan is not being recommended at these numbers:")
        for r in t["refusals"]:
            out.append(f"    - {r}")
        out.append("    The arithmetic behind the refusal is in `tools/correction_table.py`; nothing here is a maybe.")
        return "\n".join(out)

    held = next(iter(t["signal"]["weights"]))
    out.append("")
    out.append(f"  1. THIS MONTH  ({t['signal']['asof']}, trend read {t['signal']['read_on']})")
    out.append(f"     {'HOLD ' + held + ' at 100% of the account' if not t['signal']['in_equities'] else 'HOLD the equity sleeve (SPY/VOO) at 100%'}")
    out.append(f"     {'the shelter, paying ' + format(t['shelter_fee'], '.2%') + ' a year in fees' if held != 'SPY' else 'no leverage, no borrowing, no second position'}")
    out.append(f"     one switch when it flips: about {wc.TURNOVER_COST:.2%} of the account in costs, plus "
               f"{t['equity_fee'] if t['signal']['in_equities'] else t['shelter_fee']:.2%} a year while it sits there")
    out.append("")
    out.append(f"  2. WHAT THE PLAN SUPPORTS  (capital {t['capital']:,.0f})")
    out.append(f"     this plan pays      {t['safe']:>10,.2f}/mo   and failed in {t['plan']['p_fail']:.1%} of "
               f"{t['plan']['n']} ten-year windows")
    out.append(f"     plain VOO pays       {t['safe_index']:>10,.2f}/mo   and failed in {t['index']['p_fail']:.1%}")
    out.append(f"     the difference       {t['delta']:>+10,.2f}/mo   = {t['delta'] / t['safe_index']:+.0%} more income")
    out.append(f"     the ceiling          {t['cap']:>10,.2f}/mo   (the withdrawal at which the plan first stops "
               f"beating the index)")
    out.append(f"     the rule was sheltered {t['plan']['duty']:.1%} of the days on this record")
    out.append("")
    if t["companions"]:
        out.append("  3. THE OTHER WINDOWS   (printed because one number is a position, not an answer)")
        for c in t["companions"]:
            flag = "premium" if c["delta"] >= ct.BAR else "no premium"
            out.append(f"     {c['record']:7} from {c['since']}: {c['safe']:,.2f}/mo vs the fund's own {c['index']:,.2f}"
                       f" = {c['delta']:>+10,.2f}   ({flag}; the fund failed {c['p_fail_index']:.1%} of windows)")
        out.append("     The premium appears only on records containing a stretch in which plain DCA ran out of money.")
        out.append("     On the window every fund shares, none of them did, and the hedge is a cost. `sleeve_table.py`")
        out.append("     holds all fifteen rows; the decision to shelter anyway is a bet that such a stretch returns.")
    else:
        out.append("  3. THE OTHER WINDOWS   (this is the common window; there is no wider one to compare against)")
    out.append("")
    out.append(f"  4. WHAT IT IS NOT")
    out.append(f"     not a return alpha. On this record the plan's own compound growth is below the index's; it pays "
               f"more monthly because it sidesteps the sequence, not because it compounds harder (round 61, 0 of 26 "
               f"configurations beat the index on return).")
    naive = t["static"]
    out.append(f"     not a balanced portfolio. 60/40 with the other half in {t['shelter']} pays "
               f"{naive['safe'] * s:,.2f}/mo and failed in {naive['p_fail']:.1%} of windows; the trend rule is the thing "
               f"doing the work, not a second asset sitting next to it.")
    out.append("")
    out.append(f"  5. WHAT WOULD MAKE THIS WRONG")
    out.append(f"     a shelter fee above {t['shelter_fee']:.2%} was assumed and charged; a fund that actually costs "
               f"more moves the income down roughly ${0.0035 * t['capital'] / 12:,.0f}/mo per 35 bps of extra fee, all of "
               f"it in the {t['plan']['duty']:.0%} of days the plan is sheltered")
    out.append("     a trend rule that stops switching (a held position through a flat year) collects the shelter's fee "
               "and none of its benefit; the forward book prints the switch count, and that is the number to watch")
    out.append("     the failure budget is a distribution over windows. One real account lives one path, and this sheet "
               "cannot tell you which one you are on")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--payout", type=float, default=None, help="withdrawal to test; default is the plan's own safe amount")
    ap.add_argument("--record", default="long", choices=("long", "panel", "recent"))
    ap.add_argument("--conv", default="start", choices=("start", "end"))
    ap.add_argument("--shelter", default="IEF", choices=("IEF", "TLT", "GLD", "cash"))
    ap.add_argument("--asof", type=dt.date.fromisoformat, default=None)
    ap.add_argument("--years", type=int, default=YEARS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # Cash as the shelter is the plan round 64 measured the others against, and it is a legal thing to ask for. It is
    # the one shelter with no fund standing behind it, so it carries no fee and no price to refuse.
    shelter = sl.CASH if args.shelter == "cash" else args.shelter
    t = issue(args.capital, args.payout, args.record, args.conv, shelter, args.asof, args.years)
    if args.json:
        slim = {k: v for k, v in t.items() if k not in ("plan", "index", "static", "data", "spy")}
        slim["plan_p_fail"], slim["index_p_fail"], slim["months"] = (t["plan"]["p_fail"], t["index"]["p_fail"],
                                                                     t["plan"]["months"])
        print(json.dumps(slim, default=str, indent=2, sort_keys=True))
    else:
        print(render(t))
    return 0 if t["issued"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
