# The instrument nobody was allowed to change gets calibrated anyway

Round 90. New: [`skill_null.py`](../../tools/skill_null.py) and
[`test_skill_null.py`](../../tests/test_skill_null.py), 12 tests. Amended: [`RUNBOOK.md`](../RUNBOOK.md), stopping rule 3.

## Why calibrate the thing you are forbidden to move

`journal.verdict` is the pre-registered instrument, and it is pinned: 24 monthly entries and $10,000 paid in, and then
`skill: beat` if the account's money-weighted return exceeds the comparator's **by any amount at all**. No margin, no variance
term, no interval — the gap is compared to zero, in basis points, once. A threshold moved after the anchor would be a goalpost
moved, so the protocol stays exactly as it is. What was never done, in twenty rounds of leaning on that sentence, is measure how
often it says yes when the answer should be no. Round 89's runbook made rule 3 depend on it, which turned the omission into a
liability.

`skill_null.py` runs the real `journal.verdict` — not a stand-in statistic, the actual function over fabricated entries — on paths
on which it should say no. The raw material is the archive's own 192 monthly links, drawn **jointly** across SPY, QQQ and VOO so
each fund keeps its own volatility and the funds keep their correlation, chained forward from the archive's last month-end. The
book's monthly values come from `power_horizon.simulate`, the same engine `tests/test_power_horizon.py` walks against
`paper.shadow_step` over the journal's own dates, so the surrogate is not a second opinion about the mechanics.

Three constructions, because one null is not enough to be honest about what is being held equal:

- **`hurdle-fee-matched`** — every fund earns SPY's return, and the comparator is charged the tilt's own weighted expense ratio.
- **`hurdle-as-pinned`** — same single index, comparator charged VOO's real 3 bps and nothing to trade, as the protocol says.
- **`replay`** — the real returns of all three, order scrambled. Not a null: the archive's drift is in it. That is the point.

## What the pinned instrument is actually worth

600 paths, seed 20260907, band 5 points, no commission. The gap is the protocol's own `shortfall_bps`.

| construction | 24 months | 36 months | 60 months |
|---|---|---|---|
| hurdle, fee-matched — `beat` on no skill | 18.3% | 14.3% | 10.3% |
| …median gap | −103 bps | −80 | −43 |
| …margin only 5% of paths clear | +134 | +51 | +14 |
| hurdle, as pinned — `beat` on no skill | **18.8%** | 12.3% | **4.8%** |
| …median gap | −116 bps | −80 | −58 |
| …margin only 5% of paths clear | **+152** | +50 | −0 |
| replay (real drift, scrambled order) | 62.0% | 70.8% | 80.0% |
| …median gap | +83 bps | +147 | +178 |

Four things follow, and only the first was expected.

**At the floor of 24 entries the instrument prints `beat` about one time in five when there is no skill anywhere in the
construction.** Not one in two — see the next point — but nothing like proof either. The runbook's rule 3 now demands the
margin instead of the sign: more than ~150 bps annualised at 24 entries, ~50 at 36, and at 60 anything at all, because at 60 the
no-skill distribution is centred 58 bps *behind* and any positive gap already clears the 5% level.

**The floor grows conservative with length rather than merely sharper, and the reason is a cost, not a statistic.** The median
gap under no skill is negative at every horizon and less negative as the record lengthens: the book pays 3 bps on every purchase
it makes — twelve a year, forever — while `comparator_path` pays nothing, because the comparator is a construction and not an
account. The protocol says so out loud ("this is generous to it by construction, so losing to it is never a rounding error"). It
is a hurdle with a published height, and the height is roughly 100 bps of annualised drag at two years decaying to about 60 at
five. A strategy that is merely *as good as* the index loses this test, on average, by exactly that much.

**The replay rows are the most uncomfortable numbers in the file.** On the archive's own returns with the order of months
scrambled, the tilt beats plain VOO 62% of the time at 24 months and 80% at 60. So even granting that history repeats in
distribution — the most generous assumption available — a 24-month forward verdict has a roughly 3-in-5 chance of coming out
`beat` and a 2-in-5 chance of not, and the same history can produce either. That is the quantitative version of why this
repository refuses to grade a tilt on two years of anything.

**Below the floor the instrument is silent, and the study reports silence as silence.** At 12 months every construction returns
`withheld` rather than a rate, because `verdict` refuses to speak. A calibration that imputed 0.5 there would be a fabricated
number wearing a table.

## Two things the round caught in its own work

The first version called the fee-equalised construction `null-symmetric` and the summary implied it was a coin flip. It was not:
25% of paths said `beat`, not 50%, because the book still paid its spread and the comparator still paid nothing — equalising the
*expense ratio* is not equalising *costs*, and the spread cannot be equalised without editing the protocol, which is pinned. The
mode is renamed `hurdle-fee-matched` and the docstring now says the asymmetry is the finding rather than hiding it. A label that
overstates what a construction holds equal is how a study starts believing its own null.

Second, a test meant to prove `--band` was honoured failed, and the failure was instructive rather than a bug: on a one-index
null, the two sleeves move by exactly the same factor, so weights never drift, so a rebalancing band cannot fire and the band
flag has no effect *by construction*. The test now asserts that equality in the null rows and asserts the band's effect where the
sleeves are allowed to separate — in `replay`. An impossibility worth asserting is a property, and it catches plumbing rot that a
looser test sails past.

## What this changes for the objective, and what it does not

It changes no expectation about the market and adds no return. It changes one decision rule from `if report says beat, keep the
tilt` to `if the gap clears the measured margin, keep the tilt`, which at the current pace ($5,000 opening, $500 monthly) is a
rule that first becomes usable around the 24th entry and stops being a coin-toss-shaped rule entirely around the 60th. It also
prices, in the only honest unit available, what beating the index costs before any skill is claimed: about a point of annualised
return in entry costs, on a two-year record, against a comparator that is not allowed to pay for anything.

## Checks

**2185 passed, 239 subtests** (`/tmp/suite_r90.txt`), 90 standing rules. The 12 new tests take 15 seconds. `paper.py compare`
still reports five books `intact`, one entry deep; the runbook's quoted 18.8% and +152 bps are re-derived from the tool on every
test run and the test fails if either moves.

*Round 90. 90 standing rules. The protocol stays pinned; what moved is the meaning of the sentence it prints.*
