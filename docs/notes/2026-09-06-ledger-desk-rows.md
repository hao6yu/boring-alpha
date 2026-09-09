# The ledger was missing its two biggest rows, and the fix demoted its most certain one

Measured 2026-09-07, round 49. Tool: [`action_ledger.py`](../../tools/action_ledger.py)
(`FINANCING_MO`, `switch_row`, `rows`). Tests: 15 in `test_action_ledger.py` (+2).

## The ledger's completeness claim was false for four rounds

`action_ledger.py` is the file that says *every action this repository has priced*. Rounds 46 and 47 produced the
two largest actions this repository has ever priced — the financing rate card at **710bp** of posted spread, and the
sweep that eats most of the cash switch's value — and neither became a row. Meanwhile the row that *was* there,
first on the table at **$63.34/mo** and classified **`none`** for variance, was misclassified: round 47's own table
says that same action is worth **3 cents a month in 2021** and **−$1.65** in its worst month. A number that swings
four orders of magnitude with the Fed is not variance-free; it is a rate view with a date on it. That is the r41
error — a mean dressed as a guarantee — surviving in the file whose purpose is to stop exactly that.

So: one row added, one row demoted, both derived.

## The table after the change, at $20,000

| action | $/mo | variance | src |
|---|---:|---|---|
| move idle cash out of the default sweep | **+63.34** | ~~none~~ → **substantial** | 24, 47, 49 |
| **hold the loan at the cheap end of the posted rate card** | **+29.58** | **none** | 46 |
| a constant 1.25× book, financed at a posted desk rate | +27.24 | substantial | 29 |
| hold the cheapest share class of the same index | +1.07 | none | 18, 38 |
| reinvest distributions promptly | +0.01 | none | 42 |
| the vol-target rule as configured | −4.10 | substantial | 25 |
| de-risk with the trend/vol rule, unlevered | −21.15 | substantial | 26 |
| cross-sectional rotation across nine sleeves | −231.00 | substantial | cross-section |
| directional timing at any faster cadence | measured no | substantial | 2, 13, 14 |

**3 actions carry no variance and are worth $30.66/mo. 2 that do are positive and total $90.58/mo.** Read the rows,
not the totals: the two largest numbers a bot could actually act on are **where the cash sits** and **where the loan
is booked**, and neither is a model.

The new row is the round's number. On the borrowed slice of a 1.25× book, the gap between the cheapest posted base
tier (**4.90%**) and the most expensive (**12.00%**) is:

$$0.0710 \times 0.25 \times \$20{,}000 \div 12 = \$29.58\ \text{a month} = \$355\ \text{a year}$$

which is **more than the entire leveraged tilt it sits under** (+$27.24/mo, +1.63%/yr). The decision *where to
borrow* is worth more than the decision *to borrow* — which is r46's "desk → leverage → fund → model" ordering
expressed in the ledger's own units, and the strongest form the argument has taken, because it needs no simulation
to see: it is two numbers on two rate cards and one multiplication.

The row is classified `none` and that is defensible where the cash row's was not. A posted base tier is contractual
and readable — the saving is banked the day the loan is booked, at any bill yield, in any regime. Its zero-variance
claim carries a hard condition, stated in the caveat rather than assumed: **it is worth exactly $29.58 if you
borrow and exactly $0 if you don't.** The cash row's condition was the interest-rate cycle, which nobody controls.

## Four tests had to be restated, and one of them is the tell

- `test_the_only_positive_rows_that_are_not_loans_are_all_costs` — 4 positive rows, now 5. The new one passes the
  test's own rule ("a rate, a fee, or a loan"): it is a rate.
- `test_the_only_positive_stochastic_row_sits_just_above_the_comparator_fuzz` — the noise floor is a property of the
  *splicing comparator*, so only signal-derived rows may compete against it. The cash row is not a signal; the
  exclusion is a definition, stated as one.
- `test_the_idle_cash_row_beats_the_largest_single_row_that_is_not_a_loan` — r29's demotion, restated for r49. The
  comparison list the test built is **now empty by construction**: the only stochastic positives left are the cash
  rate view and the 1.25× loan, and neither is a signal. That emptiness *is* the finding and is asserted as such
  (`assertEqual(len(signals), 0)`) instead of hidden behind a guard clause.
- A pre-existing floor, `assertGreater(max(sure), 30.0)`, **failed** — and this is the tell. It was calibrated while
  the certain group was topped by the $63 cash row; after the demotion the largest certain row is the $29.58
  financing row and the floor was unreachable. Restating it as *which* row tops the group rather than *how big* it
  is makes the assertion say something the number can no longer silently break.

Two tests were added: the financing row must equal the rate card recomputed (`fd.EXPENSIVE[1] − fd.CHEAP[1]`, 2dp)
and must still outrank the tilt it finances; and the cash row must be `substantial` with round 49 cited — a test
whose only job is to make sure nobody quietly re-promotes it.

## Checks

15 tests, 0.5 s, offline. Full suite **1597 passed** (collected first: 1595 + 2). `journalctl verify`: chain intact,
comparator `100% SPY, fee 0.000945`, $0.00 paid in. The value of this round is not the $29.58 — it is that the
ledger now ranks the account's actions in the order the last four rounds earned: **open the right desk, then pick
the cheap loan book, then pick the fund, and only after all three argue about a model.**
