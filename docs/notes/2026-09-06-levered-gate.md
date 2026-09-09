# Round 12 — the same decision, mounted on leverage (`tools/levered_gate.py`)

Round 10's candidate has the shallowest drawdown in 15 of 15 cells and is a cash loser in 15 of 15:
insurance, not income. Round 11's constant leverage — no signal in it at all — clears the entire
financing menu from 1.25x up, with a drawdown about 2.5x as deep. Nobody has asked the question the
goal actually needs asked: **does the decision keep earning once it is allowed to drive a bigger
car?** A timing rule that only works at 1.0x is advice about where to sit, not a way to make money —
and leverage is the only mechanism that makes an account's exposure exceed its deposits, so it is the
only frame in which a timing rule *can* produce dollars.

`tools/levered_gate.py` runs the candidate's own weight path multiplied by a leverage factor — at
`L` the pre-registered 0.30 floor becomes `0.30L` and the 1.30 cap becomes `1.30L`, which is what
"the same rule at 2x" means: on a trend break the book cuts to 30% *of the levered target*, not to
30% of equity — on five sleeves × three windows × five levers (1.0, 1.25, 1.5, 2.0, 2.3), seven
books, two desks, and bills every book at a posted brokerage rate.

Run: `.venv/bin/python tools/levered_gate.py` (about twelve seconds for all 75 cells). The engine
accrues `cash_daily + spread` on the borrowed leg; a desk charging `r` all-in is passed a spread of
`r` minus that window's own annualised cash, holding the total at the posted rate on average.
Passing the posted rate as the spread charges the cash rate twice and overstates every desk by
150–400 bps, which is most of what this tool exists to measure.

## Pre-registration, written before the grid was run

Three readings were fixed in advance, on the cheap desk (Public, 4.90% posted — the base tier an
account of this size actually pays):

  **A** — beats DCA *and* beats its own-exposure flat at some lever, on most sleeves, with the
  reversed path doing worse: the decision is worth money at scale, and the drawdown column is the
  price, stated. **B** — clears DCA but not its own-exposure flat: the money is the borrowing, the
  instruction is "buy more index, financed cheaply", and that is round 11's answer, not a bot.
  **C** — clears nothing at any desk at any lever: the gate is Redundant at leverage too.

Four things were declared before any number existed, and they are the shape of this write-up as much
as the table is:

1. **DCA gets `band=0`.** The first draft handed every row the candidate's 10% band, including the
   comparator. On a deposit book a band is a *handicap*, not a convention: a $500 deposit is under
   10% of the account from the first year onward, so it sits in cash, and SPY's recent window came
   out at 14 fills, 95.5% invested and **$607 poorer** than the same run banded at zero. Every policy
   row was being compared against a benchmark that had been held down — the asymmetry round 11 was
   written to forbid, pointed the flattering way. The comparator is the sealed shadow's rule, pinned
   by `test_the_comparator_is_not_handed_the_policys_band`.
2. **The timing claim is the worse of two matched controls.** One flat row is not enough, because
   what the control does *between* reviews is a second design choice. The no-cadence control
   (`flat`) follows `financing_break_even`'s rule — suppressed below 1.25x, 10% band above — and at
   `L < 1.25` that band is a real handicap on it: 8,428 fills against the calendar row's 7,120 on
   SPY recent, and it loses more in the crash. The calendar-reviewed control (`flat tight`, 1% band,
   reviewed every five sessions — the candidate's own cadence) is only handicapped in a way no real
   implementation would be, because a bot can check the clock. So the verdict column is
   `min(vs_flat, vs_matched)`: the candidate must clear the stronger of its two matched controls at
   every lever. Where the two disagree, 2.0x and 2.3x, the count of cells clearing both falls from
   9/15 and 11/15 to **6/15 and 8/15**.
3. **Every policy row is run at the tight band too** (as a column, never in the verdict): the review
   gate only bites for a book that can act between reviews, and a 10% band guarantees it cannot. A
   10% band is a quarterly-review convention sitting on an engine that computes a new target every
   day.
4. **The grid's maxDD is not a price.** The question the goal asks is what the rule earns at the
   leverage whose *pain* equals the index's, so the second table bisects `L` per cell until the bot's
   maximum drawdown equals the DCA comparator's and prints that row. Its bracket may fail to cross
   in either direction — a solved `L` outside 1.0–2.3 is a different rule, past the 3.0x weight the
   policy itself calls credible — and both failures print as their own sentence.

## What the grid says

$5,000 opening, $500 a month on arrival, the sleeve's real expense ratio, 30% maintenance equity with
a forced sale to 1.0x on breach, every row — comparator included — opening on the session the
*policy* can first answer. Cheap desk Public 4.90%, dear desk Fidelity 10.575%. Medians over 15 cells.

| lev | clears DCA | clears at Fidelity | beats both controls | beats index on both axes | reversed worse | $/mo cheap | $/mo @10.6% | maxDD | flat ctrl | index | calls |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.00x | 1/15 | 0/15 | 4/15 | 1/15 | 11/15 | −68 | −113 | −21.8% | −35.0% | −33.7% | 0 |
| 1.25x | 12/15 | 2/15 | 4/15 | 12/15 | 14/15 | +40 | −87 | −26.6% | −41.9% | −33.7% | 0 |
| 1.50x | **15/15** | 5/15 | 5/15 | 10/15 | 14/15 | **+98** | −65 | −31.0% | −48.0% | −33.7% | 0 |
| 2.00x | 15/15 | 7/15 | 6/15 | 4/15 | 15/15 | +251 | −52 | −39.8% | −59.3% | −33.7% | 0 |
| 2.30x | 15/15 | 5/15 | 8/15 | 1/15 | 15/15 | +524 | −154 | −45.5% | −65.0% | −33.7% | **12** |

The tool prints **verdict A at 2.30x**, which is the honest reading of the rule as written and the
least useful row in the table: A arrives at 8/15, with 12 margin calls and a median −45.5% drawdown.
At the levers where nothing is called — up to 2.0x — the verdict is B-shaped: clears DCA, clears the
index on both axes in 10 of 15 at 1.5x, but beats its own matched exposure in only 5 of 15. The
mechanism that clears the index in every frame remains *exposure plus cheap financing*, exactly as
round 11 left it, and the bot's contribution stays a coin-fair on the timing claim.

Three things in that table are worth more than the verdict:

**The custodian is a level, not a detail.** Clearing the dear desk peaks at 7 of 15 at 2.0x and falls
back to 5 of 15 at 2.3x, because the forced deleveraging a margin call causes at a high rate undoes
the compounding the leverage was supposed to deliver. The dear column is *negative in every lever*.

**The drawdown is bought back, unevenly.** 1.0x is insurance (shallower in 15/15, cash-negative in
15/15); 1.25x is the first lever that pays anything (+$40/mo) and still pays for it in drawdown;
above 1.5x the drawdown column stops shrinking relative to the flat control and the margin calls
start. Both-axes peaks at 1.25x (12/15) and collapses to 1/15 at 2.3x.

**The band is worth a few dollars, given the cadence.** `band_wedge` is tight-minus-wide with the
review gate held fixed — not round 10's encoding wedge, which on this same book and desk is worth
**+$231,187** ($1,775,832 for the raw path against $2,007,019 for the held one, 400 turns against
222). The encoding still dwarfs the band; this tool deliberately holds the encoding at round 10's
as-traded row so the leverage question is asked of the book r10 said to trade. Given that, tightening
is not automatically free and the sign flips by sleeve: SPY full −$4,036 at 1.0x, −$6,683 at 1.5x,
−$85,859 at 2.3x; VTI full −$2,745, **+$6,733**, −$4,616. A column, not an assumption.

## Matched pain: the same drawdown as the index, and what it earns

Solving `L` per cell so the bot's worst month equals plain DCA's worst month, the solved leverage runs
**1.32x to 2.30x**. Every solved row lands within 0.44 pp of its target except QQQ full, where the
bracket's top bound binds and the row sits 1.68 pp short.

- median **+$95/mo** at the cheap desk, **−$65/mo** at Fidelity;
- clears the index at the cheap desk **14/15**, at Fidelity **4/15**;
- beats its own matched exposure (worse of the two controls) in **6/15**;
- clears on both axes in **4/15**, and in **0/15** at Fidelity;
- SPY since-2010 solves and pays **−$1/mo** — the index's own −33.4% drawdown is shallow enough that
  the leverage required only adds interest.

Same pain as the index, a median ninety-five dollars a month, and the timing claim still unproven.

## Proof that the plumbing works

`funded_policy` (round 10) prices at the engine's standing assumption, a spread of 150 bps over
archive cash. Put *that* desk in this tool's menu and the policy row reproduces round 10's as-traded
SPY full row to the cent — **222.0 turns, $2,007,019.29**, difference 0.000000 — which is the only
claim two tools that share an engine are obliged to get right. `test_priced_at_the_engines_own_assumption_it_is_round_tens_tool`
holds it. The row's margin over the index is +$110,780 (ending $2,007,019 against the comparator's
$1,896,239), and the tool's `avg_weight` 0.965 and drawdown −23.9% match too.

Then, on the same book, replace that desk with the cheapest one the April menu actually contains —
Public at 4.90% posted, which over this window is a spread of 2.36% against the engine's standing 150
bps — and the margin falls to **+$45,773**. A round 10's margin over the index was 59% financing
assumption, which is what it looks like when the assumption is charged for: the engine's 150 bps is
not nothing, it is 65% of the money.

## Guards, and what refuses

`levered_desired` **refuses** rather than clipping when `max_weight × L` would exceed the 3.0x weight
the policy's own range declares credible — a clipped cap is a different rule reported under the old
rule's name. The candidate's 1.30x cap therefore accepts 2.30x, where the cap lands exactly at 3.00x,
and refuses 2.31x with `2.31x puts the cap at 3.00x, past the 3.0x range the policy itself calls
credible — refusing to answer rather than clipping the rule`; that boundary is why the grid stops at
2.3x
(`test_a_lever_that_would_clip_the_rule_is_refused`; mutating the guard's predicate to `> 99.0` fails
it). A window too short to open an account at the policy's first live session plus 400 sessions
refuses too — note it is *this* guard that fires, since `financing_break_even`'s 252-session floor is
the weaker one (`test_a_window_too_short_to_open_an_account_is_refused`). The review calendar
must actually bind: `flat tight` refuses to trade on a session outside it and trades on the one after
(`test_the_calendar_control_cannot_trade_on_a_session_it_is_not_let_on_to`), and giving that row `False`
instead of `"calendar"` fails the test.

Six mutations, each killing a test: the comparator re-handed the 10% band; the posted rate passed as
the raw spread so the cash rate is charged twice; the verdict taken against the friendlier control;
the clip guard's predicate raised past any real lever; the bisection bracket moved the wrong way; the
calendar control made decorative. The third is the one that mattered, and the fifth is a bug the tool
had.

**The bisection was wrong before it was right.** The first version moved `bottom` to the trial
whenever the trial was shallower than the target — the opposite of correct — and the printed levers
(1.40x, 1.35x, 2.00x) looked *more* plausible than the fixed ones while the solutions were
nonsensical. The symptom that gave it away is the one to look for in any solver: 12 of 15 cells
reported a clean crossing, and the rows that reported "already as deep as the index at 1.0x" were
exactly the rows where the bracket's own drawdown was *shallower* than the target at both ends — the
incoherence was visible in the note column if the note column had been printed there, so the solver
now prints how far off `hit by` on every row. The median matched-pain figure the broken solver would
have printed, **+$273/mo against the true +$95/mo**, is what a solver that never lands outside its
bracket costs a write-up. The regression test asserts `abs(dd_gap) <= 0.006`, not the solved lever:
the original test asserted only that the lever lay in [1.3, 2.3], and it **passed on the broken
solver**, because every wrong solution stayed inside the bracket. What now catches the sign flip is
`test_the_solver_reports_which_branch_it_took`, which asks for a solve that cannot cross
(`low=2.3`) and requires the *floor* branch's sentence rather than a number.

## What this means for the goal

The goal is a model that earns extra each month and beats VOO/QQQ. On this evidence, in the deposit
frame, at costs a retail account actually pays:

- **The operating point is 1.25x–1.5x at a cheap base-tier desk**: +$40/mo at 1.25x with zero calls
  and a drawdown 7 points shallower than the index's, or +$98/mo at 1.5x with the drawdown 3 points
  shallower. Both are positive against DCA in 12–15 of 15 cells.
- **The same two rows are −$87 and −$65 at Fidelity's 10.575%.** Nothing about this strategy survives
  contact with a 10% desk. The decision at 1.5x adds about $160/mo of value between the cheapest and
  dearest base tier on the table — four times the median return of the strategy itself. Round 11 said
  the instrument and financing dominate sizing; this says they dominate the *timing rule* too.
- **The timing claim itself remains unproven at every lever** — 4/15 to 8/15 against matched exposure,
  and the tool's own verdict at the call-free levers is B: the money is the borrowing.
- So the mechanism that beats the index in every frame remains broad exposure financed cheaply, and
  the remaining untested lever against the goal is the one round 3 named: 56–58% weekly directional
  accuracy, which no input in this archive has ever come close to.

## Rule learned (r12)

**Test the rule at the leverage it would run at, and compare it to the exposure it took, not the
exposure it asked for.** A timing rule measured at 1.0x is measured on a frame where it cannot change
the account's size, only its shape; measured at 2.3x it finally produces dollars and finally loses
them the same way. The two numbers that must appear side by side are the leverage and the realized
average weight, because at 2.3x the candidate holds 1.4x — a rule asked for leverage and was given
exposure, and the control that owes it is the one that held what it held. And every solver in the
tool needs a column that says how far off it landed, because a bracket moved the wrong way still
returns a number inside the bracket.
