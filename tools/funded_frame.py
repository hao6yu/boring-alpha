"""Helpers shared by every funded (monthly-deposit) measurement in this repo.

They live here rather than in `leverage_sizing` because that tool pins the archive it was
written against, and a later round must import the *arithmetic* without inheriting the older
snapshot. Round 6's named failure mode is two simulators drifting apart, so the conversion a
goal-stated-in-dollars depends on is factored out here and asserted to be byte-identical to
what `leverage_sizing` produced before the extraction.

Two things live here, and both exist because the objective is phrased in monthly dollars and
a terminal balance is not one:

  `per_month_equivalent`  — what level monthly amount, compounded at the *comparator's* rate,
                            accumulates to this terminal gap. Discounting at the comparator's
                            rate rather than the candidate's is the whole point: a candidate
                            may not rate its own winnings. A month count below one raises
                            rather than defaulting, because the default would be a large
                            confident dollar figure built on a lost date range.
  `worst_12m_difference`  — the deepest rolling twelve-month hole between two account paths,
                            measured on money that was actually in the market. The floor of an
                            income claim is set by the worst stretch a holder lived through,
                            not by the average, and a terminal gap hides which stretch that
                            was.
"""

from __future__ import annotations

from datetime import date


def per_month_equivalent(gap: float, comparator_irr: float, months: int) -> float:
    """A terminal gap, restated as the level monthly amount it is worth.

    The annuity factor uses the comparator's own IRR, so the conversion prices the extra
    dollars as claims on the same asset the comparator holds. If the rate is effectively
    zero the annuity collapses to a plain division, and dividing is the honest limit rather
    than a division by a number that only looked non-zero.
    """

    if int(months) < 1:
        # A lost date range must not silently become "the gap was worth this much in one
        # month". Every other bug in this file produced a number that read plausibly.
        raise ValueError(f"{months} months of account cannot carry an annuity")
    months = int(months)
    r_month = (1.0 + comparator_irr) ** (1.0 / 12.0) - 1.0
    if abs(r_month) < 1e-12:
        return gap / months
    return gap * r_month / ((1.0 + r_month) ** months - 1.0)


def worst_12m_difference(path: list, reference: list) -> float:
    """The deepest rolling-year gap between a candidate's path and a comparator's.

    Both paths are monthly-deposits-inclusive daily balances, so the flows are identical and
    subtracting them leaves only the difference the strategy made. Deposits are never removed
    from this one, unlike a worst-month figure, because here it is a *difference* between two
    books that received the same money at the same moment; a contribution cancels out of the
    subtraction, it does not flatter it.

    One point per month, the last one seen, on each side, and the two books are intersected
    before stepping so a month either one is missing cannot be compared against a month the
    other has. Twelve steps that span more than thirteen days short of fourteen months are
    skipped rather than reported: a hole in a thin sleeve is not a bad year, and calling it
    one overstates the difference by the length of the hole.
    """

    def monthly_ends(series: list) -> dict[tuple[int, int], float]:
        out: dict[tuple[int, int], float] = {}
        for stamp, value in series:
            out[(stamp.year, stamp.month)] = value
        return out

    cand = monthly_ends(path)
    base = monthly_ends(reference)
    keys = sorted(set(cand) & set(base))
    if len(keys) < 13:
        return 0.0

    def difference(month: tuple[int, int]) -> float:
        return cand[month] - base[month]

    worst = 0.0
    for index in range(12, len(keys)):
        start, end = keys[index - 12], keys[index]
        span_days = (date(end[0], end[1], 1) - date(start[0], start[1], 1)).days
        # Only an upper bound, and the reason is structural rather than cautious: the grid is
        # collapsed to one point per month, so thirteen keys are thirteen *distinct* months
        # and the shortest twelve steps between them is a run of consecutive months, about
        # 365 days. A lower bound here is unreachable code, and it was written before that
        # was noticed. An archive with holes, which is what a thin sleeve actually is, moves
        # the other way — twelve steps can quietly span fourteen or fifteen months — and a
        # fifteen-month hole reported as a twelve-month hole overstates a bad year by a
        # quarter. So: skip windows that are not approximately a year.
        if span_days > 400:
            continue
        worst = min(worst, difference(end) - difference(start))
    return worst
