# What a model would have to be worth, and the benchmark that quietly flatters it

Measured 2026-09-07, round 51. Tool: [`required_edge.py`](../../tools/required_edge.py) (new). Tests: 15 in
[`test_required_edge.py`](../../tests/test_required_edge.py).

## The bar has a sample size, and it is doing most of the work

Every 10-year window in the archive, annualised, count attached per r50's rule:

| sleeve | windows | worst | q1 | median | q3 | best |
|---|---:|---:|---:|---:|---:|---:|
| **VOO** | **72** | **+11.08%** | +12.61% | **+13.36%** | +14.59% | +16.52% |
| SPY | 284 | **−3.45%** | +6.86% | **+8.79%** | +12.74% | +16.54% |
| QQQ | 210 | −8.06% | +10.42% | +13.15% | +18.47% | +22.88% |

**VOO has never had a losing decade in this archive.** Not "rarely" — its worst window is +11.08%/yr, because VOO's
whole history is 2010 onwards and the archive contains no lost decade for that ticker. SPY's same-length record has
four times the windows, a median 4.57pp lower, and a minimum below zero.

That asymmetry is not a curiosity, it *is* the objective's main risk: the objective names VOO and QQQ as the bar.
Take the concrete plan — **$50,000, withdraw $500/mo for 10 years, end with the principal whole**, which needs
exactly **+12.00%/yr**:

| conditioned on | windows below the requirement | the plan would have failed |
|---|---:|---:|
| VOO's own record | 6 of 72 | **8%** of the time |
| SPY's record | 197 of 284 | **69%** of the time |

Same plan, same arithmetic, same years of market history — an 8% failure rate or a 69% failure rate depending only
on which ticker's autobiography you read. Any statement of the form "the plan beats VOO" must carry the sentence
"…on VOO's record, which begins in 2010" or it is not a risk statement.

## The required edge, and what has actually been measured here

| capital | contributions | required return | vs VOO median | vs SPY median |
|---:|---:|---:|---:|---:|
| $20,000 | $0 | **+30.00%/yr** | +16.64pp | +21.21pp |
| $50,000 | $0 | +12.00%/yr | **−1.36pp** | +3.21pp |
| $100,000 | $0 | +6.00%/yr | −7.36pp | −2.79pp |
| $250,000 | $0 | +2.40%/yr | −10.96pp | −6.39pp |
| any of the above | +$500/mo | **0.00%** | −13.36pp | −8.79pp |

The largest net edge this repository has ever measured is **+1.63pp/yr** (constant 1.25× book, posted borrow, VOO
era) and the largest edge of any kind is the financing rate card at **+1.78pp**. Against those:

- **At $20,000 with no contributions the goal needs +16.64pp over VOO's median** — roughly ten times the best thing
  ever measured here, and it is not a modelling gap that better engineering closes.
- **At $50,000 the required 12.00% is *below* VOO's own median.** No model is required. The objective is already met
  by the index it was meant to beat — and the model's real job at that capital is not to add return, it is to not
  forfeit the guarantee for a worse one.
- **Contributions dominate everything.** Adding $500/mo of contributions to a plan withdrawing $500/mo makes the
  required return **exactly zero** — at every capital, provably: the balance never moves. This is the cheapest
  lever on the table by an order of magnitude, and it is the one finding in this round that is unambiguously good
  news for a small account.

## The two framings disagree by 3×, and the disagreement is the risk

With no contributions and a principal-preservation floor the recurrence has an exact fixed point — if the monthly
rate equals the monthly withdrawal rate the balance returns to its start every month — so **the required return is
exactly 12 × target ÷ capital, at every horizon from 5 to 30 years.** The bisection reproduces this closed form to
6 decimal places at four separate probes, which is the cheapest available proof that 80 bisection steps are solving
the right problem.

But that horizon-blindness is the trap. A required return is a **mean** statistic: length costs it nothing. Round 50
priced the same objective as a **path minimum** and got $592.97/mo per $100k at 10 years falling to $364.45 at 20.
Concretely, for $500/mo:

| framing | capital required |
|---|---:|
| capitalising VOO's median 10-year return (a mean) | **$44,910** |
| surviving the worst 20-year start in the record (a minimum) | **$137,215** |

**3.05× apart, same objective, same archive.** The difference is sequence risk, and it is why this repository prices
stances as minima. A plan spreadsheet that answers "you need 12%, VOO did 13.4%, you're fine" has answered the mean
question and skipped the one that can bankrupt you.

## Checks

15 tests, 0.6 s, offline: terminal wealth strictly increasing in the rate (bisection legality, pinned first); the
closed form verified to 1e-6 at four capital/target pairs across four horizons; the root round-tripping to the
starting capital at six grid corners; an impossible plan returning `None` rather than a big number; a $1m lump
returning exactly 0.60% with a *clearing* verdict (the tool is not rigged to say no); the benchmark's window count
travelling with its distribution; VOO's minimum staying positive and SPY's staying negative; and the two framings
staying >2.5× apart. Three of my own first-draft assertions failed on first run and were **restated because the
tool was more right than I was** — I had demanded a horizon slope in a configuration that provably has none, and a
negative required return where the exact answer is 0.60%. Full suite **1625 passed** (collected first: 1610 + 15).
`journalctl verify`: chain intact, comparator `100% SPY, fee 0.000945`, $0.00 paid in.
