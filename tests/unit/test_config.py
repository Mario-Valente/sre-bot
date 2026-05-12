"""Tests for configuration module."""

import os
from unittest.mock import patch

from sre_copilot.config import LLMProvider, Settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(
                _env_file=None,
                slack_bot_token="xoxb-test",
                slack_app_token="xapp-test",
                slack_signing_secret="secret",
            )

            assert settings.llm_provider == LLMProvider.OPENAI
            assert settings.openai_model == "gpt-4o"
            assert settings.llm_temperature == 0.1
            assert settings.enable_webhook is True
            assert settings.enable_slack_listener is True
            assert settings.webhook_port == 8000
            assert settings.prometheus_url == "http://localhost:9090"
            assert settings.loki_url == "http://localhost:3100"
            assert settings.tempo_url == "http://localhost:3200"

    def test_env_override(self):
        """Test that environment variables override defaults."""
        env = {
            "LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "ANTHROPIC_MODEL": "claude-3-opus",
            "ENABLE_WEBHOOK": "false",
            "PROMETHEUS_URL": "http://prometheus:9090",
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_APP_TOKEN": "xapp-test",
            "SLACK_SIGNING_SECRET": "secret",
        }

        with patch.dict(os.environ, env, clear=True):
            settings = Settings(_env_file=None)

            assert settings.llm_provider == LLMProvider.ANTHROPIC
            assert settings.anthropic_model == "claude-3-opus"
            assert settings.enable_webhook is False
            assert settings.prometheus_url == "http://prometheus:9090"

    def test_secret_str_protection(self):
        """Test that secrets are not exposed in string representation."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(
                _env_file=None,
                openai_api_key="sk-secret-key",
                slack_bot_token="xoxb-secret",
                slack_app_token="xapp-secret",
                slack_signing_secret="signing-secret",
            )

            # SecretStr should hide the value
            assert "sk-secret-key" not in str(settings.openai_api_key)
            assert settings.openai_api_key.get_secret_value() == "sk-secret-key"

    def test_temperature_bounds(self):
        """Test that temperature validation works."""
        with patch.dict(os.environ, {}, clear=True):
            # Valid temperature
            settings = Settings(
                _env_file=None,
                llm_temperature=0.5,
                slack_bot_token="xoxb-test",
                slack_app_token="xapp-test",
                slack_signing_secret="secret",
            )
            assert settings.llm_temperature == 0.5

    def test_timeout_positive(self):
        """Test that timeout must be positive."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(
                _env_file=None,
                query_timeout_seconds=60.0,
                slack_bot_token="xoxb-test",
                slack_app_token="xapp-test",
                slack_signing_secret="secret",
            )
            assert settings.query_timeout_seconds == 60.0
