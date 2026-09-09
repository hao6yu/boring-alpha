"""How often the protocol's own skill test cries wolf, measured on paths with no skill in them.

`journal.verdict` is the pre-registered instrument: 24 monthly entries and enough paid in, and then `beat` if the account's
money-weighted return exceeds the comparator's, in basis points, by any amount at all. There is no variance term in it, no
margin, no confidence interval — the gap is compared to zero. That is a defensible protocol *floor* (it refuses the first two
years of talk, which is most of the harm a journal can do to its owner), but it means the sentence `skill: beat` is a statement
about the sign of one number, and the sign of a number that has no margin around it is not evidence.

So the instrument gets calibrated the way any other instrument in this repository is calibrated: run it on something known.
Two knowns, both built from the archive's own monthly returns so nothing has to be assumed about markets.

`hurdle-fee-matched` — every sleeve and the comparator fund earn SPY's return, and the comparator is charged the tilt's own
weighted expense ratio. This is as close to a null as the protocol permits, and "as close" is the finding: the book still pays
the 3 bps spread on every purchase it makes, and `comparator_path` pays nothing because the comparator is a construction rather
than an account. So this is not a coin flip, it is a hurdle, and what is measured is the height of the hurdle the strategy has
to clear before the sign of the gap even turns.

`hurdle-as-pinned` — same single index, but the comparator is charged what the real witness is charged (VOO's posted 3 bps) and
trades for nothing, exactly as the protocol specifies (`comparator_return`: "Commissions are zero, because the comparator is the
thing that could have been done for free"). This is the instrument as it will actually be used on the live books. A low `beat`
rate here is not the test being strict; it is the handicap doing its work, and the median gap is the handicap's price.

`replay` — the real returns of all three funds, drawn jointly month-by-month so cross-correlation and each fund's own volatility
survive, but the *order* of months is scrambled and chained forward from the archive's last month. This is not a null: the
archive's drift is in it. It answers a different question, namely how much of a 24-month gap is a fact about the sequence rather
than about the strategy.

Usage:

    .venv/bin/python tools/skill_null.py                      # both nulls and the replay, at 12/24/36/60 months
    .venv/bin/python tools/skill_null.py --paths 2000 --seed 1
    .venv/bin/python tools/skill_null.py --json

The printed margin is the number the runbook needs: the gap, in basis points of annualised return, that only 5% of no-skill
paths clear. A protocol that says `beat` at any positive gap will therefore say it on 5% of paths where the strategy is
worthless; a decision rule that demands the margin will not. Nothing here changes the sealed protocol — it is pinned, and a
threshold moved after the anchor is a goalpost — it only records what the pinned threshold is worth.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                           # noqa: E402
import power_horizon as ph                             # noqa: E402
from boring_alpha import journal                       # noqa: E402

BOOKS = ("SPY", "QQQ")
HORIZONS = (12, 24, 36, 60)
DEFAULT_SEED = 20260907
TAIL_PERCENTILES = (0.5, 0.9, 0.95)


# --- the archive's monthly returns, as the raw material ----------------------------------------------------------------


def monthly_returns() -> list[dict]:
    """`{symbol: gross}` for each month of the sealed archive, plus the month-end date, for SPY/QQQ/VOO."""

    closes = ph.month_closes(None)
    out = []
    for (day0, p0), (day1, p1) in zip(closes, closes[1:]):
        if all(sym in p0 and sym in p1 and p0[sym] > 0 for sym in BOOKS + ("VOO",)):
            out.append({"date": day1, "ret": {sym: p1[sym] / p0[sym] for sym in BOOKS + ("VOO",)}})
    return out


def start_level() -> dict:
    """The archive's last month-end prices, so a synthetic path begins where the real record stops."""

    return dict(ph.month_closes(None)[-1][1])


def month_ends(after: dt.date, count: int) -> list[dt.date]:
    """The first `count` month-ends after `after`, synthetic calendar."""

    out, year, month = [], after.year, after.month
    for _ in range(count):
        month += 1
        if month > 12:
            year, month = year + 1, 1
        following = dt.date(year + (month == 12), (month % 12) + 1, 1)
        out.append(following - dt.timedelta(days=1))
    return out


def synth_path(sampled: list[dict], dates: list[dt.date], level: dict, same_index: bool) -> list:
    """Chain sampled gross monthly returns forward from `level`, on the synthetic month-ends."""

    prices = dict(level)
    out = []
    for row, day in zip(sampled, dates):
        gross = row["ret"]["SPY"] if same_index else None
        prices = {sym: prices[sym] * (gross if same_index else row["ret"][sym]) for sym in BOOKS + ("VOO",)}
        out.append((day, dict(prices)))
    return out


# --- one book, on one synthetic path, judged by the protocol itself ----------------------------------------------------


def entries_for(path: list, book_closes: list, fee_total: float, asof_first: dt.date) -> tuple:
    """Fabricated entries carrying what a real seal would carry: dates, transfers, the account's own closing values, and the
    comparator's price on every one of them. The cadence is the live one — the anchor month funds nothing."""

    entries = []
    n = len(path)
    for i, (day, prices) in enumerate(path):
        arrived = 0.0 if i == 0 else paper.MONTHLY
        entries.append(journal.Entry(
            index=i, asof=day, prior_hash="0" * 64, plan="skill-null rehearsal", plan_posted_on=asof_first,
            opening_value=paper.OPENING if i == 0 else 0.0, cash_arrived=arrived, invested=paper.MONTHLY,
            days_to_invest=0, fee_paid=fee_total / n if i == n - 1 else 0.0,
            closing_value=book_closes[i],
            quotes=tuple(journal.Quote(sym, prices[sym]) for sym in ("SPY", "QQQ", "VOO")),
            holdings=(journal.Holding("SPY", 1.0),), violations=(), note="rehearsal"))
    return tuple(entries)


def run_once(mode: str, months: list[dict], horizon: int, rng: random.Random, band: float,
             commission: float) -> float | None:
    """One path, judged. Returns the protocol's `shortfall_bps`, or None if it withheld the verdict."""

    same_index = mode.startswith("hurdle")
    sampled = [rng.choice(months) for _ in range(horizon)]
    level = start_level()
    dates = month_ends(ph.month_closes(None)[-1][0], horizon)
    path = synth_path(sampled, dates, level, same_index)

    weights = paper.tilt_weights()
    fees = {sym: paper.fee_for(sym) for sym in BOOKS}
    if mode == "hurdle-fee-matched":
        # Equalise the expense ratio, so the difference left is that the book trades and the comparator is a construction.
        # Without this the "null" contains a real fee advantage for one side and measures that instead. The spread cannot be
        # equalised without editing the protocol, and the protocol is pinned -- which is the round's finding, not its bug.
        weighted = sum(weights[s] * fees[s] for s in BOOKS)
        fees = {sym: weighted for sym in BOOKS}
    stats: dict = {}
    closes = ph.simulate(path, paper.OPENING, paper.MONTHLY, weights, paper.SPREAD_BPS, commission, fees,
                         band=band, stats=stats)
    entries = entries_for(path, closes, stats.get("fees", 0.0), dates[0])
    witness_fee = sum(weights[s] * paper.fee_for(s) for s in BOOKS) if mode == "hurdle-fee-matched" else paper.fee_for("VOO")
    comparator = journal.Comparator(name="skill-null VOO", weights={"VOO": 1.0}, expense_ratio=witness_fee)
    return journal.verdict(entries, comparator, dates[-1]).shortfall_bps


# --- the calibration ---------------------------------------------------------------------------------------------------


def calibrate(mode: str, months: list[dict], horizon: int, paths: int, seed: int, band: float,
              commission: float) -> dict:
    rng = random.Random(seed + horizon * 1_000 + len(mode))
    # A horizon below the protocol's floor is not a null result, it is silence, and silence is recorded as silence rather
    # than smuggled in as a zero. `journal.verdict` refuses to speak until 24 entries exist.
    gaps = [g for g in (run_once(mode, months, horizon, rng, band, commission) for _ in range(paths)) if g is not None]
    if not gaps:
        return {"mode": mode, "horizon": horizon, "paths": 0, "beat": None, "median_bps": None, "p50": None,
                "p90": None, "p95": None, "margin_bps_p95": None,
                "withheld": f"all {paths}: the protocol prints `underpowered` below"
                            f" {journal.MIN_ENTRIES_FOR_SKILL_VERDICT} entries"}
    gaps.sort()
    beaten = sum(1 for g in gaps if g > 0.0) / len(gaps)
    quantiles = {f"p{int(q * 100)}": gaps[min(int(q * len(gaps)), len(gaps) - 1)] for q in TAIL_PERCENTILES}
    return {"mode": mode, "horizon": horizon, "paths": len(gaps), "beat": beaten,
            "median_bps": statistics.median(gaps), "margin_bps_p95": quantiles["p95"], **quantiles}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paths", type=int, default=400)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--horizons", default=",".join(str(h) for h in HORIZONS))
    ap.add_argument("--band", type=float, default=paper.TILT_BAND_POINTS)
    ap.add_argument("--commission", type=float, default=0.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    months = monthly_returns()
    horizons = [int(h) for h in args.horizons.split(",") if h.strip()]
    modes = ("hurdle-fee-matched", "hurdle-as-pinned", "replay")
    rows = [calibrate(m, months, h, args.paths, args.seed, args.band, args.commission)
            for m in modes for h in horizons]

    if args.json:
        print(json.dumps({"archive_months": len(months), "band": args.band, "commission": args.commission,
                          "seed": args.seed, "rows": rows}, indent=2))
        return 0

    print(f"# the protocol's own skill test, run on {args.paths} paths of {len(months)} archived months"
          f"  [band {args.band} pts, ticket {args.commission}, seed {args.seed}]\n")
    print("construction        months   beat by any gap    median gap    p90 gap    p95 gap (the margin)")
    for r in rows:
        if r["beat"] is None:
            print(f"{r['mode']:<18} {r['horizon']:>6} {r['withheld']:>48}")
            continue
        print(f"{r['mode']:<18} {r['horizon']:>6} {r['beat']:>17.1%} {r['median_bps']:>13.0f} "
              f"{r['p90']:>10.0f} {r['p95']:>15.0f}")
    for m in ("hurdle-fee-matched", "hurdle-as-pinned"):
        candidates = [r for r in rows if r["mode"] == m and r["horizon"] == 24 and r["beat"] is not None]
        if not candidates:
            continue
        line = candidates[0]
        print(f"\n  {m}: at the protocol's own floor of 24 entries, {line['beat']:.0%} of paths with no skill available"
              f" anywhere print `skill: beat`. Only 5% of them clear +{line['margin_bps_p95']:,.0f} bps.")
    print("\n  The protocol is pinned and stays pinned: 24 entries is a floor on *talking*, not a test of skill, and the")
    print("  median column is not zero because the book pays to enter and the comparator does not. A decision about keeping")
    print("  the tilt needs the margin in the last column, or a longer record, or both.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
