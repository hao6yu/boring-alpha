# Strategy registry

Every strategy receives a stable identifier and a human-readable charter before
its final evaluation. Historical results do not live in these documents; they
belong to immutable experiment artifacts linked from a later review.

| ID | Name | Status | Charter |
|---|---|---|---|
| BA-001 | Multi-Asset Trend | Evaluation complete — Inconclusive (revision 4); sealed period unrevealed. Reviews: [development](../reviews/BA-001-development.md), [validation](../reviews/BA-001-validation.md) | [BA-001.md](BA-001.md) |
| BA-002 | Multi-Horizon Trend | [Two-feed seen-history diagnostic complete — practical no-go](../reviews/BA-002-source-sensitivity.md). Revision 1 unchanged; formal freeze unconfirmed, no holdout evaluation. | [BA-002.md](BA-002.md) |
| BA-003 | Relative-Strength Tilt | Draft proposal — defaults awaiting review; not locked, implemented or evaluated. Shared family holdout unchanged. | [BA-003.md](BA-003.md) |

## Revision policy

- Before a strategy's first run on historical market data, its charter may be
  amended in place, provided every change is dated in the charter's change log
  and the charter states that no historical data has been run. Synthetic runs
  do not count as historical data.
- From the first historical run onward, the rules below apply.
- Clarifying wording without changing behavior may update the current charter
  and must be noted in its change log.
- Any change to the universe, feature timing, signal, parameter, sizing,
  execution, costs, or acceptance criteria creates a new candidate version.
- A candidate derived after viewing BA-001 results must not replace BA-001's
  record. It receives a new ID such as BA-002 or an explicitly declared variant
  such as BA-001B.
- Rejected strategies remain in the registry. Failed research is evidence, not
  clutter to erase.
