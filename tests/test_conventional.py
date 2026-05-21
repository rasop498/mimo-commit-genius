import pytest

from mimo_commit.conventional import (
    VALID_TYPES,
    format_commit,
    is_conventional,
    parse,
)


def test_parses_simple_header():
    commit = parse("feat: add login form")
    assert commit is not None
    assert commit.type == "feat"
    assert commit.scope is None
    assert commit.subject == "add login form"
    assert commit.body == ""
    assert commit.breaking is False
    assert commit.footers == []


def test_parses_scope():
    commit = parse("fix(api): handle null user")
    assert commit is not None
    assert commit.type == "fix"
    assert commit.scope == "api"
    assert commit.subject == "handle null user"


def test_parses_bang_breaking():
    commit = parse("refactor!: rename public method")
    assert commit is not None
    assert commit.breaking is True
    assert commit.breaking_description is None


def test_parses_breaking_change_footer():
    msg = (
        "feat(auth): rotate session tokens\n"
        "\n"
        "Sessions are now rotated on every login.\n"
        "\n"
        "BREAKING CHANGE: old session tokens are invalidated on deploy"
    )
    commit = parse(msg)
    assert commit is not None
    assert commit.breaking is True
    assert commit.breaking_description == "old session tokens are invalidated on deploy"
    assert commit.body.startswith("Sessions are now rotated")


def test_rejects_unknown_type():
    assert parse("foo: do something") is None


def test_rejects_no_colon():
    assert parse("just a sentence") is None


def test_rejects_empty():
    assert parse("") is None
    assert parse("   \n  ") is None


def test_is_conventional_helper():
    assert is_conventional("docs: tidy README")
    assert not is_conventional("update readme")


@pytest.mark.parametrize("commit_type", VALID_TYPES)
def test_all_valid_types_are_accepted(commit_type: str):
    assert parse(f"{commit_type}: stuff") is not None


def test_format_commit_basic():
    msg = format_commit("feat", "add login")
    assert msg.startswith("feat: add login")


def test_format_commit_with_scope_body_footer():
    msg = format_commit(
        "fix",
        "ignore null user",
        scope="api",
        body="When a user is missing we now skip metric emission.",
        footers=["Refs: #123"],
    )
    assert "fix(api): ignore null user" in msg
    assert "When a user" in msg
    assert "Refs: #123" in msg


def test_format_commit_breaking():
    msg = format_commit(
        "feat",
        "drop v1 endpoint",
        breaking_description="/v1 has been removed",
    )
    assert "BREAKING CHANGE: /v1 has been removed" in msg


def test_format_commit_rejects_bad_type():
    with pytest.raises(ValueError):
        format_commit("nope", "bad")
