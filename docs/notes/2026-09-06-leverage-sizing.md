# Leverage sizing: what the only surviving mechanism actually costs, per month

Date: 2026-09-06 · Round 4 of the trading-model goal · tool: `tools/leverage_sizing.py`
Status: **measurement and instrument choice.** Not a recommendation to borrow.

## Why this round is about borrowing and not about a signal

Rounds 1–3 eliminated mechanisms, they did not eliminate the goal:

| round | mechanism | verdict |
|---|---|---|
| 1 | BA-004-style rotation/cash drag | `Redundant`, loses to doing nothing |
| 1 | mean reversion (mirror image) | dead on raw moments, −0.23 to −0.35 pp |
| 2 | overnight/intraday split | nightly toll 1.5%/yr beats what nights pay |
| 3 | weekly timing, incl. any news-driven variant | `Redundant`; bar 56–58%, achieved 53–58%, 15 of 16 cells short |

What survived every window, with no signal at all, was constant leverage. That is not an
edge and this note will not pretend otherwise: leverage multiplies the equity risk
premium and charges a spread for the privilege. It is sized here rather than dismissed
because the goal is stated in dollars per month, because it is the only candidate left
that has never failed the dominance rule, and because "it works in a backtest" is exactly
the claim this repository has twice been burned by not stress-testing.

The question this round answers is therefore not *should* I lever, it is **how much, in
what wrapper, and at what price per unit of pain** — with the margin cliff identified
rather than described.

## Method

Funded simulator from `run_voltarget_scan` (shared engine, extended this round with a
`path` and `carry_paid` field so a worst month and a real interest bill could be priced
without re-implementing it). $5,000 opening, $500/month, SPY, four windows, all rows net of:

- 9.45 bps fund expense on the equity leg
- 2.0 bps per unit of one-way turnover
- borrow at the archive's own cash index **+150 bps**, charged daily on borrowed notional
- 30% maintenance equity, with forced deleveraging when breached

**The 1.00× row is the load-bearing part of the table.** Target 1.0 with no band must
reproduce plain DCA exactly, and it does, to the dollar, in all four windows. Every levered
row above it is therefore measured against a comparator the same engine agrees on, and if
that row ever drifts, nothing below it is worth reading. `tests/test_leverage_sizing.py`
asserts it rather than asking anyone to eyeball a screen.

## The price list, full window (1993→2026)

Comparator: **$1,922,914** on $206,500 paid in, CAGR +10.80%, max DD −52.8%.

| lev | $ vs DCA | extra/mo | CAGR | max DD | worst mo | trades | margin calls | interest paid |
|---|---|---|---|---|---|---|---|---|
| 1.25 | +$505,861 | **+$143** | 11.80% | −62.7% | −20.9% | 36 | 0 | $46,349 |
| 1.50 | +$1,222,135 | **+$346** | 12.90% | −71.0% | −25.2% | 81 | 0 | $120,350 |
| 1.75 | +$2,150,022 | **+$609** | 14.00% | −77.3% | −30.8% | 161 | 0 | $218,031 |
| 2.00 | +$2,371,530 | **+$672** | 14.22% | −83.3% | −35.2% | 331 | 0 | $291,518 |
| 2.50 | +$3,206,715 | +$908 | 14.97% | −92.3% | −43.7% | 821 | 0 | $466,982 |
| 3.00 | +$2,685,378 | +$761 | 14.52% | **−97.0%** | −53.1% | 1,545 | **25** | $536,260 |
| 4.00 | −$1,834,285 | −$520 | −5.72% | −99.3% | −66.7% | 8,456 | **8,450** | $63,058 |

`extra/mo` is the level monthly amount whose accumulation at the comparator's own rate
equals the terminal gap — chosen over the raw gap because the goal is phrased in monthly
dollars, and discounted at the *unlevered* rate so leverage cannot rate its own winnings.

## The knee is at 1.75–2.0×, and it is a marginal question

Averages flatter the middle of a curve that turns over at the end, so the tool prints the
marginal step: what each additional quarter-turn of leverage buys, and what it costs in
drawdown points.

| step | extra $/mo | added DD pts | $ per added DD pt |
|---|---|---|---|
| 1.00 → 1.25 | +$143 | +9.9 | +1,448 |
| 1.25 → 1.50 | +$203 | +8.3 | +2,434 |
| 1.50 → 1.75 | +$263 | +6.3 | **+4,164** |
| 1.75 → 2.00 | +$63 | +5.9 | +1,056 |
| 2.00 → 2.50 | +$237 | +9.0 | +2,631 |
| 2.50 → 3.00 | −$148 | +4.7 | **−3,137** |
| 3.00 → 4.00 | −$1,280 | +2.3 | −55,240 |

Best price per unit of risk is at **1.5–1.75×**. The step from 1.75 to 2.0 buys $63 a
month for five points of drawdown — the first step that is visibly a bad trade. Past 2.5×
the marginal dollars go negative: you take more risk and receive less. At 3.0× the margin
engine fires 25 times and at 4.0× it fires 8,450 times, which is not a strategy with high
leverage, it is a liquidation that takes a while to notice itself.

**Disqualification rule used here, stated before the run:** any row with a margin call is
out regardless of its CAGR. A drawdown is a number on a screen and recovers; a forced
deleveraging is a sale executed by someone else, at the worst price, on the schedule that
guarantees it was the worst price. The 3.00× row earns +$2.7m and is still disqualified.
That is not conservatism, it is that the +$2.7m and the 25 calls are the same event
described twice.

## The instrument matters more than the sizing, and this is the round's real finding

Round 3's surprise was that the choice of sleeve swamped the choice of rule by an order of
magnitude ($49,857 to $140,155 on identical DCA). The same question had never been asked
of the leverage decision, so it was: same exposure, same window, two wrappers.

| target | retail margin (band, cash+150 bp) | ETF wrapper (daily reset, 0.90% ER, cash+25 bp) | wrapper − DIY | margin calls |
|---|---|---|---|---|
| 1.50× | $3,145,050 | $3,106,573 | **−$38,477** (DIY cheaper) | 0 / 0 |
| 2.00× | $4,294,445 | $5,009,880 | **+$715,435** (wrapper cheaper) | 0 / 0 |

There is a **crossover near 1.7×**, and the reason is arithmetic rather than mysterious:
retail margin charges 150 bp on the borrowed part, which is 0.5× NAV at 1.5× and 1.0× NAV
at 2.0×, while the wrapper pays a fatter expense ratio (≈80 bp over SPY's 9.45) but borrows
at the institutional swap rate (+25 bp). At low leverage the fatter expense ratio loses;
at high leverage the retail spread loses. Below ~1.7×, borrowing it yourself is cheaper.
Above it, a leveraged index fund is cheaper **and structurally cannot be margin called** —
it can be destroyed by a bad year, which is a risk you can size for, but not force-sold at
the bottom, which is a risk you cannot.

Two corollaries worth stating plainly:

- **Most of the leverage decision is a financing decision.** Holding 1.5× over the full
  window at 150 bp cost $120,350 of interest against $1,222,135 of gain. Repricing the
  spread to zero turns that same row into +$1,942,189 — the financing term is worth more
  than half the trade's entire benefit, and it is the one term a fund choice can move.
- **Daily rebalancing is nearly free**, against the folklore. Same 1.5× target, same
  window, 10% band versus rebalancing every session: $3,145,050 vs $3,186,911, a
  *gain* of $42k from doing it daily. Volatility-decay talk about levered funds is
  mostly the financing cost wearing a different hat.

## What this does and does not license

It does not license borrowing to the knee. Every window-specific gain is a *realised*
gain from a 33-year bull market in which SPY compounded 10.8% against a cash rate that
spent most of the period well below it. Leverage is a claim on that spread; if the spread
inverts for a decade — cash at 5%, equity flat, which is the regime the last four years
hinted at and the 1970s delivered — the same dial turns the other way and turns over
faster, because the 30% maintenance line does not care what your average was.

It says three specific things:

1. **1.5× is the defensible number, not the largest number.** It buys +$346/mo (full) and
   +$81/mo (recent window, the one closest to the regime you'd actually trade in) with
   zero margin calls in all four windows. 1.75× is where the marginal price per unit of
   risk peaks. 2.0× and above is where the tail starts eating the trade.
2. **If the target is 2× or more, the wrapper choice is worth more than the signal
   search was.** $715,435 on the full window, from a fund-selection decision requiring no
   forecast, no news feed, and no data purchase — larger than anything rounds 1–3 found.
3. **The monthly numbers are small at this account size, and that is the honest headline.**
   +$34 to +$81/month on the recent window at 1.25–1.5× is real, is not a rounding error,
   and is nowhere near "the model pays something". The objective as stated — earn extra
   each month *and* beat VOO/QQQ with a short-term news-informed bot — has now been
   measured against four signal mechanisms (all `Redundant`) and one sizing mechanism
   (works, costs money, caps out at low hundreds of dollars a month on a $33k account).

## Bugs this round found in its own tooling

Both of my errors this round pointed the wrong way and looked like findings:

- **Annual rate charged per session.** The first `wrapper_returns` priced the ETF's
  financing at cash+0.25% *per day*, reporting the wrapper as a 99% loss that "proved" DIY
  margin wins everywhere. Caught by sanity-checking the magnitude before believing it.
  Pinned twice in tests — against a hand-computable 1.15% annual drag and against a
  0.5 expense-ratio ratio — so the scale error cannot return silently.
- **Expense ratio charged on gross exposure.** Applying a 2× fund's 0.90% ER to its gross
  notional double-counts the leverage the fund already applies. Charged on NAV (the money
  in), the crossover appears at ~1.7×; charged on gross, the wrapper lost everywhere and
  the conclusion inverted.

The lesson is the same one round 3 recorded, and it is now a habit rather than a rule:
**check that a number is the right order of magnitude before checking that it is
positive.** A simulator that reports a catastrophe has usually mis-scaled a constant.

## Reproduce

```
.venv/bin/python tools/leverage_sizing.py                      # all four windows
.venv/bin/python tools/leverage_sizing.py --windows full --spread 0.0
.venv/bin/python tools/leverage_sizing.py --windows recent
.venv/bin/python -m pytest tests/test_leverage_sizing.py -q    # 13 tests
```

Suite at this commit: **1,146 passed, 233 subtests**.

## Next

The mechanism is sized and the wrapper is chosen. What remains unmeasured, and is the only
thing left that could change the answer, is the **forward** record: the paper bot currently
runs the vol-target candidate and asks for 128% exposure, which the 1.5× cap in this note
permits and the crossover in this note says should be taken in a wrapper rather than on
margin if it is ever raised. Round 5 should re-point the paper bot at the sized
configuration and start collecting the entries the forward journal needs — because every
table in this repository is now a claim about the past, and the goal is about the future.
