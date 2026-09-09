"""What did the last fetch actually move? A snapshot is re-pulled data, and re-pulled data is revised data.

Round 95 learned this the expensive way: the monthly runner fetched, the pointer moved, two days later a bit-level assertion failed,
and the failure was correct — the archive had been re-pulled and one close had moved by a hundredth of a basis point. Round 97 then
re-ran a sixteen-year replay and found all four of its totals had drifted 0.4–0.8% with paid-in and the month count unchanged. Same
cause, nobody looked. Every number in this repository is a function of a file that somebody else is allowed to revise, and until now
the project verified the *ledger* (`journalctl.py`, `audit_entries.py`) and never the *corpus*.

This file is the corpus half of rule 4. It reads two fetched snapshots and answers one question in dollars and percent: **what
moved.** It does not judge a strategy, and it does not repair a note. If the movement is bigger than the tolerance that the figure
pins in `tests/test_power_horizon.py` already use, it exits non-zero, which stops the monthly runner — not because the fetch was
wrong, but because a published figure that has moved is a published figure that has to be re-read before it is quoted again.

Run it:

    .venv/bin/python tools/corpus_diff.py            # the two newest snapshots
    .venv/bin/python tools/corpus_diff.py --against 20260906T203953Z --json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import labdata                                                   # noqa: E402  the one resolver for lab state

# The lab state root, so a rehearsal can point this tool at a copy (tools/labdata.py). The NYSE calendar below stays pinned to the
# repository: a corpus is state, a calendar is an authority, and an authority a rehearsal could move is not an authority.
SNAPSHOTS = labdata.data_root() / "snapshots"
STAMP = re.compile(r"\d{8}T\d{6}Z")        # only a fetch names a directory; a hand-made copy does not count
PRICES = "market_daily.csv"
CASH = "cash_daily.csv"
DISTRIBUTIONS = "distributions_daily.csv"

# One place for the number, three places that read it: this tool, the replay pin in test_power_horizon.py, and the runbook
# sentence that quotes it. A tolerance written twice is two tolerances (r94), and this one is the loosest thing standing
# between "the vendor revised a close" and "the archive no longer tells the story the notes tell".
CASH_FIELDS = ("cash_factor", "rate", "rate_pct", "DGS3MO")
DIVIDEND_FIELDS = ("dividend", "amount", "adj")
DIVIDEND_TOLERANCE = 0.005            # dollars a share: a restatement bigger than half a cent is a different dividend history
TOLERANCE = 0.015
TOLERANCE_WHERE = "tests/test_power_horizon.py::TheBarsHaveACommand"


CALENDAR = ROOT / "data/calendars/nyse-2006-2026-v1.json"
#: The rule set behind that artifact, importable and (since round 108) independently re-derived in
#: `tests/test_nyse_rules_independently.py`. The artifact vouches for dates it covers; the rules vouch for the reviewed window.
RULE_YEARS = (2006, 2026)
SPECIAL_CLOSURES = {"2007-01-02", "2012-10-29", "2012-10-30", "2018-12-05", "2025-01-09"}


def rule_closures(year: int) -> set[str] | None:
    """The closures the published rule set implies, or None for a year the transcription was never reviewed for."""

    if not RULE_YEARS[0] <= year <= RULE_YEARS[1]:
        return None
    from build_nyse_calendar import regular_closures                  # noqa: PLC0415  the rules live in their builder
    return {d.isoformat() for d in regular_closures(year)} | SPECIAL_CLOSURES


def why_no_new_sessions(last_session: str, fetched_on: str) -> str:
    """When a fetch adds no sessions, what does the exchange calendar say about the days in between?

    Round 105 ran a fetch that added nothing and the tool printed *"history added"* anyway. Round 106 checked the archive's own edge and
    found the honest answer was a US market holiday — but the answer is not free: it lives in a calendar whose coverage ends before the
    gap, so the tool now has to say which of the three things it knows, and name the missing thing when it knows none (r92).
    """

    end = date.fromisoformat(fetched_on)
    start = date.fromisoformat(last_session)
    # The fetch day itself is excluded: the fetcher drops the session still in progress, so the day it ran on is not a day the
    # archive could have contained. Off-by-one here would call every fetch that ran on a weekday "short by one session".
    gap = [start + timedelta(days=n) for n in range(1, (end - start).days)]
    gap = [d for d in gap if d.weekday() < 5]
    many = "s" if len(gap) != 1 else ""
    span = gap[0].isoformat() if len(gap) == 1 else f"{gap[0].isoformat()} to {gap[-1].isoformat()}"
    if not gap:
        return "the archive ends on the last completed session; the exchange has not finished another one since the fetch ran."
    if not CALENDAR.exists():
        return (f"{len(gap)} weekday{many} between them ({span}) and no exchange calendar on disk at "
                f"{CALENDAR}; this tool cannot tell a holiday from a stalled fetch.")
    cal = json.loads(CALENDAR.read_text())
    covered_to = date.fromisoformat(cal["coverage_end"])
    if covered_to < gap[-1]:
        admitted = (f"{len(gap)} weekday{many} between them ({span}) and the calendar's coverage ends {cal['coverage_end']}, "
                    f"before the gap — the checked artifact cannot vouch for them, and `tools/build_nyse_calendar.py` is what "
                    f"would extend it")
        outside = [d for d in gap if rule_closures(d.year) is None]
        if outside:
            return admitted + f", and the rule set itself stops being reviewed in {outside[-1].year}, so this tool cannot say."
        closed = [d for d in gap if d.isoformat() in rule_closures(d.year)]
        open_days = [d.isoformat() for d in gap if d.isoformat() not in rule_closures(d.year)]
        by_rules = ("the rule set transcribed in `build_nyse_calendar.py` (re-derived in `tests/test_nyse_rules_independently.py`) "
                    + (f"says it was a closure — the archive is current, not stalled." if len(gap) == 1
                       else f"says all {len(gap)} were closures — the archive is current, not stalled."))
        if open_days:
            by_rules = ("the rule set transcribed in `build_nyse_calendar.py` (re-derived in `tests/test_nyse_rules_independently.py`) "
                        f"says {len(open_days)} of them were trading days ({', '.join(open_days)}) — the source fell short.")
        return admitted + "; " + by_rules
    open_days = set(cal["sessions"])
    missed = [d.isoformat() for d in gap if d.isoformat() in open_days]
    if not missed:
        return (f"all {len(gap)} weekday{many} in between ({span}) were exchange closures — the archive is current, not stalled; "
                f"the closures were {', '.join(d.isoformat() for d in gap)}.")
    missed_many = "s" if len(missed) != 1 else ""
    return (f"the source fell short: {len(missed)} open day{missed_many} between the archive and the fetch "
            f"({', '.join(missed)}). The month may continue — the next fetch should fill them — but do not quote this "
            f"month's figures as covering a period the corpus does not contain.")


def snapshots() -> list[Path]:
    """Fetched snapshot directories, oldest first. A directory counts only if a fetch completed it, which means it has a manifest."""

    if not SNAPSHOTS.exists():
        return []
    return sorted((d for d in SNAPSHOTS.iterdir()
                   if STAMP.fullmatch(d.name) and (d / "manifest.json").exists()), key=lambda d: d.name)


def prices(path: Path) -> dict:
    """(date, symbol) -> closing price, for one snapshot."""

    out = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            out[(row["date"], row["symbol"])] = float(row["tr_close"])
    return out


def cash(path: Path) -> dict:
    """The daily cash factor. If the column this file expects is not there, the file says so instead of returning an empty dict:
    an empty diff is a *verdict*, and a verdict reached by reading nothing is the exact failure r92 lists — a check that cannot
    find its input and prints the number that lets the month continue."""

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        if "date" not in columns:
            raise SystemExit(f"{path}: no `date` column (found: {', '.join(columns) or 'nothing'})")
        field = next((c for c in CASH_FIELDS if c in columns), None)
        if field is None:
            raise SystemExit(f"{path}: no cash column among {CASH_FIELDS} (found: {', '.join(columns)})")
        return {row["date"]: float(row[field]) for row in reader if row.get(field) not in (None, "")}


def distributions(path: Path) -> dict:
    """One dividend amount per (date, symbol), same refusal as `cash`: no column, no verdict."""

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        if "symbol" not in columns or "date" not in columns:
            raise SystemExit(f"{path}: expected `date` and `symbol` (found: {', '.join(columns) or 'nothing'})")
        field = next((c for c in DIVIDEND_FIELDS if c in columns), None)
        if field is None:
            raise SystemExit(f"{path}: no dividend column among {DIVIDEND_FIELDS} (found: {', '.join(columns)})")
        return {(row["date"], row["symbol"]): float(row[field] or 0.0) for row in reader}


def revision(a: dict, b: dict) -> dict:
    """Compare two keyed dicts that should describe the same thing. Nothing is averaged: the tool reports the worst single cell."""

    shared = a.keys() & b.keys()
    worst = {"rel": 0.0, "key": None, "old": None, "new": None}
    changed = 0
    for key in shared:
        try:
            x, y = float(a[key]), float(b[key])
        except (TypeError, ValueError):
            x, y = a[key], b[key]
            if x != y:
                changed += 1
            continue
        if x == y:
            continue
        changed += 1
        rel = abs(y - x) / abs(x) if x else float("inf")
        if rel >= worst["rel"]:
            worst = {"rel": rel, "key": key, "old": x, "new": y}
    return {"shared": len(shared), "only_in_old": len(a.keys() - b.keys()), "only_in_new": len(b.keys() - a.keys()),
            "changed": changed, "worst": worst}


def compare(newer: Path, older: Path) -> dict:
    old_p, new_p = prices(older / PRICES), prices(newer / PRICES)
    old_d, new_d = distributions(older / DISTRIBUTIONS), distributions(newer / DISTRIBUTIONS)
    days_old = {d for d, _ in old_p}
    days_new = {d for d, _ in new_p}
    symbols_old = {s for _, s in old_p}
    symbols_new = {s for _, s in new_p}
    per_symbol = {}
    for symbol in sorted(symbols_new & symbols_old):
        pairs = [(d, old_p[(d, symbol)], new_p[(d, symbol)]) for d in sorted(days_old & days_new)
                 if (d, symbol) in old_p and (d, symbol) in new_p]
        if not pairs:
            continue
        worst = max(((abs(n - o) / o, d, o, n) for d, o, n in pairs if o), default=(0.0, None, None, None))
        per_symbol[symbol] = {"sessions": len(pairs), "max_revision": worst[0], "at": worst[1],
                              "old_close": worst[2], "new_close": worst[3],
                              "last": pairs[-1][2], "last_old": pairs[-1][1]}
    out = {"older": older.name, "newer": newer.name,
           "sessions": {"old": len(days_old), "new": len(days_new),
                        "added": sorted(days_new - days_old)[-6:], "removed": sorted(days_old - days_new)[-6:],
                        "last": max(days_new) if days_new else None,
                        "fetched_on": f"{int(newer.name[0:4])}-{newer.name[4:6]}-{newer.name[6:8]}"},
           "symbols": {"old": len(symbols_old), "new": len(symbols_new),
                       "added": sorted(symbols_new - symbols_old), "lost": sorted(symbols_old - symbols_new)},
           "per_symbol": per_symbol,
           "cash": revision(cash(older / CASH), cash(newer / CASH)),
           "distributions": revision(old_d, new_d),
           "tolerance": TOLERANCE}
    worst_price = max((r["max_revision"] for r in per_symbol.values()), default=0.0)
    out["worst_price_revision"] = worst_price
    out["history_lost"] = bool(days_old - days_new) or bool(symbols_old - symbols_new)
    out["worst_dividend"] = abs((out["distributions"]["worst"]["new"] or 0.0)
                                - (out["distributions"]["worst"]["old"] or 0.0)) if out["distributions"]["changed"] else 0.0
    out["within_tolerance"] = (worst_price <= TOLERANCE and not out["history_lost"]
                               and out["worst_dividend"] <= DIVIDEND_TOLERANCE)
    return out


def report(diff: dict) -> None:
    print(f"# corpus diff · {diff['older']} → {diff['newer']}")
    s = diff["sessions"]
    print(f"  sessions {s['old']:,} → {s['new']:,}"
          + (f", added {', '.join(s['added'])}" if s["added"] else "")
          + (f", REMOVED {', '.join(s['removed'])}" if s["removed"] else ""))
    print(f"  symbols {diff['symbols']['old']} → {diff['symbols']['new']}"
          + (f", LOST {', '.join(diff['symbols']['lost'])}" if diff["symbols"]["lost"] else "")
          + (f", added {', '.join(diff['symbols']['added'])}" if diff["symbols"]["added"] else ""))
    print(f"  revised closes: {sum(1 for r in diff['per_symbol'].values() if r['max_revision'] > 0)} of "
          f"{len(diff['per_symbol'])} symbols, worst single cell {diff['worst_price_revision']:.2%}"
          + (f" ({max(diff['per_symbol'], key=lambda k: diff['per_symbol'][k]['max_revision'])})" if diff["per_symbol"] else ""))
    d = diff["distributions"]
    print(f"  distributions: {d['changed']:,} amounts differ (worst ${diff['worst_dividend']:.4f} a share), "
          f"{d['only_in_new']:,} rows new, {d['only_in_old']:,} rows gone")
    c = diff["cash"]
    print(f"  cash rate: {c['changed']:,} sessions differ, worst {c['worst']['rel']:.2%}")
    for symbol, row in sorted(diff["per_symbol"].items(), key=lambda kv: -kv[1]["max_revision"])[:5]:
        print(f"    {symbol:<5} {row['sessions']:,} sessions   worst revision {row['max_revision']:.4%}"
              + (f" on {row['at']} ({row['old_close']} → {row['new_close']})" if row["at"] else "   no change"))
    verdict = (f"within the {TOLERANCE:.1%} tolerance that {TOLERANCE_WHERE} pins"
               if diff["within_tolerance"] else "OUTSIDE tolerance — read the notes this moves before quoting any figure in them")
    print(f"\n  {verdict}")
    if not diff["sessions"]["added"]:
        print(f"  no new sessions: {why_no_new_sessions(diff['sessions']['last'], diff['sessions']['fetched_on'])}")
    if diff["within_tolerance"]:
        # Round 105: this line used to read "Nothing has to be re-read … old closes unmoved" while the six lines above it printed
        # that 11 of 12 symbols' closes had moved, and the fetch it ran on did in fact move a figure in the one document the
        # operator obeys — by a dollar, which is exactly how small the tolerance is. Immaterial is a claim about the tolerance,
        # not about the prose (r95), and a re-pull is a revision (r98).
        revised = sum(1 for r in diff["per_symbol"].values() if r["max_revision"] > 0)
        n_sym = len(diff["per_symbol"])
        if revised:
            print(f"  {revised} of {n_sym} symbols' old closes moved, and immaterial at the tolerance above is not the same word as"
                  " unchanged: `docs/RUNBOOK.md` pins its bar table to the dollar and `tests/test_runbook.py` recomputes every digit"
                  " of it, so a revision small enough to be noise can still move a published sentence. Re-print the figure with the"
                  " command that printed it, never by hand.")
        else:
            print("  No old close moved at all: the past is intact, and the line above says what happened to the frontier.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--against", help="compare the newest snapshot against this stamp instead of the one before it")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    found = snapshots()
    if len(found) < 2:
        print(f"corpus_diff: {len(found)} fetched snapshot(s) in {SNAPSHOTS}; nothing to compare yet")
        return 0                                            # a first fetch is not a finding
    newer = found[-1]
    older = next((d for d in found if d.name == args.against), None) if args.against else found[-2]
    if older is None:
        raise SystemExit(f"--against {args.against}: no such snapshot (known: {', '.join(d.name for d in found)})")
    if older == newer:
        raise SystemExit("a snapshot cannot be compared with itself; the diff would be zero and the zero would be a lie")
    diff = compare(newer, older)
    if args.json:
        print(json.dumps(diff, indent=2, default=str))
    else:
        report(diff)
    return 0 if diff["within_tolerance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
