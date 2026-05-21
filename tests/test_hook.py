from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from mimo_commit.hook import HOOK_MARKER, hook_path, install_hook, uninstall_hook


def test_install_hook_creates_executable_file(git_repo: Path):
    result = install_hook(cwd=git_repo)
    assert result.action == "installed"
    path = hook_path(cwd=git_repo)
    assert path.exists()
    assert HOOK_MARKER in path.read_text()
    mode = path.stat().st_mode
    assert mode & stat.S_IXUSR


def test_install_hook_is_idempotent(git_repo: Path):
    install_hook(cwd=git_repo)
    result = install_hook(cwd=git_repo)
    assert result.action == "already-installed"


def test_install_hook_refuses_to_clobber_unrelated_hook(git_repo: Path):
    path = hook_path(cwd=git_repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\necho 'pre-existing'\n")
    with pytest.raises(RuntimeError):
        install_hook(cwd=git_repo)


def test_install_hook_force_overwrites_unrelated(git_repo: Path):
    path = hook_path(cwd=git_repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\necho 'pre-existing'\n")
    result = install_hook(cwd=git_repo, force=True)
    assert result.action == "updated"
    assert HOOK_MARKER in path.read_text()


def test_uninstall_hook_removes_only_our_hook(git_repo: Path):
    install_hook(cwd=git_repo)
    assert uninstall_hook(cwd=git_repo) is True
    assert not hook_path(cwd=git_repo).exists()


def test_uninstall_hook_refuses_unrelated(git_repo: Path):
    path = hook_path(cwd=git_repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\necho 'other'\n")
    with pytest.raises(RuntimeError):
        uninstall_hook(cwd=git_repo)


def test_uninstall_hook_when_absent(tmp_path: Path):
    # Should return False rather than raising when there's nothing to remove.
    fake = tmp_path / ".git" / "hooks"
    fake.mkdir(parents=True, exist_ok=True)
    # Use a real repo for this test rather than the empty tmp_path
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
