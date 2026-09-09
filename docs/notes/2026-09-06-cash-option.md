# The only no-variance action in the project is an option on rates, and the record says rates go to zero

Measured 2026-09-06, round 31. Extension to [`cash_yield_gap.py`](../../tools/cash_yield_gap.py) (a new `path()`
and section 2), tests in [`test_cash_yield_gap.py`](../../tests/test_cash_yield_gap.py) (now 15).

Round 30's lesson was that a rate-dependent plan priced off one window is priced off luck. The ledger's
**first-ranked action** — move idle cash out of the default sweep, +$46.12/mo on $20,000, the only large number in
this project with no variance attached — is exactly such a plan. It is priced off today's bill curve, quoted from
four windows, and printed as though 2.88% were weather. Round 30 applied that standard to the loan; it applies
equally to the recommendation this project has been treating as safe.

## The switch, priced in all 404 months of the sealed record

| bill yield | $/mo on $20,000 | what that month was |
|---:|---:|---|
| 6.68% (record high) | +$109.58 | 1994 and 2000 |
| 4.63% (upper quartile) | +$75.36 | 2023-2024 |
| **2.88% (today, 55th percentile)** | **+$46.12** | now |
| 2.13% (median) | +$33.72 | the record's typical month |
| 0.17% (lower quartile) | **+$1.05** | 2012-2021 |
| 0.01% (record low) | −$1.65 | 2020-2021, where the fund's expense ratio exceeds its yield |

**57% of the record paid $25/mo or more. 27% of it paid under $2.50, and in 19.1% of its months — 77 of them, all
in the zero-rate era — the switch was worth nothing or slightly negative.** Today sits at the 55th percentile — mid-cycle, a little above
the median — which is the single luckiest possible place for a first measurement to land, and it is where every
figure in the previous six rounds came from.

So the honest description of the recommendation is not "worth $46 a month." It is **a standing option on short
rates being positive**, with the premium paid continuously and the payoff arriving only when the curve is above
roughly the fund's expense ratio. At the median month it is worth $34. At the lower quartile it is worth one
dollar, and the effort of running a twelve-rung ladder is not worth one dollar — the switch reduces to "hold a
T-bill ETF and stop thinking about it", which costs nothing but does nothing either.

## What this changes in practice, and what it does not

**It does not change the decision, and it should not.** The switch has no meaningful downside: the worst month in
33 years cost $1.65 on $20,000 — fourteen thousandths of a percent of the balance — because an ETF's expense
ratio can exceed its yield by a hair and that is the floor. There is no path where moving off a 0.02% sweep into bills loses meaningful money, and the
option being cheap to hold is the point of holding options. The action stays first in the ledger.

**It does change what to build.** A 12-rung Treasury ladder is worth constructing when the curve is at the upper
quartile and is pure friction at the lower one, so the ladder should not be the default form of the recommendation
— it should be the *high-rate* form, and a T-bill ETF the default. Round 24's note offered both and priced
neither against the curve's own history, which is the gap this round closes. The printed section now says so where
the number is printed rather than in a note that will be read separately and forgotten.

**And it changes the forward expectation of every rate-dependent claim in this repository.** The loan in round 30
and the cash switch in round 24 are the same exposure wearing different clothes: both are long the bill curve and
short the desk. If short rates fall back toward their lower quartile — as they did for a decade, and as the curve
in the archive has done from every one of its peaks — the cash switch's $46 becomes a dollar, *and* the loan's
financing cost improves while its equity leg carries a drawdown it cannot diversify. Neither is a plan that works
in every regime, and the project should stop describing either as if it were.

## Checks

3 tests appended (15 in the file, 0.7 s, offline): the percentile must be reported and must sit between 0.30 and
0.80 with a message saying the note gets re-read if that stops being true; the lower quartile must still be under
1% — that near-zero quartile *is* the caveat, and if a re-seal ever removes it the caveat is gone, not the
history; the switch must have failed to clear $2.50/mo in at least 20% of months while clearing $25 in more than
40%; and the median month must be worth **strictly less** than today's quote, which is the test that keeps this
file's headline from quietly becoming a best-case number. One assertion started as `assertEqual(months, 404)` and
was changed to a floor of 300 before it shipped: pinning the record's length means the next archive seal fails a
test that was checking arithmetic, which is the same mistake r26 documented about counts.

Full suite: **1471 passed, 233 subtests**. `journalctl verify`: chain intact (1 entry), comparator
`100% SPY, fee 0.000945`, $0.00 paid in.

> **Restated in round 47.** The spot bill yield quoted in this note (**2.88%**, and the **+$46.12/mo** built from
> it, and the "55th percentile of the record") was computed by annualising the last three monthly buckets of the
> cash curve — and the last of those was a **four-day stub**: the archive seals after a session, and the September
> 2026 bucket held trading days 1-4 only. Compounding a four-day accrual as a month pulled the spot down **103bp**.
> On complete months the archive's own last full month is **3.81%**, the three-month spot is **3.91%**, the switch
> is worth **+$63.34/mo** at $20,000, and today sits at the **65th** percentile — *above* the record median, not
> below it. Every distribution figure in these notes (mean $39.85, median $33.72, quartiles) moved by pennies;
> only the spot and the percentile it was compared against were wrong. See
> [`2026-09-06-the-seal-is-not-a-month.md`](2026-09-06-the-seal-is-not-a-month.md).
