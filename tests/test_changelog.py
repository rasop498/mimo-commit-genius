from __future__ import annotations

from mimo_commit.changelog import (
    generate_changelog,
    group_commits,
    render_grouped_for_prompt,
    render_markdown,
)
from mimo_commit.git_utils import GitCommit
from mimo_commit.mimo_client import CompletionResult


def _commit(subject: str, body: str = "", sha: str = "deadbee", short: str | None = None) -> GitCommit:
    return GitCommit(
        sha=sha,
        short_sha=short or sha[:7],
        author="dev",
        email="dev@example.com",
        date="2026-05-21",
        subject=subject,
        body=body,
    )


def test_group_commits_buckets_by_type():
    commits = [
        _commit("feat: add a"),
        _commit("fix(api): fix b"),
        _commit("docs: tidy"),
        _commit("not a conventional message"),
    ]
    grouped = group_commits(commits)
    assert len(grouped["feat"]) == 1
    assert len(grouped["fix"]) == 1
    assert len(grouped["docs"]) == 1
    assert len(grouped["other"]) == 1


def test_group_commits_detects_breaking_change():
    commits = [
        _commit(
            "feat: rotate tokens",
            body="BREAKING CHANGE: old tokens are invalidated",
        ),
    ]
    grouped = group_commits(commits)
    assert len(grouped["breaking"]) == 1
    assert grouped["breaking"][0].breaking is True
    assert "invalidated" in (grouped["breaking"][0].breaking_description or "")


def test_render_markdown_includes_categories():
    commits = [
        _commit("feat: shiny", sha="1111111"),
        _commit("fix: oops", sha="2222222"),
        _commit("perf: faster", sha="3333333"),
        _commit("chore: tidy", sha="4444444"),  # hidden
    ]
    md = render_markdown("1.2.0", commits, date="2026-05-21")
    assert "## 1.2.0 (2026-05-21)" in md
    assert "### Features" in md
    assert "### Bug Fixes" in md
    assert "### Performance" in md
    assert "shiny" in md
    assert "(1111111)" in md


def test_render_markdown_no_changes():
    md = render_markdown("0.0.0", [], date="2026-05-21")
    assert "No notable changes" in md


def test_render_markdown_breaking_section_first():
    commits = [
        _commit("feat: shiny", sha="1111111"),
        _commit(
            "feat: rotate",
            body="BREAKING CHANGE: rotated",
            sha="2222222",
        ),
    ]
    md = render_markdown("2.0.0", commits)
    # The breaking section should come before Features
    assert md.index("BREAKING CHANGES") < md.index("Features")


def test_render_grouped_for_prompt_skips_empty_categories():
    text = render_grouped_for_prompt([_commit("docs: x", sha="abcdefg")])
    assert "Documentation" in text
    assert "Features" not in text


def test_generate_changelog_without_llm_is_deterministic():
    commits = [_commit("feat: a", sha="aaaaaaa"), _commit("fix: b", sha="bbbbbbb")]
    result = generate_changelog("1.0.0", commits, client=None, date="2026-05-21")
    assert result.completion is None
    assert "Features" in result.markdown
    assert "Bug Fixes" in result.markdown


def test_generate_changelog_with_llm_uses_completion():
    class _StubClient:
        def complete(self, system_prompt, user_prompt, **kwargs):  # noqa: ANN001
            return CompletionResult(
                content="## 1.0.0\n\n### Features\n- nice (aaaaaaa)",
                model="mimo-v2.5-instruct",
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                latency_ms=50.0,
                cost_usd=0.0000003,
            )

    commits = [_commit("feat: nice", sha="aaaaaaa")]
    result = generate_changelog(
        "1.0.0", commits, client=_StubClient(), date="2026-05-21"  # type: ignore[arg-type]
    )
    assert result.completion is not None
    assert "nice" in result.markdown
