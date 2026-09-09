# The candidate as a monthly deposit account (2026-09-06, round 9)

> **Table superseded the same day, two rounds later.** The funded simulator's review-cadence
> argument turned out not to bind, so every row below that claims a reviewed policy was priced
> as a band-rebalance rule instead. The correction, the re-measured numbers and the verdict that
> did not move are in [the cadence gate note](2026-09-06-cadence-gate.md). The table is left as
> printed: a revised claim is a record, a rewritten one is nothing.
```
.venv/bin/python tools/funded_policy.py                      # all sleeves, full window
.venv/bin/python tools/funded_policy.py --sleeve QQQ --window recent
.venv/bin/python -m pytest tests/test_funded_policy.py -q
```

## The question round 8 did not answer

Round 8 scored the pre-registered candidate as a *withdrawal*: of the money already sitting
there, what monthly amount survives every start month. It cleared the index on SPY ($518
against $379) and the reversal control said the gain was timing rather than exposure. That is
the right question for a pot being spent down. It is not the question the goal asks, which is
" money goes in every month — does this bot end with more of it than just buying VOO".

Round 7 said to expect a different answer and to expect it honestly: the same dial moved the
accumulation number up and the decumulation number down, and both readings were correct. A
gate that sells into a collapse protects a plan taking money out; a plan putting money in is
*buying* that collapse with its next deposit.

**Answer: on the deposit frame the candidate is dominated. It beats plain DCA in 1 of 15 rows,
loses to holding its own average weight flat in 13 of 15, and its drawdown is shallower in all
15 — materially so, by at least a quarter, in 12.** It is insurance, not income. The one cell it clears — SPY over the
full record, the one containing 2000–2002 — it clears by 47% less drawdown, which is the
mechanism working exactly as specified and exactly as billed.

## The table

Cadence-faithful encoding, repo convention ($5,000 opening, $500/month, deposited on arrival,
2.0 bps per unit of one-way turnover, borrow at the archive's cash index +150 bps charged
daily on the borrowed leg, sleeve's real expense ratio, 30% maintenance with forced sale).
Gap is terminal dollars against plain DCA into the same sleeve; `$/mo` discounts that gap at
the *comparator's* own rate, so a candidate cannot rate its own winnings.

| sleeve | window | gap | $/mo | same weight held flat | no trend gate | reversed | DD | DCA DD |
|---|---|---|---|---|---|---|---|---|
| SPY | full | **+154,046** | **+44** | −24,563 | +125,785 | −460,352 | −25.2% | −52.7% |
| QQQ | full | −231,009 | −64 | −513,914 | +198,945 | −1,046,715 | −24.1% | −57.4% |
| VTI | full | −92,764 | −55 | +3,777 | +85,313 | −258,793 | −22.1% | −47.7% |
| ITOT | full | −29,968 | −23 | +24,416 | +62,601 | +265,485 | −20.0% | −42.4% |
| VOO | full | −34,771 | −51 | +28,448 | +10,636 | −65,007 | −22.5% | −33.7% |
| SPY | since 2010 | −81,699 | −108 | +30,715 | +5,774 | −44,404 | −25.4% | −33.5% |
| QQQ | since 2010 | −156,611 | −129 | −26,651 | −50,351 | −129,355 | −22.3% | −34.0% |
| VTI | since 2010 | −70,626 | −97 | +21,452 | +8,461 | −81,719 | −26.2% | −34.7% |
| ITOT | since 2010 | −74,553 | −102 | +24,295 | +5,719 | −65,118 | −26.2% | −34.8% |
| SPY | recent | −319 | −4 | +400 | −103 | −2,328 | −10.8% | −16.1% |
| QQQ | recent | −4,579 | −50 | −3,040 | −1,732 | −7,070 | −13.0% | −20.3% |
| VTI | recent | −1,620 | −20 | +524 | −133 | −3,593 | −12.0% | −16.6% |
| ITOT | recent | −1,779 | −22 | +432 | +126 | −3,494 | −12.1% | −16.7% |
| VOO | recent | −143 | −2 | +530 | −11 | −2,127 | −10.7% | −16.0% |

(VOO's "since 2010" is its whole record; it is listed twice because it has no history to
separate. ITOT full is the one cell where the scrambled weights beat the ordered ones, the
same sleeve round 8 found unreadable in 11 windows.)

Three readings of the same table, all of them true:

- **Dominance.** Plain DCA wins 14 cells of 15. On a $500/month plan the shortfall in the
  window a new account would actually live through — 2022 onward — is between $2 and $50 a
  month per sleeve, and it is $108 a month on SPY since 2010. The P0 rule's verdict is
  `Redundant`, and this time it is not close in the flattering direction.
- **Insurance.** The gate halves the worst ride wherever the record is long enough to
  contain a real collapse: −25.2% against −52.7% on SPY, −24.1% against −57.4% on QQQ. In the
  recent window it still cuts a third off. That is the mechanism doing its stated job, and it
  is worth something to a human who has to watch the account.
- **The gate is not the part that pays.** The gateless vol target beats the candidate in 13 of
  15 rows and beats DCA in nine of the fifteen rows above — VOO is listed twice for want of a
  second window, so eight of thirteen distinct cells — at *higher* average exposure. What earns in the deposit frame is
  being broadly invested with the vol target riding near its cap; what costs is the trend gate.
  Round 8 found the reverse in the withdrawal frame, where the gate earned $108 a month over
  its gateless twin. Both are right, and which one applies depends entirely on whether money
  is leaving the account.

## Two wiring faults this round found, one of them mine, both of them larger than the result

**Encoding.** The same rule priced three faithful-looking ways:

| encoding | fills | costs | terminal |
|---|---|---|---|
| desired weight + 10% band | 418 | $11,726 | $1,803,243 |
| applied weight + 10% band | **241** | **$6,165** | **$2,050,286** |
| applied weight + band 0 | 8,428 | $7,601 | $2,073,977 |

The policy says it traded 232 times. The middle row is that rule; the first is a different
rule — `raw_weights` is the weight the policy *wants*, and this engine trades toward a want on
every session, so the five-session review interval evaporates and the fill count rises 80%.
Twelve percent of terminal wealth, decided by which function a caller calls. I shipped the
wrong one first, it printed a confident table, and the only reason it was caught is that this
tool cross-checks against `run_voltarget_scan --candidate`, which uses the right encoding and
has since the candidate was pre-registered: on the scan's own archive my tool reproduces its
result at **241 trades and $6,165.22 of cost, to the trade and to the cent**. Pinned by
`test_the_as_traded_encoding_booked_the_rules_own_number_of_trades` and its tripwire companion.

**Warm-up.** I then defaulted the account's opening session to 300, "past every sleeve's trend
window", believing that was the conservative choice. It is not conservative, it is a different
account: `funded` starts at `max(start, first answered target)`, and starting 270 sessions late
forfeits the fourteen monthly deposits that would have landed before it — $7,000 of principal,
$194,000 of terminal value on SPY, 11% of the comparator — and silently deletes 1993 from the
measurement. The repo's convention is `first_live`, which is session 30, the *volatility*
window, because `raw_weights` emits a weight as soon as volatility exists and simply leaves the
gate disengaged until 200 sessions do. The tool now defaults to that convention and asserts it
(`test_the_convention_is_the_one_the_pre_registered_scan_uses`). The gate running unwarmed for
two hundred sessions is a property of the pre-registered rule, already pinned in
`test_voltarget.py`, not a defect of this measurement.

**And one dead guard.** `worst_12m_difference` had a lower bound on the span of a twelve-month
window that could never fire: the grid collapses to one point per month, so thirteen keys are
thirteen distinct months and the shortest twelve steps between them is a year. A negative
control that dropped the guard passed 21 tests, which is how the dead code got noticed. The
reachable fault is the other direction — a thin sleeve with holes steps twelve months across
fourteen or fifteen — so the guard is now an upper bound, and its test prices a hole in a grid
against the same grid without one. `test_twelve_steps_across_a_hole_are_not_reported_as_a_year`.

Negative controls run, each killing a named test: headline the wrong encoding (2 fail), open at
session 0 (1), reverse the array Nones-and-all (3), off-by-one the twelve-month window (1),
widen the span guard until it binds nothing (1), take the absolute value in the annuity (1).

## What this changes about the plan

The candidate stays exactly where round 8 left it: **good at protecting a withdrawal floor and
a drawdown, unremarkable at growth.** This round adds the other half of that sentence, and it
is the half the goal's own words ("earn extra each month") need to hear: as a monthly purchase
it is not a way to earn extra, it is a way to lose a little less badly in a crash. The goal is
not satisfied by it.

What the numbers suggest for the next round, without auditioning anything, in the order the
standing rules make cheapest first:

1. **The gate is the expensive part and the vol target is the cheap part.** A gateless vol
   target at ~1.05 average weight cleared DCA in 9 of 15 cells here. That is not a
   recommendation — it is the same territory round 4 mapped, where a levered sleeve beats DCA
   by borrowing the equity premium — but the *decomposition* is new and cheap to test properly:
   gateless on SPY earns +$126k on the full window where the gated version earns +$154k, and
   the difference is not the leverage, because the gateless row carries *more* of it.
2. **`allow` is decorative**, and this round says so in the open. The engine's cadence argument
   can only ever refuse the first trade, because the test is
   `allow is None or started or position in allow` and `started` is sticky. A real fix belongs
   in `run_voltarget_scan` with a test that a 5-session rule books roughly one trade per
   review and not one per session. Until then every funded number for a cadenced rule is an
   approximation with a known direction.
3. Still open from round 6 and unchanged: the shadow chain duplicates the funded path by hand
   instead of sharing it. This round made the same fault visible from the other side — three
   call sites now encode the same policy three ways, and only two of them are the policy.

Nothing here is out of sample. Every figure is the same archive the candidate was pre-registered
against, and the forward book — one sealed entry — is still the only thing that can say whether
any of it transfers.

## Standing rule added

> **Check the encoding before the result.** Three faithful-looking call sites of one engine
> priced the same policy at $1.80m, $2.05m and $2.07m. A simulator is not a measure of a rule;
> it is a measure of the call that passed it in.
