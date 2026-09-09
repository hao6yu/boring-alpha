"""Tests for `tools/labdata.py`, the one place the lab's state root can be redirected.

The redirection exists so a rehearsal can run the published monthly block against a copy of `data/` (see
`rehearse_forward.py --scenario published`). An escape hatch that can point at the real tree is not a safety device, so most of these tests
are about refusing.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import labdata                                                       # noqa: E402


@contextlib.contextmanager
def _env(**pairs):
    saved = {k: os.environ.get(k) for k in pairs}
    os.environ.update(pairs)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class TheResolver(unittest.TestCase):
    def test_the_default_is_the_repository_and_nothing_else(self):
        self.assertEqual(labdata.data_root(), labdata.ROOT / "data")
        self.assertFalse(labdata.is_rehearsal())

    def test_an_override_is_honoured_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _env(BORINGALPHA_DATA=tmp):
                self.assertEqual(labdata.data_root(), Path(tmp).resolve())
                self.assertTrue(labdata.is_rehearsal())

    def test_an_override_naming_a_missing_directory_refuses(self):
        with self.assertRaises(SystemExit) as ctx:
            with _env(BORINGALPHA_DATA="/tmp/not-a-lab-tree-anywhere"):
                labdata.data_root()
        self.assertIn("not a directory", str(ctx.exception))

    def test_the_dangerous_typo_is_the_one_that_names_the_real_tree(self):
        """Pointing an "override" at the repository looks like an override and is a rehearsal aimed at the archive."""

        with self.assertRaises(SystemExit) as ctx:
            with _env(BORINGALPHA_DATA=str(labdata.ROOT)):
                labdata.data_root()
        self.assertIn("real tree", str(ctx.exception))
        with self.assertRaises(SystemExit):
            with _env(BORINGALPHA_DATA=str(labdata.ROOT / "data")):
                labdata.data_root()                       # naming the real data dir is the same act, spoken differently
        self.assertFalse(labdata.is_rehearsal())


class TheAnchorStaysPut(unittest.TestCase):
    def test_the_journal_moves_with_the_override_and_the_pinned_snapshot_does_not(self):
        import journalctl                                           # noqa: PLC0415

        self.assertEqual(journalctl.JOURNAL_DIR, labdata.ROOT / "data" / "journal")
        self.assertEqual(journalctl.SNAPSHOT_DIR.name, "20260904T192633Z",
                         "the pinned comparator snapshot is an anchor; a rehearsal verifies a copy of a chain, never a moved anchor")
        self.assertTrue(journalctl.SNAPSHOT_DIR.exists())

    def test_the_engine_takes_its_state_root_from_the_same_resolver(self):
        import paper                                                # noqa: PLC0415

        self.assertEqual(paper.DATA, labdata.ROOT / "data")
        self.assertEqual(paper.PAPER_DIR, paper.DATA / "paper")
        self.assertEqual(paper.SNAPSHOT, paper.DATA / "current" / "market_daily.csv")


if __name__ == "__main__":
    unittest.main()
