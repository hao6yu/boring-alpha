"""What this paper book can actually detect, at this deposit schedule, before it is asked to mean anything.

    .venv/bin/python tools/book_power.py
    .venv/bin/python tools/book_power.py --horizons 6,12,24,36,48,60 --resamples 4000
    .venv/bin/python -m pytest tests/test_book_power.py -q

The book's own report says `underpowered — 23 more monthly entries … required`. That is one true sentence with
a useful question still inside it: **how much edge would it take, at $5,000 in and $500 a month, for this
instrument to see it?** The answer is a property of the deposit schedule and the volatility, not of the
strategy, so it is computable today — and computing it is the difference between a null result at month 24
meaning something and meaning nothing.

Everything here is read from the book, not restated: the model is whatever `data/paper/model.json` says
(`voltarget`, currently), the comparator is that file's pinned spec (100% SPY at 0.000945), the opening and
monthly deposit are the sealed entry's, and the spread is the book's own `spread_bps`. If someone re-pins the
book to a different rule, this tool follows without being edited.

The strategy leg is the same rule's weight path the backtests use, converted to a monthly net return: the
weight on the fund, the cash curve on the part not invested, the curve **plus** the book's spread on the part
borrowed, the expense ratio on the invested share, and the archive's per-side friction on every pound of
churn the rebalancing band allows. The null hypothesis is that this rule has no edge at all: the monthly
difference against the fund is shifted to exact zero, blocks are resampled in pairs so the correlation and the
volatility clustering survive, and each resample is run as an account.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                       # noqa: E402  the book itself: config, candidate, ledger
import withdrawal_capacity as wc                   # noqa: E402  the archive loader and the monthly helper
import income_frontier as ifr                      # noqa: E402  series_for, and the noise floor
from boring_alpha.metrics.bootstrap import book_power    # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402
from policy_withdrawal import monthly_weights        # noqa: E402

HORIZONS = (6, 12, 24, 36, 48, 60)
SEED = 20_260_906
SWEEP = 0.0002      # round 24: audited median default brokerage sweep, 2026-09-02


def net_strategy_returns(data, symbol: str, spread_bps: float, expense: float,
                         sweep: float | None = None, borrow: str = "book",
                         cap: float | None = None, static: float | None = None) -> tuple[list, list, list, list]:
    """The rule's monthly net return, the fund's, and the weights that produced them.

    One formula carries both the cash leg and the borrow leg, because `(1 - w)` is negative when the rule is
    levered: `w*r + (1-w)*cash` earns the curve on the idle part and pays it on the borrowed part, and the
    spread is then charged only where `w > 1`, which is the only place anything is borrowed.

    Two of the assumptions an account actually has are switchable, because round 24 showed both are
    load-bearing and neither is the one the paper book is configured with. `sweep` substitutes what a
    brokerage pays on idle cash (0.02% audited median) for the archive's Treasury curve. `borrow="posted"`
    charges the whole loan at the posted desk rate rather than curve-plus-spread: `paper.py` models a line
    of credit at the bill rate plus its 3bp *execution* spread, and 3bp is the price of a fill, not the
    price of money. With both switches on, this is what a levered account at an ordinary desk earned —
    which is the number the archive itself cannot show.

    `cap` truncates the policy's own weights (round 26: the same signal, told it cannot borrow) and `static`
    replaces the whole path with a fixed weight, which is how a control for *how much* is invested gets built
    so that a claim about *when* can be checked against it.
    """

    series = ifr.series_for(data, symbol)
    days, closes = list(series.keys()), list(series.values())
    returns, rates, keys = wc.monthly(series, data.cash_factors)
    if static is not None:
        weights = [static] * len(keys)
    else:
        weights = monthly_weights(paper.CANDIDATE, days, closes, keys)
        if cap is not None:
            weights = [min(w, cap) if w is not None else None for w in weights]
    spread = spread_bps / 10_000.0
    flat = (1.0 + float(sweep)) ** (1.0 / 12.0) - 1.0 if sweep is not None else None
    out, used, held = [], [], []
    prior = None
    for i, key in enumerate(keys):
        w = weights[i] if i < len(weights) else None
        if w is None:
            continue
        cost = abs(w - prior) * (wc.TURNOVER_COST + (spread if prior is not None and w > prior else 0.0)) \
            if prior is not None else 0.0
        cash = flat if flat is not None else rates[i]
        # `withdrawal_capacity.run` charges financing as `cash_rate[month] + spread / 12.0`, and this tool has
        # to match it or the two files stop describing the same account. `MENU_PUBLIC` is an ANNUAL posted rate:
        # used per month it is 58% a year and turns a 0.3% edge into a 10% hole, which is exactly what the
        # first draft of this line did, and the first-order estimate (mean leverage 18% against a two-point
        # rate gap, about 0.7%/yr) is what caught it.
        fin = spread / 12.0 if borrow != "posted" else (1.0 + ifr.MENU_PUBLIC) ** (1.0 / 12.0) - 1.0 - cash
        gross = w * returns[i] + (1.0 - w) * cash - (max(w - 1.0, 0.0) * fin) \
            - w * expense / 12.0 - cost
        out.append(gross)
        used.append(key)
        held.append(w)
        prior = w
    index = {k: i for i, k in enumerate(keys)}
    # The comparator in `data/paper/model.json` is 100% SPY *net of its own expense ratio*, and paper.py's
    # shadow model charges it. The strategy leg pays the same fee, so the excess must net it from both legs or
    # the difference is biased against the rule by one whole expense ratio — which it was, in rounds 23 and 25,
    # by 0.0945%/yr: small, in the strategy's favour, and invisible until a static-100% control row printed
    # exactly the expense as its "excess vs the index" and made the omission arithmetic instead of prose.
    fee = expense / 12.0
    bench = [returns[index[k]] - fee for k in used]
    return out, bench, used, [w for w in (weights[i] for i in range(len(keys))) if w is not None]


def schedule() -> tuple[float, float, float]:
    """Opening, monthly deposit and spread, read from the sealed book rather than typed in here."""

    cfg = json.loads(paper.CONFIG.read_text())
    entries = paper.read(paper.LEDGER)
    opening = entries[0].opening_value if entries else paper.OPENING
    return float(opening), float(cfg.get("monthly", paper.MONTHLY)), float(cfg.get("spread_bps", 3.0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--horizons", default=",".join(str(h) for h in HORIZONS))
    ap.add_argument("--resamples", type=int, default=4_000)
    ap.add_argument("--block", type=int, default=3, help="months per block; 3 keeps vol clustering")
    ap.add_argument("--sweep", type=float, default=None,
                    help="annual rate the account is paid on idle cash, replacing the archive curve")
    ap.add_argument("--borrow", choices=("book", "posted"), default="book",
                    help="charge the loan at the book's curve+spread, or at the posted desk rate")
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    opening, monthly, spread_bps = schedule()
    cfg = json.loads(paper.CONFIG.read_text())
    symbol = next(iter(cfg["comparator"]["weights"]))
    expense = float(cfg["comparator"]["expense_ratio"])
    strat, bench, keys, weights = net_strategy_returns(data, symbol, spread_bps, expense,
                                                       sweep=args.sweep, borrow=args.borrow)
    edge = (sum(a - b for a, b in zip(strat, bench)) / len(strat))
    funded = opening + monthly * 30          # roughly what the account is worth mid-book
    # `edge` is a mean of monthly differences, so dollars a month are simply edge times capital. The first
    # draft of this line multiplied by 12 a second time and printed an annual figure under a "/mo" label,
    # which inflated the edge by a twelfth and made the book look three times as powerful as it is.
    edge_mo = edge * funded
    print(f"book: model {cfg['model_key']}, comparator {cfg['comparator']['name']} at {expense:.6f}, "
          f"${opening:,.0f} in + ${monthly:,.0f}/mo, spread {spread_bps:.1f} bps")
    print(f"rule's monthly net return over {len(strat)} months {keys[0]}..{keys[-1]}: "
          f"{edge*1200:+.2f}%/yr vs the fund = ${edge_mo:+,.2f}/mo (${edge_mo*12:+,.0f}/yr) "
          f"on ${funded:,.0f} of capital")
    print(f"null = that edge forced to zero, blocks of {args.block} months resampled in pairs, "
          f"{args.resamples} resamples\n")
    horizons = tuple(int(h) for h in args.horizons.split(","))
    rows = book_power(strat, bench, opening=opening, monthly=monthly, horizons=horizons, seed=SEED,
                      resamples=args.resamples, block=args.block, edge_monthly=edge_mo)
    print("  month   null gap p05..p95 (it should straddle zero)      smallest edge it can see    power at "
          f"${edge_mo:+,.2f}/mo")
    for row in rows:
        n = row["months"]
        value = opening + monthly * n
        print(f"  {n:>5}   ${row['p05']:>9,.0f} .. ${row['p95']:>9,.0f}   (se ${row['se']:>7,.0f})   "
              f"${row['mde_monthly']:>7,.0f} /mo  = {row['mde_monthly']/value*1200:>5.2f}%/yr   "
              f"{row['power_at_edge']*100:>5.0f}%")
    # The same rule under the four pairs of assumptions it can be run with. `edge` here is a mean of MONTHLY
    # differences, so dollars a month are edge times capital with no factor of twelve anywhere near it — the
    # unit slip this tool already made once lived in this line's neighbourhood, and a twelfth error in a table
    # whose whole point is an edge the reader cannot independently check is unforgivable.
    print(f"\n  what the {edge*1200:+.2f}%/yr is made of, and what it becomes under the two assumptions an\n"
          f"  account at an ordinary desk would actually have. `seen?` is whether the book could resolve it "
          f"at\n  month 60:")
    print(f"  {'cash leg':>24} {'borrow leg':>18} {'excess':>9} {'$/mo, $20k':>11} "
          f"{'MDE/mo':>8} {'seen?':>6}")
    variants = (("archive bill curve", None, "book: curve + 3bp", "book"),
                ("archive bill curve", None, "posted 4.90%", "posted"),
                (f"sweep {SWEEP:.2%}", SWEEP, "book: curve + 3bp", "book"),
                (f"sweep {SWEEP:.2%}", SWEEP, "posted 4.90%", "posted"))
    for clabel, sw, blabel, bo in variants:
        s2, b2, _k2, _w2 = net_strategy_returns(data, symbol, spread_bps, expense, sweep=sw, borrow=bo)
        e2 = sum(a - b for a, b in zip(s2, b2)) / len(s2)
        cap60 = opening + monthly * 60
        row60 = book_power(s2, b2, opening=opening, monthly=monthly, horizons=(60,), seed=SEED,
                           resamples=args.resamples, block=args.block, edge_monthly=e2 * cap60)[0]
        mde60 = row60["mde_monthly"]
        print(f"  {clabel:>24} {blabel:>18} {e2*1200:>+8.2f}% {e2*20_000.0:>+11,.2f} "
              f"{mde60/cap60*1200/100*100:>8.2f}% {'yes' if abs(e2*1200) >= mde60/cap60*1200 else 'no':>6}")
    seen = [r for r in rows if r["power_at_edge"] >= 0.80]
    print()
    if seen:
        print(f"  the archive's own predicted edge first becomes visible at month {seen[0]['months']}. "
              f"Until then\n  a null result is a fact about the instrument, and a positive one is luck with "
              f"a small n.")
    else:
        print(f"  nothing in this schedule makes the archive's predicted edge visible within "
              f"{max(horizons)} months. The book is\n  not a test of that edge; it is a test of whether the "
              f"rule behaves as designed when the\n  tape moves, which is the only claim this repository "
              f"has ever been willing to make about it.")
        longest_row = max(rows, key=lambda r: r["months"])
        edge_rate = edge * 1200
        rate = longest_row["mde_monthly"] / (opening + monthly * longest_row["months"]) * 1200
        print(f"  waiting is not the answer either: at month {longest_row['months']} the book can resolve "
              f"{rate:.1f}%/yr,\n  still {rate/edge_rate:.0f} times the {edge_rate:.2f}%/yr the rule is "
              f"worth on the archive. Detectability\n  improves quickly for two years and then flattens, "
              f"because the account's variance compounds\n  with its balance.")
        weakest = min(rows, key=lambda r: r["power_at_edge"])
        print(f"  best power seen anywhere: {max(r['power_at_edge'] for r in rows)*100:.0f}% "
              f"(at month {max(rows, key=lambda r: r['power_at_edge'])['months']}), against an edge of "
              f"${edge_mo:+,.2f}/mo, while the smallest edge this schedule could resolve is "
              f"${weakest['mde_monthly']:,.0f}/mo.")
    print(f"  for scale, round 18's noise floor: choosing SPY over VOO is worth ${ifr.NOISE_FLOOR/5:,.0f}/mo "
          f"per $100k.")
    print("\n  what the book CAN answer, because it does not compound:")
    behaviour(bench, keys, weights)
    return 0


def behaviour(bench: list, keys: list, weights: list) -> None:
    """The claim the book can settle inside a year: did the rule actually step aside when the fund fell apart.

    A dollar gap compounds, and so does the noise around it, which is why power over dollars is flat. A weight
    does not compound. Ask a question about the rule's *behaviour* in bad months and the sample is the bad
    months themselves — a few dozen in the archive, a handful in any two years of trading — and the answer
    arrives with the first crisis instead of after a decade of one.
    """

    episodes = list(zip(keys, bench, weights))
    bad = [row for row in episodes if row[1] < -0.05]
    worse = [row for row in episodes if row[1] < -0.10]
    years = len(episodes) / 12.0
    held = [row[2] for row in bad]                      # the exposure the rule was *holding*, not its return
    if not held:
        return
    rng = random.Random(SEED)
    # Bootstrap over episodes, not over months: the episode is the unit the claim is about, and a month-level
    # resample would count the same crash's neighbours as independent evidence about it.
    draws = sorted(statistics.fmean(rng.choices(held, k=len(held))) for _ in range(2_000))
    lo, mid, hi = draws[int(0.025 * len(draws))], statistics.fmean(held), draws[int(0.975 * len(draws))]
    print(f"    fund fell >5% in {len(bad)} months of {len(episodes)} ({len(bad)/years:.1f} a year); "
          f">10% in {len(worse)}")
    print(f"    the rule's mean weight in those months: {mid:.2f} "
          f"(95% {lo:.2f}..{hi:.2f}) against 1.00 for doing nothing")
    print(f"    expected episodes in the next 24 months: {len(bad)/years*24:.1f}, in 60: "
          f"{len(bad)/years*60:.1f} — that is the number the ledger can answer, and it is not a dollar number")
    print("    the book's `skill` line will stay underpowered at any deposit size. Its real claim is this "
          "line,\n    and it will have an answer the first time the tape moves.")


if __name__ == "__main__":
    raise SystemExit(main())
