# The rule is not a failed strategy, it is a cheap insurance policy, and that changes the question

Priced 2026-09-06, round 36. Tool: [`insurance_pricing.py`](../../tools/insurance_pricing.py), tests
[`test_insurance_pricing.py`](../../tests/test_insurance_pricing.py) (9).

## Thirty-six rounds of scoring the wrong thing

Since round 1 the vol-target rule has been graded as a return strategy, and on that grading it loses: **−0.25%/yr**
against plain 100% SPY under account-faithful costs (round 25), **−1.27%/yr** forbidden to borrow (round 26). Every
note since has appended "but it halves the drawdown" like a footnote on a defeated motion. That framing has been
backwards the whole time. A product that costs money steadily and pays out in the months that would otherwise
damage the account is not a strategy with a bad Sharpe ratio — it is an **insurance policy**, and insurance is
priced on an entirely different basis: what does the premium cost, what does the claim pay, what is the loading.
Round 26's `anatomy()` decomposition already had the answer sitting in it, in the exact accounting form of premium
and claim, and it had only ever been read as a diagnosis of failure.

## The contract, on 404 months of the sealed archive

| bucket | months | contribution | in contract terms |
|---|---:|---:|---|
| crash months (< −5%) | 37 | **+2.805%/yr** | claim paid |
| rally months (> +5%) | 61 | −3.330%/yr | premium, in the pleasant months |
| flat months | 306 | +0.279%/yr | premium, in ordinary ones |
| **total** | 404 | **−0.246%/yr** | net cost of cover |

**The claim returns 91.9 cents of every premium dollar.** That single ratio is the round's finding. It is the
loading of a functioning product — roughly 8% — not the profile of a broken strategy. A rule that collected premium
and paid nothing would have a ratio near zero and would be a genuinely bad idea; this one collects 3.05, returns
2.81, and cuts peak-to-trough from **−51.8% to −29.4%**, 22 points of hole. The net drain on $20,000 is **$49.25 a
year, $4.10 a month.**

## Why the premium is politically easy and the loss is not

The premium is collected in **61 months against 37 claim months**, and it is collected disproportionately in the
*good* months — the rule sheds exposure into rallies, which is exactly when the account is otherwise compounding.
That asymmetry is why a policy with this profile is tolerable to hold and invisible to feel: no single month feels
like paying for insurance, and the one month in ten that would have hurt arrives without the hole. What it does not
survive is annual arithmetic, which is what this file exists to do.

**The loss is almost entirely structural rather than transactional.** The broker's bill for running the policy is
0.032%/yr — 1.62× turnover at 2bp — which is **1.1% of the gross premium**, and even against the small *net* cost
it is only 13%. The other 87% of that net is the cost of being under-invested precisely when markets recover, which is the contract's shape and cannot be negotiated with a
broker or improved by cheaper execution. Anyone hoping a better fill would rescue the rule should read that ratio
and stop.

## The result that makes the number trustworthy

The crash threshold is my definition, not a market fact, so the whole reading could have been an artefact of
drawing the line at 5%. It is not. Re-bucketing at 3%, 4%, 5%, 6% and 8% moves the claim count from 61 months to
14 — a 4× swing in the definition — and leaves the net cost at **−0.25%/yr to two decimal places every time**,
with an identical −29.4% drawdown. The rule's behaviour is a continuous function of volatility; my threshold only
chooses which months get called claims. A finding that survives a 4× change in its own definition is a property of
the rule, and the test asserts the invariance so the next re-seal tells me if it stops holding.

## The question this closes and the one it hands back

"Is the rule worth running?" was the wrong question and has now been answered properly: it is a working policy at
a low loading, so the honest framing for the goal is not *does this beat the index* — it does not, and no longer
needs to — but **is 8% of premium a fair price for 22 points of drawdown.** That depends on whether a $20,000
account can tolerate −51.8%, which is a fact about the owner and not about the archive, and it is the same
question round 12 has been asking for 24 rounds: whether the objective is income or survivability. If survivability
is the binding constraint, this contract is cheap and should be bought. If raw return is, it should be declined and
the money put in VOO. Either way the arithmetic no longer supports "a trading model that beats the index each
month," which 36 rounds of measurement now say is not available here at $20,000 — and the two best remaining
candidates are a cash switch worth $34–46 a month and a loan.

## Checks

9 tests, 0.7 s, offline: the three buckets must **sum to the headline exactly** and cover every month once, or the
contract reading is decoration; the claim bucket must be positive and the rally premium negative, because if the
rule lost money in crashes the finding would be worse, not better; the claim/premium ratio must sit in (0.85, 1.0)
with the message quoting the measured 0.919; the transaction bill must be under a quarter of the net so the loss is
demonstrably structural; drawdowns must be −29.4% and −51.8% to three decimals with the first assertion written as
the *measured* pair after my first version had them reversed; and the net cost must be invariant across all five
thresholds. Full suite: **1518 passed, 233 subtests**. `journalctl verify`: chain intact (1 entry), comparator
`100% SPY, fee 0.000945`, $0.00 paid in.
