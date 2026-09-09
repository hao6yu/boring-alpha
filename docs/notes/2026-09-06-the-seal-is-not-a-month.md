# The seal is not a month: the spot bill yield was a four-day stub, and the switch is worth $63 not $46

Measured 2026-09-07, round 47. Tools: [`cash_yield_gap.py`](../../tools/cash_yield_gap.py) (`last_business_day`,
`cash_months`, `sweep_sensitivity`), [`action_ledger.py`](../../tools/action_ledger.py) (`rows`, `switch_row`).
Tests: 34 in `test_cash_yield_gap.py` (+6), 13 in `test_action_ledger.py` (+2).

## Two findings, one of which is against myself

### 1. A published spot rate was computed over a partial month

`cash_yield_gap.bill()` annualises a window by taking the mean monthly cash factor and compounding it twelve times.
The archive seals after each session, so its **final month is usually a stub**: at the 2026-09-04 seal, the
September bucket held four trading days, and `wc.monthly` emitted it as one observation — an annualised **0.73%**
where July read 3.98% and August 3.81%.

So `current3m` averaged July, August and four days of September and reported **2.88%**, where the curve's own last
complete month says 3.81%. **103bp, from a calendar artefact.** Everything downstream inherited it:

| | published | corrected |
|---|---:|---:|
| spot bill yield | 2.88% | **3.91%** |
| the switch at $20,000, today | +$46.12/mo | **+$63.34/mo** |
| percentile of the record | 55th, *"below the median"* | **65th, above the median** |
| months in the record | 404 | **403** |
| mean / median / quartiles | $39.85 / $33.72 | $39.92 / $33.72 (pennies) |

The distribution work was safe; **the spot and the one sentence built on it were not**. "Today's bill yield sits at
the 55th percentile, below the median of the record" was the file's own way of saying *this is not a good time* —
and it was an artefact of four days of September. Today is a **good** time: the switch is at the 65th percentile of
33 years, worth ~$63/mo on $20,000, near the top of its range.

Note the direction, because it matters for how the mistake should be read: the defect **understated** the
repository's top-ranked action by 37%. A wrong number that flatters your thesis gets checked eventually by someone
else; one that hurts it gets believed. The fix is structural, not editorial — `cash_months()` drops any trailing
bucket whose month has not finished, judged from the calendar (`last_business_day`), and `bill()`, `path()`,
`contingency()` and `bear_sweep()` all read it.

And the same habit bit the ledger for the second time: its first row carried **`46.12`** and *"the 55th percentile"*
as **literals** in the source — the exact r38 failure mode (a figure transcribed from a note into a table), in the
file that r38 created to stop that. Now `rows(data)` recomputes the row from `cy.path()` on every print, `--verify`
re-derives it, and a test asserts the literal cannot come back (`assertTrue(any(r[2] is None for r in ACTIONS))`).

### 2. The switch is worth what the desk's sweep is not

Thirteen rounds priced the switch against one sweep assumption: the audited **2bp default** at the eleven
bank-sweep firms. But round 46's survey round has several desks paying **3.13%** on idle cash by default, and a bill
ladder cannot beat a sweep that already pays the curve. Re-priced at the same $20,000:

| the desk's cash pays | sweep | switch, record mean | switch, today | months it paid |
|---|---:|---:|---:|---:|
| audited default | 0.02% | **+$39.92** | +$63.34 | 81% |
| large-broker default | 0.05% | +$39.42 | +$62.84 | 78% |
| a plain savings account | 1.00% | +$23.59 | +$47.01 | 63% |
| **a big desk's sweep, today** | **3.13%** | **−$11.91** | +$11.51 | **42%** |
| the MMF option at those firms | 3.40% | −$16.41 | +$7.01 | 39% |
| 4.00% | 4.00% | −$26.41 | −$2.99 | 33% |

**Break-even sweep right now: 3.82%** (the curve less SGOV's 9bp). Across the record's median month it is **2.04%** —
so in the typical month of the last 33 years, an account earning 3% on idle cash would have *lost* money running a
bill ladder instead.

Which restates the recommendation honestly. The action was never "run a ladder"; the value in the table is **not in
the ladder at all, it is in the 2bp**. A desk that pays 3.13% on settlement cash has already collected most of it.
So the ranked action is **leave the desk that pays 2bp**, and the ladder is what you do when you cannot or will not
leave — one more step in the ordering round 46 forced: **desk → leverage → fund → model**.

## Checks

34 tests here, 13 in the ledger file, 1.6 s, offline. `last_business_day` is pinned against four known
September/October/May/February 2026 month-ends (**my first draft expected 31 May, which is a Sunday — the test was
wrong, not the helper**); the record must be exactly 403 months, and the spot must sit within 1.5pp of the last
*complete* month; `worth_spot` must exceed $60 and the percentile 0.60, so neither stale figure can return; the
switch must shrink monotonically down the sweep menu and go negative today at 4.00%; `breakeven_spot` is asserted as
the identity `spot − SGOV_ER`, not a fourth measurement; doubling the balance doubles both dollar columns and leaves
every share identical. Three old tests failed on the fix and were restated rather than loosened: one had been
**recomputing the contaminated window and therefore asserting the defect**, and the never-reinvest test moved from
$1.55 to $2.11 because the number it tests moved. Full suite: **1585 passed** (collected first: 1577 + 6 cash + 2
ledger). `journalctl verify`: chain intact, comparator pinned, $0.00 paid in.
