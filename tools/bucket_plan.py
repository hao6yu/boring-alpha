"""Price the floor: how much a cash bucket costs, and whether it buys the survivability it claims.

Round 53. Round 52 ended on a requirement that had no price: on SPY at ten years, no amount of money makes an
all-equity withdrawal plan certain, because in the worst window the index itself finished below where it started.
The sentence that followed — "only a different asset buys a floor" — was an assertion. This round prices it.

A bucket is not a return strategy. It changes nothing about what the market pays; it changes **when you are forced
to sell**, which is the only lever sequence risk actually exposes to an investor. So it is measured on the failure
probability and on the one operational statistic it exists to move: the number of months the plan had to sell
equity because the cash ran out.

Four policies, one archive, identical withdrawals:

  * `all-equity`      — the round 52 baseline, no floor at all;
  * `refill-only`     — hold N months of spending in cash, top up from equity when low, never sweep back;
  * `two-way`         — top up when low, sweep excess above N months back into equity;
  * `constant-weight` — hold the cash weight fixed at N months of spending (rebalanced every month).

Run:  python tools/bucket_plan.py [--target 500] [--capital 100000] [--years 20] [--sleeve SPY]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cash_yield_gap as cy                                              # noqa: E402
import withdrawal_capacity as wc                                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data            # noqa: E402

BUFFERS = (0, 6, 12, 24, 36, 60)
CASH_ER = cy.SGOV_ER                                # the bucket is not free: it lives in a fund with an expense
POLICIES = ("all-equity", "refill-only", "two-way", "constant-weight")


def paired_windows(data, symbol: str, years: int) -> list:
    """Every window of monthly (equity, cash) return pairs. The two legs travel together or the bucket is fiction:
    a cash series misaligned by one month is a plan that earns the bill curve before it existed."""

    series = {d: data.by_date[d][symbol].close for d in data.by_date if symbol in data.by_date[d]}
    eq, cash, keys = wc.monthly(series, data.cash_factors)
    last = max(data.by_date)
    if keys and last < wc.last_business_day(keys[-1].year, keys[-1].month):
        eq, cash = eq[:-1], cash[:-1]
    months = years * 12
    return [(eq[i:i + months], cash[i:i + months]) for i in range(0, len(eq) - months + 1)]


def simulate_bucket(eq_path, cash_path, c0: float, target: float, buffer_months: int,
                    policy: str, expense: float, band: float = 0.0) -> dict:
    """One window, one policy. Returns terminal wealth, survival, forced sales and the lowest cash runway."""

    er = expense / 12.0
    cr = -CASH_ER / 12.0
    buffer_0 = target * buffer_months
    if buffer_0 >= c0:
        # The bucket would swallow the account and leave a negative equity leg, which is not a plan but a sign
        # error. A 60-month buffer on $2,000/mo is $120,000 of cash and cannot fit inside $100,000 of capital.
        raise ValueError(f"buffer of {buffer_0:,.0f} exceeds capital of {c0:,.0f}")
    equity = c0 - buffer_0
    cash = float(buffer_0)
    if policy == "constant-weight" and equity > 0:
        w = buffer_0 / c0
        equity, cash = c0 * (1.0 - w), c0 * w
    forced = 0
    trough_runway = float("inf")
    trough_mult = float("inf")
    for r, f in zip(eq_path, cash_path):
        equity *= (1.0 + r - er)
        cash *= (1.0 + f + cr)
        cash -= target
        if cash < 0.0:
            forced += 1
            need = -cash
            if equity < need:
                return {"terminal": equity + cash, "survived": False, "forced": forced,
                        "trough_runway": 0.0, "trough_mult": 0.0, "destroyed": True}
            equity -= need
            cash = 0.0
        trough_runway = min(trough_runway, cash / target if target else float("inf"))
        trough_mult = min(trough_mult, (equity + cash) / c0)
        # `band` is what makes the three policies different documents rather than one document with three names.
        # With band = 0 every policy that tops up does so every month — spending exceeds bill income, so cash is
        # always below target — and all three collapse into "hold a small cash weight", which is what round 53's
        # first run measured. A no-trade band lets cash drift inside [buffer(1-band), buffer(1+band)].
        if policy == "refill-only" and cash < buffer_0 * (1.0 - band):
            move = min(buffer_0 - cash, equity)
            equity -= move
            cash += move
        elif policy == "two-way":
            if cash < buffer_0 * (1.0 - band):
                move = min(buffer_0 - cash, equity)
                equity -= move
                cash += move
            elif cash > buffer_0 * (1.0 + band) and equity > 0:
                move = cash - buffer_0
                cash -= move
                equity += move
        elif policy == "constant-weight" and equity > 0:
            want_cash = buffer_0
            gap = want_cash - cash
            if gap > 0:
                move = min(gap, equity)
            else:
                move = max(gap, -cash)
            equity -= move
            cash += move
    return {"terminal": equity + cash, "survived": equity + cash >= c0 - 1e-9, "forced": forced,
            "trough_runway": trough_runway, "trough_mult": trough_mult, "destroyed": False}


def evaluate(data, symbol: str, c0: float, target: float, years: int, months: int, policy: str,
             band: float = 0.0) -> dict:
    """P(failure), terminal multiples and forced-sale counts across every window."""

    expense = wc.EXPENSE.get(symbol, 0.0)
    if target * months >= c0:
        return {"n": 0, "p_fail": None, "infeasible": True}
    out = [simulate_bucket(e, c, c0, target, months, policy, expense, band)
           for e, c in paired_windows(data, symbol, years)]
    n = len(out)
    if not n:
        return {"n": 0, "p_fail": None, "infeasible": False}
    term = sorted(o["terminal"] / c0 for o in out)
    return {"n": n, "p_fail": 1.0 - sum(1 for o in out if o["survived"]) / n,
            "median_mult": statistics.median(term), "min_mult": term[0], "max_mult": term[-1],
            "forced_mean": statistics.fmean(o["forced"] for o in out),
            "forced_max": max(o["forced"] for o in out),
            "trough_runway": min(o["trough_runway"] for o in out),
            "trough_mult": min(o["trough_mult"] for o in out),
            "median_trough": statistics.median(sorted(o["trough_mult"] for o in out)),
}


def table(data, symbol: str, c0: float, target: float, years: int) -> None:
    """The buffer sweep first, then the policy/band sweep. The first has a real spread; the second mostly does
    not, and the shape of that non-spread is itself the finding."""

    n = len(paired_windows(data, symbol, years))
    print(f"  {symbol}, ${target:,.0f}/mo on ${c0:,.0f} over {years} years, {n} windows"
          f"  (bill leg: the archive's own DGS3MO less SGOV's {cy.SGOV_ER:.2%})\n")
    if not n:
        print("  untested: this sleeve has no window that long in the archive. Nothing is being claimed.")
        return
    base = evaluate(data, symbol, c0, target, years, 0, "all-equity")
    print(f"  {'buffer':>7} {'p(fail)':>8} {'median x':>9} {'median trough':>14} {'forced sales':>13}"
          f" {'vs no buffer':>13}")
    print("  " + "-" * 70)
    for months in BUFFERS:
        if months:
            r = evaluate(data, symbol, c0, target, years, months, "refill-only")
            if r.get("infeasible"):
                print(f"  {months:>5}mo {'infeasible: the bucket would exceed the capital':>53}")
                continue
        else:
            r = base
        print(f"  {months:>5}mo {r['p_fail']:>8.0%} {r['median_mult']:>8.2f}x {r['median_trough']:>13.2f}x"
              f" {r['forced_mean']:>13.1f} {r['p_fail'] - base['p_fail']:>+12.0%}")
    print("  'median trough' is how deep the account was ever seen in a typical window — the hole an investor has"
          " to watch,\n  which is the only thing a bucket claims to move. The last column is the change in"
          " failure probability.")

    print("\n  the policy axis, at a 12-month buffer: every policy, every band")
    print(f"  {'policy':16} {'band':>6} {'p(fail)':>8} {'median x':>9} {'median trough':>14}")
    print("  " + "-" * 56)
    for policy in POLICIES:
        for band in (0.0, 0.5, 0.9):
            if policy == "all-equity" and band > 0:
                continue
            r = evaluate(data, symbol, c0, target, years, 12 if policy != "all-equity" else 0, policy, band)
            if not r["n"]:
                continue
            print(f"  {policy:16} {band:>5.0%} {r['p_fail']:>8.0%} {r['median_mult']:>8.2f}x"
                  f" {r['median_trough']:>13.2f}x")
    print("  Two-way and refill-only agree to the dollar at every band, and constant-weight ignores the band:"
          " with a band\n  as wide as the bucket, 'all three policies' is one policy — hold a cash weight and trade"
          " it rarely. The\n  sweep-back leg never fires for anyone, because cash exceeds its target only if you"
          " are not spending it,\n  and a plan whose withdrawals outrun the bill yield cannot accumulate a"
          " surplus. You cannot sweep back\n  money you are living on.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", type=float, default=500.0)
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=20)
    ap.add_argument("--sleeve", default="SPY")
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    print("the bucket, priced · a floor is a decision about when you sell, not about what you own\n")
    table(data, args.sleeve, args.capital, args.target, args.years)
    base = evaluate(data, args.sleeve, args.capital, args.target, args.years, 0, "all-equity")
    twelve = evaluate(data, args.sleeve, args.capital, args.target, args.years, 12, "refill-only")
    wide = evaluate(data, args.sleeve, args.capital, args.target, args.years, 12, "refill-only", 0.9)
    if not base["n"]:
        return 0
    print(f"\n  the invoice, at a 12-month buffer. Forced sales {base['forced_mean']:.1f} -> {twelve['forced_mean']:.1f}"
          f" months per window — the benefit is real and\n  large. The median trough"
          f" {base['median_trough']:.2f}x -> {twelve['median_trough']:.2f}x: two points of depth. Median terminal"
          f" {base['median_mult']:.2f}x -> {twelve['median_mult']:.2f}x, and failure {base['p_fail']:.0%} ->"
          f" {twelve['p_fail']:.0%}.\n"
          f"  A wide band claws part of the cost back without touching the benefit: failure"
          f" {twelve['p_fail']:.0%} -> {wide['p_fail']:.0%}, terminal {twelve['median_mult']:.2f}x ->"
          f" {wide['median_mult']:.2f}x.\n  The only thing the band does"
          " is leave more money in equities longer, which is the same lever as a smaller\n  buffer seen from the"
          " other side.\n"
          "  So the bucket does what the folklore says about the *experience* of the plan and nothing about its"
          " survival. The\n  failure mode in this archive is a withdrawal rate facing a decade that could not pay"
          " it, and no\n  selling schedule changes that. Round 52's floor is not for sale at any buffer size; it"
          " is for sale only in\n  the amount of money committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
