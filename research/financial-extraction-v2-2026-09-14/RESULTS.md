# Bounded financial extraction: data gate failed

The extraction prototype added 171 financial inputs across 139 company-months
and 13 companies. It did **not** pass the frozen data gate, so no new strategy
comparison, profitability run, or model fit was performed. The prior trading
baseline remains unchanged. New paid data cost was $0.

| Input present | Original | Prototype | Increase |
|---|---:|---:|---:|
| Common book equity | 2,251 / 5,700 (39.5%) | 2,338 / 5,700 (41.0%) | 87 |
| Trailing common earnings | 2,493 / 5,700 (43.7%) | 2,577 / 5,700 (45.2%) | 84 |

The denominator is every original company-month slot from January 2022 through
September 2026, including slots that are not eligible for trading. This is
input availability, not a trading success rate. All 5,700 slots and 100 original
company identities were retained. Existing nonmissing values and all other
input fields were preserved.

## Why the comparison did not run

The frozen requirement was to reproduce all 28 missing-field recoveries from
the earlier ten-company audit using general rules. The prototype reproduces
**23 of 28** exactly. It produces a better-supported value for one additional
book-equity target and abstains on four earnings targets:

| Check | Result |
|---|---|
| WHR, January 2026 book equity | $2.380 billion reported parent total; the earlier audit used $2.381 billion from rounded components. |
| WHR, January 2026 trailing earnings | Prior-year nine-month numerator does not reconcile with reported total basic EPS within the chosen rounding allowance. |
| VFC, January 2026 trailing earnings | Current quarterly EPS note covers continuing operations; the frozen rules cannot qualify the total-income numerator. |
| AON, January 2024 and January 2026 trailing earnings | Participating securities require an explicit allocation rule that this parser does not implement. |

The earlier claim of complete, exact recovery was too strong. See
[the correction and original filing evidence](ERRATA.md). The old audit is
preserved for traceability; its disputed values are not silently inserted into
the prototype. Even correcting the WHR book target would leave four failures.

Passing these fixtures would itself be necessary, not sufficient, for a useful
full-cohort dataset. Most input gaps still lack a complete, qualified source set.
Trailing earnings typically require an annual filing plus aligned current- and
prior-year quarterly figures. One newly downloaded quarter cannot supply that
history by itself.

## Scope and cost control

The source-only plan selected 90 filings before implementation or any new
return inspection. The parser was frozen after fixture development, before
the broader source check. It uses statement structure, accounting labels,
original inline-XBRL facts, precision-aware reconciliation, and a two-exchange-
session filing delay. It contains no ticker-specific rules or manually supplied
production answers.

The completed source sample contains **52 filings from 18 companies**: all 34
fixture filings and 18 further filings. Only eight of the 171 recovered inputs
belong to companies outside the original ten-company sample: EW (2), MSI (3),
and SYK (3). These results establish limited reuse; they do not establish broad
generalization.

There were 60 original-filing navigations against a ceiling of 90, including
seven repeat navigations after truncated DOM captures were detected. Eight
partial captures are retained and excluded from parsing. Filing 53 loaded but
could not be saved after repeated browser disconnections. Filings 54–90 were
not requested. Acquisition stopped with 30 navigations unused because the
frozen fixture gate had already failed; additional non-fixture filings would
not resolve those failures. The local capture server has been stopped.

## Verification and interpretation

- Sixteen defensive checks pass, covering truncation, wrong currency,
  noncontrolling dimensions, omitted equity components, invalid EPS arithmetic,
  preferred-share ambiguity, and historical availability.
- An independent source audit checks all 171 added fields through 948 fact
  uses and 271 distinct source facts. It verifies original DOM identifiers,
  entity, period, units, arithmetic, and filing delay without invoking the
  extraction parser.
- Of those 271 facts, 270 match exact accession/period records in the cached
  SEC companyfacts data. One custom fact has no corresponding API record and
  is verified against its original filing. Numerical agreement does not by
  itself resolve common-shareholder accounting scope.
- All 101 frozen prior research artifacts and the frozen input/plan hashes
  remain intact. No prices, strategy weights, risk limits, or return results
  were changed by this pass.

This is a stopped data-quality experiment, not evidence that the trading
strategy improved or failed. The useful result is a replayable extractor with
documented limits. The coverage increase is too small to justify treating it
as a completed model upgrade.

Before further strategy testing, the remaining work is to resolve the four
earnings checks, formalize the WHR rounding correction, and scope complete
filing sets across the cohort. That work needs a separate, bounded decision;
no further download, tuning, paid data, or monitoring is queued. The current
baseline remains the only evaluated version.
