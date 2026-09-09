# The trend rule's protection has a capacity: about $800 a month per $100,000. Above it, the rule is the riskier leg

Measured 2026-09-07, round 63. Tool: [`insurance_breakeven.py`](../../tools/insurance_breakeven.py) (new). Tests: 13 in
[`test_insurance_breakeven.py`](../../tests/test_insurance_breakeven.py).

Round 58: the trend leg supports 36% more monthly withdrawal than the index. Round 60: with money going in and nothing
coming out, the same leg ends 17% smaller. Round 62: at $435.47 its protection is perfect and free. Those are not three
findings, they are one curve sampled at three points. This round draws the curve: $100,000 in, a level withdrawal for
ten years, nothing added, every payout scored on every window, the whole record sliced four ways so the era effect is
in the data rather than in the machinery.

## The median terminal difference, in $/mo equivalent, against the index

| slice | starts | at $0 | at $435.47 | at $1,000 | median crossover | becomes the **riskier** leg above |
|---|---:|---:|---:|---:|---|---|
| whole record 1993-on | 283 | **+$234.67** | +$163.33 | +$52.83 | already ahead at zero | **$825/mo** |
| 1993–2005 only | 154 | +$586.98 | +$540.35 | +$434.92 | already ahead at zero | never, within $1,500 |
| since 2006 | 129 | **−$687.29** | −$551.57 | −$365.98 | never, on any payout | **$750/mo** |
| 2016-on | 9 | — | — | — | too few windows: reported as untested, not as a zero | |
| static 60/40, any slice | — | −$345 | −$275 | −$228 | never, anywhere | **$275–325/mo** |

Two things fall out, and they are different in kind.

**The sign is a property of the sample, not of the withdrawal.** Over the full record the trend rule leaves more than
the index at *every* payout, including nothing withdrawn. Since 2006 it leaves less at *every* payout. There is no
payout at which the recent sample turns the rule into a winner, and no payout at which the full record turns it into a
loser — which retires the framing that round 58 and round 60 disagreed. They were read off opposite ends of a curve
whose sign is decided by which crashed-decade you include.

**The protection has a capacity, and it is a hard number.** The rule is the *safer* leg at every payout up to
$825/mo per $100,000 (whole record: at $800 it fails 47.3% against the index's 51.6%) and the *riskier* leg above it
(at $1,000: 85.5% against 69.3%). The reason is mechanical, not mysterious: the rule's average growth is lower, so a
large enough withdrawal outruns the shelter it provides. Scaled, that is **$2,063/mo on $250,000, $4,125/mo on
$500,000** — the capacity is proportional to the capital, which is verified rather than assumed.

The asleep control from round 56 holds **a third of that capacity** — it is the riskier leg above $275–325/mo per
$100,000 — and it is never ahead on the median anywhere, at any payout, in any sample. "Buy the bond sleeve instead"
was the right instinct about the *cost* of insurance and the wrong one about its *capacity*.

## One more species of the same reporting error

Round 58's headline was that MA200 supports **$593** a month where the index supports $435. This file reports
**−$551/mo** for the same two legs in the same era. Both are correct: round 58 read the *horizontal* intercept (what
each leg's own maximum withdrawal is at the same failure budget), this file reads the *vertical* gap at a payout the
index can comfortably fund (what is left in the account at $435.47). Same curve, two intercepts, opposite signs. A
verdict that quotes one without saying which is the same failure round 60 recorded about cash-flow direction, one
layer of abstraction higher.

## Checks

13 tests, 4.1 s, offline. Invariants first: windows aligned across legs by start month and 120 long; the year range
honoured and the 2016-onward slice still under 12 starts (so the sample boundary is asserted, not assumed); at zero
withdrawal the only possible failure is ending below where you started, and the failure rate is recomputed
independently in the test and equals the index's published **8.48%** from round 58 twelve rounds earlier; median
terminal never rises as the withdrawal rises, for any leg; failure risk never falls. Homogeneity: doubling the capital
leaves every multiple and every failure rate identical to nine places, and doubles the payout that breaks the
protection (within one grid step). The scans on fabricated series: a leg identical to the index is never called better
and never becomes riskier; a leg earning 0.1%/mo more is ahead at zero; a leg earning half as much never clears the bar
and fails first. The archive: whole-record crossover exactly 0 and 2006-onward `None`; the rule's capacity inside
$750–950/mo and more than double the bond leg's; the 1993–2005 sample never turns the rule into the riskier leg. Full
suite **1787 passed** (collected first: 1774 + 13). `journalctl verify`: chain intact, comparator `100% SPY,
fee 0.000945`, $0.00 paid in.
