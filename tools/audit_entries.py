"""Audit every sealed entry against its own numbers, and stop the programme if one of them contradicts another.

Stopping rule 4 has always read "any sealed entry whose plan line contradicts its own numbers". It is the one condition in the
runbook that this project has actually been caught by: round 87 sealed an interval whose note said `borrow 0.00 at 5.91% on 0.01
borrowed` while the entry's own `plan` string promised the book never borrows, and its `violations` field was empty. The engine
was fixed that round, but the *check* was never written, which means the rule still had no command behind it and the same class of
error — a number in one field disagreeing with a number in another — would have arrived silently again.

So this file reads each sealed entry and asks it to account for itself. Everything below is derived from the sealed record; no
corpus is loaded, no market data is fetched, and no model is consulted about what it *means*, only about what it *sums to*.

`sequence`      Indices increase by one and dates increase. A ledger with a gap in it is not a ledger.
`anchor`        The first entry holds nothing and is worth what was paid in. The engine opens an account with cash and buys
                nothing until the first interval closes; a book that arrived already invested did not get there by this engine.
`priced`        Every held symbol has a sealed price on the entry that holds it. An unpriceable holding is a value nobody
                computed.
`undeclared-loan` Implied cash is `closing − holdings at the sealed quotes`, computed by `paper.recover_cash` rather than by a
                second implementation of the same subtle rule (round 82). Negative by more than a cent, with no borrow clause in
                the note, is the round-87 defect: money owed that no field admits.
`leverage`      A loan that IS declared, on a model whose plan says it never borrows (`tilt`, `tilt_band`). Levered models — the
                shelter ladder, the constant-over-100 book — are not flagged for borrowing; they are flagged for borrowing
                without saying so, which the check above already catches.
`free-trade`    The note reports money bought or sold and the entry reports zero cost. Every order in this archive has a price.
`cadence`       The transfer that arrived equals what `paper._deposits_due` says was due between this seal and the last, given
                the model's own monthly figure. Round 84's defect class: a seal that forgives a missed month, or funds the
                anchor month twice, changes paid-in, which is the denominator of every return reported here.
`idle`          `days_to_invest` equals 30 days per month of delay beyond the first. The ledger's own complaint about cash
                sitting uninvested only means something if the field is filled in.
`unreadable`    The entry could not even be constructed. `journal.Entry` refuses a plan posted after its own interval closes —
                the protocol's own anti-lookahead guard — so a ledger carrying one is not auditable, which is a finding rather
                than a traceback.
`violation`     Any entry whose `violations` field is not empty. Not a contradiction — a confession. Reported here so the same
                screen shows both.

Usage:

    .venv/bin/python tools/audit_entries.py                 # every book and the root record
    .venv/bin/python tools/audit_entries.py --book tilt_band
    .venv/bin/python tools/audit_entries.py --json

It exits non-zero on any finding, and a clean run says so explicitly rather than printing nothing: `not tested` and `nothing
found` have to look different on screen, because the difference between them is the thing that keeps an audit honest.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                           # noqa: E402
from boring_alpha import journal                      # noqa: E402

UNLEVERED = ("tilt", "tilt_band")      # models whose sealed plan text says, in words, that they never borrow
CASH_TOLERANCE = 0.005                 # round 87's cent: the engine now trims instead of borrowing it
BOUGHT = re.compile(r"bought ([\d.]+)")
SOLD = re.compile(r"sold ([\d.]+)")
BORROWED = re.compile(r"on ([\d.]+) borrowed")


def books() -> list[str]:
    """Every book beside the root record, and the root record itself, which is audited too."""

    directory = paper.PAPER_DIR / "books"
    found = sorted(d.name for d in directory.iterdir() if (d / "ledger.jsonl").exists()) if directory.exists() else []
    return ["root", *found]


def _num(pattern: re.Pattern, text: str) -> float:
    """The first number a label carries in the note, or zero where the label is absent."""

    match = pattern.search(text)
    return float(match[1]) if match else 0.0


def months_apart(before: dt.date, after: dt.date) -> int:
    return (after.year - before.year) * 12 + (after.month - before.month)


def audit(chain: tuple, model: dict) -> list[dict]:
    """Every contradiction in one chain, as findings rather than as a boolean."""

    findings: list[dict] = []

    def add(kind: str, entry: journal.Entry, detail: str) -> None:
        findings.append({"kind": kind, "index": entry.index, "asof": entry.asof.isoformat(), "detail": detail})

    monthly = float(model.get("monthly", paper.MONTHLY))
    opening = float(model.get("opening", paper.OPENING))
    model_key = str(model.get("model") or model.get("model_key") or "")

    previous: journal.Entry | None = None
    for position, entry in enumerate(chain):
        prices = {q.symbol: q.close for q in entry.quotes}
        units = {h.symbol: h.units for h in entry.holdings}

        if entry.index != position:
            add("sequence", entry, f"index {entry.index} follows {position - 1}; a ledger with a gap is not a ledger")
        if previous and entry.asof <= previous.asof:
            add("sequence", entry, f"{entry.asof} does not follow {previous.asof}")
        if position == 0:
            if entry.holdings:
                add("anchor", entry, f"the first entry already holds {len(entry.holdings)} position(s); this engine buys "
                                     f"nothing until the first interval closes")
            if abs(entry.closing_value - opening) > 0.005:
                add("anchor", entry, f"the account opened worth {entry.closing_value:,.2f} against {opening:,.2f} paid in")

        unpriced = [s for s in units if units[s] and s not in prices]
        if unpriced:
            add("priced", entry, f"holds {', '.join(sorted(unpriced))} with no sealed price on the entry that holds it")
            # Everything below needs a price. `paper.recover_cash` deliberately raises on an unquoted symbol rather than guess
            # one, and an audit that crashes has reported less than an audit that names the missing price.
            previous = entry
            continue

        bought, sold, declared = _num(BOUGHT, entry.note), _num(SOLD, entry.note), _num(BORROWED, entry.note)
        implied_cash = paper.recover_cash(entry, prices, 0.0, units)
        if implied_cash < -CASH_TOLERANCE:
            if declared <= 0.0:
                add("undeclared-loan", entry, f"holdings are worth {-implied_cash:,.2f} more than the entry's balance, and no "
                                              f"field admits a loan")
            elif model_key in UNLEVERED:
                add("leverage", entry, f"the entry declares {declared:,.2f} borrowed; `{model_key}` is a plan that says it "
                                       f"never borrows")
        if bought + sold > 0.01 and entry.fee_paid <= 0.0:
            add("free-trade", entry, f"{bought:,.2f} bought and {sold:,.2f} sold with no cost on the entry that did it")

        if previous is not None:
            due = paper._deposits_due(previous, entry.asof, monthly)
            if abs(entry.cash_arrived - due) > 0.005:
                add("cadence", entry, f"{entry.cash_arrived:,.2f} arrived where the schedule owed {due:,.2f} since "
                                      f"{previous.asof}")
            gap = months_apart(previous.asof, entry.asof)
            expected_idle = 30 * max(gap - 1, 0)
            if entry.days_to_invest != expected_idle:
                add("idle", entry, f"days_to_invest is {entry.days_to_invest} where a {gap}-month gap makes it "
                                   f"{expected_idle}")

        for violation in entry.violations:
            add("violation", entry, violation)
        previous = entry
    return findings


def model_file(book: str) -> Path:
    return paper.PAPER_DIR / ("model.json" if book == "root" else f"books/{book}/model.json")


def audit_book(book: str) -> dict:
    path = paper.PAPER_DIR / ("ledger.jsonl" if book == "root" else f"books/{book}/ledger.jsonl")
    if not path.exists():
        raise SystemExit(f"no ledger at {path}")
    try:
        verified = bool(paper.verify(path))
        chain = paper.read(path) if verified else ()
    except ValueError as exc:
        # A line that will not construct is not a clean chain and not a crash: it is the one kind of finding rule 4 exists for.
        return {"book": book, "entries": 0, "sealed_fees": 0.0,
                "findings": [{"kind": "unreadable", "index": -1, "asof": "?", "detail": f"{path.name}: {exc}"}]}
    if not verified:
        raise SystemExit(f"refusing to audit a chain that does not verify: {path}")
    source = model_file(book)
    model = json.loads(source.read_text()) if source.exists() else {}
    return {"book": book, "entries": len(chain), "findings": audit(chain, model),
            "sealed_fees": sum(e.fee_paid for e in chain)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--book", default=None, help="one book, or the root record with --book root")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    reports = [audit_book(name) for name in ([args.book] if args.book else books())]
    total = sum(len(r["findings"]) for r in reports)
    if args.json:
        print(json.dumps({"audited": len(reports), "findings": total, "books": reports}, indent=2))
        return 1 if total else 0

    print(f"# entry audit: {len(reports)} record(s), {total} finding(s)")
    for report in reports:
        if not report["entries"]:
            print(f"  {report['book']:<12} not tested: the chain is empty")
            continue
        if not report["findings"]:
            print(f"  {report['book']:<12} clean — {report['entries']} entries account for themselves"
                  f" (sealed fees ${report['sealed_fees']:,.2f})")
            continue
        print(f"  {report['book']:<12} {len(report['findings'])} finding(s) in {report['entries']} entries")
        for finding in report["findings"]:
            print(f"      {finding['kind']:<16} entry {finding['index']} on {finding['asof']}: {finding['detail']}")
    if total:
        print("\n  Stopping rule 4: an entry that contradicts itself stops the programme until it is understood.")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
