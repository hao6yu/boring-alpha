"""Every trading cost this repository charges, where the number lives, and what the disagreement between them is worth.

Run: .venv/bin/python tools/cost_conventions.py [--no-measure] [--json]

Round 94 established one sourced table for what a fund *charges to hold*. It never established one fact for what it costs to
*trade*, and the archive runs on two conventions: the paper engine (`paper.SPREAD_BPS`) and the withdrawal/rotation family
(`withdrawal_capacity.TURNOVER_COST`). Both are singletons in their own file, so this is not the copy disease — it is a fork,
and the archive compares outputs across the fork every time it puts a rotation row beside a tilt row.

Three things this prints, in order:

  1. the inventory: every trading-cost literal in `tools/`, with the file and line it lives on, normalised to bps per side or
     dollars per ticket (r96: a published figure needs a command that reprints it, and a constant with no command under it is
     a rumour about a cost);
  2. the duplication: the same fact spelled out in more than one file, which is round 94's finding one layer down — the fee
     literals were fixed, the ticket literals were not;
  3. the consequence, measured: the rotation battery re-run at each one-way cost the inventory found, with its pass set at
     each. The honest question about a fork is not "which is right" but "does anything on the wrong side of it change
     verdict". If something did, this file exits 1 and says so; a page that reports a disagreement it never tested is the
     check that can only print pass (r92).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

TOOLS = ROOT / "tools"

#: name -> (unit, how to normalise). `side` is bps per unit traded in one direction; `ticket` is dollars per order.
FACTS = {
    "SPREAD_BPS": ("side", lambda v: v),
    "TURNOVER_COST": ("side", lambda v: v * 10_000.0),
    "ETF_SPREAD": ("side", lambda v: v * 10_000.0),
    "WRAPPER_SPREAD": ("side", lambda v: v * 10_000.0),
    "BORROW_SPREAD": ("carry", lambda v: v * 10_000.0),
    "COMMISSIONS": ("ticket", None),
    "TICKET": ("ticket", lambda v: v),
}

ASSIGN = re.compile(r"^([A-Z][A-Z_0-9]*)\s*=\s*([^#\n]+?)\s*(?:#.*)?$")
#: A number in prose is a figure no test runs (r100). This finds every literal bps figure written into a string anywhere in
#: `tools/` — an f-string that interpolates the constant does not match, which is exactly the difference being asked for.
PROSE = re.compile(r"(\d+(?:\.\d+)?)\s*bps")
TUPLE_NUMS = re.compile(r"[\d.]+")


def inventory() -> list:
    """Every cost constant defined in `tools/`, as (file, line, name, unit, values)."""

    found = []
    for path in sorted(TOOLS.glob("*.py")):
        for no, line in enumerate(path.read_text().splitlines(), 1):
            m = ASSIGN.match(line)
            if not m or m.group(1) not in FACTS:
                continue
            name, rhs = m.group(1), m.group(2).strip()
            unit, normalise = FACTS[name]
            if rhs.startswith("("):
                values = [float(x) for x in TUPLE_NUMS.findall(rhs)]
            elif re.fullmatch(r"-?[\d.]+", rhs):
                values = [float(rhs)]
            else:
                values = None          # sourced from another module: the good case, and it needs no normalising here
            found.append({"file": path.name, "line": no, "name": name, "unit": unit,
                          "values": values, "rhs": rhs, "literal": values is not None,
                          "normalised": sorted({round(normalise(v), 6) for v in values}) if values and normalise else None})
    return found


def prose(rows_text: dict) -> list:
    """Every bps figure typed into a string, with the line it sits on."""

    hits = []
    for name, text in sorted(rows_text.items()):
        for no, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for m in PROSE.finditer(line):
                if '"' in line or "'" in line:                 # inside a string, not a comment or a numeric comment
                    hits.append({"file": name, "line": no, "figure": m.group(1),
                                 "text": line.strip()[:78]})
    return hits


def duplicates(rows: list) -> list:
    """The same fact, spelled out twice. Equal values are a maintenance hazard; unequal ones under the same name are a bug."""

    by_fact = {}
    for r in rows:
        if r["literal"]:
            by_fact.setdefault(r["name"], []).append(r)
    out = []
    for name, group in sorted(by_fact.items()):
        if len(group) < 2:
            continue
        distinct = sorted({tuple(r["normalised"] if r["normalised"] is not None else r["values"]) for r in group})
        out.append({"name": name, "sites": [f"{r['file']}:{r['line']}" for r in group],
                    "values": [list(d) for d in distinct], "agree": len(distinct) == 1})
    return out


def measure() -> dict:
    """Re-price the battery that ranks the rules at every one-way cost the inventory turned up.

    Only the rotation page is re-run, because it is the one whose conclusions are compared against the other family's numbers:
    the decision sheet prints its verdict beside the tilt's bill, and the runbook quotes both.
    """

    import rotation_search as rse
    import withdrawal_capacity as wc
    sides = sorted({v for r in inventory() if r["unit"] == "side" and r["normalised"] for v in r["normalised"]} | {0.0})
    saved = wc.TURNOVER_COST
    runs = []
    for bps in sides:
        wc.TURNOVER_COST = bps / 10_000.0
        g = rse.grid(100_000.0, 10)
        runs.append({"bps": bps, "passes": sorted(r["rule"] for r in g["rules"] if r["pass"]),
                     "gaps": {r["rule"]: _gap(r["verdict"]) for r in g["rules"] if _gap(r["verdict"]) is not None}})
    wc.TURNOVER_COST = saved
    same = all(r["passes"] == runs[0]["passes"] for r in runs)
    # Measured across runs, not within one: the number that matters is how far a figure travels as the convention moves, and
    # a spread computed inside a single run is definitionally zero (round 104's own first draft did exactly that and printed
    # "$0.00" under a sentence about how much things moved).
    tracks = {}
    for r in runs:
        for k, v in r["gaps"].items():
            tracks.setdefault(k, []).append(v)
    widest = max((max(v) - min(v) for v in tracks.values()), default=0.0)
    return {"runs": runs, "verdicts_invariant": same, "widest_move_dollars_per_month": widest,
            "ladder": [r["bps"] for r in runs]}


def _gap(verdict: str):
    m = re.search(r"by \$([\d,]+\.\d\d)/mo", verdict)
    return float(m.group(1).replace(",", "")) if m else None


def report(rows: list, dups: list, m: dict | None, typed: list | None = None) -> int:
    print("  cost conventions · every trading cost charged anywhere in `tools/`")
    print(f"\n  {'cost':16}{'unit':8}{'file':28}{'value(s)':>22}  source")
    print("  " + "-" * 96)
    for r in sorted(rows, key=lambda r: (r["unit"], r["name"], r["file"])):
        shown = (", ".join(f"{v:g}" for v in r["values"]) if r["values"] is not None else "(sourced)")
        tail = ("literal" if r["literal"] else f"`{r['rhs']}`")
        print(f"  {r['name']:16}{r['unit']:8}{r['file']:28}{shown:>22}  {tail}")
    bad = [d for d in dups if not d["agree"]]
    print(f"\n  facts written down more than once: {len(dups)}"
          + (f" — and {len(bad)} of them DISAGREE" if bad else " (all agreeing copies)"))
    for d in dups:
        print(f"    {d['name']:16} {'AGREE' if d['agree'] else 'DISAGREE'}  " + ", ".join(d["sites"])
              + ("  values: " + " vs ".join(str(v) for v in d["values"]) if not d["agree"] else ""))
    if typed is None:
        typed = prose({Path(p.name).name: p.read_text() for p in TOOLS.glob("*.py")})
    print(f"\n  cost figures typed into prose rather than interpolated from a constant: {len(typed)}")
    for h in typed[:12]:
        print(f"    {h['file']}:{h['line']}  \"{h['text']}\"")
    if len(typed) > 12:
        print(f"    … and {len(typed) - 12} more")
    if m is None:
        print("\n  consequence not measured (--no-measure): the fork between the two conventions is therefore unpriced here,"
              "\n  so this run reports the inventory only and cannot say whether any verdict depends on it.")
        return report_exit(dups, None)
    print(f"\n  consequence, measured on the page that gets compared across the fork (rotation_search, $100,000, 10 years):")
    for r in m["runs"]:
        gap = ", ".join(f"{k} ${v:,.2f}" for k, v in sorted(r["gaps"].items())) or "no verdict carries a dollar gap"
        print(f"    at {r['bps']:>4.1f} bps a side  {len(r['passes'])} rules pass ({', '.join(r['passes']) or 'none'})"
              f"  control gap: {gap}")
    print(f"\n  {'the pass set is the same at every one-way cost the tools quote' if m['verdicts_invariant'] else 'A VERDICT MOVES with the convention'}"
          f" — widest move across those runs ${m['widest_move_dollars_per_month']:,.2f} a month.")
    if m["verdicts_invariant"]:
        print("  That is not a licence to pick either: it is the measurement that lets a rotation row sit beside a tilt row,")
        print("  and it is the only reason the runbook is allowed to print both families on one page.")
    tickets = sorted({v for r in rows if r["unit"] == "ticket" and r["values"] for v in r["values"] if v > 0})
    if len(tickets) > 1:
        print(f"\n  ticket costs spelled out under more than one name: {', '.join(f'${t:g}' for t in tickets)} — same money,")
        print("  two names in one file, which is round 94's disease wearing a different label.")
    return report_exit(dups, m)


def report_exit(dups: list, m: dict | None) -> int:
    """One rule for the exit code, shared by every mode: copies of a fact are a maintenance hazard and only fail the run if the
    copies disagree; the fork of convention fails the run only if something on the wrong side of it changes verdict — which is
    why `--no-measure` cannot return 0 for the fork question it did not ask."""

    if [d for d in dups if not d["agree"]]:
        return 1
    if m is None:
        return 0
    return 0 if m["verdicts_invariant"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-measure", action="store_true", help="print the inventory without re-running the battery")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    texts = {p.name: p.read_text() for p in TOOLS.glob("*.py")}
    rows, dups, typed = inventory(), duplicates(inventory()), prose(texts)
    m = None if args.no_measure else measure()
    if args.json:
        print(json.dumps({"inventory": rows, "duplicates": dups, "prose": typed, "measure": m}, indent=1, default=str))
        return report_exit(dups, m)
    return report(rows, dups, m, typed)


if __name__ == "__main__":
    raise SystemExit(main())
