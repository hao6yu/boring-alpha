"""Run the published monthly procedure in the published order, and stop at the first command that fails.

The runbook is the authority: this file does not contain the procedure, it reads the first ```sh block of
[`docs/RUNBOOK.md`](../docs/RUNBOOK.md) and runs those commands in that order, plus one `paper.py step` per book found on disk —
the block names one book and says "and each other book, one command each", which is prose a human reads and a script cannot infer.
`tests/test_monthly_runner.py` fails if the two ever disagree, so this file cannot drift from the document it executes.

What this is not matters more than what it is.

*It is not a trading bot.* It fetches a corpus, seals the books that were anchored in advance, verifies the hashes, audits each
sealed entry against its own numbers, and reports. The decision content was fixed at the anchoring — model, sleeves, band, witness —
because a monthly argument about the model is what this archive has repeatedly failed to be able to grade (r90, r91). Every
mechanical step is here so that it can be done in one command and never half-done, and every judgement is deliberately left out so
that it cannot be done by accident.
*It takes no discretionary knob.* No `--force`, no `--yes`, no `--tilt`, no `--band`. A rebalancing band is a measured property of a
model and the engine refuses to be told one (r88); a runner that could pass one would be the hole in that refusal.
*It does not continue past a failure.* The commands are ordered for a reason: fetch before seal (the engine will not seal a date the
corpus does not contain), and seal before report (a report about a stale chain is worse than no report). Stopping at the first
non-zero exit is the whole value of the file.
*It re-reads the stopping-condition screen afterwards*, so what is seen is the state after the seals rather than the state before
them, which is the only version worth reading.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "RUNBOOK.md"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                           # noqa: E402
from boring_alpha import journal                      # noqa: E402

BLOCK = re.compile(r"```sh\n(.*?)\n```", re.DOTALL)


def published_commands() -> list[list[str]]:
    """The runbook's own command block, stripped of its comments, in the order it was published."""

    match = BLOCK.search(RUNBOOK.read_text())
    if not match:
        raise SystemExit(f"{RUNBOOK.name} has no ```sh block; the procedure is the authority and it is missing")
    commands = []
    for line in match.group(1).splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            commands.append(shlex.split(line))
    if not commands:
        raise SystemExit("the runbook's command block is empty")
    return commands


def books_on_disk() -> list[str]:
    directory = paper.PAPER_DIR / "books"
    if not directory.exists():
        return []
    return sorted(d.name for d in directory.iterdir() if (d / "ledger.jsonl").exists())


def corpus_last() -> journal.date | None:
    """The last session the corpus contains — the same number `command_step` compares against, read rather than re-derived.

    The engine seals at `max(data.dates)`, which is whatever the exchange last finished trading and not a calendar month end,
    so this is the only honest way to know whether a seal is due without running one.
    """

    data = paper.load_data()
    return max(data.dates) if data.dates else None


def head_of(book: str) -> journal.Entry | None:
    path = paper.PAPER_DIR / ("ledger.jsonl" if book == "root" else f"books/{book}/ledger.jsonl")
    chain = paper.read(path) if path.exists() else ()
    return chain[-1] if chain else None


def not_due(book: str, asof) -> str | None:
    """Why a seal is not due, or None where it is. Same comparison the engine makes, same words."""

    head = head_of(book)
    if head is None:
        return "the book has no anchor"
    if asof is None or asof <= head.asof:
        return f"corpus ends {asof}, book `{book}` already closed at {head.asof}"
    return None


def plan() -> list[tuple[list[str], str]]:
    """What will run, and why. Every book on disk gets the same seal command, which the block leaves to prose.

    The block's per-book line is found rather than assumed, so adding a fourth book to the directory adds its seal without
    anybody editing this file or the runbook.
    """

    commands = published_commands()
    seal = next((c for c in commands if "step" in c and "--book" in c), None)
    asof = corpus_last()
    out: list[tuple[list[str], str]] = []
    for command in commands:
        out.append((command, "published procedure"))
        if command is seal:
            for book in books_on_disk():
                if command[-1] != book:
                    out.append(([book if a == command[-1] else a for a in command], f"book `{book}` found on disk"))
    # Annotate every seal with whether the calendar actually asks for it, so a mid-month run can skip honestly instead of
    # stopping on a refusal that is a fact about the date and not a fault.
    annotated: list[tuple[list[str], str, str | None]] = []
    for command, why in out:
        reason = None
        if "step" in command:
            book = command[command.index("--book") + 1] if "--book" in command else "root"
            reason = not_due(book, asof)
        annotated.append((command, why, reason))
    return annotated


def resolve(command: list[str]) -> list[str]:
    """Rewrite the interpreter to the one running this file.

    The runbook writes `.venv/bin/python` because that is what an operator types. A runner that shelled out to a literal path
    would break the moment the suite ran under a different interpreter, and a runner that silently kept going after such a
    breakage would report a month that never happened.
    """

    first = command[0]
    if first.endswith("python") or first.endswith("python3"):
        return [sys.executable, *command[1:]]
    return list(command)


def run(plan_rows: list[tuple]) -> tuple[int, int, list[dict]]:
    """Execute the plan, skipping seals the calendar has not asked for. Returns (attempted, succeeded, log)."""

    log: list[dict] = []
    for index, row in enumerate(plan_rows):
        command, why, skip = row[0], row[1], (row[2] if len(row) > 2 else None)
        if skip:
            print(f"  [{index + 1}/{len(plan_rows)}] {' '.join(command)}  SKIPPED — not due: {skip}")
            log.append({"command": " ".join(command), "why": why, "exit": 0, "skipped": skip})
            continue
        argv = resolve(command)
        try:
            proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=900)
            code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except Exception as exc:                                              # a missing interpreter is a failure, not a crash
            code, out = 255, f"{type(exc).__name__}: {exc}"
        log.append({"command": " ".join(command), "why": why, "exit": code,
                    "tail": " | ".join(l.strip() for l in out.strip().splitlines()[-2:])})
        print(f"  [{index + 1}/{len(plan_rows)}] {' '.join(command)}"
              f"{'  (' + why + ')' if why != 'published procedure' else ''}")
        for line in out.strip().splitlines()[-12:]:
            print(f"      {line}")
        if code != 0:
            print(f"\n  STOPPED: `{command[-2] if '--' in command[-1] else command[-1]}` exited {code}."
                  f"\n  The rest of the procedure did not run, and the month is not sealed until it does.")
            return len(log), sum(1 for r in log if r["exit"] == 0) - 1, log
    return len(log), len(log), log


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print the plan and run nothing")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = plan()
    if args.dry_run:
        print(f"# the monthly procedure, {len(rows)} commands, in this order")
        for index, row in enumerate(rows, 1):
            command, why, skip = row[0], row[1], (row[2] if len(row) > 2 else None)
            note = "" if why == "published procedure" else f"   [{why}]"
            print(f"  {index:2}. {' '.join(command)}{note}" + (f"   — not due: {skip}" if skip else ""))
        print("\n  Nothing ran. Every command above is the published procedure or a mechanical consequence of a book on disk.")
        print("  A skipped seal is a fact about the calendar, not an error: the engine seals at the corpus's last session.")
        return 0

    ran, passed, log = run(rows)
    if args.json:
        print(json.dumps({"ran": ran, "passed": passed, "log": log}, indent=2))
    if passed < ran:
        print("\n  The procedure is incomplete, so no summary is printed. A month that stopped halfway is not a month.")
        return 1
    print("\n# after the seals, the stopping conditions again")
    screen = subprocess.run(resolve([".venv/bin/python", "tools/forward_p0.py", "--status"]), cwd=ROOT,
                            capture_output=True, text=True)
    print(screen.stdout.rstrip())
    return 0 if screen.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
