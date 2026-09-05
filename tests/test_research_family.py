"""Canonical journal location uses only temporary Git metadata, never prices."""

from pathlib import Path
import subprocess

import pytest

from boring_alpha import research_family


def git(root, *arguments):
    return subprocess.run(["git", "-C", str(root), *arguments], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repository(tmp_path, monkeypatch):
    root = tmp_path / "fictional-package"
    root.mkdir()
    git(root, "init", "--quiet")
    # An empty commit exists only in this throwaway fixture so Git can create
    # a linked worktree. No BoringAlpha branch or research artifact is touched.
    git(root, "-c", "user.name=Fictional test", "-c", "user.email=fixture@example.invalid",
        "commit", "--quiet", "--allow-empty", "-m", "Temporary worktree fixture")
    monkeypatch.setattr(research_family, "SOURCE_ROOT", root)
    return root


def test_candidates_share_one_read_only_location_independent_of_cwd(repository, tmp_path, monkeypatch):
    expected = (repository / ".git/boring-alpha/journals/BA-TREND.json").resolve()
    first = research_family.canonical_journal_path("BA-001")
    elsewhere = tmp_path / "different-config-directory"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert research_family.canonical_journal_path("BA-002") == first == expected
    assert not expected.parent.exists()


def test_linked_worktree_uses_common_history_not_its_private_gitdir(repository, tmp_path, monkeypatch):
    expected = research_family.canonical_journal_path("BA-002")
    linked = tmp_path / "linked-fictional-package"
    git(repository, "worktree", "add", "--quiet", "--detach", str(linked))
    monkeypatch.setattr(research_family, "SOURCE_ROOT", linked)
    assert research_family.canonical_journal_path("BA-001") == expected
    assert not expected.parent.exists()


def test_foreign_git_environment_cannot_redirect_the_family_history(repository, tmp_path, monkeypatch):
    foreign = tmp_path / "foreign-checkout"
    foreign.mkdir()
    git(foreign, "init", "--quiet")
    expected = research_family.canonical_journal_path("BA-002")
    monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_COMMON_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(foreign))
    assert research_family.canonical_journal_path("BA-002") == expected


def test_non_git_installation_refuses_without_falling_back_to_cwd(repository, tmp_path, monkeypatch):
    outside = tmp_path / "not-a-checkout"
    outside.mkdir()
    monkeypatch.setattr(research_family, "SOURCE_ROOT", outside)
    monkeypatch.chdir(repository)
    with pytest.raises(ValueError, match="historical research requires a Git checkout"):
        research_family.canonical_journal_path("BA-002")
    assert list(outside.iterdir()) == []


def test_unknown_candidate_refuses_before_git_lookup(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unregistered candidate consulted Git")
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="unregistered"):
        research_family.canonical_journal_path("BA-003")
