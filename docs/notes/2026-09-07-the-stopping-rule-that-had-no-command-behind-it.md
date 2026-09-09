# The stopping rule that had no command behind it

Round 91. New: [`forward_p0.py`](../../tools/forward_p0.py) and
[`test_forward_p0.py`](../../tests/test_forward_p0.py), 13 tests. Amended: [`RUNBOOK.md`](../RUNBOOK.md) — rule 1, and one line
in the monthly block.

## The gap

Rule 1 of the runbook has been in the repository's prose since the P0 rule was written, and round 89 put it first in a list of
conditions under which the programme stops: the tilt must beat plain index investing, net of every fee and every ticket, or it is
retired. No command computed that. What existed:

- `paper.py report`, which scores a book against its own **witness** — the same sleeves, zero commission — so it answers "is the
  model worth its costs" but not "is this better than the index".
- `journal.verdict`, whose comparator is generous **by design**: `comparator_return` says commissions are zero "because the
  comparator is the thing that could have been done for free", and `comparator_path` advances it by `cash_arrived − fee_paid`,
  which hands it the book's net cash. Generous to the bar is right for a protocol whose fear is a false claim of skill. It is
  wrong for P0, whose question is whether the whole apparatus earns its keep against the boring alternative.

So the first stopping condition could be asserted and could not be evaluated. That is the kind of gap that survives for years,
because every report looks like it answers the question.

## What the new command does

`forward_p0.py --book <name> --commission <ticket>` reads one sealed chain and rebuilds the comparison from it:

- **Book side**: `closing_value`, exactly as sealed. Every expense ratio and basis point of spread is already inside it, because
  the engine put it there at seal time.
- **Index side**: the same transfers on the same dates into VOO alone, priced off the *same sealed quotes* through
  `journal.comparator_path`, with the fee line cleared first (`dataclasses.replace`, so the comparator is charged VOO's expense
  ratio and not the book's), then reduced by the tickets that plan would really have paid: one buy in each month money arrived,
  and nothing else.
- **The book's tickets are counted off the sealed holdings, not assumed**: between consecutive entries, a sleeve whose units rose
  was bought, one whose fell was sold. A banded book is therefore charged for the breaches it actually traded and a monthly book
  for its monthly churn, and the chain — not a description of the model — decides the bill.

Below two entries it says so and prints no comparison: the anchored books hold no positions, so no interval exists to price.
Below 24 entries it prints the cost sheet and the words `not decidable`. It refuses a negative commission ("a rebate"), and it
refuses to score a chain that does not verify — tested by copying a live ledger into a scratch directory, changing one closing
value by a dollar, and demanding the refusal.

## The forward bill, measured rather than forecast

`rebalance_cost.py` already counts orders on the sealed archive, and at the live schedule it says the two-sleeve book makes **48
tickets in two years where plain VOO makes 24**. At $9.95 that is $477.60 against $238.80 — an extra $238.80, which on
$16,500 paid in is **2.81% of every dollar put in**. Round 86 measured the same book's two-year advantage over VOO, commission
free, at +3.12% of paid in. Put those together and the sentence the objective most needs is this:

> On a $5,000 account over two years, **the broker's per-order price consumes about 90% of the growth tilt's entire measured
> advantage over plain VOO.** On a $25,000 account the same 48 tickets cost 0.56% and the argument changes sides.

That is not a forecast of return; it is a measurement of cost, from the same tool, on the same archive, and it is the strongest
practical argument this project has produced. `forward_p0.py` will not have to assume the 48: it will read the number of trades
the book actually made.

## The margin is not this file's to invent

Past 24 entries the command applies round 90's no-skill margins (+152 bps at 24, +50 at 36, 0 at 60) rather than the bare sign,
so a book that is "ahead" by an amount a no-skill path clears a fifth of the time reads `ahead, but inside the no-skill margin:
not evidence either way` instead of a verdict. Those constants are the only numbers in the file that came from elsewhere, so a
test re-derives them by running `skill_null.py` and comparing to the printed p95 (the first version of that test read the wrong
row of the JSON and compared the fee-matched construction against the pinned one — caught by a 17 bp delta, which is exactly the
kind of mistake a hand-copied constant invites).

## Checks

**2198 passed, 239 subtests** (`/tmp/suite_r91.txt`), 91 standing rules. All five live books still answer `nothing to compare
yet`, which is the correct output for a programme that is three weeks old: the first honest P0 number arrives at the 24th entry,
and the command is now the thing that will produce it.

*Round 91. 91 standing rules. A stopping rule you cannot evaluate is a decoration; this one now has a command, a price per order
as its only input, and a test that tampers with a live ledger to make sure the command would rather refuse than guess.*
