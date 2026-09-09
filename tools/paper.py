"""The forward book: what was planned, what was done, what it cost, in a chain nobody can quietly edit.

Everything else in this repository reads the past. A backtest can only ever report a claim about history, and this
project's history has been looked at often — the trend family has been evaluated three times, and a fourth idea died on a
diagnostic, all against the same twenty-odd years. The book is the one artefact here that faces forward: it seals what it
decided before the next month-end exists, so the answer it produces is one nobody has seen yet. That is the entire
justification for its cost in complexity.

Six models, four live books beside the root one. `shelter` (the root) holds SPY above its 200-day average read on the
first trading day of the month before the one it governs, and the shelter leg below; `constant` holds a fixed financed
125%; `voltarget` is the pre-registered candidate; `tilt` and `tilt_band` hold the static 50/50 SPY/QQQ balance that
rounds 74-83 left standing as the only construction that beat plain VOO net of costs, rebalanced monthly in one and past
a five-point band in the other. The book is not a recommendation engine and does not become one: it is a record, and the
only verdicts it renders are the ones its own sealed entries support.

What this file refuses, and why each refusal is a line of code rather than a comment:

* It refuses an unposted expense ratio to a comparator (`posted_fee`). An unposted sleeve is held and charged the
  conservative flat guess, because holding it is the investor's decision; a benchmark is what the account is scored
  against, and scoring against a fund at a fee nobody posted is how a winner is manufactured (round 81).
* It refuses a caller's tilt weight or band (`main`). Both were measured, one against `mix_sweep`'s control row and one
  against `rebalance_cost`'s regime table. A number whose whole value is that it was not chosen cannot be chosen on a
  command line without destroying the reason for using it.
* It refuses a second `init` on a book that has sealed anything, and refuses it unless *both* chains are absent: the
  strategy and its witness advance together, so removing one is not a reset (rounds 67, 69).
* It refuses to render a skill verdict the protocol does not allow, and prints what remains instead. Costs are measured
  from the first entry; skill is inferred, and inference from one month on a $5,000 account is noise wearing a
  conclusion.
* It refuses to answer when its rule cannot answer: a missing 200-day average yields no weights at all rather than the
  shelter, because a rule whose silence means "sell" has a failure mode instead of a floor (rounds 45, 66, 85).
* It refuses a step for a session it has already sealed, rather than writing a second entry for it.

Two accounting rules live here alone, in one place each, because both were got wrong in both chains at once and both
decide the central claim: `recover_cash` (round 82) and `orders_within_band`'s drift convention (rounds 83, 84).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from boring_alpha.data.csv_loader import load_csv_market_data                     # noqa: E402
from boring_alpha.journal import (ChainReport, Comparator, Entry, GENESIS, Holding,   # noqa: E402
                                 Quote, Verdict, append, create_ledger, entry_hash,
                                 measure, read as read_entries, verify, verdict)
from boring_alpha.signals.voltarget import VolTargetPolicy                        # noqa: E402

# The journal's own reader, re-exported: a reader of the book should need only this file to know what a sealed entry is,
# and `book_power.py` reads a ledger through this module rather than through the package because the book is the thing it
# is reading about. `read` is the journal's function and this file has no second file-reading helper, which is the point of
# a journal with one way to read it.
read = read_entries

# --- where things live -------------------------------------------------------

# The one place the state root is resolved, so a rehearsal can aim the whole loop at a disposable copy of the tree.
# `tools/labdata.py` owns the rule; this file only consumes it, and every other tool inherits it through `paper.PAPER_DIR`.
import labdata                                              # noqa: E402  one resolver for the whole loop

DATA = labdata.data_root()
PAPER_DIR = DATA / "paper"
LEDGER = PAPER_DIR / "ledger.jsonl"
SHADOW = PAPER_DIR / "shadow.jsonl"
CONFIG = PAPER_DIR / "model.json"

SNAPSHOT = DATA / "current" / "market_daily.csv"
CASH_FILE = DATA / "current" / "cash_daily.csv"

# --- the account, shared by every book by construction -----------------------

OPENING = 5000.0
MONTHLY = 500.0
SPREAD_BPS = 3.0

#: The leg this chain used to omit entirely: a book sized above 100% carries a loan, and a loan at zero interest is a
#: margin account no broker offers. Round 30 measured a real all-in desk spread near this; the first version of this
#: constant was 150 bps and it was raised, at a re-init, to what the posted desk quotes. Pre-registered in the sense that
#: matters: it may move only at an anchoring, which starts a new chain, never mid-chain — otherwise a book stops being
#: comparable with its own history for a reason that has nothing to do with the market.
import fund_fees                                                 # noqa: E402  the one expense table

BORROW_SPREAD = 0.0202
TRADING_DAYS = 252       # the archive's cash factor is per session; annualised the way the research files annualise it

#: A fee for a symbol this repository has NO source for at all. As of round 94 that is no longer any sleeve in the archive:
#: every leg in `SLEEVES` has a sourced ratio in `fund_fees.py`, and the guess survives only for a symbol nobody has added
#: there yet. It is not zero, and it is above the average of the priced universe on purpose, since a missing fee is worth
#: more than a guess. It is also not, as a previous version of this comment claimed, "deliberately the pessimistic
#: direction" for every leg: measured against the published ratios the old flat guess was 20 bps too harsh on IEF and TLT
#: and 49 bps too kind on DBC, and a comment that is mostly true about a cost is how a cost stops being watched.
UNPOSTED_FEE = fund_fees.GUESS

#: Every ratio this repository charges, in one place, with the source it came from (`fund_fees.py`). The five the repository
#: has always posted keep their exact values — sealed chains are priced with them and cannot be re-priced without becoming
#: two chains — and the other seven carry the published figures that replaced round 94's flat guess.
FEES: dict[str, float] = dict(fund_fees.FEES)

#: The eight sleeves the cross-sectional and trend work in this repository has always used, and with `QQQ`/`VOO`/`VTI`/`ITOT`
#: the twelve-symbol universe the archive is priced on and the set every sealed entry quotes. A seal that quotes only what it
#: holds cannot be repriced against a model that changes its mind, so every entry quotes the whole universe — which is also
#: why every one of them now has a sourced ratio rather than a shared guess: an entry that quotes a fund cannot be priced by
#: a number that was invented for it.
SLEEVES = ("SPY", "IWM", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC")

#: Refuse at import rather than at seal time: a sleeve that quotes on every sealed entry must have a ratio with a source
#: behind it. This used to be a `setdefault` that quietly charged the guess, which is how four of these legs got a number
#: in one tool and a different number in another.
_missing = [leg for leg in SLEEVES if not fund_fees.priced(leg)]
if _missing:
    raise SystemExit(f"`fund_fees.py` does not price {', '.join(_missing)}; every sealed entry quotes them, so none may be "
                     f"priced by a guess")

#: Symbols with an expense ratio the repository actually posted. A witness must be one of these; a holding need not be.
POSTED = tuple(sorted(k for k, v in FEES.items() if v != UNPOSTED_FEE))

CANDIDATE_SERIES = "SPY"
SHELTER = "IEF"

#: The ratio the book's own fund bills, and the number its witness is priced at while the witness is that same fund. Named
#: separately from `fee_for` because tests and other tools ask for the book's fee, not a fee for a symbol.
EXPENSE_RATIO = FEES[CANDIDATE_SERIES]

#: The pre-registered candidate, in one place: an 18% volatility target on a 30-day window, a 200-day trend gate, a 30%
#: floor, a 1.30x cap, a ten-percent band, five-session review. Changing any of those five numbers makes a new candidate,
#: and picking the best of a grid on the data used to judge it is what killed BA-004. `policy_withdrawal.py` carries the
#: same construction by value, and its comment says it was copied from here.
CANDIDATE = VolTargetPolicy(target_vol=0.18, vol_window=30, trend_window=200,
                            max_weight=1.3, min_weight=0.3, rebalance_band=0.10,
                            review_every=5)

#: The `constant` model's exposure. Not a view about the market and not a target to be hit: a fixed financed position,
#: which is the only honest way to describe a plan whose excess over the fund is leverage rather than timing (rounds 30-32).
CONSTANT_WEIGHT = 1.25

# --- the live income book's two parameters, both measured elsewhere ----------

TILT_WEIGHT = 0.50
TILT_SERIES = ("SPY", "QQQ")
TILT_BAND_POINTS = 5.0
TILT_COMPARATOR = "VOO"

MA200 = 200
TREND_READING = "first trading day of the month BEFORE the one it governs"
MODELS = ("trend", "voltarget", "constant", "shelter", "tilt", "tilt_band")

BUY = "BUY"
SELL = "SELL"


# --- the two surfaces the book writes with ----------------------------------

@dataclass(frozen=True)
class Order:
    """One intended fill. `units` is always positive: the direction lives in `side` and nowhere else."""

    symbol: str
    side: str
    units: float
    notional: float
    cost: float


@dataclass(frozen=True)
class Signal:
    """What a model wants held at a session, and what it had to know to want it.

    The attributes carry the names the journal and its tests use — `target_weights`, `asset_returns`, `cash_return` —
    while the constructor takes the plainer `weights`, `returns`, `hurdle`. `tests/test_paper_constant.py` pins that
    pairing by asserting on `cash_return` rather than on the keyword that filled it, so the mismatch is load-bearing and
    is documented instead of tidied away. `WeightVector` is this class under its older name, not a second definition: two
    vectors of intended exposure would be two places for the disclosure rules to disagree.

    `asset_returns` is empty for every model this book runs, and that is a disclosure rather than an omission: none of
    these models forecasts a return, and a field quietly filled with trailing returns would read like one. The tilt
    model's is pinned empty for exactly that reason.
    """

    asof: date
    target_weights: dict[str, float]
    asset_returns: dict[str, float]
    cash_return: float
    name: str
    read_on: date | None = None
    band: float = 0.0

    def __init__(self, asof: date, weights: dict[str, float], returns: dict[str, float], hurdle: float,
                 name: str, read_on: date | None = None, band: float = 0.0) -> None:
        object.__setattr__(self, "asof", asof)
        object.__setattr__(self, "target_weights", dict(weights))
        object.__setattr__(self, "asset_returns", dict(returns))
        object.__setattr__(self, "cash_return", hurdle)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "read_on", read_on)
        object.__setattr__(self, "band", band)


WeightVector = Signal


# --- small surfaces ---------------------------------------------------------

def snapshot_id() -> str:
    """The sealed snapshot's own id, never the `current` pointer.

    `current` is the one thing in the path guaranteed to change, so a record naming it proves nothing about what it was
    built from. The tests pin both halves: not the pointer, and shaped like a timestamp.
    """

    try:
        return SNAPSHOT.parent.resolve().name
    except OSError:
        raise SystemExit(f"the data pointer {SNAPSHOT.parent} does not resolve to a snapshot")


def load_data(asof: date | None = None):
    """The archive as it stood at `asof`. Every caller that means "now" passes nothing and gets the pointer's record."""

    return load_csv_market_data(SNAPSHOT, CASH_FILE, end=asof)


def fee_for(symbol: str) -> float:
    """The expense ratio to charge a *holding*: the posted one where one is posted, the labelled flat guess otherwise.

    A symbol outside the universe is refused rather than guessed at. An unpriced symbol is not a free symbol, and a fee
    function that hands a default to anything it has not heard of turns a typo into a zero-cost position — round 69's
    rule, that a fee comes from the table or the call is refused, worded the same way in `sleeve_table.py` and enforced
    by `shelter_ticket.py`'s refusal of a shelter the file has no price for.
    """

    if symbol not in FEES:
        raise SystemExit(f"{symbol} has no fee in this book's table: the fee comes from the table or the sleeve is"
                         f" refused, and an unpriced symbol is not a free one")
    return FEES[symbol]


def posted_fee(symbol: str) -> float:
    """The expense ratio a *benchmark* may be charged: a posted one, or a refusal.

    The distinction is the whole reason this function exists. An unposted sleeve may be held — that is the investor's
    decision, and the conservative guess is the honest way to cost it — but a comparator is the number the account is
    scored against, and a benchmark charged a fee nobody posted is a benchmark nobody can verify. Round 81's first
    finding against the live artefact: the tilt's witness was being charged a guess.
    """

    if symbol in FEES:
        return FEES[symbol]
    if fund_fees.priced(symbol):
        # A cash leg has a sourced ratio and no price series. Since round 99 the fee table knows the difference, and a
        # gate that only asked "is it priced?" would have let `--witness SGOV` through the fee check and then died on a
        # KeyError inside the ledger — a traceback where a sentence belongs (r93).
        raise SystemExit(f"{symbol} has a sourced ratio but is not a traded leg of this archive: the corpus quotes no "
                         f"price for it, so it can be neither held nor made a witness")
    raise SystemExit(f"{symbol} has no posted expense ratio; it may be held and charged the conservative "
                     f"{UNPOSTED_FEE:.2%} guess, but it cannot witness")


def comparator_spec(symbol: str) -> dict:
    """A witness, written down: name, weights, fee. All three derived, none of them typed.

    The config used to describe its benchmark twice, in two different amounts — a top-level ratio beside a comparator
    that could be any fund, a 6.45 bps disagreement baked into the file the journal trusts. Both fields come from this
    call now, and a test asserts they agree.
    """

    return {"name": f"100% {symbol}", "weights": {symbol: 1.0}, "expense_ratio": posted_fee(symbol)}


def book_sleeves(model: str) -> tuple[str, ...]:
    """Every book trades its model's sleeves and no others. A model that can drift into another's sleeves is a second
    construction wearing the first one's name, so the list is derived from the model rather than configured."""

    if model == "trend":
        return SLEEVES
    if model in ("voltarget", "constant"):
        return (CANDIDATE_SERIES,)
    if model == "shelter":
        return (CANDIDATE_SERIES, SHELTER)
    if model in ("tilt", "tilt_band"):
        return TILT_SERIES
    raise SystemExit(f"unknown model {model!r}; the book knows {', '.join(MODELS)}")


def book_fees(model: str) -> dict:
    """The fee table a book may charge, derived from the sleeves it is allowed to hold — never typed in."""

    return {s: fee_for(s) for s in book_sleeves(model)}


def tilt_weights() -> dict:
    """The live income book's entire view: half the cheap broad-market fund, half growth, no cash, no leverage.

    Summing to 1.0 exactly is the design, not the arithmetic: a tilt that borrows is a different claim than the one
    `mix_sweep` measured, and `tests/test_paper_tilt.py` pins the sum from below as well as from above.
    """

    return {s: (TILT_WEIGHT if s == "QQQ" else 1.0 - TILT_WEIGHT) for s in TILT_SERIES}


# --- the models -------------------------------------------------------------

def _first_of_month(days: list, want: tuple[int, int]) -> int | None:
    """Index of the first trading day of month `want`, or None if the record has none."""

    for i, day in enumerate(days):
        if (day.year, day.month) == want:
            return i
    return None


def _prev_month(key: tuple[int, int]) -> tuple[int, int]:
    return (key[0] - (key[1] == 1), 12 if key[1] == 1 else key[1] - 1)


def shelter_weights(data, asof: date) -> tuple[dict, float | None, date | None, float]:
    """The sheltered month's decision, and the day it was actually taken.

    Returns `(weights, close_at_reading, read_on, want_spy)`. The second element is the reading's own close — the price
    the gate was judged at, kept so a reader can check the comparison rather than trust its conclusion. The tests index
    [0], [2] and [3]; nothing asserts on [1], and `shelter_ticket.py` names it `_last` and ignores it.

    Two rules in here are load-bearing, and each was a defect before it was a comment:

    * The reading is taken on the first trading day of the month BEFORE `asof`'s month, never on `asof` itself. The
      ticket that carried this printed "trend read 2026-09-04" — the last date in the file — for a decision actually
      taken on 2026-08-03. A sheet that cannot name the price it acted on cannot be audited against it, which is the
      entire purpose of a dated decision (round 85).
    * A missing 200-day average returns **no weights at all**, not `{SHELTER: 1.0}`. The first version defaulted to the
      shelter, so a rule that cannot answer answered "sell": round 45's defect installed in the forward book's own rule,
      unreachable on the live record and immediate on a truncated one, which is how it was found.

    The window and the comparison follow `shelter_long_record.month_signal(..., "start")` and `carry` day for day: the
    average includes the reading day's own close, and the reading governs the month after it.
    """

    days = sorted(data.dates)
    index = _first_of_month(days, _prev_month((asof.year, asof.month)))
    if index is None:
        return {}, None, None, 0.0
    read_on = days[index]
    if index < MA200 - 1:
        return {}, None, read_on, 0.0               # the gate declines; the book does not answer on its behalf
    closes = [data.by_date[d][CANDIDATE_SERIES].close for d in days]
    window = closes[index - (MA200 - 1):index + 1]
    want_spy = 1.0 if closes[index] > sum(window) / len(window) else 0.0
    weights = {CANDIDATE_SERIES: 1.0} if want_spy else {SHELTER: 1.0}
    return weights, closes[index], read_on, want_spy


def _closes(data, symbol: str, asof: date) -> tuple[list, list]:
    """Dates and closes for one sleeve through `asof`. Date-keyed throughout: nothing here aligns by row number."""

    days = [d for d in sorted(data.dates) if d <= asof and symbol in data.by_date[d]]
    return days, [data.by_date[d][symbol].close for d in days]


def _tilt_name(band: float) -> str:
    """One ordering drives both strings in this disclosure, because they once disagreed.

    `50% SPY / 50% QQQ` sat beside `0.200% / 0.095%`, charging the cheap fund with the expensive fee — the wrong number in
    the one place a reader is told what the sleeves cost. Round 81's third finding, and the reason the weights and the
    ratios below come out of a single sorted list.
    """

    weights = tilt_weights()
    order = sorted(TILT_SERIES, key=lambda s: (-weights[s], s))
    parts = " / ".join(f"{weights[s]:.0%} {s}" for s in order)
    ratios = " / ".join(f"{fee_for(s):.3%}" for s in order)
    rule = "rebalanced monthly" if band <= 0.0 else f"rebalanced only past {band:g} points"
    return (f"static {parts} against {TILT_COMPARATOR}: a balance and not a signal, at {ratios}, {rule}"
            f" — the row mix_sweep scored as its control")


def signal_for(data, asof: date, model: str) -> Signal | None:
    """What `model` wants held at `asof`, or None where the model cannot answer and refuses to guess."""

    if model in ("tilt", "tilt_band"):
        band = TILT_BAND_POINTS if model == "tilt_band" else 0.0
        return Signal(asof=asof, weights=tilt_weights(), returns={}, hurdle=0.0, name=_tilt_name(band), band=band)

    if model == "shelter":
        weights, _close, read_on, _want = shelter_weights(data, asof)
        if not weights:
            return None
        return Signal(asof=asof, weights=weights, returns={}, hurdle=0.0, read_on=read_on,
                      name=f"MA200 read {read_on} ({TREND_READING.lower()})")

    if model == "constant":
        return Signal(asof=asof, returns={}, hurdle=0.0,
                      weights={CANDIDATE_SERIES: CONSTANT_WEIGHT},
                      name=(f"constant {CONSTANT_WEIGHT:.0%} {CANDIDATE_SERIES}: a financed loan at "
                            f"{BORROW_SPREAD:.2%} over the posted cash curve, not a view"))

    if model == "voltarget":
        days, closes = _closes(data, CANDIDATE_SERIES, asof)
        if len(closes) < CANDIDATE.warmup() + 1:
            return None
        returns = [0.0] + [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
        weight = CANDIDATE.raw_weights(closes, returns)[-1]
        if weight is None:
            # Before the windows fill the policy declines to answer. Holding the floor rather than skipping the month is
            # the conservative reading — it keeps the risk on — and it is `policy_withdrawal`'s reading too, so the two
            # files cannot disagree about what the candidate does in its first two months.
            weight = CANDIDATE.min_weight
        return Signal(asof=asof, weights={CANDIDATE_SERIES: weight}, returns={}, hurdle=0.0, name=CANDIDATE.name)

    if model == "trend":
        # The model this book started with, kept runnable and unloved: equal weight across the sleeves whose own MA200
        # reading put them above their average, taken on the day the shelter reads. No live book is anchored on it.
        eligible = []
        for symbol in SLEEVES:
            days, closes = _closes(data, symbol, asof)
            index = _first_of_month(days, _prev_month((asof.year, asof.month)))
            if index is None or index < MA200 - 1:
                continue
            window = closes[index - (MA200 - 1):index + 1]
            if closes[index] > sum(window) / len(window):
                eligible.append(symbol)
        if not eligible:
            return None
        share = 1.0 / len(eligible)
        return Signal(asof=asof, weights={s: share for s in eligible}, returns={}, hurdle=0.0,
                      name=(f"equal-weight {len(eligible)} of {len(SLEEVES)} sleeves above MA200, read on the prior "
                            f"month's first session"))

    raise SystemExit(f"unknown model {model!r}; the book knows {', '.join(MODELS)}")


# --- the account's bookkeeping, one place per rule --------------------------

def orders_for(weights: dict, units: dict, prices: dict, equity: float) -> list[Order]:
    """Orders that take the book to `weights` of `equity`, charged the book's own spread.

    Two rules here are pinned by defects that were live before they were tested:

    * The union of wanted and held symbols. A position the model no longer wants must be closed, and until round 84 the
      code iterated the targets only — so the shelter's first month out of bonds would have gone on holding the bonds
      while paying to buy equities with cash it no longer had.
    * `units` is the magnitude and `side` carries the direction. The field used to hold the signed delta, the applier
      negated it again on a sell, and the two sign conventions cancelled in the wrong place: an order labelled SELL of a
      whole position *bought twice as much of it*. It had never fired, because every model in the book had only ever held
      one symbol and never wanted out — which is the general lesson, not a detail: a code path no live model exercises is
      untested however many months the book has run.
    """

    want_value = {s: equity * w for s, w in weights.items()}
    for symbol in units:
        want_value.setdefault(symbol, 0.0)
    rate = SPREAD_BPS / 10_000.0
    orders: list[Order] = []
    for symbol in sorted(want_value):
        price = prices[symbol]
        delta = want_value[symbol] - units.get(symbol, 0.0) * price
        if abs(delta) < 1.0:
            continue                                   # dust: cheaper to leave it than to disclose it
        notional = delta if delta > 0 else -delta
        if delta > 0:
            # The spread is paid *out of* the amount being deployed, not on top of it: `delta` dollars at the ask buy
            # `delta / (1 + rate)` of fund, so `notional` is the cash leaving the account and `units` is what arrived for
            # it. Sizing the cash on the net instead put an unlevered book that had just invested to the last cent into a
            # fifteen-cent loan — and a book with a loan in its note carries a borrow charge in its fee line, so the
            # witness was being judged against a cost that did not exist. Same convention as `power_horizon.simulate` and
            # `shadow_step`, which is what keeps that differential test inside a quarter.
            net = notional / (1.0 + rate)
            orders.append(Order(symbol, BUY, net / price, notional, notional - net))
        else:
            orders.append(Order(symbol, SELL, notional / price, notional, notional * rate))
    return orders


def orders_within_band(weights: dict, units: dict, prices: dict, equity: float, cash: float,
                       band_points: float) -> tuple[list[Order], float]:
    """Rebalance only past `band_points` of weight. Below it, invest the arriving cash and sell nothing.

    Returns `(orders, drift)`, drift being the largest distance from a target in **points of weight**. Three conventions
    in here are the whole design, and each is shared with `power_horizon.simulate` so the study and the book cannot
    disagree about what they are comparing (rounds 83, 84):

    * Drift is measured across the invested book, not across equity including the cash that has just arrived. Including
      the deposit inflates the reading by about the deposit's share every month — five points on a book funded at 10% a
      month — which breaches any sane band on schedule and turns a band into a monthly rebalance with extra steps. The
      first draft did exactly that, and the band looked inert.
    * Inside the band the deposit is still invested, in full, split by the **target** weights. Suppressing the deposit
      along with the rebalance is round 83's most expensive bug: it left the account's own cash line negative
      permanently and measured a low-turnover policy as a cash-drag policy for sixteen years.
    * A breach rebalances everything to the full targets, and returns the identical list `orders_for` produces. The band
      decides when to trade; it must not change where the book is going.
    """

    invested = sum(units.get(s, 0.0) * prices[s] for s in weights)
    if invested > 0.0:
        drift = 100.0 * max(abs(weights[s] - units.get(s, 0.0) * prices[s] / invested) for s in weights)
    else:
        # At inception every sleeve is its whole target weight adrift — 50 points on a 50/50 book. Not zero: an empty
        # account is the most adrift account there is, and reading it as in balance is how a band strands an opening.
        drift = 100.0 * max(abs(w) for w in weights.values())
    if drift > band_points:
        return orders_for(weights, units, prices, equity), drift
    rate = SPREAD_BPS / 10_000.0
    orders: list[Order] = []
    for symbol in sorted(weights):
        deployment = cash * weights[symbol]            # the whole deposit, split by target weights, never by current ones
        if deployment < 1.0:
            continue
        net = deployment / (1.0 + rate)                # the spread comes out of the deposit, as in `orders_for`
        orders.append(Order(symbol, BUY, net / prices[symbol], deployment, deployment - net))
    return orders, drift


def recover_cash(head: Entry, prices: dict, arrived: float, units: dict) -> float:
    """The cash line at the open of a new interval, recovered from what the ledger sealed and not from today's marks.

    One implementation, called by the strategy step and by the witness step, so neither chain can grow its own version of
    a subtle rule — which is exactly how this defect arrived in the first place: the same wrong line, written twice.

    The previous entry's balance is the sum of its cash and its holdings priced *then*. The new interval sees those
    holdings at today's prices, so subtracting them here would put the mark-to-market into the cash line, where the
    month's orders would invest it or sweep it and the interval would close worth whatever had been deposited into it. In
    a rising market that makes the benchmark a straight line, so every strategy beats it; in a falling one it is still a
    straight line, so every strategy loses to it. Round 82's finding, and the P0 dominance rule is the one claim here
    that must not rest on the graded party's arithmetic — so this line is pinned by name in
    `tests/test_paper_compounding.py`, which reads this file's source to check both steps still call it.

    Today's prices remain an argument: a symbol with no sealed price — one the book has never quoted — has to be valued
    at the new marks, and that is where `prices` earns its place.
    """

    if head is None:
        return OPENING + arrived
    sealed_value = sum(units.get(q.symbol, 0.0) * q.close for q in head.quotes)
    quoted = {q.symbol for q in head.quotes}
    unsealed = sum(u * prices[s] for s, u in units.items() if u and s not in quoted)
    return head.closing_value + arrived - sealed_value - unsealed


def _burn_fees(units: dict, prices: dict, ratios: dict) -> float:
    """Erode each sleeve by its own expense ratio, monthly, and report what that cost.

    Pro-rata on a *summed* expense charges the cheap sleeve the expensive sleeve's rate and the reverse: round 81's fee
    ordering bug wearing a different hat, value-preserving in total, which is why no headline moved when it was fixed.
    The mix moved. It was caught by an oracle comparing one two-sleeve account against the two single-fund accounts it
    has to equal.

    The fee is taken by eroding units, never by debiting a cash line: a benchmark whose cash line is already at zero
    would otherwise be pushed into an overdraft it is defined never to carry, and the `max(0.0, cash)` that hid that
    first version was worse than the bug, because a clamp that forgives a fee biases the number used to judge everything.
    """

    expense = 0.0
    for symbol in list(units):
        value = units[symbol] * prices[symbol]
        ratio = float(ratios.get(symbol, fee_for(symbol))) / 12.0
        if value <= 0.0 or ratio <= 0.0:
            continue
        expense += value * ratio
        units[symbol] -= value * ratio / prices[symbol]
    return expense


def _fee_split(units: dict, prices: dict) -> str:
    """Per-sleeve fees, spelled out in the sealed note, so a reader can see what each leg cost."""

    return " / ".join(f"{s} {fee_for(s):.2%}" for s in sorted(units) if units[s] * prices.get(s, 0.0) > 0.0)


def _borrow_rate(data, asof: date) -> float:
    """The cost of the loan: the archive's own cash curve on the day, plus the pre-registered spread. Read, not assumed."""

    factor = data.cash_factors.get(asof)
    if factor is None:
        prior = [d for d in data.cash_factors if d <= asof]
        if not prior:
            raise SystemExit(f"no cash rate on or before {asof}; the loan cannot be priced from nothing")
        factor = data.cash_factors[max(prior)]
    return factor ** TRADING_DAYS - 1.0 + BORROW_SPREAD


def _months_apart(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def _deposits_due(head: Entry, asof: date, monthly: float) -> float:
    """One deposit per calendar month, taken at that month's first seal.

    The anchor's own month counts as funded: the anchor sealed the opening as cash the account already owns, so paying
    the opening in again on the first seal would fund the book twice. `tests/test_paper.py` pins the cadence with two
    steps in one February — one deposit, two entries, because a sealed entry is an interval and not a pay cheque.

    A missed month is not forgiven, and `days_to_invest` records how long the oldest tranche sat: see below.
    """

    # One deposit for EVERY calendar month since the last seal, not one per seal. The two differ the first time a month-end
    # is missed, and the difference runs in the book's favour: a sealed entry's `cash_arrived` is the denominator of every
    # dollar-weighted return in `journal.py`, so forgiving a deposit that would really have been transferred lowers paid-in
    # and raises the measured return. Round 84's rebuild could not pin which convention the destroyed file used, so the
    # conservative one was chosen and is pinned here, in writing, before the first seal exists to be affected by it.
    return monthly * _months_apart(head.asof, asof)


# --- the two chains ---------------------------------------------------------

def _quotes(data, asof: date) -> tuple[Quote, ...]:
    day = data.by_date.get(asof) or {}
    return tuple(Quote(s, day[s].close) for s in sorted(FEES) if s in day)


def _units_of(entry: Entry) -> dict:
    """Held units, filtered on the value the ledger can actually carry. A holding sealed at zero units is not a position,
    and carrying it forward is how the shelter's exit looked like a purchase."""

    return {h.symbol: h.units for h in entry.holdings if round(h.units, 8) > 0.0}


def _seal(units: dict, prices: dict) -> tuple[Holding, ...]:
    return tuple(Holding(s, u) for s, u in sorted(units.items()) if round(u, 8) > 0.0)


def _seal_quotes(prices: dict) -> tuple[Quote, ...]:
    return tuple(Quote(s, c) for s, c in sorted(prices.items()))


def _anchor_entry(asof: date, data) -> Entry:
    return Entry(index=0, asof=asof, prior_hash=GENESIS,
                 plan=f"anchor: ${OPENING:,.0f} cash, awaiting first signal", plan_posted_on=asof,
                 opening_value=OPENING, cash_arrived=0.0, invested=0.0, days_to_invest=0, fee_paid=0.0,
                 closing_value=OPENING, quotes=_quotes(data, asof), holdings=(), violations=(),
                 note="paper anchor, no positions")


def shadow_anchor(asof: date, prices: dict, comparator: Comparator | None = None) -> Entry:
    """The witness's own anchor: the same cash, no positions, and a plan nobody may revise.

    The witness has no borrowing leg. That is not generosity, it is the definition: the benchmark does nothing with the
    deposits, and a benchmark that borrows is a second strategy rather than a floor. Every other asymmetry between the
    chains would make the comparison meaningless — same quotes, same deposits, same dates — and
    `tests/test_paper_shadow.py` checks all of them interval by interval.
    """

    return Entry(index=0, asof=asof, prior_hash=GENESIS,
                 plan="do nothing: deposit, buy on arrival, never rebalance, never borrow", plan_posted_on=asof,
                 opening_value=OPENING, cash_arrived=0.0, invested=0.0, days_to_invest=0, fee_paid=0.0,
                 closing_value=OPENING, quotes=_seal_quotes(prices), holdings=(), violations=(),
                 note=f"shadow comparator anchor; snapshot {snapshot_id()}")


def _comparator_from(config: dict) -> Comparator:
    """Rebuild the pinned witness from the config the book was anchored with.

    Never from a literal and never from a flag: a report that could choose its own benchmark is a report that can retire
    a strategy for nothing (round 70, pinned on the live artefact and on the scratch one). A witness of zero expense is
    honoured exactly as written, because a report that silently re-derives the fee it was given cannot be used to
    sensitivity-test one.
    """

    spec = config.get("comparator") or {}
    if not spec.get("weights"):
        raise SystemExit("this book's config carries no comparator spec; re-anchor it rather than guessing one")
    return Comparator(str(spec.get("name", "do nothing")), {str(k): float(v) for k, v in spec["weights"].items()},
                      float(spec.get("expense_ratio", 0.0)))


def shadow_step(chain: tuple, asof: date, arrived: float, prices: dict, comparator: Comparator | str,
                prior_hash: str, strategy_hash: str | None = None) -> Entry:
    """Advance the witnessed benchmark one interval: deposit, buy on arrival, never rebalance, never borrow.

    `comparator` takes a `Comparator` or a symbol string, so a caller holding a config and a caller holding a fund name
    can both use it: `power_horizon.py` walks this function over the study's own month-ends to check its simulator
    against the arithmetic the journal trusts, and the two agree to a quarter over sixteen years.

    `prior_hash` is the witness chain's own head hash — the field the chain is verified with, so the caller that means to
    append must supply it, and a caller building an entry to look at may supply anything. `strategy_hash` is the entry on
    the other chain this one closes against, written into the note as a back-reference: without it the two chains can be
    swapped independently and no hash on either would notice.

    The compounding is the point. A benchmark that could not compound — which is what the first version of this function
    was, through `recover_cash` — reports the deposit schedule whatever the market does, and hands every strategy in a
    rising tape a win it did not earn (round 82).
    """

    if isinstance(comparator, str):
        comparator = Comparator(f"100% {comparator}", {comparator: 1.0}, posted_fee(comparator))
    head = chain[-1]
    units = _units_of(head)
    cash = recover_cash(head, prices, arrived, units)
    pot = sum(u * prices[s] for s, u in units.items()) + cash
    rate = SPREAD_BPS / 10_000.0
    spread = bought = 0.0
    for symbol, weight in comparator.weights.items():
        price = prices[symbol]
        delta = pot * weight - units.get(symbol, 0.0) * price
        if abs(delta) < 0.005:
            continue
        held_value = units.get(symbol, 0.0) * price
        if delta > 0:
            spend = delta / (1.0 + rate)                # the fill is at the ask: `spend` buys `delta` of fund
            units[symbol] = units.get(symbol, 0.0) + spend / price
            cash -= delta
            spread += delta - spend
            bought += spend
        else:
            proceeds = -delta * (1.0 - rate)
            units[symbol] = units.get(symbol, 0.0) + delta / price
            cash += proceeds
            spread += held_value - proceeds if held_value > 0.0 else -delta * rate
    expense = _burn_fees(units, prices, {s: comparator.expense_ratio for s in comparator.weights})
    closing = cash + sum(u * prices[s] for s, u in units.items())
    return Entry(index=len(chain), asof=asof, prior_hash=prior_hash,
                 plan="do nothing: deposit, buy on arrival, never rebalance, never borrow", plan_posted_on=asof,
                 opening_value=head.closing_value, cash_arrived=arrived,
                 invested=min(bought, arrived + head.opening_value),
                 days_to_invest=30 * max(_months_apart(chain[-1].asof, asof) - 1, 0),
                 fee_paid=spread + expense, closing_value=closing,
                 quotes=_seal_quotes(prices), holdings=_seal(units, prices), violations=(),
                 note=(f"shadow expense_fee={expense:.6f} spread_fee={spread:.6f} "
                       f"expense_ratio={comparator.expense_ratio:.6f} "
                       f"closed against {(strategy_hash or prior_hash)[:16]}"))


def command_step(args) -> int:
    """Seal one interval on both chains. Money arrives, the model decides, the book pays for what it did."""

    name = _book(args)
    config = _read_config(name)
    model = str(config["model"])
    with use_book(name):
        chain = read(LEDGER)
        if not chain:
            raise SystemExit(f"book {name or '(root)'} has no anchor entry; init it first")
        head = chain[-1]
        data = load_data()
        asof = max(data.dates)
        if asof <= head.asof:
            raise SystemExit(f"book is already closed at {head.asof}; nothing new to seal")
        arrived = _deposits_due(head, asof, float(config.get("monthly", MONTHLY)))
        # How long the oldest arriving tranche had been waiting, in days: `journal.py`'s idle-cash finding is unreachable
        # while this is hard-coded to zero, and a book that skipped a seal really did hold that month's deposit in cash.
        late = 30 * max(_months_apart(head.asof, asof) - 1, 0)
        prices = {q.symbol: q.close for q in _quotes(data, asof)}
        units = _units_of(head)
        cash = recover_cash(head, prices, arrived, units)
        equity = cash + sum(u * prices[s] for s, u in units.items() if s in prices)

        signal = signal_for(data, asof, model)
        if signal is None or not signal.target_weights:
            raise SystemExit("insufficient history: the model declines rather than guessing, so nothing was sealed")
        for symbol in signal.target_weights:
            prices.setdefault(symbol, data.by_date[asof][symbol].close)
        band = float(signal.band or 0.0)
        drift = 0.0
        if band > 0.0:
            # Read from the signal at the call site on purpose: a second rebalancing rule living down here would be
            # inherited silently by the next model that does not want one.
            orders, drift = orders_within_band(signal.target_weights, units, prices, equity, cash, band)
        else:
            orders = orders_for(signal.target_weights, units, prices, equity)

        # A plan whose weights sum to at most one may not overdraft: it has told the journal it never borrows, and the
        # sealed `plan` string on every entry says so in words. Rounding a target allocation to whole units can leave a buy
        # sized a fraction of a cent past the cash that exists — round 87's rehearsal caught exactly one cent of that on a
        # band-triggered rebalance — which the engine would have booked as a loan, charged interest on, and left unflagged.
        # Trimmed here instead, so the dust stays in cash where the plan says it is. Models that DO intend leverage (the
        # shelter ladder, whose weights exceed one) are untouched: the guard reads the plan's own weights, not a list of
        # names, so a new unlevered model inherits it and a levered one cannot lose it by being forgotten.
        unlevered = sum(signal.target_weights.values()) <= 1.0 + 1e-12
        spread = bought = sold = 0.0
        for order in orders:
            if order.side == BUY:
                if unlevered and order.notional > cash > 0.0:
                    trim = cash / order.notional
                    order = Order(symbol=order.symbol, side=order.side, units=order.units * trim,
                                  notional=cash, cost=order.cost * trim)
                units[order.symbol] = units.get(order.symbol, 0.0) + order.units
                cash -= order.notional                     # gross: the spread is inside it, not beside it
                bought += order.notional
            else:
                units[order.symbol] = units.get(order.symbol, 0.0) - order.units
                cash += order.notional - order.cost
                sold += order.notional
            spread += order.cost
            if units[order.symbol] <= 0.0:
                units.pop(order.symbol)

        loan = -cash if cash < 0.0 else 0.0
        rate = _borrow_rate(data, asof)
        interest = loan * rate / 12.0 if loan > 0.0 else 0.0
        cash -= interest                                   # the loan is serviced, not merely observed
        fund_value = sum(u * prices[s] for s, u in units.items())
        expense = _burn_fees(units, prices, config.get("fees") or {})
        held = sum(u * prices[s] for s, u in units.items())
        closing = cash + held
        violations = () if held <= equity * CANDIDATE.max_weight + 1.0 else \
            (f"gross exposure {held:,.2f} passed the {CANDIDATE.max_weight:.2f}x cap at {asof}",)
        if unlevered and cash < -0.005:
            violations += (f"a plan that sums to no more than 100% of the book ended the interval owing {abs(cash):,.2f}",)
        # The note names the interest and the rate it was charged at, and the principal they were computed on. The field
        # `borrow` is the money that left the account, not the balance that caused it: `tests/test_paper.py` reads it as a
        # cost and bounds it against a tenth of the book, which is the difference between a fee and a lie about size.
        note = (f"deposit {arrived:.2f}, bought {bought:.2f}, sold {sold:.2f}"
                + (f", borrow {interest:.2f} at {rate:.2%} on {loan:.2f} borrowed" if loan > 0.0 else "")
                + f", expense {expense:.2f} on {fund_value:.2f} fund value ({_fee_split(units, prices)})"
                + (f", drift {drift:.1f} points" if band > 0.0 else "")
                + (f", MA200 read {signal.read_on} (first day of the prior month)" if signal.read_on else ""))
        entry = Entry(index=len(chain), asof=asof, prior_hash=entry_hash(head), plan=signal.name,
                      plan_posted_on=signal.read_on or asof, opening_value=head.closing_value, cash_arrived=arrived,
                      invested=min(bought, arrived + head.opening_value),
                      days_to_invest=late, fee_paid=spread + interest + expense, closing_value=closing,
                      quotes=_seal_quotes(prices), holdings=_seal(units, prices), violations=violations, note=note)
        append(LEDGER, entry)

        shadow = read(SHADOW)
        if not shadow:
            raise SystemExit("the witness chain is missing; a book without a benchmark cannot be graded")
        witness = shadow_step(shadow, asof, arrived, prices, _comparator_from(config),
                              entry_hash(shadow[-1]), entry_hash(entry))
        append(SHADOW, witness)

    print(f"  sealed {name or '(root)'} {entry.asof}  value ${entry.closing_value:,.2f}"
          f"   witness ${witness.closing_value:,.2f}"
          f"  gap {entry.closing_value - witness.closing_value:+,.2f}  fees ${entry.fee_paid:,.2f}")
    return 0


def _fees(entries: tuple) -> float:
    return sum(e.fee_paid for e in entries)


def _chain_state(report: ChainReport) -> str:
    return "chain intact" if report.ok else f"BROKEN — {report.reason}"


def _dominance(entries: tuple, shadow: tuple) -> str:
    """The P0 line: the book against the thing that cost nothing to do.

    A tie is level and is labelled level. The first version printed BEHIND … [DOMINATED] at a $0.00 gap on the anchor
    entry, which put a verdict on the ledger before a single interval had elapsed — the exact habit this journal exists to
    break. DOMINATED now appears only when the book is actually behind, and the fee line is quoted beside it because the
    whole point of sealing costs is that the gap can be attributed rather than merely observed.
    """

    if not entries or not shadow:
        return "no sealed entries yet, so no comparison"
    gap = entries[-1].closing_value - shadow[-1].closing_value
    if abs(gap) < 0.005:
        return ("LEVEL with doing-nothing by $0.00   [level at the anchor, nothing measured yet]" if len(entries) < 2
                else "LEVEL with doing-nothing by $0.00   [level so far: no edge, and no cost advantage either]")
    if gap > 0:
        return f"AHEAD of doing-nothing by ${gap:,.2f}   [skill, if it survives the rest of the record]"
    return f"BEHIND doing-nothing by ${-gap:,.2f}   [DOMINATED — the fee line is ${_fees(entries):,.2f}]"


def _verdict_line(config: dict, entries: tuple, asof: date) -> str:
    """The protocol's own sentence, unedited. The journal computes what remains before a skill claim is supportable, and
    the report's job is to print it rather than to improve on it — a book that paraphrases its own gate is a book that
    can move it. At the anchor this reads `underpowered — 23 more monthly entries, $5,000 more paid in …`, which is the
    line the round-84 report is quoted as printing.
    """

    if not entries:
        return "skill: no entries sealed, so nothing is claimable and nothing is refused"
    return f"skill: {verdict(entries, _comparator_from(config), asof).skill}"


def command_report(args) -> int:
    """Read one book. It reports against the witness the book was anchored with, and it rewrites nothing."""

    name = _book(args)
    config = _read_config(name)
    with use_book(name):
        chain = read(LEDGER)
        shadow = read(SHADOW)
        report: ChainReport = verify(LEDGER)
        witness_report: ChainReport = verify(SHADOW)
        print(f"book {name or '(root)'}   model {config['model']}"
              f"   comparator {config['comparator']['name']} at {config['comparator']['expense_ratio']:.4%}"
              f"   anchored {chain[0].asof if chain else 'never'}   snapshot {config.get('snapshot')}")
        print(f"  strategy {_chain_state(report)} ({report.entries} entries)"
              f"   witness {_chain_state(witness_report)} ({witness_report.entries} entries)")
        if not report.ok or not witness_report.ok:
            print("  DO NOT READ ANY FIGURE BELOW THIS LINE")
            return 1
        for entry in chain[1:]:
            witness = next((s.closing_value for s in shadow if s.index == entry.index), float("nan"))
            print(f"  sealed entry {entry.index}  {entry.asof}  ${entry.closing_value:,.2f}"
                  f"   witness ${witness:,.2f}  gap {entry.closing_value - witness:+9.2f}")
        if chain:
            print(f"  paid in ${chain[0].opening_value + sum(e.cash_arrived for e in chain):,.2f}"
                  f"   strategy fees ${_fees(chain):,.2f}   witness fees ${_fees(shadow):,.2f}")
            for finding in measure(chain):
                magnitude = "" if finding.magnitude_bps is None else f"  ({finding.magnitude_bps:.1f} bps/yr)"
                print(f"  {finding.kind}: {finding.detail}{magnitude}")
            print("  " + _verdict_line(config, chain, chain[-1].asof))
            print("  " + _dominance(chain, shadow))
    return 0


def command_show(args) -> int:
    """The book on one screen, including the day its rule was actually read."""

    name = _book(args)
    config = _read_config(name)
    with use_book(name):
        chain = read(LEDGER)
        print(json.dumps(config, indent=2, sort_keys=True))
        if chain:
            head = chain[-1]
            print(f"  {len(chain)} entries, last {head.asof} at ${head.closing_value:,.2f}")
            print(f"  note: {head.note}")
            if config["model"] in ("shelter", "trend") and len(chain) > 1:
                weights, _close, read_on, _want = shelter_weights(load_data(), head.asof)
                print(f"  MA200 read {read_on} (first day of the prior month) -> "
                      f"{sorted(weights) if weights else 'the rule declines'}")
    return 0


def command_compare(args) -> int:
    """Every book against its own witness: same quotes, same deposits, both chains hashed.

    The fee and witness columns are the sealed entries' own fields, not computed here. A comparison the graded party can
    recompute from its own arithmetic is not evidence — which is the reason this chain exists at all.
    """

    print("  book       model      entries        asof      value  fees paid    witness       gap  chain")
    print("  " + "-" * 102)
    for name, _path in books():
        config = _read_config(name)          # resolved before the repathing, so a book cannot be looked up twice
        with use_book(name):
            chain, shadow = read(LEDGER), read(SHADOW)
            if not chain:
                continue
            report, witness_report = verify(LEDGER), verify(SHADOW)
            head, witness = chain[-1], (shadow[-1] if shadow else None)
            status = ("intact" if report.ok and witness_report.ok
                      else "BROKEN — " + (report.reason if not report.ok else witness_report.reason))
            value = witness.closing_value if witness else float("nan")
            print(f"  {(name or '(root)'):<10}{str(config['model']):<11}{len(chain):>7}  {head.asof}"
                  f"  {head.closing_value:>10,.2f}  {head.fee_paid:>9,.2f}"
                  f"  {value:>11,.2f}  {(head.closing_value - value):+9,.2f}  {status}")
    print("  fee and witness columns are the sealed entries' own fields, not recomputed here")
    print("  a book's gap is its closing balance against its own sealed witness on the same quotes")
    return 0


# --- anchoring, the only moment anything may be chosen ----------------------

def command_init(args) -> int:
    """Anchor a new book: write its config once, then seal the same opening balance on both chains.

    Everything in the config that could be derived is derived — the comparator from `comparator_spec`, the sleeves from
    the model, the fees from the sleeves — because two fields describing one witness used to disagree by 6.45 bps in the
    file the journal trusts. The band appears only for a model that has one, so a book anchored without a band cannot
    acquire one later by editing its config, and its own test reads the raw bytes to make sure the word never appears
    there.
    """

    for flag in ("--tilt", "--band"):
        if getattr(args, flag[2:], None) is not None:
            raise SystemExit(_refusal(flag))
    name = _book(args)
    model = str(getattr(args, "model", None) or "shelter")
    if model not in MODELS:
        raise SystemExit(f"unknown model {model!r}; the book knows {', '.join(MODELS)}")
    with use_book(name):
        if LEDGER.exists() or SHADOW.exists():
            raise SystemExit("a book's chains are append-only and advance together; neither may be replaced alone")
        symbol = getattr(args, "comparator", None)
        if symbol is None:
            symbol = TILT_COMPARATOR if model in ("tilt", "tilt_band") else CANDIDATE_SERIES
        spec = comparator_spec(str(symbol))
        requested = getattr(args, "asof", None)
        data = load_data(requested)
        asof = requested if requested is not None and requested in data.by_date else max(data.dates)
        config = {"model": model, "model_key": model, "sleeves": list(book_sleeves(model)),
                  "fees": book_fees(model), "comparator": spec, "expense_ratio": spec["expense_ratio"],
                  "opening": OPENING, "monthly": MONTHLY, "spread_bps": SPREAD_BPS, "snapshot": snapshot_id(),
                  "trend_reading": TREND_READING if model in ("shelter", "trend") else None}
        if model == "tilt_band":
            config["rebalance_band_points"] = TILT_BAND_POINTS
        PAPER_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        anchor = _anchor_entry(asof, data)
        create_ledger(LEDGER, anchor)
        create_ledger(SHADOW, shadow_anchor(asof, {q.symbol: q.close for q in anchor.quotes}))
    print(f"  anchored {name or '(root)'} as {model} on {asof} against {spec['name']} at {spec['expense_ratio']:.4%},"
          f" snapshot {config['snapshot']}, opening ${OPENING:,.0f} and ${MONTHLY:,.0f} a month")
    return 0


def _refusal(flag: str) -> str:
    if flag == "--tilt":
        return (f"--tilt is refused: the tilt weight is not a caller's choice. It is `paper.TILT_WEIGHT`"
                f" ({TILT_WEIGHT:.0%}), the control row of `mix_sweep.MIXES`, pinned there by a test. The reason the"
                " book exists is that the weight was measured rather than picked.")
    return (f"--band is refused: the drift band is not a caller's choice. It is `paper.TILT_BAND_POINTS`"
            f" ({TILT_BAND_POINTS:g} points), pinned to the regime in `rebalance_cost.REGIMES` that produced it."
            " If the band must change, change that table and the test that reads it, and the book changes with it.")


# --- books, and the one way to name them ------------------------------------

_BOOK_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")


def _check_book_name(name: str) -> str:
    """A book name is a directory name, so it gets the checks that implies. A ledger you can escape from with two dots is
    not a separate account, it is a suggestion."""

    if not _BOOK_NAME.match(name):
        raise SystemExit(f"book names are 1-32 characters of letters, digits, dash and underscore, not starting with a"
                         f" dot or a dash; refused {name!r}")
    return name


def _book(args) -> str:
    name = str(getattr(args, "book", "") or "")
    return _check_book_name(name) if name else ""


def _book_dir(name: str) -> Path:
    return PAPER_DIR if not name else PAPER_DIR / "books" / _check_book_name(name)


@contextlib.contextmanager
def use_book(name: str = ""):
    """Point the module's four paths at one book, then put them back. `""` is the root book.

    The four are repathed together or not at all: a book whose config is the root's and whose ledger is its own is how a
    scratch book gets graded against somebody else's benchmark.
    """

    global PAPER_DIR, LEDGER, SHADOW, CONFIG
    directory = _book_dir(name)
    saved = (PAPER_DIR, LEDGER, SHADOW, CONFIG)
    PAPER_DIR = directory
    LEDGER = directory / "ledger.jsonl"
    SHADOW = directory / "shadow.jsonl"
    CONFIG = directory / "model.json"
    try:
        yield directory
    finally:
        PAPER_DIR, LEDGER, SHADOW, CONFIG = saved


def books():
    """The root book first, then every named book that has a ledger — not merely a directory, which is how a
    half-written init would otherwise appear as a book with no entries and no explanation."""

    yield "", PAPER_DIR
    shelf = PAPER_DIR / "books"
    if shelf.is_dir():
        for path in sorted(shelf.iterdir()):
            if (path / "ledger.jsonl").exists():
                yield path.name, path


def _read_config(name: str) -> dict:
    path = _book_dir(name) / "model.json"
    if not path.exists():
        raise SystemExit(f"book {name or '(root)'} has no config at {path}; nothing here is guessed")
    config = json.loads(path.read_text(encoding="utf-8"))
    if str(config.get("model", "")) not in MODELS:
        raise SystemExit(f"{path} names a model this book does not know")
    return config


# --- the command line -------------------------------------------------------

def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="the forward book: an append-only account of a model nobody has graded yet")
    sub = ap.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="anchor a new book; the only moment any of its inputs may be set")
    init.add_argument("--model", default="shelter", choices=MODELS)
    init.add_argument("--book", default="", help="a name for a book kept beside the root one")
    init.add_argument("--comparator", default=None, help="a posted fund to witness against; defaults to the model's own")
    init.add_argument("--asof", default=None, type=date.fromisoformat, help="seal the anchor at this session")
    init.add_argument("--tilt", type=float, default=None, help="refused: the weight was measured, not chosen")
    init.add_argument("--band", type=float, default=None, help="refused: the band was measured, not chosen")

    for cmd in ("step", "report", "show", "compare"):
        sub.add_parser(cmd).add_argument("--book", default="", help="a book beside the root one")

    args = ap.parse_args(argv)
    if args.command == "init" and (args.tilt is not None or args.band is not None):
        # Refused here, before a book is touched: a flag that was parsed and then quietly ignored would leave the caller
        # holding a book anchored at a number they believe they chose.
        raise SystemExit(_refusal("--tilt" if args.tilt is not None else "--band"))
    handler = {"init": command_init, "step": command_step, "report": command_report,
               "show": command_show, "compare": command_compare}[args.command]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
