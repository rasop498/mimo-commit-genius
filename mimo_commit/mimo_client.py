"""Thin client around the Xiaomi MiMo V2.5 chat completions endpoint.

The MiMo API is OpenAI-compatible, but we keep this client minimal so the
library only needs ``requests`` as a hard dependency.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from .config import MiMoConfig

logger = logging.getLogger(__name__)


class MiMoError(RuntimeError):
    """Raised when the MiMo API returns an error or is unreachable."""


@dataclass
class CompletionResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    cost_usd: float


# Rough estimate based on published MiMo V2.5 pricing tiers.
# Treated as a heuristic — the source of truth is your platform invoice.
_TOKEN_COST_USD = 0.0000001


class MiMoClient:
    """Minimal chat-completions client for the MiMo V2.5 API."""

    def __init__(self, config: MiMoConfig, session: requests.Session | None = None):
        self.config = config
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "mimo-commit-genius/0.1",
            }
        )
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0
        self.total_cost = 0.0

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        """Send a chat completion request and return the parsed response."""
        if not self.config.api_key:
            raise MiMoError("MIMO_API_KEY is not configured")

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "stream": False,
        }

        start = time.monotonic()
        try:
            resp = self._session.post(
                f"{self.config.api_base}/chat/completions",
                json=payload,
                timeout=self.config.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise MiMoError(f"MiMo API request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise MiMoError(
                f"MiMo API returned {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise MiMoError(f"MiMo API returned non-JSON body: {exc}") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise MiMoError(f"Unexpected MiMo response shape: {data!r}") from exc

        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        cost_usd = total_tokens * _TOKEN_COST_USD
        latency_ms = (time.monotonic() - start) * 1000

        self.total_requests += 1
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost += cost_usd

        return CompletionResult(
            content=content.strip(),
            model=data.get("model", self.config.model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )

    def stats(self) -> dict[str, Any]:
        return {
            "requests": self.total_requests,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_cost_usd": round(self.total_cost, 8),
        }

    def health_check(self) -> bool:
        """Best-effort liveness check against the ``/models`` endpoint."""
        try:
            resp = self._session.get(f"{self.config.api_base}/models", timeout=10)
        except requests.exceptions.RequestException:
            return False
        return resp.status_code == 200
