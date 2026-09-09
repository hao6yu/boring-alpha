# What beats VOO is the withdrawal, not the return — and a static 60/40 loses to VOO on both

Measured 2026-09-07, round 68. Tool: [`correction_table.py`](../../tools/correction_table.py) (new). Tests: 11 in
[`test_correction_table.py`](../../tests/test_correction_table.py).

Round 66 moved the flagship income figure down by up to $104/mo, and it was not the only figure sitting on that
convention. This file re-measures every construction the repository has published a claim about, on two records and both
readings of "monthly", and prices each against **the index over exactly its own dates** — the discipline round 66 showed
matters more than the sample, since a delta between two date sets is not a delta between two strategies.

The axis is named in every cell, because the objective says "beat VOO" and there are two ways to mean it. On **total
return** nothing in this repository has beaten it: 0 of 26 configurations, best information ratio −0.01 (round 61). On
**withdrawal capacity** — what a plan can pay monthly and still keep its promise in 95 of 100 ten-year windows — some
things do, and the reason they can is that they remove the *order* returns arrive in rather than their average.

| construction | shelter | signal | windows | safe $/mo | index, same dates | delta | P(fail) @435.47 | index P(fail) | capacity |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| **long record, from 2002-08** | | | | | | | | | |
| 100% SPY | — | — | 169 | **436.76** | 436.76 | +0.00 | 4.1% | 4.1% | — |
| MA200 | bills | start | 169 | 494.11 | 436.76 | +57.34 | 0.0% | 4.1% | $700 |
| MA200 | bills | end | 169 | 530.91 | 436.76 | +94.15 | 0.0% | 4.1% | $750 |
| **MA200** | **IEF** | **start** | 169 | **567.22** | 436.76 | **+130.46** | **0.0%** | 4.1% | **$775** |
| **MA200** | **IEF** | **end** | 169 | **581.64** | 436.76 | **+144.88** | **0.0%** | 4.1% | **$850** |
| static 60/40 | bills | — | 169 | **353.23** | 436.76 | **−83.53** | **30.2%** | 4.1% | $350 |
| static 60/40 | IEF | — | 169 | 498.97 | 436.76 | +62.21 | 0.0% | 4.1% | $575 |
| **panel, from 2006-02** | | | | | | | | | |
| 100% SPY | — | — | 127 | **435.47** | 435.47 | +0.00 | 5.5% | 5.5% | — |
| MA200 | bills | start | 127 | 489.62 | 435.47 | +54.16 | 0.0% | 5.5% | $650 |
| MA200 | bills | end | 127 | 527.08 | 435.47 | +91.61 | 0.0% | 5.5% | $650 |
| MA200 | IEF | start | 127 | 562.70 | 435.47 | +127.24 | 0.0% | 5.5% | $675 |
| MA200 | IEF | end | 127 | 571.06 | 435.47 | +135.59 | 0.0% | 5.5% | $725 |
| static 60/40 | bills | — | 127 | 351.72 | 435.47 | −83.74 | 19.7% | 5.5% | $350 |
| static 60/40 | IEF | — | 127 | 498.97 | 435.47 | +63.51 | 0.0% | 5.5% | $575 |

Three things in this table were not known before it was assembled.

**The premium is real and about a third the size it was quoted at.** The trend rule's published income advantage over the
index was $157.66/mo per $100,000. Warmed, on the same panel, it is $54.16 or $91.61 depending on which day of the month
you read the trend on. With the IEF shelter and on the longer record — the honest cell — it is **+$130.46 to +$144.88**,
which is a 30-33% lift in what the plan can pay, and the ranking is the same under every convention and on both records.
Scaled to $250,000 that is **+$326 to +$362 a month**.

**A static 60/40 with the bond half in bills is worse than holding VOO**, on both records: **−$83.53/mo** of capacity
and a failure rate of **30.2%** against the index's 4.1% on the long record (19.7% vs 5.5% on the panel). Diversifying a
fifth of the account into an asset earning the bill curve costs you withdrawal capacity, because it lowers the mean
without removing the sequence. This is the same number that makes round 62's verdict on 60/40 legible: it has zero
insurance *and* negative capacity. Note the sign flips entirely when the off-equity half is IEF instead of bills: same
weights, +$62.21/mo, **0.0%** failure, $575 of capacity — the cheapest thing in the table that clears the index, and it
needs no signal at all.

**The axis explains how both findings are true at once.** Look at the two P(fail) columns with the delta column. The
trend rule loses on average return (round 61) and fails in **none** of 169 windows where the index fails in seven: what
it removes is *when* the bad years land relative to the withdrawals, not how much they cost. That is why it can support a
larger monthly payment while compounding to less. Anyone comparing these strategies on terminal wealth will get the
opposite answer, and be right on that axis.

## Checks

11 tests, 7.5 s, offline. The index row on the panel must come back at **$435.47** — that is round 58's payout figure,
which *was* the index's safe withdrawal, so the table and the repository's oldest published number are the same number by
construction. The long-record index is pinned at $436.76 over 169 windows. The correction has to move the flagship
premium **down**, never up, from the published 157.66. The verdict thresholds are constants in the tool (`BAR = 25`,
round 60's), not prose: the signal alone is material but under $100, the shelter is what carries it over, on both records
under both conventions. The naive-60/40 row is pinned to be negative *and* to fail more often than the index, so nobody
can reintroduce it as the cautious option. Every row within a record shares its date set (asserted), an undeclared
construction raises rather than defaulting to cash, and loosening the failure budget never lowers a safe amount. Full
suite **1851 passed** (collected first: 1840 + 11). `journalctl verify`: chain intact, comparator `100% SPY, fee
0.000945`, $0.00 paid in.
