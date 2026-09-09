"""The vol-target rule sold as what it demonstrably is: an insurance policy on a drawdown, not an alpha.

    .venv/bin/python tools/insurance_pricing.py
    .venv/bin/python tools/insurance_pricing.py --capital 20000 --crash 0.05
    .venv/bin/python -m pytest tests/test_insurance_pricing.py -q

For most of this project's life the rule has been scored as a return strategy, and on that score it loses:
round 25 measured it at **−0.25%/yr** against plain 100% SPY under account-faithful costs and **−1.27%/yr** once
forbidden to borrow. Rounds 26 and 32 kept noting it "halves the drawdown" as though that were a consolation
prize attached to a failed investment case. It isn't. A product that loses money steadily and prevents a large
loss is not a bad investment strategy — **it is an insurance policy**, and insurance policies are evaluated on a
completely different basis: what does the premium cost, what does the claim pay, and would a cheaper contract
buy the same coverage. Nobody in 36 rounds had asked that question, and it is the only framing under which the
rule can be defended at all.

This file re-scores the rule as a contract. The anatomy decomposition in `unlevered_timing.py` already splits
the excess into crash months, rally months and flat months that sum to the headline exactly, which is precisely
premium and claim in accounting form:

| bucket | months | contribution | role in the contract |
|---|---:|---:|---|
| crash (< −5%) | 37 | **+2.80%/yr** | the claim paid |
| rally (> +5%) | 61 | **−3.33%/yr** | the premium, in bad months |
| flat | 306 | **+0.28%/yr** | the premium, in ordinary months |
| **total** | 404 | **−0.25%/yr** | net cost of the cover |

## The finding, and it is not the one I expected

**The rule pays out, and it pays out almost everything it takes in.** The claim is worth +2.80%/yr averaged
across the whole record; the premium is −3.33% in rallies plus +0.28% in flat months, totalling −3.05%. The
claim recovers **91.9 cents of every premium dollar**, which is the ratio of a functioning insurance product —
a loading of roughly 8% — and not the ratio of a broken strategy. The residual −0.25%/yr is the net drain.

That reframing is the round's actual contribution. Scored as a return strategy the rule is a failure at
−0.25%/yr. Scored as a contract it is a **cheap policy that works**: it collects 3.05, returns 2.81, and cuts
peak-to-trough from −51.8% to −29.4%. The question stops being "why doesn't this make money" and becomes
"is 8% loading a fair price for 22 points of drawdown," which has an answer and it isn't determined by the
archive. Over the 34 years that drain is $4.10 a month on
$20,000, against a drawdown reduction from −51.8% to −29.4%.

Two things make that worse than it sounds. First, the premium is **61 months against 37 claim months** — the
policyholder pays in six out of ten notable months and collects in four, and the paying months are the pleasant
ones, which is why it survives being felt. Second, the *opportunity* cost dwarfs the cash cost: the rule's own
turnover bill is 0.032%/yr, trivial, so nearly all of the −0.25% is the cost of being under-invested at the
moment markets recover, and that is not a fee a broker charges, it is the contract's own structure.

## The question this cannot answer, and it is the one that matters

Whether −0.25%/yr is a fair price for avoiding 22 points of drawdown is not an arithmetic question. It depends
entirely on whether the account can survive the unhedged path — and a $20,000 account that falls 52% and rebuilds
is a different decision from one where that fall means abandoning the plan. That is a fact about the owner, not
the archive, and round 12 has been waiting on exactly that answer for 24 rounds. What this file can do is state
the price honestly, so the question can be asked with a number in it: **the cover costs about $49 a year on
$20,000, and buys a smaller hole in the four years out of thirty-four when one appears.**

## What this file does not do

  * **It does not simulate buying a put.** That is the obvious alternative contract and needs an options price
    series this archive does not contain, so no comparison is offered — the "cheaper contract" question is left
    open rather than answered with a guess.
  * **The crash threshold is a definition, not a measurement.** `--crash` re-buckets the same record; a policy
    that is expensive at 5% may be cheap at 3% and the answer should not depend on that dial, which is why the
    sweep is printed.
  * **Still no tax, still survivorship-biased.** See `action_ledger.py`.

"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import unlevered_timing as ut                      # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

TURNOVER_COST = float(wc.TURNOVER_COST)


def price(data, crash: float, capital: float) -> dict:
    """The rule, priced as a contract: premium paid, claim received, net cost, and the cover bought."""

    r = ut.run(data, crash=crash)
    held = ut.run(data, static=r["mean_w"], crash=crash)
    a = r["anatomy"]
    w = [x for x in r["weights"] if x is not None]
    turn = sum(abs(w[i] - w[i - 1]) for i in range(1, len(w))) / (len(w) / 12.0)
    n_flat = a["months"] - a["n_crash"] - a["n_rally"]
    return {
        "claim": a["crash"], "premium_rally": a["rally"], "premium_flat": a["flat"],
        "n_claim": a["n_crash"], "n_premium": a["n_rally"], "n_flat": n_flat,
        "months": a["months"], "net": a["total"], "bill": turn * TURNOVER_COST * 100.0,
        "turnover": turn, "dd_rule": r["dd"], "dd_held": held["dd"],
        "worst_rule": r["worst"], "worst_held": held["worst"],
        "net_mo": a["total"] / 1200.0 * capital, "claim_mo": a["crash"] / 1200.0 * capital,
        "premium_mo": (a["rally"] + a["flat"]) / 1200.0 * capital,
        "crash": crash, "capital": capital, "mean_w": r["mean_w"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="price the vol-target rule as an insurance contract")
    ap.add_argument("--capital", type=float, default=20_000.0)
    ap.add_argument("--crash", type=float, default=ut.CRASH, help="the month that counts as a claim")
    ap.add_argument("--sweep", action="store_true", help="re-bucket at several thresholds")
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    if args.sweep:
        print(f"the same contract, defined at several claim thresholds · ${args.capital:,.0f}\n")
        print(f"  {'crash >':>8} {'claims':>7} {'claim/yr':>9} {'premium/yr':>11} {'net/yr':>8} "
              f"{'$/mo':>8} {'drawdown':>9}")
        for c in (0.03, 0.04, 0.05, 0.06, 0.08):
            p = price(data, c, args.capital)
            print(f"  {c:>7.0%} {p['n_claim']:>7} {p['claim']:>+8.2f}% {p['premium_rally']+p['premium_flat']:>+10.2f}% "
                  f"{p['net']:>+7.2f}% {p['net_mo']:>+7.2f} {p['dd_rule']:>8.1%}")
        print("\n  If the verdict flipped across this row the answer would be a definition and not a finding.\n")

    p = price(data, args.crash, args.capital)
    print(f"the rule as an insurance policy · {p['months']} months · claims at > {p['crash']:.0%} a month\n")
    print(f"  {'the claim, paid in':>22} {p['n_claim']:>4} months   {p['claim']:>+7.2f}%/yr   "
          f"${p['claim_mo']:>+6.2f}/mo")
    print(f"  {'the premium, in rallies':>22} {p['n_premium']:>4} months   {p['premium_rally']:>+7.2f}%/yr")
    print(f"  {'the premium, in flat':>22} {p['n_flat']:>4} months   {p['premium_flat']:>+7.2f}%/yr   "
          f"${p['premium_mo']:>+6.2f}/mo")
    print(f"  {'':22} {'':>4}        {'':>7}")
    print(f"  {'NET COST OF COVER':>22} {'':>4}        {p['net']:>+7.2f}%/yr   ${p['net_mo']:>+6.2f}/mo"
          f"   (${abs(p['net'])/100*args.capital:,.0f}/yr on the account)")

    print(f"\n  what the cover buys")
    print(f"    max drawdown   {p['dd_rule']:.1%} held, against {p['dd_held']:.1%} unhedged   "
          f"({abs(p['dd_rule']-p['dd_held'])*100:.0f} points of hole)")
    print(f"    worst month    {p['worst_rule']:+.1%} held, against {p['worst_held']:+.1%} unhedged")
    print(f"    mean exposure  {p['mean_w']:.3f} of the account, against 1.000 unhedged")
    print(f"\n    the broker's bill for the policy is only {p['bill']:.3f}%/yr "
          f"({p['turnover']:.2f}x turnover),")
    print(f"    so the rest of the {p['net']:+.2f}% is not a fee — it is the cost of being under-invested")
    print(f"    exactly when markets recover, which is the structure of the contract and cannot be negotiated.")
    print(f"\n  Premium paid in {p['n_premium']} months, claim received in {p['n_claim']}. The paying months are")
    print(f"  the pleasant ones, which is why a policy that loses money every year can still be held by someone")
    print(f"  who never does the arithmetic. Whether {abs(p['net']):.2f}% a year is a fair price for")
    print(f"  {abs(p['dd_rule']-p['dd_held'])*100:.0f} points of drawdown is a question about the account, not the archive.")
    print("\n  No options price series exists in this archive, so no alternative contract is priced here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
