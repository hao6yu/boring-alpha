"""The paper candidate scored as a monthly-deposit account, which is the frame the goal uses.

Run: .venv/bin/python tools/funded_policy.py [--sleeve SPY] [--window full|since 2010|recent]

Round 8 scored the candidate as a *withdrawal*: of the money already sitting there, what
monthly amount survives every start date. It cleared the index on SPY and VTI, and the reversal
control showed the gain was timing rather than exposure. That is the right question for a pot
being spent down. It is not the question the goal asks, which is "I put money in each month —
does this bot end with more of it than just buying VOO".

Round 7 is the reason to expect a different answer here and to expect it honestly: the same
dial moved the accumulation number up and the decumulation number down, and both were correct.
A gate that sells into a collapse protects a plan that is taking money out; a plan putting
money in is *buying* that collapse with its next deposit. The same mechanism can pay in one
frame and cost in the other, and only one of the two has been charged so far.

Method, and why each piece is the shape it is:

  Engine       imported from `run_voltarget_scan` — the funded simulator the paper book is
               scored with, not a second one. Costs: 2.0 bps per unit of one-way turnover,
               borrow at the archive's cash index plus 150 bps charged daily on the borrowed
               leg only, the sleeve's real expense ratio, 30% maintenance equity with a forced
               sale when breached, $5,000 opening and $500 a month deposited on arrival. The
               dollar conversions come from `funded_frame`, which is shared with
               `leverage_sizing`, so two tools cannot disagree about what a dollar a month
               means.
  Encoding     three encodings of the same rule, because which one you pick changes the
               answer by twelve percent of terminal wealth and none of them looks wrong. The
               first two are given the same cadence gate (`reviewed_sessions`, round 10):

                 desired weight + 10% band    400 trades  $11,399 costs  $1,775,832
                 applied weight + 10% band    222 trades   $5,988 costs  $2,007,019

               The rule reports trade sessions of its own and the second row is the one that
               counts like the policy — it is the row `run_voltarget_scan --candidate` uses, and
               on the scan's own pinned archive this tool reproduces that scan to the trade and
               to the cent: 222 fills, $5,988.17. The first row is what a caller gets by writing
               the code without reading the engine: `raw_weights` is the weight the rule *wants*,
               and an engine trades toward a want on every session it is let on to — which, for a
               weight that redraws its mind almost daily, is nearly all of them. 400 fills
               against 222, $11,399 of turnover against $5,988, and 12% less terminal wealth: a
               different rule, priced as if it were the same one. A third encoding — the applied
               weight with `band=0` and no cadence argument at all — is what a careful-looking
               caller writes on the theory that a zero band must be the strictest setting. It is
               the loosest: it chases drift on every session and books 8,428 fills for a rule
               that made 232 trades.

               `score()` reports the first two and words the verdict off the second, the encoding
               that matches the rule's own cadence, because the goal is an account and not a
               simulation. Reporting the better of two encodings of the same rule would be
               hedging; the honest version of that is both numbers.
  Warm-up      every row, comparator included, opens on the same session: the one the
               candidate can first answer on, which is what the pre-registered scan uses. The
               engine starts at
               `max(start, first answered target)`, so a default of 0 handed the unlevered
               comparator two hundred sessions of compounding the policy never had and then
               called the difference the policy's performance.
  Comparator   plain DCA into the same sleeve, same schedule, unlevered, one entry cost per
               deposit — the P0 dominance rule, priced the way the sealed shadow book prices
               it.
  Controls     flat at the candidate's own *realized* average weight (daily, the fair one, and
               banded, which shows the cash wedge a band puts under a monthly deposit); the
               same weights read backwards; and the vol target with the trend gate removed.
  Money units  the terminal gap as a level monthly amount at the comparator's own rate, plus
               the deepest rolling twelve-month hole against the comparator. The first is what
               the goal asks for; the second is what it would feel like.

One note on the engine, because it changed under this tool. `allow` used to be decorative: the
trade test read `allow is None or started or position in allow or …` and `started` was sticky
from the first fill, so from session two on the engine traded whenever its band said so and the
argument only ever refused the opening trade. Round 10 gave it teeth — a session outside the
reviewed set is now refused whatever the drift says, the opening fill still passes, and a
maintenance forced sale still passes because a margin call is not a rebalance. That is what the
cadence gate in `score()` is priced against, and it moved this tool's own numbers: SPY full
dropped from 241 fills to 222 and from $2,050,286 to $2,007,019, and the pre-registered scan's
full-window beat fell from $156,921 to $113,439. No verdict changed. The numbers before the fix
are left standing in the round-9 note rather than quietly edited, because a claim that has been
revised is a record and a claim that has been rewritten is nothing.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from boring_alpha.data.csv_loader import load_csv_market_data  # noqa: E402
from funded_frame import per_month_equivalent, worst_12m_difference  # noqa: E402
from paper import CANDIDATE  # the live candidate, imported and not restated  # noqa: E402
from policy_withdrawal import GATELESS  # the same gateless control as round 8  # noqa: E402
from run_voltarget_scan import MONTHLY, OPENING, funded  # noqa: E402
import withdrawal_capacity as wc  # noqa: E402

SLEEVES = ("SPY", "QQQ", "VTI", "ITOT", "VOO")

WINDOWS = {
    "full": (date(1993, 1, 1), date(2026, 9, 30)),
    "since 2010": (date(2010, 1, 1), date(2026, 9, 30)),
    "recent": (date(2022, 1, 1), date(2026, 9, 30)),
}

# Every row opens on the session the *candidate* can first answer — session 30 on SPY, which
# is the volatility window, not the trend window: `raw_weights` emits a weight as soon as
# volatility is available and simply leaves the gate disengaged until 200 sessions exist. That
# is the convention `run_voltarget_scan --candidate` was specified with, and deviating from it
# is not a conservatism, it is a different account: a start of 300 forfeits the fourteen months
# of deposits that fall before it, which is $7,000 of principal and $194,000 of terminal value
# on SPY, and it silently rewrites which history is being scored. Pass --warmup to try the
# alternative deliberately and see what it costs.
WARMUP = None
COMPARATOR = "plain DCA"

HEAD = (f"{'sleeve':6} {'book':22} {'avg w':>6} {'turns':>6} {'ending':>13} "
        f"{'gap':>11} {'$/mo':>8} {'worst 12m':>11} {'costs':>8} {'carry':>8} "
        f"{'DD':>7} {'calls':>5}")


def reversed_path(desired: list[float | None]) -> list[float]:
    """The candidate's decisions in reverse order, with no holes in them.

    Reversing `desired` whole moves the warm-up Nones to the end, and the engine `continue`s
    on a None target — skipping that month's deposit and that day's carry — so a naive
    reversal quietly stops the account two hundred sessions early and then reports the
    shortfall as though the scrambled rule had traded it. Take the answered block, reverse
    that, and hold its first value across the warm-up tail: a permutation of the decisions,
    every session priced.
    """

    answered = [w for w in desired if w is not None]
    if not answered:
        raise ValueError("a weight path with nothing in it cannot be reversed and scored")
    return list(reversed(answered)) + [answered[0]] * (len(desired) - len(answered))


def reviewed_sessions(targets: list[float | None]) -> set[int]:
    """The sessions at which this weight path differs from the one before it.

    Those are the sessions on which a trader following the rule could act: the rule is a
    reviewed weight that is held between reviews, so drift between two reviews is not an
    instruction. Passing this to the engine is what makes the row's fill count a claim about
    the rule rather than about the simulator's band. It is not a tightening either: applied
    to the raw encoding it keeps almost every session, because raw weights move almost every
    session — which is precisely why the raw encoding is not the traded one.
    """

    return {i for i, w in enumerate(targets)
            if w is not None and (i == 0 or targets[i - 1] is None or targets[i - 1] != w)}


def series(symbol: str, bounds: tuple[date, date]):
    """(dates, closes, returns, cash factors) for one sleeve, from the current archive."""

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    dates = [d for d in sorted(data.by_date)
             if symbol in data.by_date[d] and bounds[0] <= d <= bounds[1]]
    closes = [data.by_date[d][symbol].close for d in dates]
    returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    returns.insert(0, 0.0)
    return dates, closes, returns, [data.cash_factors[d] for d in dates]


def first_live(desired: list[float | None]) -> int:
    """The session the candidate can first act on, which is not the session it has a full
    trend window in. See `WARMUP`."""

    for index, weight in enumerate(desired):
        if weight is not None:
            return index
    raise ValueError("the policy never answered; there is no account to open")


def score(symbol: str, window: str = "full", warmup: int | None = WARMUP) -> list[tuple]:
    """Rows for one sleeve and one window, comparator included, straight from the engine.

    Returned rather than printed so a test can assert on the numbers without capturing stdout,
    and so the verdict line and the table can never disagree about which run they describe.
    """

    dates, closes, returns, factors = series(symbol, WINDOWS[window])
    desired = CANDIDATE.raw_weights(closes, returns)
    if warmup is None:
        warmup = first_live(desired)
    if len(dates) < warmup + 400:
        raise ValueError(f"{symbol} has {len(dates)} sessions in {window}, not enough to "
                         f"open an account at session {warmup} and measure anything")
    rows: list[tuple] = []

    def row(label: str, targets: list[float | None], band: float, cadence: bool = False) -> None:
        rows.append((label, funded(closes, returns, factors, dates, targets=targets,
                                   band=band, start=warmup,
                                   allow=reviewed_sessions(targets) if cadence else None)))

    row(COMPARATOR, [1.0] * len(dates), 0.0)
    applied = [w for w, _turn in CANDIDATE.weights(closes, returns)]
    # The four rows above the control lines are all claims about the same rule, so all four
    # are held to the rule's own review sessions. The comparator and the two flat rows are
    # not: a book that buys every deposit and a book that rebalances daily have no cadence to
    # honour, and gating them would invent one.
    row("candidate (loose enc.)", desired, CANDIDATE.rebalance_band, cadence=True)
    row("candidate (as traded)", applied, CANDIDATE.rebalance_band, cadence=True)
    row("candidate, reversed", reversed_path(desired), CANDIDATE.rebalance_band, cadence=True)
    row("no trend gate", GATELESS.raw_weights(closes, returns), GATELESS.rebalance_band,
        cadence=True)
    # The leverage control has to be at the exposure the candidate actually *held*. Averaging
    # its intentions is how a control quietly becomes a different instrument: a banded book
    # and a daily-rebalanced one carry different weights for the same policy.
    average = rows[2][1].avg_weight
    row("flat at avg, daily", [average] * len(dates), 0.0)
    row("flat at avg, banded", [average] * len(dates), CANDIDATE.rebalance_band)
    return rows


def report(symbol: str, window: str, warmup: int | None) -> dict[str, float]:
    """Print one sleeve's table and its verdict line; return the gaps for aggregation."""

    rows = score(symbol, window, warmup)
    comparator = dict(rows)[COMPARATOR]
    # Months from the run's own path rather than a second read of the archive: the path is the
    # account, and an annuity over months the account did not exist would be a fiction.
    first, last = comparator.path[0][0], comparator.path[-1][0]
    months = max(int(round(max((last - first).days, 30) / 365.2425 * 12)), 1)
    expense = wc.EXPENSE.get(symbol, 0.0)

    # The header states when the account actually opened. Printing the *requested* warm-up
    # printed "session None" for the default, which hid that the default is a session the tool
    # computed rather than one the caller chose — and a header that lies about the window is
    # the cheap way for a whole table to stop meaning what it says.
    opened = (f"session {warmup}" if warmup is not None
              else "the candidate's first live session")
    print(f"\n{symbol} · {window} · ${OPENING:,.0f} opening, ${MONTHLY:,.0f}/month · "
          f"{months} months from {first} ({opened}) · expense {expense * 1e4:.2f} bps")
    print(HEAD)
    gaps: dict[str, float] = {}
    for label, res in rows:
        gap = res.ending - comparator.ending
        gaps[label] = gap
        hole = worst_12m_difference(list(res.path), list(comparator.path))
        print(f"{symbol:6} {label:22} {res.avg_weight:6.3f} {res.turns:6d} "
              f"{res.ending:13,.0f} {gap:+11,.0f} "
              f"{per_month_equivalent(gap, comparator.irr, months):+8,.0f} "
              f"{hole:+11,.0f} {res.cost_paid:8,.0f} {res.carry_paid:8,.0f} "
              f"{res.max_drawdown * 100:6.1f}% {res.margin_calls:5d}"
              f"{'  RUINED' if res.ruined else ''}")

    cand, back = gaps["candidate (as traded)"], gaps["candidate, reversed"]
    flat = gaps["flat at avg, daily"]
    verdict = ("DOMINATED by the index" if cand <= 0 else "clears the index")
    held_weight = dict(rows)["candidate (as traded)"].avg_weight
    verdict += (f"; loses to holding its own {held_weight:.3f}x flat as well"
                if flat > cand else "; beats holding that weight flat")
    verdict += ("; REVERSED WEIGHTS DO AS WELL — no timing claim"
                if back >= cand - abs(0.02 * cand) else "; the ordering is worth money")
    print(f"{symbol:6} {'VERDICT':22} {'':6} {'':6} {'':13} {cand:+11,.0f}"
          f"{'':29} {'':11} {'':8} {'':8} {'':7} {'':5}   {verdict}")
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sleeve", default=None)
    parser.add_argument("--window", default="full", choices=sorted(WINDOWS))
    parser.add_argument("--warmup", type=int, default=None,
                        help="session the account opens on, for every row including the "
                             "comparator. Default: the session the candidate can first "
                             "answer, which is what the pre-registered scan uses")
    args = parser.parse_args()

    print("a trading policy scored as a monthly deposit account, against plain DCA")
    print(f"${OPENING:,.0f} opening and ${MONTHLY:,.0f} a month · {wc.TURNOVER_COST * 10_000:.1f} bps per unit turnover · "
          f"borrow at cash + {wc.BORROW_SPREAD * 10_000:.0f} bps · {wc.MAINTENANCE_EQUITY:.0%} maintenance cushion")
    print("gap is terminal dollars against the comparator; $/mo discounts that gap at the "
          "comparator's own rate")
    print("worst 12m is the deepest rolling-year hole against the comparator, in dollars")

    for symbol in ((args.sleeve,) if args.sleeve else SLEEVES):
        try:
            report(symbol, args.window, args.warmup)
        except ValueError as error:
            print(f"\n{symbol}: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
