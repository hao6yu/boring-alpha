# Correction to the earlier financial-input audit

The previous audit's statement that all 28 missing inputs were exactly
recovered was too strong. Its files remain
unchanged; this document records the correction. No previous trading result
used those manually recovered values.

## Whirlpool: parent equity reported in rounded millions

For September 30, 2025, the original balance sheet reports parent equity of
**$2,380 million**. Its displayed common-equity components sum to **$2,381
million**: 65 + 3,479 + 1,272 − 1,888 − 547. The numbers are rounded to millions.
The earlier audit used the component sum and called the reconciliation exact.
The current parser retains the directly reported parent total and logs the
$1 million company-equity rounding difference. This is not a change to the
value of the user's account. See the
[original Whirlpool quarterly filing, balance sheet](https://www.sec.gov/Archives/edgar/data/106640/000010664025000140/whr-20250930.htm).

## Whirlpool: a comparative earnings cross-check remains unresolved

The same filing's EPS table presents 2024 nine-month net income of $69 million
and basic weighted shares of 55.0 million, while the income statement reports
total basic EPS of $1.27. The quotient is about $1.2545 and does not reconcile
within the parser's allowance for those displayed precisions. The current-year
amount qualifies, but a complete trailing-year figure requires the prior-year
amount too. The earlier −$182 million reconstruction is therefore withheld
from the automated payload. This does not establish that the filing's
numerator is erroneous; it establishes that the automated qualification needs
further accounting review. See the same
[original filing, earnings-per-share note](https://www.sec.gov/Archives/edgar/data/106640/000010664025000140/whr-20250930.htm).

## Aon: participating securities

Aon's EPS policy includes participating securities in its basic-share
calculation and describes additional diluted-EPS methods. The generic parser
does not infer that any common-income adjustment is zero. The two previously
reconstructed trailing amounts, $2.723 billion and $2.718 billion, remain
unqualified by this implementation. See Aon's original
[2022 annual filing](https://www.sec.gov/Archives/edgar/data/315293/000162828023004087/aon-20221231.htm)
and [2024 annual filing](https://www.sec.gov/Archives/edgar/data/315293/000162828025006093/aon-20241231.htm).
Source hashes are recorded for plan documents 17–20 in the retrieval manifest.

## VF: total earnings versus continuing operations

VF's quarterly EPS footnote presents continuing operations. The current and
comparative total net-income amounts reconcile numerically with total basic
EPS, but the frozen parser requires an explicit same-filing link before using
that total numerator as common earnings. It does not inherit the annual
policy across filings without further proof and does not substitute
continuing-operations income. The earlier $90.349 million trailing figure
remains unqualified. See the original
[September 2025 quarterly filing](https://www.sec.gov/Archives/edgar/data/103379/000010337925000060/vfc-20250927.htm)
and [March 2025 annual filing](https://www.sec.gov/Archives/edgar/data/103379/000010337925000023/vfc-20250329.htm),
plan documents 7–8.

These four earnings abstentions are limitations of the qualification rules,
not findings that the issuers' financial statements are wrong. No rule or
fixture target was relaxed after observing the broader extraction results.
