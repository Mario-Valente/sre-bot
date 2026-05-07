"""Tests for graph nodes."""

from datetime import datetime

import pytest

from sre_copilot.agent.nodes.extract_context import (
    extract_context,
    parse_alertmanager_payload,
)
from sre_copilot.agent.state import AgentState, AlertContext


class TestExtractContext:
    """Tests for extract_context node."""

    @pytest.mark.asyncio
    async def test_extract_valid_context(self, sample_agent_state: AgentState):
        """Test extracting context from valid state."""
        result = await extract_context(sample_agent_state)

        # Should not have errors
        assert "errors" not in result or len(result.get("errors", [])) == 0

        # Should have enriched alert
        if "alert" in result:
            assert result["alert"].service_name == "payment-api"

    @pytest.mark.asyncio
    async def test_extract_missing_service(self):
        """Test that missing service name is detected."""
        alert = AlertContext(
            alert_name="Test",
            severity="warning",
            service_name="",  # Empty service name
            cluster="main",
            namespace="production",
            timestamp=datetime.utcnow(),
        )
        state = AgentState(alert=alert)

        result = await extract_context(state)

        assert "errors" in result
        assert any("service_name" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_extract_missing_namespace(self):
        """Test that missing namespace is detected."""
        alert = AlertContext(
            alert_name="Test",
            severity="warning",
            service_name="payment-api",
            cluster="main",
            namespace="",  # Empty namespace
            timestamp=datetime.utcnow(),
        )
        state = AgentState(alert=alert)

        result = await extract_context(state)

        assert "errors" in result
        assert any("namespace" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_extract_missing_cluster_defaults_to_unknown(self):
        """Test that missing cluster is enriched with a safe default."""
        alert = AlertContext(
            alert_name="Test",
            severity="warning",
            service_name="payment-api",
            cluster="",
            namespace="production",
            timestamp=datetime.utcnow(),
        )
        state = AgentState(alert=alert)

        result = await extract_context(state)

        assert "errors" not in result
        assert result["alert"].cluster == "unknown"


class TestParseAlertmanagerPayload:
    """Tests for Alertmanager payload parsing."""

    def test_parse_firing_alert(self, alertmanager_payload: dict):
        """Test parsing a firing alert."""
        alert = parse_alertmanager_payload(alertmanager_payload)

        assert alert.alert_name == "HighErrorRate"
        assert alert.severity == "critical"
        assert alert.service_name == "payment-api"
        assert alert.namespace == "production"
        assert alert.cluster == "main"
        assert alert.pod == "payment-api-5d4f6b7c8-abc12"

    def test_parse_alert_with_annotations(self, alertmanager_payload: dict):
        """Test that annotations are extracted."""
        alert = parse_alertmanager_payload(alertmanager_payload)

        assert "Error rate is above 5%" in alert.description
        assert alert.runbook_url == "https://runbooks.example.com/high-error-rate"

    def test_parse_timestamp(self, alertmanager_payload: dict):
        """Test that timestamp is parsed correctly."""
        alert = parse_alertmanager_payload(alertmanager_payload)

        assert alert.timestamp.year == 2024
        assert alert.timestamp.month == 1
        assert alert.timestamp.day == 15

    def test_parse_empty_payload(self):
        """Test parsing empty payload."""
        alert = parse_alertmanager_payload({})

        assert alert.alert_name == "UnknownAlert"
        assert alert.service_name == ""

    def test_parse_severity_mapping(self):
        """Test severity mapping."""
        # Critical
        payload = {
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"severity": "critical", "alertname": "Test"},
                }
            ]
        }
        assert parse_alertmanager_payload(payload).severity == "critical"

        # Warning
        payload["alerts"][0]["labels"]["severity"] = "warning"
        assert parse_alertmanager_payload(payload).severity == "warning"

        # Other -> info
        payload["alerts"][0]["labels"]["severity"] = "unknown"
        assert parse_alertmanager_payload(payload).severity == "info"

    def test_parse_with_common_labels_and_annotations_fallback(self):
        """Test parsing fields from Alertmanager common labels/annotations."""
        payload = {
            "status": "firing",
            "commonLabels": {
                "alertname": "AlertmanagerClusterFailedToSendAlerts",
                "severity": "critical",
                "service": "prometheus-alertmanager",
                "namespace": "monitoring",
                "cluster": "kind-dev",
            },
            "commonAnnotations": {
                "summary": "Alertmanager failed to send notifications",
                "runbook_url": "https://runbooks.example.com/alertmanager-send-failures",
            },
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "pod": "alertmanager-main-0",
                    },
                    "annotations": {},
                }
            ],
        }

        alert = parse_alertmanager_payload(payload)

        assert alert.alert_name == "AlertmanagerClusterFailedToSendAlerts"
        assert alert.severity == "critical"
        assert alert.service_name == "prometheus-alertmanager"
        assert alert.namespace == "monitoring"
        assert alert.cluster == "kind-dev"
        assert "failed to send notifications" in alert.description
        assert alert.runbook_url == "https://runbooks.example.com/alertmanager-send-failures"
