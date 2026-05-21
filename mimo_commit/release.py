"""Suggest the next semantic version based on commits since the last tag."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .config import ReleaseConfig
from .conventional import parse
from .git_utils import GitCommit, parse_version_tag

_HEADER_TYPE_RE = re.compile(r"^(?P<type>[a-zA-Z][a-zA-Z0-9_-]*)(?:\([^)]+\))?(?P<bang>!)?:\s*(?P<subject>.+)$")


class BumpKind(str, Enum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    NONE = "none"


@dataclass
class ReleasePlan:
    current_version: str | None
    next_version: str
    bump: BumpKind
    reason: str
    breaking_subjects: list[str]
    feature_subjects: list[str]
    fix_subjects: list[str]
    other_subjects: list[str]


def _extract_type(message: str) -> tuple[str | None, bool, str | None]:
    """Pull the type/bang/subject out of a header even when the type is custom.

    Returns ``(type, breaking_bang, subject)``. Any field may be ``None``.
    """
    if not message:
        return None, False, None
    header = message.splitlines()[0]
    match = _HEADER_TYPE_RE.match(header)
    if not match:
        return None, False, None
    return match.group("type"), match.group("bang") == "!", match.group("subject").strip()


def _classify(commit: GitCommit, config: ReleaseConfig) -> tuple[BumpKind, str]:
    parsed = parse(commit.message)

    body_upper = (commit.message or "").upper()
    if any(keyword.upper() in body_upper for keyword in config.major_keywords):
        return BumpKind.MAJOR, "BREAKING CHANGE footer"

    # Prefer the strict parser when the message conforms to spec
    if parsed is not None:
        if parsed.breaking:
            return BumpKind.MAJOR, f"breaking change ({parsed.type})"
        if parsed.type in config.minor_bump_types:
            return BumpKind.MINOR, parsed.type
        if parsed.type in config.patch_bump_types:
            return BumpKind.PATCH, parsed.type

    # Fall back to permissive type extraction so custom types in config still apply
    custom_type, bang, _ = _extract_type(commit.message)
    if custom_type is not None:
        if bang:
            return BumpKind.MAJOR, f"breaking change ({custom_type})"
        if custom_type in config.minor_bump_types:
            return BumpKind.MINOR, custom_type
        if custom_type in config.patch_bump_types:
            return BumpKind.PATCH, custom_type

    return BumpKind.NONE, "unclassified"


def _bump_version(version: tuple[int, int, int], bump: BumpKind) -> tuple[int, int, int]:
    major, minor, patch = version
    if bump is BumpKind.MAJOR:
        # Pre-1.0 we still bump minor on "breaking" per common practice
        if major == 0:
            return (0, minor + 1, 0)
        return (major + 1, 0, 0)
    if bump is BumpKind.MINOR:
        return (major, minor + 1, 0)
    if bump is BumpKind.PATCH:
        return (major, minor, patch + 1)
    return version


def _format_version(version: tuple[int, int, int], prefix: str) -> str:
    return f"{prefix}{version[0]}.{version[1]}.{version[2]}"


def plan_release(
    commits: list[GitCommit],
    *,
    current_tag: str | None,
    config: ReleaseConfig | None = None,
    initial_version: str = "0.1.0",
) -> ReleasePlan:
    """Decide whether to release and what the next version should be."""
    cfg = config or ReleaseConfig()
    parsed_current = parse_version_tag(current_tag) if current_tag else None
    prefix = "v" if current_tag and current_tag.lower().startswith("v") else ""

    highest = BumpKind.NONE
    reasons: list[str] = []
    breaking_subjects: list[str] = []
    feature_subjects: list[str] = []
    fix_subjects: list[str] = []
    other_subjects: list[str] = []

    order = {BumpKind.NONE: 0, BumpKind.PATCH: 1, BumpKind.MINOR: 2, BumpKind.MAJOR: 3}

    for commit in commits:
        bump, reason = _classify(commit, cfg)
        if order[bump] > order[highest]:
            highest = bump
            reasons.append(reason)

        # Use the parsed subject when available so callers get a clean string.
        parsed = parse(commit.message)
        if parsed is not None:
            short_subject = parsed.subject
        else:
            _, _, extracted = _extract_type(commit.message)
            short_subject = extracted or commit.subject

        if bump is BumpKind.MAJOR:
            breaking_subjects.append(short_subject)
        elif bump is BumpKind.MINOR:
            feature_subjects.append(short_subject)
        elif bump is BumpKind.PATCH:
            fix_subjects.append(short_subject)
        else:
            other_subjects.append(short_subject)

    current_version_str = current_tag if parsed_current else None

    if parsed_current is None:
        # No prior version tag — propose the initial version regardless of commit shape.
        return ReleasePlan(
            current_version=current_tag,
            next_version=initial_version,
            bump=BumpKind.NONE if not commits else BumpKind.MINOR,
            reason="no prior version tag",
            breaking_subjects=breaking_subjects,
            feature_subjects=feature_subjects,
            fix_subjects=fix_subjects,
            other_subjects=other_subjects,
        )

    if highest is BumpKind.NONE:
        return ReleasePlan(
            current_version=current_version_str,
            next_version=_format_version(parsed_current, prefix),
            bump=BumpKind.NONE,
            reason="no release-worthy commits",
            breaking_subjects=breaking_subjects,
            feature_subjects=feature_subjects,
            fix_subjects=fix_subjects,
            other_subjects=other_subjects,
        )

    new_version = _bump_version(parsed_current, highest)
    return ReleasePlan(
        current_version=current_version_str,
        next_version=_format_version(new_version, prefix),
        bump=highest,
        reason=", ".join(dict.fromkeys(reasons)),
        breaking_subjects=breaking_subjects,
        feature_subjects=feature_subjects,
        fix_subjects=fix_subjects,
        other_subjects=other_subjects,
    )
