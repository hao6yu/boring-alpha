# BA-012 Stage A calendar interpretation

September 10, 2026. This is an implementation evidence note. It does not alter
the frozen BA-012 protocol, authorize a purchase, or resolve unidentified
product business-day or broker deadlines.

## Morning observation calendar

`tools/build_ba012_calendar.py` generates
`research/ba012-stage-a/calendar-v1.json` and its SHA-256 sidecar without network
or market-data access. The JSON records its generator checksum, Python version,
the reviewed upstream calendar commit, source URLs, excluded weekday reasons,
Chicago-to-UTC request boundaries, and known equity afternoon early closes.

The 2,080 weekdays from January 11, 2016 through December 31, 2023 form the
acquisition superset. The independent mask contains 2,007 joint morning dates.
Requesting holidays as part of this superset does not make them observations.
Missing bars cannot alter this calendar. The calendar is a source-based
reconstruction of scheduled 09:59–10:06 availability; it is not an assertion
that complete historical exchange notices or unscheduled halts were audited.

The base is the regular grain holiday set in
[pandas_market_calendars 5.4.0, pinned commit](https://github.com/rsheftel/pandas_market_calendars/blob/275890784073a3a3a347e4f05f4dc986456e6a75/pandas_market_calendars/calendars/cme_globex_agriculture.py),
with its holiday definitions. Grain morning trading is scheduled 08:30–13:20
Chicago on ordinary weekdays. Other reviewed parent product calendars do not
add a morning exclusion beyond this set except the mourning closure below.
Afternoon early closes remain eligible; the JSON's early-close annotations
cover known equity rules, not a complete five-product end-of-day schedule.
The generic `exchange_calendars` CMES calendar is not the chosen calendar:
different products have different holiday sessions.

Explicit exceptions and checks:

- The pinned grain calendar omits Juneteenth. Exclude June 20, 2022 from the
  contemporaneous [Nesvick broker schedule](https://www.nesvick.com/wp-content/uploads/2022/06/Juneteenth-2022-Holiday-Trading-Schedule.pdf),
  and June 19, 2023 from the contemporaneous
  [Guotai Junan broker schedule](https://www.gtjai.com/upload/UploadFiles/2023/06/14/6d29478797914e268ad308406a278a91.pdf).
  These are broker-issued trading notices, not represented as CME-authored PDFs.
- Exclude December 5, 2018: [CME SER-8289](https://www.cmegroup.com/notices/ser/2018/12/SER-8289.pdf)
  closes rates and ends the US equity-index session at 08:30 Chicago.
- Keep December 31, 2021 and January 3, 2022. New Year's Saturday does not
  automatically close the previous Friday. The
  [AMP notice relaying the CME Globex Control Center](https://www.ampfutures.com/news/new-years-holiday-trading-schedule-2021)
  confirms normal December 31 closes and January 2 evening reopening.
  A US federal holiday calendar would incorrectly remove December 31.
- TN's [CME launch record](https://www.cmegroup.com/media-room/press-releases/2016/1/15/cme_group_announcessuccessfullaunchofultra10-yearfutures.html)
  places its first trades after 17:00 on January 10, 2016. January 11 is the
  first common morning; earlier January dates are outside common availability.

## Gold: a narrow resolution sufficient for the expiry rule

[COMEX Rule 131102.E](https://www.cmegroup.com/rulebook/COMEX/1a/131.pdf)
explicitly terminates 1-Ounce Gold trading on the third-last business day of
the month **before** the contract month. The
[CME 1-Ounce Gold FAQ](https://www.cmegroup.com/articles/faqs/faq-1-oz-gold-futures.html)
agrees. Stage A may rely on this explicit last-trading rule, once the relevant
business-day calendar is identified, and exit five joint sessions earlier.

Rule 131101 separately describes a floating price on the third-last business
day of the contract month itself. That conflict remains a final-settlement
question. Stage A neither holds to final settlement nor uses that floating
price to build its reference panel, so it need not silently reinterpret the
floating-price paragraph. This note does not claim the exchange corrected it.

## Still required before exact contract selection

The observation calendar is **not** the exchange business-day calendar used
inside a last-trading-date formula. For example, grain holidays can be shortened
trading days in rates/metals, and FX delivery rules refer to banking calendars.
First determine the applicable exchange/product business days, derive the
child's deadline, and only then count backward five **joint sessions**.

For NES, MTN, M6E, 1OZ and MZC, archive the current rule version, eligible
contract months and the precise business-day interpretation. M6E additionally
requires its delivery/banking-day exceptions. Any applicable known IBKR
mandatory closeout date must enter the earlier-deadline comparison. Unknown
broker dates must be labelled unknown, not replaced with an invented date or
an assertion that no earlier cutoff exists. The present note therefore does
not supply an executable child roll manifest.

Prelaunch mapping is hypothetical application of current child schedules to
actual matching parent contracts. All-root minute acquisition covers candidate
maturities without selecting from future volume. Databento parent expansion
also includes spreads: dated symbology must identify actual outright symbols
before the independently frozen roll map is applied. No continuous front-month
symbol can stand in for the bespoke child deadlines.

## Price units and vendor availability checks

Databento's [contract-notional example](https://databento.com/docs/examples/instrument-definitions/contract-notional)
explicitly uses normalized corn prices in cents per bushel and Treasury prices
in decimal percent-of-par points. Its published ZC and Treasury example outputs
are numerical decimals, not exchange fractional display strings. Accordingly,
after DBN fixed-point decoding, child exposure uses $5 per ZC cent and $100 per
TN full decimal point. Do not apply a second cents conversion or interpret an
already-decimal TN number as a thirty-seconds display. The documentation's
Treasury sample is ZN, not an inspected historical TN definition.

The same source warns that CME's `min_price_increment_amount` can be unusable
for fractional products. Before calculation, reconcile the decoded units and
tick sizes against the actual outright instrument definitions and CME specs;
never derive units solely from that field or from plausible price magnitude.
If the archived metadata cannot establish the TN/ZC historical normalization,
report the unit check unresolved and quote any additional exact-contract
definition request before authorized acquisition.

The vendor's [D-8175 issue](https://issues.databento.com/roadmap/cme-globex-mdp2-data-has-incomplete-bars-for-many-days)
reports incomplete GLBX.MDP3 OHLCV bars before May 21, 2017, including days whose
trades were folded into one bar. On September 10, 2026 the
[vendor issue board](https://issues.databento.com/b/6vrl98vl/feature-ideas)
showed a fix in progress; older indexed views showed confirmed. Its explicit
example dates precede this study, but its stated scope overlaps 2016–17 warmup.
This is a coverage risk, not evidence that every warmup date is defective.
Any affected 252-interval input window, including early 2018 monthly windows,
must be classified **DATA_INCOMPLETE**, rather than measured high volatility
or capital infeasibility. The strategy's no-addition rule does not turn absent
data into evidence that the $5,000 capital design is impossible.

The same board reports D-8238: channel 348, CBOT Globex Interest Rate Futures II,
has gaps on some weeks between January 21, 2018 and August 1, 2020, with a fix
in progress. TN's historical channel membership was not established here; do
not assert that this proves TN gaps. Missing required bars stay missing. No
trade reconstruction, replacement source, additional inputs, or date deletion
is authorized by this note.

The generated dates match `exchange_calendars` 4.13.2 XNYS dates over this
limited period as an independent implementation cross-check. XNYS is not the
source of the CME calendar or a general substitute for futures schedules.

## Bounded follow-up: exact deadline dependencies

A subsequent official-source check narrowed the issue. The
[CME glossary](https://www.cmegroup.com/education/glossary) describes a business
day by whether the exchange is open for business. That general definition
does not itself establish whether a shortened holiday Globex session counts
inside every contract's expiry formula. For example, the
[May 2021 CME clearing notice](https://www.cmegroup.com/tools-information/holiday-calendar/files/2021-memorial-day-advisory.pdf)
discusses May 31 RTH settlement cycles while deferring bank cash movements.
Consequently, a banking holiday and a trading/clearing business day should not
be equated without product evidence.

**M6E:** [Rule 29201.G](https://www.cmegroup.com/content/dam/cmegroup/rulebook/CME/III/250/292/292.pdf)
first counts two exchange business days before the third Wednesday, then
requires an intervening Eurosystem settlement business day and moves a
Chicago/New York bank-holiday termination date to the preceding common
business day. For quarterly June 2023, the ordinary Monday date is June 19;
the bank-holiday provision moves it to Friday June 16. Treating the open
June 19 FX session as sufficient for expiry would be wrong. The Tuesday gap
to Wednesday June 21 remains a Eurosystem business day. This is an application
of the explicit exception, not an invented alternative roll rule.

**IBKR:** its public [physical-delivery policy table](https://www.interactivebrokers.ca/en/trading/marginRequirements/physicalDeliveryLiquidationRules.php)
allows GLOBEX EUR currency delivery for eligible accounts and lists no closeout
deadline for that category. Its Cash/IRA footnote instead applies the generic
cutoff: two business days before first position day for longs or last trading
day for shorts. Thus a generic earlier cutoff must not automatically be
asserted for every EUR futures account. This legacy public table is not an
account-specific M6E confirmation. The remaining broker dependency is the
account category and current M6E applicability, rather than an assumed
universal physical-FX prohibition.

**MZC:** applying its official Friday rule with either ordinary weekdays or
the reviewed joint holiday exclusions produces identical LTDs for all 40
March/May/July/September/December maturities in 2016–2023. This is a calendar
arithmetic comparison, not a price test. The extra December 5, 2018 joint
closure is outside every relevant preceding month. Accordingly, differences
between these masks do not block MZC's LTD calculation in this specific range.

**MTN and 1OZ:** only the following named maturities differ under the two masks.
The final column is a candidate generated by excluding the reviewed joint
holidays, not a newly certified exchange deadline. Good Friday closure
supports the April 2018 gold adjustment; Memorial Day/Thanksgiving treatment
requires a matching official contract-calendar example or definition.

| Child / named maturity | Weekdays only | Reviewed holidays excluded |
|---|---|---|
| MTN June 2016 | 2016-05-30 | 2016-05-27 |
| MTN December 2019 | 2019-11-28 | 2019-11-27 |
| MTN June 2021 | 2021-05-28 | 2021-05-27 |
| MTN June 2022 | 2022-05-30 | 2022-05-27 |
| 1OZ June 2016 | 2016-05-27 | 2016-05-26 |
| 1OZ June 2017 | 2017-05-29 | 2017-05-26 |
| 1OZ April 2018 | 2018-03-28 | 2018-03-27 |
| 1OZ December 2019 | 2019-11-27 | 2019-11-26 |
| 1OZ December 2020 | 2020-11-26 | 2020-11-25 |
| 1OZ June 2021 | 2021-05-27 | 2021-05-26 |
| 1OZ June 2022 | 2022-05-27 | 2022-05-26 |
| 1OZ June 2023 | 2023-05-29 | 2023-05-26 |

All other reviewed MTN/1OZ maturities give the same LTD under these masks. This
limited ambiguity affects exact roll references; it is not evidence that
capital sizing is infeasible. No strategy returns were calculated to choose
either interpretation.
