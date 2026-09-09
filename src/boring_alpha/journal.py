"""A forward journal: an append-only record of what was planned, done, and paid.

This is the only instrument in the repository that can produce evidence nobody has
seen. Everything else runs on prices that are already public, which means every
result it produces is a claim about history, and history has been looked at a lot.
The trend family has had three evaluations, and a fourth idea died on a diagnostic,
all against the same twenty-odd years. A backtest cannot recover from that; a
ledger can, because it accumulates dates that no model has touched.

Three properties are load-bearing, and each one rejects an easier design:

**Append-only, hash-chained.** Each entry embeds the hash of the entry before it.
Rewriting any past entry invalidates every hash after it, so a plan that was
changed after the fills cannot be passed off as the original plan. A plain log
file gives no such guarantee, which is why the plan text lives inside the hashed
payload rather than in a comment beside it.

**The comparator is computed from the journal's own quotes.** Each entry records
the closing price of every pinned comparator symbol on the entry date. The
do-nothing benchmark is then replayed from those same prices, with the same money
arriving on the same dates. Nothing is fetched later to reconstruct the
comparison, so the comparison cannot be re-selected once the outcome is known —
which is the failure mode the BA-004 grid exposed, where the benchmark was chosen
to be the thing the strategy already held.

**Two verdicts, kept apart.** Costs and delays are *measured*, so they are
decisive from the first entry: a fee is a fee. Skill against the comparator is
*inferred*, and inference from a handful of months on a small account is
indistinguishable from noise, so `verdict()` refuses to render one before the
minimum is met and prints what remains. A tool that hands out premature skill
verdicts is worse than no tool, because it will be used.

Prices come from the entry itself rather than a data fetch, so the ledger is
self-contained and needs no network and no re-authorised snapshot to keep running.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path

from boring_alpha.metrics.cashflow import CashFlow, money_weighted_return

PROTOCOL_VERSION = 1

#: Skill verdicts before this many entries are noise, not evidence. Two years is
#: short enough to be reachable and long enough that one lucky month cannot carry
#: the whole claim. Overridable, but the default is the pre-registered figure.
MIN_ENTRIES_FOR_SKILL_VERDICT = 24

#: Below this the shortfall in basis points is arithmetically meaningless, because
#: a dollar or two of rounding moves it by tens of bps. Measured in dollars paid in.
MIN_CONTRIBUTIONS_FOR_SKILL_VERDICT = 10_000.0

BUY = "BUY"
SELL = "SELL"


class ChainBroken(Exception):
    """The ledger's hashes do not chain. Treat the file as damaged, not as data."""


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    close: float


@dataclass(frozen=True, slots=True)
class Holding:
    symbol: str
    units: float


@dataclass(frozen=True, slots=True)
class Entry:
    """One closing interval. The whole payload is hashed, including the plan."""

    index: int
    asof: date
    prior_hash: str
    plan: str
    plan_posted_on: date
    opening_value: float
    cash_arrived: float
    invested: float
    days_to_invest: int
    fee_paid: float
    closing_value: float
    quotes: tuple[Quote, ...]
    holdings: tuple[Holding, ...]
    violations: tuple[str, ...]
    note: str

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("entry index must not be negative")
        if self.plan_posted_on > self.asof:
            raise ValueError("a plan cannot be posted after the interval it plans closes")
        if self.opening_value < 0.0 or self.closing_value < 0.0:
            raise ValueError("account values must not be negative")
        if self.cash_arrived < 0.0 or self.invested < 0.0:
            raise ValueError("cash arrived and invested must not be negative")
        if self.invested > self.cash_arrived + self.opening_value:
            raise ValueError("cannot invest more than arrived plus what the account held")
        if self.days_to_invest < 0 or self.fee_paid < 0.0:
            raise ValueError("delay and fees must not be negative")
        if not self.quotes:
            raise ValueError("an entry with no comparator quotes cannot compute a benchmark")

    def quote(self, symbol: str) -> float:
        for row in self.quotes:
            if row.symbol == symbol:
                return row.close
        raise KeyError(f"comparator quote {symbol!r} missing from entry {self.index}")


def payload(entry: Entry) -> dict:
    """Canonical dict form. Key order and date format are fixed, so hashes are stable."""

    return {
        "protocol": PROTOCOL_VERSION,
        "index": entry.index,
        "asof": entry.asof.isoformat(),
        "prior_hash": entry.prior_hash,
        "plan": entry.plan,
        "plan_posted_on": entry.plan_posted_on.isoformat(),
        "opening_value": round(entry.opening_value, 2),
        "cash_arrived": round(entry.cash_arrived, 2),
        "invested": round(entry.invested, 2),
        "days_to_invest": entry.days_to_invest,
        "fee_paid": round(entry.fee_paid, 2),
        "closing_value": round(entry.closing_value, 2),
        "quotes": [[q.symbol, round(q.close, 6)] for q in sorted(entry.quotes, key=lambda x: x.symbol)],
        "holdings": [[h.symbol, round(h.units, 8)] for h in sorted(entry.holdings, key=lambda x: x.symbol)],
        "violations": list(entry.violations),
        "note": entry.note,
    }


def entry_hash(entry: Entry) -> str:
    blob = json.dumps(payload(entry), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


GENESIS = "0" * 64


def _to_entry(raw: dict) -> Entry:
    return Entry(
        index=raw["index"],
        asof=date.fromisoformat(raw["asof"]),
        prior_hash=raw["prior_hash"],
        plan=raw["plan"],
        plan_posted_on=date.fromisoformat(raw["plan_posted_on"]),
        opening_value=raw["opening_value"],
        cash_arrived=raw["cash_arrived"],
        invested=raw["invested"],
        days_to_invest=raw["days_to_invest"],
        fee_paid=raw["fee_paid"],
        closing_value=raw["closing_value"],
        quotes=tuple(Quote(s, c) for s, c in raw["quotes"]),
        holdings=tuple(Holding(s, u) for s, u in raw["holdings"]),
        violations=tuple(raw["violations"]),
        note=raw["note"],
    )


def _to_raw(entry: Entry) -> dict:
    raw = payload(entry)
    raw["hash"] = entry_hash(entry)
    return raw


def create_ledger(path: Path, first: Entry) -> str:
    if first.index != 0 or first.prior_hash != GENESIS:
        raise ValueError("the first entry must have index 0 and the genesis hash")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text().strip():
        raise ValueError("ledger exists and is append-only; refusing to overwrite it")
    path.write_text(json.dumps(_to_raw(first), sort_keys=True) + "\n", encoding="utf-8")
    return first.prior_hash


def append(path: Path, entry: Entry) -> None:
    """Verify the chain, then add one entry. Never rewrites what is already there."""

    rows = read(path)
    head = rows[-1]
    if entry.index != head.index + 1:
        raise ValueError(f"expected index {head.index + 1}, got {entry.index}")
    expected = entry_hash(head)
    if entry.prior_hash != expected:
        raise ValueError(
            f"prior_hash mismatch: entry {head.index} hashes to {expected}, "
            f"entry {entry.index} claims {entry.prior_hash}"
        )
    if entry.asof <= head.asof:
        raise ValueError("entries must move forward in time")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_to_raw(entry), sort_keys=True) + "\n")


def read(path: Path) -> tuple[Entry, ...]:
    if not path.exists():
        return ()
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(_to_entry(json.loads(line)))
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class ChainReport:
    ok: bool
    entries: int
    broken_at: int | None
    reason: str

    def __bool__(self) -> bool:
        return self.ok


def verify(path: Path) -> ChainReport:
    """Recompute every hash and link. Trust no stored hash."""

    rows = read(path)
    if not rows:
        return ChainReport(False, 0, None, "no entries")
    for position, entry in enumerate(rows):
        expected_link = GENESIS if position == 0 else entry_hash(rows[position - 1])
        if entry.index != position:
            return ChainReport(False, len(rows), position, f"index is {entry.index}, expected {position}")
        if entry.prior_hash != expected_link:
            return ChainReport(False, len(rows), position, "prior hash does not match the stored entry")
        stored = json.loads(path.read_text(encoding="utf-8").splitlines()[position]).get("hash")
        if stored != entry_hash(entry):
            return ChainReport(False, len(rows), position, f"stored hash does not match recomputed {entry_hash(entry)}")
    return ChainReport(True, len(rows), None, "chain intact")


# --- the comparator, replayed from the journal's own prices -------------------


@dataclass(frozen=True, slots=True)
class Comparator:
    """What doing nothing would have paid, on the journal's own quotes.

    `weight` is one portfolio, not a menu: the bar is a single pinned thing. A
    comparator set with several members invites picking the winner afterwards,
    which is the exact error the P0 rule exists to prevent.
    """

    name: str
    weights: dict[str, float]
    expense_ratio: float

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"comparator weights must sum to 1, got {total}")


def comparator_flows(entries: tuple[Entry, ...]) -> tuple[CashFlow, ...]:
    """Deposits are dated at the start of the interval they are invested within.

    `cash_arrived` on entry *i* is money that entered during the interval closing at
    `entries[i].asof`, so it earns the return of that interval and no earlier. Date
    it at `asof` instead and every deposit silently loses a month of growth, which
    would flatter every strategy ever compared against this benchmark.
    """

    ordered = sorted(entries, key=lambda e: e.asof)
    return tuple(
        CashFlow(ordered[position - 1].asof, ordered[position].cash_arrived)
        for position in range(1, len(ordered))
        if ordered[position].cash_arrived > 0.0
    )


def comparator_path(entries: tuple[Entry, ...], comparator: Comparator) -> float:
    """Ending value of doing nothing, from the journal's own quotes."""

    ordered = sorted(entries, key=lambda e: e.asof)
    if len(ordered) < 2:
        raise ValueError("a comparator path needs at least two entries to price an interval")
    value = ordered[0].opening_value
    previous = {q.symbol: q.close for q in ordered[0].quotes}
    for position in range(1, len(ordered)):
        entry, prior = ordered[position], ordered[position - 1]
        value += entry.cash_arrived - entry.fee_paid
        gross, priced = 1.0, 0
        for quote in entry.quotes:
            weight = comparator.weights.get(quote.symbol)
            before = previous.get(quote.symbol)
            if weight and before:
                gross *= (quote.close / before) ** weight
                priced += 1
        if priced != len(comparator.weights):
            raise ValueError(
                f"entry {entry.index} prices {priced} of {len(comparator.weights)} pinned "
                f"comparator legs; a benchmark that cannot be priced is not a benchmark"
            )
        elapsed = max(1, (entry.asof - prior.asof).days)
        value *= gross * (1.0 - comparator.expense_ratio) ** (elapsed / 365.2425)
        previous = {q.symbol: q.close for q in entry.quotes}
    return value


def comparator_return(
    entries: tuple[Entry, ...],
    comparator: Comparator,
    opening_value: float,
    period_end: date,
) -> float:
    """Money-weighted return of doing nothing, driven by identical cash.

    Same money, same dates, same prices, no strategy. Commissions are zero,
    because the comparator is the thing that could have been done for free: this
    is generous to it by construction, so losing to it is never a rounding error.
    """

    value = comparator_path(entries, comparator)
    return money_weighted_return(
        sorted(entries, key=lambda e: e.asof)[0].asof, opening_value, period_end,
        value, comparator_flows(entries),
    )


def account_return(entries: tuple[Entry, ...], period_end: date) -> float:
    """Money-weighted return of the real account, net of every fee it reported.

    Uses the same interval convention as `comparator_flows`, or the two paths
    would differ by timing before either one contained a single bad decision.
    """

    ordered = sorted(entries, key=lambda e: e.asof)
    return money_weighted_return(
        ordered[0].asof, ordered[0].opening_value, period_end, ordered[-1].closing_value,
        comparator_flows(entries),
    )


# --- two verdicts, deliberately kept apart -----------------------------------


@dataclass(frozen=True, slots=True)
class Finding:
    kind: str
    detail: str
    magnitude_bps: float | None


@dataclass(frozen=True, slots=True)
class Verdict:
    measured: tuple[Finding, ...]
    skill: str
    shortfall_bps: float | None
    entries: int
    paid_in: float
    total_fees: float


def measure(entries: tuple[Entry, ...]) -> tuple[Finding, ...]:
    """Layer 1: costs and delays. Measured, therefore decisive from entry one."""

    findings: list[Finding] = []
    if not entries:
        return ()
    paid_in = sum(e.cash_arrived for e in entries)
    fees = sum(e.fee_paid for e in entries)
    if fees > 0.0:
        balance = sum((e.opening_value + e.closing_value) / 2.0 for e in entries) / len(entries)
        years = max(1.0, (entries[-1].asof - entries[0].asof).days / 365.2425)
        bps = fees / max(balance, 1.0) / years * 10_000.0
        findings.append(Finding("fees", f"${fees:,.2f} charged on ~${balance:,.0f} avg balance", bps))
        if paid_in > 0 and fees / paid_in > 0.005:
            findings.append(
                Finding("fee ratio", f"fees are {fees / paid_in * 100:.2f}% of everything deposited", None)
            )
    late = [e for e in entries if e.days_to_invest > 3]
    if late:
        idle = sum(e.cash_arrived * e.days_to_invest for e in entries)
        findings.append(
            Finding(
                "idle cash",
                f"{len(late)} of {len(entries)} intervals held cash more than 3 days; "
                f"{idle:,.0f} dollar-days sat uninvested",
                None,
            )
        )
    offending = [e for e in entries if e.violations]
    for entry in offending:
        for violation in entry.violations:
            findings.append(
                Finding("violation", f"entry {entry.index} ({entry.asof}): {violation}", None)
            )
    return tuple(findings)


def verdict(
    entries: tuple[Entry, ...],
    comparator: Comparator,
    period_end: date,
    min_entries: int = MIN_ENTRIES_FOR_SKILL_VERDICT,
    min_paid_in: float = MIN_CONTRIBUTIONS_FOR_SKILL_VERDICT,
) -> Verdict:
    """Cost findings always; a skill claim only when it would mean something."""

    if not entries:
        raise ValueError("no entries to judge")
    paid_in = entries[0].opening_value + sum(e.cash_arrived for e in entries)
    findings = measure(entries)
    shortfall: float | None = None
    skill = "withheld"
    blockers = []
    if len(entries) < min_entries:
        blockers.append(f"{min_entries - len(entries)} more monthly entries")
    if paid_in < min_paid_in:
        blockers.append(f"${min_paid_in - paid_in:,.0f} more paid in")
    if not blockers:
        mine = account_return(entries, period_end)
        theirs = comparator_return(entries, comparator, entries[0].opening_value, period_end)
        shortfall = (mine - theirs) * 10_000.0
        skill = "beat" if shortfall > 0.0 else "did not beat"
    else:
        skill = "underpowered — " + ", ".join(blockers) + " required before a skill claim"
    return Verdict(
        measured=findings,
        skill=skill,
        shortfall_bps=shortfall,
        entries=len(entries),
        paid_in=paid_in,
        total_fees=sum(e.fee_paid for e in entries),
    )
