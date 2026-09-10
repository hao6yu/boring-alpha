# BA-012 Stage A sizing implementation interpretation

This note documents `tools/ba012_sizing.py`; it does not amend the frozen
BA-012 version 1 protocol (SHA-256
`095fa832c82645a6f570668813b59b08afa4a21c93466980703ff78c46eec67f`).
Every input decision is independently funded from cash at $5,000, $25,000,
or $100,000, with the frozen 20% simulated loss budget and $100 operating
buffer. No strategy returns, equity path, or performance verdict are computed.

## Entry costs and partial fills

The continuous target and tracking objective use the initial decision equity
E. If an arbitrary quantity subset z has filled, its incurred stressed entry
cost is C(z), its equity is E−C(z), and its drawdown from starting equity is
C(z). Its volatility cap therefore is 0.08×(E−C(z)), rather than the unchanged
pre-entry target. Its loss-budget charge is C(z)+L(z)+X(z). Its funding check
is E−C(z)−L(z)−X(z) against twice the side-specific margin plus $100. Paid
entry cost is counted once; closing reserve is distinct from paid cost.

All empty/full sleeve vertices of the planned quantity box are checked for
`sqrt(z′Σz)+0.08 C(z) <= 0.08 E`. A positive-semidefinite covariance makes
this a convex function, so these vertices cover every intermediate integer
fill quantity and order. Stress and funding charges have positive additive
coefficients, so their maximum is the completed basket. The pinned initial
margin exceeds maintenance in every sleeve/side, making its funding test
sufficient for both. Terminal diversification and concentration are not
applied to the first fill. This calculation includes entry costs, but does
not invent intervening market prices or establish an intraday loss bound.

## Arithmetic and optimization

Input movement values are converted to finite float64; no timestamp,
contract-selection, or causal-sign audit is inferred from numeric validity.
Money comparisons use exact integer units of $0.0001. Sample covariance uses
the complete 252-row window, demeaned with denominator 251, then the frozen
50% diagonal shrink and 252 annualization.

Volatility-normalized risk and concentration comparisons allow 1e-12 for
floating roundoff. Objective ties use Python float rounding to 12 decimal
places (ties to even), then exact money cost, exact stipulated price stress,
then lexicographic absolute quantities. The branch-and-bound search uses
optimistic continuous Schur-complement minima;
its pruning threshold includes 1e-10 outward padding. Verification is with
respect to these disclosed floating-point comparisons, not a formal
interval-arithmetic certificate.

The finite search is bounded by stress, side-specific funding and the
cost-adjusted single-sleeve risk cap. `OPTIMAL` means it completed a global
search/proof under those rules. `SEARCH_LIMIT` means unresolved and returns
null selected quantities; an incumbent is diagnostic only. Objective
pruning does not enumerate every feasible basket. Consequently cash optimality
does not by itself prove that no feasible nonzero basket exists; the separate
`nonzero_feasibility` field distinguishes a witness, an infeasibility proof,
and an unresolved feasibility question.

## Scope of margin and execution

The September 10 pinned broker margins are a contemporary stress proxy
without offsets. They are not reconstructed historical margin, account
permission, or a present executable margin quote. Prelaunch child exposure
translated through parent contracts remains hypothetical. Actual-child
spread, size, permission, timestamped margin, and fill audits remain separate
requirements. An 8% forecast cap and the stipulated stress budget are not
probabilistic guarantees of a maximum loss.

## Stage A runner

`tools/run_ba012_stage_a.py` takes a prepared input report, its explicit
SHA-256, the dated mapping file, and a new output directory. It verifies the
frozen design, exact 72 scheduled month-end cases, each complete 252-interval
window, and the input/mapping hashes before sizing. It never reopens raw
price archives. Each READY case is evaluated at all three registered capitals.
DATA_INCOMPLETE cases are skipped; invalid risk estimates and SEARCH_LIMIT
results remain unresolved, with null selected quantities.

The runner saves one file per decision date and a summary containing their
hashes, input/design/source hashes, Python executable/version, and the actual
installed NumPy file manifest/version. These record the current execution
environment; they are not a complete operating-system lockfile. A complete
cash rejection requires 72 complete, verified cash optima at that capital.
Partial nonzero observations count as participation evidence within an
incomplete study. No runner verdict is a performance or funded-approval pass.
