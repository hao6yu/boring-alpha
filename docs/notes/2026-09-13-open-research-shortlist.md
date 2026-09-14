# Open research worth borrowing

Reviewed September 13, 2026. Scope: articles, academic research, public source
code and data documentation. This review did not run outside code, install a
framework, collect a new strategy dataset, purchase data or test returns.

## Decision

Use **Open Source Asset Pricing as the research reference**, paired with
published work on implementation costs. It offers traceable hypotheses and
reference implementations that can reduce our dependence on inventing rules.
It does not establish a profitable strategy for this account.

Of the distinct information sources reviewed, **publicly disclosed insider
purchases merit a bounded literature-and-data audit**. Earnings surprise is a
useful published reference but overlaps our completed earnings experiment.
Futures infrastructure remains useful if the breadth and capital questions are
reopened. No candidate from this review is ready for a funded pilot.

The priority order reflects research usefulness, feasibility and novelty for
this project. It is not a ranking of expected investment returns.

## What the previous failures mean

Our [earnings-language expansion](../../research/equity-event-expansion-2026-09-13/RESULTS.md)
returned 5.42% annualized under base costs and 2.05% under stressed costs;
numeric-only returned 6.77% and 0.20%. The text contribution was unsupported.
Those results remain adverse evidence for that model and its account rules.

The [BA-012 larger-account diagnostic](2026-09-10-ba012-traded-profitability.md)
also lost money at both $25,000 and $100,000. Its full intended evaluation
remained incomplete, while the $5,000 version could not trade under its rules.
Borrowing a futures repository does not erase those findings.

The [earlier reset](2026-09-10-research-reset.md) records the failed intraday
implementations, conditional crypto-carry economics and reasons for parking
generic pairs/options searches. A public repository using the same signal is
an implementation reference, not independent new evidence.

## Useful projects and exactly what to borrow

### 1. Open Source Asset Pricing — best research starting point

Chen and Zimmermann's project connects academic papers, signal definitions,
source code and downloadable research outputs. Its October 2025 data release
provides monthly portfolio returns for 212 predictors; most current series end
in December 2024. Stock-level characteristics are also available. These are
historical research products, not a current trading feed.
[Data and coverage](https://www.openassetpricing.com/data/).

Borrow the documented signal formulas, original-paper references and separation
between signal generation and portfolio construction. Full signal regeneration
can require WRDS and licensed underlying datasets. Downloadable outputs can
support an initial evidence audit without rebuilding that pipeline.
[Repository](https://github.com/OpenSourceAP/CrossSection).

I inspected `EarningsSurprise.py` and `Mom12m.py`. The former removes a trailing
earnings-growth drift and standardizes the residual; the latter compounds
lagged monthly returns and excludes the current month. These are inspectable
examples, not recommendations to run both. Their upstream inputs, missing-data
conventions and availability dates still need validation.
[Earnings source](https://github.com/OpenSourceAP/CrossSection/blob/master/Signals/pyCode/Predictors/EarningsSurprise.py),
[momentum source](https://github.com/OpenSourceAP/CrossSection/blob/master/Signals/pyCode/Predictors/Mom12m.py).

The authors' documentation explicitly notes that implementation details change
anomaly performance and describes accounting-data lags. Their site also records
a 2024 look-ahead correction to `AnnouncementReturn`. Versioning and examination
of data timing remain necessary even in reputable replication work.
[FAQ](https://www.openassetpricing.com/faq/).

**Project decision:** use as a reference library. Avoid ranking all 212 signals
by historical return and selecting the winners; that would create a large,
unrecorded model search. Broad long-short portfolio returns also do not establish
what a concentrated, long-only $5,000 account would earn.

### 2. AssayingAnomalies and the trading-cost papers — borrow the economics

Novy-Marx and Velikov's 2016 study finds that a gap between entry and retention
criteria is an effective way to reduce trading costs. A position can remain
worth holding even when it would no longer justify paying to enter it.
[Published study](https://doi.org/10.1093/rfs/hhv063).

An illustrative implementation is entering only very highly ranked stocks but
retaining existing positions through a wider rank band. The exact bands must
be fixed and justified before evaluating returns. This can reduce churn; it
cannot manufacture information in an uninformative signal.

The authors' **AssayingAnomalies** toolkit provides portfolio sorts, cost
analysis and a protocol for evaluating proposed signals. Full execution needs
MATLAB and WRDS access to CRSP/Compustat, with additional subscriptions for some
spread measures. It is an academic toolkit, not a broker-connected bot.
[Code and requirements](https://github.com/velikov-mihail/AssayingAnomalies).

Read the counterevidence alongside the original anomaly papers. Chen and
Velikov's 2023 study of 204 long-short anomalies adjusts for spreads,
post-publication effects and modern trading conditions. It estimates only
about four basis points per month for the average anomaly, even before some
additional costs. This is a result for their study design, not an expected
return for us or a statement that every public strategy fails.
[Paper](https://doi.org/10.1017/S0022109022000874).

Their [replication repository](https://github.com/velikov-mihail/Chen-Velikov)
documents the cost and portfolio experiments. Its source can be inspected;
reuse licensing was not established in this review. The separate
AssayingAnomalies repository has an MIT license.

**Project decision:** borrow the cost methodology and evidence standards;
installing the whole academic stack would add dependencies before resolving
our strategy question.

### 3. QuantConnect/LEAN and standardized unexpected earnings — a concrete reference

QuantConnect publishes a long-only strategy that selects the highest 5% of
standardized earnings surprises from a liquid-stock universe and rebalances
monthly. Its article provides the formula, selection code and a historical
2009–2019 backtest. It uses changes in quarterly EPS relative to the prior year,
scaled by historical variability; analyst consensus estimates are not required
by this particular implementation.
[Strategy and code](https://www.quantconnect.com/research/15369/standardized-unexpected-earnings/).

This is a reference for post-earnings drift. It differs from our language model,
but our numeric baseline already used earnings growth: it belongs in the same
research family. The Open Source Asset Pricing version also includes a drift
adjustment, so these two implementations are not exact duplicates.

Borrow the transparent baseline and scheduling ideas. Before adapting it, audit
original versus restated EPS, fiscal-period alignment, data publication times,
warm-up history, portfolio breadth and small-order commissions. Its reported
backtest is not an independently verified live record or evidence of survival
at our cost and risk limits.

[LEAN](https://github.com/QuantConnect/Lean) supplies a reusable trading engine.
A free engine license does not imply free fundamental data or hosted services.
**Project decision:** retain as a reference; do not automatically reopen the
failed earnings experiment or migrate our existing simulator.

### 4. Public insider purchases + EdgarTools — a distinct research lead

Cohen, Malloy and Pomorski's *Decoding Inside Information* distinguishes
predictable routine insider transactions from more informative opportunistic
ones. Its historical findings motivate separating transaction types rather
than treating every ownership increase as a bullish signal. The underlying
sample is 1986–2007, which materially limits a present-day profitability claim.
[Published paper](https://doi.org/10.1111/j.1540-6261.2012.01740.x),
[sample description](https://www.nber.org/digest/apr11/decoding-inside-information).

The SEC provides quarterly, flattened ownership filings covering January 2006
through June 2026 on the page reviewed. This establishes an accessible raw-data
route, not a clean research panel. The SEC cautions that the extracts omit some
metadata and do not replace the original filings.
[Official dataset](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets).

[EdgarTools](https://github.com/dgunning/edgartools) can retrieve and parse Form 4.
Its [guide](https://github.com/dgunning/edgartools/blob/main/docs/guides/track-form4.md)
shows transaction codes, prices, share amounts and filing dates. Borrow that
parsing layer. A net increase in shares is not necessarily an open-market
purchase: grants and exercises need separate treatment, and code P can also
include private purchases. Amendments, duplicate owners and footnotes matter.

**Project decision:** first distinct lead for an evidence audit, not a selected
trading model. Returns earned by an insider before disclosure cannot be assigned
to a public follower. Any eventual rule must use information actually public
before entry, past-only insider history and realistic prices. Fresh evidence
after disclosure, in sufficiently liquid stocks and after costs, is still
unverified. Price histories, delistings and issuer identity joins also remain
necessary despite free filings. A long-only adaptation would need its own test.

### 5. pysystemtrade and Qlib — useful tools with different roles

**pysystemtrade** implements Rob Carver's systematic futures framework with an
IBKR connection. The current `develop` README uses `ib_async` and records the
move to the `pst-group` organization. Borrow portfolio sizing, trading buffers,
roll handling and operational architecture if futures research resumes.
It overlaps BA-012; it does not solve attainable diversification or prove an
edge for our capital.
[Current project](https://github.com/pst-group/pysystemtrade).

**Microsoft Qlib** provides ML research workflows and model benchmarks. Its main
benchmark page uses Chinese A-share/CSI300 data; documentation also describes
US-market support. Those published benchmark results are not US retail return
estimates. Borrow experiment tracking and fixed baseline comparisons when there
is a defined forecasting question.
[Benchmarks](https://github.com/microsoft/qlib/blob/main/examples/benchmarks/README.md),
[data documentation](https://github.com/microsoft/qlib/blob/main/docs/component/data.rst).

**Project decision:** retain as engineering references. Framework migration and
an unrestricted contest between neural networks would not resolve our current
evidence gap.

## Repository maintenance and reuse snapshot

GitHub public metadata inspected on the review date; “last push” can include
branches other than the default. Activity is not evidence of profitability.

| Repository | Default branch | Last push, UTC date | Declared license |
|---|---|---|---|
| OpenSourceAP/CrossSection | master | 2025-10-22 | GPL-2.0 |
| velikov-mihail/AssayingAnomalies | main | 2023-01-26 | MIT |
| QuantConnect/Lean | master | 2026-09-12 | Apache-2.0 |
| dgunning/edgartools | main | 2026-09-11 | MIT |
| pst-group/pysystemtrade | develop | 2026-07-18 | GPL-3.0 |
| microsoft/qlib | main | 2026-09-02 | MIT |

All six were unarchived. Code licenses do not grant rights to third-party market
data. Review scope was documentation, metadata and selected signal source files;
this was not a full code audit or reproduction of any advertised results.

## Bounded next decision

**Follow-up completed:** the user authorized the bounded audit below. Its
[result and proposed experiment](../../research/insider-purchase-audit-2026-09-13/RESULTS.md)
record mixed modern evidence, 13 filing controls, one timestamp discrepancy and
the remaining insider-history requirement. No strategy returns were calculated.
The recommendation below is preserved as the scope agreed before that audit.

Recommend one evidence audit of **public, non-routine insider purchases**, using
the cost discipline above. Cap the follow-up at two hours and $0 of new paid
data; no framework installation or return-model search.

The deliverable should specify one published rule, identify which results begin
after public disclosure, check recent independent evidence or counterevidence,
and map every required field to an available source. Inspect a small fixed
filing sample only for field/timestamp feasibility. No return-based threshold
selection at this stage.

Stop with a documented no-go if the support depends on pre-disclosure prices,
inaccessible inputs or illiquid-stock execution we cannot represent. A passing
audit would justify proposing a fixed experiment, not funding it. The existing
unseen equity strategy window remains reserved.

This prioritization is a research judgment based on a different information
source and accessible filings. No defensible probability of profitability, net
return forecast or assurance of staying within a 20% decline has been established.
