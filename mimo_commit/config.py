"""Configuration loading for MiMo Commit Genius."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class MiMoConfig:
    """Settings for the MiMo API client."""

    api_key: str = ""
    api_base: str = "https://platform.xiaomimimo.com/api/v1"
    model: str = "mimo-v2.5-instruct"
    temperature: float = 0.2
    max_tokens: int = 512
    timeout: float = 60.0


@dataclass
class ReleaseConfig:
    """Settings for semver bump logic."""

    minor_bump_types: list[str] = field(default_factory=lambda: ["feat"])
    patch_bump_types: list[str] = field(
        default_factory=lambda: ["fix", "perf", "revert", "refactor"]
    )
    major_keywords: list[str] = field(
        default_factory=lambda: ["BREAKING CHANGE", "BREAKING-CHANGE"]
    )


@dataclass
class AppConfig:
    mimo: MiMoConfig = field(default_factory=MiMoConfig)
    release: ReleaseConfig = field(default_factory=ReleaseConfig)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> AppConfig:
        """Build a config from environment variables (defaults to ``os.environ``)."""
        e = env if env is not None else os.environ

        def _split(value: str) -> list[str]:
            return [item.strip() for item in value.split(",") if item.strip()]

        mimo = MiMoConfig(
            api_key=e.get("MIMO_API_KEY", ""),
            api_base=e.get("MIMO_API_BASE", "https://platform.xiaomimimo.com/api/v1"),
            model=e.get("MIMO_MODEL", "mimo-v2.5-instruct"),
            temperature=float(e.get("MIMO_TEMPERATURE", "0.2")),
            max_tokens=int(e.get("MIMO_MAX_TOKENS", "512")),
            timeout=float(e.get("MIMO_TIMEOUT", "60")),
        )

        release_defaults = ReleaseConfig()
        release = ReleaseConfig(
            minor_bump_types=(
                _split(e["MIMO_MINOR_BUMP_TYPES"])
                if e.get("MIMO_MINOR_BUMP_TYPES")
                else release_defaults.minor_bump_types
            ),
            patch_bump_types=(
                _split(e["MIMO_PATCH_BUMP_TYPES"])
                if e.get("MIMO_PATCH_BUMP_TYPES")
                else release_defaults.patch_bump_types
            ),
            major_keywords=(
                _split(e["MIMO_MAJOR_BUMP_KEYWORDS"])
                if e.get("MIMO_MAJOR_BUMP_KEYWORDS")
                else release_defaults.major_keywords
            ),
        )

        return cls(mimo=mimo, release=release)
