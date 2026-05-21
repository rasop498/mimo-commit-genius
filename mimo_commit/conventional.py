"""Conventional Commits v1.0.0 parsing and formatting utilities.

Spec: https://www.conventionalcommits.org/en/v1.0.0/
"""

from __future__ import annotations

import re
from dataclasses import dataclass

VALID_TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)

HEADER_RE = re.compile(
    r"^(?P<type>[a-z]+)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?"
    r":\s*(?P<subject>.+)$"
)

BREAKING_FOOTER_RE = re.compile(
    r"^BREAKING[- ]CHANGE(?:\([^)]+\))?:\s*(?P<text>.+)$",
    re.MULTILINE,
)


@dataclass
class ConventionalCommit:
    type: str
    scope: str | None
    subject: str
    body: str
    footers: list[str]
    breaking: bool
    breaking_description: str | None

    def format(self) -> str:
        """Render the commit back to a multi-line Conventional Commit string."""
        scope = f"({self.scope})" if self.scope else ""
        bang = "!" if self.breaking and not self.breaking_description else ""
        header = f"{self.type}{scope}{bang}: {self.subject}"

        parts = [header]
        if self.body:
            parts.extend(("", self.body.rstrip()))

        footers = list(self.footers)
        if self.breaking and self.breaking_description and not any(
            f.upper().startswith("BREAKING") for f in footers
        ):
            footers.append(f"BREAKING CHANGE: {self.breaking_description}")

        if footers:
            parts.append("")
            parts.extend(footers)

        return "\n".join(parts).rstrip() + "\n"


def parse(message: str) -> ConventionalCommit | None:
    """Parse a commit message string. Returns ``None`` if it does not match the spec."""
    if not message or not message.strip():
        return None

    lines = message.strip().splitlines()
    header = lines[0].strip()
    match = HEADER_RE.match(header)
    if not match:
        return None

    type_ = match.group("type")
    if type_ not in VALID_TYPES:
        return None

    scope = match.group("scope")
    subject = match.group("subject").strip()
    breaking_bang = match.group("breaking") == "!"

    body_lines: list[str] = []
    footers: list[str] = []
    breaking_description: str | None = None

    in_footers = False
    remainder = lines[1:]
    while remainder and not remainder[0].strip():
        remainder.pop(0)

    for line in remainder:
        if not in_footers and _looks_like_footer(line):
            in_footers = True

        if in_footers:
            if line.strip():
                footers.append(line.rstrip())
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    for footer in footers:
        m = re.match(r"^BREAKING[- ]CHANGE(?:\([^)]+\))?:\s*(.+)$", footer)
        if m:
            breaking_description = m.group(1).strip()
            break

    if breaking_description and not breaking_bang:
        breaking = True
    else:
        breaking = breaking_bang or bool(breaking_description)

    return ConventionalCommit(
        type=type_,
        scope=scope,
        subject=subject,
        body=body,
        footers=footers,
        breaking=breaking,
        breaking_description=breaking_description,
    )


_FOOTER_PREFIX_RE = re.compile(r"^[A-Za-z-]+(?:\([^)]+\))?:\s+\S")
_BREAKING_PREFIX_RE = re.compile(r"^BREAKING[- ]CHANGE(?:\([^)]+\))?:\s*\S")


def _looks_like_footer(line: str) -> bool:
    if not line.strip():
        return False
    if _BREAKING_PREFIX_RE.match(line):
        return True
    return bool(_FOOTER_PREFIX_RE.match(line))


def format_commit(
    type: str,
    subject: str,
    *,
    scope: str | None = None,
    body: str = "",
    footers: list[str] | None = None,
    breaking: bool = False,
    breaking_description: str | None = None,
) -> str:
    """Build a well-formed Conventional Commit message from parts."""
    if type not in VALID_TYPES:
        raise ValueError(f"Unsupported type {type!r}; expected one of {VALID_TYPES}")

    commit = ConventionalCommit(
        type=type,
        scope=scope,
        subject=subject.strip(),
        body=body,
        footers=list(footers or []),
        breaking=breaking or bool(breaking_description),
        breaking_description=breaking_description,
    )
    return commit.format()


def is_conventional(message: str) -> bool:
    """Cheap predicate — does the header look like a Conventional Commit?"""
    return parse(message) is not None
