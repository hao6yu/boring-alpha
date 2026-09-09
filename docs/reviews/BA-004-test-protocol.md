# BA-004 — Pre-registered test protocol

Status: **pinned before computation.** Written 2026-09-05. Every assumption,
budget, scenario and gate in this document was fixed before any BA-004 number
was computed, and the file is hashed at the foot. A number that contradicts a
prediction here is reported as a contradiction, not reconciled.

Per the [registry revision policy](../strategies/README.md), synthetic runs do
not count as a historical run. Two scenarios below use archived real prices and
are therefore recorded as BA-004's first historical run. That run is permitted
and harmless for a reason worth stating: BA-004 has no signal parameter, so
there is nothing for a historical result to tune. The only quantities a result
could influence are the budgets, and those are pinned above.

## 1. What "works" means, fixed in advance

BA-004 is a retention audit, so it passes or fails on two independent axes.
Both must be reported and neither may substitute for the other.

**Axis A — is the declared budget reachable?** Running the registered policy
with honest, declared, non-adversarial assumptions, does the Tier-2 shortfall
stay within 30 bps/year?

**Axis B — is the audit discriminating?** Can the ledger that reports Axis A
detect and correctly attribute leakage planted at known magnitudes? A ledger
that reports "within budget" but cannot find a deliberate 35-bps fee is not
reporting within budget, it is blind. **Axis B outranks Axis A.** A passing
number from a blind instrument is the exact failure this repository exists to
catch, and BA-001 through BA-003 all died of variants of it.

Verdict vocabulary, fixed in advance:

| Verdict | Condition |
|---|---|
| **Works** | A passes in every declared regime, B passes on all six channels, scale behaviour as predicted |
| **Works, conditionally** | B passes; A passes only under a named subset of declared assumptions. The binding channel and the binding assumption are named |
| **Does not work** | B fails on any channel, or A fails in every declared regime |
| **Inconclusive** | Reserved for a broken instrument or failed identity check, i.e. evidence that the measurement is invalid — not a soft verdict on the strategy |

**What no verdict in this document may claim.** No verdict forecasts a market
return. No verdict means the account has been audited: that requires live fills
and real published NAV data over the charter's three-year window and remains
future work. No verdict endorses holding the instrument chosen in §3, per the
charter's own limitation that retention says nothing about whether the thing
retained is right.

## 2. Pinned assumptions

Declared for the test, and explicitly flagged as placeholders for the holder's
real §12 answers. Changing one after seeing a result creates BA-004B.

| # | Assumption | Pinned value |
|---|---|---|
| A1 | Account opening value | $2,000 |
| A2 | Monthly contribution | $500, deposited same day as purchase unless a latency scenario says otherwise |
| A3 | Horizon | 10 years, monthly |
| A4 | Fund gross index return | Two synthetic regimes from `data/synthetic.py` (`trending`, `random_walk`) plus two archived real windows (seen A 2007-06→2017-12, seen B 2018-01→2021-12) |
| A5 | Fund expense ratio, candidate | 7.0 bps |
| A6 | Fund expense ratio, expensive comparator | 42.0 bps |
| A7 | Cash vehicle return | 4.0% annualised |
| A8 | Realised spread, limit-order policy | 3.0 bps per side |
| A9 | Realised spread, market-order-at-open policy | 12.0 bps per side |
| A10 | Declared maximum idle cash | 3.0% of account value |
| A11 | Contribution latency, clean case | 0 days |
| A12 | Contribution latency, late case | 10 days |
| A13 | Platform fee, eligible vehicle | $0 |
| A14 | Platform fee, fixed-dollar scenario | $10 per month |
| A15 | Gate: Tier-2 shortfall | ≤ 30.0 bps per year, money-weighted |
| A16 | Gate: violations | exactly 0 |

A5/A6 are test inputs, not claims about any real fund. The holder must pin real
published figures before the charter's live audit; a placeholder fee must never
survive into a real report.

## 3. Ex-ante predictions, written down so being wrong is informative

Predicted before any run, from arithmetic only. The point of writing these is
that if the ledger disagrees, the ledger is wrong first until proven otherwise.

**P1 — the dominant channel will be idle cash, by a wide margin.** Cash drag is
`w_cash × (r_equity − r_cash)`. At the A10 ceiling of 3% with a 5-point
equity-cash gap, that is 15 bps/year — half the A15 gate from one channel.
Prediction: cash contributes roughly 0 to 15 bps and is the only channel capable
of binding the gate on its own.

**P2 — spread cost will shrink as the account grows.** Spread drag is
`bps_per_side × traded_notional / average_value`. Contribution notional is fixed
while value compounds, so a 3 bps-per-side policy costing roughly 3.6 bps in
year one should cost well under 1 bps by year ten. Prediction: year 1 > 3 bps,
year 10 < 1 bps, monotone decline.

**P3 — the clean run lands near 16–20 bps, not near 30.** Fee excluded by tier
definition, plus roughly 1–4 spread, plus roughly 0–15 cash, plus under 1 latency.
Prediction: within budget with genuine headroom, and **the headroom is cash
discipline, not cleverness.**

**P4 — the expensive comparator fails the gate on its own.** A 42 bps fund
versus a 7 bps fund is a 35 bps Tier-1-to-Tier-2 gap against a 30 bps total
gate: an instrument choice can single-handedly defeat the entire strategy before
a single order is placed. Prediction: A6 scenario fails, attributed to the
instrument channel.

**P5 — retention is return-regime independent, and that is the whole appeal.**
Cash drag is the only term that depends on the equity-cash return gap; every
other term is a fee, a spread or a day count. Prediction: ordering of channels
holds across `trending`, `random_walk`, seen A and seen B, even where the level
moves with the gap. A strategy whose failure mode is the same in a flat decade
and a crashing one is worth more than a signal that only works in one.

**P6 — a fixed-dollar fee is not scale-invariant and must break the gate at real
scale.** $10/month on roughly $5,000 average value is about 24 bps; the same fee
on roughly $50,000 is about 2.4 bps. Prediction: A14 fails the gate at A1 scale
and passes at 10x, which is the arithmetic reason a $2,000 account cannot afford
what a $50,000 account treats as free.

## 4. Declared scenario grid

Fixed now. No scenario may be added after results are seen. The two cost rows
are stress rows, not candidates to select a winner from.

| Scenario | Change from clean policy | Predicted Tier-2 shortfall |
|---|---|---:|
| S-CLEAN | A8 spreads, 0 idle cash, 0 latency, $0 fee | ≤ 5 bps |
| S-CASH-1 | clean, but 1% idle cash | ≤ 6 bps |
| S-CASH-3 | clean, but 3% idle cash, at the A10 ceiling | ≤ 20 bps |
| S-CASH-8 | clean, but 8% idle cash — an undeclared breach of A10 | ≥ 35 bps, fail |
| S-MARKET-ORDER | A9 instead of A8, 0 idle cash | ≤ 12 bps |
| S-LATE-10 | A12 instead of A11, 0 idle cash | ≤ 6 bps |
| S-FIXED-FEE | A14 instead of A13, 0 idle cash | ≈ 24 bps at 1x, fail; pass at 10x |
| S-BEHAVIOUR-1 | clean plus one registered violation during a declared blackout | void, violation count 1 |
| S-EXPENSIVE-FUND | A6 instead of A5, 0 idle cash | fails at Tier 1, never reaches Tier 2 |

Run at 1x scale (A1/A2) for every scenario and at 10x scale ($20,000 opening,
$5,000 monthly) for S-CLEAN, S-CASH-3, S-FIXED-FEE and S-EXPENSIVE-FUND.

## 5. Injection battery — Axis B, the axis that outranks the other

Each channel is injected singly into an otherwise clean run, at a magnitude
declared here, with a required attribution. A channel is **detected** if the
reported shortfall rises by at least 80% of the planted magnitude, and
**attributed** if the ledger names the planted channel as the largest contributor
rather than smearing the loss into a residual or an unlabelled line. A catch-all
bucket exceeding 10% of planted bps is an attribution failure even if the total
is right, because a total without a name cannot be acted on.

| Channel injected | Planted magnitude | Must be detected as |
|---|---:|---|
| Idle cash, 8% | ≈ 40 bps/yr | cash drag |
| Market orders at the open | ≈ 9 bps/yr uplift over A8 in early years | spread / execution |
| Contribution latency 10 days | its own small arithmetic value, exactly | latency |
| Platform fee $10/month | ≈ 24 bps/yr at 1x | platform fee |
| Fund fee 42 bps | 35 bps at Tier 1 | instrument selection, and must **not** appear inside the Tier-2 total |
| One behavioural violation | not a bps figure | violation count 1, return voided as evidence |

The fee row is the strictest check in the battery: it must be caught at Tier 1
and kept **out** of the Tier-2 total. A ledger that mixes a wrapper fee into a
behaviour score has destroyed the distinction on which BA-004's whole
attribution argument rests.

## 6. Measurement mechanics, pinned

- **Primary metric: money-weighted annualised return (XIRR)** on the actual
  dated cash-flow series, because A1/A2 make the account's outcome dominated by
  contributions rather than by markets. Time-weighted CAGR is reported beside it,
  labelled, and never compared against a BA-001/002/003 figure: those describe a
  self-financing lump sum and this describes a funded account. Reporting the
  wrong one here is a defect, not a rounding choice.
- **Cross-check: Modified Dietz**, on the *shortfall* rather than the level. This
  replaces an original pin requiring the two metrics' **levels** to agree inside
  15 bps/year, which a unit test disproved on the first try: twelve monthly
  contributions in a rising year put roughly 70 bps between a linear and a
  multiplicative annualisation, and no amount of correctness closes that gap.
  Level agreement was the wrong requirement. What must agree is the audited
  difference, because both accounts carry identical cash flows and the
  approximation error is common-mode.
  The bound is then **5% of the reported shortfall, and 20 bps absolute**,
  whichever binds first. Measured over 286 distinct policy combinations before
  any scenario was run: worst absolute error 19.69 bps, worst relative error
  4.19%, with the ratio essentially flat. The error is therefore **proportional
  to the leakage**, which a flat tolerance could not have described honestly in
  either direction — a flat 5 bps would have failed every heavily-leaked run for
  the wrong reason and passed a lightly-leaked one too easily.
  Two consequences follow, stated now rather than discovered later.
  **First**, the audit cannot distinguish a shortfall below roughly 3 bps/year
  from zero; a result in that band is reported as "indistinguishable from zero by
  this instrument", never as a pass and never as a win. **Second**, at a shortfall
  near the 30 bps gate the cross-check error is around 1–2 bps, so the gate
  decision is not a coin toss but is also not a precision instrument: a result of
  30.0 bps and a result of 28.5 bps are the same finding, and the report must say
  which side of the gate it is on without pretending to more resolution than
  4.19% supports.
- **Shortfall** = reference IRR minus candidate IRR, both carrying identical cash
  flows, so leakage is the only difference by construction. This is an identity
  check, not an inference: no distribution, no sampling, no regime assumption,
  and therefore no honest route to Inconclusive.
- **Attribution must sum to the total** within 1 bps/year. If it does not, the
  ledger has an unlabelled leak and Axis B fails on that run.
- Determinism: same inputs, same hash, same output. Violations append, never
  edit. Any run that fails an identity check is evidence of an invalid
  instrument, not a strategy result.

## 7. Reporting

One note in `docs/notes/`, containing: the grid with predicted-versus-actual
side by side, the battery table with detect/attribute pass-fail per channel, the
binding channel named, the binding assumption named, the scale comparison, and a
verdict drawn from §1 and nothing else. The registry row is updated to point at
it. Then BA-004 stops, and the live three-year audit in the charter's §10 stays
as future work rather than being quietly folded into this conclusion.

---

Pinned at 2026-09-05 before computation. SHA-256 as finally pinned (pin 3):

    da3f81f55a1e5694c380b820eadaf390a163549a058c947628cf411de346a279

## Change log

- 2026-09-05 (pin 1) — initial protocol, all assumptions and gates as written.
  SHA-256 `5e1fa056d2cf0e5aecb763d805826b5babaa8e95d619f3d8742b2cd4e628c12c`.
- 2026-09-05 (pin 2) — §6 cross-check rule amended before any BA-004 result
  existed, for the reason stated in §6: the level-agreement tolerance was wrong
  and was replaced by a difference-agreement requirement. The 5 bps figure and
  the 3 bps measurement floor come from a unit-test fixture on the two return
  formulas, **not** from any scenario output; none existed at the time and none
  was consulted. This is the only amendment permitted before the first run;
  further edits after results would create BA-004B.

- 2026-09-05 (pin 3) — §6 cross-check bound restated as proportional (5% of the
  reported shortfall, 20 bps absolute) after measuring 286 policy combinations:
  worst absolute error 19.69 bps, worst relative 4.19%, ratio essentially flat.
  A flat tolerance could not have described that honestly in either direction.
  Still no scenario result. Scenario grid ran after this pin.
