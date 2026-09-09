# The first size at which the tilt loses

Round 86. Tools changed: [`rebalance_cost.py`](../../tools/rebalance_cost.py) (a dominance scan),
[`decision_sheet.py`](../../tools/decision_sheet.py) (a fourth section, and a `--commission` flag). Tests added:
[`test_decision_execution.py`](../../tests/test_decision_execution.py), 17 of them.

## The claim that had never been priced

Seventy-plus rounds have established that the growth tilt beats plain VOO, and that it does so *at any scale* — the
scale-invariance of round 82. Both statements are about proportions. Expense ratios are proportions. Spreads are proportions.
A commission is not: it is a flat number stamped on a ticket, and it is the one cost in this account that a bigger deposit
does not dilute — it is the cost that makes a small account poor in a way a big one is not.

So the tilt was never asked the question this note answers. It was asked of `rebalance_cost.dominance()`: run the two-sleeve
50/50 tilt against plain VOO at a named capital, on the sealed month-ends, both books charged the same spread and the same
per-ticket commission, both buying every month, neither holding anything the other could not hold. Gap is reported per dollar
paid in, so the columns are comparable across the ladder; the commission-free column is the denominator.

**At $2,500 of capital, on a broker charging $9.95 a ticket, over two years, the tilt ends behind plain VOO.** It has ended
behind by 0.30% of everything paid in — a real loss, not a wash — on a book that every prior table in this repository says
dominates. This is the first P0 failure the tilt has ever produced. P0 is the rule that a strategy must beat plain
index-dollar-cost-averaging net of real costs, and until today it had only ever been failed by timing rules and by payout
levels, never by the tilt itself.

## What the ladder says

Gap per dollar paid in, tilt minus plain VOO, at a $9.95 ticket:

| horizon | $1,000 | $2,500 | $5,000 | $25,000 | $250,000 | $1,000,000 |
|---|---|---|---|---|---|---|
| two years | **−5.4%** | **−0.3%** | +1.4% | +2.8% | +3.1% | +3.1% |
| five years | **−7.2%** | +1.5% | +4.4% | +6.7% | +7.2% | +7.3% |
| the whole record | +46.8% | +76.9% | +87.0% | +95.0% | +96.8% | +96.9% |

With no commission at all, every cell in a row is identical: +3.12% at two years whether the account is a thousand dollars or
a million, because the whole thing scales. That invariance is the reason the rest of the sheet can be a page instead of a
spreadsheet. It is also the reason this table matters — the commission is not a hair on that invariance, it is a second
physics that only bites at one end of the range.

Two readings of the same table, both true. Over sixteen years the drag costs 20 points of a 97-point edge — the tilt keeps
79% of its advantage at a thousand dollars, and nobody should care which broker they use, because at that distance even a
punitive ticket buys a smaller hill rather than the wrong hill. Over two years the same $9.95 costs the small account *more
than the whole edge*: it goes negative. Short horizons shrink the denominator (the divergence between QQQ and VOO that the
tilt is harvesting has had less time to happen) while leaving the ticket count untouched, and the ratio is what decides
whether a second sleeve is worth buying.

The asymmetry is mechanical: the tilt pays two tickets a month, the witness pays one. The tier lines on the sheet say it in
one number each — at a $2,500 account the second sleeve keeps 100% of the commission-free two-year edge, 45% at $4.95, and
minus ten percent at $9.95. Negative means the flat charge ate more than the whole reason to be there.

## What this changes, and what it does not

It does not change the recommendation, because the recommendation was never "two sleeves no matter what". It changes *where
the recommendation lives*: the decision sheet now prints a fourth section, at the capital you name, and refuses to let you
run a two-sleeve book at a size and broker where the archive says it loses.

```
$ .venv/bin/python tools/decision_sheet.py --capital 2500 --commission 9.95
  4. HOW TO EXECUTE IT, AT YOUR SIZE  [rebalance_cost.py, paper.py]
     rebalance only past 5 points of drift, measured over the record by rebalance_cost: the bill for rebalancing monthly is
       0.003-0.054% of paid-in and the *policy* is worth 10.4% of it
     with no commission the comparison does not depend on size at all: the tilt is ahead by +3.1% of paid in over two years
       and +97.0% over the record, at every size the tool prices (the ladder runs 1,000 to 1,000,000)
     at $9.95 a ticket, 2,500 of capital over two years: the tilt FAILS against plain VOO by 0.3% of everything paid in
       (48 tickets against the witness's 24)
     at $9.95 a ticket, 2,500 of capital over five years: the tilt dominates plain VOO by 1.5% of everything paid in
       (120 tickets against the witness's 60)
     at $9.95 a ticket, 2,500 of capital over the record: the tilt dominates plain VOO by 76.9% of everything paid in
       (384 tickets against the witness's 192)
     tier $0.00: the two-sleeve book keeps 100% of its commission-free two-year edge at this size and still dominates
     tier $4.95: the two-sleeve book keeps 45% of its commission-free two-year edge at this size and still dominates
     tier $9.95: the two-sleeve book gives up 110% of its commission-free two-year edge at this size and ENDS BEHIND the witness
     REFUSED at this size on this broker: two years is enough — the two-sleeve form ends behind the witness. Hold one fund,
       or use a broker that charges nothing per ticket; the ticket count is set by the fund count, not by the rebalancing policy
```

Ask it without `--commission` and it declines to invent a broker, prices the commission-free case, and tells you the
invariance. That is the same discipline the sheet already used to refuse news vetoes and intraday claims, turned on a cost
it had been ignoring: the sheet prints no number it did not read from the tool named beside it, and the broker's tariff is
now one of those numbers (round 79's no-typed-dollars rule caught me writing "$1,000 to $1,000,000" into the sheet and
demanded the ladder's ends be read from `rc.CAPITAL_LADDER` instead, which is the rule working exactly as designed).

The refusal is conditional on two horizons rather than on a threshold. There is no dollar crossover asserted anywhere in
this repository: the ladder brackets it (below $5,000 at two years, below $2,500 at five years, on a $9.95 ticket), which is
what "the tape said this, not I" looks like. The crossover is not a fact about the tilt; it moves every time the tape
redistributes QQQ and VOO, and it is a different number at every broker.

For the person actually trying to earn extra each month, the finding translates into one actionable line: **the choice of
execution venue is currently worth more than any signal this archive contains** — because a flat ticket can turn the whole
tilt negative at a small account and a two-year horizon, while the archive's best timing rule is worth $88 a month on a
$100,000 account and $22 on a $25,000 one. That is not "trade more carefully". That is one fund at a paid broker, or two at a
free one.

## A defect the check itself turned up

The last figure above needed the best rule's monthly value at a stated capital, so it was read off the sheet at two sizes —
and the sheet printed **the same $88.29 for a $25,000 account and a $400,000 one**. That line was a figure per $100,000 of
book wearing a dollar sign: `rotation_search` reports capacity per hundred thousand, every other dollar line on the sheet
multiplies by `capital / 100_000`, and this one had been quietly not doing so. The comparison it reports is scale-free in
sign — the control beats the rule at every size, and no verdict in the sheet changed — which is precisely why it survived
thirty rounds of a human reading the page: it only ever misreported magnitude, never direction. The line is scaled now
($22.07 at $25,000, $353.16 at $400,000, a clean 16× for 16× the capital) and two tests in the new file assert that every
monthly dollar figure on the sheet is linear in the capital quoted, at four points rather than two, so that no future line
can be a percentage in disguise. Round 79's rule that a sheet may print no figure it did not measure is what sent me to look
at the number at all: it had refused my typed `$1,000 to $1,000,000` and made the sheet read the ladder's ends from the
tool, and the same discipline then caught the scaling bug two lines away.

## Footer

**2138 passed, 239 subtests** in 711 s (`/tmp/suite_r86.txt`): round 85's 2119 plus the 19 here. `journalctl.py verify` still
reports `chain intact`, `paper.py compare` lists five books all `intact`, and 86 standing rules. The dominance scan is deterministic and reads the sealed
archive (`rebalance_cost.py`, `paper.fee_for`, `power_horizon.simulate`) rather than any live bookkeeping; the live books are
untouched and still hold one entry each. No claim in this note depends on a live seal: the two-year row is sealed history,
and the forward books are calendar-bound to month-ends as before.

*Round 86. 86 standing rules. The archive found its first cost that does not scale, and for the first time a table had to say
no at a real account size.*
