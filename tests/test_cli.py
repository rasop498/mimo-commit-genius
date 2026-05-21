from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from mimo_commit import cli
from mimo_commit.mimo_client import CompletionResult


def _run_cli(argv: list[str], monkeypatch: pytest.MonkeyPatch, cwd: Path) -> tuple[int, str, str]:
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_help_lists_subcommands(capsys: pytest.CaptureFixture[str]):
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    captured = capsys.readouterr()
    for cmd in ("suggest", "changelog", "release", "install-hook", "stats"):
        assert cmd in captured.out


def test_version_flag(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "mimo-commit" in capsys.readouterr().out


def test_stats_without_ping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    rc, out, _ = _run_cli(["stats"], monkeypatch, tmp_path)
    assert rc == 0
    assert "Model" in out


def test_suggest_outside_repo_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    rc, _, err = _run_cli(["suggest"], monkeypatch, tmp_path)
    assert rc != 0
    assert "git repository" in err


def test_suggest_with_no_staged_changes(monkeypatch: pytest.MonkeyPatch, git_repo: Path):
    rc, _, err = _run_cli(["suggest"], monkeypatch, git_repo)
    assert rc != 0
    assert "no staged changes" in err


def test_suggest_end_to_end_with_stub_client(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
):
    (git_repo / "x.py").write_text("def x():\n    return 1\n")
    git_repo._git("add", "x.py")  # type: ignore[attr-defined]

    class _Stub:
        def __init__(self, *a: Any, **kw: Any) -> None:
            self.total_requests = 0

        def complete(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> CompletionResult:
            return CompletionResult(
                content="feat(x): add x() helper",
                model="mimo-v2.5-instruct",
                prompt_tokens=100,
                completion_tokens=10,
                total_tokens=110,
                latency_ms=80.0,
                cost_usd=0.0000001,
            )

        def health_check(self) -> bool:  # pragma: no cover
            return True

    monkeypatch.setattr(cli, "MiMoClient", _Stub)
    rc, out, _ = _run_cli(["suggest"], monkeypatch, git_repo)
    assert rc == 0
    assert "feat(x): add x() helper" in out


def test_suggest_json_output(monkeypatch: pytest.MonkeyPatch, git_repo: Path):
    (git_repo / "y.py").write_text("y = 1\n")
    git_repo._git("add", "y.py")  # type: ignore[attr-defined]

    class _Stub:
        def __init__(self, *a: Any, **kw: Any) -> None:
            self.total_requests = 0

        def complete(self, *a: Any, **kw: Any) -> CompletionResult:
            return CompletionResult(
                content="chore: tweak y",
                model="mimo-v2.5-instruct",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                latency_ms=10.0,
                cost_usd=0.0,
            )

    monkeypatch.setattr(cli, "MiMoClient", _Stub)
    rc, out, _ = _run_cli(["suggest", "--json"], monkeypatch, git_repo)
    assert rc == 0
    payload = json.loads(out)
    assert payload["message"] == "chore: tweak y"
    assert payload["conventional"] is True
    assert payload["type"] == "chore"


def test_changelog_no_llm_renders_markdown(monkeypatch: pytest.MonkeyPatch, populated_repo: Path):
    rc, out, _ = _run_cli(["changelog", "1.0.0", "--no-llm"], monkeypatch, populated_repo)
    assert rc == 0
    assert "## 1.0.0" in out
    assert "Features" in out
    assert "BREAKING CHANGES" in out


def test_release_json(monkeypatch: pytest.MonkeyPatch, populated_repo: Path):
    rc, out, _ = _run_cli(["release", "--json"], monkeypatch, populated_repo)
    assert rc == 0
    payload = json.loads(out)
    assert payload["current"] == "v0.1.0"
    assert payload["bump"] == "major"
    # Pre-1.0 a "breaking" bump is intentionally demoted to minor
    assert payload["next"] == "v0.2.0"
    assert "drop legacy endpoint" in payload["breaking"]


def test_install_and_uninstall_hook(monkeypatch: pytest.MonkeyPatch, git_repo: Path):
    rc, out, _ = _run_cli(["install-hook"], monkeypatch, git_repo)
    assert rc == 0
    assert "installed" in out

    rc, out, _ = _run_cli(["install-hook", "--uninstall"], monkeypatch, git_repo)
    assert rc == 0
    assert "Removed" in out
