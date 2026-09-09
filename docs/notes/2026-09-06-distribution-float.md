# The distributions file, read at last: the reinvestment assumption is worth nothing, and that is worth knowing

Measured 2026-09-06, round 27. No new tool, deliberately; the measurement is below and it belongs in
[`cash_yield_gap.py`](../../tools/cash_yield_gap.py)'s territory rather than in a new file.
Round 26 left the search in an unusual position: trend, volatility targeting, leverage, attention/news,
calendar, sleeve choice and cross-sectional rotation had all been measured and had all failed their own bars,
and the only verified money in the entire project was in **costs and rates**. So this round went looking in the
one place with data nobody had opened — 73,009 rows of `distributions_daily.csv` — against a hypothesis that
sounded promising and turned out to be wrong.

## The hypothesis, stated before it was tested

Every backtest in this repository runs on **total-return** prices (`tr_close = adjclose`), which silently assumes
each distribution is reinvested on its ex-date at the close. A real account with dividend reinvestment switched
off receives cash and it sits wherever it lands. Since round 24 established that idle cash at a brokerage earns
0.02% rather than the bill curve, the natural next question was: **how much does the reinvestment assumption
cost, now that the cash leg it lands on is nearly worthless?** For a monthly-income goal this looked like the
most relevant unexamined number in the archive.

It is worth about nothing. The reasoning for why it could have been large was wrong in a specific,
instructive way.

## What the file says

| sleeve | events/yr | distribution yield | median gap between ex-dates | largest single cheque, as a share of a year |
|---|---|---|---|---|
| SPY | 4.1 | 1.65% | 91 days | 0.27% |
| VOO / VTI / ITOT | 4.0–4.1 | 1.64–1.66% | 91 days | 0.27% |
| QQQ | 4.0 | 0.66% | 91 days | 0.98% |
| IWM | 4.1 | 1.29% | 91 days | 0.98% |
| EFA | 1.9 | 2.81% | 182 days | 1.01% |
| EEM | 2.1 | 1.97% | 182 days | 1.01% |
| TLT | **12.0** | 3.26% | 30 days | 0.17% |
| IEF | **12.1** | 2.84% | 30 days | 0.13% |
| GLD | none | — | — | — |
| DBC | 0.5 | 1.27% | 364 days | **10.02%** |

Three things worth knowing, none of which is the headline:

- **The bond funds pay monthly and the equity funds quarterly.** A monthly-income plan built on TLT/IEF receives
  a cheque every month; one built on SPY receives one every quarter. The archive contains this asymmetry and no
  round had used it. It is not an edge — it is a *cash-flow shape*, and it decides whether a "monthly income"
  sleeve actually delivers cash in the month you need it or makes you sell to manufacture it.
- **`GLD` pays nothing at all**, and `DBC` pays twice a decade with one cheque that is 10% of a year's
  distributions in a single event. Any income framing that treats these as interchangeable with SPY is wrong in
  a way the return series cannot show.
- **`VOO` and `SPY` have identical distribution yields to two decimal places** (1.64% vs 1.65%). Round 18's
  share-class conclusion was about the expense ratio, and this confirms the fee is the whole difference — the
  distributions are not part of it.

## Why the reinvestment assumption costs nothing

The float being delayed is not the account, it is one quarter's dividend: **0.27% of the account for SPY**, paid
four times a year. Delaying reinvestment of that by a full week at a 0.02% sweep costs

> (yield ÷ events per year) × sweep rate × (days ÷ 365) = 0.41% × 0.0002 × 0.019 ≈ **0.00000004 of the account**

i.e. a fraction of a basis point a year, at any plausible holding period, on every sleeve. Even the pathological
case — never reinvesting anything, letting every distribution sit as cash indefinitely — costs
**0.047%/yr on SPY, 0.093%/yr on TLT, 0.080%/yr on EFA**, because what is forgone is the spread between the bill
rate and the sweep applied to a *yield*, not the yield itself. At $20,000 the worst of those is $1.55 a month.

The mistake in the hypothesis was the one round 24's own finding invites and then forbids: **a rate spread is
only worth money on a balance that exists.** The idle cash in round 24 was the *account* (or the contribution
stream), which is $20,000; the idle cash in a distribution is one cheque, which is 0.27% of it. The same 2.86%
spread applied to 100% of the account is $46 a month, and applied to a quarterly dividend float it is a rounding
error. That distinction — the balance the spread applies to, not the size of the spread — is the transferable
lesson, and it is the same one round 23 taught about account size and statistical power.

## What this closes

The distribution file is not a source of return, and the total-return assumption every backtest here makes is
**not** hiding a cost, which means the 26 rounds of results do not need re-pricing on this axis. It is a source
of information about cash-flow *shape*, and the only actionable item it produces is small and cheap: if a
monthly income stream is the goal, the monthly-paying sleeves remove the need to sell in order to be paid, and
`GLD` should never appear in an income framing at all.

## Checks

4 tests appended to [`test_cash_yield_gap.py`](../../tests/test_cash_yield_gap.py) (now 12, 0.5 s, offline),
because a negative result that lives only in prose comes back as an idea: the delay cost must be under a
millionth of the account a year *and* under a cent a month on $20,000; the never-reinvest worst case must be
under $2.00/mo on $20,000; the TLT-to-SPY events-per-year ratio must stay above 2.5 (the cash-flow finding,
asserted rather than described); and VOO and SPY must distribute within 5bp of each other, which is the
condition under which round 18's share-class result stays a fee story and nothing else. Full suite: **1455
passed, 233 subtests** (1451 before these four), collected and run at the same number. `journalctl verify`:
chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.

After this round the archive has no unexamined file and the search has no untried family that the data can
support. That is the state to be in: what remains is the cost list from rounds 18 and 24, and a decision about
whether to spend the next thing on a candidate rather than on another audit.
