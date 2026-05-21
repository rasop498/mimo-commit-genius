"""Shared fixtures for the mimo-commit-genius test suite."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class GitFixture:
    """A disposable git repository with a callable ``_git`` helper.

    Provided as a wrapper because :class:`pathlib.Path` does not accept
    arbitrary attributes.
    """

    path: Path
    _git: Callable[..., subprocess.CompletedProcess[str]]

    # Allow tests to use the fixture in places that expect a Path
    def __fspath__(self) -> str:
        return str(self.path)

    def __truediv__(self, other: str | Path) -> Path:
        return self.path / other

    @property
    def parent(self) -> Path:
        return self.path.parent

    def resolve(self) -> Path:
        return self.path.resolve()

    def exists(self) -> bool:
        return self.path.exists()


def _make_git_env() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_AUTHOR_DATE": "2026-05-21T12:00:00Z",
        "GIT_COMMITTER_DATE": "2026-05-21T12:00:00Z",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }


@pytest.fixture
def git_repo(tmp_path: Path) -> GitFixture:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    env = _make_git_env()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo_dir)],
        check=True,
        capture_output=True,
        env=env,
    )

    def _git(*args: str, message_input: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo_dir), *args],
            check=True,
            capture_output=True,
            text=True,
            input=message_input,
            env=env,
        )

    return GitFixture(path=repo_dir, _git=_git)


@pytest.fixture
def populated_repo(git_repo: GitFixture) -> GitFixture:
    """Repo with a small but realistic commit history for changelog/release tests."""
    _git = git_repo._git
    (git_repo / "README.md").write_text("hello\n")
    _git("add", "README.md")
    _git("commit", "-m", "chore: initial commit")
    _git("tag", "v0.1.0")

    (git_repo / "feature.py").write_text("def f(): return 1\n")
    _git("add", "feature.py")
    _git("commit", "-m", "feat(api): add f()")

    (git_repo / "feature.py").write_text("def f(): return 2\n")
    _git("add", "feature.py")
    _git("commit", "-m", "fix: correct return value")

    (git_repo / "docs.md").write_text("docs\n")
    _git("add", "docs.md")
    _git(
        "commit",
        "-m",
        "feat!: drop legacy endpoint\n\nBREAKING CHANGE: /v1/old has been removed",
    )

    return git_repo
