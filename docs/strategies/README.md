# Strategy registry

Every strategy receives a stable identifier and a human-readable charter before
its final evaluation. Historical results do not live in these documents; they
belong to immutable experiment artifacts linked from a later review.

| ID | Name | Status | Charter |
|---|---|---|---|
| BA-001 | Multi-Asset Trend | Locked for implementation | [BA-001.md](BA-001.md) |

## Revision policy

- Clarifying wording without changing behavior may update the current charter
  and must be noted in its change log.
- Any change to the universe, feature timing, signal, parameter, sizing,
  execution, costs, or acceptance criteria creates a new candidate version.
- A candidate derived after viewing BA-001 results must not replace BA-001's
  record. It receives a new ID such as BA-002 or an explicitly declared variant
  such as BA-001B.
- Rejected strategies remain in the registry. Failed research is evidence, not
  clutter to erase.
