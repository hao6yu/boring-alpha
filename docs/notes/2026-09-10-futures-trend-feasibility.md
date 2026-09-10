# Five-market futures trend: practical feasibility

September 10, 2026. Authorized scope: the futures candidate selected after the
[strategy review](2026-09-10-strategy-research.md). Research began 05:55 UTC.
No strategy code, return backtest, paid data, subscription, account change or
order was undertaken. Simple arithmetic and public-source archiving support
this worksheet. Crypto carry and options were not reopened.

## Decision

**Continue with one risk-constrained research candidate. Do not fund a fixed
one-contract-each basket.** The five instruments exist, have observed trading
activity and have identifiable retail fees. A $5,000 account can meet current
margin requirements, but holding all five minimum units already exceeds the
approximately $1,000 tolerance in the stipulated larger joint shock.

A five-market *universe* can contain flat positions. A four-position example
below fits the same mechanical stress constraint, so the evidence does not
justify rejecting all $5,000 implementations. It also does not establish that
this reduced portfolio has enough diversification or expected return. Risk
sizing and executable spreads remain the decisive missing evidence.

This is a conditional research decision, not a profitability or live-readiness
pass. The next deliverable should be one frozen sizing/evaluation protocol,
with positions allowed to round to zero. No parameter sweep or bot build is
justified by this worksheet.

## 1. Exact instruments and dollar exposure

| Root | Exposure / price convention | Dollar P&L sensitivity, one long | Outright tick |
|---|---|---|---:|
| NES | S&P 500 index points | $0.50 per index point | $0.25 |
| MTN | Micro Ultra 10-Year Treasury **price**, $10,000 face | $100 per full bond-price point | $1.5625 |
| M6E | USD per EUR; €12,500 contract | $125 per 0.0100 USD/EUR | $1.25 |
| 1OZ | USD per troy ounce; one ounce | $1 per $1/oz | $0.25 |
| MZC | Cents per bushel; 500 bushels | $5 per one quoted cent/bu | $2.50 |

Short P&L reverses the sign. MTN is not the 10Y constant-DV01 yield future:
`108′245` means `108 + 24.5/32 = 108.765625`, not 108.245. MZC's tick is
**0.5 cent**, or $0.005/bushel. The CME HTML agriculture FAQ's $0.050 entry
conflicts with the fact card and filed rules; those establish the smaller tick.
[NES](https://www.cmegroup.com/articles/faqs/faq-e-nano-equity-index-futures.html),
[MTN rules](https://www.cmegroup.com/rulebook/CBOT/III/54.pdf?redirect=/rulebook/CBOT/V/54.pdf),
[M6E rules](https://www.cmegroup.com/content/dam/cmegroup/rulebook/CME/III/250/292/292.pdf),
[gold](https://www.cmegroup.com/articles/faqs/faq-1-oz-gold-futures.html),
[corn fact card](https://www.cmegroup.com/markets/agriculture/files/micro-ag-futures-fact-card.pdf),
[corn filed rules, p. 6](https://www.cmegroup.com/content/dam/cmegroup/market-regulation/rule-filings/2025/1/25-024.pdf)

Expiry matters to the actual instrument choice:

- NES cash settles to a third-Friday opening index calculation; September
  expires September 18. December's liquidity must be checked for the roll.
- MTN cash settles two business days before its named month. September MTN
  already expired in August; December is the relevant current candidate.
- M6E is **physically delivered**. September rules imply September 14 last
  trading and September 16 delivery, subject to holiday and broker deadlines.
  Use December for an ongoing position and close before delivery restrictions.
- 1OZ cash settles and stops trading in the month preceding its named month.
  October stops September 28; December was much more active in the observation.
  Chapter 131 has inconsistent floating-price versus termination wording; verify
  the official calendar before any expiry exposure. The design should roll out.
- MZC cash settles before its named month; September already expired in August.
  December is the current candidate.

The cited rules and FAQs establish these mechanics. The gold inconsistency is
retained rather than silently resolved by assumption.
[Gold Chapter 131](https://www.cmegroup.com/rulebook/COMEX/1a/131.pdf)

## 2. Observed trading activity, not assumed execution

CME tables were updated September 10 around 00:56–00:57 CT. They explicitly
delay market data by at least ten minutes. These are **partial-session last
trades and volumes**, not synchronized executable quotes.

| Maturity | Last trade | Displayed row time, CT | Session volume |
|---|---:|---|---:|
| NESU6 | 7,664.50 | Sep 10 00:46:48 | 279 |
| NESZ6 | Missing | Sep 9 21:16:48 | 0 |
| MTNZ6 | 108′245 | Sep 10 00:31:35 | 21 |
| M6EZ6 | 1.1679 | Sep 10 00:45:06 | 1,405 |
| 1OZZ6 | 4,471.75 | Sep 10 00:47:58 | 11,860 |
| MZCZ6 | 528.5 cents/bu | Sep 10 00:46:55 | 34 |

NESZ6's prior settlement, 7,709.50, is not a current last trade.
Sources: CME [NES](https://www.cmegroup.com/markets/equities/sp/e-nano-sandp-500.quotes.html),
[MTN](https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-ultra-10-year-us-treasury-note.quotes.html),
[M6E](https://www.cmegroup.com/markets/fx/g10/e-micro-euro.quotes.html),
[1OZ](https://www.cmegroup.com/markets/metals/precious/1-ounce-gold.quotes.html),
[MZC](https://www.cmegroup.com/markets/agriculture/grains/micro-corn/quotes).

September 9 **PRELIMINARY, full-session root totals** give additional context:

| Root | Volume | Open interest | CME bulletin |
|---|---:|---:|---|
| NES | 2,390 | 669 | [Equity, p. 2](https://www.cmegroup.com/daily_bulletin/current/Section01C_Summary_Volume_And_Open_Interest_Equity_Index_Futures_And_Options.pdf) |
| MTN | 236 | 858 | [Rates, p. 1](https://www.cmegroup.com/daily_bulletin/current/Section02A_Summary_Volume_And_Open_Interest_Int_Rates_Futures_And_Options.pdf) |
| M6E | 20,448 | 19,437 | [FX, p. 1](https://www.cmegroup.com/daily_bulletin/current/Section01B_Summary_Volume_And_Open_Interest_FX_Futures_And_Options.pdf) |
| 1OZ | 61,472 | 80,298 | [Metals, p. 1](https://www.cmegroup.com/daily_bulletin/current/Section02B_Summary_Volume_And_Open_Interest_Metals_Futures_And_Options.pdf) |
| MZC | 740 | 1,474 | [Agriculture, p. 1](https://www.cmegroup.com/daily_bulletin/current/Section01A_Summary_Volume_And_Open_Interest_AlT_Investment_Futures_And_Options.pdf) |

These totals combine maturities and do not establish December roll liquidity.
No bid, ask or depth columns were exposed. Low overnight volume does not prove
that resting quotes are absent; positive daily volume does not prove tight
spreads. MTN, MZC and the NES roll require particular scrutiny.

## 3. Published fees and transparent cost scenarios

Assume U.S. IBKR **fixed futures pricing**, non-member first-volume tier and
IBKR execution/clearing. The user's actual plan and permissions remain
unverified. No give-up surcharge is included. The fixed-plan description says
there is no overnight carrying fee; tiered pricing requires a separate check.
[Broker commissions](https://www.interactivebrokers.com/en/pricing/commissions-futures.php),
[fixed-plan description](https://www.interactivebrokers.com/en/accounts/fees/futnorthambundcoms.php?path=3)

| Root | Broker / side | Exchange / side | NFA / side | Total / side | Fees / round trip |
|---|---:|---:|---:|---:|---:|
| NES | $0.25 | $0.35 | $0.01 | $0.61 | $1.22 |
| MTN | $0.25 | $0.30 | $0.01 | $0.56 | $1.12 |
| M6E | $0.15 | $0.24 | $0.01 | $0.40 | $0.80 |
| 1OZ | $0.15 | $0.50 | $0.01 | $0.66 | $1.32 |
| MZC | $0.25 | $0.50 | $0.01 | $0.76 | $1.52 |

Exchange/regulatory sources: [CME](https://www.interactivebrokers.com/en/accounts/fees/CME.php),
[CBOT](https://www.interactivebrokers.com/en/accounts/fees/CBOT.php),
[COMEX](https://portal.interactivebrokers.com/en/accounts/fees/COMEX.php).

For sensitivity, charge **one tick per execution** in the base case and two
ticks per execution in stress, in addition to fees. These are combined
execution-friction assumptions relative to a reference price, **not measured
spreads or execution upper bounds**; do not add a second identical spread cost.
One round trip contains two executions. Rolls, reversals and resizing all
consume executions; a monthly decision does not necessarily produce a trade.

| Root | Fees + one tick each way | Fees + two ticks each way |
|---|---:|---:|
| NES | $1.720 | $2.220 |
| MTN | $4.245 | $7.370 |
| M6E | $3.300 | $5.800 |
| 1OZ | $1.820 | $2.320 |
| MZC | $6.520 | $11.520 |

Nonprofessional CME, CBOT and COMEX L1 subscriptions list $1.55 each per month:
**$55.80 annually** together. This is a future operating-cost scenario, not a
purchase. No hosting charge or account cash interest is assumed.
[Data fees](https://www.interactivebrokers.com/en/pricing/market-data-pricing.php)

| Annual one-unit turnover scenario | Base trading + data | Stress trading + data |
|---|---:|---:|
| Calendar rolls only: 4 NES, 4 MTN, 4 M6E, 6 gold, 5 corn | $136.38 | $188.88 |
| 12 round-trip equivalents per market, all activity included | $267.06 | $406.56 |
| 24 round-trip equivalents per market, all activity included | $478.32 | $757.32 |

The first row is a steady-state front-contract illustration, excluding initial
deployment/final liquidation and signal changes. It is not a mandatory roll
schedule or universal cost floor. Other rows include rolls rather than adding
them twice. Actual sizing and turnover must replace all three illustrations.

At $5,000, the 12-round-trip base case consumes **5.34%** of starting capital.
With zero earned interest, beating a 6% cash scenario would require **$567.06
gross trading profit, or 11.34%**, before tax. The stress-cost requirement is
$706.56, or 14.13%. These are hurdles, not return forecasts. IBKR does not pay
ordinary USD cash interest on the first $10,000 or on commodity-segment cash.
[Interest rules](https://www.interactivebrokers.com/en/accounts/fees/pricing-interest-rates.php)

## 4. Margin, stress and integer sizing

The public September 10 IBKR snapshot gives these overnight requirements:

| Root | Long initial | Short initial | Maintenance, either direction, rounded |
|---|---:|---:|---:|
| NES | $324.12 | $298.78 | $259.81 |
| MTN | $710.68 | $751.28 | $616.95 |
| M6E | $329.44 | $334.44 | $286.47 |
| 1OZ | $459.69 | $464.19 | $399.73 |
| MZC | $206.92 | $234.42 | $179.93 |

Using the larger initial requirement for each direction gives **$2,108.45**;
maintenance totals **$1,742.89**, without cross-product offsets. Exact source
precision is retained in the arithmetic. Current account/contract requirements
may differ. Initial margin governs opening/replacement; maintenance governs
continued holding. Neither is a loss ceiling.
[IBKR schedule](https://www.interactivebrokers.com/en/trading/margin-futures-fops.php?ex=us&hm=us&pm=0&rgt=0&rsk=1&rst=101004100808)

The observed last trades imply roughly **$36,422 gross contract value** for
one each, about **7.28 times** a $5,000 account. These nonsynchronous reference
values describe exposure, not an executable portfolio or a comparable risk
measure across asset classes.

Assume the following simultaneous adverse movements, reversing direction for
shorts. No probability, historical percentile or covariance is attributed to
them; they are explicit sensitivity scenarios.

| Root | Stress A adverse move | One-unit loss A | Loss B: double the move |
|---|---|---:|---:|
| NES | 200 index points | $100 | $200 |
| MTN | 1 full bond-price point | $100 | $200 |
| M6E | 0.0100 USD/EUR | $125 | $250 |
| 1OZ | $100/oz | $100 | $200 |
| MZC | 20 cents/bu | $100 | $200 |
| **Total** | | **$525** | **$1,050** |

For one each, combine A with 1.5× margins and B with 2× margins:

| $5,000 account, before execution costs | A + 1.5× margins | B + 2× margins |
|---|---:|---:|
| Equity after price loss | $4,475.00 | $3,950.00 |
| Headroom above stressed maintenance | $1,860.66 | $464.22 |
| Headroom above stressed initial | $1,312.32 | **−$266.91** |
| Remaining $1,000 loss tolerance | $475.00 | **−$50.00** |

B breaches the investor's tolerance even though maintenance headroom remains
positive. Its initial deficit constrains opening or rolling positions; it is
not by itself a liquidation finding. A stop cannot guarantee an exit before
a $1,000 drawdown when markets gap or liquidity is unavailable.

**Counterexample to rejecting the whole universe:** hold one NES, MTN, gold
and corn, with M6E flat. B then loses $800. Including two-tick-each-way
round-trip friction on those four costs $23.43, leaving $4,176.57 equity.
Against doubled margins, initial headroom is $628.55 and maintenance headroom
$1,263.73. This fits the stipulated $1,000 stress budget from a fresh account,
with $176.57 left. Prior drawdown would consume that buffer.

This is a mechanical example, **not a recommended allocation or volatility-balanced
portfolio**. It retains four markets across equities, rates and commodities,
with fewer independent exposures than the academic research. Ordinary sizing
still needs dollar-volatility and covariance estimates. Risk constraints must
be allowed to set positions to zero rather than rounding upward to force trades.

## 5. What more capital would and would not solve

Keep the same five units; do not automatically scale positions:

| Capital | Initial margin / capital | Stress B price loss / capital | Maintenance headroom after B and 2× margins |
|---|---:|---:|---:|
| $5,000 | 42.17% | 21.00% | $464.22 |
| $25,000 | 8.43% | 4.20% | $20,464.22 |
| $100,000 | 2.11% | 1.05% | $95,464.22 |

More capital improves collateral capacity. With an unchanged $1,000 dollar
tolerance, it does not fix minimum dollar risk. Increasing positions in
proportion to capital preserves the percentage stress. Keeping positions
unchanged also dilutes their percentage return while increasing the cash
benchmark in dollars. These comparisons do not justify a larger deposit.

## 6. The one candidate that advances, and remaining evidence

Retain the original monthly, 12-month long/short trend hypothesis in these five
markets, with cash allowed. Add no signal filters. The next protocol must fix:

1. Dollar-volatility/covariance estimation and risk targets before inspecting
   candidate returns; quantify whole-contract rounding and concentration.
2. A drawdown-aware constraint: accumulated drawdown plus stipulated additional
   stress loss and exit costs must fit the pilot tolerance. Also require cash
   above stressed maintenance and enough initial margin for the proposed roll.
3. Maturity-specific spread, available size and roll evidence, particularly
   MTN/MZC/NESZ6. The current public last-trade tables cannot supply these.
4. Costs and cash return on all committed capital, with an after-tax comparison
   before a funded proposal. Preserve seen history and unopened holdout files.

Public liquidity evidence is sufficient to avoid rejecting the instruments as
inactive. It is insufficient to claim that one- or two-tick friction is
conservative. Likewise, the illustrative integer basket is sufficient to show
mechanical possibility, not acceptable expected drawdown or positive expectancy.
These two distinctions govern the conditional research decision.

The scope remains one candidate. No funded pilot, bot build or return backtest
is queued by this result. Exact quote entitlement and normal risk estimates are
unresolved; they should be resolved directly, without another vendor search.

## Audit materials

[Arithmetic worksheet](../../research/trend-feasibility/2026-09-10/worksheet.json)
and [fee-source manifest](../../research/trend-feasibility/2026-09-10/fee-source-manifest.json)
preserve assumptions and downloaded broker pages with hashes. The
[CME archive record](../../research/trend-feasibility/2026-09-10/cme-bulletins-metadata.json)
records incomplete downloads. The locally saved agricultural detail PDF does
**not** contain the cited MZC summary row. The five summary bulletins and browser
quote tables remain tool observations at the dated URLs; `/current/` URLs are
mutable and should not be treated as immutable source archives.
