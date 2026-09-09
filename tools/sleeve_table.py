"""The same rule, on every fund the objective actually named — each one scored against the fund it would have been.

Run: .venv/bin/python tools/sleeve_table.py [--capital 100000] [--conv start] [--proxy] [--json]

Rounds 66 to 72 measured one construction on one sleeve, SPY, and published +$130 a month per $100,000 against plain DCA.
The objective says VOO and QQQ, and the funds differ in two ways that matter: what the file charges to hold them (3 bps
for VOO/VTI/ITOT, 9.45 for SPY, 20 for QQQ), and when their own price series begins — VOO in September 2010, which means
**a record long enough to hold 2008 cannot be built out of VOO prices at all.** Round 66's own warning, that a record's
length is a position taken by whoever wrote the tool, turns on the headline here.

So this file scores each sleeve three ways and lets the columns disagree with each other:

  `own`     that fund's longest record, from the later of this repository's floor and its own 201st session. The honest
            answer to "would this rule have helped a VOO account?", and it is also the answer with the least history in it.
  `panel`   the 2006-02 record, which contains 2008 and is still only 20 years.
  `recent`  the window every swept sleeve can be scored on — 2011-06-24, the first session after the *latest* warmup.
            Shortest, but the only window that treats every swept fund alike, and the one closest to a live account's life.

The insurance reading (round 67) says a hedge is worth what the thing it hedges costs when it fails, so the table prints
the index's own failure rate beside every premium. That column is the story: where the plain fund never failed a window,
the hedge is negative; where it failed, the hedge is positive; and which ticker it was barely matters.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import fund_fees                                                  # noqa: E402
import correction_table as ct                                # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402

# The broad index funds the objective could plausibly have meant, in the one sense that matters to a reader deciding what to
# hold: a single fund, bought and left alone. Round 102 swept three more — IWM, EFA, EEM — because the reason this file had left
# them out (round 69's rule that a fee must be sourced, and no fee was) stopped being true in round 94, and the gate underneath
# went on repeating it: `correction_table.measure` refused them with "carries no posted expense ratio" while `fund_fees.py` was
# carrying exactly that. A refusal naming a missing thing that is present is worse than no refusal: it sends the next reader to
# the wrong shelf (r92). Sweeping them also put round 67's insurance law in front of a control it had never seen — see the
# counterexamples this file now prints.
SWEEP = ("SPY", "VOO", "VTI", "ITOT", "QQQ", "IWM", "EFA", "EEM")
#: Why the archive's other priced legs are not swept here. None of these reasons is a fee.
REFUSED = {"IEF": "it is the shelter, not a sleeve — scoring it would hedge a bond with itself",
           "TLT": "same asset class as the shelter, and a duration bet the objective did not ask about",
           "GLD": "not equity beta; the failure column would be comparing asset classes",
           "DBC": "commodities, and the dearest ratio in the table at 0.84%"}
SHELTER = "IEF"
YEARS = 10
P_MAX = 0.05


def data():
    from boring_alpha.data.csv_loader import load_csv_market_data
    return load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)


def warmup_day(legs: dict) -> dt.date:
    """The first session on which that sleeve's own 200-day average exists — and therefore the first session the rule
    could have been traded on. `carry` fills a missing mark by holding the previous month's decision, and at the start
    of a record there is no previous decision, so a record that opens before its own warmup is silently opened in the
    shelter: round 45's artefact, wearing a longer coat."""

    return sorted(legs)[sl.WARMUP]


def windows(legs: dict, common: dt.date) -> dict:
    w = warmup_day(legs)
    return {"own": max(ct.SINCE, w), "panel": max(ct.PANEL, w), "recent": max(common, w)}


def common_start(d: dict) -> dt.date:
    """The window every swept sleeve can be scored on, set by the youngest of them."""

    return max(warmup_day(sl.legs(d, s)) for s in SWEEP)


def rows(capital: float, conv: str, proxy: bool) -> list:
    d = data()
    common = common_start(d)
    out = []
    for s in SWEEP:
        legs = sl.legs(d, s)
        dts = sorted(legs)
        marks = {c: sl.month_signal(dts, legs, c) for c in ("start", "end")}
        for label, since in sorted(windows(legs, common).items()):
            r = ct.measure(d, legs, "MA200", SHELTER, since, marks, conv, capital, ct.PUBLISHED_PAYOUT, YEARS, P_MAX,
                           sleeve=s)
            r["window"] = label
            r["verdict"] = ("clears the bar" if r["delta"] >= ct.BAR
                            else f"does not clear the ${ct.BAR:.0f} bar" if r["delta"] > 0 else "neither arm could fund a dollar" if r["index"] <= 0.0
                            else "loses to the fund itself")
            out.append(r)
    if proxy:
        # The question the objective actually asks, which no honest VOO row can answer: what would the rule have paid on
        # the cheap S&P fund over a record that includes 2008? VOO did not exist, so the path is SPY's and the fee is
        # VOO's. It is a proxy and it is labelled one on every line it appears on.
        legs = sl.legs(d, "SPY")
        dts = sorted(legs)
        marks = {c: sl.month_signal(dts, legs, c) for c in ("start", "end")}
        for label, since in (("own", ct.SINCE), ("panel", ct.PANEL), ("recent", common)):
            r = ct.measure(d, legs, "MA200", SHELTER, since, marks, conv, capital, ct.PUBLISHED_PAYOUT, YEARS, P_MAX,
                           sleeve="VOO")
            r["sleeve"] = "VOO*"
            r["window"] = label
            r["verdict"] = "PROXY: SPY's path, VOO's fee"
            out.append(r)
    return out


def report(rs: list, conv: str, common: dt.date) -> None:
    print(f"  sleeve table · MA200 sheltered in {SHELTER} · {conv}-of-month readings · scored against the same fund"
          f" unlevered · {len([r for r in rs if not r['sleeve'].endswith('*')])} real rows")
    print(f"  common window {common} = first session after the youngest swept sleeve's warmup\n")
    print(f"  {'fund':7}{'window':>8}{'record from':>14}{'wins':>6}{'fee':>8}{'plan $/mo':>11}{'fund alone':>12}"
          f"{'delta':>10}{'fund P(fail)':>14}{'duty':>7}  verdict")
    print("  " + "-" * 118)
    last = None
    for r in rs:
        if last and (last != r["sleeve"]):
            print()
        last = r["sleeve"]
        print(f"  {r['sleeve']:7}{r['window']:>8}{str(r['since']):>14}{r['n']:>6}{r['fee']:>8.2%}{r['safe']:>11.2f}"
              f"{r['index']:>12.2f}{r['delta']:>+10.2f}{r['p_fail_index']:>14.1%}{r['duty']:>7.1%}  {r['verdict']}")
    real = [r for r in rs if not r["sleeve"].endswith("*")]
    com = [r for r in real if r["window"] == "recent"]
    won = [r for r in com if r["delta"] > 0]
    print("\n  Read down the delta column with the P(fail) column beside it, not down the fund column.")
    print(f"  On the window every swept sleeve can stand ({len(com)} sleeves), "
          + (f"{len(won)} of them pay a premium: " + ", ".join(f"{r['sleeve']} {r['delta']:+.2f}" for r in won)
             if won else "not one sleeve pays: the shelter costs money on every fund when the record has no failure in it")
          + ".")
    broken = [r for r in real if (r["p_fail_index"] > 0) != (r["delta"] > 0)]
    degenerate = [r for r in broken if r["index"] <= 0.0 and r["safe"] <= 0.0]
    material = [r for r in broken if r not in degenerate]
    # "A record that contains a failure decade" has to mean the record, not the label on the row: VOO's `own` window is the
    # 2011-on window wearing an `own` name, because the fund started in 2010, and counting it as a failure decade would be
    # the tool's own version of the mistake the proxy row exists to avoid.
    deep = [r for r in real if r["window"] in ("own", "panel") and r["since"] <= dt.date(2007, 1, 1)]
    if material:
        print(f"\n  Round 67's insurance law — a hedge is worth what its fund costs when it fails — is not an equivalence.")
        print(f"  It breaks on {len(material)} row(s), and not by rounding:")
        for r in sorted(material, key=lambda r: r["delta"]):
            print(f"    {r['sleeve']:<5} {r['window']:>6}  fund failed {r['p_fail_index']:>5.1%} of windows"
                  f"  delta {r['delta']:>+9.2f}  out of equities {r['duty']:.1%} of days")
        if degenerate:
            print(f"  (and {len(degenerate)} row(s) where neither arm could fund a dollar at all — a tie at zero is not"
                  f" a premium)")
        # The law's own domain is the rows where the fund actually failed; the tie-at-zero rows carry no information about a
        # premium. QQQ is out in both directions — its fund never failed, so it is not a counterexample but the law working:
        # nothing to insure, nothing paid.
        scored = [r for r in deep if r["p_fail_index"] > 0 and r["index"] > 0.0]
        paid = [r for r in scored if r["delta"] > 0]
        lost = [r for r in scored if r["delta"] <= 0]
        gap = min((r["duty"] for r in lost), default=1.0) - max((r["duty"] for r in paid), default=0.0)
        if paid and lost and gap > 0:
            print(f"  What separates them is the duty column, not the failure column. On the {len(scored)} rows whose record")
            print(f"  contains the failure decade and whose fund really did fail, every shelter that paid was out of equities")
            print(f"  for at most {max(r['duty'] for r in paid):.1%} of days and every shelter that lost for at least"
                  f" {min(r['duty'] for r in lost):.1%} — {gap:.1%} of separation.")
            iwm = [r for r in deep if r["sleeve"] == "IWM"]
            if iwm:
                worst = min(iwm, key=lambda r: r["delta"])
                print(f"  Read it as a warning about small caps: IWM's fund failed {worst['p_fail_index']:.1%} of its"
                      f" windows on the {worst['window']} record — the hedge still cost ${abs(worst['delta']):,.0f} a month,"
                      f" with the book out of equities {worst['duty']:.1%} of the time.")
        else:
            print("  No duty separation in this sample: the sleeves that paid and the sleeves that lost overlap on the")
            print("  duty column, so the failure decade alone does not sort them and the rows have to be read one by one.")
    print("\n  The premium is not a ticker's property. It is a property of whether the record contains a decade in which")
    print("  plain DCA ran out of money, and of how often the shelter was called out while trying to dodge it. VOO's own")
    print("  record cannot answer that question: the fund started in 2010, so ask it about 2002-2011 and you are asking")
    print(f"  about SPY's path at {fund_fees.fee_for('VOO') * 10_000:.0f} bps — the PROXY row, the only defensible way to"
          " price the cheap S&P fund over a record")
    print("  that contains the failure the hedge is for.")
    print("\n  not swept here: " + "; ".join(f"{k} — {v}" for k, v in REFUSED.items()))
    print("  None of those reasons is a fee. Every leg the archive carries, twelve of them, has a sourced ratio in")
    print("  `fund_fees.py` since round 94; what is scarce here is a record that contains a failure, and an asset class.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--conv", default="start", choices=("start", "end"))
    ap.add_argument("--proxy", action="store_true", help="add the VOO-priced-on-SPY's-path rows")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rs = rows(args.capital, args.conv, args.proxy)
    if args.json:
        print(json.dumps(rs, default=str, indent=2, sort_keys=True))
    else:
        report(rs, args.conv, common_start(data()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
