"""Pytest configuration and fixtures."""

import os
from datetime import datetime
from unittest.mock import patch

import pytest

from sre_bot.agent.state import AgentState, AlertContext


@pytest.fixture(autouse=True)
def mock_env():
    """Mock environment variables for all tests."""
    env = {
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test-key",
        "SLACK_BOT_TOKEN": "xoxb-test-token",
        "SLACK_APP_TOKEN": "xapp-test-token",
        "SLACK_SIGNING_SECRET": "test-signing-secret",
        "PROMETHEUS_URL": "http://localhost:9090",
        "LOKI_URL": "http://localhost:3100",
        "TEMPO_URL": "http://localhost:3200",
        "GITHUB_TOKEN": "ghp-test-token",
        "GITHUB_ORG": "test-org",
    }
    with patch.dict(os.environ, env, clear=False):
        yield


@pytest.fixture
def sample_alert() -> AlertContext:
    """Create a sample alert context for testing."""
    return AlertContext(
        alert_name="HighErrorRate",
        severity="critical",
        service_name="payment-api",
        cluster="production-us-east-1",
        namespace="payments",
        pod="payment-api-5d4f6b7c8-abc12",
        status_code=500,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        description="Error rate is above 5% for the last 5 minutes",
        runbook_url="https://runbooks.example.com/high-error-rate",
        raw_payload={
            "alertname": "HighErrorRate",
            "severity": "critical",
        },
    )


@pytest.fixture
def sample_agent_state(sample_alert: AlertContext) -> AgentState:
    """Create a sample agent state for testing."""
    return AgentState(
        alert=sample_alert,
        slack_channel="C123456",
        slack_thread_ts="1234567890.123456",
    )


@pytest.fixture
def alertmanager_payload() -> dict:
    """Sample Alertmanager webhook payload."""
    from tests.fixtures.sample_alerts import ALERTMANAGER_WEBHOOK_FIRING

    return ALERTMANAGER_WEBHOOK_FIRING.copy()


@pytest.fixture
def prometheus_response() -> dict:
    """Sample Prometheus query response."""
    from tests.fixtures.sample_alerts import PROMETHEUS_QUERY_RESPONSE

    return PROMETHEUS_QUERY_RESPONSE.copy()


@pytest.fixture
def loki_response() -> dict:
    """Sample Loki query response."""
    from tests.fixtures.sample_alerts import LOKI_QUERY_RESPONSE

    return LOKI_QUERY_RESPONSE.copy()


@pytest.fixture
def tempo_response() -> dict:
    """Sample Tempo search response."""
    from tests.fixtures.sample_alerts import TEMPO_SEARCH_RESPONSE

    return TEMPO_SEARCH_RESPONSE.copy()


@pytest.fixture
def github_commits_response() -> list:
    """Sample GitHub commits response."""
    from tests.fixtures.sample_alerts import GITHUB_COMMITS_RESPONSE

    return GITHUB_COMMITS_RESPONSE.copy()
