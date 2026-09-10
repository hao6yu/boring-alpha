# BA-012 Stage A: complete acquisition, unusable monthly inputs

September 10, 2026. **Version 1 has no valid sizing or profitability verdict.**
All 2,080 quoted reference windows were downloaded and verified, but none of
the 72 scheduled monthly cases has the complete 252-interval input required
by the frozen protocol. The result is `INCOMPLETE_STUDY_NO_CAPITAL_VERDICT`.

This exposes a reference-data design problem. It does not establish that the
$5,000 account must remain in cash, that a larger account solves the problem,
or that the trend hypothesis is profitable or unprofitable.

## Measured result

The archive covers every quoted weekday window from January 11, 2016 through
December 29, 2023, including the independently reconstructed 2,007 joint
sessions. It contains 42,944 raw parent records, including other maturities
and spreads. Complete acquisition means the requested responses are present;
it does not imply that every selected outright traded at the required time.

The dated contract mapping resolved all 189 required raw symbols. Matching
those identities to the frozen roll schedule found **134 missing exact-minute
references across 125 joint dates**:

| Child exposure | Parent reference | Missing required references |
|---|---|---:|
| NES equity | ES | 0 |
| MTN Treasury | TN | 47 |
| M6E currency | 6E | 0 |
| 1OZ gold | GC | 85 |
| MZC corn | ZC | 2 |

All issues are absent required outright bars. No missing symbol identity or
nonpositive selected price was substituted for a coverage gap. Of the 85 gold
gaps, **82 involve October contracts**. Treasury gaps are concentrated in the
earlier years, with 45 of 47 occurring in 2016–2020.

Each January 2018–December 2023 monthly window has only **212–239 valid
intervals of the required 252**. Thus all 72 cases are `DATA_INCOMPLETE`.
No missing interval was filled, omitted to shorten the window, or treated as
a cash decision. The runner records the same unresolved input status for
the virtual $5,000, $25,000 and $100,000 cases. It invokes no numerical sizing
optimization when inputs are incomplete.

## Cost and reproducibility

The user approved a $1 aggregate acquisition estimate budget. Across all
runs, including failed or uncertain requests, **2,155 reserved data attempts
total $0.162474512840 in provider estimates**. This leaves $0.837525487160
of the estimate budget. Actual billing or remaining signup credit was not
queried; the estimate is not a provider-enforced billing cap.

Repeated transport timeouts required resumptions. Complete files were reused;
failed attempts remained in the shared budget ledger. The final collector
uses 16 concurrent workers, a shared limit of 10 metadata starts per second,
one paid attempt per date per run, and bounded resumptions. Transient failures
allow other dates to finish, while validation, authorization, reconciliation
and budget failures stop new requests. No credential was written to an
artifact. The final full-plan pass plus two remainder passes completed all
dates. The earlier collector was stopped between drained runs before replacing
its scheduling logic.

The 61 focused collector checks passed after that change. The sizing core,
input preparation and result runner had separately passed 67 checks and
independent review. These checks establish implementation behavior, not
economic performance.

- [Coverage and acquisition evidence](../../research/ba012-stage-a/coverage-and-acquisition-v1.json)
- [Pinned monthly inputs](../../research/ba012-stage-a/inputs-v1.json)
  — SHA-256 `603629b98c3d9f7c65dd9ed66865cf1c5c36df7ae7a75d4328901e3170846b0b`
- [Stage A result summary and per-date hashes](../../research/ba012-stage-a/results-v1/summary.json)
  — SHA-256 `01f9da693aebaaa935ee6df905bf4e461e950f6b4d73bfd88c53fc8ba618eaa5`

The frozen protocol hash remains
`095fa832c82645a6f570668813b59b08afa4a21c93466980703ff78c46eec67f`.
No BA-012 strategy P&L, 2024–2025 price inspection, order, subscription or
funded pilot occurred.

## Decision and next bounded step

**Stop version 1 before the return study.** Its current reference and contract
selection cannot supply the complete panel it requires. Changing capital
would leave that defect unchanged.

The [data-design diagnosis](2026-09-10-ba012-data-design-diagnosis.md) identifies
an independently documented liquid gold schedule that bypasses October, and
a documented path to CME official settlement messages. The next step is one
small settlement-coverage check, including publication/revision timing and
legacy-history limitations, before freezing revised input rules. Complete
settlement history is not yet verified and no replacement series was bought
or tested. Preserve this result; do not spend effort on a return engine until
the revised input design has usable evidence.
