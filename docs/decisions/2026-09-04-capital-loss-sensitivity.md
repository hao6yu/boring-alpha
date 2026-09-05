# Capital-loss deductions: explicit, non-gating sensitivity

Date: 2026-09-04. The holder accepted this approach after the branch review.

BA-002's existing eight tax scenarios and eligibility gates remain unchanged.
Their baseline excludes the ordinary-income capital-loss deduction. Add a
separate diagnostic, off unless explicitly requested with `aftertax
--loss-sensitivity POLICY`, rather than assuming the maximum deduction benefits
every investor or treating an estimated tax saving as a strategy improvement.

## Assumptions and arithmetic

The IRS generally permits a net capital loss to offset ordinary income up to
$3,000 per year ($1,500 married filing separately), with unused losses carried
forward. The year's allowable deduction reduces the carryover, consuming
short-term losses first. This is a tax-return-level calculation, not an
independent allowance for each account.
[IRS Topic 409](https://www.irs.gov/taxtopics/tc409),
[Publication 550, Capital Losses](https://www.irs.gov/publications/p550).

The policy explicitly declares annual unused capacity, available outside
ordinary taxable income, savings destination, and an optional ordinary rate
override. These fixed annual scenario assumptions are not inferred from this
account or the holder's finances. They do not calculate tax brackets, other
household capital trades, benefit phaseouts, NIIT, state taxes or future tax law.
Capacity is limited to $3,000; an MFS scenario must supply its lower applicable
capacity. The checked-in example uses zero capacity and zero outside income.

For each year, net capital items with character-preserving carryovers first.
Then consume the lesser of remaining losses, declared capacity and declared
outside taxable income, reducing short-term carryovers before long-term ones.
Apply the declared marginal ordinary rate to that deduction. Subsequent years
use only the reduced carryovers. Compute the final year with and without
terminal liquidation from the same incoming carryovers so neither the
deduction nor its tax savings are counted twice.

`outside_account` keeps the savings in a separate household cash balance with
zero assumed return. It does not credit account performance with an outside
refund. `contribute_to_account` explicitly injects those savings into the
existing stylized NAV-rescaling calculation and reports the deposits. It is
not an exact model of purchasing real tax lots with tax refunds or raising
cash to pay tax. Contribution-mode self-financing CAGR, tax drag and the
mixed-account-size effective-tax-rate ratio are not
reported; compare terminal account/household wealth and declared cash flows.
Both modes retain the overlay's year-end timing convention, not actual filing
or refund dates. Each account/scenario is a separate counterfactual; do not
sum their capacities or savings.

## Identity and interpretation

Separate `tax-loss-sensitivity-*.json` artifacts contain baseline results,
sensitivity results, resolved policy/hash, code/input identities and account
size. They do not replace `tax.json` or criteria. Classification rejects a
sensitivity record as a gating account. Existing ordinary `aftertax` calls
continue to run the baseline eight-scenario grid.

The research account is already $100,000. A fixed-dollar deduction breaks
scale-free comparisons; a $2,000–$5,000 account needs its own explicit analysis.
The review's roughly 60-bps estimate was a screening approximation, not a
recomputed incremental return. It is not adopted as a verified bound or
published performance result. No historical account was evaluated under this
new sensitivity during implementation, and BA-001's archived results remain
unchanged. Any later historical recomputation needs its own deliberate run.
