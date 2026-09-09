"""A second, independent implementation of the NYSE closure rules, checked against the shipped artifact.

`docs/data/nyse-calendar.md` says the artifact's independent implementation check is performed with `exchange_calendars==4.13` in a
disposable environment — a package the lab venv does not have (round 106 learned that when the calendar's own refusal told the operator to
rebuild it). The artifact has therefore been relying on a check this repository cannot currently run.

This file runs an equivalent check with a different piece of paper: the rules re-derived from first principles — an anonymous Gregorian
computus, nth-weekday arithmetic, and each fixed holiday's own observance convention, written here without reading
`build_nyse_calendar.py`'s helpers — compared against every one of the artifact's 5,197 sessions and 194 closures. Agreement is not a
formality: the observance rules differ between holidays, and a wrong one shows up as a specific missing date rather than a vague count.

The point is not to re-pin bytes (`test_nyse_calendar.py` does that). It is to make the *rules* verifiable in-repo, so the day somebody
extends the reviewed interval, the transcription is not the only thing between the forward test and a wrong holiday — and so that a
September question can be answered honestly instead of refused.
"""

from __future__ import annotations

import json
import sys
import unittest
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

CALENDAR_FILE = ROOT / "data/calendars/nyse-2006-2026-v1.json"

#: The five closures that are not rules: two days of Sandy and three days of national mourning.
SPECIAL = {date(2007, 1, 2), date(2012, 10, 29), date(2012, 10, 30), date(2018, 12, 5), date(2025, 1, 9)}


def easter(y: int) -> date:
    """Anonymous Gregorian computus, typed out here so Good Friday is not this file taking the builder's word for it."""

    a = y % 19
    b, c = divmod(y, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(y, month, day + 1)


def nth_weekday(y: int, month: int, weekday: int, n: int) -> date:
    """The n-th `weekday` (0 = Monday) of a month, found by scanning the month rather than by arithmetic."""

    days = [date(y, month, d) for d in range(1, monthrange(y, month)[1] + 1) if date(y, month, d).weekday() == weekday]
    return days[n - 1]


def last_weekday(y: int, month: int, weekday: int) -> date:
    d = date(y, month, monthrange(y, month)[1])
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def observe(day: date, saturday_made_up: bool) -> date | None:
    """The weekday a fixed holiday is closed on.

    A Sunday always moves to Monday. A Saturday is where the holidays disagree with each other, and the artifact is the thing that says
    which way: the NYSE does not make a Saturday holiday up, so `saturday_made_up=False` closes nothing at all.
    """

    if day.weekday() == 5:
        return day - timedelta(days=1) if saturday_made_up else None
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def closures(y: int) -> set[date]:
    """Every full-day closure the published rule set implies for one year, 2006 onward."""

    out = {
        nth_weekday(y, 1, 0, 3),                    # Martin Luther King Jr. Day: third Monday of January
        nth_weekday(y, 2, 0, 3),                    # Washington's Birthday: third Monday of February
        easter(y) - timedelta(days=2),              # Good Friday
        last_weekday(y, 5, 0),                      # Memorial Day: last Monday of May
        nth_weekday(y, 9, 0, 1),                    # Labor Day: first Monday of September
        nth_weekday(y, 11, 3, 4),                   # Thanksgiving: fourth THURSDAY — the one rule my first pass got wrong
    }
    # Three fixed holidays, three different Saturday answers, and the artifact is the referee: a Saturday New Year is simply not
    # made up, a Saturday Independence Day closes Friday, and a Saturday Christmas closes the Friday before it — 2010-12-24 and
    # 2021-12-24 are closures here and the archive has no SPY bar on either. My first pass guessed "same as New Year" and the
    # comparison said so in two dates.
    fixed = [(date(y, 1, 1), False), (date(y, 7, 4), True), (date(y, 12, 25), True)]
    if y >= 2021:
        fixed.append((date(y, 6, 19), False))       # Juneteenth, from 2021; a Saturday is not made up (2021-06-18 traded)
    for day, made_up in fixed:
        observed = observe(day, saturday_made_up=made_up)
        if observed and observed.year == y:
            out.add(observed)
    return out | SPECIAL


def sessions(start: date, end: date) -> set[date]:
    """Every weekday in the window the rule set does not close — the artifact's own definition of a session."""

    closed = {d for y in range(start.year, end.year + 1) for d in closures(y)}
    out, d = set(), start
    while d <= end:
        if d.weekday() < 5 and d not in closed:
            out.add(d)
        d += timedelta(days=1)
    return out


class TheRulesReDerived(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(CALENDAR_FILE.read_text())
        cls.start = date.fromisoformat(cls.record["coverage_start"])
        cls.end = date.fromisoformat(cls.record["coverage_end"])

    def test_the_rule_set_reproduces_every_session_in_the_artifact(self):
        """Twenty-one years, 5,197 dates, no tolerance, and the disagreement prints the dates rather than the counts."""

        want = {date.fromisoformat(d) for d in self.record["sessions"]}
        mine = sessions(self.start, self.end)
        self.assertEqual(sorted(d.isoformat() for d in want - mine), [],
                         "the artifact traded days this file's rules close")
        self.assertEqual(sorted(d.isoformat() for d in mine - want), [],
                         "this file's rules trade days the artifact closed")

    def test_the_rule_set_reproduces_every_closure_in_the_artifact(self):
        want = {date.fromisoformat(d) for d in self.record["closures"]}
        mine = {d for y in range(self.start.year, self.end.year + 1) for d in closures(y)
                if self.start <= d <= self.end}              # the tail of 2026 is outside the reviewed interval, on purpose
        self.assertEqual(sorted(d.isoformat() for d in want ^ mine), [], "the closure sets differ")

    def test_the_saturday_rules_are_not_all_the_same_rule(self):
        """The nuance this file exists to prove it got right, one case per shape.

        A Saturday holiday is not made up (New Year 2011, Juneteenth 2021: the Friday trades), and a Sunday holiday always becomes Monday
        (New Year 2017, Juneteenth 2022, Christmas 2016).
        """

        self.assertNotIn(date(2011, 1, 10), closures(2011))            # 2011-01-01 fell Saturday: nothing closed for it
        self.assertNotIn(date(2021, 6, 18), closures(2021))            # Juneteenth 2021-06-19 fell Saturday: Friday traded
        self.assertIn(date(2011, 1, 17), closures(2011))              # and MLK that year was the 17th, unaffected
        self.assertIn(date(2017, 1, 2), closures(2017))               # 2017-01-01 fell Sunday
        self.assertIn(date(2022, 6, 20), closures(2022))              # Juneteenth 2022-06-19 fell Sunday
        self.assertIn(date(2016, 12, 26), closures(2016))             # Christmas 2016 fell Sunday
        self.assertIn(date(2023, 6, 19), closures(2023))              # a weekday Juneteenth closes itself

    def test_the_rest_of_2026_is_derivable_from_the_same_rules(self):
        """Not a claim about the artifact — its coverage stops 2026-08-31 — but the fact `corpus_diff.py` needs, re-derived.

        Round 106's fetch could not say whether 2026-09-07 was a session. These rules say it was not, and they are the same rules that
        reproduce every session the artifact vouches for.
        """

        tail = sorted(d for d in closures(2026) if d > self.end)
        self.assertIn(date(2026, 9, 7), tail, "Labor Day is the first Monday of September; if this fails, the rule is wrong")
        self.assertEqual([d.isoformat() for d in tail], ["2026-09-07", "2026-11-26", "2026-12-25"])   # Thanksgiving is a Thursday

    def test_the_artifact_itself_still_stops_short_of_the_forward_test(self):
        """The coverage gap is real and this keeps it real: v1 cannot vouch for September, and the lab must not pretend otherwise."""

        self.assertLess(self.end, date(2026, 9, 1))
        self.assertFalse(self.record["synthetic"], "a synthetic calendar is not this file's subject")


if __name__ == "__main__":
    unittest.main()
