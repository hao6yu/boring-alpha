#!/usr/bin/env python3
"""How reproducible is the corpus, measured rather than assumed — and does the drift reach a verdict?

The archive says its snapshots are immutable and content-addressed, and they are: nothing in this repository edits a snapshot directory. What
that claim does not say is what happens when the same window is fetched a second time. Round 8 fetched it, into a scratch directory, on the
same day as an archived snapshot covering the identical date range, and 72.6% of the price rows disagreed. They disagreed by almost nothing —
the largest relative move was 2.31e-06, about a hundredth of a cent on a $770 close — because a vendor's adjusted series is a *derived*
quantity: every dividend and split between the row and today is folded into it, so the restatement of one adjustment moves the whole history in
its last digits.

That is a fact about the noise floor of the corpus, and it matters for two reasons. A monthly book seals quotes taken from a fetch, and a later
audit recomputes against a fetch: if the numbers do not survive re-fetching, the audit is comparing a book against a moving ruler. And a
reader who cannot reproduce a snapshot byte for byte needs to know whether the conclusions reproduce instead.

So this tool answers both questions, and refuses on the second one:

    .venv/bin/python tools/corpus_drift.py data/current /tmp/wherever/i/just/fetched

The row statistics are reported as measurement. The verdict is not about whether the bytes match — they will not — but whether the four figures
this objective actually publishes come out the same from both corpora: P0's affordable monthly bill, its median multiple, the 20% sleeve's bill,
and the max drawdown that gates it. If any of them moves, the exit code is 1 and the message says which, because *that* is the point at which
"the vendor revised the history" stops being trivia.

Run it before trusting a re-fetch, and before believing that a sealed figure can be recomputed from the vendor rather than from the archive.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import ba005                                                     # noqa: E402  the figures this objective publishes
import ba006                                                     # noqa: E402  recomputed the same way the specs compute them
import monthly_income_race as mir                                # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

PRICES = "market_daily.csv"
CASH = "cash_daily.csv"


def rows(snapshot: Path) -> dict[tuple[str, str], tuple[float, float]]:
    with (snapshot / PRICES).open(newline="") as handle:
        return {(r["date"], r["symbol"]): (float(r["tr_open"]), float(r["tr_close"])) for r in csv.DictReader(handle)}


def row_drift(a: Path, b: Path) -> dict:
    left, right = rows(a), rows(b)
    shared = set(left) & set(right)
    moved = [(abs(right[k][1] - left[k][1]) / left[k][1], k) for k in shared if left[k] != right[k] and left[k][1]]
    rel = sorted(r for r, _ in moved)
    return {"rows_a": len(left), "rows_b": len(right), "shared": len(shared),
            "only_one_side": len(set(left) ^ set(right)), "differing": len(moved),
            "share": len(moved) / max(len(shared), 1),
            "median_rel": rel[len(rel) // 2] if rel else 0.0,
            "max_rel": rel[-1] if rel else 0.0,
            "worst": sorted(moved, reverse=True)[0][1] if moved else None}


def figures(snapshot: Path) -> dict:
    """The published numbers, computed through the same functions the specs quote them from — never a second implementation."""

    md = load_csv_market_data(snapshot / PRICES, snapshot / CASH)
    legs = ba006.price_legs(md)
    p0_bill = ba006.bill_of(legs["voo"])
    costed = ba006.sleeve_returns(legs, 0.0)
    stats = mir.plan_stats(legs["voo"], ba005.CAPITAL, p0_bill, ba006.YEARS, floor=1.0)
    return {"last": str(md.dates[-1]), "sessions": len(md.dates), "p0_bill": p0_bill,
            "p0_median_multiple": stats["median_mult"],
            "sleeve20_bill": ba006.bill_of(ba006.blend(costed, legs["voo"], max(ba006.WEIGHTS))),
            "sleeve20_drawdown": ba006.drawdown(ba006.blend(costed, legs["voo"], max(ba006.WEIGHTS)))}


#: A figure's tolerance is the precision it is *published* at, not a number invented here. Half of the smallest printed unit is the
#: largest difference that leaves every published rendering of the figure unchanged; the round-8 measurement put the corpus's own noise at
#: 2.31e-06 relative, an order of magnitude inside that, which is the only reason the distinction is affordable. A change big enough to
#: notice at all — MATERIAL_REL, a relative cap — fails on its own terms, however it is printed. The relative cap is not decoration: an absolute
#: tolerance goes slack where a figure is near zero, and a monthly bill halved from $0.004 to $0.008 is the same printed cent.
TOLERANCES = {"p0_bill": ("$", "$/mo, printed to the cent", 0.005),
              "p0_median_multiple": ("x", "printed to two decimals", 0.005),
              "sleeve20_bill": ("$", "$/mo, printed to the cent", 0.005),
              "sleeve20_drawdown": ("", "printed as a percent to two decimals", 0.00005)}
MATERIAL_REL = 0.01


def compare(a: Path, b: Path) -> tuple[dict, list[str]]:
    drift, fa, fb = row_drift(a, b), figures(a), figures(b)
    report = {"drift": drift, "first": fa, "second": fb, "figures": {}}
    problems = []
    if drift["only_one_side"]:
        problems.append(f"{drift['only_one_side']} keys exist on one side only: the two corpora do not cover the same panel")
    if fa["last"] != fb["last"]:
        problems.append(f"the two corpora end on different sessions: {fa['last']} against {fb['last']}")
    # 1e-9 of a dollar is not a rounding convention arguing with itself; anything a cent could notice is a changed answer.
    for key, label in (("p0_bill", "P0's affordable bill"), ("p0_median_multiple", "P0's median multiple"),
                       ("sleeve20_bill", "the 20% sleeve's bill"), ("sleeve20_drawdown", "the 20% sleeve's drawdown")):
        unit, precision, tolerance = TOLERANCES[key]
        delta = fb[key] - fa[key]
        report["figures"][key] = {"first": fa[key], "second": fb[key], "delta": delta, "tolerance": tolerance}
        if abs(delta) > tolerance or abs(delta) > MATERIAL_REL * max(abs(fa[key]), 1e-12):
            problems.append(f"{label} moved by {unit}{delta:+.6f} (tolerance {unit}{tolerance}, {precision})")
    return report, problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("first", type=Path, help="a snapshot directory (usually `data/current`)")
    ap.add_argument("second", type=Path, help="another snapshot of the same window, usually a fresh fetch")
    args = ap.parse_args()
    for snapshot in (args.first, args.second):
        if not (snapshot / PRICES).exists():
            raise SystemExit(f"{snapshot} has no {PRICES}; a drift probe needs two snapshots, not two ideas")

    report, problems = compare(args.first, args.second)
    d, fa, fb = report["drift"], report["first"], report["second"]
    print("  Corpus reproducibility, measured as row drift and as verdict stability")
    print(f"    rows          {d['rows_a']:,} against {d['rows_b']:,}, {d['shared']:,} shared, "
          f"{d['only_one_side']:,} present on one side only")
    print(f"    drifted       {d['differing']:,} rows ({d['share']:.1%} of the shared panel)")
    print(f"    size          median {d['median_rel']:.2e}, max {d['max_rel']:.2e} relative"
          + (f"  worst {d['worst'][0]} {d['worst'][1]}" if d["worst"] else ""))
    for key, facts in report["figures"].items():
        unit = TOLERANCES[key][0]
        print(f"      {key:<20}{unit}{facts['first']:>12,.6f}  against {unit}{facts['second']:>12,.6f}"
              f"   delta {unit}{facts['delta']:+.6f}  tolerance {unit}{facts['tolerance']}")
    print(f"    conclusions   P0 bill ${fa['p0_bill']:,.2f} against ${fb['p0_bill']:,.2f}   "
          f"median {fa['p0_median_multiple']:.2f}x against {fb['p0_median_multiple']:.2f}   "
          f"20% bill ${fa['sleeve20_bill']:,.2f} against ${fb['sleeve20_bill']:,.2f}   "
          f"20% DD {fa['sleeve20_drawdown']:.2%} against {fb['sleeve20_drawdown']:.2%}")
    if problems:
        print("    VERDICT: the drift reaches a published figure — a re-fetch is not a re-reading of the same archive")
        for problem in problems:
            print(f"      - {problem}")
        return 1
    print("    VERDICT: the history is not byte-reproducible and the conclusions are; the snapshot, not the vendor, remains the authority")
    return 0


if __name__ == "__main__":
    sys.exit(main())
