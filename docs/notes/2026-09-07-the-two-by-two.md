# The rule's protection lands in 56 of 56 places it was needed, at zero cost — and all 56 entries sit inside one episode

Measured 2026-09-07, round 62. Tool: [`entry_state.py`](../../tools/entry_state.py) (new). Tests: 16 in
[`test_entry_state.py`](../../tests/test_entry_state.py).

Two claims survived rounds 55 to 61 and both are about shape, not average return: round 58's trend leg supported 36%
more monthly withdrawal, and round 60's long record found 4.2% of 10-year windows left a contributor with less than
they deposited while the trend rule had none. An average over 283 windows is the wrong statistic for a person who will
live through exactly **one** entry. So this round scores every entry month separately and cross-tabulates it against
the index:

| | rule survives | rule fails |
|---|---|---|
| **index fails** | insurance — the only cell that pays for a risk claim | redundant — cost, no shelter |
| **index survives** | fine | cost — protection bought and not used |

## Withdrawal frame: $435.47 a month from $100,000, 10 years, 283 entry months (1993-03 → 2016-09)

The index plan failed in **56 of 283 entries (19.8%)**.

| leg | insurance | redundant | cost | fine | P(fail) | P(fail \| index fails) |
|---|---:|---:|---:|---:|---:|---:|
| SPY hold | 0 | 56 | 0 | 227 | 19.8% | 100% |
| **MA200 monthly** | **56** | **0** | **0** | 227 | **0.0%** | **0%** |
| static 60/40 | **0** | 56 | **65** | 162 | **42.8%** | 100% |
| `ma200_and_gate` | 45 | 11 | 34 | 157 | 18.2% | 20% |

The trend rule insureds every single entry the index broke, and fails in no entry the index survived. At this fixed
payout the medians happen to point the same way (index 1.55×, rule 1.75×, 60/40 1.22×) — but they need not have, and
round 60 measured the other way at no withdrawal, where the rule ends 17% smaller on the panel. The cells are the
statistic for a plan you live once; a median is what the average of 283 different lives looks like.

## Contribution frame: $1,000 a month from nothing, failure = ends below what was deposited

Index failed in 12 of 283 (4.2%, matching round 60 through a second implementation).

| leg | insurance | redundant | cost | P(fail) | concordance |
|---|---:|---:|---:|---:|---:|
| MA200 monthly | **12** | 0 | 0 | 0.0% | 0% |
| static 60/40 | 3 | 9 | 0 | 3.2% | 75% |

## A table that neat has to be doubted, so it was doubted

* **The payout ladder.** A leg that never fails may be a leg nobody scored. Raising the payout moves the count
  immediately: **0** failures at $435.47, 33 at $600, 134 at $800, 262 at $1,100. The zero is one rung below where the
  failures start, not an absence of measurement.
* **Direct counts match the cells**: 56 index failures, 0 rule failures, computed outside the contingency function.
* **Round 60's 4.2% reappears** from this file's own simulation loop — two implementations of the same plan, one number.
* **The worst three entries** for a payout are 2000-09, 2000-07 and 2000-04: the index ends at 0.29×–0.34× and fails;
  the rule ends at 1.19×–1.28× and survives; the 60/40 ends at 0.45×–0.50× and fails.

## The caveat that keeps this from being the round that found the answer

**All 56 failing entries fall between 1998-02 and 2007-07, and 54 of the 56 (96%) started in 1998-2002.** One
episode, one protection. Since 2007 no 10-year entry at this payout has broken the index plan at all, which is also
why round 59 found the trend rule *losing* in the 2016-onward era: the leg that would have insured those entries has
had nothing to insure. Perfect protection in a record that needed it once is a real property of this archive and a
weak basis for an expectation.

Two further readings the table forbids:

* **Round 58's asleep control is pure cost here.** static 60/40 has 0 insurance, shares all 56 index failures and adds
  65 of its own (42.8% overall). "It pays $569/mo on the median" and "it fails twice as often as the index" are the
  same fact: it is the lower-average-return, lower-tail-leg member of the pair.
* **The macro overlay turns insurance into cost.** `ma200_and_gate` keeps 45 of the 56 saves and introduces 34 entries
  where it fails and the index did not — 13.8% cost, and its own failure rate is 18.2% against MA200's 0.0%.

## Checks

16 tests, 1.9 s, offline. The synthetic cases come first and *define* the cells: a leg built to fail exactly when the
index fails must land in `redundant` with concordance 1.0; a leg that never fails must be pure insurance with
concordance 0.0; a clone of the index must produce `insurance = 0, cost = 0`; a leg that always fails must fill the
cost cell with the benchmark's non-failures; concordance must be `None` rather than 0 when the benchmark never fails.
Then the archive: cells partition the start set for every leg; **56 insurance / 0 redundant / 0 cost** for the trend
rule in the payout frame; the payout ladder strictly increasing with a non-zero first rung; the index's failing starts
confined to 1998-2007 with ≥90% in 1998-2002; the 60/40 holding zero insurance and a cost cell above 30; the
contribution frame reproducing 12 failures and 4.2% exactly; the three worst payout entries still the year 2000 and
still under 0.40×; and the CLI refusing to drop the reference leg or accept an invented one. Full suite
**1774 passed** (collected first: 1758 + 16). `journalctl verify`: chain intact, comparator `100% SPY, fee 0.000945`,
$0.00 paid in.
