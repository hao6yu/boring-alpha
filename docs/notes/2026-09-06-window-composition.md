# The window is doing half the work, and last round's explanation for it was wrong

Measured 2026-09-06, round 39. Tool: [`combined_account.py`](../../tools/combined_account.py) (`common_months`);
tests [`test_combined_account.py`](../../tests/test_combined_account.py) (9).

## What last round claimed

Round 38 closed with the loan's edge quoted two ways — **+2.48%/yr** on VOO and **+1.63%/yr** on SPY — and explained
the 0.85%/yr difference as *fund selection*: "which near-identical fund the tool happened to name", invoking round
18's noise floor, and pinned with a test asserting the difference exceeded five times the fee gap. The test passed.

The test passed because it was comparing 404 months against 192.

## The precondition nobody checked

| series | months | first session | expense |
|---|---:|---|---:|
| SPY | 404 | 1993-01-29 | 0.09% |
| QQQ | 330 | 1999-03-10 | 0.20% |
| VTI | 303 | 2001-06-15 | 0.03% |
| ITOT | 272 | 2004-01-23 | 0.03% |
| VOO | **192** | **2010-09-09** | 0.03% |

The archive's series do not start together, by design. VOO — the fund the goal named — begins **September 2010**,
inside the strongest sustained bull market in the record, and so never sees dot-com or 2008. SPY carries both. Any
comparison that changes the symbol and does not pin the sample is therefore comparing **decades while pretending to
compare funds.**

On the **common 192 months**, SPY and VOO give **+2.460%** and **+2.484%** — differing by **0.024%/yr, which is
tighter than the 0.065% fee gap between them.** That is the behaviour two funds tracking one index are *required* to
exhibit, and it is the opposite of what round 38 asserted and tested for.

## What the window is actually worth

The same fund, the same policy, the same financing, two samples:

| sleeve | months | own window | common window | expense |
|---|---:|---:|---:|---:|
| SPY | 404 | +1.63% | **+2.46%** | 0.09% |
| VOO | 192 | +2.48% | +2.48% | 0.03% |
| QQQ | 330 | +1.98% | **+3.56%** | 0.20% |
| VTI | 303 | +1.42% | **+2.43%** | 0.03% |
| ITOT | 272 | +1.64% | **+2.43%** | 0.03% |

**Every sleeve looks better on the common window than on its own**, because the common window is the recent one and
the recent one is kind to levered equity. For SPY the shift is **+0.83%/yr — half the edge.** And on the shared
window the four *broad-market* funds collapse into **2.43%–2.48%**, a five-basis-point band, exactly as four funds on
broad indexes must. QQQ's **+3.56%** is the only outlier, and it is QQQ — a concentrated tech index that genuinely
out-earned the others in that window — while charging **0.20%**, the most expensive line in the menu.

So the honest statement of the plan is now two numbers rather than one: **the 1.25× book is worth about +2.45%/yr on
any broad index over the last sixteen years, and about +1.6%/yr across each fund's full history**, and the difference
between them is a statement about the calendar. The sign is robust everywhere. The magnitude belongs to a window.

## Why this error survived a passing test

Unequal windows do not throw an exception. They produce **plausible numbers** — +2.48% and +1.63% are both real
measurements of real things — and an explanation that *sounds* right ("it's the fund, the fee can't explain it, so
it must be splicing noise") closes the loop. The test written to confirm that explanation passed, because a test
that asserts a difference between two unequal samples will always find one. Nothing in the suite could have caught
this; only noticing that the two runs reported different month counts did, and both counts had been printed all
along.

The generalisable rule: **a cross-series comparison must assert the sample is shared before it asserts anything
about the difference.** That is now a precondition test (`test_the_archive_does_not_hand_every_symbol_the_same_window`)
rather than a hope — if the series are ever aligned upstream, it fails loudly instead of letting the wrong conclusion
quietly become correct.

## What this changes in the project's conclusions

Nothing about the composition stands or falls on it. Cash loses monotonically, the switch is worth exactly zero at
w = 1.0, the loan and the switch are one exposure to the rate curve, and **only borrowing beats holding the index** —
all of that holds on every window and every sleeve in the table. What changes is what the headline number means, and
the direction of the doubt: round 38 worried the edge was soft because of fund choice. It is soft because of era —
which is the larger and less fixable problem, since a fund can be chosen and a decade cannot.

## Checks

9 tests, 0.4 s, offline: the archive must **not** hand every symbol the same window (404 vs 192, differing by more
than 100 months — if that ever stops being true this test fails rather than the conclusion quietly flipping); on a
shared window the two funds must agree **to within their fee gap** and under 0.1%/yr, the direct negation of the
claim this round removed; the era must move the edge by more than half its size; and `common_months` must return the
**shortest** series, not the longest. Full suite: **1536 passed, 233 subtests**. `journalctl verify`: chain intact
(1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.
