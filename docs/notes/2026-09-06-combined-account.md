# The four positive actions composed into one account, and only one of them survives being composed

Measured 2026-09-06, round 38. Tools: [`combined_account.py`](../../tools/combined_account.py),
[`action_ledger.py`](../../tools/action_ledger.py); tests
[`test_combined_account.py`](../../tests/test_combined_account.py) (7) and
[`test_action_ledger.py`](../../tests/test_action_ledger.py) (11).

## The question, asked for the first time in 39 rounds

The goal is one sentence: **does the whole thing beat just buying VOO.** Thirty-eight rounds priced individual
actions and round 28 sorted them into a table — but a table is not an account, and this repository had never summed
its own positive rows into one portfolio. This round went to do the sum and found it could not be done, for two
reasons that are the round's finding. The tool below is what makes the sum well-defined: one capital, one path, one
benchmark, one dial.

## Finding one: the ledger's headline row was a noise floor, 23× too big

`action_ledger.py` had carried **$25.00/mo** for the cheap-share-class row for nine rounds, and it is quoted that
way in three other notes. **$25/mo was round 18's noise floor** — the size of the artefact produced by naming SPY
rather than VOO as the comparator — and it had been transcribed into the ledger as though it were the *value of the
action*. The action is worth the expense ratio and nothing else:

> 6.45 bps × $20,000 = **$12.90 a year = $1.07 a month.** The published row was **23× too large.**

What makes this more than a typo is that the same number appears in three notes as evidence about the *size of
things*, and a floor and a prize are different kinds of quantity. A floor says how badly you can measure; it says
nothing about what anything is worth. The correction moved the ledger's own summary: certain actions **$46.13 →
$47.20/mo** (it is now counted as variance-free, which a fee schedule genuinely is) and positive stochastic actions
**$52.24 → $27.24/mo**, a 48% reduction in "money available if you take a view". The row is now derived from
`wc.EXPENSE` at import and re-printed under `--verify`, so it cannot silently disagree with the fee table again.
That was the second thing wrong with it: `--verify` covered two of eight rows and the unverified one rotted.

## Finding two: the positive rows are not additive, they are opposite stances

The engine makes this mechanical rather than rhetorical. `book_power.py` prices cash and borrow in one term,
`(1 - w) * cash`, so at a full 1.0 weight the idle-cash decision multiplies out to **exactly zero**, and at the
loan's 1.25 weight it is negative. Composing every stance on one path, against 100% VOO with no view:

| equity | idle | excess vs VOO | $/mo | switch worth |
|---:|---:|---:|---:|---:|
| 0.00× | 100% | −11.89% | −198.17 | +47.00 |
| 0.50× | 50% | −5.95% | −99.09 | +23.50 |
| 0.90× | 10% | −1.19% | −19.82 | +4.70 |
| **1.00×** | 0% | 0.00% | 0.00 | **0.00** |
| 1.10× | −10% | +0.99% | +16.56 | 0.00 |
| **1.25×** | −25% | **+2.48%** | **+41.40** | **0.00** |

Read the last column against the fourth. **The cash switch is worth precisely nothing to a fully invested
account** — and at the loan it is *also* nothing, for a subtler reason: under posted borrow the cash term appears
twice and cancels, `(1-w)·c − (w-1)·(menu−c) = −(w-1)·menu`. A borrowed account cannot simultaneously collect a
deposit rate. That is round 31's finding from the other side — the switch and the loan are one exposure to the rate
curve, not two wins to stack — and here it falls out of the algebra unasked.

So the ledger's two headline positive rows describe **opposite uses of the same dollars**: one needs 100% of the
account in cash, the other needs 125% in equity. Holding 50% cash gets you $23.50 of switch and −$99.09 of forgone
market. **Every stance that holds cash loses to plain VOO, monotonically.**

## The answer

**+2.48%/yr, $41.40/mo on $20,000** — obtained by borrowing 25% and owning nothing but the index. No signal, no
forecast, no news. Every cash-holding stance loses; the fee choice is worth $1.07 and is already inside the
benchmark; distributions are still nothing. The account beats the index **by borrowing, or holds cash and does
not.**

## And the size of that is softer than the table looks

The same stance on SPY instead of VOO — same index, same policy, same financing — gives **+1.63%/yr, $27.24/mo**.
The two funds differ by **0.85%/yr** and the fee ratio explains **0.065%** of it. The remaining ~0.79%/yr is which
near-identical fund the tool happened to name: round 18's noise floor, and in round 38 still about **a third of the
only positive plan this repository contains**. The sign is robust; the magnitude is not known to decimals, and any
sentence about a 2% edge should carry that caveat in the same breath.

The SPY figure reproduces the ledger's loan row to the cent, which is a test and not a coincidence — two files that
price the same stance and disagree are worse than one file that is wrong, because the disagreement is invisible.

> **Amended in round 39: the 0.85%/yr above is not a fund gap at all, and the sentence explaining it is wrong.**
> SPY was run over 404 months and VOO over 192, because that is all each series contains — VOO's first session is
> 2010-09-09, inside the strongest sustained bull in the archive, SPY's is 1993-01-29 and so carries dot-com and
> 2008. Re-run on the **common 192 months**, the two funds give **+2.460%** and **+2.484%** and differ by
> **0.024%/yr — tighter than the 0.065% fee gap that separates them**, which is what two funds tracking one index
> must do. The whole 0.85%/yr was the sample: the *same fund and policy* over its own 404 months and over the
> common 192 gives **+1.63%** against **+2.46%**, so the era is worth **0.83%/yr, half the edge**. Nothing above
> about the composition of the account changes — cash loses monotonically, the switch is worth zero at w=1.0, and
> only borrowing beats the index. What changes is what the number means: **the plan earns 1.63%/yr over 33 years
> and 2.46%/yr over the last 16, and the difference is the calendar.** Any excess figure in this project is a
> statement about a window as much as a policy, and the archive's windows differ by series by design.

## Checks

Suite: **1534 passed, 233 subtests** (collected 1534 before the run and confirmed after). Tests pin: this tool's
1.25× stance on SPY must equal the ledger's row to the cent; the cash sweep must be monotone and every cash-holding
stance must lose; the switch must be worth *exactly* zero at w=1.0 to twelve decimal places; the share-class row
must equal the expense ratio and be classified variance-free; and — the correction of this note's own closing claim — on a
**shared** window two index funds must agree to *within* their fee gap, while the window itself must still move the
edge by more than half its size. Three tests failed before they passed: two asserted a direction I had guessed
rather than measured, and one compared a percent-denominated quantity against a dollar threshold. Three tests failed before they passed: two asserted a direction I had
guessed rather than measured, and one compared a percent-denominated quantity against a dollar threshold.
`journalctl verify`: chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.
