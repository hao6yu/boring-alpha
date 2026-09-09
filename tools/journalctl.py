"""Record a month, check the chain, and be told what it cost.

    .venv/bin/python tools/journalctl.py init      # once, from the authorised snapshot
    .venv/bin/python tools/journalctl.py close     # once a month, interactively
    .venv/bin/python tools/journalctl.py report     # two verdicts, kept apart
    .venv/bin/python tools/journalctl.py verify     # who edited this?

`init` anchors the ledger at a real date using the already-authorised snapshot, so
the comparator has a starting price before any money exists. `close` refuses to
record an interval whose plan was not declared first, and `report` refuses to call
a few months of a small account evidence about skill. The point is not a nicer
spreadsheet: it is that the number it eventually produces cannot be argued with.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from boring_alpha.data.csv_loader import load_csv_market_data
from boring_alpha.journal import (
    GENESIS,
    Comparator,
    Entry,
    Holding,
    Quote,
    append,
    create_ledger,
    entry_hash,
    read,
    verdict,
    verify,
)

import labdata                                              # noqa: E402  the same resolver `paper.py` uses, so the two agree

JOURNAL_DIR = labdata.data_root() / "journal"
LEDGER = JOURNAL_DIR / "ledger.jsonl"
SPEC = JOURNAL_DIR / "comparator.json"
# Deliberately NOT resolved through `labdata`: this directory is the anchor `verify` checks the chain against, and an override that
# could move an anchor would turn a verification tool into a way of passing. A rehearsal verifies a *copy* of the chain, and the anchor
# stays where it was pinned.
SNAPSHOT_DIR = ROOT / "data" / "snapshots" / "20260904T192633Z"
SNAPSHOT = SNAPSHOT_DIR / "market_daily.csv"
CASH_FILE = SNAPSHOT_DIR / "cash_daily.csv"


def spec_hash() -> str:
    return hashlib.sha256(SPEC.read_bytes()).hexdigest()


def load_comparator() -> Comparator:
    """Load the pinned comparator and refuse it if the file has been edited."""

    if not SPEC.exists():
        raise SystemExit("no comparator pinned. run `journalctl.py init` first.")
    raw = json.loads(SPEC.read_text(encoding="utf-8"))
    pinned = raw.pop("protocol_hash", None)
    body = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    computed = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if pinned is not None and pinned != computed:
        raise SystemExit(
            f"comparator spec has been edited after pinning ({computed} != {pinned}).\n"
            "Amending the benchmark after the fact is the exact failure this journal "
            "exists to prevent. Re-pin it in the protocol document, in writing, first."
        )
    return Comparator(raw["name"], raw["weights"], raw["expense_ratio"])


def command_init(args: argparse.Namespace) -> None:
    if LEDGER.exists():
        raise SystemExit(f"ledger already exists at {LEDGER}; it is append-only")
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    body = {"name": args.name, "weights": args.weights, "expense_ratio": args.fee,
            "pinned_on": date.today().isoformat()}
    SPEC.write_text(
        json.dumps(
            {**body, "protocol_hash": hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()},
            sort_keys=True, indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    data = load_csv_market_data(SNAPSHOT, CASH_FILE, end=args.asof)
    quotes = tuple(
        Quote(symbol, data.by_date[max(data.by_date)][symbol].close)
        for symbol in sorted(args.weights)
        if symbol in data.by_date[max(data.by_date)]
    )
    if len(quotes) != len(args.weights):
        raise SystemExit("every pinned comparator leg needs a price at the anchor date")

    first = Entry(
        index=0, asof=args.asof, prior_hash=GENESIS,
        plan=args.plan, plan_posted_on=args.asof,
        opening_value=args.opening, cash_arrived=0.0, invested=0.0,
        days_to_invest=0, fee_paid=0.0, closing_value=args.opening,
        quotes=quotes, holdings=(), violations=(),
        note="anchor entry, priced from snapshot 20260904T192633Z",
    )
    create_ledger(LEDGER, first)
    print(f"ledger anchored at {args.asof}, {len(quotes)} legs priced")
    pinned = json.loads(SPEC.read_text())["protocol_hash"]
    print(f"comparator: {args.name} @ {args.fee * 100:.4f}%, protocol hash {pinned}")
    print("pin that hash in docs/reviews/FORWARD-JOURNAL-protocol.md before the first fill.")


def _ask(prompt: str, cast=float, allow_blank=False):
    while True:
        raw = input(prompt).strip()
        if not raw and allow_blank:
            return None
        try:
            return cast(raw)
        except ValueError:
            print(f"  expected a {cast.__name__}, try again")


def command_close(args: argparse.Namespace) -> None:
    rows = read(LEDGER)
    if not rows:
        raise SystemExit("no ledger. run `journalctl.py init` first.")
    head = rows[-1]
    comparator = load_comparator()
    print(f"closing interval {len(rows)} (previous entry: {head.asof})\n")

    plan = input("  plan, as declared before you acted: ").strip()
    posted = date.fromisoformat(input("  date that plan was written down [YYYY-MM-DD]: "))
    opening = _ask(f"  account value at interval start [${head.closing_value:,.2f}]: ") or head.closing_value
    arrived = _ask("  new cash deposited during the interval: $")
    invested = _ask(f"  of which, actually invested [{arrived:,.2f}]: ") or arrived
    days = _ask("  days that money sat before it was invested [0]: ", int, allow_blank=True) or 0
    fees = _ask("  all platform fees and commissions charged [0]: ", float, allow_blank=True) or 0.0
    closing = _ask("  account value at interval close: $")
    asof = date.fromisoformat(input("  interval closing date [YYYY-MM-DD]: "))

    print("  closing prices for the pinned comparator legs:")
    quotes = []
    for symbol in sorted(comparator.weights):
        quotes.append(Quote(symbol, _ask(f"    {symbol} close: ")))

    violations = []
    while True:
        line = input("  declared violation, or Enter for none: ").strip()
        if not line:
            break
        violations.append(line)

    units = []
    for symbol in sorted(comparator.weights):
        held = _ask(f"  units of {symbol} held at close [0]: ", float, allow_blank=True) or 0.0
        if held:
            units.append(Holding(symbol, held))

    entry = Entry(
        index=len(rows), asof=asof, prior_hash=entry_hash(head), plan=plan,
        plan_posted_on=posted, opening_value=opening, cash_arrived=arrived,
        invested=invested, days_to_invest=days, fee_paid=fees, closing_value=closing,
        quotes=tuple(quotes), holdings=tuple(units), violations=tuple(violations),
        note=input("  note, or Enter: ").strip(),
    )
    append(LEDGER, entry)
    print(f"\nentry {entry.index} sealed at {entry_hash(entry)[:16]}")


def command_report(args: argparse.Namespace) -> None:
    rows = read(LEDGER)
    if not rows:
        raise SystemExit("no ledger.")
    chain = verify(LEDGER)
    report = verdict(rows, load_comparator(), rows[-1].asof)
    paid_in = report.paid_in

    print(f"ledger: {report.entries} entries, chain {'intact' if chain else 'BROKEN at ' + str(chain.broken_at)}")
    print(f"paid in ${paid_in:,.2f}, fees charged ${report.total_fees:,.2f}\n")

    print("LAYER 1 — measured. True regardless of what the market did.")
    if not report.measured:
        print("  nothing found: no fees, no declared delay past 3 days, no violations.")
    for finding in report.measured:
        cost = "" if finding.magnitude_bps is None else f"  {finding.magnitude_bps:,.1f} bps/yr"
        print(f"  [{finding.kind}] {finding.detail}{cost}")

    print("\nLAYER 2 — inferred. Needs the gate to mean anything.")
    if report.shortfall_bps is None:
        print(f"  {report.skill}.")
        print("  Cost findings above are still fully actionable. A fee is not underpowered.")
    else:
        direction = "beat" if report.shortfall_bps > 0 else "lost to"
        print(f"  {direction} the pinned comparator by {abs(report.shortfall_bps):,.1f} bps.")
        print("  Two years is enough to be informative and not enough to be conclusive.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="anchor the ledger from the authorised snapshot")
    init.add_argument("--asof", type=date.fromisoformat, default=date(2026, 9, 3))
    init.add_argument("--opening", type=float, default=0.0)
    init.add_argument("--plan", default="fund the account, buy the pinned comparator, hold")
    init.add_argument("--name", default="100% SPY")
    init.add_argument("--weights", type=json.loads, default={"SPY": 1.0})
    init.add_argument("--fee", type=float, default=0.000945)
    init.set_defaults(func=command_init)

    close = sub.add_parser("close", help="record one closed interval")
    close.set_defaults(func=command_close)

    rep = sub.add_parser("report", help="both verdicts, kept apart")
    rep.set_defaults(func=command_report)

    ver = sub.add_parser("verify",
                 help="recompute every hash and re-check the pinned comparator")
    # `verify` used to recompute only the ledger chain and then announce
    # "chain intact" while a hand-edited comparator.json sat beside it. That is
    # the one edit that matters: the benchmark is the thing the protocol pins, and
    # the failure mode this journal exists to prevent is precisely someone
    # softening the benchmark rather than the results. A verify that cannot catch
    # it is reporting on the lock while leaving the door open.
    def command_verify_both(_args: argparse.Namespace) -> None:
        report = verify(LEDGER) if LEDGER.exists() else None
        if report is None:
            print("no ledger")
        else:
            print(f"ledger: {report.reason} ({report.entries} entries)")
        try:
            comparator = load_comparator()
        except SystemExit as exc:
            print(f"comparator: {exc}", file=sys.stderr)
            raise SystemExit(2)
        print(f"comparator: pinned spec intact "
              f"({comparator.name}, fee {comparator.expense_ratio:.6f})")

    ver.set_defaults(func=command_verify_both)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
