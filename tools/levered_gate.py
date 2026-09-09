"""The same decision rule, mounted on leverage instead of on 1.0x — and billed at real desks.

Run: .venv/bin/python tools/levered_gate.py [--sleeve SPY] [--window full] [--lever 1.5]

Eleven rounds leave one timing mechanism still breathing and one exposure mechanism that clears
the index everywhere. They have only ever been measured apart:

  * round 10's candidate — vol-targeted, trend-gated, capped at 1.30x — has the shallowest
    drawdown in 15 of 15 cells and is a cash loser in 15 of 15. It is insurance, not income.
  * round 11's constant leverage — no signal in it at all, just a fixed weight — clears the whole
    financing menu at 1.25x and above, with a drawdown about 2.5x as deep.

Nobody has asked the question the goal actually needs asked: **does the decision keep earning once
it is allowed to drive a bigger car?** A timing rule that only works at 1.0x is advice about where
to sit, not a way to make money. And a levered book is the only book on which a rule can add
dollars, because leverage is the only thing that makes an account's exposure exceed its deposits.

So this tool runs the candidate's own weight path multiplied by a leverage factor — at `L x` the
pre-registered 0.30 floor becomes `0.30L` and the 1.30 cap becomes `1.30L`, which is what "the same
rule, run at 2x" actually means: on a trend break the book cuts to 30% *of the levered target*, not
to 30% of equity. Four books, and the two that decide the question are not the index:

  DCA              plain unlevered dollar-cost averaging into the same sleeve. The P0 dominance
                   rule. A levered book that cannot clear this is not worth the argument.
  flat at the gate's OWN realized average weight    the timing claim itself, and the control that
                   answers it (round 8's rule: charge a policy against the exposure it took,
                   not the exposure it asked for). The candidate averages ~1.07x at L=1.0, so a
                   control set at L flat would be a different amount of risk and the comparison
                   would be a claim about leverage dressed up as a claim about timing. If the gate
                   does not beat this row, the leverage is the whole of the result and the bot is
                   decoration.
  the same weights read backwards    the negative control. A rule whose reverse earns as much is
                   reading nothing.
  the vol target with the trend gate switched off    which half of the rule carries the row.

**Two flat controls, not one, and the row's verdict is the worse of the two.** A declared tightening
made after the grid was first run, and stated here rather than smoothed over. The single flat row
suppresses rebalancing below its band, so at `L < 1.25` its band *is* the no-drift rule
`financing_break_even` runs, and it turns out to be the weaker control: band-suppressed it sits in
cash through the early deposits — 8,428 fills against the calendar-reviewed row's 7,120 on SPY
recent — and it loses more in the crash. But the calendar-reviewed row is only a fair comparison of
the policy's own *timing*; a bot can check the clock. Judging a timing claim against an exposure
control whose timing is handicapped in a way no real implementation would be flatters the policy, so
the verdict row is `min(vs_flat, vs_matched)` — the candidate must clear the better of its two
matched controls at every lever, not whichever is nearer. Where the two diverge, 2.0x and 2.3x, the
count of cells clearing both falls from 9/15 and 11/15 to 6/15 and 8/15.

A second tightening, same honesty: the per-lever grid reports the bot's drawdown, not its price. The
question the goal actually asks is what the rule earns *at the leverage whose pain equals the
index's*, so `report_dd_match` bisects `L` per cell until the bot's maximum drawdown equals the DCA
comparator's and prints that row too. Its bracket may fail to cross in either direction and both
failures are printed as their own sentence, never collapsed into a number.

Pre-registered reading, written before the grid was run. On the cheap desk (Public, 4.90% posted —
the base tier an account of this size actually pays):

  A — beats DCA *and* beats its own-exposure flat at some lever, on most sleeves, with the reversed
      path doing worse: the decision is worth money at scale, and the drawdown column is the price,
      stated.
  B — clears DCA but not its own-exposure flat: the money is the borrowing. The instruction is
      "buy more index, financed cheaply", which is round 11's answer and not a bot.
  C — clears nothing at any desk at any lever: the gate is Redundant at leverage too, and the
      goal's mechanism is not a trading model at all.

Conventions, all inherited so the tables read together: $5,000 opening and $500 a month on arrival,
2.0 bps per unit of one-way turnover, the sleeve's real expense ratio, borrow accrued daily on the
borrowed leg only, 30% maintenance equity with a forced sale to 1.0x when breached. Every row — the
comparator included — opens on the session the *policy* can first answer, so no book is handed
compounding the others were denied.

**Bands are per row, and one band for every row is a bug.** The first draft of this tool passed the
candidate's 10% band to all seven books at once. On the comparator that band is a handicap dressed
as a convention: a $500 deposit is under 10% of the account from the first year onward, so it sits
in cash, and SPY's recent window came out at 14 fills, 95.5% invested and $607 poorer than the same
run banded at zero. That is the asymmetry round 11 was written to forbid, pointed the flattering
way. So: DCA gets `band=0` — deposit spent on arrival, the way the sealed shadow book spends it; the
flat control follows `financing_break_even`'s rule, suppressed below 1.25x and 10% above; the policy
rows keep the 10% they were pre-registered with *and* are also run at the tight band, because a wide
band is a concession to leverage and the honest dollar figure is the one billed at the band a trader
would actually trade. The verdict reads off the tight-band rows, the candidate's own band is shown
beside them, and the difference between the two is a column rather than an assumption.

Policy rows are gated to their own reviewed sessions (round 10); the comparator and the flat controls
are not, because a book that buys every deposit and a book that holds one weight have no cadence to
honour, and gating them would invent one. Borrow is quoted at each desk's *posted* rate by
subtracting that window's own annualised cash from the spread, so the all-in charge is the posted
rate and the cash rate is not charged twice.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import financing_break_even as fbe  # noqa: E402  (the menu, the cached cell, the cash maths)
import funded_frame  # noqa: E402
import funded_policy as fp  # noqa: E402  (series, warm-up, cadence, reversal — imported, not restated)
import run_voltarget_scan as engine  # noqa: E402
import withdrawal_capacity as wc  # noqa: E402
from run_voltarget_scan import MONTHLY, OPENING, funded  # noqa: E402

LEVERS = (1.0, 1.25, 1.5, 2.0, 2.3)
SLEEVES = fp.SLEEVES
WINDOWS = fbe.WINDOWS
BAND = fp.CANDIDATE.rebalance_band          # the candidate's own band, from the candidate
TIGHT = fbe.TIGHT                          # the band a levered trader would actually trade
DESKS = ("Public", "Fidelity")              # cheapest on the menu, and a large custodian
CADENCE = fp.CANDIDATE.review_every         # the control's review calendar, matched to the policy
# (path key, band, who decides when the book may trade) per row. The comparator and the two flat
# books are not gated to reviewed sessions — a book that buys every deposit and a book that holds
# one weight have no cadence to honour. `flat tight` is the exception, and it is gated by the
# *calendar* rather than by target changes, because what makes it a fair control is that it is
# looked at exactly as often as the rule is.
# (label, path key, band, gated?) — built after the paths exist, per desk.
ROWS = {
    "DCA":            ("uniform", 0.0,   False),   # the dominance rule, deposit spent on arrival
    "gate":           ("gate",    BAND,  True),    # the pre-registered encoding
    "gate tight":     ("gate",    TIGHT, True),    # the billed encoding
    "flat":           ("flat",    None,  False),   # None = financing_break_even's own rule
    "flat tight":     ("flat",    TIGHT, "calendar"),
    "reversed":       ("back",    TIGHT, True),
    "no trend gate":  ("ungated", TIGHT, True),
}
ORDER = ("gate", "gate tight", "flat", "flat tight", "reversed", "no trend gate", "DCA")
HEAD = (f"{'L':>4} {'book':14} {'avg w':>6} {'turns':>6} {'ending':>13} {'vs DCA':>11} "
        f"{'vs flat':>11} {'$/mo cheap':>11} {'$/mo @10.6%':>12} {'maxDD':>7} {'calls':>5} "
        f"{'carry':>8}")


def series(symbol: str, window: str):
    """One slice of the archive, in this tool's argument order: sleeve first, window second.

    `financing_break_even.cell` takes them the other way round and `funded_policy.series` takes a
    sleeve and a date pair, so a call site written from memory has a 50% chance of loading the wrong
    slice and a KeyError is the luckier outcome. One call site, one order, and it is this tool's.
    """

    return fbe.cell(window, symbol)


def review_calendar(sessions: int, every: int = CADENCE) -> set[int]:
    """Every `every`-th session: the days a held weight gets looked at, decision or no decision.

    The policy's cadence is not a fact about volatility, it is a fact about how often somebody
    sits down with the account. A control that is let look at the book daily pays more to discover
    it needs no trade than one that is looked at weekly, and `flat` at one band or the other is
    cheap on churn for the same reason the candidate is. This row is the no-decision alternative
    that has been to the same number of meetings.
    """

    return {i for i in range(sessions) if i % every == 0}


def levered_desired(lever: float, closes: list[float], returns: list[float],
                    gated: bool = True) -> list[float | None]:
    """The candidate's weight path, multiplied by the leverage factor.

    Scaling the *answer* rather than re-parameterising the policy is the point. `VolTargetPolicy`
    refuses a target volatility above 1.0 and a cap above 3.0x, so building a 2x book by editing it
    would change the rule under test; multiplying its output by L leaves every clip and every gate
    firing exactly where it fired, at L x the size. A lever whose cap would pass the policy's own
    3.0x credibility limit is refused rather than clipped, because clipping silently replaces the
    rule at precisely the leverage where the rule is being asked to earn its keep.
    """

    policy = fp.CANDIDATE if gated else fp.GATELESS
    if policy.max_weight * lever > 3.0:
        raise ValueError(f"{lever:.2f}x puts the cap at {policy.max_weight * lever:.2f}x, past "
                         f"the 3.0x range the policy itself calls credible — refusing to answer "
                         f"rather than clipping the rule")
    return [None if w is None else w * lever for w in policy.raw_weights(closes, returns)]


def spread_for(rate: float, factors: list[float]) -> float:
    """A desk's posted all-in rate, as the spread the engine accrues.

    The engine charges `cash_daily + spread`, so passing a posted rate straight through as the
    spread bills the cash rate twice and overstates every desk by 150-400 bps — most of the room
    this line of work exists to measure. Floored at −5% for the reason round 11 floored it: no desk
    pays you to borrow, so a spread below cash-minus-five is a fiction about a world where they do.
    """

    return max(rate - fbe.annualised_cash(factors), -0.05)


def cell_books(symbol: str, window: str, lever: float) -> dict:
    """Every book for one cell, keyed by (desk, name), all opening on the same session.

    Two passes, because the flat controls are set from the *billed* gate run's realized average and
    that run has to exist first. The average is taken per desk: the borrow moves the equity path, so
    the two desks' runs end at slightly different weights and a control pinned to one would not
    match the other.
    """

    dates, closes, returns, factors = series(symbol, window)
    desired = levered_desired(lever, closes, returns)
    warmup = fp.first_live(desired)
    if len(dates) < warmup + 400:
        raise ValueError(f"{symbol} has {len(dates)} sessions in {window}, not enough to open an "
                         f"account at session {warmup} and measure anything")

    paths = {
        "gate": [None if w is None else w * lever for w, _
                 in fp.CANDIDATE.weights(closes, returns)],
        "back": fp.reversed_path(desired),
        "ungated": levered_desired(lever, closes, returns, gated=False),
        "uniform": [1.0] * len(dates),
    }
    runs: dict[tuple[str, str], object] = {}
    averages: dict[str, float] = {}
    saved = (engine.BORROW_SPREAD, engine.EXPENSE)
    engine.EXPENSE = wc.EXPENSE.get(symbol, 0.0)
    calendar = review_calendar(len(dates))
    try:
        for desk in DESKS:
            engine.BORROW_SPREAD = spread_for(dict(fbe.MENU)[desk], factors)
            for name in ("gate", "gate tight", "reversed", "no trend gate", "DCA"):
                path_key, band, gated = ROWS[name]
                runs[(desk, name)] = funded(
                    closes, returns, factors, dates, targets=paths[path_key], band=band,
                    start=warmup,
                    allow=fp.reviewed_sessions(paths[path_key]) if gated is True else None)
            average = runs[(desk, "gate tight")].avg_weight
            averages[desk] = average
            for name in ("flat", "flat tight"):
                band = ROWS[name][1]
                runs[(desk, name)] = funded(
                    closes, returns, factors, dates, targets=[average] * len(dates),
                    band=band if band is not None else (0.0 if average < fbe.SUPPRESS_BELOW
                                                        else BAND),
                    start=warmup, allow=calendar if ROWS[name][2] == "calendar" else None)
    finally:
        engine.BORROW_SPREAD, engine.EXPENSE = saved
    return {"runs": runs, "warmup": warmup, "average": averages}


def score(symbol: str, window: str, lever: float) -> dict:
    """One cell as numbers: the two gaps that matter, the dollars, and the drawdowns.

    The verdict rows are `gate tight` — the rule billed at the band a levered trader would trade —
    against `flat` (round 11's comparable control) and `flat tight` (the control at the same review
    calendar). `vs_dca` answers the dominance rule; `vs_flat` and `vs_matched` are the timing claim.
    """

    cell = cell_books(symbol, window, lever)
    runs = cell["runs"]
    cheap, dear = DESKS
    base = runs[(cheap, "DCA")]
    months = max(int(round(max((base.path[-1][0] - base.path[0][0]).days, 30)
                           / 365.2425 * 12)), 1)

    def monthly(book) -> float:
        return funded_frame.per_month_equivalent(book.ending - base.ending, base.irr, months)

    gate, wide = runs[(cheap, "gate tight")], runs[(cheap, "gate")]
    flat, matched = runs[(cheap, "flat")], runs[(cheap, "flat tight")]
    return {
        "sleeve": symbol, "window": window, "lever": lever, "months": months,
        "cell": cell, "runs": runs, "base": base, "flat": flat, "matched": matched,
        "gate": gate, "avg_weight": gate.avg_weight,
        "vs_dca": gate.ending - base.ending,
        "vs_flat": gate.ending - flat.ending,
        "vs_matched": gate.ending - matched.ending,
        # The timing claim is the WORSE of the two controls, not the friendlier one. Which control
        # is cheaper to run flips with the leverage: below 1.25x the no-cadence book has its band
        # suppressed and rebalances 8,428 times, so a margin over it is partly a cost artifact; above
        # it the calendar book trades most often and is the stronger of the pair. Taking the minimum
        # is the one comparison that cannot be accused of having been picked.
        "vs_control": min(gate.ending - flat.ending, gate.ending - matched.ending),
        "beats_control": min(gate.ending - flat.ending,
                             gate.ending - matched.ending) > 0,
        "band_wedge": gate.ending - wide.ending,
        "vs_rev": gate.ending - runs[(cheap, "reversed")].ending,
        "vs_ungated": gate.ending - runs[(cheap, "no trend gate")].ending,
        "mo_cheap": monthly(gate), "mo_dear": monthly(runs[(dear, "gate tight")]),
        "dd": gate.max_drawdown, "dd_flat": flat.max_drawdown, "dd_dca": base.max_drawdown,
        "calls": gate.margin_calls, "carry": gate.carry_paid, "turns": gate.turns,
        "ruined": gate.ruined,
        "clears_cheap": gate.ending > base.ending,
        "clears_dear": runs[(dear, "gate tight")].ending > runs[(dear, "DCA")].ending,
        # More money *and* a shallower hole than the index, in the same cell. Declared as an
        # addition made after the first run of the grid: the pre-registered A/B/C is a verdict on
        # the timing claim, which is not the question the goal asks, and the goal's question — does
        # any rule beat doing nothing on both axes at once — had no column. It is reported as a
        # diagnostic and the registered verdict above is left exactly where it was registered.
        "both_axes": gate.ending > base.ending and gate.max_drawdown > base.max_drawdown,
        "both_axes_dear": (runs[(dear, "gate tight")].ending > runs[(dear, "DCA")].ending
                           and runs[(dear, "gate tight")].max_drawdown
                           > runs[(dear, "DCA")].max_drawdown),
    }


_DCA: dict[tuple[str, str, str], object] = {}


def dca_row(symbol: str, window: str, desk: str = None):
    """The dominance comparator for one slice, run once and remembered.

    The same book `score()` uses — band zero, opening on the policy's first live session — factored
    out because the drawdown-matching below has to know the index's own worst month *before* it
    knows the leverage it is solving for, and two definitions of "the index over this window" in one
    tool is how a matched-pain comparison quietly stops matching. Desk-invariant by construction: an
    unlevered book never borrows, so the spread cannot touch it, which is also why `carry` is zero on
    every DCA row in the table.
    """

    key = (symbol, window, desk or DESKS[0])
    if key not in _DCA:
        dates, closes, returns, factors = series(symbol, window)
        warmup = fp.first_live(levered_desired(1.0, closes, returns))
        saved = (engine.BORROW_SPREAD, engine.EXPENSE)
        engine.BORROW_SPREAD = spread_for(dict(fbe.MENU)[desk or DESKS[0]], factors)
        engine.EXPENSE = wc.EXPENSE.get(symbol, 0.0)
        try:
            _DCA[key] = funded(closes, returns, factors, dates, targets=[1.0] * len(dates),
                               band=0.0, start=warmup)
        finally:
            engine.BORROW_SPREAD, engine.EXPENSE = saved
    return _DCA[key]


def gate_at(symbol: str, window: str, lever: float, desk: str = None):
    """Just the policy row, at one leverage, at one desk — the piece a bisection needs.

    `score()` runs seven books at two desks because its job is the table. This runs one, because
    bisection asks the same question a dozen times and a solver that re-runs the controls each
    time is a slow solver with the same answer.
    """

    dates, closes, returns, factors = series(symbol, window)
    path = [None if w is None else w * lever for w, _ in fp.CANDIDATE.weights(closes, returns)]
    warmup = fp.first_live(levered_desired(lever, closes, returns))
    saved = (engine.BORROW_SPREAD, engine.EXPENSE)
    engine.BORROW_SPREAD = spread_for(dict(fbe.MENU)[desk or DESKS[0]], factors)
    engine.EXPENSE = wc.EXPENSE.get(symbol, 0.0)
    try:
        return funded(closes, returns, factors, dates, targets=path, band=TIGHT, start=warmup,
                      allow=fp.reviewed_sessions(path))
    finally:
        engine.BORROW_SPREAD, engine.EXPENSE = saved


def dd_match(symbol: str, window: str, desk: str = None, low: float = 1.0, high: float = 2.3,
             tolerance: float = 0.005) -> dict:
    """The leverage at which the bot's worst drawdown equals the index's own, and what it pays.

    Comparing at a fixed leverage is the fair test of *timing* and it is the one above, but it is
    not the question the goal asks. Nobody chooses leverage for its own sake; they choose how much
    worst month they can sleep through and then want the most money available at that pain level.
    A rule that cuts exposure into a collapse earns the right to hold more exposure the rest of the
    time, and the only honest way to price that right is to *give it away*: solve for the leverage
    at which the bot's deepest hole is as deep as simply holding the index, and then count the
    dollars. If they are not ahead at that point, the rule's risk reduction is worth less than the
    same risk reduction obtained by holding less.

    `high` is 2.3x because that is where the candidate's own 1.30x cap reaches the 3.0x its class
    calls credible; a solver that wandered past it would be answering with a different rule. Drawdown
    is monotone in leverage over the archive on every sleeve measured here — if it ever stops being,
    the bisection still returns a crossing and `note` says how far off the target it landed. The
    drawdown being matched is a single path-dependent number on a single history, which is a crude
    yardstick and the only one a daily archive offers.
    """

    base = dca_row(symbol, window, desk)
    target = base.max_drawdown
    shallower_at_floor = gate_at(symbol, window, low, desk).max_drawdown > target
    shallower_at_ceiling = gate_at(symbol, window, high, desk).max_drawdown > target
    if not shallower_at_floor:
        lever, note = low, "already as deep as the index at 1.0x — no leverage to solve for"
    elif shallower_at_ceiling:
        lever, note = high, "cap binding: still shallower than the index at the 3.0x ceiling"
    else:
        # `gap > 0` means this leverage is still shallower than the target, and the way to a deeper
        # hole is more leverage, so the *floor* moves up. The first draft had the two branches the
        # other way round, which is invisible on any cell whose crossing happens to sit near the
        # midpoint of the inverted bracket (VOO full window landed on it to 0.1 pp by luck) and wrong
        # everywhere else: half the matched-pain table it produced was answering a different question.
        bottom, top, lever, gap = low, high, low, 0.0
        for _ in range(16):
            lever = (bottom + top) / 2.0
            gap = gate_at(symbol, window, lever, desk).max_drawdown - target
            if abs(gap) <= tolerance:
                break
            bottom, top = (lever, top) if gap > 0 else (bottom, lever)
        note = f"solved to {abs(gap) * 100:.2f} pp of the index's own drawdown"
    cell = score(symbol, window, lever)
    return {"lever": lever, "target_dd": target, "note": note,
            # How far the run landed from the pain it was solved to match. A solver that reports a
            # bracket hit as a crossing is caught by this number rather than by the prose: the lever
            # may sit anywhere in the bracket, the drawdown may not.
            "dd_gap": cell["dd"] - target,
            "solved": note.startswith("solved"),
            **{k: cell[k] for k in ("vs_dca", "mo_cheap", "mo_dear", "vs_flat", "vs_matched",
                                    "vs_control", "beats_control", "both_axes", "both_axes_dear",
                                    "dd", "calls", "avg_weight", "clears_cheap", "clears_dear",
                                    "carry", "months", "ruined")}}


def report_dd_match(windows: list, sleeves: list) -> None:
    print(f"\nmatched-pain comparison — for each cell, the leverage at which the bot's deepest "
          f"hole equals\nplain DCA's, both books then billed at the same desks "
          f"({' and '.join(DESKS)}):")
    print(f"{'sleeve':6} {'window':11} {'L*':>5} {'maxDD':>7} {'index DD':>9} {'hit by':>7} "
          f"{'vs DCA':>12} "
          f"{'$/mo cheap':>11} {'$/mo @10.6%':>12} {'vs control':>11} {'calls':>5}")
    rows = []
    for window in windows:
        for symbol in sleeves:
            try:
                m = dd_match(symbol, window)
            except ValueError as error:
                print(f"{symbol:6} {window:11} {error}")
                continue
            rows.append((symbol, window, m))
            # The miss is printed on every row, solved or not. Printing the note only where the
            # solve fell back to a bracket is what let an inverted solver ship a table: it labelled a
            # 28-point miss "solved to 28.81 pp of the index's own drawdown" and the column that
            # would have shown the absurdity for what it was stayed blank.
            print(f"{symbol:6} {window:11} {m['lever']:5.2f} {m['dd'] * 100:6.1f}% "
                  f"{m['target_dd'] * 100:8.1f}% {m['dd_gap'] * 100:+6.2f}pp "
                  f"{m['vs_dca']:+12,.0f} {m['mo_cheap']:+11,.0f} "
                  f"{m['mo_dear']:+12,.0f} {m['vs_control']:+11,.0f} {m['calls']:5d}"
                  + ("" if m["solved"] else f"   {m['note']}"))
    if rows:
        cheap = [m["mo_cheap"] for _s, _w, m in rows]
        dear = [m["mo_dear"] for _s, _w, m in rows]
        print(f"  median at the cheap desk ${statistics.median(cheap):+,.0f}/mo, at "
              f"{DESKS[1]} ${statistics.median(dear):+,.0f}/mo; clears the index in "
              f"{sum(1 for _s, _w, m in rows if m['clears_cheap'])}/{len(rows)} cells cheap, "
              f"{sum(1 for _s, _w, m in rows if m['clears_dear'])}/{len(rows)} at "
              f"{DESKS[1]}; beats both exposure controls in "
              f"{sum(1 for _s, _w, m in rows if m['beats_control'])}/{len(rows)}; beats the index "
              f"on both axes in {sum(1 for _s, _w, m in rows if m['both_axes'])}/{len(rows)} cells"
              f" ({sum(1 for _s, _w, m in rows if m['both_axes_dear'])} of those also at "
              f"{DESKS[1]})")


def report(symbol: str, window: str, tally: list) -> None:
    dates, _c, _r, factors = series(symbol, window)
    print(f"\n{symbol} · {window} · {dates[0]}..{dates[-1]} · {len(dates)} sessions · "
          f"cash over window {fbe.annualised_cash(factors):.2%} · verdict rows billed at "
          f"{TIGHT:.0%} band, review gate enforced")
    print(HEAD)
    for lever in LEVERS:
        try:
            cell = score(symbol, window, lever)
        except ValueError as error:
            print(f"{lever:4.2f} {error}")
            continue
        runs = cell["cell"]["runs"]
        gaps = {"gate": cell["vs_flat"], "gate tight": cell["vs_flat"],
                "flat": cell["vs_flat"], "flat tight": cell["vs_matched"],
                "reversed": cell["vs_rev"], "no trend gate": cell["vs_ungated"], "DCA": 0.0}
        for name in ORDER:
            book = runs[(DESKS[0], name)]
            dollars = (f" {cell['mo_cheap']:+11,.0f} {cell['mo_dear']:+12,.0f}"
                       if name == "gate tight" else f"{'':>11}{'':>12}")
            print(f"{lever:4.2f} {name:14} {book.avg_weight:6.3f} {book.turns:6d} "
                  f"{book.ending:13,.0f} {book.ending - cell['base'].ending:+11,.0f} "
                  f"{gaps[name]:+11,.0f}{dollars}"
                  f" {book.max_drawdown * 100:6.1f}% {book.margin_calls:5d} {book.carry_paid:8,.0f}"
                  + ("  RUINED" if book.ruined else ""))
        print(f"{'':4} {'':14} {'':6} {'':6} {'':13} {'':11} {'':11}"
              f"  band wedge on the gate {cell['band_wedge']:+,.0f}")
        tally.append(cell)


def reading(tally: list) -> str:
    """The pre-registered verdict — A, B or C — read off the cheap desk's two gaps.

    A is a property of a *lever* on a *grid*, not of the grid whole, so the rule is evaluated per
    lever and the lever is named: clearing the index on every cell while failing the timing test on
    most of them is B, and clearing it on every cell while passing the timing test on a majority is
    A. Nothing about that ordering was chosen after the numbers arrived; what was added after
    seeing them is the sentence naming which condition failed, because a verdict that does not say
    which of its two tests failed cannot be argued with.
    """

    print(f"\n{'—' * 78}")
    clears = sum(1 for t in tally if t["clears_cheap"])
    earns = sum(1 for t in tally if t["clears_cheap"] and t["beats_control"])
    print(f"{earns} of {len(tally)} cells beat plain DCA *and* both of their own-exposure controls "
          f"at the cheap desk; {clears} clear DCA; "
          f"{sum(1 for t in tally if t['vs_flat'] > 0)} beat the no-cadence flat control, "
          f"{sum(1 for t in tally if t['vs_matched'] > 0)} the review-matched one")
    verdict = "C"
    for lever in LEVERS:
        leg = [t for t in tally if t["lever"] == lever]
        if not leg:
            continue
        won = sum(1 for t in leg if t["clears_cheap"])
        timed = sum(1 for t in leg if t["beats_control"])
        if won == len(leg) and timed * 2 > len(leg):
            verdict = "A"
            print(f"verdict A at {lever:.2f}x — the index is clear in all {len(leg)} cells and the "
                  f"decision beats the worse of its two exposure controls in {timed} of them. Read "
                  f"the drawdown column before the dollar column.")
            break
        if won == len(leg) and verdict != "A":
            verdict = "B"
    if verdict == "B":
        print("verdict B — the index is cleared somewhere on the grid but the timing test fails "
              "there. The money is the borrowing; the instruction is 'hold more index, financed "
              "cheaply', which is round 11's answer and not a bot.")
    elif verdict == "C":
        print("verdict C — the decision earns nothing at any leverage on this grid. The money here "
              "is the borrowing, and round 11's constant-leverage table is the better document.")
    for lever in LEVERS:
        leg = [t for t in tally if t["lever"] == lever]
        if not leg:
            continue
        print(f"  {lever:.2f}x: clears DCA in {sum(1 for t in leg if t['clears_cheap']):2d}/"
              f"{len(leg)}, beats the worse control in "
              f"{sum(1 for t in leg if t['beats_control']):2d}/{len(leg)} (no-cadence "
              f"{sum(1 for t in leg if t['vs_flat'] > 0):2d}, review-matched "
              f"{sum(1 for t in leg if t['vs_matched'] > 0):2d}), both axes "
              f"{sum(1 for t in leg if t['both_axes']):2d}/{len(leg)} "
              f"[{sum(1 for t in leg if t['both_axes_dear']):2d} at {DESKS[1]}], clears at "
               f"{DESKS[1]} in {sum(1 for t in leg if t['clears_dear']):2d}/{len(leg)}, reversed "
              f"worse in {sum(1 for t in leg if t['vs_rev'] > 0):2d}/{len(leg)}, trend gate earns "
              f"vs none in {sum(1 for t in leg if t['vs_ungated'] > 0):2d}/{len(leg)}; median "
              f"${statistics.median([t['mo_cheap'] for t in leg]):+,.0f}/mo at "
              f"{DESKS[0]}, ${statistics.median([t['mo_dear'] for t in leg]):+,.0f}/mo at "
              f"{DESKS[1]}; median maxDD {statistics.median([t['dd'] for t in leg]) * 100:5.1f}% "
              f"vs flat control {statistics.median([t['dd_flat'] for t in leg]) * 100:5.1f}% and "
              f"unlevered DCA {statistics.median([t['dd_dca'] for t in leg]) * 100:5.1f}%; "
              f"{sum(1 for t in leg if t['calls'])} cell(s) with a margin call"
              + (f", {sum(1 for t in leg if t['ruined'])} ruined"
                 if any(t["ruined"] for t in leg) else ""))
    return verdict


def main() -> int:
    global LEVERS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sleeve", default=None, choices=list(SLEEVES))
    parser.add_argument("--window", default="all", choices=["all", *WINDOWS])
    parser.add_argument("--lever", type=float, default=None,
                        help="one leverage factor instead of the grid")
    args = parser.parse_args()
    if args.lever is not None:
        LEVERS = (args.lever,)

    print("the pre-registered decision rule, run at leverage, billed at posted margin rates")
    print(f"${OPENING:,.0f} opening, ${MONTHLY:,.0f}/month, {BAND:.0%} band, review gate enforced")
    print("vs flat is the gap to a constant book at this run's OWN realized average weight: that")
    print("column, not the gap to DCA, is the timing claim. Desks: "
          + ", ".join(f"{n} {dict(fbe.MENU)[n]:.2%}" for n in DESKS))

    chosen = [args.sleeve] if args.sleeve else list(SLEEVES)
    windows = [args.window] if args.window != "all" else list(WINDOWS)
    tally: list = []
    for window in windows:
        for symbol in chosen:
            try:
                series(symbol, window)
            except ValueError as error:
                print(f"\n{symbol} · {window}: {error}")
                continue
            report(symbol, window, tally)
    if tally:
        reading(tally)
    if not args.lever:                      # the solve needs a grid to interpolate on
        report_dd_match(windows, chosen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
