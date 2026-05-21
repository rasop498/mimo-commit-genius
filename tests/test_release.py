from __future__ import annotations

from mimo_commit.config import ReleaseConfig
from mimo_commit.git_utils import GitCommit
from mimo_commit.release import BumpKind, plan_release


def _commit(subject: str, body: str = "") -> GitCommit:
    return GitCommit(
        sha="0" * 40,
        short_sha="0000000",
        author="dev",
        email="dev@example.com",
        date="2026-05-21",
        subject=subject,
        body=body,
    )


def test_no_prior_tag_returns_initial_version():
    plan = plan_release(commits=[_commit("feat: a")], current_tag=None, initial_version="0.1.0")
    assert plan.next_version == "0.1.0"
    assert plan.bump is BumpKind.MINOR


def test_no_commits_returns_no_bump():
    plan = plan_release(commits=[], current_tag="v1.0.0")
    assert plan.bump is BumpKind.NONE
    assert plan.next_version == "v1.0.0"


def test_patch_bump_for_fix():
    plan = plan_release(commits=[_commit("fix: pick this")], current_tag="v1.2.3")
    assert plan.bump is BumpKind.PATCH
    assert plan.next_version == "v1.2.4"


def test_minor_bump_for_feat():
    plan = plan_release(
        commits=[_commit("fix: a"), _commit("feat: b")],
        current_tag="v1.2.3",
    )
    assert plan.bump is BumpKind.MINOR
    assert plan.next_version == "v1.3.0"


def test_major_bump_for_breaking_bang():
    plan = plan_release(commits=[_commit("feat!: drop")], current_tag="v1.2.3")
    assert plan.bump is BumpKind.MAJOR
    assert plan.next_version == "v2.0.0"


def test_major_bump_for_breaking_footer():
    plan = plan_release(
        commits=[_commit("feat: rotate", body="BREAKING CHANGE: rotate keys")],
        current_tag="v1.2.3",
    )
    assert plan.bump is BumpKind.MAJOR
    assert plan.next_version == "v2.0.0"


def test_pre_1_0_breaking_promotes_minor_only():
    plan = plan_release(commits=[_commit("feat!: drop")], current_tag="v0.5.7")
    assert plan.bump is BumpKind.MAJOR
    assert plan.next_version == "v0.6.0"


def test_keeps_tag_prefix_style():
    plan = plan_release(commits=[_commit("fix: x")], current_tag="1.0.0")
    assert plan.next_version == "1.0.1"


def test_unconventional_commits_ignored():
    plan = plan_release(commits=[_commit("update readme")], current_tag="v1.0.0")
    assert plan.bump is BumpKind.NONE


def test_custom_minor_type_via_config():
    cfg = ReleaseConfig(minor_bump_types=["feat", "feature"])
    plan = plan_release(
        commits=[_commit("feature: lol")],
        current_tag="v1.0.0",
        config=cfg,
    )
    assert plan.bump is BumpKind.MINOR


def test_lists_subjects_by_category():
    plan = plan_release(
        commits=[
            _commit("feat: a"),
            _commit("fix: b"),
            _commit("feat!: c"),
        ],
        current_tag="v1.0.0",
    )
    assert "a" in plan.feature_subjects
    assert "b" in plan.fix_subjects
    assert "c" in plan.breaking_subjects
