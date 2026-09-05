# Report A — After-tax evaluation overlay (layer 1)

Verdict: With fixes (documentation fixes, not code). Critical 0 · Important 1 · Minor 10.

Branch `after-tax-overlay`, range `7cbe449..fd729f4`. Scope: src/boring_alpha/tax/*, tax parts of config.py, domain.py, cli.py (aftertax), sweep.py (tax wiring, _after_tax_lines, tax.json), report.py, data/distributions.py, signals/trend.py::TargetExposureAllocation, configs/tax_policy.toml, all tests/test_tax_*.py, tax additions in test_cli.py / test_sweep.py / test_config.py / test_distributions.py, spec §3–§5, §7–§10, §14, the corrections record, the v2 decision record and the BA-001 note. All read end to end.

Read-only checks performed (no writes under experiments/ or data/; no data after 2021-12-31 evaluated):
1. Recomputed every table in the BA-001 note from the two cited artifacts. All figures reproduce exactly.
2. Replayed apply_overlay in memory on the archived development (2007–2017) and validation (2018–2021) strategy, exposure-matched and benchmark runs under hifo-deferral-base; stock code reproduced the archived after_tax_cagr to < 1e-12. Re-ran with one rule changed (Minor #1) to measure materiality.
3. Bounded the omitted $3,000 ordinary-income loss offset from the archived by_year records.
4. Probed the absolute over-sell tolerance at 1e2 … 1e9 units.

## Q1. Accounting correctness
Correct in every mechanism traced, with two departures from tax law measured immaterial (Minor #1, #2) and one material omission documented only in the corrections record (Important #1).

- Real shares: shares = q·A_f/P_f, factor sampled once per ex-date interval (lots.py:24-51); growth on ex-date u = F(u)/F(prev session); pooled child lot = Σ shares·(g−1), basis = Σ cash (lots.py:276-336). Identity checked every session; observed 1.85e-6 / 1.29e-6 on real data against the 1e-5 threshold.
- Return of capital: parent basis reduced by min(cash, basis), child basis = cash, excess over basis realised as gain on the ex-date (lots.py:320-327) — not in the spec, correct tax law, justified addition.
- Wash sales (lots.py:339-410): 61-day inclusive window; one chronological ledger for buys and reinvestments; per-share replacement_capacity; matched shares split into their own slice with the disallowed loss and tacked period; unmatched shares untouched; a January purchase changes December's taxable loss. Earliest-acquired candidates first.
- Lot selection: HIFO by wash-adjusted basis_per_share; FIFO by acquired, not tacked opened (lots.py:235-242).
- Year-end netting (yearend.py:119-194): carryovers enter their own pool in full; long carry hits the 28% bucket first; net ST loss offsets 28% gain before other LT gain; net LT loss offsets ST gain; only final negative balances carry, character retained. Matches the Schedule D / 28% Rate Gain Worksheet ordering.
- Commodity pool: deferral = standard gains + ROC; mtm_60_40 = year-end mark, basis stepped, 60/40 signed (overlay.py:186-194). Final-session mark precedes liquidation; nothing double-counted.
- Collectibles: LT gains to collectibles_rate; cap ≤ min(ordinary, 0.28) enforced at load.
- Qualified dividends: qualifies() counts (min(closed, ex+60) − max(acquired+1, ex−60)).days + 1 > 60 (yearend.py:28-38); boundaries correct. Uses untacked acquired (overlay.py:222) — conservative.
- Cash interest: cash_{t−1}·(factor_t − 1), first session excluded, matching the engine.
- NAV convention (overlay.py:254-287): exactly §4.8; liquidation year computed twice on the same carry-in. A liquidation netting to a loss gives negative tax_liquidation — legitimate, untested (Minor #7).
- is_long_term > 365 days: one day lenient in leap years; immaterial.
- TargetExposureAllocation (trend.py:192-224): hold = annual and month != 12; engine enters on an empty book. Matches §5.1–5.2.

## Q2. Can the tests fail?
Yes, overwhelmingly; they are hand-computed. Mechanism → test table: real-share conversion (AdjustmentFactorTests, DistributionTests, JitterTests); pooled child lot (test_two_lots_share_one_pooled_child_lot); ROC (two tests); wash 30 in / 31 out; partial match slices (ReplacementSliceTests ×4); matched once; ledger order, Jan fixes Dec; FIFO by acquisition after tack; HIFO vs FIFO through overlay; netting (NettingTests, 18 hand cases); MTM 60/40; collectibles; QDI boundaries (HoldingPeriodTests ×6 and others); cash interest; NAV rescale; identity failure surfaced; grid fixed, hash excludes path; replay reconciliation; aftertax = in-sweep, naming, idempotency, legacy refusals (AfterTaxCommandTests ×16).
Weak/shape-only: test_the_command_prints_one_line_per_run (substrings only); a few appropriate shape tests. No tautological tests. Gaps: Minor #7; ROC after an mtm step-up; DBC sale character under mtm.

## Q3. Replay / reconcile
test_aftertax_reproduces_the_in_sweep_result_exactly asserts produced["runs"] == in_sweep["runs"] for both distribution paths. Not byte-for-byte at file level by design (envelope carries "source": "aftertax" and a possibly different code_sha256). The name tax-<policy12>-<dist12>-<code12>.json is honest: policy hash = rates + fractions + classes, path excluded; distribution hash = canonical truncated CSV + methodology + truncated splits + fingerprint_version; code hash = every .py under the package. validate_replay is independent of the lot identities. Legacy schema-5 archives are labelled legacy-unverified, and the note says so.

## Q4. BA-001 note
Every number traces and reproduces exactly. Provenance accurate. Claims proportionate. One gap: the caveats list the NAV convention and pre-tax drawdown but not the $3,000 offset (Important #1). Does not change direction; should be stated.

## Q5. Anything > 5 bps/yr
One item: the $3,000 offset — account-size dependent, up to ~60 bps/yr at $100k in a validation-like period, ~6 bps/yr at $1M. Everything else measured or bounded below 5 bps/yr: same-lot self-match ≤ 0.003 bps/yr measured; DBC sale character under mtm within the 1.2–1.3 bps/yr the note reports for the whole mtm axis; QDI without tack, leap-day leniency, GLD expense sales (~1 bp) smaller. Foreign tax credit pass-through on EFA/EEM omitted; rough bound ≈ 3 bps/yr of gross income.

## Strengths
- Right shape for the problem: real shares with unadjusted-dollar basis, piecewise-constant factor, pooled child lot keeping lot count linear.
- Wash ledger handles the hard cases correctly and is tested on them.
- net_and_tax is a faithful Schedule D with eighteen hand-computed cases.
- NAV convention exactly as written; liquidation is a difference of two full netting passes.
- Identity checks reported whether or not they pass; thresholds fixed before the corrected replays.
- Replay independent of tax identities; refuses cropped windows, missing variants, altered bytes, non-finite values, wrong fill prices.
- Content addressing honest and tested from both sides.
- BA-001 note fully traceable.

## Issues

### Critical — none.

### Important
1. Omitted $3,000/yr ordinary-income capital-loss offset — material at the note's account size, asymmetric, not stated where readers look. overlay.py:47-55 (KNOWN_OMISSIONS), yearend.py:179-182, docs/notes/2026-09-04-BA-001-after-tax.md. U.S. individuals deduct up to $3,000 of net capital loss against ordinary income yearly, reducing the carryover. The overlay never does (test_income_is_never_offset_by_capital_losses pins the absence). The corrections record's "Remaining scope" lists it; KNOWN_OMISSIONS, summary.md and the note do not. From archived by_year (hifo-deferral-base), upper-bound credit min(3000, new net loss) × 0.35 added to terminal wealth: development — strategy 3/11 net-loss years ≈ $1,190 ≈ +7 bps/yr; exposure-matched 4/11 ≈ $1,610 ≈ +10; benchmark 4/11 ≈ $2,120 ≈ +12. Validation — strategy 3/4 ≈ $2,710 ≈ +60 bps/yr; exposure-matched and benchmark 0. Lower bound ≈ 43% of these. A fixed dollar amount scaling inversely with account size — the overlay's homogeneity is exactly what excludes it. BA-002's gate is 50 bps/yr.
Fix: (a) add to KNOWN_OMISSIONS with bound and account-size dependence; (b) one paragraph in the note with these figures; (c) for BA-002, decide before the charter locks: model it (NAV convention accommodates a fixed-dollar credit as negative tax at the cost of declaring initial_cash as account size) or state the criterion excludes it and the direction of bias. Reviewer recommendation: (a)+(b) now; (c) modelled.

### Minor
1. Partially sold lot's own remainder treated as its wash replacement (lots.py:389-392; pinned by tests/test_tax_lots.py:357). Reviewer believes the IRS position (Rev. Rul. 56-602, as recalled — citation unverified) is that shares retained from the same single-lot purchase are not replacement shares. Measured with self-matching disabled: after_tax_cagr moves ≤ +0.003 bps/yr. Fix: exclude lots sharing the sold lot's purchase_id from pre-sale candidates; confirm the ruling with the account holder.
2. DBC sales characterised 60/40 under mtm_60_40, not by holding period (overlay.py:230-240, yearend.py:76-79). Whole mtm axis is 1.2–1.3 bps/yr. Fix: mark_to_market=False for sale records, or document in §4.5 and KNOWN_OMISSIONS.
3. by_year.wash_disallowed scaled, totals.wash_sale_disallowed_total unscaled (overlay.py:258 vs :332-335). Exclude reporting fields from Amounts.scaled, or label units in both places.
4. Code fingerprint covers the whole package (report.py:101-107): any unrelated source change yields a "new" tax identity. Optional overlay_code_sha256.
5. Over-sell guard is absolute 1e-9 shares (lots.py:21,229). Harmless at lab scale.
6. run_aftertax appends provenance on idempotent re-runs (cli.py:399-400).
7. Untested: negative tax_liquidation; ROC after an mtm step-up; DBC sale character under mtm.
8. test_the_command_prints_one_line_per_run asserts substrings only.
9. QDI period ignores wash tack (overlay.py:222): conservative and deliberate; record as a stated approximation in §4.5.
10. Leap-year leniency in is_long_term (yearend.py:22-25); mention the Feb 29 case in §4.5.

## Recommendations
1. Land Important #1 (a) and (b) before the note is cited elsewhere. Take (c) as an explicit BA-002 charter decision.
2. Resolve Minor #1 with the account holder.
3. Make the mtm sale-character choice explicit (Minor #2).
4. Fix Minor #3 before summary.md tables are read without the note's caveat.
5. Extend KNOWN_OMISSIONS to match the corrections record's "Remaining scope".

## Assessment
Ready to merge: With fixes — documentation fixes (Important #1 a/b), not code. The accounting is correct where it matters; the real archives were replayed in memory and reproduce the cited artifacts to machine precision; the two places where the code's rule differs from tax law are far below 5 bps/yr. The tests are hand-computed and would fail on any plausible regression. The BA-001 note is fully traceable and proportionate except for the one unstated omission.
