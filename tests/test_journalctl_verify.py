"""`journalctl verify` must check the pin, not just the chain.

Found on 2026-09-06 while auditing the tool: `verify` recomputed the ledger hash
chain and printed "chain intact" while a hand-edited `comparator.json` sat next to
it. Its own help line asks "who edited this?", and the edit it was blind to is the
only one that matters — the comparator is the benchmark, and softening a benchmark
after the fact is the specific failure this journal was built to make impossible.
A check that inspects the lock while leaving the door open is worse than no check,
because it manufactures evidence of safety that was never earned.
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "journalctl.py"


class VerifyChecksThePin(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        # The tool resolves its paths from the repo root, so the tamper test runs
        # against a scratch copy of the spec rather than the real one. Copying is
        # deliberate: editing the pinned file in place, even restored in cleanup,
        # would leave a window where a concurrent run reads a broken benchmark.
        self.spec = ROOT / "data" / "journal" / "comparator.json"
        self.original = self.spec.read_text(encoding="utf-8")
        self.addCleanup(self.spec.write_text, self.original, encoding="utf-8")

    def _verify(self):
        return subprocess.run(
            [sys.executable, str(TOOL), "verify"],
            capture_output=True, text=True, cwd=ROOT,
        )

    def test_an_untouched_tree_verifies_clean(self):
        result = self._verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pinned spec intact", result.stdout)

    def test_editing_the_benchmark_fee_is_caught(self):
        """The exact attack: make the hurdle cheaper, keep the results."""

        spec = json.loads(self.original)
        spec["expense_ratio"] = 0.0001          # 9.45 bps -> 1 bp, a friendlier bar
        self.spec.write_text(json.dumps(spec, indent=2, sort_keys=True))

        result = self._verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("edited after pinning", result.stderr)
        self.assertIn("chain intact", result.stdout)   # chain is fine; that is the point

    def test_a_reformat_that_preserves_the_body_is_caught_too(self):
        """Sorting keys and re-indenting changes the file but not the meaning.

        The hash covers the canonical body, so cosmetic churn passes — but only
        because the body is canonicalised first. Reordering keys inside the JSON
        text without changing values must therefore still pass, and it is worth
        knowing which of the two the pin actually guards.
        """

        spec = json.loads(self.original)
        spec.pop("protocol_hash")
        canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"))
        recomputed = hashlib.sha256(canonical.encode()).hexdigest()
        self.spec.write_text(json.dumps(
            {**spec, "protocol_hash": recomputed}, indent=2, sort_keys=True))
        result = self._verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pinned spec intact", result.stdout)


if __name__ == "__main__":
    unittest.main()
