# A cost with no transaction in it

Round 97. Changed: [`power_horizon.py`](../../tools/power_horizon.py) (six bars, `mix_sweep.drawdown`, a convention caveat in the
header), [`test_power_horizon.py`](../../tests/test_power_horizon.py) (21 → 25), [`RUNBOOK.md`](../RUNBOOK.md).

## The table grew three rows and the ordering stopped being a surprise

Round 96 put a command under the archive's most consequential headline. Round 97 asked the same command the question the *forward
books* actually pose: what does the construction being traded cost, against the same two funds touched less often?

```
    plain VOO, the standing bar          paid in $  2,020,000   closed at $    7,853,675   worst hole -22.0%
    plain QQQ, the free version of the same bet paid in $  2,020,000   closed at $   12,216,556   worst hole -31.3%
    plain SPY, the free market           paid in $  2,020,000   closed at $    7,760,092   worst hole -22.0%
    the tilt, rebalanced monthly         paid in $  2,020,000   closed at $    9,778,202   worst hole -26.8%
    the tilt, only past 5 points of drift paid in $  2,020,000   closed at $    9,812,538   worst hole -26.8%
    the tilt, never rebalanced           paid in $  2,020,000   closed at $    9,988,324   worst hole -27.6%
```

Monotone in how little the book trades: monthly < banded < never, and all three behind the free version of the bet. The same two
funds, the same deposits, the same fee table, the same simulator — the only difference is how often somebody sells what rose.

## The part the fee ledger cannot see

Round 83 measured this book's rebalancing bill at **$1,091, 0.054% of paid in**, over sixteen years, and it is still true. It is also
not the cost of the policy. The gap between the band and the drift control is **$175,786, 8.70% of paid in** *(corrected in round 100: this note said 0.87%, a
mental division against a paid-in figure of ten times its size; the dollars were right and the share was a tenth of the truth, which is the
direction that makes a policy look cheap — see the round-100 note)*, and there is no
transaction anywhere inside it: it is what holding a fixed 50/50 weight on a pair that trends apart costs, in weight you were not
allowed to keep. A ledger that itemises tickets cannot show that number, and neither can any broker's statement, because nothing was
traded — the account simply ended up smaller than the same account that left it alone.

So the two measurements agree in sign and differ in kind: trading costs $1,091 of fees and **$175,786 of forgone drift**. That reframes
stopping rule 2 rather than weakening it. The cap on the band's shortfall against its twin is still 0.054% of paid in, because that is
what was pre-registered and a cap is not renegotiated once the tape is in — but a `no verdict either way` inside that cap must be read
as "the band did not cost *tickets*", which is no longer the same sentence as "the band cost nothing".

Nothing about the live books changes. `tilt_band`'s config was written at its anchor and is never rewritten, so the drift control is
not available to it — it is available to the *next* anchoring, which is the only moment this project is allowed to change a policy.

## The recent window, and a tripwire

Over the last 61 month-ends the banded and never-rebalanced rows are **identical to the cent** ($1,169,396): five points of drift have
not been breached since 2021, which is why the five-year bill was $18 and why `report` prints `sold 0 sleeve(s), drift 0.0 points`. The
band is not clever; on this window it has simply been idle. There is a test asserting that equality with `delta=1.0`, and its message
says what to do when it fails: *re-read this note rather than relax the assertion* — the day the band fires in the recent window, the
thing being graded has started happening, and that is news, not a flaky test.

## Two conventions for "drawdown", said out loud

The new column is peak-to-trough of the **balance**, with deposits still arriving, so a fall is diluted by new money: VOO -22.0%,
QQQ -31.3%. `mix_sweep.py` reports drawdown of the **index** and prints larger numbers (33.7% and 35.2% for the mixes on its own
window). Both are honest and neither checks the other, so the header now says so on the same screen. A figure that appears twice with
two meanings is r94's fee-table lesson one round old, and the fix is the same: name the convention where the number is printed.

## Where this leaves the objective

Third independent measurement of the same shape: round 82 (QQQ beats the rebalanced tilt), round 75 (the static control beats the best
signal rule), round 97 (the *least* active variant of the tilt is the best variant of the tilt). Every time this archive has compared
doing something with doing less, doing less won, and it won by more than the fees the activity cost. That is the most reliable
prediction the repository has ever made about itself, and the forward books exist to find out whether it survives contact with months
that have not happened.

## Checks

**2272 passed, 239 subtests** — four new tests: every row's hole is a real negative number; the concentrated bar has the deeper hole;
the three tilt variants are ordered monthly ≤ banded ≤ never *and* separated by more than noise ($10,000 on $2.02M paid in); the band
and the drift control are identical in the recent window. The published-figure pins moved only in one row name (`the tilt, 50/50
rebalanced monthly` → `the tilt, rebalanced monthly`), and the presence check now fails if a published row disappears at all rather
than skipping it quietly. Live state unchanged: five books, one anchor each, all chains verify, sealed fees $0.00, first seal
2026-09-30.

*Round 97. 97 standing rules. The most expensive thing in this account is a decision to rebalance, and it does not appear on any
invoice.*
