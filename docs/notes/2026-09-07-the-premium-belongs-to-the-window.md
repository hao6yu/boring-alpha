# The premium belongs to the window

Measured 2026-09-07, round 73. New tool: [`sleeve_table.py`](../../tools/sleeve_table.py). Tests: 15 in
[`test_sleeve_table.py`](../../tests/test_sleeve_table.py), 2 in [`test_shelter_ticket.py`](../../tests/test_shelter_ticket.py).

The objective says *VOO, QQQ or whatever*, and seven rounds of evidence existed on one fund, SPY. Trying to sweep the
others found out why not: `correction_table.measure` charged every construction `wc.EXPENSE["SPY"]`, whatever it was
measuring. A QQQ row priced at 9.45 bps instead of 20, a VOO row at 9.45 instead of 3 — a sweep through that function
would have been wrong in the one cost both arms share, and wrong in the direction that flatters the expensive fund.
`measure` now takes a `sleeve` and looks the fee up by that symbol, refusing any symbol the file has no posted expense for
(round 69's rule: a fee comes from the table or it is labelled an assumption). Then the table, fifteen real rows and three
labelled proxies, each fund scored against the plain fund itself over exactly its own dates:

| fund | window | record from | wins | fee | plan | fund alone | delta | fund P(fail) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| SPY | own | 2002-08-01 | 169 | 0.09% | 567.22 | 436.76 | **+130.46** | 4.1% |
| SPY | panel | 2006-02-07 | 127 | 0.09% | 562.70 | 435.47 | +127.24 | 5.5% |
| SPY | recent | 2011-06-24 | 63 | 0.09% | 759.96 | 919.02 | **−159.06** | 0.0% |
| VOO | own = recent | 2011-06-24 | 63 | 0.03% | 770.25 | 925.97 | **−155.72** | 0.0% |
| VTI | own | 2002-08-01 | 169 | 0.03% | 642.77 | 464.66 | +178.10 | 0.6% |
| VTI | recent | 2011-06-24 | 63 | 0.03% | 717.12 | 885.42 | −168.31 | 0.0% |
| ITOT | own | 2004-11-08 | 142 | 0.03% | 637.08 | 453.31 | +183.77 | 0.7% |
| ITOT | recent | 2011-06-24 | 63 | 0.03% | 731.58 | 892.09 | −160.52 | 0.0% |
| QQQ | own | 2002-08-01 | 169 | 0.20% | 598.84 | 662.59 | **−63.76** | 0.0% |
| QQQ | panel | 2006-02-07 | 127 | 0.20% | 707.67 | 733.13 | **−25.47** | 0.0% |
| VOO\* | own | 2002-08-01 | 169 | 0.03% | 570.88 | 441.07 | +129.82 | 1.8% |

Four findings, and the first three contradict how the last seven rounds have been worded.

**1. The premium is the window's, not the ticker's.** On the window all five funds can be scored on — 2011-06-24, the first
session after the *youngest* fund's warmup — every US equity sleeve loses to holding the fund, and they lose within $12.59
of each other (−$155.72 to −$168.31; QQQ −$191.47). On their own longest records the same funds earn +$130.46 to +$183.77,
a spread of $53.31. Funds agree to tens of dollars; windows disagree by hundreds. Round 66 wrote that a record's length is
a position taken by whoever wrote the tool, and this is that warning turned on the round's own headline: `+$130` was always
a statement about 2002-2011.

**2. The sign is the hedge's payout band, not the fund.** Read `delta` beside `fund P(fail)` and the table has one law:
**a row pays a premium exactly when the plain fund failed at least one window.** It holds on 18 of 18 month-start rows,
proxies included, and it is pinned as a test over all of them rather than as a paragraph. At month-end readings exactly
one row deviates — QQQ's panel row, +$13.91 on a fund that never failed — which is under round 60's $25 bar, so it is
noise wearing the finding's clothes; it is pinned by name and by size so a second exception, or this one growing up,
breaks the build. Where the fund never fails, the hedge is a subscription to protection that never pays: that was
round 67's rule, and it has now predicted six rows it had never seen.

**3. A record about VOO that contains 2008 cannot exist.** VOO started in September 2010, so its own honest record *is*
the common window; there is no older VOO price to hedge. The only defensible answer to "would this rule have helped a VOO
account since 2002" is a labelled proxy — SPY's path at VOO's fee, the `VOO*` row — and it pays +$129.82 against SPY's own
+$130.46. The entire expense-ratio difference between the cheapest and the dearest S&P fund is worth **$0.64 a month** on
this construction, so the fee is nowhere near the reason the answers differ.

**4. QQQ loses on every window at both conventions.** −$63.76 from 2002, −$25.47 from 2006, −$191.47 on the common window;
at month-end readings −$315.13. A 200-day rule on a growth index exits the 2000 and 2008 collapses late, gives back more
on the V than it saves, and pays 20 bps for the privilege. This closes the oldest idea in the project's own brief: the
construction does not transfer to the fund with the best headline returns, and the objective's "or QQQ" has now been
answered with a number rather than a hope.

## The hazard the sweep found in the shared engine

`carry` expands monthly marks into daily weights by holding *the previous month's decision*, starting from `0.0` — which
for a record that opens before the fund's own 201st session means the record silently **opens sheltered**, because there is
no previous decision to hold. Round 45's artefact (a rule with no answer reporting a decision) again, one level further
down: unreachable on SPY, whose history predates every record floor in this repository, and live the moment a younger fund
is swept. The sweep therefore starts every row at `max(floor, that fund's own warmup)`, and a test asserts no row's record
begins before the day its own average exists. No published number changes: the SPY rows reproduce to the cent
(+$130.46, 19.6% duty).

## The live sheet changed too

`shelter_ticket.py` can no longer print one window. An issued sheet gains a block —

```
  3. THE OTHER WINDOWS   (printed because one number is a position, not an answer)
     panel   from 2006-02-07: 562.70/mo vs the fund's own 435.47 =    +127.24   (premium; the fund failed 5.5% of windows)
     recent  from 2011-06-24: 759.96/mo vs the fund's own 919.02 =    -159.06   (no premium; the fund failed 0.0% of windows)
```

— and `--record recent` refuses outright:

```
  NOT ISSUED. The plan is not being recommended at these numbers:
    - loses to holding the fund itself by 159.06/mo on the recent record from 2011-06-24; the sheet will not print a
      premium that is not there
```

The refusal wording honours sign now: a shortfall under the bar and a loss are different sentences, and the old wording
called a loss a shortfall.

## What this leaves the objective holding

The construction is insurance against the decade in which plain DCA runs out of money, and nothing else. Over 24 years of
the long record the premium is +$130/mo per $100k with P(fail) driven from 4.1% to 0.0%; over the last 15 years it is a
**cost of about $160/mo per $100k** on every fund, and the last 15 years is the only stretch any of these funds have all
lived through. So the fork is explicit and the search does not end here: either that is the trade — pay ~$160 a month per
$100k for a promise that held through 2008 — or the next rounds look for something that clears the *recent* window too,
which is the binding constraint and now the named target.

## Checks

15 + 2 tests. The whole suite **1928 passed** (collected first: 1911 + 17). Both conventions, the proxy identity, the fee
provenance, the cold-open guard, the unposted-fund refusal, the rendered columns, the law over all 18 rows and its one
named exception are each pinned separately, so the table can be changed and the finding cannot quietly go away.

---

**Amended in round 102.** The window claim survived the sweep; the *insurance* law did not. Adding IWM, EFA and EEM — refused
here for four rounds on a fee reason round 94 had already made false — put the table in front of sleeves whose funds failed
often and whose shelters still lost: IWM's fund failed 8.7% of its windows and the hedge cost $300.47 a month at 30.6% of days
out of equities. What sorts the payers from the losers on the failure-containing records is the **duty** column, not the failure
column: payers ≤ 28.2% of days out, losers ≥ 30.6%, on 11 rows. ([the round's own note](2026-09-08-a-refusal-that-named-a-fee-which-was-not-missing.md))
