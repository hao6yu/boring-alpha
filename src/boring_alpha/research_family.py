"""Reviewed family lineage and the one shared checkout-local run journal.

Git's common directory is shared by linked worktrees. Neither a configuration
path nor the shell's working directory chooses a fresh research history.
"""
from datetime import date
from pathlib import Path
import os
import subprocess
from types import MappingProxyType

FAMILY_ID = "BA-TREND"
PROTECTED_START = date(2022, 1, 1)
REGISTERED_FAMILIES = MappingProxyType({"BA-001": FAMILY_ID, "BA-002": FAMILY_ID})
SOURCE_ROOT = Path(__file__).resolve().parents[2]


class ResearchAccessError(ValueError):
    """Refusal before parsing observations, or inability to record an attempt."""


def resolve_family(candidate_id: str) -> str:
    try:
        return REGISTERED_FAMILIES[candidate_id]
    except (KeyError, TypeError) as exc:
        raise ResearchAccessError(
            f"unregistered research candidate {candidate_id!r}; resolve reviewed lineage before input access"
        ) from exc


def canonical_journal_path(candidate_id: str) -> Path:
    """Locate, but never create, the family journal for this package checkout.

Historical execution from a source distribution outside Git is refused. A
separate clone has a separate common directory and must not be represented as
a fresh scientific holdout; this procedural guard does not police cloning.
"""
    family = resolve_family(candidate_id)
    try:
        result = subprocess.run(
            ["git", "-C", str(SOURCE_ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            check=True, capture_output=True, text=True,
            env={key: value for key, value in os.environ.items()
                 if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"}},
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ResearchAccessError(
            "historical research requires a Git checkout with a shared family journal; "
            "cannot resolve this package's Git common directory"
        ) from exc
    common = Path(result.stdout.strip())
    if not common.is_absolute() or not common.is_dir():
        raise ResearchAccessError("Git did not return an existing absolute common directory for the research journal")
    return common.resolve() / "boring-alpha" / "journals" / f"{family}.json"
