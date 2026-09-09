#!/usr/bin/env python3
"""BA-005: BTC-USD above its own 200-day mean, monthly, against plain QQQ and plain VOO on the same months.

The spec (`docs/strategies/BA-005.md`) is locked and this file does not re-litigate it: one asset, one average length, one frequency, one
window, a verdict decided by the ruin promise rather than the terminal. What this file contributes before a fee is known is the shape of the
answer that needs no fee:

    terminal(fee) = terminal(0) x (1 - fee) ** switch_events

Each switch of the position is one trade of the whole sleeve, so it costs one taker fee; a round trip is two switches. The whole fee
sensitivity of this rule is therefore carried by a single number — the switch count — and the fee at which the rule ties plain QQQ falls out
of it in closed form. That is worth printing without a fee record, because it converts "we need your fee tier" into "your tier has to beat
N bps, and here is how fast the money leaks past that".

With a current Coinbase fee record (`tools/venue_fees.py ingest …`) this prints the verdict the spec demands. Without one it prints
everything that does not depend on the fee, says **NO VERDICT** in the same breath, and exits 3: it will not grade on an assumption, and it
will not claim the missing number is immaterial (rule 103; rule 105's lesson that "immaterial" is a statement about a tolerance).

The cost asymmetry is deliberate and runs against this file's own candidate: the index legs are held commission-free at a broker and pay
nothing to enter, while the crypto leg pays Coinbase taker on every switch. No expense ratio is added on top of either, because the corpus's
`tr_close` column is a total-return series computed on NAV, which is already net of the fund's expenses.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import withdrawal_capacity as wc                                               # noqa: E402  corpus paths and the monthly convention
import monthly_income_race as mir                                              # noqa: E402  the archive's own definition of an affordable bill
import venue_fees                                                              # noqa: E402  the fee, or the refusal
from boring_alpha.data.csv_loader import load_csv_market_data                   # noqa: E402

CRYPTO_DIR = ROOT / "data" / "crypto" / "current"
CRYPTO_FILE = CRYPTO_DIR / "crypto_daily.csv"
SPEC = ROOT / "docs" / "strategies" / "BA-005.md"

#: The locked numbers, read out of the spec rather than duplicated. If the spec is re-locked, this file follows it or fails loudly.
SPEC_TEXT = SPEC.read_text()
_window = re.search(r"\*\*Window\*\*:\s*(\d{4}-\d{2}-\d{2})\D*(\d{4}-\d{2}-\d{2})", SPEC_TEXT, re.S)
SMA_DAYS = int(re.search(r"mean of the last (\d+) daily closes", SPEC_TEXT).group(1))
PAIR = re.search(r"\*\*Instrument\*\*:\s*(\w{3}-\w{3})", SPEC_TEXT).group(1)
WINDOW_START = date.fromisoformat(_window.group(1)) if _window else None
DD_LIMIT = float(re.search(r"no worse than\s+(\d(?:\.\d+)?)[x×]", SPEC_TEXT).group(1))

FEE_GRID_BPS = (0.0, 10.0, 30.0, 60.0, 90.0, 120.0, 180.0, 240.0)

#: Step 3's horizon. Ten years is the archive's headline convention, but 123 months of crypto history holds four 10-year windows,
#: and four windows is not a distribution. Five years is the longest horizon this record can be honest about.
RUIN_YEARS = 5
P_FAIL_MAX = 0.05
CAPITAL = 100_000.0                                                             # scale-parametric: every figure is per $100k paid in
BARS = ("QQQ", "VOO")


def crypto_closes(pair: str) -> dict[date, float]:
    if not CRYPTO_FILE.is_file():
        raise SystemExit(f"no crypto archive at {CRYPTO_FILE}; run tools/fetch_crypto.py before BA-005 can be priced")
    out: dict[date, float] = {}
    with CRYPTO_FILE.open() as handle:
        for row in csv.DictReader(handle):
            if row["pair"] == pair:
                out[date.fromisoformat(row["date"])] = float(row["close"])
    if not out:
        raise SystemExit(f"the crypto archive holds no {pair} candles, so BA-005 has no instrument to price")
    return out


def above_sma(closes: dict[date, float], as_of: date, span: int | None = None) -> bool:
    """The locked signal: the close at `as_of` against the mean of the `span` closes ending there.

    A record too short to have `span` closes is not a bearish reading, it is missing information, so the rule holds cash. The report prints
    how many months that cost, because a rule whose first two years are silence is being graded on fewer bets than it claims.
    """

    span = span or SMA_DAYS
    days = sorted(d for d in closes if d <= as_of)
    if len(days) < span or as_of not in closes:
        return False
    return closes[as_of] > sum(closes[d] for d in days[-span:]) / span


def grid(md, start: date) -> tuple[list[date], list[float], list[float]]:
    """The months the whole test is priced on: the equity legs' completed months inside the locked window.

    Reusing `withdrawal_capacity.monthly_complete` is deliberate. The archive's own convention already knows how to drop a trailing
    calendar month that has not finished (round 47's defect), and a crypto test that invented its own month grid would be graded on a
    different set of months from the index it is supposed to beat.
    """

    qqq = {day: md.bar(day, "QQQ").close for day in md.symbol_dates["QQQ"]}
    returns, rates, keys = wc.monthly_complete(qqq, md.cash_factors, md.dates[-1])
    keep = [(r, c, k) for r, c, k in zip(returns, rates, keys) if k >= start]
    rets, cash_rates, months = [x[0] for x in keep], [x[1] for x in keep], [x[2] for x in keep]
    return months, rets, cash_rates


def run(months: list[date], btc: dict[date, float], cash_rates: list[float], fee_bps: float,
        qqq_returns: list[float], span: int | None = None) -> dict:
    """Walk the locked rule monthly on the shared grid. The fee is charged once per switch, on the whole sleeve, and nowhere else."""

    fee = fee_bps / 10_000.0
    wealth = CAPITAL
    in_btc = False
    switches = 0
    months_in_btc = 0
    warm_up = 0
    peak, worst = wealth, 0.0
    path, returns = [], []
    previous_wealth = wealth
    for i, month in enumerate(months):
        previous = months[i - 1] if i else None
        span = span or SMA_DAYS
        signal = above_sma(btc, previous, span) if previous else False
        if previous and len([d for d in btc if d <= previous]) < span:
            warm_up += 1
            signal = False
        if previous and signal != in_btc:
            switches += 1
            wealth *= (1.0 - fee)
            in_btc = signal
        if signal:
            months_in_btc += 1
            wealth *= btc[month] / btc[previous] if previous and month in btc and previous in btc else 1.0
        else:
            wealth *= 1.0 + cash_rates[i]
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1.0)
        path.append((month, wealth))
        returns.append(wealth / previous_wealth - 1.0)
        previous_wealth = wealth
    years = max(1e-9, (months[-1] - months[0]).days / 365.25)
    fees_paid = CAPITAL * (1.0 - (1.0 - fee) ** switches) if fee > 0 else 0.0
    return {"months": len(months), "switches": switches, "round_trips": switches / 2.0, "months_in_btc": months_in_btc,
            "warm_up": warm_up, "terminal": wealth, "cagr": (wealth / CAPITAL) ** (1 / years) - 1.0,
            "max_dd": -worst, "fees_paid": fees_paid, "fee_bps": fee_bps, "path": path, "returns": returns}


def hold(qqq_returns: list[float], months: list[date]) -> dict:
    """The bar as the objective states it: buy the fund at the first mark, hold it, pay nothing to do so."""

    wealth, peak, worst = CAPITAL, CAPITAL, 0.0
    path = []
    for r in qqq_returns:
        wealth *= 1.0 + r
        path.append(wealth)
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1.0)
    years = max(1e-9, (months[-1] - months[0]).days / 365.25)
    return {"terminal": wealth, "cagr": (wealth / CAPITAL) ** (1 / years) - 1.0, "max_dd": -worst,
            "returns": list(qqq_returns), "path": path}


def breakeven_fee(gross_terminal: float, bar_terminal: float, switches: int) -> float | None:
    """The taker fee, in bps, at which this rule's terminal equals the bar's. Nothing above it can be made to work by hoping."""

    if switches <= 0 or gross_terminal <= bar_terminal:
        return None
    return (1.0 - (bar_terminal / gross_terminal) ** (1.0 / switches)) * 10_000.0


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def report_lines(md, fee: float | None, record: dict | None, quiet: bool = False) -> tuple[list[str], int]:
    """The whole output, as lines plus the exit code, so a test can read the verdict without owning a terminal."""

    btc = crypto_closes(PAIR)
    months, qqq_returns, cash_rates = grid(md, WINDOW_START)
    if len(months) < 12:
        raise SystemExit(f"only {len(months)} completed months in the locked window; BA-005 needs months to fail in")
    voo_returns = [md.bar(months[i], "VOO").close / md.bar(months[i - 1], "VOO").close - 1.0
                   for i in range(1, len(months))]

    out: list[str] = []
    p = out.append
    gross = run(months, btc, cash_rates, 0.0, qqq_returns)
    qqq, voo = hold(qqq_returns, months), hold(voo_returns, months)
    held = hold([btc[months[i]] / btc[months[i - 1]] - 1.0 for i in range(1, len(months))], months)
    p(f"  BA-005 · {PAIR} above its {SMA_DAYS}-day mean, monthly · {months[0]} to {months[-1]} · {gross['months']} months")
    p(f"    inputs: crypto {sha(CRYPTO_FILE)} · equity {sha(wc.SNAPSHOT)} · spec {sha(SPEC)} · "
      f"drawdown limit {DD_LIMIT:g}x the bar's")
    p(f"    gross (fee = 0, which is not a possible world): ${gross['terminal']:,.0f} on ${CAPITAL:,.0f}, CAGR {gross['cagr']:+.2%}, "
      f"max DD {gross['max_dd']:.1%}")
    p(f"      held crypto {gross['months_in_btc']}/{gross['months']} months · {gross['switches']} switches "
      f"({gross['round_trips']:.1f} round trips) · {gross['warm_up']} months lost to the {SMA_DAYS}-day warm-up")
    p(f"      the grid's first month carries no signal — the archive's monthly() keys each month by its first session, so the first row has")
    p("      no prior mark to read a signal from and earns cash. One month of a "
      f"{gross['months']}-month test, stated rather than quietly priced.")
    p(f"    the bar on the same months: QQQ ${qqq['terminal']:,.0f} ({qqq['cagr']:+.2%}, DD {qqq['max_dd']:.1%}) · "
      f"VOO ${voo['terminal']:,.0f} ({voo['cagr']:+.2%}, DD {voo['max_dd']:.1%}) [P0]")
    p(f"    and simply holding the asset, no signal at all: ${held['terminal']:,.0f} ({held['cagr']:+.2%}, DD {held['max_dd']:.1%}) — "
      f"the timing is worth {gross['terminal'] / held['terminal'] - 1.0:+.1%} over the decade of holding, and its drawdown is "
      f"{held['max_dd'] - gross['max_dd']:.1%} points shallower")
    if gross["terminal"] <= qqq["terminal"]:
        p("    the rule trails plain QQQ at a fee of zero, so no fee tier can rescue it. The grid below is for the record.")
    be_qqq = breakeven_fee(gross["terminal"], qqq["terminal"], gross["switches"])
    be_voo = breakeven_fee(gross["terminal"], voo["terminal"], gross["switches"])
    if be_qqq is not None:
        p(f"    break-even taker fee: {be_qqq:,.0f} bps to tie QQQ · "
          + (f"{be_voo:,.0f} bps to tie VOO" if be_voo is not None else "it ties VOO only by not trading"))
    elif gross["terminal"] > qqq["terminal"]:
        p("    break-even taker fee: none — it stays ahead of QQQ at every fee below 100% per side")

    if not quiet:
        p("")
        p("    taker bps    terminal      CAGR     max DD     vs QQQ   fees paid     note")
        for bps in FEE_GRID_BPS:
            net = run(months, btc, cash_rates, bps, qqq_returns)
            note = "  <- the fee on record" if fee is not None and abs(bps - fee) < 1e-9 else ""
            p(f"    {bps:>9.0f}   ${net['terminal']:>9,.0f}  {net['cagr']:+7.2%}   {net['max_dd']:6.1%}   "
              f"{net['terminal'] / qqq['terminal'] - 1.0:+6.1%}   {net['fees_paid'] / CAPITAL:6.1%}{note}")

    ruin = ruin_section(months, qqq_returns, gross, held, fee,
                            run(months, btc, cash_rates, fee, qqq_returns) if fee is not None else None)
    p("")
    for line in ruin["lines"]:
        p("    " + line)

    # A gate that fails at a fee of zero fails at every fee the venue could charge, because fees only ever take money out of a path.
    # Refusing to grade is for when the missing number is the one that decides; refusing when it cannot decide is just hiding (rule 106).
    best_dd = min(run(months, btc, cash_rates, b, qqq_returns)["max_dd"] for b in FEE_GRID_BPS)
    gates = []
    if best_dd > DD_LIMIT * qqq["max_dd"]:
        gates.append(f"the deepest drawdown anywhere on the grid is {best_dd:.1%} against {DD_LIMIT * qqq['max_dd']:.1%} allowed "
                     f"({DD_LIMIT:g}x QQQ's {qqq['max_dd']:.1%})")
    if ruin["ours_worse"]:
        gates.append(f"at QQQ's own affordable bill of ${ruin['bill']:,.0f}/mo it fails in "
                     f"{ruin['ours']['p_fail']:.0%} of {ruin['windows']} windows against QQQ's {ruin['bar']['p_fail']:.0%} "
                     f"(one window of {ruin['windows']} is {100.0 / ruin['windows']:.1f} points, so read that pair cautiously) "
                     f"while being halved at least once in {ruin['ours']['p_erase']:.0%} of them against QQQ's "
                     f"{ruin['bar']['p_erase']:.0%}")
    if gates:
        p(f"\n    FAIL, and no fee record can change it: " + "; ".join(gates) + ".")
        p("    The terminal is not in doubt — break-even sits at "
          + (f"{be_qqq:,.0f} bps, far above any venue could charge" if be_qqq else "an unreadable fee grid")
          + " — which is exactly why the spec locked the failure condition to the ruin promise and not to the terminal: this asset's "
            "decade was spectacular, and the question the objective asks is whether it can be *held* monthly without being wiped out.")
        return out, 1

    if fee is None:
        p("\n    NO VERDICT — BA-005 prices a trade only against a current Coinbase fee record, and there is none.")
        for line in str(_refusal()).splitlines():
            p("   " + line)
        return out, 3

    net = run(months, btc, cash_rates, fee, qqq_returns)
    checks = [("terminal above plain QQQ", net["terminal"] > qqq["terminal"], f"${net['terminal']:,.0f} vs ${qqq['terminal']:,.0f}"),
              (f"max drawdown within {DD_LIMIT:g}x QQQ's", net["max_dd"] <= DD_LIMIT * qqq["max_dd"],
               f"{net['max_dd']:.1%} against {DD_LIMIT * qqq['max_dd']:.1%} allowed"),
              ("fee drag stated, not hidden", True, f"{net['fees_paid'] / CAPITAL:.1%} of paid in at {fee:.0f} bps per switch")]
    passed = all(c[1] for c in checks)
    p(f"\n    at the recorded {fee:.0f} bps ({record['product']}, as of {record['as_of']}):")
    for name, ok, detail in checks:
        p(f"      {'PASS' if ok else 'FAIL'}  {name:<36} {detail}")
    p(f"    {'PASS' if passed else 'FAIL'} — BA-005 "
      + ("holds on the terms it was locked with; the ruin test (step 3) is next, and only then a fifth book."
         if passed else
         "is a failure on the locked rule and window. No re-scue by parameters, window, leverage, a second asset, or frequency."))
    return out, 0 if passed else 1


def ruin_section(months: list[date], bar_returns: list[float], ours: dict, held: dict,
                 fee: float | None, net: dict | None = None) -> dict:
    """Step 3: the ruin promise, priced with the archive's own definition of an affordable bill.

    `monthly_income_race.safe_amount` is the function that produced the equity book's $435/mo figure, and `plan_stats` is what produced its
    failure rates, so this section is comparable to those numbers rather than a new invention with a similar name. Two caveats are printed
    rather than buried. The horizon here is 5 years, because 123 months of crypto history contains four 10-year windows and the archive's
    own round-47 lesson is that a statistic annualised over too few windows is pricing days that were never traded; and a bill is meaningless
    without its promise, so both `ends whole` and `never zero` are priced (round 54).
    """

    years = RUIN_YEARS
    windows = len(bar_returns) - years * 12 + 1
    lines: list[str] = []
    if windows < 12:
        return {"lines": [f"ruin test needs {years * 12} months of history plus windows to fail in; the record has {len(bar_returns)}"],
                "bill": None, "ours_p_fail": None, "bar_p_fail": None, "ours_worse": False}
    bill_ew = mir.safe_amount(bar_returns, CAPITAL, years, P_FAIL_MAX, floor=1.0)
    bill_nz = mir.safe_amount(bar_returns, CAPITAL, years, P_FAIL_MAX, floor=0.0)
    lines.append(f"the ruin promise · {years}-year windows · {windows} of them · failure budget {P_FAIL_MAX:.0%} · "
                 f"one window is {100.0 / windows:.1f} points, so a {100.0 / windows:.1f}-point gap in P(fail) is one plan, not a trend")
    lines.append(f"QQQ's own affordable bill at that budget: ${bill_ew:,.0f}/mo to end whole · ${bill_nz:,.0f}/mo to never reach zero")
    lines.append(f"{'leg':<26}{'P(fail) ends whole':>19}{'median':>9}{'P(erase)':>10}{'at the bill':>13}")

    rows = [("QQQ, held", bar_returns), ("BA-005, fee = 0", ours["returns"]), ("BTC-USD, held", held["returns"])]
    if net is not None and fee is not None:
        rows.insert(2, (f"BA-005, at {fee:.0f} bps", net["returns"]))
    stats = {}
    for label, series in rows:
        s = mir.plan_stats(series, CAPITAL, bill_ew, years, floor=1.0)
        stats[label] = s
        lines.append(f"{label:<26}{s['p_fail']:>18.0%} {s['median_mult']:>8.2f}x{s['p_erase']:>9.0%}{bill_ew:>12,.0f}")
    ours, bar = stats["BA-005, fee = 0"], stats["QQQ, held"]
    return {"lines": lines, "bill": bill_ew, "windows": windows, "ours": ours, "bar": bar,
            "ours_p_fail": ours["p_fail"], "bar_p_fail": bar["p_fail"],
            # A failure rate over few windows is a coarse instrument, so the gate is the pair: failing more often *and* being
            # more likely to have the capital halved. Either alone can be one window's worth of noise.
            "ours_worse": (ours["p_fail"] > bar["p_fail"] and ours["p_erase"] > bar["p_erase"]),
            "worse_erase": ours["p_erase"] > bar["p_erase"]}


def _refusal() -> str:
    try:
        venue_fees.taker_bps("BA-005")
    except SystemExit as exc:
        return str(exc)
    return ""


def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    md = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    record = venue_fees.load()
    fee = None
    if record is not None and venue_fees.age_days(record) <= venue_fees.MAX_AGE_DAYS:
        fee = float(record["taker_bps"])
    lines, code = report_lines(md, fee, record)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
