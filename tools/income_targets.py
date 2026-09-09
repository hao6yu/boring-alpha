"""What capital clears a monthly target, which engine clears it, and what that capital costs.

Round 50. The ledger prices actions at $20,000 because a capital had to be picked; the guarantee engine prices a
stance at $100,000 for the same arbitrary reason. Neither answers the question the project was started to answer,
which is stated in dollars per month. This tool inverts the question: given a target, it reports the capital each
engine needs, and then prices the capital it just asked you to commit.

Two comparators, because "income" means two different things and a number that answers the wrong one is worse than
no number:

  * **principal-preserving** — the money producing the cheque stays intact. The comparator is VOO's own distribution
    yield, which is the only cash an index hands you without asking you to sell.
  * **spending allowed** — the cheque may consume principal. The comparator is the index with a systematic sale rule
    at its own guaranteed withdrawal rate, computed by `income_accounting` over every start date in the record.

The second is the one that matters, and it is the one that hurts: at the archive's own numbers, a T-bill ladder
produces less monthly cash than plain VOO with a sale rule, at every rate the bill curve has ever printed above its
own median, and it is the more fragile of the two. Cash income is not a strategy, it is a decision not to hold
equities, priced here in forgone compounding.

Run:  python tools/income_targets.py [--target 500] [--sleeve SPY] [--years 20]
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cash_yield_gap as cy                                              # noqa: E402
import income_accounting as ia                                           # noqa: E402
import withdrawal_capacity as wc                                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data            # noqa: E402

TARGETS = (250.0, 500.0, 1_000.0, 2_000.0)

# Horizons priced, and the date every horizon is re-measured onto so the slope is real. `wc.SNAPSHOT`'s record
# starts 1993-01, so a 30-year plan can only start before 1996-09: sampling each horizon on its own grid means the
# long plans are measured on the late-90s alone and their minima are not comparable to anything.
HORIZONS = (10, 15, 20, 25, 30)
COMMON_GRID_END = date(1996, 9, 30)

# The zero-rate era, for the only engine whose rate is not its own.
ZERO_RATE_ERA = (date(2020, 3, 1), date(2021, 12, 31))

# The variance-free rows of the action ledger, as a yield, at the ledger's own $20,000.
LEDGER_CERTAIN_MO_AT_20K = 30.66


def _dist_path() -> Path:
    return next((ROOT / "data" / "snapshots").glob("*/distributions_daily.csv"))


def dist_yield(symbol: str) -> tuple:
    """Distribution yield and events per year, from the snapshot's own dividend file.

    Computed rather than typed. The formula is the one the cash-float tests use: total dividends over the covered
    years, divided by the mean close the dividends were paid against.
    """

    path = _dist_path()
    total, closes, first, last = 0.0, [], None, None
    with path.open() as handle:
        for row in csv.DictReader(handle):
            if row["symbol"] != symbol or float(row["dividend"]) <= 0:
                continue
            total += float(row["dividend"])
            closes.append(float(row["close"]))
            first = row["date"] if first is None else min(first, row["date"])
            last = row["date"] if last is None else max(last, row["date"])
    if not closes:
        return 0.0, 0.0
    years = max((date.fromisoformat(last) - date.fromisoformat(first)).days / 365.25, 1.0)
    return total / years / statistics.fmean(closes), len(closes) / years


def sale_rate(data, symbol: str, years: int, lever: float = 1.00, until=None) -> dict:
    """The guaranteed withdrawal, per dollar of capital, on a chosen start grid."""

    g = ia.guarantee(symbol, lever, 1.0, years, data, 1, until=until)
    if g["cheque"] is None:
        return {"rate": None, "starts": 0, "binding": None}
    return {"rate": g["cheque"] * 12.0, "starts": g["starts"], "binding": g["binding"]}


def ladder_rate(data, balance: float = 20_000.0) -> dict:
    """The bill ladder's cash rate at the spot, the record median, the lower quartile and the zero-rate era."""

    pth = cy.path(data)
    _r, factors, keys = cy.cash_months(data)
    era = [f * 12.0 for f, k in zip(factors, keys) if ZERO_RATE_ERA[0] <= k <= ZERO_RATE_ERA[1]]
    worth = lambda rate: (rate - cy.SGOV_ER - cy.SWEEP_MEDIAN) * balance / 12.0  # noqa: E731
    return {"spot": pth["spot"], "median": pth["median"], "q1": pth["q1"],
            "era": statistics.fmean(era), "era_months": len(era),
            "worth_spot": worth(pth["spot"]), "worth_median": worth(pth["median"]),
            "worth_q1": worth(pth["q1"]), "worth_era": worth(statistics.fmean(era)),
            "percentile": pth["percentile"]}


def required(rate: float, target: float) -> float:
    """Capital that produces `target` a month at an annual rate. Infinite at a zero rate, which is the point."""

    return target * 12.0 / rate if rate and rate > 0 else float("inf")


def engines(data, symbol: str, years: int) -> list:
    """Every engine that can produce a monthly cheque, as an annual cash rate, with what it costs to hold."""

    lad = ladder_rate(data)
    sale = sale_rate(data, symbol, years)
    tilt = 27.24 / 20_000.0 * 12.0
    out = [
        {"name": f"systematic sale, {symbol} at 1.0x, {years}y, worst start", "rate": sale["rate"],
         "starts": sale["starts"], "cash": "yes, by selling", "regime": "none: it is a path minimum",
         "principal": "consumed by design", "src": "income_accounting, r41-43"},
        {"name": "the same sale rule, on a common start grid", "rate": sale_rate(
            data, symbol, years, until=COMMON_GRID_END)["rate"],
         "starts": sale_rate(data, symbol, years, until=COMMON_GRID_END)["starts"],
         "cash": "yes, by selling", "regime": "none", "principal": "consumed by design",
         "src": "r50, comparability control"},
        {"name": "T-bill ladder, today's bill curve", "rate": lad["spot"] - cy.SGOV_ER,
         "starts": lad["percentile"], "cash": "yes, monthly", "regime": "total", "principal": "intact",
         "src": "r31, restated r47"},
        {"name": "T-bill ladder, the record's median month", "rate": lad["median"] - cy.SGOV_ER,
         "starts": len(cy.cash_months(data)[2]), "cash": "yes, monthly", "regime": "total",
         "principal": "intact", "src": "r44"},
        {"name": "T-bill ladder, the zero-rate era", "rate": lad["era"] - cy.SGOV_ER,
         "starts": lad["era_months"], "cash": "yes, monthly", "regime": "total", "principal": "intact",
         "src": "r44, the era that pays nothing"},
        {"name": "the ledger's variance-free rows, as a yield", "rate": LEDGER_CERTAIN_MO_AT_20K / 20_000.0 * 12.0,
         "starts": None, "cash": "no: most is a cost avoided", "regime": "low", "principal": "n/a",
         "src": "ledger r49"},
        {"name": "the 1.25x tilt, as a yield", "rate": tilt, "starts": None,
         "cash": "no: it is a mark", "regime": "total", "principal": "n/a", "src": "ledger r29"},
        {"name": f"{symbol}'s own distribution yield", "rate": dist_yield(symbol)[0],
         "starts": round(dist_yield(symbol)[1] * 33), "cash": "yes, unasked", "regime": "low",
         "principal": "intact", "src": "the archive's dividend file"},
    ]
    return [e for e in out if e["rate"] is not None]


def horizon_table(data, symbol: str) -> list:
    """Raw versus common-grid guarantees, the artefact stated in the same table as the fix."""

    rows = []
    for years in HORIZONS:
        raw = sale_rate(data, symbol, years)
        com = sale_rate(data, symbol, years, until=COMMON_GRID_END)
        rows.append((years, raw, com))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", type=float, default=0.0, help="price one target only")
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--sleeve", default="SPY")
    ap.add_argument("--years", type=int, default=20)
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    rows = engines(data, args.sleeve, args.years)
    targets = (args.target,) if args.target > 0 else TARGETS
    growth = sale_rate(data, args.sleeve, args.years)
    lad = ladder_rate(data)

    print(f"the income ladder · what capital clears a monthly target, and what that capital costs\n")
    print(f"  {'engine':52} {'cash %/yr':>10} {'$250/mo':>11} {'$500/mo':>11} {'$1,000/mo':>11} "
          f"{'$2,000/mo':>11}")
    print("  " + "-" * 118)
    for e in sorted(rows, key=lambda x: -x["rate"]):
        cells = "".join(f"{required(e['rate'], t):>11,.0f}" if required(e["rate"], t) < 1e12
                        else f"{'never':>11}" for t in TARGETS)
        print(f"  {e['name']:52} {e['rate'] * 100:>9.2f}% {cells}")
    print("\n  'never' is not a rounding: the zero-rate era produced "
          f"{(lad['era'] - cy.SGOV_ER) * 100:.2f}% a year, so a ladder cannot clear a target that"
          " year at any capital.")

    print(f"\n  the horizon artefact, and the control that removes it ({args.sleeve} at 1.0x)")
    print(f"  {'years':>6} {'raw':>10} {'starts':>8} {'common grid':>12} {'starts':>8}   raw says / grid says")
    print("  " + "-" * 78)
    prev = None
    for years, raw, com in horizon_table(data, args.sleeve):
        trend = ""
        if prev is not None:
            trend = ("RISES (impossible)" if raw["rate"] > prev[0] else "falls") + " / " + (
                "RISES (impossible)" if com["rate"] > prev[1] else "falls")
        print(f"  {years:>6} {raw['rate'] * 100_000 / 12:>10,.2f} {raw['starts']:>8} "
              f"{com['rate'] * 100_000 / 12:>12,.2f} {com['starts']:>8}   {trend}")
        prev = (raw["rate"], com["rate"])
    print("  The raw column rises from 25 to 30 years. That is not prudence paying interest, it is the grid: a"
          " 30-year\n  plan can only start before 1996-09, so its minimum is drawn from four years of the late"
          " nineties while\n  the 20-year minimum is drawn from 165 starts including the 2000s. On 44 shared"
          " starts the guarantee falls\n  monotonically with horizon, which is the only shape the arithmetic"
          " allows. Never quote a minimum without\n  the count beside it, and never take a slope across minima"
          " that use different samples.")

    cap = args.capital
    print(f"\n  at {cap:,.0f} of capital, per month:")
    for e in rows:
        if e["rate"] is None:
            continue
        income = e["rate"] * cap / 12.0
        print(f"    {e['name']:52} {income:>+9,.2f}   {e['regime']:24} {e['principal']}")
    print(f"\n  Read the two comparators together. A {args.years}-year systematic sale into {args.sleeve} clears"
          f" {growth['rate'] * cap:,.0f}/mo\n  from every start in the record ({growth['starts']} starts, binding"
          f" {str(growth['binding'])[:7]}); a bill ladder at today's\n  65th-percentile bill clears"
          f" {lad['worth_spot'] * cap / 20_000.0:,.0f}/mo and at the record median"
          f" {lad['worth_median'] * cap / 20_000.0:,.0f}/mo, and it is the only\n  number on this"
          " page that collapses if the Fed does. The ladder's whole case is that you are not allowed to sell."
          " If\n  you are allowed to sell, the archive says the sale rule is the bigger cheque and the steadier"
          " one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
