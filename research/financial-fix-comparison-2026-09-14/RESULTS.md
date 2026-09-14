# Accounting follow-up: 27 of 28 checks pass

The additional round resolves three of the four remaining earnings cases and
formally adopts the previously documented Whirlpool book-equity correction.
**One earnings case remains unresolved. The before-and-after return comparison
did not run**, in accordance with the agreed data gate. We still cannot say
whether the corrected version earns more or less than the original baseline.

No strategy rules, portfolio settings, prices, or previous results were
changed. This round used only existing local data: zero new data requests,
$0 new paid data, zero model fits, and zero trading simulations.

| Check | Previous round | This round |
|---|---|---|
| VF, January 2026 trailing common earnings | Unqualified | $90.349 million, qualified |
| Aon, January 2024 trailing common earnings | Unqualified | $2.723 billion, qualified |
| Aon, January 2026 trailing common earnings | Unqualified | $2.718 billion, qualified |
| Whirlpool, January 2026 book equity | Different from old target | $2.380 billion reported parent total; corrected target accepted |
| Whirlpool, January 2026 trailing common earnings | Unqualified | Still unqualified |

## What resolved the three earnings cases

VF's quarterly filing explicitly says its accounting policies have not
materially changed from its fiscal 2025 annual report. That annual report
defines the total basic-EPS numerator. The generic rule now follows this
specific, historically available source reference and checks total net income,
common shares, and total basic EPS. It retains discontinued operations in total
earnings; it does not substitute the continuing-operations figure. See the
[quarterly filing](https://www.sec.gov/Archives/edgar/data/103379/000010337925000060/vfc-20250927.htm)
and [referenced annual filing](https://www.sec.gov/Archives/edgar/data/103379/000010337925000023/vfc-20250329.htm).

Aon's annual EPS policy expressly includes participating securities in the
basic-share denominator. Its quarterly filings direct readers to the specific
preceding annual statements. The new rule follows that reference, checks the
same issuer and annual period, requires the annual filing to predate the
quarterly filing, and reconciles parent net income with basic shares and EPS.
It continues to reject a separately disclosed earnings-allocation adjustment
or an arithmetic mismatch. The former blanket rejection of participating
securities was too broad for this explicitly described basic-EPS method. See
the [2022 annual policy](https://www.sec.gov/Archives/edgar/data/315293/000162828023004087/aon-20221231.htm),
[2023 quarterly reference](https://www.sec.gov/Archives/edgar/data/315293/000162828023035412/aon-20230930.htm),
[2024 annual policy](https://www.sec.gov/Archives/edgar/data/315293/000162828025006093/aon-20241231.htm),
and [2025 quarterly reference](https://www.sec.gov/Archives/edgar/data/315293/000162828025047805/aon-20250930.htm).

The reported Whirlpool equity total was already qualified by v2; this round
corrects the expected test value rather than changing its production value.
Original audit and v2 files remain intact.

## Why Whirlpool still stops this comparison

The September 2025 filing repeats a 2024 nine-month basic-EPS numerator of
$69 million, 55.0 million basic shares, and basic EPS of $1.27. Given their
stated precision:

- The numerator can lie between $68.5 million and $69.5 million.
- Shares multiplied by EPS imply between $69.51175 million and $70.18875 million.
- Those intervals do not overlap; their nearest edges differ by $11,750.

The comparative quarter also fails: $109 million and 55.2 million shares versus
$2.01 EPS leave a minimum $1.07575 million gap between their precision intervals.
The quarterly discrepancy is supporting evidence; the nine-month discrepancy
is the one that blocks the trailing-year input.

Whirlpool discloses a changed rounding presentation, but that general notice
does not quantify a correction that closes these gaps. Cached SEC companyfacts
records show the same nine-month figures under both the original October 2024
accession and the October 2025 comparative accession. A later restatement is
therefore not the explanation found in our cached evidence. See the
[original comparative filing and EPS note](https://www.sec.gov/Archives/edgar/data/106640/000010664025000140/whr-20250930.htm).

This is an unresolved source qualification under our rules, not a finding that
the issuer's statements are materially wrong. We did not widen rounding
tolerances, infer an earnings amount backwards from rounded EPS, or drop this
fixture to make the gate pass.

## Coverage and checks

| Inputs present across all 5,700 company-month slots | Original baseline | Previous v2 | This round |
|---|---:|---:|---:|
| Common book equity | 2,251 (39.5%) | 2,338 (41.0%) | 2,338 (41.0%) |
| Trailing common earnings | 2,493 (43.7%) | 2,577 (45.2%) | 2,595 (45.5%) |

The new rules add 18 earnings inputs relative to v2. In total, the candidate
payload contains 189 recovered fields across 142 company-months and 13
companies. Every original nonmissing input and every previous v2 candidate
value is preserved. The source sample remains 52 filings from 18 companies;
replaying every slot does not make this a complete financial dataset. Coverage
includes slots that are not eligible for trading.

Eight focused checks pass, including rejection of wrong-company, wrong-period,
future, missing, and ambiguous annual policy sources. All 70 accepted policy
uses are checked against original source text and historical availability.
An independent numeric source audit checks all 189 recovered fields through
1,062 fact uses and 298 unique facts. Of those, 297 match exact cached SEC API
records; the remaining custom parent-equity fact is verified in its original
filing. These checks do not override the remaining fixture failure.

The frozen protocol, extraction rules, inputs, results, and verification are
saved alongside this report. All 136 protected prior artifacts and the
previously frozen raw input hashes remain unchanged.

The practical decision is to **park this upgrade and retain the original as
the only evaluated baseline**. Three accounting fixes are now reusable, but
the coverage gain remains modest and no return improvement has been shown.
An independently supported explanation of the Whirlpool figures would be
needed to reconsider this gated comparison. No further parser cycle, download,
backtest, paper monitor, or live trading is queued.
