# BA-002 source sensitivity — practical no-go

Date: 2026-09-05. **Both sources fail the existing economic requirements.**
Recommendation: do not fund or spend the holdout on BA-002 as currently defined.
This is a completed, separately authorized **non-gating diagnostic**, not a
formal `classify` verdict, live-trading result, or new independent validation.

The [protocol](../decisions/2026-09-05-ba002-source-sensitivity.md) was recorded
before performance computation. It held the 9/12/15 rule, all five grid rows,
eight ETFs, $100,000 capital, 10/20-bps paired costs, annual 60%-invested
benchmark, eight stylized tax scenarios and both seen windows fixed.

## The result that matters

CAGR below is **annualized, after modeled tax and final liquidation**, not a
weekly target. Ranges span the eight fixed tax scenarios. Drawdown is the
**pre-tax, cost-net** peak-to-trough magnitude required by the existing charter.
The conservative margin is worst strategy CAGR minus best benchmark CAGR;
the base rule needed **at least +50 bps/year**.

| Seen window / source | Strategy after-tax CAGR range | Benchmark after-tax CAGR range | Conservative margin, bps/year | Strategy drawdown | Benchmark drawdown |
|---|---:|---:|---:|---:|---:|
| 2007-06–2017 / corrected Yahoo | 2.89–2.99% | 2.87–2.92% | −3.69 | 9.93% | 20.50% |
| 2007-06–2017 / Tiingo | 2.82–2.92% | 2.86–2.92% | −9.78 | 9.94% | 20.50% |
| 2018–2021 / corrected Yahoo | 2.00–2.03% | 4.16–4.21% | −221.07 | 13.70% | 12.18% |
| 2018–2021 / Tiingo | 2.00–2.03% | 4.16–4.21% | −220.95 | 13.70% | 12.18% |

The development drawdown reduction is real in these simulations: roughly 10%
versus 20.5%. It does not bring the required after-tax return advantage. In
seen B the base strategy both earns less and has a worse drawdown than its
paired benchmark, although its absolute drawdown remains below 20%.

This conclusion does **not** depend on comparing different tax scenarios:
within each identical scenario, the base strategy trails its benchmark in
seen B by approximately **2.16–2.18 percentage points/year**, under both feeds.
Nor is it only a tax-overlay result. Pre-tax, cost-net base CAGR in seen B is
approximately **2.70% versus 5.45%** for the benchmark under both feeds.

For context, the base strategy's worst drawdown in seen B runs from its
2018-01-26 high-water mark to 2020-03-18; the benchmark's corresponding maximum
runs from 2020-02-19 to 2020-03-18. These are each account's own maximum
drawdowns, not an artificially chosen common peak. This experiment does not
decompose the return gap into individual signal-timing, cost and tax causes.

## Full fixed grid — no selected winner

All values below are conservative after-tax margins in **bps/year**. The base
requires ≥50; each stress row requires >0. Each row also needs strategy
drawdown ≤20% and no worse than its cost-matched benchmark.

| Row | Seen A Yahoo | Seen A Tiingo | Seen B Yahoo | Seen B Tiingo |
|---|---:|---:|---:|---:|
| Base 9/12/15 | −3.69 | −9.78 | −221.07 | −220.95 |
| Double cost | −14.35 | −20.37 | −233.17 | −233.04 |
| Without 9 | +15.65 | +6.61 | −201.54 | −201.39 |
| Without 12 | −37.61 | −43.53 | −260.43 | −260.30 |
| Without 15 | +12.00 | +8.32 | −203.16 | −203.06 |

Every strategy row meets the absolute 20% drawdown ceiling. All development
rows also beat their paired benchmark's drawdown. In seen B, only the
without-9 row meets the relative drawdown requirement; **every row fails the
return requirement under both feeds**. No row clears both periods. No horizon,
cost, tax scenario, threshold or date was changed after the results appeared.

Changing the source moves the base conservative margin by about **6.08 bps/year
in seen A** and **0.13 bps/year in seen B**. The development numbers are
source-sensitive at the small-edge level, and neither feed is certified ground
truth. The practical no-go conclusion is nevertheless unchanged in every row
and window comparison. There is no empirical reason in this experiment to
pick a favorable vendor and continue to the holdout.

Do not overstate that agreement: the tiny development **matched-scenario**
base margins are all slightly positive with corrected Yahoo, but mixed in
sign with Tiingo. Failure of the 50-bps requirement is stable; the sign of a
near-zero estimated edge is not. After the TLT repair, archived base decisions
still differ in three of 3,048 development horizon votes and zero of 1,152
seen-B votes. Benchmark decisions are identical across sources.

## Inputs and evidence

The [preflight](BA-002-preflight.md) found a genuinely missing TLT distribution
in Yahoo. Its issuer-supported repair and the independent Tiingo normalization
were completed in **new snapshots**. Both contain only 2006-02-28–2021-12-31,
including warmup, and share the identical bounded DGS3MO cash input. Original
Yahoo/BA-001 files and `data/current` were not replaced.

The correction inserts one dividend and adjusts 1,682 preceding TLT
total-return-price rows under Yahoo's previous-close multiplier convention.
It does not alter raw prices, other symbols, or ex-date/later adjusted prices.
The exact sources, manifests and formula are recorded in the protocol and
snapshot manifests. No historical API request or credential access was needed
for this experiment; it used the existing local captures.

| Case | Case ID | Local artifact directory |
|---|---|---|
| Yahoo / seen A | `70f53fc6c41ba3bf` | [yahoo-development](../../experiments/BA-002/source-sensitivity/20260905/yahoo-development/manifest.json) |
| Tiingo / seen A | `b28b37f07b12bf49` | [tiingo-development](../../experiments/BA-002/source-sensitivity/20260905/tiingo-development/manifest.json) |
| Yahoo / seen B | `1b04ebacd1612888` | [yahoo-validation](../../experiments/BA-002/source-sensitivity/20260905/yahoo-validation/manifest.json) |
| Tiingo / seen B | `4a6715f2babebd78` | [tiingo-validation](../../experiments/BA-002/source-sensitivity/20260905/tiingo-validation/manifest.json) |

All four cases completed: **40 accounts and 320 tax-overlay evaluations**.
Every account was reconstructed from its archived fills/equity, independently
reconciled against archived prices, checked against the exchange calendar, and
then scored under every tax scenario. All three required tax-identity flags
passed for every scenario. There were no quality or strategy warnings.

Each case preserves deterministic compressed inputs, source/correction
manifests, effective-rule metadata, all decisions, orders, fills and equity
curves, full tax records, account maps, the prior protocol, and source code.
There are 71 checksummed payloads per Yahoo case and 70 per Tiingo case; each
completion manifest was published last. Licensed raw and row-level evidence
remains local and Git-ignored, not redistributed in the public repository.

Independent result verification checked all **282 payload hashes**, recomputed
every row's tax envelope directly from archived scenario records, and rebuilt
drawdowns from equity curves without using the runner's summary function.
All 320 reported after-tax CAGRs also reproduce from archived post-liquidation
wealth. Rule, policy, code, calendar and protocol identities agree across all
four cases, and cash bytes agree across sources within each window.

Final full repository test run:
**`1044 passed, 220 subtests passed in 120.78s`**. This is one observed pytest
execution count, not a claim about distinct declared test methods. The new
snapshot and runner tests include fictional boundary/identity failures and
discriminating return-envelope, split and missing-dividend fixtures.

Shared identities:

- Rule: `974c1dd5b9eae726ded1d25abb202c138d58f78e150b617c92ed85a4a0a23ba7`.
- Tax policy: `9abb91e20b43a0d18a9e8404439145f13e5cf338d4eed4fd7363293146f54542`.
- Runtime code: `a63a77df3adb569a6048336fdba40c775013fcd80fac3ad6a55002b09ea7dbb8`.
- Evaluator: `0bc4655d3d60667ed03a53403b739a5d6fdd49e13205826149b430b1b69d1b8d`.
- Protocol: `7a44ff88d094ddf832ad4702c69e8faac9570bf08d4722c56a2320580ec5de59`.

The exact runtime tar archive and all five driver/conversion/helper scripts
are included with each case. The reference config's old v2 data/freeze paths
are explicitly **not** the current input identity; the actual feed, methodology
and checksums are recorded separately. The artifacts deliberately have a
distinct diagnostic kind and no formal schema-7 classification envelope.

## Reproduction and stopping point

The [builder](../../tools/build_ba002_source_snapshots.py) is offline and refuses
changed original inputs or existing output directories. The
[runner](../../tools/run_ba002_source_sensitivity.py) accepts only the two seen
periods and two declared source methodologies. A reproduction uses a new output
path, for example:

```sh
.venv/bin/python -m tools.run_ba002_source_sensitivity \
  --snapshot data/snapshots/ba002-yahoo-corrected-seen-20260905-v1 \
  --period development \
  --output experiments/BA-002/source-sensitivity/reproduction/yahoo-development
```

Repeat with the validation period and Tiingo snapshot to reproduce the full
comparison. Do not pass these diagnostics to `classify` or relabel them as
formal evidence. The original freeze remains draft, no family journal was
initialized, and no formal sweep or holdout evaluation occurred. No protected
observations on or after 2022-01-01 were numerically loaded.

The practical next step is to **retire this candidate as currently designed**,
retain the results, and reserve the holdout for a separately justified hypothesis.
Do not tune the losing ensemble into another apparent winner in these same
seen windows. This result rejects neither all trend strategies nor the value
of the lab; it says this particular taxable ETF rule has not earned deployment.
