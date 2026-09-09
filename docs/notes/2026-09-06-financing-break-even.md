# What the last mechanism standing actually costs (2026-09-06, round 11)

```
.venv/bin/python tools/financing_break_even.py            # 45 cells, ~6 seconds
.venv/bin/python -m pytest tests/test_financing_break_even.py -q
```

## Why this round exists

Ten rounds in, one mechanism has beaten plain DCA in the frame it was measured in, and it is not
a trading model: hold more of the index than you have money for. Round 4 measured it on SPY at
borrow = archive cash **+150 bps**, and nothing since has asked whether that number exists.

It was the most important unchecked thing in the repo, for a reason worth writing down: it is the
only load-bearing input in the whole project that comes from *outside* the archive. Prices,
expense ratios, and the cash index are all fetched and sealed. The borrow spread was typed in.

And the real number is not one number. US retail margin is posted and tiered, and the base tier —
the tier a $5,000 opening and $500 a month actually pays, since the discounts start at $25k-$100k
— spanned **4.90% to ~12.00%** across brokers in April 2026: [a comparison of the published
schedules](https://sidebysidebrokers.com/blog/margin-rates-2026-comparison.html) (a review site,
single source for most rows; [Interactive Brokers' own page](https://www.interactivebrokers.com/en/trading/margin-rates.php)
corroborates its end of it) puts Public at 4.90%, Robinhood Gold and Webull Premium at 5.75%,
IBKR Pro at 5.83% (a $1M+ tier, unreachable at this balance), Moomoo 6.80%, then Schwab 10.00%, E\*TRADE
10.45%, Fidelity 10.575%, Merrill ~11.13%, TradeStation ~11.50%, Ally ~11.75%, Firstrade 12.00%.

**710 basis points of dispersion on identical collateral under identical rules.** For scale: the
timing edge on the pre-registered candidate, measured across 33 years and four windows, is worth
$32 a month on this account. The broker's fee schedule is worth twenty times that, deterministically.

## The bill

`tools/financing_break_even.py` solves, for 5 sleeves × 3 windows × 3 leverages, what each desk
costs — priced at the desk's *posted* rate, not at a spread over a historical average, because
financing is a nominal cost. The archive's own cash index averaged 2.54% over the full record and
**3.81% over the last year**, so the two frames are not interchangeable and both are printed.

45 cells (5 sleeves × 3 windows × 3 levers), billed at each desk:

| desk | posted | median across cells | worst cell | positive in |
|---|---|---|---|---|
| Public | 4.90% | **+$206/mo** | +$45/mo | **45 of 45** |
| Robinhood Gold | 5.75% | +$175/mo | +$41/mo | 45 of 45 |
| IBKR Pro | 5.83% | +$172/mo | +$41/mo | 45 of 45 |
| Moomoo | 6.80% | +$137/mo | +$36/mo | 45 of 45 |
| Schwab | 10.00% | +$28/mo | −$219/mo | 35 of 45 |
| E\*TRADE | 10.45% | +$20/mo | −$246/mo | 31 of 45 |
| Fidelity | 10.57% | +$18/mo | −$253/mo | 31 of 45 |
| Firstrade | 12.00% | **−$12/mo** | −$322/mo | 19 of 45 |

Room before the gap closes — the break-even spread over each window's own cash, by bisection, every
cell converged to within ±$3 — is **500 to 1,309 bps, median 966**. Read that against the menu's own
spreads of 109 to 819 bps and the result is one sentence: **the room overlaps the menu.** The four
desks under ~7% sit inside the room everywhere and all 45 cells pay; the four at 10% and above sit
inside it in most cells, which is why 10 cells are already negative on Schwab's money and 26 on
Firstrade's. Only 5 of the 45 cells leave less room than the 710 bps that separates the cheapest
desk from the dearest. So the mechanism is not fragile to the borrow rate in the abstract — it is
fragile to *which* rate, and that is a decision about an account rather than a property of markets.

A few rows, full windows, at 2.0×:

| sleeve | DCA | levered ending | $/mo at 4.90% | $/mo at 10.575% | room | max DD | margin calls |
|---|---|---|---|---|---|---|---|
| SPY | $1,915,496 | $4,282,173 | +$447 | −$253 | 500 bps | −83.2% | 0 |
| QQQ | $2,010,738 | $7,262,745 | +$1,010 | +$11 | 864 bps | −92.1% | 0 |
| VTI | $945,436 | $2,204,698 | +$412 | −$169 | 647 bps | −80.9% | 0 |
| ITOT | $749,498 | $1,756,565 | +$454 | −$125 | 704 bps | −77.3% | 0 |
| VOO | $399,908 | $952,154 | +$511 | −$9 | 887 bps | −59.3% | 0 |

## What that means for the goal, said plainly

*(Two rounds later this paragraph has an artifact attached to it:
[the monthly ticket](2026-09-06-monthly-ticket.md) turns the bill below into an order sheet with a refusal
path, and restates the +$142/month at the size an account actually starts at — $23.)*

- **The only thing in this repo that reliably beats VOO, QQQ, VTI and ITOT on monthly dollars is
  the amount you pay to borrow.** It is not a bot. It has no signal, no trend read, no news, no
  regime detection, nothing to run at 9pm on a Sunday. It is a margin loan and a brokerage
  account, and switching brokers is worth more than every model this project has built.
- **The price is the drawdown, and it is not small.** −63% at 1.25×, −83% on SPY and **−92% on
  QQQ** at 2.0×, versus −53% and −58% unlevered. Zero margin calls at 2×: the account is not
  liquidated, it is *forced to sell on the way down by its own rebalancing rule*, several hundred
  times, which is why the drawdown is deeper than the liquidation it avoids.
- **So the real question for round 12 is not "what signal beats DCA" but "what rule on top of the
  leverage keeps the premium and gives back less of the drawdown"** — the same levered sleeve with
  the leverage itself vol-targeted, billed at the cheap desk. The candidate's gate halved
  drawdown in round 10 while losing money; mounted on 1.5× instead of 1.0× it may do both. That
  is the first experiment in eleven rounds whose *starting point* beats the index.

## What was checked on the way

Four things in this tool could have lied, and each was made to confess:

- **the solver's band.** Solving the break-even under the engine's 10% band while billing under a
  1% one produced a break-even **40-65 bps too generous** — a lie in the flattering direction, by
  two individually reasonable lines. The residual test caught it; the solver and the verdict now
  price the same mandate.
- **the terminal is step-discontinuous in the spread.** The spread moves the account along a
  path, and the path flips whole trade decisions where it crosses the band boundary. Measured at
  1.25× on the wide band: move the borrow spread by **one tenth of a basis point** and the gap to
  DCA moves from +$17,018 to −$2,578 — a $19,596 jump, and $24,109 at 2.0× on the same sleeve.
  The break-even point exists but the function does not cross zero there, it leaps over it. So
  every break-even is printed with the residual it actually achieved (`619 bps ±$1`, and ±$1 only
  because the solver now runs at the tight band) rather than four decimals of false precision.
- **`at_rate` can charge the cash rate twice**, which is what the obvious implementation does —
  pass the posted rate straight through as the spread. That overstates every desk by 150-400 bps,
  most of the margin being measured. The first test written for it survived that mutation, because
  it only asserted the bill was negative; the invariant that kills it is *a desk charging exactly
  the cash rate must cost the same as a book financed spread-free*.
- **the maintenance guard**, which disqualifies high leverage in round 4's table, fires 25 times at
  3× on SPY and never at 2×. Round 10's rule: a zero is only evidence if the guard could have made
  it non-zero.

The band column is honest in both directions and shouldn't be read as a cost: at 1.25× the band is
wider than the monthly deposit and the wedge is **+$125,757** in favour of dropping it; at 2.0× on
QQQ the band also suppresses the forced sell-back-to-target through a V-shaped collapse, and the
wedge is **−$525,837**, i.e. the band paid.

## Caveats that are not in the code

The menu is one review site's April 2026 snapshot of eight brokers' published base tiers, with
IBKR's own page corroborating IBKR. Base tiers move with the Fed and with broker whims, and this
repo's convention — $5,000 opened, $500 a month — sits under every tier discount. The tool prints
*room* precisely so the menu can be swapped without re-solving anything. Nothing here is a
recommendation to borrow: at 2× on QQQ, the drawdown is a −92% event on the account, and the
mechanism's edge on the same sleeve over the last four years is $219 a month.

## Rule this round adds

**Charge the borrowed money at what money actually costs.** Every input in this repo is fetched
and sealed except the one the whole surviving mechanism depends on, which was typed in — and the
world's answer for it spans 710 bps, more than every timing edge ever measured here combined.
Where a number comes from outside the archive, print the outside answer next to yours, and print
the decision the difference leaves.
