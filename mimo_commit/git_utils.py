"""Git plumbing helpers used by the CLI and other modules.

Everything here shells out to the ``git`` binary so it works in any standard
repo without extra dependencies.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    """Raised when a git invocation fails."""


def run_git(args: list[str], cwd: str | os.PathLike[str] | None = None) -> str:
    """Run a git command and return stdout. Raises :class:`GitError` on failure."""
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def is_git_repo(cwd: str | os.PathLike[str] | None = None) -> bool:
    try:
        run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd)
        return True
    except GitError:
        return False


def repo_root(cwd: str | os.PathLike[str] | None = None) -> Path:
    """Return the absolute path to the repository's top-level directory."""
    out = run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return Path(out.strip())


def git_dir(cwd: str | os.PathLike[str] | None = None) -> Path:
    """Return the path to the ``.git`` directory (resolved for worktrees)."""
    out = run_git(["rev-parse", "--git-dir"], cwd=cwd)
    path = Path(out.strip())
    if not path.is_absolute():
        path = Path(cwd or os.getcwd()) / path
    return path.resolve()


def staged_diff(cwd: str | os.PathLike[str] | None = None) -> str:
    """Return the diff of staged changes (``git diff --cached``)."""
    return run_git(["diff", "--cached", "--no-color"], cwd=cwd)


def working_diff(cwd: str | os.PathLike[str] | None = None) -> str:
    """Return the diff of unstaged changes."""
    return run_git(["diff", "--no-color"], cwd=cwd)


def staged_files(cwd: str | os.PathLike[str] | None = None) -> list[str]:
    """Return a list of file paths that are currently staged."""
    out = run_git(["diff", "--cached", "--name-only"], cwd=cwd)
    return [line for line in out.splitlines() if line]


def latest_tag(cwd: str | os.PathLike[str] | None = None) -> str | None:
    """Return the most recent annotated/lightweight tag, or ``None`` if there is none."""
    try:
        out = run_git(["describe", "--tags", "--abbrev=0"], cwd=cwd)
        tag = out.strip()
        return tag or None
    except GitError:
        return None


@dataclass(frozen=True)
class GitCommit:
    sha: str
    short_sha: str
    author: str
    email: str
    date: str
    subject: str
    body: str

    @property
    def message(self) -> str:
        if self.body:
            return f"{self.subject}\n\n{self.body}"
        return self.subject


_LOG_FORMAT = "%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b%x1e"


def commits_between(
    from_ref: str | None,
    to_ref: str = "HEAD",
    cwd: str | os.PathLike[str] | None = None,
) -> list[GitCommit]:
    """Return commits reachable from ``to_ref`` but not from ``from_ref``.

    If ``from_ref`` is ``None``, returns all commits up to ``to_ref``.
    """
    if from_ref:
        range_arg = f"{from_ref}..{to_ref}"
    else:
        range_arg = to_ref

    out = run_git(
        ["log", f"--pretty=format:{_LOG_FORMAT}", range_arg],
        cwd=cwd,
    )

    commits: list[GitCommit] = []
    for raw in out.split("\x1e"):
        record = raw.strip("\n")
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) < 7:
            continue
        sha, short, author, email, date, subject, body = parts[:7]
        commits.append(
            GitCommit(
                sha=sha,
                short_sha=short,
                author=author,
                email=email,
                date=date,
                subject=subject,
                body=body.strip(),
            )
        )
    return commits


_VERSION_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].+)?$")


def parse_version_tag(tag: str) -> tuple[int, int, int] | None:
    """Extract a (major, minor, patch) tuple from a version-like tag, or ``None``."""
    match = _VERSION_TAG_RE.match(tag.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))
