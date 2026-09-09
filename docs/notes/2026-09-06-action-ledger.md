# The action ledger: twenty-eight rounds, one table, and the column nobody asked for

Measured 2026-09-06, round 28. Tool: [`action_ledger.py`](../../tools/action_ledger.py), tests
[`test_action_ledger.py`](../../tests/test_action_ledger.py) (7).

Nothing new was measured this round, and that is the point. Twenty-seven rounds of single verdicts had produced
a file series with an unusual property: every note was honest and almost none of them disagreed, so the
*aggregate* had never been read. `--verify` re-derives the two rows that are cheap to recompute, and the rest
are transcribed from the notes, with each row citing the round it came from. This is a table of record.

| action | $/mo at $20k | variance | round |
|---|---:|---|---|
| move idle cash out of the default sweep | **+46.12** | none | 24 |
| hold the cheapest share class of the same index | **+1.07** ⚠ | none | 18, 38 |
| reinvest distributions promptly | +0.01 | none | 27 |
| the rule as configured, cap 1.3× | −4.10 | substantial | 25 |
| the same rule unlevered, cap 1.0× | −21.15 | substantial | 26 |
| monthly nine-sleeve momentum rotation | −231.00 | substantial | cross-section |
| directional timing at any faster cadence | measured no | substantial | 2, 13, 14 |

## Why the table is sorted by dollars and must be read by variance

The second column is what people ask for. The third is what decides it, and round 23 is the reason it exists
here rather than in a footnote: at this account size, **a stochastic edge of the magnitude this repository has
ever found cannot be observed**. The paper book resolves roughly 6%/yr at month 60 against a candidate worth
0.4%/yr, and that ratio does not improve with money — an edge and its own noise both scale with capital, so
fifty times the deposits buys fifty times the standard deviation and a resolution 4.5 years down the calendar.

So the two rows that are actually *actions* are the two with `none` in the variance column, because they are the
only ones whose outcome the owner can verify inside a month: a quoted sweep rate on a statement, and a fund's
expense ratio, both arithmetic on a balance. Everything below them in the table is either a preference about
drawdown or a documented failure. The idle-cash row is worth **$46.12/mo** and the second-ranked positive row
is worth $1.07 **with no variance at all**, so the honest ordering is not the dollar ordering at all.

> **Amended in round 38.** This row read **+25.00** for nine rounds and is quoted that way in three other
> notes. The $25 was round 18's *noise floor* — the size of the artefact produced by naming SPY rather than VOO
> as the comparator — and it was transcribed into the ledger as though it were the value of the action. The action
> is worth the expense ratio and nothing else: **6.45bp, $12.90 a year, $1.07 a month on $20,000**. The floor and
> the prize were never the same quantity; conflating them inflated the row 23× and, worse, made a certain fee
> saving look like a variance-bearing estimate. Ledger totals moved: certain actions $46.13 → **$47.20/mo**,
> positive stochastic actions $52.24 → **$27.24/mo**. The row is now derived from `wc.EXPENSE` at import and
> re-printed by `--verify`, so it cannot silently disagree with the fee table again.

Read it as a bot specification and the finding sharpens. Everything in this repository that could plausibly be
called a *trading bot* — faster cadence, rotation, volatility targeting, trend gates, leverage — is on the
losing side of the table or unmeasurable. What survives is closer to a **housekeeping bot**: move settlement
cash to a bill fund on the first of the month, hold the cheap share class, and leave the equity exposure alone.
The goal as stated was "a trading model that beats VOO and QQQ"; what the archive supports is "an
optimisation-of-everything-else model that beats VOO by 0.28%/yr before any market view at all". That is a
different sentence and it deserves to be said out loud rather than left as the sum of twenty-eight notes.

## `--verify`, and why a summary table needs one

A summary table outlives the analysis that justified it and keeps its authority after its numbers rot. So two
rows are re-derived from the archive on demand, and both are pinned by tests:

```
unlevered rule vs the index: -1.27%/yr = $-52.87/mo at $50,000 (the row says -21.15 at $20,000)
static control at the same mean weight (0.843): -1.78%/yr
```

The first line caught a real bug in this file on its first run: an earlier version of the print re-derived
`$/mo` from the annualised percent by hand and divided by twelve twice, which would have printed −$52.87 against
a row of −$21.15 at the *same* capital and looked like a discrepancy of 2.5× rather than of a factor of twelve.
It now uses `unlevered_timing.run()["mo"]`, which is the figure the note published, computed in the place that
owns it. A duplicated derivation is a second place to be wrong; where the first version of a `--verify` flag
disagrees with the row it is checking, the flag is usually the liar, and it is worth finding out on the first
run rather than after the table has been quoted somewhere.

The 7 tests are mostly about the table's ability to stay honest: the variance labels come from a closed set
rather than free prose; a row may not claim `none` variance without a point estimate; the positive rows are
asserted to be exactly three and all cost-shaped, so a fourth positive row cannot appear without a round being
cited; the dollar column is linear in capital to twelve places; and the timing premium that the rule's caveat
relies on must stay inside **+0.30% to +0.70%/yr**, tight on purpose, since a band that would pass at +5%/yr is
not testing the claim the caveat makes.

## Checks

7 new tests, 0.2 s. Full suite: **1462 passed, 233 subtests** (1455 before these seven), collected count and
run count both 1462 and confirmed by a second consecutive run. `journalctl verify`: chain intact (1 entry),
comparator `100% SPY, fee 0.000945`, $0.00 paid in — the ledger changes no measurement, so the sealed record is
expected to be untouched and is.

> **Restated in round 47.** The spot bill yield quoted in this note (**2.88%**, and the **+$46.12/mo** built from
> it, and the "55th percentile of the record") was computed by annualising the last three monthly buckets of the
> cash curve — and the last of those was a **four-day stub**: the archive seals after a session, and the September
> 2026 bucket held trading days 1-4 only. Compounding a four-day accrual as a month pulled the spot down **103bp**.
> On complete months the archive's own last full month is **3.81%**, the three-month spot is **3.91%**, the switch
> is worth **+$63.34/mo** at $20,000, and today sits at the **65th** percentile — *above* the record median, not
> below it. Every distribution figure in these notes (mean $39.85, median $33.72, quartiles) moved by pennies;
> only the spot and the percentile it was compared against were wrong. See
> [`2026-09-06-the-seal-is-not-a-month.md`](2026-09-06-the-seal-is-not-a-month.md).
