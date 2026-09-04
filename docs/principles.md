# Research principles

## 1. Pre-register the hypothesis

Write the economic story, universe, timestamps, parameters, benchmarks, costs,
and rejection conditions before revealing the final test period. Record every
attempt, including failures.

## 2. Information must travel forward in time

A signal may use only information observable at its timestamp. A month-end
close signal cannot fill at that same close. BA-001 executes at the following
session's open.

## 3. Separate data, signal, portfolio, and execution

The signal expresses a view. The portfolio layer converts views into target
weights. The execution layer converts targets into trades and costs. Backtest,
paper, and live modes must share the first three layers.

## 4. Model frictions before celebrating

Include spread, slippage, fees, taxes when the account is taxable, cash
returns, unavailable assets, missing data, and realistic execution timing.
Paper fills are evidence about plumbing, not proof of achievable live
performance.

## 5. Prefer stability to the best historical score

A plausible edge should survive nearby parameter values, different periods,
higher costs, and the removal of its best trade or asset. Complexity must earn
its place against a simpler baseline.

## 6. Make results reproducible and immutable

Every run records its configuration hash, data hash, code-facing inputs,
decisions, trades, equity curve, metrics, and warnings. Existing results are
never silently replaced.

## 7. Risk constraints outrank return targets

The system may choose zero exposure. No weekly return is required. Leverage,
shorting, options, and autonomous live execution remain prohibited until they
receive separate charters and controls.
