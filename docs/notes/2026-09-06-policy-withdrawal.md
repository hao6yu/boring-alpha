# The candidate scored as a spending plan (2026-09-06, round 8)

```
.venv/bin/python tools/policy_withdrawal.py
.venv/bin/python tools/policy_withdrawal.py --sleeve SPY --lag 1
.venv/bin/python -m pytest tests/test_policy_withdrawal.py tests/test_withdrawal_capacity.py -q
```

## The question, which round 7 left standing

Round 7 measured leverage on an index sleeve and found the floor falls at every leverage:
$379 a month per $100k at 1×, $335 at 1.25×, $300 at 1.5×, financing free. Leverage bought
dispersion and not income. That result is about *constant* leverage, and the pre-registered
candidate is not constant: an 18% vol target on a 30-day window, a 200-day trend gate, a 30%
floor, a 1.30× cap. The regime that sets round 7's floor — 2000 to 2002 — is the regime a
trend gate claims to read. Round 8's plan was one sentence: score the candidate in withdrawal
units, since no mechanism here has ever been measured that way.

The answer is **yes on SPY and VTI, no on ITOT, half on QQQ** — and the interesting part is
which control decided it.

## The table

20-year windows, every third month as a start, $100k, real SPY expense 9.45 bps, 2 bps a unit
of turnover, cash index + 150 bps financing, 30% maintenance cushion, withdrawals indexed 2.5%.
Every figure is the worst start month in that sleeve's record.
Archive `20260906T203953Z` — SPY from 1993-01 through 2026-09-04, 404 month-ends, 8,458
sessions; QQQ from 1999-03, VTI from 2001-06, ITOT from 2004-01, and VOO refused again for
having no 20-year window.

| sleeve | book | avg lev | starts | first | median |
|---|---|---|---|---|---|
| SPY | flat 1.00× | 1.00 | 55 | 379 | 626 |
| SPY | flat at avg weight | 1.02 | 55 | 380 | 634 |
| SPY | **candidate** | 1.02 | 55 | **518** | 712 |
| SPY | wrong months | 1.02 | 55 | 343 | 574 |
| SPY | no trend gate | 1.11 | 55 | 410 | 675 |
| QQQ | flat 1.00× | 1.00 | 31 | 171 | 728 |
| QQQ | **candidate** | 0.86 | 31 | **411** | 604 |
| QQQ | wrong months | 0.86 | 31 | **0** | 596 |
| VTI | flat 1.00× | 1.00 | 22 | 509 | 645 |
| VTI | **candidate** | 1.03 | 22 | **626** | 735 |
| VTI | wrong months | 1.03 | 22 | 410 | 566 |
| ITOT | flat 1.00× | 1.00 | 11 | 607 | 634 |
| ITOT | **candidate** | 1.06 | 11 | **669** | 716 |
| ITOT | wrong months | 1.06 | 11 | **720** | 746 |

Round 7's flat numbers are unchanged to the dollar, so the new plumbing did not move the
thing it was built beside.

The SPY result holds at every horizon the record supports, and thins as it widens, which is
what sequence risk says it should: 10-year windows pay $841 against a $620 control and a $575
reversal (95 starts), 20-year $518 / $380 / $343 (55 starts), 30-year $680 / $600 / $518
(15 starts, 15 of 15 paying more than the control). Short windows are also richer windows — a
10-year floor is roughly double a 20-year one — so the honest reading of the whole page is
that the policy protects a *long* plan best, and round 7's warning stands: a 10-year ceiling
and a 20-year floor are different products.

Five rows per sleeve, each answering a different accusation. **flat 1.00×** is the Dominance
Rule. **flat at the policy's own average weight** holds leverage fixed, so a win there cannot
be a leverage win wearing a costume. **no trend gate** asks whether the 200-day average does
any work. **candidate** is the thing under test. And **wrong months** — the candidate's own
weights read backwards — is the row that has to lose: same multiset of weights, same mean,
same time spent at every weight, only the order different, so anything it cannot match can
only be *when the policy moved*.

On SPY the floor goes $379 → $518 (+37%) at an average weight of 1.02, it beats the same
weights held flat (+$138) and the gateless version (+$108, which carries *more* leverage,
1.11), and it beats the same weights reversed (+$175). **55 of 55 starts pay more than the
flat-at-average control, and no start pays more than $56 less.** On VTI the same shape,
22/22, worst start +$30. The mechanism is visible: the gate holds the floor through 2000–2002
and 2008, which is exactly where a withdrawal's floor is set.

Then the two results that keep this honest. On **QQQ** the floor doubles ($171 → $411) but
only **16 of 31** starts pay more, and at one of them the policy pays **$262 a month less**
than a spreadsheet cell holding its own average weight. A floor is a minimum over starts, and
a mechanism can raise the minimum while making half of starts worse. On **ITOT** the reversed
path scores **$720 against the candidate's $669** — the same weights, scrambled, do better.
Eleven windows. There is no timing claim to be made there and the row says so.

## What the alignment shift actually showed, which is not what was promised

The tool's docstring promised a test showing that shifting the path by a month changes the
answer materially. It does not. One month either way moves SPY's floor from $518 to $529,
about 2%. The test is now called `test_decision_timing_one_month_off_is_not_where_the_money_is`
and asserts the *insensitivity*, which is the property worth having: the claim is not an
artefact of where the month boundary falls. Both shifts happen to score marginally *better*,
which is also worth knowing — it says the exact decision date is not carrying the result, and
it rules out the one shape a look-ahead could have taken here (a leak is knife-edge
sensitive, and this is not).

## Three holes found on the way, and what each one would have cost

**The median column was lying.** `per_window` unpacked each window into a 3-tuple and threw
the weight path away, so every path row — which the tool scores at `lever=0.0` because the
path *is* the exposure — was simulated as a zero-position account. The column read **$0** for
every policy row and it looked like a finding about the policy. It is now the window's own
tuple, and `capacity`/`smallest_cheque`/`per_window` refuse `lever <= 0` unless every window
carries a path. `test_per_window_honours_the_path_it_was_given` is the negative control.

**`capacity([])` paid out.** `reliable` over no windows is vacuously true, so a sleeve with no
20-year window returned the top of the grid as its frontier: $6,000 a month for VOO, which was
never scored at all. Worse, it made three of the new tests pass by measuring nothing. All three
entry points now raise on an empty list, and every helper in the new test class asserts how
many windows it scored. `test_an_empty_window_list_is_refused_rather_than_paid`.

**A path could be indexed past its end.** The closing rebalance asks for a weight one month
after the last month in the slice, which is harmless with a constant leverage and an
`IndexError` with a path. Held at the last known weight — a path has nothing to say about a
month that is not in it — and pinned by
`test_a_path_shorter_than_the_window_holds_its_last_weight`.

Also pinned, since the shape of the result was suspicious: a constant path of 1.25 written out
240 times scores **bit-identically** to `lever=1.25`; and each window is checked to carry *its
own* slice of the path rather than the shared array, with a ramped weight series so the two
slices cannot be confused for each other. The negative controls were run, not assumed:
dropping the path kills one named test, un-clamping the index kills one, removing the
dead-leverage guard kills one, removing the empty guard kills one, handing every window the
whole array kills one, sorting the weights kills two.

## What is still not measured

- **Monthly approximation.** The live book reviews every five sessions; this reviews at the
  month boundary, which understates the policy's responsiveness. The forward book can settle
  that; this table cannot.
- **The gate is disengaged for a sleeve's first ten months** (vol window warms at 30 sessions,
  trend window at 200), so a new sleeve runs at the cap while the gate has nothing to say, and
  that happens where the records are thinnest. Pinned by
  `test_the_gate_is_disengaged_before_the_trend_window_fills` so a future fix is a decision.
- **Costs are the flat 2 bps**, not the policy's real turnover, and no market-impact model
  touches a 1.3× sleeve in a February-2018 gap.
- Nothing here is out of sample. Every number is the same archive the candidate was built on,
  and the forward book is still the only thing that can answer whether any of it transfers.
- The forward book was **not** advanced this round: a fresh fetch into a scratch directory
  returned the same 73,009 rows through 2026-09-04 (a Friday), so there was no new session to
  seal and no reason to move `data/current` out from under the numbers above.

## Standing rule added

> An edge must be scored against its own weights read backwards — same exposures, wrong
> months. Anything the reversal matches was never timing.
