from __future__ import annotations

import json
from typing import Any

import pytest

from mimo_commit.config import MiMoConfig
from mimo_commit.mimo_client import MiMoClient, MiMoError


class _FakeResponse:
    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body) if not isinstance(body, str) else body

    def json(self) -> Any:
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


class _FakeSession:
    def __init__(self, response: _FakeResponse | None = None, raise_exc: Exception | None = None):
        self._response = response
        self._raise = raise_exc
        self.headers: dict[str, str] = {}
        self.last_payload: dict[str, Any] | None = None
        self.last_url: str | None = None

    def post(self, url: str, json: dict[str, Any] | None = None, timeout: float = 0):
        self.last_url = url
        self.last_payload = json
        if self._raise is not None:
            raise self._raise
        assert self._response is not None
        return self._response

    def get(self, url: str, timeout: float = 0):
        if self._raise is not None:
            raise self._raise
        assert self._response is not None
        return self._response


def _config() -> MiMoConfig:
    return MiMoConfig(api_key="test-key")


def test_complete_returns_parsed_result():
    body = {
        "model": "mimo-v2.5-instruct",
        "choices": [{"message": {"content": "feat: hello"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105},
    }
    session = _FakeSession(_FakeResponse(200, body))
    client = MiMoClient(_config(), session=session)

    result = client.complete("sys", "user")
    assert result.content == "feat: hello"
    assert result.total_tokens == 105
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 5
    assert result.cost_usd > 0
    assert client.total_requests == 1
    assert session.last_payload is not None
    assert session.last_payload["model"] == "mimo-v2.5-instruct"
    assert session.last_payload["messages"][0]["role"] == "system"
    assert session.last_payload["messages"][1]["content"] == "user"


def test_complete_requires_api_key():
    client = MiMoClient(MiMoConfig(api_key=""))
    with pytest.raises(MiMoError):
        client.complete("sys", "user")


def test_complete_raises_on_http_error():
    session = _FakeSession(_FakeResponse(429, {"error": "rate-limited"}))
    client = MiMoClient(_config(), session=session)
    with pytest.raises(MiMoError):
        client.complete("sys", "user")


def test_complete_raises_on_invalid_json():
    session = _FakeSession(_FakeResponse(200, "<html>oops</html>"))
    client = MiMoClient(_config(), session=session)
    with pytest.raises(MiMoError):
        client.complete("sys", "user")


def test_complete_raises_on_missing_choices():
    session = _FakeSession(_FakeResponse(200, {"choices": []}))
    client = MiMoClient(_config(), session=session)
    with pytest.raises(MiMoError):
        client.complete("sys", "user")


def test_stats_accumulate():
    body = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }
    session = _FakeSession(_FakeResponse(200, body))
    client = MiMoClient(_config(), session=session)
    client.complete("s", "u")
    client.complete("s", "u")
    stats = client.stats()
    assert stats["requests"] == 2
    assert stats["prompt_tokens"] == 20
    assert stats["completion_tokens"] == 4
    assert stats["total_tokens"] == 24


def test_health_check_success_and_failure():
    ok_session = _FakeSession(_FakeResponse(200, {"data": []}))
    assert MiMoClient(_config(), session=ok_session).health_check() is True

    bad_session = _FakeSession(_FakeResponse(503, {"error": "down"}))
    assert MiMoClient(_config(), session=bad_session).health_check() is False
