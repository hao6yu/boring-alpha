# The brake cost less than nothing, and the ruin gate was the real one

Goal round 2 (of 96), `goal-91eb485f…`. Yesterday's round built `tools/ba005.py` and got a fee-independent FAIL on the drawdown gate. This
round finishes the objective's step 3 — the ruin promise, which is the half of "earn extra monthly income" that actually asks a question —
and writes the step-4 bar that the failure obliges me to state.

## Step 3, priced with the archive's own machinery

Not a new simulator: `tools/ba005.py` calls `monthly_income_race.safe_amount` and `plan_stats`, the same functions that produced the equity
book's headline $435/mo, so the crypto numbers are comparable to that figure instead of being a new invention with a similar name. One thing
had to give: the horizon. Ten years is the archive's convention, but 123 months of BTC history contains four 10-year windows, and four
windows is not a distribution — so the horizon is 5 years, giving 64 windows, and that is printed rather than buried.

```
    the ruin promise · 5-year windows · 64 of them · failure budget 5% · one window is 1.6 points, so a 1.6-point gap in
      P(fail) is one plan, not a trend
    QQQ's own affordable bill at that budget: $1,019/mo to end whole · $2,000/mo to never reach zero
    leg                        P(fail) ends whole   median  P(erase)  at the bill
    QQQ, held                                 5%     1.38x       0%       1,019
    BA-005, fee = 0                           6%     4.10x      16%       1,019
    BTC-USD, held                            14%     6.32x      32%       1,019
```

Read the middle pair carefully, because it is the trap in this table. 6% against 5% is **one window of 64** — 4 failing plans against 3 —
and on this record that is the resolution limit, not a finding. The tool therefore prints the resolution inside the same block as the rates,
and its gate fires only when the candidate fails more often *and* is more often halved. The last column is the one with evidence behind it:
**16% of windows in which BA-005 watches its capital halve, against 0% for the index**, at the same $1,019/mo draw, on the same windows.
Median terminal is 4.10x against 1.38x. That is the shape of the whole thing: much more money if it goes right, and one window in six where
the income plan stops being an income plan.

## The verdict

Both locked risk conditions fail — drawdown 56.5% against 40.7% allowed, ruin no better than the index at the index's own bill — while the
terminal is 17x the index's and the break-even fee is 1,333 bps a side. **BA-005 is archived as a failure and there is no fifth forward
book.** The spec now carries the step-4 statement the objective asked for; the short form, in the order that matters:

1. **Costs are not where a Coinbase rule can be beaten** at monthly frequency. Spread is fractions of a basis point (measured, r110), the fee
   is a fraction of a percent, and the asset moves enough to make 1,333 bps the break-even. So any future candidate must be *risk-specified
   before it is return-specified* — otherwise it is graded on the one axis that cannot lose it.
2. **Full-weight single-asset crypto cannot clear the drawdown gate.** BTC's own worst fall inside this window was 76.7%; the budget is 40.7%;
   a monthly brake recovered 20 points and still left 56.5. A Coinbase candidate therefore has to hold the volatile asset at a *fractional
   sleeve* — which changes the question from "beat QQQ" to "beat a blend of QQQ and the asset", a question this repository already knows how
   to price and has already answered in the archive's standing favour: doing less won.
3. **The overlay must earn its brake.** +2.9% over ten years is not a model, it's a seatbelt: the objective is better served by holding the
   asset with a size limit and no model at all.
4. **P(erase) is the bar, not P(fail).** 0% versus 16%. A 5% budget on 64 windows cannot even resolve a 1.6-point difference, so a candidate
   that only clears P(fail) hasn't been tested.

## What this changes about the goal, honestly

The objective was "a Coinbase-executable model, not worse than plain VOO/QQQ". Two rounds of work on a live Coinbase archive, with the fee as a
missing input and then as an irrelevant one, produce the same conclusion the equity archive keeps producing in a new asset class: the money in
the record is the asset's, not the model's, and the model's own contribution was a brake that cut the drawdown by 20 points, added +2.9% over
a decade, and still failed the promise it was written to keep. Nothing here is a claim crypto can't work; it is a claim that *this* pre-registered idea doesn't, on
*these* terms, and that the terms were right to lock first.

What I'd do next, and it is a smaller thing than a new strategy: the sized-sleeve question in point 2 is answerable with machinery that
already exists (sleeve tables, P0, the ruin functions used above) and needs no new data, no new venue, and no fee record — a Coinbase-sized BTC
sleeve at 5/10/20% against the P0 blend, graded on P(erase) at the index's own bill. If that loses — which the archive's history suggests it
will — the honest answer to the objective is that a Coinbase account's best monthly-income use is the boring one, and I should say so in one
line rather than generate candidate number six. The forward loop is untouched either way: first real seal 2026-09-30, 23 entries to a skill
claim.

## Checks

**2400 passed, 239 subtests** (2396 + 4 new; collected count printed before the run). Rules: **112**. Nothing in the runbook's pricing
changed — P0 is still 100% VOO, still priced before evidence, and the equity legs here pay nothing to enter, which is the conservative side of
the asymmetry.

*Goal round 2. The Coinbase model is fully graded and archived as a failure on its own locked terms, the failure bar for the venue is written
down, and the remaining honest question is smaller than the one I started with.*
