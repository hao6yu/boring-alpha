"""What allocation buys the floor that money and buckets cannot — and what it costs in the good decades.

Round 54. Round 52 proved an all-equity withdrawal plan on SPY cannot be made certain at any account size: in the
worst window the index itself finished below where it started. Round 53 proved a cash *bucket* does not buy the
floor either, because a bucket only moves the timing of the sale. Both rounds ended pointing at the same candidate:
a second **asset**, held all the time, rebalanced. This round prices that, because "only a different asset buys a
floor" is still an assertion until somebody writes down the weight and the invoice.

The instrument is a constant mix: fraction `w` in T-bills via SGOV, the rest in the equity sleeve, rebalanced every
month, both legs charged their expense, the cheque taken monthly. Two failure conditions are reported separately
because they are different promises:

  * **liquidation** — the balance hit zero and the cheque stopped. This is the condition round 50's guarantee
    measures, and the one an income plan actually cares about.
  * **erasure** — the plan finished below where it started. Strictly harder, and the one a "principal intact"
    spreadsheet demands.

Run:  python tools/allocation_floor.py [--capital 100000] [--years 20] [--sleeve SPY] [--stride 3]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import bucket_plan as bp                                                 # noqa: E402
import cash_yield_gap as cy                                              # noqa: E402
import income_accounting as ia                                           # noqa: E402
import withdrawal_capacity as wc                                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data            # noqa: E402

WEIGHTS = (0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.65, 0.80, 1.00)
CASH_ER = cy.SGOV_ER


def simulate_mix(eq_path, cash_path, c0: float, target: float, weight: float, expense: float,
                 inflate: float = 0.0) -> dict:
    """One window, one constant mix. Withdrawals at month end, then the mix is reset — selling into strength, which
    is the whole mechanism: the rebalancing is what converts a second asset into a floor.

    `inflate` raises the nominal cheque every twelve months. It is not a refinement: at the capacity engine's 2.5%
    it is worth 18% of the headline figure, and the two conventions are different promises about different things.
    """

    er = expense / 12.0
    cr = -CASH_ER / 12.0
    equity, cash = c0 * (1.0 - weight), c0 * weight
    trough = 1.0
    for i, (r, f) in enumerate(zip(eq_path, cash_path)):
        equity *= (1.0 + r - er)
        cash *= (1.0 + f + cr)
        total = equity + cash
        if total <= 0.0:
            return {"terminal": total, "liquidated": True, "erased": True, "trough": 0.0}
        cash -= target * (1.0 + inflate) ** (i // 12)
        if cash < 0.0:
            equity += cash
            cash = 0.0
            if equity <= 0.0:
                return {"terminal": 0.0, "liquidated": True, "erased": True, "trough": 0.0}
        total = equity + cash
        trough = min(trough, total / c0)
        want = total * weight
        if want > total:
            want = total
        move = want - cash
        if move > equity:
            move = equity
        equity -= move
        cash += move
    total = equity + cash
    return {"terminal": total, "liquidated": False, "erased": total < c0 - 1e-9, "trough": trough}


def evaluate(data, symbol: str, c0: float, target: float, years: int, weight: float,
             inflate: float = 0.0) -> dict:
    """Both failure probabilities and the terminal distribution, over every window."""

    expense = wc.EXPENSE.get(symbol, 0.0)
    out = [simulate_mix(e, c, c0, target, weight, expense, inflate)
           for e, c in bp.paired_windows(data, symbol, years)]
    n = len(out)
    if not n:
        return {"n": 0, "p_liq": None, "p_erase": None}
    term = sorted(o["terminal"] / c0 for o in out)
    return {"n": n, "p_liq": sum(1 for o in out if o["liquidated"]) / n,
            "p_erase": sum(1 for o in out if o["erased"]) / n,
            "median_mult": statistics.median(term), "min_mult": term[0], "max_mult": term[-1],
            "worst_trough": min(o["trough"] for o in out)}


def safe_income(data, symbol: str, c0: float, years: int, weight: float, budget: float = 0.0,
                inflate: float = 0.0) -> float:
    """The largest monthly cheque that keeps the plan unliquidated in at least (1 - budget) of the windows.

    Legal to bisect: a smaller cheque can only ever leave more money in the account, so the set of feasible targets
    is an interval. Budget 0 is the guarantee — the cheque that survives the worst start in the record.
    """

    lo, hi = 0.0, c0
    if evaluate(data, symbol, c0, hi, years, weight, inflate)["p_liq"] <= budget:
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if evaluate(data, symbol, c0, mid, years, weight, inflate)["p_liq"] > budget:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=20)
    ap.add_argument("--target", type=float, default=500.0)
    ap.add_argument("--sleeve", default="SPY")
    ap.add_argument("--stride", type=int, default=3)
    ap.add_argument("--inflate", type=float, default=0.025)
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    print(f"the floor, priced by allocation · {args.sleeve} + SGOV at the archive's own bill curve"
          f" less {CASH_ER:.2%}, monthly rebalancing\n")
    print(f"  one plan: ${args.target:,.0f}/mo on ${args.capital:,.0f} over {args.years} years")
    print(f"  {'bills':>6} {'windows':>8} {'P(liquidation)':>15} {'P(erasure)':>12} {'median x':>9}"
          f" {'worst x':>8} {'worst trough':>13}")
    print("  " + "-" * 70)
    rows = {}
    for w in WEIGHTS:
        r = rows[w] = evaluate(data, args.sleeve, args.capital, args.target, args.years, w)
        if not r["n"]:
            print(f"  {w:>5.0%} {'untested':>8}")
            continue
        print(f"  {w:>6.0%} {r['n']:>8} {r['p_liq']:>15.0%} {r['p_erase']:>12.0%} {r['median_mult']:>8.2f}x"
              f" {r['min_mult']:>7.2f}x {r['worst_trough']:>12.2f}x")
    print("  P(liquidation) is the promise an income plan needs: the cheque never stops. P(erasure) is the"
          " stricter\n  one a principal-preservation spreadsheet asks for.")

    print(f"\n  guaranteed monthly cheque per ${args.capital:,.0f} — the largest first-year amount that never gets"
          f" the plan\n  liquidated in any of the windows. Two promises, two numbers, same capital.")
    print(f"  {'bills':>6} {'level cheque':>14} {'indexed 2.5%':>14} {'indexed vs none':>16} {'median terminal':>16}")
    print("  " + "-" * 66)
    lev0 = safe_income(data, args.sleeve, args.capital, args.years, 0.0)
    idx0 = safe_income(data, args.sleeve, args.capital, args.years, 0.0, 0.0, args.inflate)
    best_w, best_v = 0.0, idx0
    for w in WEIGHTS:
        lev = safe_income(data, args.sleeve, args.capital, args.years, w)
        idx = safe_income(data, args.sleeve, args.capital, args.years, w, 0.0, args.inflate)
        if idx > best_v:
            best_w, best_v = w, idx
        print(f"  {w:>6.0%} {lev:>13,.2f} {idx:>13,.2f} {idx - idx0:>+15,.2f}"
              f" {rows[w]['median_mult']:>15.2f}x")
    print(f"  the maximum indexed cheque sits at {best_w:.0%} bills: ${best_v:,.2f}/mo,"
          f" {'+' if best_v >= idx0 else ''}{best_v - idx0:,.2f} against no bills at all.")
    print(f"  Level buys ${lev0:,.2f} and indexed buys ${idx0:,.2f} on the same account: the convention is worth"
          f" {lev0 / idx0 - 1.0:.0%} of\n  the headline. A guarantee quoted without saying which one is holding"
          " two numbers and\n  showing you one.")

    g = ia.guarantee(args.sleeve, 1.00, args.capital, args.years, data, args.stride)
    print(f"\n  cross-check against round 50's capacity engine, both on the indexed promise: engine"
          f" ${g['cheque']:,.2f}/mo at stride\n  {args.stride}, this file ${idx0:,.2f}/mo — a"
          f" {abs(idx0 - g['cheque']) / g['cheque']:.1%} disagreement between two implementations that share no"
          f" code. The engine indexes at the\n  same {args.inflate:.1%} by construction (`wc.capacity`"
          f" `inflate=0.025`); this file did not, on its first run,\n  and the two looked 18% apart. Match the"
          " convention before you debug the code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
