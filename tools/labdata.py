"""One answer to "where does the lab's state live", so a rehearsal can point it somewhere disposable.

Two files need this and they need it to agree: `paper.py`, which owns the books, and `journalctl.py`, which verifies the chain the books
write. Everything else reaches the books through `paper.PAPER_DIR` and inherits the answer rather than restating it.

The override exists for one purpose, and it is not convenience. The monthly loop has a code path — *seal* — that runs once a month and
that has never yet run for real: the first real seal is 2026-09-30, and a first run of a monthly procedure is also its first test
(`docs/RUNBOOK.md`). A rehearsal therefore has to be able to run the whole published loop against a throwaway copy of the tree with a
synthetic corpus advanced to the seal date. That copy must be reachable by name, and the real tree must be unaddressable by accident, so
the environment variable is read in exactly one place and defaults to the repository.

What the override deliberately does **not** cover: `journalctl.py`'s pinned comparator snapshot. That directory is an anchor — the thing
`verify` checks the chain against — and an override that could move an anchor would turn a verification tool into a way of passing. The
rehearsal verifies a copy of the chain against the same immutable anchor, which is the only version of the exercise worth doing.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ENV_VAR = "BORINGALPHA_DATA"


def data_root() -> Path:
    """The lab's writable state: `data/paper`, `data/journal`, `data/current`. Real tree unless a rehearsal says otherwise."""

    override = os.environ.get(ENV_VAR)
    if not override:
        return ROOT / "data"
    path = Path(override).expanduser().resolve()
    if path == ROOT / "data" or path == ROOT.resolve():
        # Both ways of saying "the archive itself". The second is the typo that matters: a rehearsal pointed at the repository reads like a
        # rehearsal, and then writes into the append-only ledgers the whole objective depends on. Refusing is the only answer that cannot
        # be misread, and the caller who really means the real tree should simply unset the variable.
        raise SystemExit(f"{ENV_VAR}={override} names the real tree; unset it to run for real, or point it at a copy to rehearse")
    if not path.is_dir():
        raise SystemExit(f"{ENV_VAR}={override} is not a directory; a rehearsal must point at one it built")
    return path


def is_rehearsal() -> bool:
    """True when the state being touched is a copy. Anything that writes should be able to say which tree it is in."""

    return data_root() != ROOT / "data"
