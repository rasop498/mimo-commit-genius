from __future__ import annotations

import pytest

from mimo_commit.mimo_client import CompletionResult
from mimo_commit.suggester import CommitSuggester


class _StubClient:
    def __init__(self, content: str):
        self._content = content
        self.last_user_prompt: str | None = None
        self.last_system_prompt: str | None = None

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        return CompletionResult(
            content=self._content,
            model="mimo-v2.5-instruct",
            prompt_tokens=50,
            completion_tokens=10,
            total_tokens=60,
            latency_ms=120.0,
            cost_usd=0.0000001,
        )


SAMPLE_DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,4 @@
 def main():
+    print("login")
"""


def test_suggest_returns_parsed_conventional_commit():
    client = _StubClient("feat(app): add login print\n\nemits a debug print during startup")
    suggester = CommitSuggester(client)  # type: ignore[arg-type]
    suggestion = suggester.suggest(SAMPLE_DIFF, branch="feature/login")
    assert suggestion.is_valid
    assert suggestion.parsed is not None
    assert suggestion.parsed.type == "feat"
    assert suggestion.parsed.scope == "app"
    assert "login" in suggestion.parsed.subject
    assert "feature/login" in (client.last_user_prompt or "")


def test_suggest_strips_code_fences():
    client = _StubClient("```\nfeat: hello\n```")
    suggestion = CommitSuggester(client).suggest(SAMPLE_DIFF)  # type: ignore[arg-type]
    assert suggestion.message == "feat: hello"
    assert suggestion.is_valid


def test_suggest_marks_invalid_when_model_returns_garbage():
    client = _StubClient("This is just a sentence with no type.")
    suggestion = CommitSuggester(client).suggest(SAMPLE_DIFF)  # type: ignore[arg-type]
    assert not suggestion.is_valid
    assert suggestion.parsed is None


def test_suggest_passes_forced_type_into_prompt():
    client = _StubClient("fix: handle null")
    CommitSuggester(client).suggest(SAMPLE_DIFF, forced_type="fix")  # type: ignore[arg-type]
    assert "type='fix'" in (client.last_user_prompt or "")


def test_suggest_rejects_unknown_forced_type():
    client = _StubClient("feat: x")
    with pytest.raises(ValueError):
        CommitSuggester(client).suggest(SAMPLE_DIFF, forced_type="bogus")  # type: ignore[arg-type]


def test_suggest_rejects_empty_diff():
    client = _StubClient("feat: x")
    with pytest.raises(ValueError):
        CommitSuggester(client).suggest("")  # type: ignore[arg-type]


def test_suggest_truncates_huge_diff():
    huge = "diff --git a/x b/x\n" + ("+line\n" * 50_000)
    client = _StubClient("feat: x")
    CommitSuggester(client).suggest(huge)  # type: ignore[arg-type]
    assert client.last_user_prompt is not None
    # The truncation notice should be inserted into the diff block
    assert "diff truncated" in client.last_user_prompt
