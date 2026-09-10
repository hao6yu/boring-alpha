# BA-012 covered-period profitability diagnostic

**The current $5,000 configuration made no trades in the covered simulation.**
From July 1, 2022 through December 31, 2023, the account ended at **$4,916.30**
after $83.70 in modeled recurring data fees. The calendar annualized return was
**−1.1161%**. This is a fully reconciled, restricted-period cash/expense result;
the planned full 2018–2023 trading-return study remains unresolved.

The user explicitly requested profitability testing after the download and
sizing results. The diagnostic window and account rules were recorded before
calculating this ledger. The window was selected after inspecting data coverage
and known cash decisions, so it is not independent validation. It is the longest
fully covered consecutive sequence supporting return months within the original
development period. No frozen strategy parameter or settlement rule changed.

## Modeled account results

| Metric | July 2022–December 2023 |
| --- | ---: |
| Starting equity | $5,000.00 |
| Ending equity | $4,916.30 |
| Trades | 0 |
| Gross trading profit/loss | $0.00 |
| Monthly data fees | 18 × $4.65 = $83.70 |
| Net profit/loss | **−$83.70** |
| Total return | −1.6740% |
| Calendar CAGR | −1.1161% |
| Maximum marked drawdown | $83.70 / 1.6740% |
| Account halt | No |
| 4% annual cash-scenario ending value | $5,303.84 |
| Shortfall to 4% cash scenario | $387.54 |
| 6% annual cash-scenario ending value | $5,457.99 |
| Shortfall to 6% cash scenario | $541.69 |

The account is continuous with no annual reset or deposit. July–December 2022
loses $27.90 in fees, leaving $4,972.10. Calendar 2023 then loses $55.80, leaving
$4,916.30. CAGR and benchmark compounding use 549 calendar days and a 365-day
year, as specified. The cash rates are research scenarios, not assertions about
a currently offered account rate. Base and stressed trading-cost cases coincide
because neither has an execution.

## Why the account stays flat

The June 30, 2022 monthly signal seeds the first July session. Each subsequent
month uses the preceding month's completed signal, ending with November 30,
2023 for December. The December 2023 signal is not used to trade in December.

Every one of those 18 monthly decisions has a verified necessary infeasibility
proof at $5,000: fewer than three market groups can hold even one contract
within the frozen individual risk and money limits. The strategy requires
three groups and an 8% annual volatility cap. This is a sizing constraint on
this configuration, not evidence about the return quality of the trend signal.

The ledger independently recomputes each one-contract bound at actual equity
before and after the monthly expense, including the remaining $1,000 loss
budget after drawdown. Falling equity cannot restore a missing feasible group.
Execution-day rechecks can only reduce planned quantities, and daily updates
cannot reopen positions between monthly instructions. Starting in cash therefore
determines a zero-position account path throughout this interval.

All 377 joint-session dates have complete preceding-day and same-day 252-interval
risk windows. No missing interval was filled, omitted or classified as cash to
obtain this result. No execution price or held-position mark is invented: there
are no orders or holdings requiring one. Fees occur on the first joint session
of each month, and the initial $5,000 high-water mark never resets.

## Limits and remaining question

The modeled fee and zero-interest assumptions come from the existing protocol.
Taxes and hosting costs remain excluded there. The separate $0.6114 estimated
research-data acquisition expense is not added to historical recurring operating
fees. This parent-history exposure setup does not establish native child fills,
broker availability, or funded results.

The result does not pass either cash hurdle. It establishes inactivity and its
modeled cost in the covered $5,000 configuration. Larger-capital and continuously
divisible implementations have not had their profitability tested.

The full 2018–2023 Stage B test has not been run. Forty-seven of its Stage A
monthly sizing windows remain incomplete under the frozen reference eligibility
rules, and no participation has been established at $5,000. A trading ledger
with nonzero positions would also need the specified execution observations;
daily settlement prices would not by themselves supply those fills. The
2024–2025 holdout remains unopened.

## Reproduction

- Frozen diagnostic plan: `research/ba012-profitability/covered-cash-plan-v1.json`
- Reproducible calculation: `research/ba012-profitability/covered_cash_ledger.py`
- Daily ledger, monthly instructions, annual summaries and benchmarks:
  `research/ba012-profitability/covered-cash-result-v1.json`

The calculation verifies pinned source hashes and calendar/risk coverage before
producing results. The plan and result have SHA256 sidecars. Existing artifacts
are preserved; rerunning with the same output filename refuses to overwrite it.
Two independent reviews reconciled the calendar, lagged instructions, actual
equity risk bounds, fees, annual continuity, drawdown and benchmark arithmetic.
