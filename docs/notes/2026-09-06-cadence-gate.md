# The review cadence was a comment, so the numbers moved (2026-09-06, round 10)

```
.venv/bin/python tools/run_voltarget_scan.py --candidate
.venv/bin/python tools/funded_policy.py --sleeve SPY --window full
.venv/bin/python -m pytest tests/test_funded_policy.py tests/test_voltarget.py -q
```

## What was wrong

Round 9's write-up ended with a sentence saying the engine's `allow` argument "is decorative"
and left it there. It was worse than decorative. The trade test read:

```python
if delta and (allow is None or started or position in allow or abs(delta) > 1.0):
```

`started` is set on the first session and never cleared, so from the second session onward the
expression is true no matter what `allow` says; the second refusal, `abs(delta) < 1.0`, is a
one-dollar floor on a book that reaches six figures, so it refuses nothing either. The argument
could refuse exactly one trade — the opening one — and it refused that one by accident.

The consequence is that every number in the repo quoting a *reviewed* policy has been quoting a
different rule: the one that rebalances whenever drift exceeds ten percent of the account, which
is what the band alone does. The candidate is specified as a five-session review. On the full
archive it was being simulated into 241 fills.

## What the fix does

`run_voltarget_scan.funded` now refuses a non-reviewed session whatever the drift says, with two
exceptions and both of them necessary:

- **the opening fill** — an account that cannot buy on day one reports zero as a result;
- **the maintenance forced sale** — a margin call is not a rebalance and no cadence should
  pretend to be allowed to prevent one.

`funded_policy.score()` passes the gate to the four rows that claim the rule (candidate loose,
candidate as traded, reversed, no-gate), derived from each row's *own* weight path by
`reviewed_sessions`. It does not pass it to the comparator or to the two flat rows, which have
no cadence to honour; gating a buy-every-deposit index fund would have invented one and then
charged the policy for the difference.

The loose encoding is gated too, and stays expensive. That is the point of the fair comparison:
raw weights change on almost every session, so the reviewed set for the loose row is almost every
session, and the gate cannot rescue an encoding that is not the traded one. The 12% gap between
the two rows survived the fix intact.

## The pre-registered scan, re-measured

Same archive (8,457 sessions), same candidate, same costs. Only the engine changed.

| window | comparator | gap before | gap after | fills before | fills after |
|---|---|---|---|---|---|
| full 1993..2026 | $1,903,583 | +$156,921 | **+$113,439** | 241 | 222 |
| seen A 2007-06..2017-12 | — | +$5,089 | **+$1,845** | 75 | 65 |
| seen B 2018..2021 | — | −$1,195 | **−$967** | 37 | 32 |
| recent 2022..2026 | — | −$268 | **−$1,020** | 38 | 29 |

Nineteen fills on the full window, and 3.7% of the terminal, belonged to a rule nobody
pre-registered. Two of four windows beat the comparator before the fix and two of four after, so
the classification is untouched: the pre-registration's bar was all four windows, and the
candidate is still `Redundant`. What changed is the size of the thing being declined — a
full-window beat of $113k on ~$5.1m deposited is roughly $32 a month, not $44.

The pre-registered document itself is not edited. The scan prints its numbers fresh; the note
that recorded them keeps them, and this note is the reason they differ.

## The corrected deposit-frame table

Same convention as round 9 — $5,000 opening, $500 a month, 2.0 bps per unit of one-way turnover,
borrow at the archive's cash index plus 150 bps on the borrowed leg, the sleeve's real expense
ratio, 30% maintenance with forced sale — with the cadence gate now binding on the four policy
rows. Archive `20260906T203953Z`, through 2026-09-04.

| window | sleeve | gap vs DCA | $/mo | own avg flat | no trend gate | reversed | DD | DCA DD | fills |
|---|---|---|---|---|---|---|---|---|---|
| full | SPY | **+$110,780** | **+$32** | −$102,411 | +$47,092 | −$445,452 | −23.9% | −52.7% | 222 |
| full | QQQ | −$286,287 | −$79 | −$546,023 | +$218,555 | −$1,033,785 | −23.6% | −57.4% | 239 |
| full | VTI | −$76,250 | −$46 | −$25,945 | +$98,421 | −$274,741 | −22.1% | −47.7% | 163 |
| full | ITOT | −$32,395 | −$25 | −$36,415 | +$58,229 | **+$243,595** | −20.0% | −42.4% | 149 |
| full | VOO | −$42,226 | −$62 | +$14,808 | +$13,913 | −$62,924 | −22.1% | −33.7% | 88 |
| since 2010 | SPY | −$84,358 | −$111 | +$20,969 | +$15,205 | −$52,145 | −25.4% | −33.5% | 109 |
| since 2010 | QQQ | −$162,718 | −$134 | −$36,604 | −$46,896 | −$134,985 | −22.3% | −34.0% | 170 |
| since 2010 | VTI | −$73,216 | −$100 | +$13,431 | +$6,658 | −$91,708 | −26.2% | −34.7% | 108 |
| since 2010 | ITOT | −$74,842 | −$102 | +$16,139 | +$5,046 | −$73,272 | −26.2% | −34.8% | 108 |
| since 2010 | VOO | −$42,226 | −$62 | +$14,808 | +$13,913 | −$62,924 | −22.1% | −33.7% | 88 |
| recent | SPY | −$1,067 | −$13 | −$915 | +$117 | −$2,760 | −10.1% | −16.1% | 29 |
| recent | QQQ | −$4,494 | −$50 | −$3,238 | −$1,732 | −$7,341 | −13.0% | −20.3% | 44 |
| recent | VTI | −$1,712 | −$21 | −$130 | −$219 | −$3,363 | −12.0% | −16.6% | 31 |
| recent | ITOT | −$1,797 | −$22 | −$209 | +$78 | −$3,537 | −12.1% | −16.7% | 31 |
| recent | VOO | −$853 | −$10 | −$806 | +$224 | −$2,155 | −10.0% | −16.0% | 29 |

(VOO's "since 2010" is its whole record, so it appears twice for want of a second window to
separate; thirteen distinct cells. ITOT full is again the cell where the scrambled weights beat
the ordered ones — the same sleeve round 8 found unreadable in eleven windows.)

Six readings, all of them true:

- **Dominance is where it was: the candidate clears DCA in 1 cell of 15**, SPY over the full
  record, by $32 a month. Everywhere else the index wins, and in the window a new account would
  actually live through — 2022 on — the shortfall is $10 to $50 a month.
- **It beats holding its own realized average weight flat in 3 cells of 15** (SPY full, QQQ full,
  ITOT full), up from two. The gate takes away more from a book that was drift-trading than from
  one that was drift-trading at a *constant* weight, so the control moves further away.
- **Drawdown is shallower in 15 of 15, and by at least a quarter in 12.** That did not move. The
  insurance is still the product; SPY's −23.9% against −52.7% is the whole case for the rule.
- **The gate is worth more than the trend filter.** The gateless vol target beats the candidate in
  14 of 15 cells and clears DCA in 12 of them, at *higher* average exposure. Under the un-gated
  engine that gap looked narrower because drift was doing the gateless row a favour.
- **The reversal control weakened, and it should be read as weakened.** Read backwards, the same
  decisions lose to the ordered ones in 11 of 15 cells rather than 14 — and on ITOT full the
  scrambled order is the only row on the grid that beats both the candidate and the index,
  +$243,595 against −$32,395. Round 8's verdict on that sleeve was "unreadable in eleven
  windows"; this is the same fact wearing the deposit frame.
- **Nothing on this grid pays.** The one positive cell pays $32 a month for a rule that halves
  drawdown. If the objective is dollars per month from a $500 deposit, that is not it, and the
  mechanism that has cleared the index in every frame it has been measured in remains broader
  exposure, which is round 4's finding and not a trading model.

## What the tests do

`tests/test_funded_policy.py` gained `TheCadenceGateIsEnforced` (six tests). The load-bearing one
is not a policy test at all: a hand-set allow of *one session out of eight thousand*, on a book
carrying its full weight, must produce exactly one fill. It does. The same vector un-gated
produces 21, so the control that is supposed to churn churns, and the razor is not cutting air —
that control failed first with a threshold of 50 invented out of optimism about SPY's compounding
rather than read off the archive, and was corrected to a ratio against the gated row.

Also pinned: `reviewed_sessions` against a hand vector, so the set that decides what may trade is
not verified by the trades it produces; the gate strictly reducing the fill count of the vector
the row actually uses; the loose encoding staying loose once both are gated; the opening fill
surviving an allow set that excludes the opening session; and `band=0` being deadly only when no
one says where the reviews are (gated, the same vector books less than a tenth of the fills).

The round-9 tests that priced the naive un-gated call site were left un-gated deliberately, and
their docstrings now say so: they document the damage a caller does by not passing the argument,
which is a different claim from "the engine enforces cadence".

## Rule this round adds

**Test that a guard can refuse.** An argument that cannot change the output is a comment wearing
an argument's clothes, and every number that appeared to be enforced by it was an accident with a
citation attached.
