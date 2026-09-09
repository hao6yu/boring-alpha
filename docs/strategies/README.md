# Strategy registry

Every strategy receives a stable identifier and a human-readable charter before
its final evaluation. Historical results do not live in these documents; they
belong to immutable experiment artifacts linked from a later review.

| ID | Name | Status | Charter |
|---|---|---|---|
| BA-001 | Multi-Asset Trend | Evaluation complete — Inconclusive (revision 4); sealed period unrevealed. Reviews: [development](../reviews/BA-001-development.md), [validation](../reviews/BA-001-validation.md) | [BA-001.md](BA-001.md) |
| BA-002 | Multi-Horizon Trend | [Two-feed seen-history diagnostic complete — practical no-go](../reviews/BA-002-source-sensitivity.md). Revision 1 unchanged; formal freeze unconfirmed, no holdout evaluation. | [BA-002.md](BA-002.md) |
| BA-003 | Relative-Strength Tilt | Draft proposal — defaults awaiting review; not locked, implemented or evaluated. Shared family holdout unchanged. | [BA-003.md](BA-003.md) |
| BA-004 | Passive Capture | **Redundant** (see charter §13) — [result note](../notes/2026-09-05-BA-004-retention-audit.md). Audit is discriminating on all injected channels; budget reachable only under four named conditions. No live audit; consumes no holdout observation. | [BA-004.md](BA-004.md) |
| BA-005 | BTC-USD above its 200-day mean | Evaluation complete — **FAIL** on its own locked drawdown gate at every fee (see [round note](../notes/2026-09-08-a-hundredfold-asset-and-a-brake-on-it.md)); Coinbase question sized down into BA-006. | [BA-005.md](BA-005.md) |
| BA-006 | Sized Coinbase BTC sleeve | Pre-registered 2026-09-08, not run — awaiting the operator fee record its gates require. Consumes no BA-TREND observation. | [BA-006.md](BA-006.md) |
| BA-007 | Crypto Cross-Sectional Selection | **Evaluation complete — closed at the sealed reveal.** XS-MOM: FAIL on seen windows (2/6), sealed sessions never opened. XS-CARRY: after a dated engine-direction correction ([sweep note](../notes/2026-09-09-ba007-first-cross-sectional-sweep.md)), PASS 6/6 on seen windows — then **FAIL the sealed reveal 1/4** (2025-01→2026-09: +9.58%/yr [−44.91%, +63.25%], scrambled median +9.84% — the ranking carried no information). Program closed per §11. | [BA-007.md](BA-007.md) |
| BA-008 | Funding Momentum (XS-FMOM) | **Withdrawn 2026-09-09 before its first graded session** — its locked premise (long *high* funding) was inverted by the engine-direction defect corrected in the BA-007 sweep note; the registered BA-007 CARRY direction is the one that passed, and its test is BA-007's sealed reveal. Forward-only grading protocol (52/104-week bars) transfers to the paper book. | [BA-008.md](BA-008.md) |

BA-004 is not a member of the `BA-TREND` family. It holds no forecast, so it
neither consumes nor releases a sealed observation, and its evaluation cannot be
tuned by its own result because it has no signal parameter to tune.

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
