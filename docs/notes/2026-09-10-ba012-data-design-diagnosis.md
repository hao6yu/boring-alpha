# BA-012: reference-data design diagnosis

This is a diagnosis of the frozen version 1 input design, made before any
BA-012 strategy returns. It does not change the frozen protocol or register a
replacement strategy. The observed gaps and final Stage A status are recorded
in the separate Stage A result note.

## Gold contract selection

The frozen rule uses every even gold maturity, including October. CME's
settlement procedure effective October 23, 2017 instead defines active GC
months as February, April, June, August and December, excluding the spot
month. October is listed but absent from this active sequence. CME's 2021
guide likewise lists October contracts while omitting October from its active
TAS/TAM months. Listing alone was an insufficient basis for choosing a
historical reference contract.

Sources: [2017 settlement rules, Appendix B](https://www.cmegroup.com/market-regulation/rule-filings/2017/09/17-358_1.pdf)
and [2021 Metals Guide](https://www.cmegroup.com/trading/metals/files/metals-prod-guide-2021.pdf).

The initial snapshot's 26 missing gold references were all October GCV
contracts. Their alignment with the listed-versus-active distinction is
evidence of a design problem, not proof of the cause of every missing minute
or a guarantee that December has complete coverage.

## Treasury references

CME's 2016 Treasury calendar-spread study describes open-interest migration
near the delivery-month boundary. It uses a nine-exchange-day roll window
ending on the first business day of the delivery month and identifies August
25, 2016 as a peak-roll day for TNU6–TNZ6. The child-driven early transition
can precede peak migration, although it remains within that wider roll period.
Strong calendar-spread activity does not establish an outright trade during
every selected one-minute window.
[CME calendar-spread study](https://www.cmegroup.com/trading/interest-rates/files/treasury-futures-calendar-spreads.pdf).

## Concrete next research step

A data-specification revision should use an independently justified liquid
gold maturity schedule and investigate official daily settlement references.
First verify a narrowly defined settlement-coverage sample; only then freeze
any revised timing, contract and missing-data rules. Preserve version 1's
failure to obtain complete inputs. No return result should be consulted to
choose the replacement rules.

Databento documents CME settlement messages in `GLBX.MDP3`'s `statistics`
schema (`stat_type=3`, `rtype=24`). That is a feasible source path, not proof
of complete usable history. CME can publish multiple preliminary/final
updates; it does not publish MDP settlements for instruments without open
interest or volume. `ts_ref` identifies the trading-session date, while
`ts_event` and `ts_recv` describe publication/receipt timing. A causal study
must preserve updates and reject prices unavailable at its fixed decision
cutoff. It cannot retrospectively substitute an eventual final settlement.
[Statistics schema](https://databento.com/docs/schemas-and-data-formats/statistics),
[CME normalization](https://databento.com/docs/venues-and-datasets/glbx-mdp3).

The dataset's overall June 2010 start does not establish schema-specific
coverage. Legacy data before May 21, 2017 lacks capture timestamps, which
limits receipt-time reconstruction.
[Dataset coverage](https://databento.com/datasets/GLBX.MDP3).

No revised input series, settlement data purchase, P&L test, account change
or order is authorized by this diagnosis. It prepares a specific next
coverage test instead of another open-ended strategy search.
