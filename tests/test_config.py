from mimo_commit.config import AppConfig


def test_default_config_when_env_is_empty():
    config = AppConfig.from_env(env={})
    assert config.mimo.api_key == ""
    assert config.mimo.model == "mimo-v2.5-instruct"
    assert config.mimo.api_base.endswith("/api/v1")
    assert config.mimo.temperature == 0.2
    assert "feat" in config.release.minor_bump_types
    assert "fix" in config.release.patch_bump_types


def test_config_reads_env_overrides():
    env = {
        "MIMO_API_KEY": "test-key",
        "MIMO_MODEL": "mimo-v2.5-custom",
        "MIMO_TEMPERATURE": "0.7",
        "MIMO_MAX_TOKENS": "1024",
        "MIMO_MINOR_BUMP_TYPES": "feat, feature",
        "MIMO_MAJOR_BUMP_KEYWORDS": "BREAKING CHANGE,REMOVE",
    }
    config = AppConfig.from_env(env=env)
    assert config.mimo.api_key == "test-key"
    assert config.mimo.model == "mimo-v2.5-custom"
    assert config.mimo.temperature == 0.7
    assert config.mimo.max_tokens == 1024
    assert config.release.minor_bump_types == ["feat", "feature"]
    assert config.release.major_keywords == ["BREAKING CHANGE", "REMOVE"]


def test_config_parses_csv_with_whitespace():
    env = {"MIMO_PATCH_BUMP_TYPES": " fix , perf , revert "}
    config = AppConfig.from_env(env=env)
    assert config.release.patch_bump_types == ["fix", "perf", "revert"]
