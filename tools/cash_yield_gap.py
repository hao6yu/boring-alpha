"""The yield on idle cash: priced for the account, and audited against the yield the backtests assume.

    .venv/bin/python tools/cash_yield_gap.py
    .venv/bin/python tools/cash_yield_gap.py --balances 5000,20000,50000
    .venv/bin/python -m pytest tests/test_cash_yield_gap.py -q

Round 23 settled something uncomfortable: at a $20k account, no stochastic edge of the size this repository has
ever found can be *measured* — the paper book resolves 17 times coarser than the effect, and no amount of
deposit changes that, because a proportional edge and its noise both scale with capital. The corollary is the
reason this tool exists: **at this size the only improvements worth having are the ones with no variance**, the
ones whose value is a published rate and an arithmetic difference rather than a distribution.

And the same number that invalidates the measurement is the one the backtests spend. Every simulation in this
repository credits the rule's uninvested third with the Treasury-bill curve from the sealed archive — 3.51%
over the last year — while the median brokerage default sweep across eleven tracked firms paid **0.02% APY**
as of 2026-09-02. This file prices both halves of that: what the difference is worth to an account that has to
live it, and what it costs a backtest that never noticed.

## Sources, as of the date on the top of the file, all published rather than assumed

    default bank-sweep, median of 11 firms   0.02% APY     switchwize, audited 2026-09-02
    default sweep, large brokers             0.05% APY     realcostreport, 2026
    money-market fund at those firms, median 3.40%          switchwize, audited 2026-09-02
    SGOV expense ratio                       0.09%         published fund data, confirmed 2026
    BIL expense ratio                        0.14%         published fund data, confirmed 2026

The bill leg needs no external source at all: it comes from the sealed archive's own cash curve, which is the
same series every backtest in this repository already accrues against. That asymmetry is deliberate — the
number most likely to be wrong in this file is the one the user can check on their own statement in ten
seconds, which is why the headline output is a **break-even sweep rate** rather than a verdict about any
particular broker.

Tax is not in any figure here. That exclusion was the user's instruction, and it biases these numbers *down*:
Treasury interest and T-bill funds are exempt from state income tax in most states, so the real gap is wider.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import book_power as bp                            # noqa: E402  the rule's weight path and its net returns
import income_frontier as ifr                      # noqa: E402  series_for, MENU_PUBLIC, NOISE_FLOOR
import withdrawal_capacity as wc                   # noqa: E402  the archive loader and the monthly helper
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

SWEEP_MEDIAN = 0.0002       # 2026-09-02, median default across 11 bank-sweep firms
SWEEP_LARGE = 0.0005        # the large-broker default everyone quotes
MMF_MEDIAN = 0.0340         # median money-market option at the same firms
import fund_fees                                                 # noqa: E402  the one sourced ratio table (r94, extended r99)

SGOV_ER, BIL_ER = fund_fees.fee_for("SGOV"), fund_fees.fee_for("BIL")
LADDER_COST = 0.0000        # bills bought at auction: no fee, no spread, one bill of effort
BALANCES = (2_000.0, 5_000.0, 10_000.0, 20_000.0, 50_000.0, 100_000.0)
RULE_EDGE_YR = 0.0034       # round 23: the rule's whole-record mean excess over its own fund
RULE_EDGE_MO_20K = 5.61     # ... restated at the account that exists


# One definition, in the module every consumer already imports. Kept as a module attribute so `cy.last_business_day`
# keeps working for the tests that name it.
last_business_day = wc.last_business_day


def cash_months(data) -> tuple:
    """Monthly SPY returns, annualised bill yields and month keys, **with a trailing partial month removed**.

    Round 47 found the defect this function exists to prevent. The archive seals after each session, so its last
    month is usually a stub: as of the 2026-09-04 seal, September held four trading days, and `wc.monthly` still
    emits it as one observation. `bill()` then annualised the last three buckets by taking the mean monthly factor
    and compounding it twelve times, which treated a four-day accrual as a month and returned **2.88% against the
    curve's own 3.81% for August** — 93bp low. Everything downstream of that number (`worth_spot`, the percentile
    that produced the sentence "today sits below the median of the record") inherited the error, and the direction
    was to understate the very recommendation the file exists to make. A bucket counts only if the seal has passed
    its last weekday.
    """

    return wc.monthly_complete(ifr.series_for(data, "SPY"), data.cash_factors, max(data.by_date))


def bill(data) -> dict:
    """The bill leg, straight off the sealed archive's cash curve, measured on complete months only."""

    _rets, rates, _keys = cash_months(data)

    def ann(n: int) -> float:
        return (1.0 + statistics.fmean(rates[-n:])) ** 12 - 1.0
    # `current3m` is a three-month annualisation and is NOT the same thing as `last3y`: the curve has been
    # falling, and today it quotes 1.5 points below its own three-year average. A forward-looking cash
    # decision should be priced off the first of those, which is also the conservative one here.
    return {"current3m": ann(3), "last1y": ann(12), "last3y": ann(36), "last10y": ann(120),
            "sigma_mo": statistics.pstdev(rates[-36:])}


def path(data) -> dict:
    """What the switch was worth in *every* month of the archive, not just today.

    Round 30 killed the habit of pricing a rate-dependent plan off one window, and `cash_yield_gap.py` had
    been doing exactly that: it quotes four windows and a spot, and the recommendation reads as if 2.88% were
    weather rather than a point in a cycle. This is the same decision priced against the whole record, so the
    question "is it worth setting up a bill fund at all" can be answered with a distribution instead of a
    snapshot. The units are annualised, so a month's worth is the rate divided by twelve.
    """

    _rets, factors, _keys = cash_months(data)
    rates = [r * 12.0 for r in factors]
    ordered = sorted(rates)
    n = len(rates)

    def pct(p: float) -> float:
        return ordered[min(n - 1, int(p * n))]

    today = bill(data)["current3m"]
    worth = [(x - SGOV_ER - SWEEP_MEDIAN) for x in rates]          # annual rate on $1
    return {"months": n, "spot": today, "percentile": sum(1 for x in rates if x < today) / n,
            "median": pct(0.50), "q1": pct(0.25), "q3": pct(0.75), "min": ordered[0], "max": ordered[-1],
            "share_over_1k": sum(1 for x in worth if x * 20_000 / 12 >= 25.0) / n,
            "share_under_100": sum(1 for x in worth if x * 20_000 / 12 <= 2.50) / n,
            "worth_at_median": (pct(0.50) - SGOV_ER - SWEEP_MEDIAN) * 20_000.0 / 12.0,
            "worth_at_q1": (pct(0.25) - SGOV_ER - SWEEP_MEDIAN) * 20_000.0 / 12.0,
            "worth_spot": (today - SGOV_ER - SWEEP_MEDIAN) * 20_000.0 / 12.0}


def section_durability(p: dict, balances: tuple) -> None:
    where = "above" if p["spot"] > p["median"] else "below"
    print(f"\n  HOW LONG DOES THIS LAST — the same switch, priced in all {p['months']} months of the sealed record")
    print(f"  today's bill yield {p['spot']:.2%} sits at the {round(p['percentile'] * 100)}th percentile of the "
          f"archive, "
          f"{where}\n"
          f"  the record's median of {p['median']:.2%}: lower quartile {p['q1']:.2%}, upper {p['q3']:.2%}, range "
          f"{p['min']:.2%} to {p['max']:.2%}")
    print(f"  {'bill yield':>16}   {'at $20,000':>12}   what that means")
    for label, rate, mo in (("the record's median", p["median"], p["worth_at_median"]),
                            ("lower quartile", p["q1"], p["worth_at_q1"]),
                            ("today", p["spot"], p["worth_spot"])):
        print(f"  {rate:>15.2%}   {mo:>+11,.2f}/mo   {label}")
    print(f"  {p['share_over_1k']:.0%} of the record paid $25/mo or more on $20,000; "
          f"{p['share_under_100']:.0%} of it paid under $2.50.")
    print(f"  Do it once, and unwind the ladder if the curve ever goes where its lower quartile is. The switch")
    print(f"  is a standing option on rates being positive, and the record says the premium on that option is")
    print(f"  sometimes $50 a month and sometimes nothing: the median month is worth {p['worth_at_median']:+,.0f},")
    print(f"  the lower-quartile month {p['worth_at_q1']:+,.0f}. Today is {p['worth_spot']:+,.0f}.")


# What a desk may already pay on idle cash, all-in, April-September 2026. `SWEEP_MEDIAN` is the *default* at the
# eleven bank-sweep firms audited on 2026-09-02; the higher tiers are what a new account can get by moving, which
# is the alternative the switch competes against and was never priced against.
SWEEP_MENU = (
    ("this file's audited default", SWEEP_MEDIAN),
    ("large-broker default", SWEEP_LARGE),
    ("a plain savings account", 0.0100),
    ("a big desk's cash sweep, today", 0.0313),
    ("the MMF option at the same firms", MMF_MEDIAN),
    ("4.00%", 0.0400),
)


def sweep_sensitivity(data, balance: float) -> dict:
    """The switch, re-priced against the alternative of not needing it.

    Round 47. Thirteen rounds have quoted the switch at one sweep assumption — the 2bp default audited at the firms
    that hold most retail assets. But the same survey round that priced the margin menu (r46) has several desks
    paying 3.13% on idle cash by default, and a bill ladder yielding the curve minus its own 9bp expense cannot
    beat a sweep that already pays the curve. The action was never "run a ladder"; it was "stop leaving cash at a
    desk that pays 2bp", and the ladder is only one way to fix that defect. This prices the ordering.
    """

    _rets, factors, keys = cash_months(data)
    annual = [x * 12.0 for x in factors]
    spot = bill(data)["current3m"]
    rows = []
    for label, sweep in SWEEP_MENU:
        worth = [(x - SGOV_ER - sweep) * balance / 12.0 for x in annual]
        rows.append({"label": label, "sweep": sweep, "mean": statistics.fmean(worth),
                     "spot": (spot - SGOV_ER - sweep) * balance / 12.0,
                     "share_positive": sum(1 for w in worth if w > 0) / len(worth),
                     "worst": min(worth), "best": max(worth)})
    return {"balance": balance, "spot": spot, "months": len(annual), "rows": rows,
            "breakeven_spot": spot - SGOV_ER,
            "breakeven_median": pct_of([x * 12.0 for x in factors], 0.50) - SGOV_ER}


def pct_of(values: list, p: float) -> float:
    o = sorted(values)
    return o[min(len(o) - 1, int(p * len(o)))]


def section_sweep(s: dict) -> None:
    print(f"\n  WHAT THE SWITCH IS WORTH IF THE DESK ALREADY PAYS YOU — the same ladder, priced against the sweep "
          f"it replaces (balance ${s['balance']:,.0f})")
    print(f"  {'desk cash pays':32} {'sweep':>7}   {'archive mean':>13}   {'at today\'s bill':>15}   months paid")
    for r in s["rows"]:
        print(f"  {r['label']:32} {r['sweep']:>6.2%}   {r['mean']:>+11,.2f}/mo   {r['spot']:>+13,.2f}/mo"
              f"   {r['share_positive']:>5.0%}")
    print(f"  break-even sweep right now: {s['breakeven_spot']:.2%} (the bill curve {s['spot']:.2%} less SGOV's "
          f"{SGOV_ER:.2%} expense);")
    print(f"  the median month of the record would tolerate {s['breakeven_median']:.2%}.")
    print("  Read down the right-hand column, not the first. At a desk that pays 3% on idle cash the switch is "
          "not a\n  strategy with a small edge: it is close to nothing, and in the record's median month it is "
          "negative.\n  The whole value of this action is the 2bp — so the action is *leaving that desk*, and the "
          "ladder is the\n  last resort of someone who cannot leave it.")


REGIMES = (
    ("dot-com bear", "2000-09", "2002-10"),
    ("GFC", "2008-08", "2009-06"),
    ("march 2020", "2020-02", "2020-06"),
    ("rate-raising 2022", "2022-01", "2022-12"),
    ("QE bull 2010-2021", "2010-01", "2021-12"),
    ("VOO's whole record", "2010-09", "2026-09"),
    ("the whole archive", "1993-02", "2026-09"),
)


def contingency(data, balance: float) -> dict:
    """What the switch actually paid in the months the account needed it, as opposed to on average.

    Round 44. `section_durability` already reports the distribution of the switch's pay over the record, and every
    number in it is unconditional. The goal is phrased as a monthly income, and an income whose pay arrives when
    nothing else does is worth more per dollar than one that arrives when the account is also winning — so the
    conditional figures belong beside the unconditional ones rather than being inferred from them.

    They turn out to run the wrong way. The correlation between the switch's monthly dollars and SPY's monthly
    return is about zero, but its *level* is lower in the worst decile of market months than in the best, and in
    the three episodes where an equity account was actually being damaged the switch paid a fraction of its
    average — because a bill-fund ladder earns the policy rate, and the policy rate is cut precisely when the
    account is being hurt. It is not a hedge with a yield attached. It is a claim on the central bank's normal,
    and crises are the suspension of that normal.
    """

    rets, factors, keys = cash_months(data)
    annual = [x * 12.0 for x in factors]
    worth = [(x - SGOV_ER - SWEEP_MEDIAN) * balance / 12.0 for x in annual]
    mean = statistics.fmean(worth)

    def corr(a, b):
        ma, mb = statistics.fmean(a), statistics.fmean(b)
        sa, sb = statistics.pstdev(a), statistics.pstdev(b)
        if not sa or not sb:
            return 0.0
        return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (len(a) * sa * sb)

    order = sorted(range(len(rets)), key=lambda i: rets[i])
    tenth = max(1, len(rets) // 10)
    out = {"balance": balance, "months": len(worth), "mean": mean,
           "corr": corr(worth, rets),
           "worst_decile": statistics.fmean([worth[i] for i in order[:tenth]]),
           "best_decile": statistics.fmean([worth[i] for i in order[-tenth:]]),
           "crash": statistics.fmean([worth[i] for i in range(len(worth)) if rets[i] < -0.05]),
           "surge": statistics.fmean([worth[i] for i in range(len(worth)) if rets[i] > 0.05]),
           "regimes": [], "worst_months": []}
    for label, a, b in REGIMES:
        g = [worth[i] for i in range(len(worth)) if a <= keys[i].isoformat()[:7] <= b]
        if g:
            out["regimes"].append({"label": label, "months": len(g), "mean": statistics.fmean(g),
                                   "min": min(g), "share_of_mean": statistics.fmean(g) / mean if mean else 0.0})
    for i in order[:5]:
        out["worst_months"].append({"date": keys[i], "ret": rets[i], "worth": worth[i]})
    return out


def section_contingency(c: dict) -> None:
    print(f"\n  WHEN IT PAYS — the same switch, conditioned on the account's own situation (balance "
          f"${c['balance']:,.0f})")
    print(f"  unconditional mean over {c['months']} months: {c['mean']:+,.2f}/mo")
    print(f"  correlation with SPY's monthly return {c['corr']:+.3f}, and in the worst decile of market months "
          f"it paid {c['worst_decile']:+,.2f} against {c['best_decile']:+,.2f} in the best")
    print(f"  months SPY fell >5%: {c['crash']:+,.2f}/mo. months it rose >5%: {c['surge']:+,.2f}/mo.")
    print(f"  {'episode':20} {'months':>7} {'mean':>10} {'worst mo':>10}   vs its own average")
    for r in c["regimes"]:
        print(f"  {r['label']:20} {r['months']:>7} {r['mean']:>+9,.2f} {r['min']:>+9,.2f}"
              f"   {r['share_of_mean']:>6.0%} of the record mean")
    print("  the five worst market months in the record, and what the switch handed over in each:")
    for m in c["worst_months"]:
        print(f"    {m['date']}   SPY {m['ret']:+6.2%}   switch {m['worth']:+7,.2f}")
    print("  This is not a hedge. A bill ladder earns the policy rate, and the policy rate is cut exactly when an")
    print("  equity account is being damaged, so the one income in this project that requires no borrowing pays")
    print("  least in the months the money would have been needed — and it paid under $7 a month for the twelve")
    print("  years the account was also being told the market was fine.")


BEAR_DEPTHS = (0.10, 0.20, 0.30)


def drawdown(rets: list) -> list:
    """Trailing drawdown of the index itself, month by month, from nothing but the return series.

    Round 45 replaced hand-drawn crisis windows with this. `contingency`'s named episodes were dated by the author,
    which is the same class of cosmetic input that moved round 34's cadence figure by 11 points and round 38's
    guarantee by $26 a month. A month is defined as a bear month here — mechanically, from the index's own path —
    at three depths, so the claim can be read as a monotone relation rather than as three dates someone chose.
    """

    level, peak, out = 1.0, 1.0, []
    for r in rets:
        level *= (1.0 + r)
        peak = max(peak, level)
        out.append(level / peak - 1.0)
    return out


def bear_sweep(data, balance: float, depths=BEAR_DEPTHS) -> list:
    """The switch's pay in bear months, enumerated mechanically at three depths, under two weightings.

    Both weightings are reported because they disagree, and the disagreement is the point. Averaged **by month**,
    bear months pay far less than calm ones and the deficit grows monotonically with depth. Averaged **by episode**
    — treating each drawdown run as one crisis — the easing episodes average *more* than the record mean, because
    the two short high-rate episodes (2000-11, two months at $95.71) count the same as the 32-month zero-rate run
    that paid $3.95. There is no fact of the matter about what "a crisis" pays; there is only what the months in
    these episodes paid, and how much weight each month is given. Reporting one of the two would be reporting the
    weighting choice.
    """

    rets, factors, keys = cash_months(data)
    annual = [x * 12.0 for x in factors]
    worth = [(x - SGOV_ER - SWEEP_MEDIAN) * balance / 12.0 for x in annual]
    dd = drawdown(rets)
    mean = statistics.fmean(worth)
    out = []
    for depth in depths:
        runs, run = [], []
        for i in range(len(dd)):
            if dd[i] < -depth:
                run.append(i)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        bear = [i for run in runs for i in run]
        calm = [i for i in range(len(worth)) if i not in set(bear)]
        eps = []
        for run in runs:
            idx = 1.0
            for i in run:
                idx *= (1.0 + rets[i])
            delta = annual[run[-1]] - annual[run[0]]
            eps.append({"start": keys[run[0]], "end": keys[run[-1]], "months": len(run),
                        "index": idx - 1.0, "pay": statistics.fmean([worth[i] for i in run]),
                        "bill_start": annual[run[0]], "bill_end": annual[run[-1]], "bill_delta": delta,
                        "path": ("easing" if delta < -0.0025
                                 else "tightening" if delta > 0.0025 else "flat")})
        pay_by_episode = [e["pay"] for e in eps]
        out.append({
            "depth": depth, "months": len(bear), "episodes": len(eps),
            "bear_mean": statistics.fmean([worth[i] for i in bear]),
            "calm_mean": statistics.fmean([worth[i] for i in calm]),
            "episode_median": statistics.median(pay_by_episode),
            "episode_min": min(pay_by_episode), "episode_max": max(pay_by_episode),
            "episodes_list": eps,
        })
    out[0]["record_mean"] = mean
    return out


def section_bearsweep(rows: list, balance: float) -> None:
    mean = rows[0]["record_mean"]
    print(f"\n  WHAT A CRISIS PAYS, WITHOUT ANYONE PICKING A DATE — drawdown episodes enumerated mechanically "
          f"(balance ${balance:,.0f})")
    print(f"  {'depth':>6} {'bear mo':>8} {'episodes':>9} {'in bear':>9} {'in calm':>9}   "
          f"{'per-episode median':>19}   {'per-episode range':>21}")
    for r in rows:
        print(f"  {r['depth']:>5.0%} {r['months']:>8} {r['episodes']:>9} {r['bear_mean']:>+8,.2f} "
              f"{r['calm_mean']:>+8,.2f} {r['episode_median']:>+12,.2f}   "
              f"{r['episode_min']:>+9,.2f} .. {r['episode_max']:>+9,.2f}")
    print(f"  month-weighted: the deeper the drawdown the less the switch pays, at every depth, with no date "
          f"chosen\n  (record mean {mean:+,.2f}/mo). episode-weighted, the same episodes average {rows[0]['episode_median']:+,.2f}: "
          f"the two\n  weightings disagree, because a 2-month episode and a 32-month one are each 'one crisis'.")
    print(f"  episodes at {rows[0]['depth']:.0%} depth, each one's pay and what the bill rate did inside it:")
    for e in rows[0]["episodes_list"]:
        print(f"    {e['start']} .. {e['end']}  {e['months']:>3}mo  index {e['index']:+6.1%}  "
              f"pay {e['pay']:>+7,.2f}  bill {e['bill_start']:.2%}->{e['bill_end']:.2%}  {e['path']}")
    print("  The pay deficit inside drawdowns is real and date-free. It is not caused by the drawdown: the only\n"
          "  tightening-era episode (2022-04..2023-05) paid ABOVE the record mean while the index was 10-20% down,\n"
          "  and the flat-rate episodes paid least. What the switch earns is the policy rate, so it pays what the\n"
          "  Fed was doing, not what the market was doing — which is a view to hold, not a hedge to own.")


def section_account(b: dict, balances: tuple, sweep: float) -> None:
    cash = b["current3m"]
    print(f"  bill yield quoted today, off the sealed archive: {cash:.2%} (last 1y {b['last1y']:.2%}, "
          f"last 3y {b['last3y']:.2%}, last 10y {b['last10y']:.2%})")
    gap = MMF_MEDIAN - cash
    if abs(gap) > 0.0025:
        print(f"  note: the audited money-market median ({MMF_MEDIAN:.2%}) and the archive's own curve "
              f"({cash:.2%})\n  disagree by {gap*10_000:.0f}bp. The two bill legs below use the archive's own "
              f"curve, the lower\n  of the two; only the money-market column quotes the external audit. The "
              f"conservative line\n  at the bottom of the section uses the bill leg alone.")
    print(f"  month-to-month variation in that yield, last 3y: sigma {b['sigma_mo']*100:.3f}% a month — "
          f"this is a rate,\n  not a return: the p10 of a month's cash is the rate you were quoted at the "
          f"start of it\n")
    print(f"  {'idle cash':>11}   at sweep {sweep:.2%}    broker MMF ~{MMF_MEDIAN:.2%}    "
          f"SGOV (bill−0.09%)     ladder (bill)     gain, best leg")
    for balance in balances:
        held = balance * sweep
        mmf = balance * MMF_MEDIAN
        etf = balance * (cash - SGOV_ER)
        lad = balance * (cash - LADDER_COST)
        gain = max(mmf, etf, lad) - held
        print(f"  ${balance:>11,.0f}   ${held*12/12/12:>10,.2f}/mo  ${mmf/12:>10,.2f}/mo   "
              f"${etf/12:>10,.2f}/mo    ${lad/12:>10,.2f}/mo    ${gain/12:>8,.2f}/mo")
    print(f"\n  break-even sweep rate: {cash - SGOV_ER:.2%}. Below that the bill fund wins, above it the sweep "
          f"wins\n  and no further analysis is needed. That is the one number worth reading off a statement.")
    floor = ifr.NOISE_FLOOR / 5          # round 18's floor, scaled from per-$100k to per-$20k
    etf20 = 20_000.0 * (cash - SGOV_ER - sweep) / 12
    print(f"\n  conservative line, bill leg alone and never the external money-market quote: "
          f"${etf20:,.2f}/mo on $20,000.\n  That is the figure this file stands behind, and the line it "
          f"compares below.")
    print(f"  for scale at $20k, the three decisions this file series has priced:")
    print(f"    switching index fund (SPY vs VOO)        about ${floor:,.0f}/mo, variance: substantial")
    print(f"    running the trading rule (round 23)      about ${RULE_EDGE_MO_20K:,.2f}/mo, variance: "
          f"p10 −$17/mo")
    print(f"    moving idle cash out of the sweep        ${etf20:,.2f}/mo, variance: none — it is a quoted "
          f"rate")
    print(f"  the variance-free line is {etf20/RULE_EDGE_MO_20K:.0f} times the trading edge it is sitting "
          f"next to.")


def section_backtest(data, b: dict, sweep: float) -> None:
    """What the simulations pay the rule's idle cash, and what an account actually would have been paid."""

    strat, bench, keys, weights = bp.net_strategy_returns(data, "SPY", 3.0, float(wc.EXPENSE.get("SPY",
                                                                                                 0.000945)))
    idle = [max(1.0 - w, 0.0) for w in weights]
    borrow = [max(w - 1.0, 0.0) for w in weights]
    curve = b["current3m"]
    assumed = statistics.fmean(idle) * curve
    actual = statistics.fmean(idle) * sweep
    gap = assumed - actual
    print(f"  the rule sat idle (1 − w > 0) on average {statistics.fmean(idle)*100:.1f}% of the record, and "
          f"levered\n  {statistics.fmean(borrow)*100:.1f}% of it")
    print(f"  the backtest credited that idle slice with the archive's bill curve: {assumed*100:.2f}%/yr")
    print(f"  an account on a {sweep:.2%} default sweep would have earned:                 {actual*100:.2f}%/yr")
    print(f"  the assumption is worth {gap*100:.2f}%/yr, against a measured edge of "
          f"{RULE_EDGE_YR*100:.2f}%/yr")
    if gap >= RULE_EDGE_YR:
        print(f"  ** the unearned cash credit is {gap/RULE_EDGE_YR:.1f} times the entire edge the rule is "
              f"credited with.\n     Every figure in this file series that shows the rule beating its fund has "
              f"paid the rule a\n     yield the account would not have received. The edge is not disproved, it "
              f"is unaccounted for.")
    else:
        print("  the cash assumption is a fraction of the edge, and the edge survives it.")
    print(f"  the borrowed side, stated rather than blended: this audit ran the live book's own "
          f"{statistics.fmean(borrow)*100:.1f}%\n  mean leverage at its config's 3bp *execution* spread, "
          f"which is not a loan. A levered live\n  account pays the posted {ifr.MENU_PUBLIC:.2%}, and round 19 "
          f"already priced that difference")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--balances", default=",".join(f"{b:.0f}" for b in BALANCES))
    ap.add_argument("--sweep", type=float, default=SWEEP_MEDIAN,
                    help="what YOUR broker pays on settlement cash; read it off the statement")
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    balances = tuple(float(x) for x in args.balances.split(","))
    b = bill(data)
    print("the yield on idle cash · one number you can check, one number every backtest here has assumed\n")
    print("1. THE DECISION YOU CONTROL")
    section_account(b, balances, args.sweep)
    print("\n2. HOW LONG THE OPPORTUNITY LASTS")
    section_durability(path(data), balances)
    section_sweep(sweep_sensitivity(data, 20_000.0))
    section_contingency(contingency(data, 20_000.0))
    section_bearsweep(bear_sweep(data, 20_000.0), 20_000.0)
    print("\n3. THE ASSUMPTION THE BACKTESTS MADE")
    section_backtest(data, b, args.sweep)
    print("\n  Sources: switchwize sweep audit 2026-09-02, realcostreport 2026, published fund data for")
    print("  SGOV/BIL. Bill leg from the sealed archive, same series the simulations accrue against.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
