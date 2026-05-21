"""Changelog generation from commit history.

This module groups commits by Conventional Commit type and renders either
a deterministic markdown changelog (no LLM call), or a polished one via
:meth:`MiMoClient.complete` when an :class:`MiMoClient` is supplied.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from .conventional import parse
from .git_utils import GitCommit
from .mimo_client import CompletionResult, MiMoClient
from .prompts import (
    CHANGELOG_SYSTEM_PROMPT,
    RELEASE_NOTES_SYSTEM_PROMPT,
    build_changelog_user_prompt,
    build_release_notes_user_prompt,
)

# Order matters — it controls the rendered section order.
CATEGORY_ORDER: list[tuple[str, str]] = [
    ("breaking", "⚠ BREAKING CHANGES"),
    ("feat", "Features"),
    ("fix", "Bug Fixes"),
    ("perf", "Performance"),
    ("refactor", "Refactors"),
    ("docs", "Documentation"),
    ("test", "Tests"),
    ("other", "Other"),
]

HIDDEN_TYPES = {"chore", "ci", "build", "style"}


@dataclass
class GroupedCommit:
    sha: str
    short_sha: str
    type: str
    scope: str | None
    subject: str
    breaking: bool
    breaking_description: str | None


def group_commits(commits: list[GitCommit]) -> dict[str, list[GroupedCommit]]:
    """Bucket a list of git commits by their Conventional Commit category."""
    buckets: dict[str, list[GroupedCommit]] = {key: [] for key, _ in CATEGORY_ORDER}

    for commit in commits:
        parsed = parse(commit.message)
        if parsed is None:
            buckets["other"].append(
                GroupedCommit(
                    sha=commit.sha,
                    short_sha=commit.short_sha,
                    type="other",
                    scope=None,
                    subject=commit.subject,
                    breaking=False,
                    breaking_description=None,
                )
            )
            continue

        grouped = GroupedCommit(
            sha=commit.sha,
            short_sha=commit.short_sha,
            type=parsed.type,
            scope=parsed.scope,
            subject=parsed.subject,
            breaking=parsed.breaking,
            breaking_description=parsed.breaking_description,
        )

        if parsed.breaking:
            buckets["breaking"].append(grouped)

        target = parsed.type if parsed.type in buckets else "other"
        buckets[target].append(grouped)

    return buckets


def render_markdown(
    version: str,
    commits: list[GitCommit],
    *,
    date: str | None = None,
    previous: str | None = None,
) -> str:
    """Render a deterministic markdown changelog without calling the LLM.

    Useful as a fallback when no MiMo client is configured, and as ground
    truth for unit tests.
    """
    date_str = date or _dt.date.today().isoformat()
    grouped = group_commits(commits)

    lines: list[str] = []
    header = f"## {version} ({date_str})"
    if previous:
        header += f" — previous: {previous}"
    lines.append(header)
    lines.append("")

    rendered_any = False
    for key, title in CATEGORY_ORDER:
        items = grouped.get(key) or []
        if not items:
            continue
        # Avoid noisy categories unless they're the only ones present
        if key == "other" and rendered_any and len(items) == sum(
            len(v) for k, v in grouped.items() if k != "other"
        ):
            continue

        lines.append(f"### {title}")
        lines.append("")
        for item in items:
            scope = f"**{item.scope}**: " if item.scope else ""
            bang = " ⚠" if item.breaking and key != "breaking" else ""
            extra = ""
            if key == "breaking" and item.breaking_description:
                extra = f" — {item.breaking_description}"
            lines.append(f"- {scope}{item.subject}{bang} ({item.short_sha}){extra}")
        lines.append("")
        rendered_any = True

    if not rendered_any:
        lines.append("_No notable changes._")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_grouped_for_prompt(commits: list[GitCommit]) -> str:
    """Render commits as a plain-text bulleted summary the LLM can chew on."""
    grouped = group_commits(commits)
    out: list[str] = []
    for key, title in CATEGORY_ORDER:
        items = grouped.get(key) or []
        if not items:
            continue
        out.append(f"{title}:")
        for item in items:
            scope = f"({item.scope}) " if item.scope else ""
            tag = " [BREAKING]" if item.breaking else ""
            out.append(f"- {scope}{item.subject}{tag} ({item.short_sha})")
        out.append("")
    return "\n".join(out).strip() or "(no commits)"


@dataclass
class ChangelogResult:
    markdown: str
    completion: CompletionResult | None


def generate_changelog(
    version: str,
    commits: list[GitCommit],
    *,
    client: MiMoClient | None = None,
    date: str | None = None,
    previous: str | None = None,
    use_llm: bool = True,
) -> ChangelogResult:
    """Generate a release changelog.

    Falls back to deterministic markdown when ``client`` is missing or
    ``use_llm`` is ``False``.
    """
    if not client or not use_llm:
        return ChangelogResult(
            markdown=render_markdown(version, commits, date=date, previous=previous),
            completion=None,
        )

    grouped_text = render_grouped_for_prompt(commits)
    user_prompt = build_changelog_user_prompt(
        version=version,
        grouped_commits=grouped_text,
        date=date or _dt.date.today().isoformat(),
        previous=previous or "",
    )
    completion = client.complete(
        system_prompt=CHANGELOG_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    return ChangelogResult(markdown=completion.content.strip() + "\n", completion=completion)


def generate_release_notes(
    version: str,
    commits: list[GitCommit],
    client: MiMoClient,
) -> CompletionResult:
    """Produce 3-5 sentence release notes via the LLM."""
    grouped_text = render_grouped_for_prompt(commits)
    user_prompt = build_release_notes_user_prompt(version=version, grouped_commits=grouped_text)
    return client.complete(
        system_prompt=RELEASE_NOTES_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
