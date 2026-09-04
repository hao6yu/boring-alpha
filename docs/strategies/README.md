# Strategy registry

Every strategy receives a stable identifier and a human-readable charter before
its final evaluation. Historical results do not live in these documents; they
belong to immutable experiment artifacts linked from a later review.

| ID | Name | Status | Charter |
|---|---|---|---|
| BA-001 | Multi-Asset Trend | Locked for implementation (revision 3) | [BA-001.md](BA-001.md) |

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
