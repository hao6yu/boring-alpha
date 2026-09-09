# The amendment that cannot pay for itself

Measured 2026-09-07, round 76. New tool: [`tilt_brake.py`](../../tools/tilt_brake.py). Tests: 15 in
[`test_tilt_brake.py`](../../tests/test_tilt_brake.py).

Round 75 left a hypothesis written down before it was measured: a static half-SPY-half-QQQ blend beats plain SPY by
+$182.64/mo per $100k on the recent window with no decisions at all, and the best rule available gave back $94.35 of that to
buy crash protection. The synthesis everyone would try next is obvious — keep the tilt, add a trend brake — and this file is
the price of that idea, tested against the row it amends rather than against the index, which round 75 established is no
longer a demanding opponent. Four brake variants, one control, two single-fund floors, one shared calendar from 2005-09-06,
one pass rule fixed before the first run: beat the blend by $25/mo on both windows, hold that at month-end, do not raise the
failure probability, and not be plain QQQ in disguise.

| rule | Δ vs the blend, long | Δ vs the blend, recent | recent, month-end | Δ vs plain QQQ, recent | switches |
|---|---:|---:|---:|---:|---:|
| brake_both (50/50 → all IEF when both under MA200) | +8.08 | **−223.08** | −496.75 | −390.55 | 22 |
| brake_half (same trigger, half the book braked) | +36.07 | **−112.95** | −241.14 | −280.42 | 22 |
| brake_either (a sleeve under its own average is replaced by IEF) | **+60.92** | −166.55 | −309.73 | −334.03 | 29 |
| brake_cash (`brake_both`, braking into cash) | −15.32 | −161.77 | −467.21 | −329.25 | 22 |
| blend_sq (the control) | +0.00 | +0.00 | +0.00 | −167.47 | 0 |
| spy_only | −154.18 | −182.64 | −182.64 | −350.12 | 0 |
| qqq_only | +130.13 | +167.47 | +167.47 | +0.00 | 0 |

**0 of 4 pass.** The hypothesis died on the first clause, which is the one that matters: every brake is worse than doing
nothing on the window the objective cares about, by $113 to $223 a month per $100,000. Three of the four are worth something
on the record that contains 2008 and 2020 — by $8 to $61 — which is what insurance costs when the thing it insures has a
fifteen-year gap.

## The convergence, which is the actual result

Three orthogonal families, three rounds, one sign:

- **rounds 73-74, hedging:** nine trend/volatility/drawdown rules over one fund, −$111 to −$458/mo on the recent window.
- **round 75, selection:** rotating between equity regimes, best rule +$88.29 vs plain SPY but −$94.35 against a static blend.
- **round 76, a brake on the tilt:** −$112.95 to −$223.08 against that same static blend.

Different data, different triggers, different instruments, priced by the same engine through the same cost model. The
archive's answer to "a monthly trading decision that beats holding a growth-tilted blend" is not *no* for one family — it is
no for the three families the archive can price, and the size of the loss is set by how long the plan spends not holding
equity. That is a property of 2011-2026, not of the rules.

## The clause that could not fire, and what that says about the measure

Clause 3 was supposed to be the brake's defence: it protects the left tail. On this archive at the published payout of
$435.47/mo, **every brake and the control have an identical failure probability of 0.0%** — over 132 ten-year windows on the
long record and 63 on the recent one — so the clause
is inert — the measure cannot see the benefit of the brake while it charges its cost. That is not the brake's fault and not
the measure's: at that withdrawal the floor simply isn't binding for a book holding growth over ten years.

The clause is still doing real work, just elsewhere: it is the only clause that catches plain SPY, whose long-window failure
probability is **5.3%** against the blend's zero. So the one construction in this repository that improves *both* capacity
and the tail is the one with no decisions in it — diversifying across two styles — and nothing that trades improves the tail
by a measurable amount at this payout. If the tail is what a person actually cares about, the next thing to measure is
P(fail) at a payout that binds, not another overlay.

## Three things the tests hold down

**The brake misses the month it exists for.** `brake_both` is asserted to be fully in Treasuries through October 2008 *and
May 2020* — and to be **unsheltered in March 2020**, because last month's close against a 200-day average, applied this
month, cannot see a one-month collapse. A test that instead asserted "sheltered in March 2020" would have failed, and a test
that quietly checked "some month in 2020" would have hidden the lag that the long-window numbers are paying for.

**The two tools have to agree on the row they both price.** `spy_only` is priced by `rotation_search.py` and here, on the
same calendar; round 75 published it as −$154.18 / −$182.64 against plain SPY and this file prices it as the negative of the
blend's premium, and the test asserts the two cancel to the cent. A shared helper changed under one tool would show there
before it showed in a verdict.

**Which brake is cheaper flips with the window.** Treasuries beat cash on the crash-containing record and lose to it on the
last fifteen years, where the shelter itself fell while rates rose. Same rule, opposite ranking, window deciding — the
repository's oldest lesson, arriving again with a new instrument.

## Where that leaves the objective

Honest position: within anything this archive can price at monthly cadence and retail costs, the highest-capacity
construction the repository has found is a static tilt — no reading, no switch, no veto — at +$182.64/mo per $100k over
plain SPY on the recent window, 0.0% failure. Every decision tested on top of it costs capacity. The objective named
short-horizon decisions informed by trend and global news, and that is precisely the part the evidence cannot reach: this
archive is daily closes, the attention corpus was refuted as a veto in round 72, and a five-day or intraday strategy cannot
be priced here at all because there is no spread, no queue, and no intraday print in it. So the fork in front of the project
is not "another overlay" — it is **acquire a data source that can support short-horizon decisions and price them honestly**,
or accept that on daily-close data the answer is the tilt, and stop looking. Rounds 73 to 76 have made the second branch
fairly thoroughly true.
