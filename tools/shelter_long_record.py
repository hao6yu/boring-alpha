"""The shelter question on a record twice as long — because round 64's sample was an artefact of a ten-sleeve panel.

Round 64 priced the shelters on 2006-onward, which is the window `rotation_edge.panel` is forced into by the shortest of
its ten sleeves (DBC, listed 2006-02-06). That is a constraint of the panel, not of the question: a two-asset plan needs
only SPY, the shelter and the bill curve, and IEF and TLT have been quoted since 2002-07-30. So the same question can be
asked over a record that includes 2008, and over 169 ten-year windows instead of 127.

This file runs its own two-asset daily engine, on the repository's standing conventions: the trend read monthly,
expense ratios charged daily at 1/252 of the annual figure, 2 bps one-way on a change of position, and the bill curve
credited on the days the account is not in equities. The engine is pinned, not trusted — `--pin` hands it round 58's own
weights and must return **$593.13**, that round's published figure reached by a third independent path through this
repository. It does, to the cent.

`--pin` also separates the engine from the signal. The same rule on the same window is read four ways, and the spread
between those four readings is larger than any shelter gain this repository has measured — which is why the table prints
the convention it used and shows the other one beside it.

Run:  python tools/shelter_long_record.py [--since 2002-08-01] [--shelter all] [--conv start|end] [--pin]
"""

from __future__ import annotations

import argparse
import datetime as dt
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

# noqa is already unrolled below; plan_survival is the same simulator round 62 scored with
import plan_survival as ps                              # noqa: E402
import monthly_income_race as mir                          # noqa: E402
import shelter_test as st                                  # noqa: E402
import trend_cost_test as tc                               # noqa: E402
import withdrawal_capacity as wc                           # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data     # noqa: E402

CASH = "cash"
SHELTERS = (CASH, "IEF", "TLT", "GLD")
ER_GRID = st.ER_GRID
PANEL_PIN = 593.13          # round 58's figure, reached again through this file's own engine
WARMUP = 200                # days a 200-day average needs, and the length of the hole round 58's row sits in
PANEL_START = dt.date(2006, 2, 7)


def legs(data, sym: str) -> dict:
    """Date-keyed close and bill factor for one sleeve, so nothing is ever aligned by row number."""

    days, closes = tc.days_of(data, sym), tc.closes_of(data, sym)
    return {days[i]: (closes[i], data.cash_factors[days[i]] - 1.0) for i in range(len(days))}


def two_asset_path(dates: list, spy: dict, shelter, w: list, er_spy: float, er_shelter: float) -> list:
    """The daily balance of a plan that is in SPY or in the shelter, never in both, never partly in cash.

    `shelter` is None for the cash shelter, the one construction every earlier round measured: the off-equity half then
    earns the bill curve rather than an asset. Returns one balance per date after the first.
    """

    wealth, prev, out = 1.0, 0.0, []
    for i in range(1, len(dates)):
        d, dp = dates[i], dates[i - 1]
        weight = w[i - 1]
        gross = weight * (spy[d][0] / spy[dp][0] - 1.0 - er_spy / tc.DAYS)
        rest = 1.0 - weight
        if shelter is None:
            rest_ret = spy[d][1]                          # the bill factor, carried on the SPY dates
        else:
            rest_ret = shelter[d][0] / shelter[dp][0] - 1.0 - er_shelter / tc.DAYS
        wealth *= (1.0 + gross + rest * rest_ret - abs(weight - prev) * wc.TURNOVER_COST)
        prev = weight
        out.append(wealth)
    return out


def multi_asset_path(dates: list, series: dict, weights: dict, ers: dict, bill: dict) -> list:
    """The daily balance of a plan that holds any number of sleeves at once, with the rest in the bill curve.

    The general case of `two_asset_path`, written for the rotation round, and differentially tested against it: given one
    sleeve and one shelter at weights summing to 1, it reproduces that function's output to the last digit (see
    `tests/test_rotation_search.py`), because the costs have to mean the same thing in both. Turnover is therefore charged
    the same way — as **half the sum of the absolute weight changes**, which is one-way turnover, and which reduces to the
    single `abs(Δw)` the two-asset engine charges when only two legs exist. That convention, not a new one: rounds 61 to 74
    all priced switches this way, and a generalisation that quietly re-bases the cost model would invalidate every one of
    them while still looking self-consistent.
    """

    syms = sorted(weights)
    wealth, prev, out = 1.0, {s: 0.0 for s in syms}, []
    er_day = {s: ers.get(s, 0.0) / tc.DAYS for s in syms}
    for i in range(1, len(dates)):
        d, dp = dates[i], dates[i - 1]
        gross, bought, held = 0.0, 0.0, 0.0
        for s in syms:
            w = weights[s][i - 1]
            held += w
            gross += w * (series[s][d][0] / series[s][dp][0] - 1.0 - er_day[s])
            bought += max(0.0, w - prev[s])
            prev[s] = w
        rest = 1.0 - held
        wealth *= (1.0 + gross + rest * bill[d][1] - bought * wc.TURNOVER_COST)
        out.append(wealth)
    return out


def month_signal(dates: list, spy: dict, which: str = "end") -> dict:
    """Monthly marks: hold SPY if its close on the first (`start`) or last (`end`) trading day of a month was above a
    200-day moving average. Both are honest readings of "monthly MA200" and they are not the same rule.

    The average is computed over the WHOLE date list handed in, never over a window slice: computed on a slice it does
    not exist for the first two hundred days and the rule sits in cash through the opening year of the record, which is
    what the first draft of this file did and what it cost it a twelfth of its answer.
    """

    closes = [spy[d][0] for d in dates]
    mark = {}
    for i, d in enumerate(dates):
        prv = dates[i - 1] if i else None
        nxt = dates[i + 1] if i + 1 < len(dates) else None
        edge = ((prv is None or (prv.year, prv.month) != (d.year, d.month)) if which == "start"
                else (nxt is None or (nxt.year, nxt.month) != (d.year, d.month)))
        if edge:
            m = tc.sma(closes, WARMUP, i)
            if m is not None:
                mark[(d.year, d.month)] = 1.0 if closes[i] > m else 0.0
    return mark


def carry(mark: dict, dates: list) -> list:
    """Expand monthly marks into a daily weight series: hold the decision taken at the last reading of the month before."""

    w, live = [], 0.0
    for d in dates:
        key = (d.year - (d.month == 1), 12 if d.month == 1 else d.month - 1)
        if key in mark:
            live = mark[key]
        w.append(live)
    return w


def cadence_carry(dates: list, marks_by_index: dict, symbols: tuple = ()) -> dict:
    """Expand decisions made on a schedule of *any* period into daily weights, holding each decision for one full period.

    This is `carry` generalised off the calendar month, and it exists so cadence can be tested rather than assumed: a weekly
    plan and a monthly plan must be charged the same lag, or the only thing a sweep measures is which of them cheated first.
    The convention is `carry`'s, unchanged — the weight in force at day `k` is the decision read at the start of the period
    *before* the one containing `k`, never the period you are standing in, so no decision can trade on a reading taken after
    the close it would be applied to. A period whose predecessor made no decision holds the previous weight, which is also
    what `carry` does with a month that declined to answer. `marks_by_index` maps a decision day's index into `dates` to a
    `{symbol: weight}` dict; days before the first decision hold nothing at all.
    """

    order = sorted(marks_by_index)
    seen = {s for m in marks_by_index.values() if m for s in m}
    out = {s: [0.0] * len(dates) for s in (tuple(symbols) or tuple(sorted(seen)))}
    live: dict = {}
    for j, start in enumerate(order):
        stop = order[j + 1] if j + 1 < len(order) else len(dates)
        prior = marks_by_index[order[j - 1]] if j and marks_by_index.get(order[j - 1]) is not None else None
        if prior is not None:
            live = dict(prior)
        for k in range(start, stop):
            for s in out:
                out[s][k] = float(live.get(s, 0.0))
    return out


def held_stats(dates: list, series: dict, held: list) -> tuple:
    """Annualised return and worst drawdown of a sleeve, measured only over the days the signal was holding it."""

    tot = base = peak = 1.0
    worst, n = 0.0, 0
    for i in range(1, len(dates)):
        if not held[i - 1]:
            continue
        n += 1
        r = series[dates[i]][0] / series[dates[i - 1]][0] - 1.0
        tot *= (1.0 + r)
        base *= (1.0 + r)
        peak = max(peak, base)
        worst = min(worst, base / peak - 1.0)
    if not n:
        return 0.0, 0.0, 0
    return tot ** (tc.DAYS / n) - 1.0, -worst, n


def capacity(monthly: list, bench: list, capital: float, years: int, hi: float = 1_500.0) -> tuple:
    """Round 63's ceiling, recomputed here so the longer record gets its own rather than inheriting the panel's."""

    rows = []
    for p in (25.0 * i for i in range(int(hi // 25) + 1)):
        a = mir.plan_stats(monthly, capital, p, years, 0.0, 1.0)["p_fail"]
        b = mir.plan_stats(bench, capital, p, years, 0.0, 1.0)["p_fail"]
        if a is None or b is None or b >= 1.0 - 1e-12:
            break
        rows.append((p, a, b))
    signs = [1 if a > b + 1e-12 else 0 for _p, a, b in rows]
    first = next((rows[i][0] for i in range(len(signs)) if signs[i]), None)
    return first, {"flips": sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1]), "rungs": len(rows)}


def record(data, spy: dict, shelter: str, since: dt.date, capital: float, years: int, p_max: float,
           payout: float, conv: str) -> dict:
    """One shelter, one record, one convention: income, failure rate, capacity, and what the shelter did while held."""

    er_spy = wc.EXPENSE["SPY"]
    er = 0.0 if shelter == CASH else max(ER_GRID)
    series = None if shelter == CASH else legs(data, shelter)
    if series is None:
        dates = [d for d in sorted(spy) if d >= since]
    else:
        sd = set(series)
        dates = [d for d in sorted(spy) if d >= max(since, min(sd)) and d in sd]
    all_days = sorted(spy)
    marks = month_signal(all_days, spy, conv)
    other = "end" if conv == "start" else "start"
    sig = carry(marks, dates)
    path = two_asset_path(dates, spy, series, sig, er_spy, er)
    # `month_marks` indexes the path as `i - 1` against the date list it is given, so it must be handed the FULL date
    # list. Handing it the days the path covers shifts every month-end back one trading day. Round 58's trap.
    monthly = mir.month_marks(dates, path)[1]
    bench = mir.month_marks(dates, two_asset_path(dates, spy, None, [1.0] * len(dates), er_spy, 0.0))[1]
    alt = mir.month_marks(dates, two_asset_path(dates, spy, series,
                                               carry(month_signal(all_days, spy, other), dates), er_spy, er))[1]
    held = [x < 1e-9 for x in sig]
    cap, info = capacity(monthly, bench, capital, years)
    if shelter == CASH:
        hc, hm = statistics.fmean([spy[d][1] for d in dates[1:]]) * tc.DAYS, 0.0
    else:
        hc, hm, _n = held_stats(dates, series, held)
    stats = mir.plan_stats(monthly, capital, payout, years, 0.0, 1.0)
    return {"dates": dates, "monthly": monthly, "alt": mir.safe_amount(alt, capital, years, p_max, floor=1.0),
            "safe1": mir.safe_amount(monthly, capital, years, p_max, floor=1.0),
            "safe0": mir.safe_amount(monthly, capital, years, p_max, floor=0.0),
            "p_fail": stats["p_fail"], "n": stats["n"], "hcagr": hc, "hmdd": hm, "cap": cap,
            "bench_monthly": bench,
            "flips": info["flips"], "duty": sum(held) / len(held), "months": len(monthly), "since": dates[0]}


CELLS = ("insurance", "redundant", "cost", "fine")


def score_starts(monthly: list, capital: float, payout: float, contribution: float, years: int) -> list:
    """Every start month with a full plan in front of it, and whether the promise held. Same promise, same simulator as
    round 62, so the two rounds' tables can be read against each other."""

    months = years * 12
    rows = []
    for s in range(0, len(monthly) - months + 1):
        w = monthly[s:s + months]
        if contribution > 0:
            r = ps.simulate(w, capital, 0.0, contribution, 0.0)
            total = capital + contribution * months
            rows.append({"n": s, "failed": r["terminal"] < total - 1e-9, "multiple": r["terminal"] / total})
        else:
            r = ps.simulate(w, capital, payout, 0.0, 0.0)
            rows.append({"n": s, "failed": not r["survived"], "multiple": r["terminal"] / capital})
    return rows


def contingency(plans: dict, bench: list, capital: float, payout: float, contribution: float,
                years: int) -> dict:
    """Round 62's 2x2: a hedge earns its keep only in the cell where the thing it hedges would have failed."""

    base = score_starts(bench, capital, payout, contribution, years)
    out = {"__bench__": {"n": len(base), "fails": sum(1 for r in base if r["failed"]),
                        "skipped": 0}}
    for name, monthly in plans.items():
        if name == "__bench__":
            continue
        rows = score_starts(monthly, capital, payout, contribution, years)
        if len(rows) != len(base):
            out["__bench__"]["skipped"] += 1
            out[name] = {"n": len(rows), "insurance": None, "redundant": None, "cost": None, "fine": None,
                         "p_fail_self": None, "concordance": None, "spans": None, "short": True}
            continue
        cells = dict(zip(CELLS, (0, 0, 0, 0)))
        fails = []
        for r, b in zip(rows, base):
            if b["failed"] and r["failed"]:
                cells["redundant"] += 1
            elif b["failed"]:
                cells["insurance"] += 1
                fails.append(r["n"])
            elif r["failed"]:
                cells["cost"] += 1
            else:
                cells["fine"] += 1
        n_base_fail = cells["insurance"] + cells["redundant"]
        cells["n"] = sum(cells[k] for k in CELLS)
        cells["p_fail_self"] = (cells["redundant"] + cells["cost"]) / cells["n"]
        cells["concordance"] = (cells["redundant"] / n_base_fail) if n_base_fail else None
        cells["spans"] = (fails[0], fails[-1]) if fails else None
        out[name] = cells
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default="2002-08-01")
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--p-max", type=float, default=0.05)
    ap.add_argument("--payout", type=float, default=435.47)
    ap.add_argument("--conv", default="start", choices=("start", "end"),
                    help="which day of the month the trend is read on")
    ap.add_argument("--shelter", default="all")
    ap.add_argument("--pin", action="store_true", help="reproduce round 58 and separate engine from convention")
    ap.add_argument("--grid", action="store_true", help="round 62's 2x2, scored on this record")
    ap.add_argument("--contribution", type=float, default=1000.0)
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    spy = legs(data, "SPY")
    since = dt.date.fromisoformat(args.since)
    wanted = SHELTERS if args.shelter == "all" else tuple(x.strip() for x in args.shelter.split(","))

    if args.pin:
        import frequency_cost as fc
        import rotation_edge as re_
        ordered, rets, bills, base = re_.panel(data, re_.UNKNOWN_ER)
        pos = {d: i for i, d in enumerate(tc.days_of(data, "SPY"))}
        cl = tc.closes_of(data, "SPY")
        closes = {"SPY": [cl[pos[d]] for d in ordered]}
        wts = fc.weights_for_family("ma200", ordered, rets, bills, base, closes, "monthly", re_.UNKNOWN_ER)
        theirs = [float(w[re_.UNIVERSE.index("SPY")]) for w in wts]
        marks = {c: month_signal(sorted(spy), spy, c) for c in ("start", "end")}

        def safe(sig):
            path = two_asset_path(ordered, spy, None, sig, wc.EXPENSE["SPY"], 0.0)
            return mir.safe_amount(mir.month_marks(ordered, path)[1], args.capital, args.years, args.p_max,
                                   floor=1.0)

        got = safe(theirs)
        cell = {}
        for conv in ("start", "end"):
            warmed = carry(marks[conv], ordered)
            cell[(conv, "warmed")] = safe(warmed)
            cell[(conv, "cold")] = safe([0.0] * WARMUP + warmed[WARMUP:])
        ok = got is not None and abs(got - PANEL_PIN) < 0.01
        low, high = min(cell.values()), max(cell.values())
        first_day = fc.signal_days(ordered, "monthly")[0]
        print("engine and convention, separated · one engine, one window, cash shelter, four signals")
        print(f"  round 58 published: month-end signal days, average cold for the first {WARMUP} days, so the rule"
              f" sits in cash until {str(ordered[first_day])}                 {got:>10,.2f}")
        for conv in ("start", "end"):
            for state in ("cold", "warmed"):
                print(f"  this file, month-{conv:5}, average {state:6}                                     "
                      f"{'':>2} {cell[(conv, state)]:>10,.2f}")
        print(f"\n  engine pin: {got:,.2f} against round 58's {PANEL_PIN:,.2f} — "
              f"{'AGREES, exactly' if ok else 'DISAGREES, stop here'}")
        print(f"  the same rule and the same money, read four ways, spans {high - low:,.2f}/mo "
              f"({(high - low) / low:.0%} of the lowest), and the published cell is the highest of the four.")
        print(f"  warm-up, month-start {cell[('start', 'cold')] - cell[('start', 'warmed')]:+,.2f}"
              f"   month-end {cell[('end', 'cold')] - cell[('end', 'warmed')]:+,.2f}"
              f"   · convention at a warmed average {cell[('end', 'warmed')] - cell[('start', 'warmed')]:+,.2f}")
        print("\n  So it is not the arithmetic that moves this number. It is the warm-up hole, which is not a market")
        print("  judgement at all but a side-effect of where the panel begins: a rule held in cash by fiat for the")
        print("  first thirteen months of its own record is being handed an entry point, and the figure it earns from")
        print("  that entry point is the one this repository has quoted since round 58. The table below reads the trend")
        print("  from the first day it can, on a record that begins in 2002, and prints the other convention beside it.")
        return 0 if ok else 1

    print(f"the shelter question on a longer record · {args.capital:,.0f} start · {args.years}-year plans"
          f" · failure budget {args.p_max:.0%} · from {since}")
    print("  engine pinned against round 58's $593.13 by --pin; read that first\n")
    print(f"  signal read month-{args.conv}, average warmed from 1993 data · last column is the other reading")
    print(f"  {'shelter':9} {'from':10} {'months':>7} {'windows':>8} {'safe $/mo':>10} {'never-zero':>11}"
          f" {'P(fail)':>8} {'held CAGR':>10} {'held maxDD':>11} {'capacity':>9} {'vs cash':>9} {'other conv':>11}")
    print("  " + "-" * 122)
    out = {}
    for shelter in wanted:
        r = record(data, spy, shelter, since, args.capital, args.years, args.p_max, args.payout, args.conv)
        out[shelter] = r
        cap_txt = "—" if r["cap"] is None else f"${r['cap']:,.0f}"
        delta = "—" if shelter == CASH else f"{r['safe1'] - out[CASH]['safe1']:>+9,.2f}"
        print(f"  {shelter:9} {str(r['since']):10} {r['months']:>7} {r['n']:>8} {r['safe1']:>10,.2f}"
              f" {r['safe0']:>11,.2f} {r['p_fail']:>8.1%} {r['hcagr']:>10.2%} {r['hmdd']:>11.1%} {cap_txt:>9}"
              f" {delta:>9} {r['alt']:>11,.2f}")
    if args.grid:
        plans = {w: out[w]["monthly"] for w in wanted}
        bench = out[wanted[0]]["bench_monthly"]
        cells = contingency(plans, bench, args.capital, args.payout, args.contribution, args.years)
        frame = (f"{args.contribution:,.0f}/mo in, the promise that it ends whole" if args.contribution > 0
                 else f"{args.payout:,.2f}/mo out, the promise that it is not destroyed")
        print(f"\nround 62's 2x2, re-scored here · month-{args.conv} signal · {frame} · {args.capital:,.0f} start")
        print("  `insurance` is an entry where the index plan failed and this one held; `cost` is the debt. A hedge with")
        print("  an empty insurance cell is a cost with a story.\n")
        print(f"  {'leg':10} {'n':>4} {'insurance':>10} {'redundant':>10} {'cost':>5} {'fine':>5}"
              f" {'P(fail)':>8} {'concord.':>9}  entries it covered")
        print("  " + "-" * 96)
        d0 = args.years * 12
        dates = out[wanted[0]]["dates"]
        for name, c in cells.items():
            if name == "__bench__":
                print(f"  {'index':10} {c['n']:>4} {'—':>10} {'—':>10} {'—':>5} {'—':>5} "
                      f"{c['fails'] / c['n']:>8.1%} {'100%':>9}  the entries every other row is scored against")
                continue
            if c.get("short"):
                print(f"  {name:10} {c['n']:>4} {'—':>10} {'—':>10} {'—':>5} {'—':>5} {'—':>8} {'—':>9}"
                      f"  DROPPED: a shorter record than the index's, so the pairs would not line up")
                continue
            span = ("—" if c["spans"] is None
                    else f"{str(dates[d0 + c['spans'][0]]):10} to {str(dates[d0 + c['spans'][1]])}")
            conc = "—" if c["concordance"] is None else f"{c['concordance']:.0%}"
            print(f"  {name:10} {c['n']:>4} {c['insurance']:>10} {c['redundant']:>10} {c['cost']:>5}"
                  f" {c['fine']:>5} {c['p_fail_self']:>8.1%} {conc:>9}  {span}")
        print("\n  Concordance is the fraction of index-failing entries this leg ALSO failed at: zero is what a hedge")
        print("  looks like. Round 62 measured 0% over 283 starts from 1993 on the long record and a cash shelter.")
        print("  What is different here is the record's other half: more windows, a shelter that pays, and the trend")
        print("  read from the first day it can be.")
        return 0

    print("\n  `windows` is how many ten-year plans can be started in the record, which is the sample every number")
    print("  above is drawn from. Round 64 had 127. The point of this file is to have more of them, and to have them")
    print("  start in the years that lead into 2008 — and every shelter's own record begins when it was listed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
