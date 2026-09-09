"""The de-risking signal with its borrowing removed, and its P&L taken apart by month type.

    .venv/bin/python tools/unlevered_timing.py
    .venv/bin/python tools/unlevered_timing.py --floor-crash 0.05
    .venv/bin/python -m pytest tests/test_unlevered_timing.py -q

Round 25 located the failure precisely: the rule's whole excess over the index was the rate it was credited with
on its borrowings, and at the posted desk rate the excess is −0.00%/yr. That leaves one question worth spending
a round on, and it is not "can this rule beat the index" — twenty-five rounds have answered that. It is whether
there is anything inside the rule worth keeping, which requires three separations the archive can make and a
live account cannot:

  * **debt vs signal** — run the same signal with borrowing forbidden (`cap`), so nothing about the result can
    be financed by a loan rate;
  * **size vs timing** — compare the capped rule against a *static* position of the same average weight, because
    a rule that holds 95% of the fund on average is not owed a comparison with 100%; anything it earns over a
    static 95% is timing, and anything it earns over 100% would have to be leverage or luck;
  * **crashes vs rallies** — decompose the excess into the months the fund fell hard, the months it rose hard,
    and everything in between. This is the only part of the case that needs no statistical power: it is an
    accounting identity over the record, and the two tallies are the entire argument for the rule.

Accounting is the account-faithful pair from round 25: idle cash at the audited brokerage sweep (0.02%), any
borrowing at the posted desk rate (4.90%). Under those assumptions the comparison is against money, not against
a nicer counterparty.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import book_power as bp                            # noqa: E402  the weight path and the net-return builder
import income_frontier as ifr                      # noqa: E402  MENU_PUBLIC, series_for
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

SWEEP = bp.SWEEP
SYMBOL = "SPY"
EXPENSE = float(wc.EXPENSE[SYMBOL])
CAPITAL = 20_000.0
CRASH = 0.05


def drawdown(returns: list) -> float:
    """Worst peak-to-trough of the compounding path, no deposits: what a holder of this rule saw."""

    value = peak = 1.0
    worst = 0.0
    for r in returns:
        value *= (1.0 + r)
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def anatomy(strat: list, bench: list, keys: list, crash: float) -> dict:
    """Split the total excess into the three month types, so the rule's case can be read as two tallies.

    Contributions are to the *mean monthly* difference, so they sum to the headline exactly: the sum over each
    subset divided by the whole record length. Anything that failed to add up would mean a month was counted
    twice, which is why the caller checks.
    """

    d = [a - b for a, b in zip(strat, bench)]
    out = {"crash": 0.0, "rally": 0.0, "flat": 0.0, "n_crash": 0, "n_rally": 0}
    for i, b in enumerate(bench):
        if b < -crash:
            out["crash"] += d[i]
            out["n_crash"] += 1
        elif b > crash:
            out["rally"] += d[i]
            out["n_rally"] += 1
        else:
            out["flat"] += d[i]
    n = len(d)
    for k in ("crash", "rally", "flat"):
        out[k] = out[k] / n * 1200.0
    out["total"] = sum(d) / n * 1200.0
    out["months"] = n
    out["keys"] = keys
    return out


def run(data, cap: float | None = None, static: float | None = None, crash: float = CRASH) -> dict:
    strat, bench, keys, weights = bp.net_strategy_returns(data, SYMBOL, 3.0, EXPENSE, sweep=SWEEP,
                                                          borrow="posted", cap=cap, static=static)
    total = sum(a - b for a, b in zip(strat, bench)) / len(strat)
    return {"strat": strat, "bench": bench, "keys": keys, "weights": weights,
            "mean_w": statistics.fmean(weights), "total": total, "mo": total * CAPITAL,
            "dd": drawdown(strat), "dd_bench": drawdown(bench), "worst": min(strat),
            "anatomy": anatomy(strat, bench, keys, crash)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--crash", type=float, default=CRASH, help="month type threshold, as a fraction")
    ap.add_argument("--capital", type=float, default=CAPITAL)
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    print("the de-risking signal, unlevered · idle cash at "
          f"{SWEEP:.2%}, any borrow at the posted {ifr.MENU_PUBLIC:.2%}, capital ${args.capital:,.0f}\n")

    book = run(data, crash=args.crash)
    capped = run(data, cap=1.0, crash=args.crash)
    ctrl = run(data, static=capped["mean_w"], crash=args.crash)
    CRASH_ = args.crash
    print(f"  {'variant':34} {'mean w':>7} {'excess vs 100%':>15} {'$/mo':>8} {'vs static ctrl':>15} "
          f"{'max DD':>8} {'worst mo':>9}")
    rows = [("100% SPY, do nothing", run(data, static=1.0)),
            ("the book's rule, cap 1.30", book),
            (f"same signal, capped at 1.00", capped),
            (f"static at {capped['mean_w']:.3f} (the control)", ctrl)]
    for label, r in rows:
        vs_index = r["total"] * 1200.0
        vs_ctrl = (r["total"] - ctrl["total"]) * 1200.0
        print(f"  {label:34} {r['mean_w']:>7.3f} {vs_index:>+14.2f}% {r['mo']*12/12:>+8,.2f} "
              f"{vs_ctrl if label != rows[3][0] else 0.0:>+14.2f}% {r['dd']:>7.1%} {r['worst']:>9.1%}")

    a = capped["anatomy"]
    print(f"\n  the capped rule's excess taken apart ({a['months']} months, "
          f"{a['n_crash']} falls worse than −{CRASH:.0%}, {a['n_rally']} rises better than +{CRASH:.0%}):")
    for key, label in (("crash", "what it saved in the crashes"), ("rally", "what it gave up in the rallies"),
                       ("flat", "what it did in the other months")):
        print(f"    {label:34} {a[key]:>+8.2f}%/yr   ${a[key]/1200*args.capital:>+8,.2f}/mo")
    summed = a["crash"] + a["rally"] + a["flat"]
    print(f"    {''.ljust(34)} {''.rjust(9)}")
    print(f"    {'total (must equal the table above)':34} {summed:>+8.2f}%/yr   "
          f"${a['total']/1200*args.capital:>+8,.2f}/mo")
    if abs(summed - a["total"]) > 0.005:
        print("    ** the decomposition does not add up; a month is counted twice or dropped")
    print(f"    bench max drawdown over the same window: {capped['dd_bench']:.1%}, capped rule {a['crash']*0+drawdown(capped['strat']):.1%}")

    print()
    if a["crash"] > 0 and a["crash"] < abs(a["rally"]):
        print("  the two tallies, read together: the rule earns its keep in the "
              f"{a['n_crash']} months that hurt most and\n  loses more than that in the {a['n_rally']} months "
              "that went well. That is a drawdown device with a\n  negative premium, which is what round 22 "
              "priced and this round now states as a decomposition\n  rather than a summary.")
    if capped["total"] < 0:
        print(f"\n  with borrowing forbidden the signal is {capped['total']*1200:+.2f}%/yr behind the index it "
              f"tracks.\n  Against its own equal-exposure control it is "
              f"{(capped['total']-ctrl['total'])*1200:+.2f}%/yr, which is the timing and nothing else:\n  "
              f"that number, not the one above, is the only honest measure of whether the signal is worth\n  "
              f"keeping. A rule that holds less than the index will lose to the index in a rising market\n  "
              f"by construction, and calling that a failure of the signal would be a category error.")
    print(f"\n  what this cannot say: that any of these differences is real rather than noise. Round 23 "
          f"settled\n  that a ${5_000:,.0f} + ${500:,.0f}/mo book resolves about "
          f"{6.0:.1f}%/yr at month 60 and none of these rows is close.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
