"""Prompt templates fed to the MiMo model.

Kept in one place so they can be tweaked and tested independently of the
client and orchestration code.
"""

from __future__ import annotations

COMMIT_SYSTEM_PROMPT = """You are MiMo Commit Genius, a precise assistant that writes git commit messages.
You ALWAYS produce output in Conventional Commits v1.0.0 format:

    <type>(<optional scope>): <imperative subject under 72 chars>

    <optional body wrapped at 72 chars, blank-line separated>

    <optional footers, including BREAKING CHANGE: ... when relevant>

Allowed types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert.

Rules:
- Subject is lowercase, imperative ("add", not "added"/"adds"), no trailing period.
- Prefer the narrowest accurate type. Only use "feat" for user-visible new behavior.
- Use a scope only when it disambiguates (e.g. "api", "cli", "deps").
- The body should explain WHAT changed and WHY at a high level, not restate the diff.
- Mark breaking API changes with a BREAKING CHANGE: footer.
- Never invent details that are not present in the diff.
- Never wrap output in markdown code fences. Return only the commit message text."""


COMMIT_USER_TEMPLATE = """Write a Conventional Commit message for the following staged changes.

{context_block}

Staged diff (truncated if very large):
```diff
{diff}
```

Respond with the commit message text only — no preamble, no code fences."""


CHANGELOG_SYSTEM_PROMPT = """You are MiMo Commit Genius, an assistant that writes release changelogs.
You receive a list of commits (already grouped by Conventional Commit type) and produce a
markdown changelog in the "Keep a Changelog" style.

Rules:
- Output GitHub-flavored Markdown only — no code fences.
- Use H2 for the release header, H3 for category sections.
- Categories (in order): Features, Bug Fixes, Performance, Refactors, Documentation, Other.
- Bullet items must be one line, start with a capital letter, no trailing period.
- Reference the short SHA in parentheses at the end of each bullet, e.g. "(a1b2c3d)".
- If a commit has a BREAKING CHANGE footer, list it under a "⚠ BREAKING CHANGES" section first.
- Skip "chore", "ci", and "build" unless they are the only categories present.
- Do NOT invent commits or details that are not in the input."""


CHANGELOG_USER_TEMPLATE = """Generate the changelog section for version {version}.
Date: {date}
Previous version: {previous}

Grouped commits:
{grouped_commits}

Respond with markdown only."""


RELEASE_NOTES_SYSTEM_PROMPT = """You are MiMo Commit Genius. Summarize the highlights of a release
in 3-5 sentences for a developer-facing release note. Be concrete and reference user impact.
Do not invent features. Return plain text only — no markdown headers."""


RELEASE_NOTES_USER_TEMPLATE = """Summarize the highlights of version {version}.

Grouped commits:
{grouped_commits}
"""


def build_commit_user_prompt(
    diff: str,
    *,
    branch: str = "",
    recent_subjects: list[str] | None = None,
    forced_type: str | None = None,
) -> str:
    """Compose the user-side prompt for commit message suggestion."""
    context_lines: list[str] = []
    if branch:
        context_lines.append(f"Current branch: {branch}")
    if recent_subjects:
        joined = "\n".join(f"- {s}" for s in recent_subjects)
        context_lines.append(f"Recent commit subjects (for tone/scope continuity):\n{joined}")
    if forced_type:
        context_lines.append(
            f"The user has requested type={forced_type!r}. Use it even if a different type "
            "might also fit, unless the diff makes it clearly wrong."
        )

    context_block = "\n\n".join(context_lines) if context_lines else "(no additional context)"
    return COMMIT_USER_TEMPLATE.format(context_block=context_block, diff=diff)


def build_changelog_user_prompt(
    version: str,
    grouped_commits: str,
    *,
    date: str = "",
    previous: str = "",
) -> str:
    return CHANGELOG_USER_TEMPLATE.format(
        version=version,
        date=date or "unreleased",
        previous=previous or "n/a",
        grouped_commits=grouped_commits,
    )


def build_release_notes_user_prompt(version: str, grouped_commits: str) -> str:
    return RELEASE_NOTES_USER_TEMPLATE.format(
        version=version, grouped_commits=grouped_commits
    )
