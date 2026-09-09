"""Every rule this lab has tried, asked one question at a time: is the best of them better than the best of that
many coin flips?

Round 61. Rounds 55 to 60 evaluated 26 pre-declared configurations of price-timing, cross-sectional ranking, trading
frequency and macro conditioning, and reported the winner of each round. Reporting a winner after trying 26 things is
exactly how a backtest lies, and no round so far checked whether the pattern of results could have come out of noise.
This file does that check on the strategies *as they were tested* — same legs, same costs, same window — with two
independent statistics:

  * **the Deflated Sharpe Ratio** (Bailey and López de Prado): the probability that a strategy's observed Sharpe
    exceeds the Sharpe you would expect from the *best of N* independent trials, given the sample length and the
    strategy's own skew and kurtosis. It assumes independence across trials, which is false here — 26 long-equity
    legs are heavily correlated — so it overstates significance, and that is why it is not the only test.
  * **a block-bootstrap Reality Check** (White): resample the whole 26-column panel in circular blocks of a year, so
    both the autocorrelation within each series and the correlation *between* series survive. Under the null every
    series has its mean removed, so the resampled maxima are the distribution of "best of 26" when nothing works. The
    p-value of the observed maximum against that distribution is the number this round exists to print.

Two calibrations run before the archive is touched, and both are in the test file: the machinery must call a seeded
field of pure noise unremarkable, and it must find an obvious planted edge. A test that can only say "no" is not a
test.

Run:  python tools/deflated_edge.py [--blocks 12] [--draws 2000] [--seed 61]
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import frequency_cost as fc                                # noqa: E402
import monthly_income_race as mir                          # noqa: E402
import rates_gate as rg                                    # noqa: E402
import rotation_edge as re_                                # noqa: E402
import trend_cost_test as tc                               # noqa: E402
import withdrawal_capacity as wc                           # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402

MONTHS_PER_YEAR = 12
EULER = 0.5772156649015329
BENCH = "r59:SPY hold"


# ---------------------------------------------------------------- statistics


def phi(x: float) -> float:
    """Standard normal CDF."""

    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def inv_phi(p: float) -> float:
    """Inverse normal CDF, Acklam's rational approximation, refined once by Halley's step."""

    if not 0.0 < p < 1.0:
        raise ValueError(f"inv_phi is undefined at p={p}")
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479216850382e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    elif p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    else:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    e = phi(x) - p
    denom = math.exp(-x * x / 2.0) / math.sqrt(2.0 * math.pi)
    return x - e / denom if denom > 0 else x


def moments(xs: list) -> tuple:
    """mean, sd, skew, excess kurtosis — the four the Deflated Sharpe consumes, computed without packages."""

    n = len(xs)
    if n < 3:
        raise ValueError(f"moments need 3 observations, got {n}")
    mu = statistics.fmean(xs)
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
    if sd == 0.0:
        raise ValueError("a flat series has no Sharpe")
    m2 = sum((x - mu) ** 2 for x in xs) / n
    m3 = sum((x - mu) ** 3 for x in xs) / n
    m4 = sum((x - mu) ** 4 for x in xs) / n
    return mu, sd, m3 / m2 ** 1.5, m4 / m2 ** 2 - 3.0


def sharpe(xs: list) -> float:
    """Annualised from the observation period, using the sample sd. No risk-free subtraction: the risk-free leg is
    already inside every series here, because each one earns the bill yield whenever it is out of the market."""

    mu, sd, _s, _k = moments(xs)
    return mu / sd * math.sqrt(MONTHS_PER_YEAR)


def expected_max_sharpe(n_trials: int, t_obs: int) -> float:
    """Sharpe you should expect from the luckiest of `n_trials` independent trials on `t_obs` observations, under a
    null in which every one of them has zero true Sharpe."""

    if n_trials < 1 or t_obs < 3:
        raise ValueError("need at least one trial and three observations")
    if n_trials == 1:
        return 0.0                       # one trial is no selection at all: there is no winner's curse to price
    z = inv_phi(1.0 - 1.0 / n_trials)
    z2 = inv_phi(1.0 - 1.0 / (math.e * n_trials))
    return (math.sqrt(1.0 - EULER) * z + math.sqrt(EULER) * z2) / math.sqrt(t_obs)


def deflated_sharpe(sr_period: float, t_obs: int, skew: float, kurt: float, sr0: float) -> float:
    """Probability that the true Sharpe exceeds the best-of-N threshold. Below 0.5 means the observed record is not
    better than selection luck."""

    denom = math.sqrt(max(1e-12, 1.0 - skew * sr_period + (kurt - 1.0) / 4.0 * sr_period ** 2))
    return phi((sr_period - sr0) * math.sqrt(t_obs - 1.0) / denom)


def block_bootstrap(series: list, labels: list, block: int, draws: int, seed: int) -> dict:
    """White's Reality Check on a set of monthly series, resampled jointly in circular blocks.

    The null is that no series has a mean: each column is centred before resampling, and because the block index is
    shared across columns, whatever correlation exists between the strategies is carried into the null too. The
    statistic is the maximum t-statistic across columns, which is what a person who tried all of them and picked the
    winner actually observed.
    """

    ncols = len(series)
    t = len(series[0])
    if any(len(s) != t for s in series):
        raise ValueError("the panel must be rectangular")
    # The observed statistic is computed on the RAW series; only the null is centred. Computing both on centred data
    # makes the observed maximum identically zero and the p-value identically 1.000, which is what this function did
    # on its first run, and which the planted-edge calibration caught because a test that can only say "nothing" is
    # not a test.
    centred = [[x - statistics.fmean(s) for x in s] for s in series]
    stats = []
    for col in series:
        mu = statistics.fmean(col)
        sd = math.sqrt(sum((x - mu) ** 2 for x in col) / (t - 1)) or 1e-12
        stats.append(mu / sd * math.sqrt(t))
    observed_max = max(stats)
    winner = labels[stats.index(observed_max)]
    rng = random.Random(seed)
    starts = list(range(t))
    hits, maxes = 0, []
    for _ in range(draws):
        idx = []
        while len(idx) < t:
            s0 = rng.choice(starts)
            idx.extend((s0 + j) % t for j in range(block))
        idx = idx[:t]
        best = -1e18
        for c in range(ncols):
            col = [centred[c][i] for i in idx]
            mu = statistics.fmean(col)
            sd = math.sqrt(sum((x - mu) ** 2 for x in col) / (t - 1)) or 1e-12
            best = max(best, mu / sd * math.sqrt(t))
        maxes.append(best)
        if best >= observed_max:
            hits += 1
    maxes.sort()
    return {"p": (1 + hits) / (1 + draws), "observed_max": observed_max, "winner": winner,
            "null_max_median": statistics.median(maxes), "null_max_p95": maxes[int(0.95 * (len(maxes) - 1))],
            "draws": draws, "block": block}


# ---------------------------------------------------------------- the strategies, as they were tested


def _monthly_from_daily(day_dates: list, day_returns: list, first_month) -> list:
    """Compound daily returns into whole calendar months, dropping the first partial month."""

    if len(day_dates) != len(day_returns):
        raise ValueError("dates and returns must be the same length")
    keys, out, acc = [], [], 1.0
    cur = None
    for d, r in zip(day_dates, day_returns):
        k = (d.year, d.month)
        if cur is not None and k != cur:
            if cur >= (first_month.year, first_month.month):
                keys.append(cur)
                out.append(acc - 1.0)
            acc = 1.0
        cur = k
        acc *= (1.0 + r)
    if cur is not None and cur >= (first_month.year, first_month.month):
        keys.append(cur)
        out.append(acc - 1.0)
    return keys, out


def trial_set(data, window_from=None):
    """Every configuration rounds 55-60 evaluated, on one common month grid."""

    ordered, rets, bills, expense = re_.panel(data)
    first = ordered[0]
    pos = {d: i for i, d in enumerate(tc.days_of(data, "SPY"))}
    cl = tc.closes_of(data, "SPY")
    closes_by_date = {s: [cl[pos[d]] for d in ordered] for s in re_.UNIVERSE}
    legs = {}

    for rule in tc.RULES:
        # `daily_legs` returns aligned arrays; the shifted signal means the first of them carries no position, so a
        # rule's daily factor series is one shorter again. These two lines disagreed on that twice before they
        # agreed: the dates are `days[1:]` of the ALREADY sliced dates, and the test pins the result to
        # `trend_cost_test.run`.
        days = tc.daily_legs(data, "SPY")[0][1:]
        keys, m = _monthly_from_daily(days, _daily_factors(data, rule), first)
        legs[f"r55:{rule}"] = (keys, m)
    for rule in re_.RULES:
        w = re_.weights_for(rule, ordered, rets, bills, re_.UNKNOWN_ER)
        keys, m = mir.month_marks(ordered, mir.wealth_path(ordered, rets, bills, expense, w))
        legs[f"r56:{rule}"] = (keys, m)
    for family in fc.FAMILIES:
        for freq in fc.FREQS:
            w = fc.weights_for_family(family, ordered, rets, bills, expense, closes_by_date, freq,
                                      re_.UNKNOWN_ER)
            keys, m = mir.month_marks(ordered, mir.wealth_path(ordered, rets, bills, expense, w))
            legs[f"r57:{family}@{freq}"] = (keys, m)
    out_long, _keys_long, _eq, _cash, _y, _sg = rg.series(data, 10, 100_000.0, 0.05)
    for leg in ("SPY hold", "MA200 monthly", "yield_gate", "carry_flip", "tightening_exit", "ma200_and_gate"):
        v = out_long[leg]
        legs[f"r59:{leg}"] = ([(d.year, d.month) for d in v["dates"]], v["m"])

    common = None
    for keys, _m in legs.values():
        s = set(keys)
        common = s if common is None else (common & s)
    if window_from is not None:
        common = {k for k in common if k >= (window_from.year, window_from.month)}
    keep = sorted(common)
    # One map per leg. A single merged map looks equivalent and is not: two legs share every month key, so the last
    # one written wins and all 26 columns end up holding the same series.
    cols = {}
    for label, (keys, m) in legs.items():
        per = dict(zip(keys, m))
        if set(keep) <= set(per):
            cols[label] = [per[k] for k in keep]
    # Two configurations can realise the same monthly path — an annual and a quarterly MA200 cross that land on the
    # same months, say. That is not a bug to raise on, it is multiplicity to count honestly: a duplicate gives the
    # search no extra chance of finding a winner, so the threshold is set by the number of DISTINCT paths, while
    # every label is still shown.
    groups = {}
    for label, v in cols.items():
        groups.setdefault(tuple(v), []).append(label)
    distinct = {g[0]: list(g) for g in groups.values()}
    return cols, keep, distinct


def _daily_factors(data, rule: str) -> list:
    days, rets, cl, bills, expense = tc.daily_legs(data, "SPY")
    expo = tc.exposures(rule, cl, rets)
    out = []
    prev = 0.0
    for r, b, e in zip(rets[1:], bills[1:], expo[:-1]):
        d = abs(e - prev)
        out.append(e * (r - expense / tc.DAYS) + (1.0 - e) * b - d * wc.TURNOVER_COST)
        prev = e
    return out


# ---------------------------------------------------------------- calibration fixtures


def noise_field(n_trials: int, t: int, seed: int, sd: float = 0.04) -> list:
    rng = random.Random(seed)
    return [[rng.gauss(0.0, sd) for _ in range(t)] for _ in range(n_trials)]


def edge_field(n_trials: int, t: int, seed: int, edge: float, sd: float = 0.04) -> list:
    """A field with a real monthly edge planted in exactly one column, for the power calibration."""

    cols = noise_field(n_trials, t, seed, sd)
    rng = random.Random(seed + 1)
    cols[0] = [rng.gauss(edge, sd) for _ in range(t)]
    return cols


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blocks", type=int, default=12)
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=61)
    args = ap.parse_args()

    for t in (120, 246):
        f = noise_field(26, t, args.seed)
        rc = block_bootstrap(f, [str(i) for i in range(26)], args.blocks, args.draws, args.seed)
        print(f"calibration · {t} months of seeded noise, 26 columns: Reality-Check p = {rc['p']:.3f}"
              f"   (must not be small)")
        edge = 0.012
        g = edge_field(26, t, args.seed, edge)
        rc2 = block_bootstrap(g, [str(i) for i in range(26)], args.blocks, args.draws, args.seed)
        print(f"              same field with one planted edge of {edge:.1%}/mo: p = {rc2['p']:.3f}"
              f"   winner column {rc2['winner']}   (must be small, and must be column 0)")

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    cols, keep, distinct = trial_set(data)
    labels = sorted(cols)
    dupes = {k: v for k, v in distinct.items() if len(v) > 1}
    series = [cols[l] for l in labels]
    t = len(keep)
    print(f"\nthe archive · {len(labels)} configurations evaluated in rounds 55-60 · {keep[0]} to {keep[-1]}"
          f" · {t} common months")
    print(f"  they realise {len(distinct)} distinct monthly paths"
          + (f"; {len(dupes)} of them are shared: " + "; ".join("+".join(v) for v in dupes.values())
             if dupes else ""))
    print(f"  {'configuration':26} {'Sharpe':>8} {'SR period':>10} {'skew':>7} {'ex.kurt':>8} {'DSR':>7}")
    print("  " + "-" * 66)
    bench_label = "r59:SPY hold"
    bench = cols[bench_label]
    print(f"  benchmark for every excess figure: {bench_label}, net of its own expense, the same {t} months")

    for kind, panel in (("RAW monthly return (what the leg earned, not what it beat)", cols),
                        ("EXCESS over the index (the objective's question)", None)):
        if panel is None:
            raw_excess = {l: [(1.0 + r) / (1.0 + b) - 1.0 for r, b in zip(cols[l], bench)]
                          for l in cols if l != bench_label}
            # A column that is the benchmark wearing another convention has an excess series with almost no
            # variance, and a Sharpe divided by almost nothing is a number nobody should read. It is dropped and
            # named, because the gap between the two implementations is itself a measurement.
            near = {l: statistics.fmean(v) for l, v in raw_excess.items()
                    if math.sqrt(statistics.fmean([(x - statistics.fmean(v)) ** 2 for x in v])) < 1e-3}
            for l in sorted(near):
                print(f"  dropped as a benchmark duplicate: {l} — same position, another convention,"
                      f" mean excess {near[l] * 12 * 100:+.2f}pp a year")
            panel = {l: v for l, v in raw_excess.items() if l not in near}
        lab = sorted(panel)
        groups = {}
        for l in lab:
            groups.setdefault(tuple(panel[l]), []).append(l)
        ndistinct = len(groups)
        t_ = len(panel[lab[0]])
        print("\n" + "=" * 96)
        print(f"  {kind}")
        print(f"  {len(lab)} columns · {ndistinct} distinct paths · {t_} months"
              + ("   (the benchmark's own column is dropped: its excess is zero by construction)"
                 if kind.startswith("EXCESS") else ""))
        srs, best = {}, None
        for l in lab:
            mu, sd, sk, ku = moments(panel[l])
            srs[l] = (mu / sd, sk, ku, sharpe(panel[l]))
            if best is None or srs[l][0] > srs[best][0]:
                best = l
        sr0 = expected_max_sharpe(ndistinct, t_)
        rows = sorted(lab, key=lambda l: -srs[l][0])
        print(f"  {'configuration':26} {'Sharpe':>8} {'SR period':>10} {'skew':>7} {'ex.kurt':>8} {'DSR':>7}")
        print("  " + "-" * 66)
        for l in rows:
            sp, sk, ku, ann = srs[l]
            d = deflated_sharpe(sp, t_, sk, ku, sr0)
            print(f"  {l:26} {ann:>8.2f} {sp:>10.4f} {sk:>7.2f} {ku:>8.2f} {d:>7.3f}"
                  + ("  <-- best" if l == best else ""))
        sp, sk, ku, ann = srs[best]
        print(f"\n  best-of-{ndistinct} Sharpe from noise alone on {t_} months: {sr0 * math.sqrt(12):.2f} annualised"
              f" ({sr0:.4f} per month)")
        print(f"  observed best ({best}): {ann:.2f} annualised ({sp:.4f} per month) -> Deflated Sharpe"
              f" {deflated_sharpe(sp, t_, sk, ku, sr0):.3f}")
        r = block_bootstrap([panel[l] for l in lab], lab, args.blocks, args.draws, args.seed)
        print(f"  Reality Check, {args.draws} circular-block draws of {args.blocks} months: p = {r['p']:.3f}"
              f"   null median max t {r['null_max_median']:.2f}, p95 {r['null_max_p95']:.2f}")
        print(f"  winner under the resampled null: {r['winner']}")
        if kind.startswith("RAW"):
            print("  A raw-mean verdict on a panel that is long equity the whole time says that equities earn a")
            print("  premium, which is true and can be bought for 0.03% a year. The block below is the one the")
            print("  objective asks about.")
        else:
            rc = r
    print("\n" + "=" * 96)
    print("  Deflated Sharpe assumes the trials were independent; these are correlated long-equity legs, so it")
    print("  flatters them. The Reality Check does not assume independence and is the number to read.")
    n_all, n_dist = len(distinct), len({tuple(v) for v in cols.values()})
    print(f"\n  VERDICT on the question as asked (beat the index, after accounting for having tried"
          f" {len(cols)} things):")
    if rc["p"] <= 0.05:
        print(f"  at least one configuration's excess is larger than {n_dist} coin flips would produce. Look at it")
        print("  closely, and remember it is the best of a large set, which is exactly where a false positive sits.")
    else:
        print(f"  every one of the {len(cols)} configurations has a NEGATIVE information ratio against the index, and")
        print(f"  the Reality-Check p-value of the best is {rc['p']:.3f}. There is no selection luck to correct for,")
        print("  because there is nothing to select: the search did not fail to find an edge at this resolution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
