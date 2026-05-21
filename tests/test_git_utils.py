from pathlib import Path

import pytest

from mimo_commit.git_utils import (
    GitError,
    commits_between,
    is_git_repo,
    latest_tag,
    parse_version_tag,
    repo_root,
    run_git,
    staged_diff,
    staged_files,
)


def test_parse_version_tag_with_prefix():
    assert parse_version_tag("v1.2.3") == (1, 2, 3)


def test_parse_version_tag_without_prefix():
    assert parse_version_tag("1.2.3") == (1, 2, 3)


def test_parse_version_tag_with_pre_release():
    assert parse_version_tag("v2.0.0-rc.1") == (2, 0, 0)


def test_parse_version_tag_rejects_garbage():
    assert parse_version_tag("release") is None
    assert parse_version_tag("v1.2") is None
    assert parse_version_tag("") is None


def test_is_git_repo_true(populated_repo: Path):
    assert is_git_repo(populated_repo)


def test_is_git_repo_false(tmp_path: Path):
    assert not is_git_repo(tmp_path)


def test_repo_root(populated_repo: Path):
    assert repo_root(populated_repo) == populated_repo.resolve()


def test_run_git_propagates_failure(tmp_path: Path):
    with pytest.raises(GitError):
        run_git(["status"], cwd=tmp_path)


def test_latest_tag_returns_tag(populated_repo: Path):
    assert latest_tag(populated_repo) == "v0.1.0"


def test_latest_tag_returns_none_when_no_tags(git_repo: Path):
    git_repo._git("commit", "--allow-empty", "-m", "feat: bootstrap")  # type: ignore[attr-defined]
    assert latest_tag(git_repo) is None


def test_commits_between_tag_and_head(populated_repo: Path):
    commits = commits_between("v0.1.0", "HEAD", cwd=populated_repo)
    assert len(commits) == 3
    subjects = [c.subject for c in commits]
    assert subjects == [
        "feat!: drop legacy endpoint",
        "fix: correct return value",
        "feat(api): add f()",
    ]


def test_commits_between_full_history(git_repo: Path):
    _git = git_repo._git  # type: ignore[attr-defined]
    (git_repo / "a.txt").write_text("a")
    _git("add", "a.txt")
    _git("commit", "-m", "feat: first")
    commits = commits_between(None, "HEAD", cwd=git_repo)
    assert len(commits) == 1
    assert commits[0].subject == "feat: first"
    assert commits[0].author == "Test"


def test_staged_diff_and_files(git_repo: Path):
    _git = git_repo._git  # type: ignore[attr-defined]
    (git_repo / "a.txt").write_text("hello\n")
    _git("add", "a.txt")
    diff = staged_diff(cwd=git_repo)
    assert "diff --git" in diff
    assert "a.txt" in diff
    assert staged_files(cwd=git_repo) == ["a.txt"]
