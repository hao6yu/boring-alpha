# Numerical and text feature contract for a later experiment

This defines extraction rules before any fitting or investment-return calculation.
It is not a claim that all numerical fields have been extracted or validated.
The original 100-slot availability result and the revised event-definition result
remain separate. The future experiment still needs its own point-in-time universe,
training schedule, costs, risk rules and evaluation registration.

Use the earliest full quarterly/year-end earnings release defined by repair v2.
Retain earlier preliminary releases, guidance and selected financial updates as
separate dated information. Both numerical-only and text-plus-numerical models
receive the same predecessor and coverage flags and the same pre-entry price data.
An unsearched interval is unknown; it is not a verified absence of preliminary
information. Initial price features end at the session before proposed entry.

For a future dataset, inspect the 90 calendar days preceding the full release,
plus any explicitly referenced earlier preliminary disclosure. Classify by fiscal
period, not merely date proximity. This is a collection scope, not proof no other
public information existed. Preserve the archive coverage status for every event.

## Source and observation time

- Store every extracted value with original accession, exhibit, source hash,
  table/row/column label, units, currency, fiscal period, duration, accounting
  basis, share basis and availability date. SEC-furnished original exhibits
  qualify as public original documents; the word "filed" is not a restriction to
  securities-law liability status.
- The original current release's explicitly comparable prior-year columns can
  supply numerical comparisons because they were available at this decision.
  They do not replace the mandatory original prior-release document used for
  language comparison and provenance. Keep originally reported and currently
  recast comparative figures separately, and flag differences.
- Later amendments, restatements, current companyfacts snapshots and future
  share adjustments cannot overwrite the event-time inputs. Corrections become
  information only at their own availability times.

## First numerical specification

Use reported GAAP revenue and diluted EPS attributable to common shareholders.
Use an explicitly labeled equivalent sales/total-revenue measure only when its
definition matches in both compared periods. Do not substitute bank managed
revenue for reported revenue, segment revenue for consolidated revenue, or
non-GAAP EPS for GAAP EPS. Adjusted/non-GAAP numbers remain audit annotations
for this first specification rather than extra predictors selected after results.

Revenue growth is `(current revenue / comparable prior revenue) - 1` only when
the prior value is positive, definitions/currency match and periods have equal
duration. Otherwise the feature is missing with a specific reason. Do not
convert zero prior revenue to an arbitrarily large growth rate.

The EPS feature is the change in comparable GAAP diluted EPS divided by the raw
stock close from the session before entry. Both EPS values must be on the same
share basis as that price. Prefer current-release comparative columns explicitly
restated onto the same share basis. Otherwise use only verified splits already
effective by the decision, recording the transformation. If the share basis is
unresolved, the feature is missing. EPS divided by a future split-restated price
does not qualify.

Quarterly and full-year observations have separate scope flags. Match a quarter
to the same fiscal quarter and a full year to the same fiscal year, including
52/53-week year identity. Document matching does not imply equal duration.
Revenue/EPS growth across a 13-week versus 14-week quarter is missing in the
first specification, with an unequal-duration flag. Do not normalize by weeks
and imply that the seasonal extra week has average sales or earnings.

For IFRS-to-U.S.-GAAP or other definition changes, a numerical comparison is
allowed only where the original current release supplies explicit same-basis
comparatives/reconciliation. Otherwise preserve the event, use missing numerical
values and record the basis-transition flag. Original prior language stays
unchanged; an IFRS report is not rewritten as if it had originally used GAAP.

Missing predictor values may later receive a training-only median and a missing
indicator, using the same procedure in both models. This is a declared modeling
choice for inputs. Missing prices, outcomes, delisting cash and original source
documents are never given fabricated returns or silently removed from the audit.

## Text and document scope

Use identified full earnings-release narrative. Where that release explicitly
refers to a shareholder letter furnished in the same original filing as the
vehicle for the full results, include that identified narrative and retain its
document-type flag. Keep tables for numerical extraction; avoid counting copied
tables, navigation, image text placeholders or duplicate attachments as repeated
language. Do not silently add conference-call transcripts or later presentations.

Align current and prior document types explicitly. Missing prior narrative or
an unresolved document-type substitution remains a source problem. Record
document length/type and accounting-transition flags in both baselines so the
text comparison does not silently receive extra selection metadata.

Vocabulary, scaling, imputation, regularization and any dimensionality reduction
must use matured past training data only. Modern pretrained model scores do not
supply historical trading signals. An agent may extract source-grounded values
with evidence; future knowledge must not supply missing financial values or labels.

## Audit examples that these rules must handle

| Case already observed | Required handling |
| --- | --- |
| TEAM IFRS-to-U.S.-GAAP transition | Original prior document joins can pass; numerical fields need original-current same-basis comparatives or missing flags. |
| SNPO 13-week versus 14-week Q4 | Keep original fiscal-period join; mark first-spec growth features missing and preserve duration. |
| NXTC annual and quarterly figures together | Select the declared matched scope and correct table column; do not substitute annual values for Q4. |
| ENVX press release plus shareholder letter | Preserve the two original document types and the referenced full-results narrative; no later investor presentation. |
| PTN split-restated price candidate | Prove historical raw/share basis and actions before dividing EPS by price or sizing whole shares. |

This contract resolves the treatment choices. A subsequent extraction audit must
verify actual values and flags before any model training is authorized.
