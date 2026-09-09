"""P0, as a command: did this book beat plain index investing, net of what it really cost?

The runbook's first stopping rule says the tilt must beat plain index dollar-cost-averaging — VOO, same transfers, same costs —
net of every fee and every ticket, and that if the sealed books say otherwise after 24 entries the tilt is retired. Until round
91 that sentence had no command behind it. `paper.py report` prints the gap to a book's own *witness* (its twin sleeve-for-sleeve
at zero commission), and `journal.verdict`'s comparator is deliberately generous: it is charged the book's own net cash and pays
nothing to trade, because `comparator_return` says losing to it should never be a rounding error. Neither one answers P0, which
is the harder question: **against a one-fund index account that is charged its own real costs and pays its own tickets.**

So this file computes that comparison from the sealed record and nothing else.

The book's side is what the ledger already says it is worth — every expense ratio and every basis point of spread it was charged
is inside `closing_value`, because the engine put it there at seal time. The index side is rebuilt from the same sealed quotes:
the same transfers on the same dates, into VOO alone, charged VOO's posted expense ratio by `journal.comparator_path`, and then
reduced by the tickets that plan would actually have paid — one buy in every month a transfer arrived, and nothing else, because
a plain index account neither rebalances nor sells.

The book's tickets are not assumed. They are counted out of the chain: for every interval, a sleeve whose units rose was bought
and a sleeve whose units fell was sold, one ticket each. That is the discipline round 86 arrived at from the other direction (a
flat ticket is paid per order, so the number of orders is the size of the cost), and it means the answer changes with the
model's behaviour rather than with a guess about it: a banded book that lets weights drift pays fewer tickets than one that
rebalances monthly, and the chain says which one ran.

Round 90's margin is applied rather than the bare sign, because `beat by any amount` is worth about a coin flip at the protocol's
floor: at 24 entries a no-skill path clears +152 bps of annualised gap 5% of the time, at 36 +50, at 60 nothing is required
because the no-skill distribution is already 58 bps behind. Those figures are `skill_null.py`'s; `--margin` overrides them and
`tests/test_forward_p0.py` re-derives them so this table cannot rot.

Usage:

    .venv/bin/python tools/forward_p0.py                          # the root book, no commission
    .venv/bin/python tools/forward_p0.py --book tilt_band --commission 9.95
    .venv/bin/python tools/forward_p0.py --book tilt --commission 0 --json
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                           # noqa: E402
from boring_alpha import journal                       # noqa: E402

#: What a no-skill path clears 5% of the time, in basis points of annualised money-weighted gap, by `skill_null.py` at 600
#: paths on the pinned seed. Below 24 entries the protocol does not speak, so no margin is quoted.
MARGINS = {24: 152.0, 36: 50.0, 60: 0.0}
WITNESS = "VOO"

#: The measured bill for rebalancing the 50/50 book, as a share of everything paid in: $1,091 on $2,020,000 over the 16-year
#: record (`rebalance_cost.py`), which is 0.054%. It is the ceiling the banded book is allowed to fall behind its unbanded twin by
#: before the band is declared cost without benefit, so it is charged against paid in rather than read as a dollar figure, and it
#: is the reason stopping rule 2 has a number in it rather than an opinion. `--bill-cap` overrides it.
BAND_BILL_SHARE = 0.00054
TWIN = "tilt"          # the unbanded form of the same model: the only fair comparison for the band
BAND = "tilt_band"


def chain_path(book: str | None) -> Path:
    return (paper.PAPER_DIR / "books" / book / "ledger.jsonl") if book else (paper.PAPER_DIR / "ledger.jsonl")


def count_tickets(chain: tuple) -> dict:
    """Buys and sells, read off the sealed holdings rather than assumed from the model's description of itself."""

    buys = sells = 0
    per_interval = []
    previous: dict[str, float] = {}
    for entry in sorted(chain, key=lambda e: e.asof):
        now = {h.symbol: h.units for h in entry.holdings}
        bought = [s for s, u in now.items() if u > previous.get(s, 0.0) + 1e-9]
        sold = [s for s, u in previous.items() if u > now.get(s, 0.0) + 1e-9]
        buys += len(bought)
        sells += len(sold)
        per_interval.append({"asof": entry.asof.isoformat(), "buys": bought, "sells": sold})
        previous = now
    return {"buys": buys, "sells": sells, "tickets": buys + sells, "per_interval": per_interval}


def plain_index_tickets(chain: tuple) -> int:
    """One buy in every month a transfer arrived, and nothing else: the ticket count of the thing being compared against."""

    return sum(1 for e in chain if e.cash_arrived > 0.0)


def gross_chain(chain: tuple) -> tuple:
    """The same entries with their fee line cleared, so the index side is charged its own costs and not the book's.

    `journal.comparator_path` advances the comparator by `cash_arrived - fee_paid`, which is right for the protocol's generous
    comparator and wrong here: P0 charges each side what that side would have paid. Clearing the fee line hands the comparator
    the gross transfer, and this file then charges it VOO's expense ratio (which `comparator_path` applies) and its own tickets.
    """

    return tuple(dataclasses.replace(e, fee_paid=0.0) for e in chain)


def evaluate(chain: tuple, commission: float, margin: float | None = None, witness: str = WITNESS) -> dict:
    """Price the book against one index, at that index's own fee and its own ticket count.

    `witness` is a parameter because the objective names two indexes and this file was built to ask one question. The standing
    rule stays VOO — it is the plainest thing that would have done the job, and a bar moved mid-programme is how a programme
    grade itself into passing. Anything else is a **secondary bar**, and the verdict wording says so, because a file that can
    ask a second question must not be able to quietly replace the first.
    """

    if commission < 0.0:
        raise SystemExit("a negative commission is a rebate, and this file is not built to price rebates")
    if not chain:
        raise SystemExit("no chain to evaluate")
    fee = paper.posted_fee(witness)          # refuses a symbol this repository has no source for
    sleeve = witness in paper.tilt_weights() or witness in {h.symbol for h in chain[-1].holdings}
    out: dict = {"entries": len(chain), "commission": commission, "witness": witness, "witness_fee": fee,
                 "witness_is_a_sleeve": sleeve,
                 "paid_in": chain[0].opening_value + sum(e.cash_arrived for e in chain)}
    tickets = count_tickets(chain)
    out["tickets"] = tickets
    out["index_tickets"] = plain_index_tickets(chain)
    out["book_value"] = chain[-1].closing_value
    out["book_fees_sealed"] = sum(e.fee_paid for e in chain)
    out["ticket_cost_book"] = tickets["tickets"] * commission
    out["ticket_cost_index"] = out["index_tickets"] * commission

    if len(chain) < 2:
        out["index_value"] = None
        out["gap"] = None
        out["verdict"] = (f"nothing to compare yet: the book holds its anchor, whose holdings are empty by design, so there is "
                          f"no interval over which to price {witness}")
        return out

    comparator = journal.Comparator(name=f"P0 {witness}", weights={witness: 1.0}, expense_ratio=fee)
    try:
        index_value = journal.comparator_path(gross_chain(chain), comparator)
    except ValueError as exc:
        # r93's rule applied to this tool: a run that dies on a traceback reports less than one that names the missing input.
        raise SystemExit(f"{witness} cannot be the bar for this chain: it has no sealed quote for it. {exc}")
    net_book = out["book_value"] - out["ticket_cost_book"]
    net_index = index_value - out["ticket_cost_index"]
    out["index_value"], out["net_book"], out["net_index"] = index_value, net_book, net_index
    out["gap"] = net_book - net_index

    needed = journal.MIN_ENTRIES_FOR_SKILL_VERDICT - len(chain)
    if needed > 0:
        out["verdict"] = (f"not decidable — {needed} more monthly entries before the protocol permits a skill claim; the gap "
                          f"above is a cost report, not evidence")
        return out

    horizon = min(MARGINS, key=lambda h: abs(h - len(chain)))
    required = margin if margin is not None else MARGINS.get(horizon, 0.0)
    out["margin_bps_required"] = required
    out["gap_bps"] = None            # the protocol's own bps figure, reported beside the dollars when it exists
    verdict = journal.verdict(chain, comparator, chain[-1].asof)
    out["protocol_bps"] = verdict.shortfall_bps
    if verdict.shortfall_bps is None:
        out["verdict"] = f"withheld by the protocol: {verdict.skill}"
    elif out["gap"] <= 0.0:
        out["verdict"] = (f"FAILS {'P0' if witness == WITNESS else 'the secondary bar at ' + witness} — behind by "
                          f"${-out['gap']:,.2f} net of tickets, and a no-skill margin cannot rescue a negative gap")
    elif required > 0 and (verdict.shortfall_bps or 0.0) < required:
        out["verdict"] = (f"ahead, but inside the no-skill margin ({verdict.shortfall_bps:,.0f} < {required:,.0f} bps): "
                          f"not evidence either way")
    else:
        out["verdict"] = ("DOMINATES the index net of tickets" if out["gap"] > 0.0
                          else "FAILS P0 — the index, charged its own costs, is ahead")
    if witness != WITNESS and "cannot redefine P0" not in out["verdict"]:
        # Every wording a non-standing bar can produce carries its own limit, including the ones above that were written
        # before the flag existed. A tool that can ask a second question must never be able to restate the first.
        out["verdict"] = (out["verdict"].replace("FAILS P0", f"FAILS the secondary bar at {witness}")
                          .replace("DOMINATES the index", f"clears the secondary bar at {witness} but does not settle P0")
                          + " (a secondary bar cannot redefine P0)")
    return out


def evaluate_pair(chain: tuple, twin: tuple, commission: float, bill_cap: float = BAND_BILL_SHARE) -> dict:
    """Stopping rule 2: a band is only worth having if it costs less than the bill it avoids.

    Dollars of net value at identical paid-in, because two books on the same schedule are comparable in exactly one currency, and
    tickets are counted separately for each — which is the point: a band that trades less has to win on the difference, not on a
    claim about drift. The two chains must have sealed the same intervals, or the comparison is between different periods and not
    between two policies.
    """

    a, b = evaluate(chain, commission), evaluate(twin, commission)
    if [e.asof for e in chain] != [e.asof for e in twin]:
        raise SystemExit("the two books have not sealed the same intervals; a policy comparison across different periods is "
                         "not a policy comparison")
    paid_in = a["paid_in"]
    net_a, net_b = a.get("net_book"), b.get("net_book")
    out = {"book": BAND, "twin": TWIN, "entries": a["entries"], "paid_in": paid_in, "commission": commission,
           "net_book": net_a, "net_twin": net_b,
           "tickets_book": a["tickets"]["tickets"], "tickets_twin": b["tickets"]["tickets"],
           "gap": None if net_a is None or net_b is None else net_a - net_b, "bill_cap": bill_cap * paid_in}
    if net_a is None or net_b is None:
        out["verdict"] = ("nothing to compare yet: neither book has sealed an interval with holdings in it"
                          if len(chain) < 2 else
                          "not decidable — the books hold no interval that a policy could have acted on")
        return out
    if out["gap"] == 0.0:
        out["verdict"] = ("identical net value on the sealed record, so the band bought nothing; the twin is the cheaper "
                          "construction to run and the band should go")
    elif out["gap"] > 0.0:
        out["verdict"] = (f"the band is ahead of its own twin by ${out['gap']:,.2f} on the sealed record; keep it, but the "
                          f"twin is the cheaper construction by default")
    elif -out["gap"] <= out["bill_cap"]:
        out["verdict"] = (f"the band is behind its twin by ${-out['gap']:,.2f}, inside the measured rebalancing bill of "
                          f"${out['bill_cap']:,.2f} ({bill_cap:.3%} of paid in): no verdict either way")
    else:
        out["verdict"] = (f"BAND FAILS its own twin by ${-out['gap']:,.2f}, more than the measured bill of "
                          f"${out['bill_cap']:,.2f}: the band is cost without benefit")
    return out


def status(commission: float, margin: float | None = None, bill_cap: float = BAND_BILL_SHARE) -> dict:
    """All four stopping conditions, one command, each with the tool that owns it.

    Deliberately unable to conclude anything the archive has not yet earned: three of the four read `not decidable` today, and a
    status line that pretended otherwise would be the most expensive line in this repository.
    """

    books = sorted(d.name for d in (paper.PAPER_DIR / "books").iterdir() if (d / "ledger.jsonl").exists())
    out: dict = {"commission": commission, "books": {}, "conditions": []}

    integrity, entries = [], {}
    for name in ["root", *books]:
        path = chain_path(None if name == "root" else name)
        ok = path.exists() and bool(paper.verify(path))
        integrity.append({"book": name, "intact": ok, "entries": len(paper.read(path)) if path.exists() else 0})
        entries[name] = integrity[-1]["entries"]
    out["books"], out["integrity_all_intact"] = integrity, all(i["intact"] for i in integrity)

    def add(rule: str, owner: str, verdict: str) -> None:
        out["conditions"].append({"rule": rule, "command": owner, "answer": verdict})

    band = next((i for i in integrity if i["book"] == BAND), None)
    subject = chain_path(BAND) if band else chain_path("root")
    p0 = evaluate(paper.read(subject), commission, margin)
    add("P0 — beat plain VOO net of everything", "tools/forward_p0.py --book tilt_band --commission <ticket>",
        p0["verdict"])

    if band and TWIN in books:
        pair = evaluate_pair(paper.read(chain_path(BAND)), paper.read(chain_path(TWIN)), commission, bill_cap)
        add("The band, against its own twin", "tools/forward_p0.py --against tilt --book tilt_band", pair["verdict"])
    else:
        add("The band, against its own twin", "tools/forward_p0.py --against tilt --book tilt_band",
            f"not applicable: {BAND} and {TWIN} are not both anchored here")

    if band and entries.get(BAND, 0) >= 2:
        comparator = journal.Comparator(name=f"status {WITNESS}", weights={WITNESS: 1.0},
                                       expense_ratio=paper.fee_for(WITNESS))
        verdict = journal.verdict(paper.read(subject), comparator, paper.read(subject)[-1].asof)
        add("Skill, past the protocol's floor", "tools/paper.py report --book tilt_band", verdict.skill)
    else:
        add("Skill, past the protocol's floor", "tools/paper.py report --book tilt_band",
            f"underpowered — {journal.MIN_ENTRIES_FOR_SKILL_VERDICT - entries.get(BAND, 1)} more monthly entries and "
            f"${max(0.0, journal.MIN_CONTRIBUTIONS_FOR_SKILL_VERDICT - p0['paid_in']):,.0f} more paid in")

    # Round 93's audit, folded into the condition it belongs to: hashes matching is half of "the record is sound", and the other
    # half is an entry agreeing with its own numbers, which is the half round 87 actually failed.
    import audit_entries
    reports = [audit_entries.audit_book(i["book"]) for i in integrity if i["intact"]]
    findings = [dict(f, book=r["book"]) for r in reports for f in r["findings"]]
    out["findings"] = findings
    chains = "all chains verify" if out["integrity_all_intact"] else \
        "INTEGRITY FAILURE: " + ", ".join(i["book"] for i in integrity if not i["intact"])
    entries = "every entry accounts for itself" if not findings else \
        "CONTRADICTIONS: " + ", ".join(f"{f['book']}@{f['index']} {f['kind']}" for f in findings)
    add("Integrity, immediately", "tools/journalctl.py verify; tools/audit_entries.py",
        chains + ", and " + entries if out["integrity_all_intact"] else chains + ", entries not audited")
    out["fee_line"] = sum(e.fee_paid for e in paper.read(subject))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--book", default=None, help="a book beside the root one")
    ap.add_argument("--commission", type=float, default=0.0, help="what one order costs on the venue in use")
    ap.add_argument("--margin", type=float, default=None, help="override the no-skill margin in basis points")
    ap.add_argument("--witness", default=WITNESS,
                    help="the index to price against; a comma list prints one block each. Only VOO is P0 — the rest are "
                         f"secondary bars ({WITNESS} is the standing rule)")
    ap.add_argument("--against", default=None, metavar="BOOK",
                    help="compare against another book's net value instead of against the index (stopping rule 2)")
    ap.add_argument("--bill-cap", type=float, default=BAND_BILL_SHARE,
                    help="allowed band-vs-twin shortfall as a share of paid in (default: the measured 0.054%%)")
    ap.add_argument("--status", action="store_true", help="all four stopping conditions, one screen")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.status:
        out = status(args.commission, args.margin, args.bill_cap)
        if args.json:
            print(json.dumps(out, indent=2, default=str))
            return 0
        print(f"# stopping conditions, at {args.commission:,.2f} per order   [{len(out['books'])} books]"
              f"   sealed fees to date ${out['fee_line']:,.2f}\n")
        for condition in out["conditions"]:
            print(f"  {condition['rule']}")
            print(f"     {condition['answer']}")
            print(f"     owner: {condition['command']}\n")
        print("  Three of these four say `not decidable` because the programme is three weeks old. That is the correct output,"
              "\n  and the day one of them stops saying it is the day this file starts being worth reading.")
        return 0

    if args.against is not None:
        if args.book is None:
            raise SystemExit("--against needs --book: a policy comparison is between two named books")
        for name in (args.book, args.against):
            path = chain_path(name)
            if not path.exists():
                raise SystemExit(f"no ledger for book {name!r} at {path}")
            if not bool(paper.verify(path)):
                raise SystemExit(f"refusing to judge a book whose chain does not verify: {path}")
        out = evaluate_pair(paper.read(chain_path(args.book)), paper.read(chain_path(args.against)),
                            args.commission, args.bill_cap)
        out["book"], out["twin"] = args.book, args.against
        if args.json:
            print(json.dumps(out, indent=2, default=str))
            return 0
        print(f"# the band against its own twin: `{args.book}` versus `{args.against}`"
              f", at {args.commission:,.2f} per order  [{out['entries']} entries, ${out['paid_in']:,.0f} paid in]")
        if out["net_book"] is None:
            print(f"  {out['verdict']}")
            return 0
        print(f"  net of tickets  ${out['net_book']:,.2f} ({out['tickets_book']} orders) against "
              f"${out['net_twin']:,.2f} ({out['tickets_twin']} orders)")
        print(f"  allowed shortfall by the measured bill: ${out['bill_cap']:,.2f}")
        print(f"\n  verdict: {out['verdict']}")
        return 0

    path = chain_path(args.book)
    if not path.exists():
        raise SystemExit(f"no ledger at {path}")
    report = paper.verify(path)
    if not bool(report):
        raise SystemExit(f"refusing to judge a book whose chain does not verify: {path}")
    chain = paper.read(path)
    witnesses = [w.strip().upper() for w in args.witness.split(",") if w.strip()]
    if not witnesses:
        raise SystemExit("--witness needs at least one ticker")
    out = evaluate(chain, args.commission, args.margin, witnesses[0])
    extra = [evaluate(chain, args.commission, args.margin, w) for w in witnesses[1:]]
    out["book"] = args.book or "root"
    out["chain"] = str(path.relative_to(ROOT))

    if args.json:
        print(json.dumps({"primary": out, "secondary": extra}, indent=2, default=str))
        return 0

    print(f"# P0 for the `{out['book']}` book, at {args.commission:,.2f} per order"
          f"  [{out['entries']} entries, ${out['paid_in']:,.0f} paid in]")
    print(f"  book            ${out['book_value']:,.2f}   (after ${out['book_fees_sealed']:,.2f} of sealed expense and spread)")
    if out["index_value"] is None:
        print(f"  {out['verdict']}")
        for other in extra:
            print(f"  secondary bar at {other['witness']}: {other['verdict']}")
        return 0
    print(f"  plain {out['witness']:<9}   ${out['index_value']:,.2f}   (same transfers, {out['witness']}'s "
          f"{out['witness_fee']:.2%} expense, "
          f"{out['index_tickets']} tickets)")
    print(f"  tickets         book paid for {out['tickets']['tickets']} orders "
          f"({out['tickets']['buys']} buys, {out['tickets']['sells']} sells) = ${out['ticket_cost_book']:,.2f}"
          + ("" if args.commission == 0 else f"   [index would have paid ${out['ticket_cost_index']:,.2f}]"))
    print(f"  net of tickets  ${out['net_book']:,.2f} against ${out['net_index']:,.2f}   "
          f"gap {'+' if out['gap'] >= 0 else ''}{out['gap']:,.2f}")
    print(f"\n  verdict: {out['verdict']}")
    if out["witness_is_a_sleeve"]:
        print(f"  note: {out['witness']} is one of the book's own sleeves, so this measures the *weighting* rather than the "
              f"instrument choice — the free version of the bet, priced at its own fee")
    for other in extra:
        print(f"\n  secondary bar at {other['witness']}: "
              + (other["verdict"] if other.get("gap") is not None else other["verdict"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
