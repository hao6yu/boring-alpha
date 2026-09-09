# Four files, four answers, one fact: what a fund charges

Round 94. Changed: [`fund_fees.py`](../../tools/fund_fees.py) (new), [`test_fund_fees.py`](../../tests/test_fund_fees.py) (11
tests), `paper.py` / `cross_section.py` / `run_comparator_battery.py` / `withdrawal_capacity.py` (their fee tables are now imports),
and two pins rewritten — [`test_paper_shelter.py`](../../tests/test_paper_shelter.py),
[`test_paper_tilt.py`](../../tests/test_paper_tilt.py).

## What was found

The same eight numbers were written down in four places and agreed in none of them.

| leg | the engine charged | the comparator battery said | the cross-sectional scanner said | published |
|---|---|---|---|---|
| IWM | 0.35% | 0.19% ✓ | 0.19% ✓ | **0.19%** |
| EFA | 0.35% | 0.29% | 0.32% ✓ | **0.32%** |
| EEM | 0.35% | 0.32% | 0.72% ✓ | **0.72%** |
| IEF | 0.35% | 0.38% | 0.15% ✓ | **0.15%** |
| TLT | 0.35% | 0.48% | 0.15% ✓ | **0.15%** |
| GLD | 0.35% | 0.40% ✓ | 0.40% ✓ | **0.40%** |
| DBC | 0.35% | 0.65% | 0.87% | **0.84%** |

Round 83 measured this book's entire rebalancing bill, over sixteen years, at **0.054% of paid in**. The battery's TLT line alone
was 0.33 percentage points a year wrong — six times the cost the strategy was being graded on — and the file carrying it had a
comment explaining that an error in that table only hurts *if it is too low*, in a table where two of eight legs were too low. The
engine's flat guess had a comment claiming it was "deliberately the pessimistic direction", and three of the seven legs it was
pessimistic about were actually dearer than the guess: it undercharged DBC by 49 bps, EEM by 37. A comment that is mostly true about
a cost is how a cost stops being watched.

`tools/fund_fees.py` is now the one table, with the issuer, the retrieval date (2026-09-08) and the URL pattern for each ratio.
The four consumers import it. `tests/test_fund_fees.py` scans every file in `tools/` for a ticker mapped to a number between zero
and two percent and fails if it finds one outside the table — a regex with a numeric guard, because `{"SPY": 0.5, "QQQ": 0.5}` is an
allocation and not a cost, and a scan that flags allocations gets ignored inside a week.

## What changed, at any size you like

Per $100,000 held for a year, the flat guess over-billed **$200 on IEF, $200 on TLT, $160 on IWM** and under-billed **$490 on DBC,
$370 on EEM, $50 on GLD, $30 on EFA** — $560 too much and $940 too little, across seven legs held equally. The correction is not one
direction, which is the actual finding: "a conservative guess" was not conservative, it was a number that happened to be near the
middle of a universe whose cheapest and dearest legs differ by a factor of 28 (VOO 0.03% to DBC 0.84%).

Three things this does **not** do.

**It does not re-price a sealed book.** A paper book's fees are frozen in its config at the anchor, and a book whose cost assumption
moves mid-chain stops being one chain — so the live `shelter` book still charges its bond legs 0.35%, which is now *known* to be 20
bps harsher than IEF and TLT actually charge. Its reported drag is conservative by that much, and its witness (VOO) always carried
its real fee, so no comparison in the archive moved. What changed is what the research tools say and what the next anchor will charge.

**It does not pretend a ratio is constant.** iShares has moved EFA and EEM's ratios inside the sixteen years this repository scores.
Every figure here is today's published ratio, which is why the table carries a retrieval date rather than a "last reviewed" shrug:
where a fund's fee has been cut, scoring its early years at today's rate understates the drag; where raised, the reverse. The
direction is fund-specific and this table cannot know it.

**It does not retire the refusal.** An unknown ticker is still refused as a witness — `paper.posted_fee("XLU")` exits. The refusal's
*teeth* moved from four named funds to "anything without a source", which is what round 81 was actually asking for: not a permanent
ban on bond ETFs, a ban on scoring a benchmark at a fee nobody posted. `test_paper_tilt.py` now asserts both halves.

## Two pins that had to be told the truth

`test_paper_tilt.py` asserted IEF/EFA/GLD/DBC were *not* posted and would exit if asked to witness. That was a real decision, and it
is now superseded by better information — sourced ratios exist, so those four may witness at their own fee. Rewritten, with the
refusal kept for unsourced tickers, per r88's rule that a superseded decision is recorded rather than quietly deleted.

`test_paper_shelter.py` was named `test_the_shelter_costs_three_times_what_the_old_global_fee_would_have_charged`. The bug it
pinned — the book charging its equity fund's fee on a Treasury fund — was real and survives. The "three times" did not: at the guess
the multiple was 3.7×, at the published 0.15% it is 1.6×. The number belonged to the guess, not to the fund. The test now derives the
multiple and asserts both that it is above one and that it stays below three, so if a future ratio makes the old headline true again
the test says so instead of nodding.

## Why it survived six years, in one arithmetic

The battery re-ran against the corrected table and its rows barely moved, which is the actual reason nobody noticed. Per leg, the
old table's error (positive = charged too much): EFA −3 bps, EEM −40, IEF +23, TLT +33, DBC −19, and zero on the three it got right.
Equal-weight across those eight nets to **−0.75 bps a year** — about 0.08% of terminal value over a ten-year window — and the
all-weather-ish 40/20/20/20 basket nets to **+1.00 bps**. The errors cancelled inside every basket the file prints and hid entirely
inside the single-leg rows, where the worst was 40 bps a year on one fund. A cancelling error in the headline row and a large one in
the detail is the worst possible distribution for a bug: the summary check passes, and the number someone might actually act on is
the one that moved.

Nothing elsewhere in this repository quotes a battery row, so no published figure needed retracting — checked before writing that
sentence, not assumed.

## The patch that ate a test, and how it was caught

Rewriting the witness pin, the patch sliced from the target method's name to the next `class` statement and replaced everything in
between. That region held one method in the author's reading of the file and two in the file's actual contents:
`test_the_income_book_s_witness_is_charged_the_benchmark_s_own_fee_not_the_book_s`, round 81's guard against charging the tilt's
blended 14.7 bps to a benchmark that costs 3 bps, was destroyed silently. Nothing failed. The suite went *greener*, from 2240
expected to 2239 actual — the only evidence that a guard had vanished was an arithmetic that did not add up.

So the discipline, now stated: **a rewrite of a test file is verified by counting tests before and after, not by the rewrite
succeeding.** The count is part of the assertion, and a suite whose total shrank without anybody deleting a test on purpose is
reporting a loss, not a gain. The rebuilt test is a reconstruction from the behaviour it protected (round 81's finding, restated
in its docstring) rather than a recovery: the file is not in git, and the only cached bytecode was the post-edit one. The original
wording is gone, which is exactly the argument for the first commit that has been offered for ten rounds.

## Checks

**2239 passed, 239 subtests** at the point of measurement, then 2240 after the rebuilt witness test landed — the next full run is
expected to read 2240, and the difference is the destroyed test rather than anything about the fee table. 94 standing rules. `cross_section.py`, `paper.py`, `run_comparator_battery.py` and
`withdrawal_capacity.py` all agree with the table to twelve decimal places, and the battery was re-run against the corrected ratios
before anything in this file quoted it.

*Round 94. The fee line is the input this programme has repeatedly found dominates every signal — and it had four copies, three of
them wrong, two in the flattering direction, each defended by a comment that was mostly true.*

---

**Amended in round 103.** The note said one sourced table; it did not say every lookup had been pointed at it. `rotation_search.py`
— the battery that ranks the archive's candidate rules — went on doing `wc.EXPENSE[sym] if sym in wc.EXPENSE else FLAT_FEE`, a
*publication* list used as a fee lookup: three of its five legs were still billed the 0.35% guess, worst on IEF at **20 bps**, the
leg every shelter rule hides in ([the round's own note](2026-09-08-the-fifth-file-that-guessed-and-the-footer-that-said-it-had-not.md)).
