#!/usr/bin/env python3
"""BA-007: the cross-sectional screen engine — the charter's locked mechanics, computed and never typed in.

The charter (`docs/strategies/BA-007.md`) was pre-registered before any signal touched the real archive. This file implements exactly what
it locks and nothing it does not: a point-in-time top-30-by-volume universe with a 60-day history floor, two signals (7-day cross-sectional
momentum; 72-hour summed funding carry), weekly dollar-neutral tercile books at gross 1.0, fees on traded notional both sides, funding
charged at realized rates daily, delistings closed at their last observed close, and the four controls the gates accuse the signal with
(reversed ranks, 20 seeded scrambles, gross-minus-net, single legs). Evaluation periods truncate the panel before anything is computed —
the development window never sees a validation bar, which is the property `test_ba007.py` pins down.

The engine separates *preparation* (each week's eligible universe and each signal's scores, computed once per week per signal) from
*bookkeeping* (each book consumes the same preparation), so the scrambled and reversed controls are the same arithmetic as the candidate
with the ranks changed and nothing else — the same property that made the equity family's mirror-image controls damning.

What this file is not: a place where a rule gets nudged until a table clears. The charter's §4 declares two signals, one construction, one
fee grid as the whole family; the verdict is arithmetic on artifacts, and Inconclusive kills the candidate as surely as FAIL.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

PERPS = ROOT / "data" / "perps" / "current"
BACKTESTS = ROOT / "data" / "perps" / "backtests"
UNIVERSE_N = 30                     # charter §3
HISTORY_FLOOR_DAYS = 60
VOLUME_WINDOW_DAYS = 30
MIN_ELIGIBLE = 12
MOMENTUM_DAYS = 7                   # charter §4 signal 1
CARRY_HOURS = 72                    # charter §4 signal 2
GROSS = 1.0
FEE_BPS_PRIMARY = 5.0               # charter §6
FEE_BPS_STRESS = 10.0
BLOCK_LENGTH = 10                   # charter §8 G1
BOOTSTRAP_RESAMPLES = 2_000
SCRAMBLE_SEEDS = tuple(range(20))   # charter §8 G3
ANNUALIZATION_DAYS = 365

DEVELOPMENT = (date(2020, 2, 1), date(2022, 12, 31))
VALIDATION = (date(2023, 1, 1), date(2024, 12, 31))
SEALED = (date(2025, 1, 1), None)   # never opened by this charter


# ---------------------------------------------------------------- the panel ---------------------------------------------------------------

def load_panel(directory: Path = PERPS) -> tuple[dict, dict, dict]:
    """The spine's two CSVs into close / quote-volume / daily-funding matrices: {symbol: {date: value}}.

    A funding event's rate is the amount paid for holding through that event, whatever the event's cadence, so a symbol's daily funding is
    the plain sum of that day's event rates — the engine never averages across cadences, because holding through three events at 0.01%
    costs 0.03% that day no matter how the venue slices the hours.
    """

    closes: dict[str, dict[date, float]] = {}
    volumes: dict[str, dict[date, float]] = {}
    with (directory / "perps_daily.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            day = date.fromisoformat(row["date"])
            sym = row["symbol"]
            closes.setdefault(sym, {})[day] = float(row["close"])
            volumes.setdefault(sym, {})[day] = float(row["quote_volume"])
    funding: dict[str, dict[date, float]] = {}
    with (directory / "funding_events.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            day = datetime.fromisoformat(row["ts_utc"].replace("Z", "+00:00")).date()
            funding.setdefault(row["symbol"], {})[day] = \
                funding.get(row["symbol"], {}).get(day, 0.0) + float(row["rate"])
    return closes, volumes, funding


def weekly_rebalance_dates(sessions: list[date]) -> list[date]:
    """The first served session of each ISO week, ascending — one decision a week, on data that closed before the position exists."""

    seen: dict[tuple[int, int], date] = {}
    for day in sessions:
        key = day.isocalendar()[:2]
        if key not in seen or day < seen[key]:
            seen[key] = day
    return sorted(seen.values())


def sessions_in(closes: dict[str, dict[date, float]], period: tuple[date, date | None]) -> list[date]:
    """Every session the panel serves inside the period; the boundary truncates before anything is computed."""

    start, end = period
    union: set[date] = set()
    for series in closes.values():
        union |= {d for d in series if d >= start and (end is None or d <= end)}
    return sorted(union)


# ---------------------------------------------------------------- preparation ------------------------------------------------------------

def momentum(series: dict[date, float], t: date) -> float | None:
    """Total close-to-close return over the MOMENTUM_DAYS calendar days ending at t, on observed closes; silence is not a price."""

    if t not in series:
        return None
    start = t - timedelta(days=MOMENTUM_DAYS)
    priors = sorted(d for d in series if start <= d < t)
    if not priors:
        return None
    return series[t] / series[priors[-1]] - 1.0


def carry_sum(funding: dict[date, float], t: date) -> float:
    """Summed realized funding over the trailing CARRY_HOURS whole UTC days ending at t, whatever cadence the venue pays at."""

    window_start = t - timedelta(days=CARRY_HOURS // 24 - 1)              # (t-72h, t] on the daily grid: t-2, t-1, t
    return sum(v for d, v in funding.items() if window_start <= d <= t)


def eligible_universe(closes: dict[str, dict[date, float]], volumes: dict[str, dict[date, float]],
                      t: date) -> list[str]:
    """Charter §3: observed close at t, HISTORY_FLOOR_DAYS of life, ranked by trailing VOLUME_WINDOW_DAYS median quote volume, top UNIVERSE_N."""

    scored: list[tuple[float, str]] = []
    for sym, series in closes.items():
        if t not in series:
            continue
        if min(series) > t - timedelta(days=HISTORY_FLOOR_DAYS):
            continue
        window = [volumes[sym][d] for d in series if t - timedelta(days=VOLUME_WINDOW_DAYS) < d <= t]
        if not window:
            continue
        scored.append((-statistics.median(window), sym))
    scored.sort()
    return [sym for _, sym in scored[:UNIVERSE_N]]


def prepare_weeks(closes: dict[str, dict[date, float]], volumes: dict[str, dict[date, float]],
                  funding: dict[str, dict[date, float]], sessions: list[date],
                  rebalances: list[date], signal_name: str) -> list[dict]:
    """Each rebalance week's universe and scores, computed once: the candidate and every control consume the same preparation."""

    if signal_name not in ("MOM", "CARRY"):
        raise SystemExit(f"unknown signal {signal_name!r}; the charter declares MOM and CARRY and nothing else")
    weeks = []
    for day in rebalances:
        universe = eligible_universe(closes, volumes, day)
        scores: dict[str, float] = {}
        for sym in universe:
            value = momentum(closes[sym], day) if signal_name == "MOM" else carry_sum(funding.get(sym, {}), day)
            if value is not None:
                scores[sym] = value
        if len(scores) >= MIN_ELIGIBLE:
            weeks.append({"date": day, "universe": sorted(scores), "scores": scores})
    return weeks


def terciles(universe: list[str], scores: dict[str, float], reverse: bool = False,
             scramble_seed: int | None = None) -> tuple[list[str], list[str]]:
    """Long tercile / short tercile of the ranked universe. Reversed swaps the sides; a scramble permutes the ranks before cutting.

    The scrambled book is not a different construction: it is this construction fed a ranking known to carry no information, which is
    exactly what the G3 gate needs to accuse the signal with.
    """

    ranked = list(universe)
    if scramble_seed is not None:
        rng = random.Random(scramble_seed)
        order = ranked[:]
        rng.shuffle(order)
        scores = {name: -i for i, name in enumerate(order)}
    by_score = sorted(ranked, key=lambda s: scores[s], reverse=True)
    k = max(1, len(by_score) // 3)
    top, bottom = by_score[:k], by_score[len(by_score) - k:]
    return (bottom, top) if reverse else (top, bottom)


# ---------------------------------------------------------------- the book ----------------------------------------------------------------

def run_book(weeks: list[dict], closes: dict[str, dict[date, float]], funding: dict[str, dict[date, float]],
             sessions: list[date], fee_bps: float, leg: str = "both",
             reverse: bool = False, scramble_seed: int | None = None) -> dict:
    """One book's daily record over the period: gross spread, funding, fees, turnover — the charter's construction, nothing else."""

    if leg not in ("both", "long", "short"):
        raise SystemExit(f"unknown leg {leg!r}; the charter prices both, long-only and short-only as diagnostics")
    rebalance_on = {week["date"]: week for week in weeks}
    weights: dict[str, float] = {}
    daily: list[dict] = []
    pending_fee = 0.0
    closed_symbols: set[str] = set()

    for day in sessions:
        gross_ret = funding_ret = 0.0
        dead = []
        for sym, weight in weights.items():
            series = closes[sym]
            prior = max((d for d in series if d < day), default=None)
            if day not in series or prior is None:
                dead.append(sym)                                            # delisted mid-week: closed at its last close
                continue
            gross_ret += weight * (series[day] / series[prior] - 1.0)
            funding_ret += weight * funding.get(sym, {}).get(day, 0.0)
        for sym in dead:
            del weights[sym]                                                # the notional sits in cash until the next rebalance
            closed_symbols.add(sym)

        week = rebalance_on.get(day)
        if week is not None:
            long_side, short_side = terciles(week["universe"], week["scores"],
                                             reverse=reverse, scramble_seed=scramble_seed)
            k_long, k_short = max(1, len(long_side)), max(1, len(short_side))
            new_weights: dict[str, float] = {}
            if leg in ("both", "long"):
                for sym in long_side:
                    new_weights[sym] = new_weights.get(sym, 0.0) + (GROSS / 2) / k_long
            if leg in ("both", "short"):
                for sym in short_side:
                    new_weights[sym] = new_weights.get(sym, 0.0) - (GROSS / 2) / k_short
            if leg == "long":
                new_weights = {sym: GROSS / k_long for sym in long_side}
            elif leg == "short":
                new_weights = {sym: -GROSS / k_short for sym in short_side}
            turnover = sum(abs(new_weights.get(s, 0.0) - weights.get(s, 0.0))
                           for s in set(new_weights) | set(weights))
            pending_fee += turnover * fee_bps / 10_000
            weights = new_weights

        net_ret = gross_ret - funding_ret - pending_fee
        daily.append({"date": day, "gross": gross_ret, "funding": funding_ret,
                      "fees": pending_fee, "net": net_ret, "positions": len(weights)})
        pending_fee = 0.0

    return _summarize(daily, fee_bps, leg, reverse, scramble_seed, closed_symbols)


def _summarize(daily: list[dict], fee_bps: float, leg: str, reverse: bool,
               scramble_seed: int | None, closed_symbols: set[str]) -> dict:
    """The period's arithmetic: annualized means, the bootstrap interval the gates read, drawdown, and where the gross went."""

    if not daily:
        return {"fee_bps": fee_bps, "leg": leg, "days": 0}
    nets = [row["net"] for row in daily]
    mean_daily = statistics.fmean(nets)
    annualized = mean_daily * ANNUALIZATION_DAYS
    low, high = bootstrap_interval(nets)
    equity, peak, max_dd = 1.0, 1.0, 0.0
    for value in nets:
        equity *= 1.0 + value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1.0)
    vol = statistics.pstdev(nets)
    return {
        "fee_bps": fee_bps, "leg": leg, "reverse": reverse, "scramble_seed": scramble_seed,
        "days": len(daily), "first": daily[0]["date"].isoformat(), "last": daily[-1]["date"].isoformat(),
        "annualized_net": annualized, "annualized_gross": statistics.fmean(r["gross"] for r in daily) * ANNUALIZATION_DAYS,
        "funding_annualized": statistics.fmean(r["funding"] for r in daily) * ANNUALIZATION_DAYS,
        "fees_paid": sum(r["fees"] for r in daily),
        "annualized_vol": vol * (ANNUALIZATION_DAYS ** 0.5),
        "sharpe": annualized / (vol * (ANNUALIZATION_DAYS ** 0.5)) if vol else 0.0,
        "max_drawdown": max_dd,
        "bootstrap_low": low, "bootstrap_high": high,
        "closed_symbols": sorted(closed_symbols),
        "daily": daily,
    }


def bootstrap_interval(nets: list[float], block: int = BLOCK_LENGTH,
                       resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 7) -> tuple[float, float]:
    """Stationary-block-bootstrap 95% interval of the annualized mean — the honest counterweight to a point estimate. Seeded: deterministic."""

    rng = random.Random(seed)
    n = len(nets)
    if n < block * 2:
        return (float("nan"), float("nan"))
    means = []
    for _ in range(resamples):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.randrange(n)
            length = max(1, round(rng.gauss(block, block / 2)))
            for offset in range(length):
                sample.append(nets[(start + offset) % n])
                if len(sample) >= n:
                    break
        means.append(statistics.fmean(sample) * ANNUALIZATION_DAYS)
    means.sort()
    return (means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1])


# ---------------------------------------------------------------- the verdict ----------------------------------------------------------------

def verdict(dev: dict, val: dict, reversed_dev: dict, scrambled_means: list[float],
            stress_dev: dict, stress_val: dict) -> dict:
    """Charter §8: G1..G4 computed from artifacts. Inconclusive kills the candidate as surely as FAIL; there is no third window."""

    def clears_g1(book: dict) -> bool:
        return book.get("annualized_net", float("nan")) > 0 and book.get("bootstrap_low", float("nan")) > 0

    checks = {
        "G1_dev_bootstrap_excludes_zero": clears_g1(dev),
        "G1_val_bootstrap_excludes_zero": clears_g1(val),
        "G3_reversed_loses_in_dev": reversed_dev.get("annualized_net", float("inf")) < dev.get("annualized_net", float("-inf")),
        "G3_scrambled_median_loses_in_dev": dev.get("annualized_net", float("-inf")) > (statistics.median(scrambled_means)
                                                                                       if scrambled_means else float("inf")),
        "G4_stress_holds_in_dev": clears_g1(stress_dev),
        "G4_stress_holds_in_val": clears_g1(stress_val),
    }
    return {"checks": checks, "verdict": "PASS" if all(checks.values()) else "FAIL"}


def evaluate_signal(signal_name: str, closes, volumes, funding) -> dict:
    """One signal, one construction, both seen periods, every control: the charter's whole family for that signal."""

    out: dict = {"signal": signal_name}
    for period_name, period in (("development", DEVELOPMENT), ("validation", VALIDATION)):
        sessions = sessions_in(closes, period)
        rebalances = weekly_rebalance_dates(sessions)
        weeks = prepare_weeks(closes, volumes, funding, sessions, rebalances, signal_name)
        base = run_book(weeks, closes, funding, sessions, FEE_BPS_PRIMARY)
        stress = run_book(weeks, closes, funding, sessions, FEE_BPS_STRESS)
        reversed_book = run_book(weeks, closes, funding, sessions, FEE_BPS_PRIMARY, reverse=True)
        scrambled_means = [run_book(weeks, closes, funding, sessions, FEE_BPS_PRIMARY,
                                    scramble_seed=seed)["annualized_net"] for seed in SCRAMBLE_SEEDS]
        out[period_name] = {"base": base, "stress": stress, "reversed": reversed_book,
                            "scrambled_median": statistics.median(scrambled_means),
                            "scrambled_all": scrambled_means}
        row = base
        print(f"  {period_name:<11} {signal_name:<5} net {row['annualized_net']:+.2%}/yr "
              f"[{row['bootstrap_low']:+.2%}, {row['bootstrap_high']:+.2%}] sharpe {row['sharpe']:.2f} "
              f"dd {row['max_drawdown']:+.1%} | stress {stress['annualized_net']:+.2%} "
              f"reversed {reversed_book['annualized_net']:+.2%} scrambled median {statistics.median(scrambled_means):+.2%}")
    out["verdict"] = verdict(out["development"]["base"], out["validation"]["base"],
                             out["development"]["reversed"], out["development"]["scrambled_all"],
                             out["development"]["stress"], out["validation"]["stress"])
    print(f"  {signal_name} verdict: {out['verdict']['verdict']} "
          f"({sum(out['verdict']['checks'].values())}/{len(out['verdict']['checks'])} gates)")
    return out


def main() -> int:
    closes, volumes, funding = load_panel()
    results = {name: evaluate_signal(name, closes, volumes, funding) for name in ("MOM", "CARRY")}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = BACKTESTS / stamp
    target.mkdir(parents=True)
    slim = json.loads(json.dumps(results, default=str))                      # datetimes become strings; sizes stay readable
    for result in slim.values():                                             # the daily series live in the CSVs, not the manifest
        for period_name in ("development", "validation"):
            result[period_name]["base"].pop("daily", None)
            result[period_name]["stress"].pop("daily", None)
            result[period_name]["reversed"].pop("daily", None)
    (target / "metrics.json").write_text(json.dumps(slim, indent=2, sort_keys=True) + "\n")
    for name, result in results.items():
        for period_name in ("development", "validation"):
            daily = result[period_name]["base"]
            with (target / f"daily-{period_name}-{name}-base.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "gross", "funding", "fees", "net", "positions"])
                writer.writeheader()
                writer.writerows(result[period_name]["base"].get("daily", []))
    print(f"  artifacts: {target}")
    print("  verdicts are computed from these artifacts, never typed in (charter §8)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
