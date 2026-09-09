# One start date was the whole result

Goal round 4 (of 96), `goal-91eb485f…`. BA-006's 20% sleeve was the first candidate in 113 rounds to beat the index on the *promise* rather
than merely out-earning it: +25.8% affordable bill, P(erase) 0%, 0.9 points more drawdown. The fee record withholds the PASS (condition 5),
which gave this round an obvious job that does not need anyone's fee number: find out how much of that row is the fact that the archive
happens to start in 2016.

## The ladder, printed with the verdict

Same test, same gates, same weights, whole-year-later starts, every rung printed unconditionally:

| start | months | P0 bill | 5% sleeve | 10% sleeve | 20% sleeve |
| --- | --- | --- | --- | --- | --- |
| 2016-05-18 (locked) | 122 | $831 | $919 (+11%, fails seatbelt) | $980 (+18%, fails seatbelt) | **$1,045 (+26%, clears)** |
| 2018-05-18 | 98 | $872 | $931 (+7%, fails seatbelt) | $932 (+7%, fails seatbelt) | $925 (+6%, fails seatbelt) |
| 2020-05-18 | 74 | $899 | $902 (+0%, fails bill, seatbelt) | $902 (+0%, fails bill, seatbelt) | $893 (−1%, fails bill) |

> a clearing weight appears at 2016-05-18 and nowhere at 2018-05-18, 2020-05-18; a decision made today sits closer to the later starts than
> the earlier ones.

So the answer to "is the sized sleeve a property of the rule or of the window?" is: **of the window, and of one window at that.** The
sleeve's entire advantage is bitcoin's 2016-2021 run — from 2018 the sleeve adds 6-7% at every weight and the *largest* weight does worst, every weight there failing the seatbelt;
from 2020 it adds nothing and at 20% it goes backwards. The two windows nearest a decision someone could actually make now contain no clearing
weight at any rung. And the seatbelt — the model versus just holding the coin — fails on every roll that has enough months in it, which is the
round-3 finding with support now rather than once.

## The bug in the disclosure, which was the round's best catch

The first version of the summary line compared each roll's *raw bill gain* against the 5% margin and reported "the gain survives at
2016-05-18, 2018-05-18". That was wrong in the specific direction that matters: the 2018 roll does gain 6-7% on some weight, and does **not**
clear the gates — every weight there fails the seatbelt, and at 20% it fails drawdown too. A looser copy of a threshold is a different
threshold, and it had flattered the result in exactly the paragraph written to be honest about it. There is now one `gates()` function, three
callers (table, ladder, summary), and a test that the zero-roll matches the graded table to the dollar.

I also built `--sensitivity`, and removed it. A switch that hides the sentence undermining the headline is not a disclosure; the test suite
now asserts the flag does **not** exist in the source, and that every rung appears at every weight on every run.

## What this says about the objective, and what it does not

It does not revoke anything: the locked conditions are untouched, exit 3 stands, and if a fee record arrives and 20% still clears at the real
cost, the licence is as written — a fifth book carrying both legs. What changed is the expectation attached to it, pre-registered in the spec
rather than negotiated later: **the forward book is expected to show no improvement over P0's affordable bill.** A flat first seal is then the
predicted outcome, not a surprise needing an excuse.

What it says about the money question is the thing the objective should hear plainly, and it is the same sentence the equity archive has now
produced in three asset classes: the way to not be worse than plain VOO/QQQ is to hold plain VOO/QQQ. If a Coinbase account wants crypto
exposure, the honest evidence frames that as a size decision the individual makes directly — a capped slice, no signal attached — because on
this record the 200-day rule added −$23, $0, +$17 a month against simply holding the same slice, and the slice's own advantage appeared only
when the clock starts in 2016.

## Loop integrity, checked rather than assumed

With the corpus and tools having grown twice since the last look, step 5's machinery was verified read-only: `monthly.py --dry-run` plans all
13 commands and correctly reports every book `not due: corpus ends 2026-09-04, book 'root' already closed at 2026-09-04`;
`journalctl.py verify` returns `ledger: chain intact (1 entries)` and `comparator: pinned spec intact (100% SPY, fee 0.000945)`;
`forward_p0.py --status` still says three of four stopping conditions are `not decidable` because the programme is three weeks old. First real
seal 2026-09-30, 23 entries to a skill claim — unchanged, and still the only forward evidence this objective has.

## Checks

**2420 passed, 239 subtests** (2416 + 4 new; collected count printed before the run). Rules: **114**. Files: `tools/ba006.py` (one `gates()`
for everything, ladder printed unconditionally), `tests/test_ba006.py` (16→20), `docs/strategies/BA-006.md` (disclosure section, gates
untouched).

*Goal round 4. The best Coinbase result in this repository is one start date wide, the disclosure that found it has no off switch, and the
honest answer to the objective is converging on the boring one.*
