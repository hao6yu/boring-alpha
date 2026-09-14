# One data source and one bounded stock-selection experiment

**Status update: paid purchase parked; the existing-credit/free sample is now
complete.** The user authorized checking Databento plus SEC. [The results](../ml-free-data-feasibility-2026-09-13/RESULTS.md)
support continuing that route with bounded preparation, although the exact
financial features and corporate actions remain unfinished. [The comparison](FREE_SOURCES.md)
explains the shorter history. No subscription purchase is approved; the
chronology below remains the earlier paid-option proposal and has not been run.

**Previously proposed paid option: Sharadar Personal Use, Bundle, Full History, monthly billing
at $69 before any applicable tax.** Start with one paid month and cancel renewal
at period end. Do not purchase the annual plan for this first attempt. The
public sample API works from this machine. Full paid coverage has not been
tested. This is the concrete proposal requested by the user; no subscription
or model training has started.

## Source choice and full cost

| Item | Proposed first attempt | Continuing service, if later justified |
|---|---:|---:|
| Sharadar full-history bundle | $69 for one month | $69/month, or $499/year |
| New GPU/cloud services | $0; use existing local CPU | Not required by this design |
| New model API calls | $0; numerical models run locally | Not required by this design |
| Additional historical-data vendors | $0 | None proposed |
| Sales tax | Checkout-dependent; not yet known | Checkout-dependent |

The current Codex subscription, local electricity, disk space and the user's
time are existing resources, not a claim that research has no economic cost.
The first external cash commitment is **$69 plus applicable tax**, with no
renewal proposed. An eight-active-hour research cap after data access is an
effort limit, not a promise of completion or a token-price quote.

The $29 headline bundle includes only five years; ten years costs $49/month.
Full history is needed for the chronological design below. Buying full-history
fundamentals and prices separately would cost $78/month. Twelve monthly bundle
payments total $828; the annual option costs $499 upfront. All are posted
personal-use prices, not a confirmed checkout invoice.
[Current pricing](https://sharadar.com/subscribe).

At $10,000, ongoing data alone costs 8.28% of initial capital annually on monthly
billing, or 4.99% on the annual plan. This is a serious hurdle. The first $69 is
a research expense, not proof that a $10,000 live strategy can carry the service.
Show trading returns, the first-month research cost, and continuing subscription
economics separately; do not conceal the annual drag or assume a larger deposit.

The personal license covers private research and trading one's own account.
It does not cover managing other people's money or a commercial data product.
Cancellation ends access at the term boundary. The terms require deleting
source data and reconstructible copies within 30 days of termination; derived
models/results that cannot reproduce the data may remain. A one-month purchase
therefore does not buy a permanent raw-data archive. Keep licensed source data
and reversible derived panels out of version control and public reports.
[Personal-use FAQ](https://sharadar.com/docs/faqs),
[Terms, particularly sections 6 and 10](https://sharadar.com/terms),
[Cancel-at-period-end support](https://sharadar.com/blog/posts/upgrade-pause-resume).

### Alternatives screened

| Source | Verified public price | Reason not selected for this combined task |
|---|---|---|
| Norgate US Platinum | $346.50/6 months or $630/year | Includes removed stocks and index history, but its fundamental fields are current-only; historical fundamentals would need another source. |
| Tiingo | $30/month or $300/year individual plan | Fundamental API is a separate add-on whose complete price was not established; avoid assuming the base plan includes it. |
| Open Source Asset Pricing | Public historical research outputs | Useful reference; current production inputs, underlying licenses and complete account histories are not supplied by those outputs alone. |

[Norgate prices](https://norgatedata.com/stockmarketpackages.php),
[Norgate fundamental history limitation](https://norgatedata.com/data-content-tables.php#fundamentals),
[Tiingo pricing and add-on footnote](https://www.tiingo.com/about/pricing),
[Open Source Asset Pricing data](https://www.openassetpricing.com/data/).

## What the chosen source supplies

- `fundamentals`: use the ART as-reported trailing-year dimension, indexed by
  SEC filing date. Do not use the MR restated dimensions for historical inputs.
  Financial history is advertised from 1998. Our two-session availability lag
  below is a research convention, not an archived vendor-receipt timestamp.
  [Definitions](https://sharadar.com/docs/fundamentals).
- `stocks`: raw close for fills and valuations, split-adjusted OHLCV, and close
  adjusted for splits, dividends and spinoffs for return features. Price history
  is advertised from December 1997. Whole-share account cashflows must be
  reconciled separately from adjusted returns.
  [Price fields](https://sharadar.com/docs/stocks).
- `daily`: point-in-time price-based metrics. **Market cap is in USD millions**;
  multiply by 1,000,000 before combining with fundamental dollar fields.
  [Units](https://sharadar.com/docs/daily).
- `tickers`, `actions`, `sp500`: stable security identifiers, corporate events,
  and historical index membership. These provide a historical-to-current path
  using the same API, subject to checking actual completeness after access.
  [Identifiers](https://sharadar.com/docs/tickers),
  [Actions](https://sharadar.com/docs/actions),
  [Membership history](https://sharadar.com/docs/sp500).

Important limits: the provider estimates about 95% acquisition-consideration
coverage and does not supply historical primary-exchange changes. Its stated
99% freedom from survivorship bias is a vendor estimate, not our verification.
Use dated index membership for the research universe; never filter historical
stocks using the latest exchange, delisted flag, industry or market-cap bucket.
Missing cash/stock merger consideration stays unresolved; it is not zero and
does not justify a fictitious sale at the last mark. Contingent value rights
and elective consideration may need separate evidence.
[Coverage explanations](https://sharadar.com/docs/faqs).

## Public sample actually checked

Using only the provider's published Apple demo key, six data queries succeeded:
eight ART observations from 2022–2023, 23 August 2023 price rows, four 2023
dividends, one security-master row, eight 2022–2023 membership snapshots, and
four August 2023 daily market-cap rows. No personal key was read or created.

Filing dates were on or after report periods, the requested ART filter held,
and date-bounded observations stayed before 2024. Required price and financial
fields were present in this sample. These checks establish API/schema usability;
they do not verify paid history, failed companies, or every action type.
No strategy returns or model scores were calculated.

Raw samples and documentation snapshots are private local artifacts; hashes,
request scope and status are in `source-and-sample-evidence.json`. The probe is
`probe_public_sample.py`. Two local-client setup attempts failed before useful
HTTP responses; the successful probe uses system curl with TLS verification.

## Fixed first experiment proposed

**Question:** do learned interactions between valuation, profitability,
momentum and risk improve monthly stock selection beyond a linear model,
and can that improvement survive the pilot's account constraints?

### Universe and historical dates

Use the **historical S&P 500 constituent set at each prior month-end**, restricted
to the issuer's primary common security linked to fundamentals. This chooses
a liquid large-company research universe; it is not an ETF allocation or a
claim to represent the entire US stock market. Reconstruct membership from
dated snapshots/additions/deletions. Check changes against quarterly snapshots;
do not project today's members backwards or remove names because they later fail.

An issuer is entry-eligible when it has at least 252 preceding qualified trading
sessions, prior raw close of at least $5, and median 63-session dollar turnover
of at least $10 million. Compute dollar turnover as split-adjusted close times
split-adjusted volume, which preserves notional; raw volume, when needed, is
volume times split-adjusted close divided by raw close. Membership and price
coverage exceptions remain in the monthly roster.

Acquire date-filtered history from 1998 through 2023, with 1998–1999 as warm-up,
2000–2010 as initial training, and 2011–2023 as the first walk-forward historical
diagnostic (156 forecast months). Fetch no 2024–2025 price, daily-fundamental,
or strategy-feature rows for this phase. Avoid full-table bulk downloads that
would mix reserved years into the working panel. Metadata may identify current
names; it must not become a future-data eligibility filter.

Refit annually before the January decision, using only completed prior-month
labels from 2000 onward. Keep the models fixed between annual refits. The
2011–2023 period has been encountered in related research and is **exploratory**,
even though this particular stock panel/model has not been evaluated. It is not
a fresh economic holdout. The separate 2024–2025 strategy windows stay reserved;
any later release or forward paper test requires its own recorded scope.

### Inputs, label and two models

At the previous month-end, compute six raw features:

| Feature | Definition |
|---|---|
| Book value relative to price | Latest available ART `equityusd` / month-end USD market capitalization |
| Earnings relative to price | Latest available ART `netinccmnusd` / month-end USD market capitalization |
| Profitability | ART `netinc` / ART `assetsavg`, with positive denominator and matching reporting currency |
| Operating cash generation | ART `ncfo` / ART `assetsavg`, same denominator treatment |
| Momentum | Eleven months of total return ending one month before the signal month-end; skip the latest month |
| Volatility | Annualized sample standard deviation of the last 63 daily total returns |

An ART row is available only on the second NYSE session after its filing date.
Use the latest eligible row with filing age at most 365 days and report-period
age at most 550 days. These conservative conventions are fixed before outcomes.
Require valid momentum and volatility plus an eligible ART row and positive
market cap. Retain negative earnings/book values as observations. A missing
financial feature is an explicit missing value, not a fabricated zero ratio.

Transform each feature to its within-month fractional rank minus 0.5; ties use
average ranks and missing ranks become 0 with separate missing indicators.
Both models receive the identical six ranks and six indicators. The known
cross-section supplies the ranking transformation; no future months enter it.

The label is the stock's total return from the **second trading session's close
to that month's final close**, minus the equally weighted eligible-universe
return over that interval. This aligns the forecast horizon with a delayed
monthly entry. Delistings require cash/share conversion and successor valuation;
adjusted-close endpoints alone cannot dispose of a security. Unknown labels
are kept as unresolved, excluded from fitting with counts disclosed, and cannot
support an unconditional complete-universe comparison.

1. **Baseline:** Ridge regression, alpha 100, intercept enabled.
2. **Challenger:** histogram gradient-boosted regression trees, squared-error
   loss, learning rate 0.05, 150 iterations, 15 maximum leaves, minimum 100
   samples per leaf, L2 penalty 10, early stopping disabled, seed 20260914.

Each training month has equal total observation weight, normalized so the
overall average row weight is one. No hyperparameter search, feature selection,
additional model family, or outcome-driven change is included. These are
bounded starting choices, not asserted optimal settings. A fixed reference
score averages the two valuation ranks, two quality ranks, momentum rank and
negative-volatility rank; it serves as an additional transparent comparison.

Before computation, freeze this specification, the downloaded input manifest,
software versions, source adapter and scoring code. Correct mechanical defects
with an explicit version trail; never silently amend the financial hypothesis.

### Prediction and account evidence

First report monthly rank correlation with realized labels, the paired
tree-minus-linear difference, and yearly consistency. Use a stationary block
bootstrap across whole months: 2,000 replicates, expected block length 12 months,
seed 20260914. Preserve all stocks within a sampled month; stocks experiencing
the same market are not independent regime observations. Report coverage and
paired usable counts rather than hiding missing labels.

In parallel with that analysis, run identical $10,000 cash accounts for the
linear, tree and fixed-score rankings under both previously registered cost
cases. Reuse the inspected momentum account conventions: ten slots, entry
among the top 10%, retention through the top 20%, entry budget at most $800 or
8% of prior NAV, $2,000 settled-cash reserve, whole shares, no leverage,
10/50 bps per side plus the archived Pro Fixed fee scenario, and seven-day
sale-proceeds lock. Move the scheduled review/entry to the second NYSE session
to match this label and the vendor's daily delivery. Retained positions drift;
no same-day replacement financed by unsettled proceeds is assumed.

The $2,000 trailing dollar-loss halt remains permanent within each simulated
account, with next-executable-session liquidation and overshoot reported. This
can stop an account early; the continuously evaluated ranking diagnostics remain
separate from that stopped account's performance. There is no volatility overlay,
market-timing rule, risk-threshold tuning, or restart-after-loss assumption.

Daily account value includes verified dividend and merger claims; uncertain
payment dates do not create spendable cash. Extend the adapter for evidenced
stock-for-stock conversions and spinoffs before any affected holdings are
valued. Missing held marks/actions make full account performance unresolved.
Cash earns zero under the small-account scenario. This is consistent with
IBKR's published exclusion of the first $10,000 of uninvested USD cash from
interest; it is not a historical interest-rate reconstruction or a claim about
the user's broader account balances.
[IBKR cash rules](https://www.interactivebrokers.com/en/accounts/fees/pricing-interest-rates.php).

Report return, drawdown, turnover, fees, receivables and cash exposure for every
case. Show 4% and 6% constant cash reference scenarios; they are not asserted
current obtainable rates. Show a whole-share unranked account using a fixed
hash ordering as well as a same-universe aggregate return reference to identify
broad stock-market exposure. The aggregate reference is not a tradable $10,000
portfolio. No favorable reference may be selected after the run.
Use ascending SHA-256 of `MLSS-v1-unranked|permaticker` for that unranked
ordering, and ascending SHA-256 of `MLSS-v1-tie|permaticker` to break tied
predicted scores. Both strings are fixed before evaluation.

Show the trading-only account first, then separately simulate recurring
subscription debits with $499 at account inception and each annual anniversary as the economical continuing
full-history license scenario. Also disclose the $828 annual total if monthly
billing continues. Do not simply subtract costs from a final return while
pretending affordable holdings and halt dates are unchanged. Record the actual
$69 initial research expense separately from these continuing-service scenarios.
Taxes are not estimated from unknown personal circumstances; report pretax.

### Effort budget and decision

Propose **eight active agent hours after paid access** for this first round:
up to two for ingestion and source qualification, two for panel/model setup,
two for account integration/calculation, and two for verification/reporting.
Local unattended compute may continue within the paid access term, but no new
subscription period, GPU service, provider purchase or automation is implied.
If the cap is reached, preserve calculated results and state exactly what is
unresolved. Do not substitute a smaller survivor-only sample to force completion.

This round can support another research step only if the challenger improves
on the baseline across time and after stressed trading costs, with a positive
95% block-bootstrap lower bound for the mean paired rank-correlation difference.
Account economics must separately beat the 6% cash reference after the modeled
continuing data charge and stay within approximately 20% observed drawdown.
These are necessary screening conditions, not sufficient validation or proof
of future returns. Missing required coverage prevents a complete pass; calculate
and report the supported subset instead of stopping before economic analysis.

If predictive improvement exists but $10,000 economics fail because of fixed
costs, record that distinction. Do not request a larger deposit or loosen risk
to rescue the result. A positive historical screen would justify proposing a
separately specified untouched or forward paper test; it authorizes no funding.

## Current decision

The public evidence is sufficient to recommend **one $69 full-history month as
a bounded data/research trial**, subject to purchase approval and the paid
coverage check. This round has spent $0 on data, queried only small public
samples, and opened no reserved strategy prices. Approval would cover a
specific subscription and the experiment above; the public sample is not a
profitability result.
