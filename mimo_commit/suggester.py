"""Orchestrates commit-message suggestions from a staged diff."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .conventional import VALID_TYPES, ConventionalCommit, parse
from .mimo_client import CompletionResult, MiMoClient
from .prompts import COMMIT_SYSTEM_PROMPT, build_commit_user_prompt

logger = logging.getLogger(__name__)

# Hard cap: keep prompts well under the model context window. We deliberately
# truncate gigantic diffs because commit messages don't need every line.
MAX_DIFF_CHARS = 20_000


@dataclass
class CommitSuggestion:
    message: str
    parsed: ConventionalCommit | None
    completion: CompletionResult

    @property
    def is_valid(self) -> bool:
        return self.parsed is not None


class CommitSuggester:
    """Asks MiMo to produce a Conventional Commit message for a staged diff."""

    def __init__(self, client: MiMoClient):
        self.client = client

    def suggest(
        self,
        diff: str,
        *,
        branch: str = "",
        recent_subjects: list[str] | None = None,
        forced_type: str | None = None,
    ) -> CommitSuggestion:
        if not diff or not diff.strip():
            raise ValueError("Cannot suggest a commit message for an empty diff")

        if forced_type and forced_type not in VALID_TYPES:
            raise ValueError(
                f"Unsupported forced_type {forced_type!r}; expected one of {VALID_TYPES}"
            )

        prompt_diff = _truncate(diff, MAX_DIFF_CHARS)
        user_prompt = build_commit_user_prompt(
            prompt_diff,
            branch=branch,
            recent_subjects=recent_subjects,
            forced_type=forced_type,
        )

        completion = self.client.complete(
            system_prompt=COMMIT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        message = _strip_codefence(completion.content).strip()
        parsed = parse(message)

        if parsed is None:
            logger.warning(
                "MiMo returned a non-conventional commit message; keeping raw output."
            )

        return CommitSuggestion(message=message, parsed=parsed, completion=completion)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit - 200]
    return head + "\n\n... [diff truncated for prompt length] ...\n"


def _strip_codefence(text: str) -> str:
    """Remove a single wrapping code fence if MiMo accidentally adds one."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped
