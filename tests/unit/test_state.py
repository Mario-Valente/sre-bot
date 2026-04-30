"""Tests for agent state models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from sre_copilot.agent.state import (
    AgentState,
    AlertContext,
    GitHubData,
    IncidentAnalysis,
    LogEntry,
    LogsData,
    MetricPoint,
    MetricSeries,
    MetricsData,
    SpanInfo,
    TracesData,
)


class TestAlertContext:
    """Tests for AlertContext model."""

    def test_create_valid_alert(self):
        """Test creating a valid alert context."""
        alert = AlertContext(
            alert_name="HighErrorRate",
            severity="critical",
            service_name="payment-api",
            cluster="production-us-east-1",
            namespace="payments",
            timestamp=datetime.utcnow(),
        )

        assert alert.alert_name == "HighErrorRate"
        assert alert.severity == "critical"
        assert alert.service_name == "payment-api"

    def test_optional_fields(self):
        """Test that optional fields default correctly."""
        alert = AlertContext(
            alert_name="HighErrorRate",
            severity="warning",
            service_name="payment-api",
            cluster="main",
            namespace="production",
            timestamp=datetime.utcnow(),
        )

        assert alert.pod is None
        assert alert.status_code is None
        assert alert.description == ""
        assert alert.runbook_url is None
        assert alert.raw_payload == {}

    def test_severity_validation(self):
        """Test that severity is validated."""
        # Valid severities
        for severity in ["critical", "warning", "info"]:
            alert = AlertContext(
                alert_name="Test",
                severity=severity,
                service_name="test",
                cluster="test",
                namespace="test",
                timestamp=datetime.utcnow(),
            )
            assert alert.severity == severity

        # Invalid severity should raise
        with pytest.raises(ValidationError):
            AlertContext(
                alert_name="Test",
                severity="invalid",
                service_name="test",
                cluster="test",
                namespace="test",
                timestamp=datetime.utcnow(),
            )


class TestMetricsData:
    """Tests for MetricsData model."""

    def test_empty_metrics(self):
        """Test creating empty metrics data."""
        metrics = MetricsData()

        assert metrics.cpu_usage == []
        assert metrics.memory_usage == []
        assert metrics.error_rate_5xx == []
        assert metrics.anomalies_detected == []

    def test_with_series_data(self):
        """Test creating metrics with actual data."""
        series = MetricSeries(
            labels={"pod": "payment-api-abc123"},
            values=[
                MetricPoint(timestamp=1234567890.0, value=0.75),
                MetricPoint(timestamp=1234567905.0, value=0.82),
            ],
        )

        metrics = MetricsData(
            cpu_usage=[series],
            anomalies_detected=["High CPU usage detected: 82%"],
        )

        assert len(metrics.cpu_usage) == 1
        assert len(metrics.cpu_usage[0].values) == 2
        assert metrics.anomalies_detected[0] == "High CPU usage detected: 82%"


class TestLogsData:
    """Tests for LogsData model."""

    def test_empty_logs(self):
        """Test creating empty logs data."""
        logs = LogsData()

        assert logs.error_logs == []
        assert logs.fatal_logs == []
        assert logs.total_error_count == 0

    def test_with_log_entries(self):
        """Test creating logs with entries."""
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level="error",
            message="Connection refused to database",
            labels={"pod": "payment-api-abc123"},
        )

        logs = LogsData(
            error_logs=[entry],
            log_patterns=["Connection refused (x5)"],
            total_error_count=5,
        )

        assert len(logs.error_logs) == 1
        assert logs.error_logs[0].level == "error"
        assert logs.total_error_count == 5


class TestTracesData:
    """Tests for TracesData model."""

    def test_with_spans(self):
        """Test creating traces with span data."""
        span = SpanInfo(
            trace_id="abc123",
            span_id="def456",
            service_name="payment-api",
            operation_name="POST /api/payments",
            duration_ms=1500.0,
            status="error",
            error_message="Timeout",
            timestamp=datetime.utcnow(),
        )

        traces = TracesData(
            failed_traces=[span],
            bottleneck_services=["database-service"],
        )

        assert len(traces.failed_traces) == 1
        assert traces.failed_traces[0].duration_ms == 1500.0
        assert "database-service" in traces.bottleneck_services


class TestIncidentAnalysis:
    """Tests for IncidentAnalysis model."""

    def test_create_analysis(self):
        """Test creating an incident analysis."""
        analysis = IncidentAnalysis(
            summary="High error rate in payment-api due to database connection issues",
            probable_root_cause="Database connection pool exhaustion",
            contributing_factors=[
                "Recent traffic spike",
                "Connection timeout too high",
            ],
            evidence=[
                "Error rate increased from 0.1% to 15%",
                "Database connection errors in logs",
            ],
            suggested_actions=[
                "Increase connection pool size",
                "Add circuit breaker",
            ],
            confidence="high",
            needs_human_escalation=False,
        )

        assert analysis.confidence == "high"
        assert not analysis.needs_human_escalation
        assert len(analysis.suggested_actions) == 2

    def test_escalation_with_reason(self):
        """Test analysis requiring escalation."""
        analysis = IncidentAnalysis(
            summary="Unknown issue affecting payment-api",
            probable_root_cause="Unable to determine",
            contributing_factors=[],
            evidence=[],
            suggested_actions=["Manual investigation required"],
            confidence="low",
            needs_human_escalation=True,
            escalation_reason="Insufficient data to determine root cause",
        )

        assert analysis.needs_human_escalation
        assert analysis.escalation_reason is not None


class TestAgentState:
    """Tests for AgentState model."""

    def test_create_initial_state(self):
        """Test creating initial agent state."""
        alert = AlertContext(
            alert_name="HighErrorRate",
            severity="critical",
            service_name="payment-api",
            cluster="main",
            namespace="production",
            timestamp=datetime.utcnow(),
        )

        state = AgentState(alert=alert)

        assert state.alert == alert
        assert state.metrics is None
        assert state.logs is None
        assert state.traces is None
        assert state.github is None
        assert state.analysis is None
        assert state.errors == []

    def test_state_with_slack_context(self):
        """Test state with Slack metadata."""
        alert = AlertContext(
            alert_name="Test",
            severity="warning",
            service_name="test",
            cluster="test",
            namespace="test",
            timestamp=datetime.utcnow(),
        )

        state = AgentState(
            alert=alert,
            slack_channel="C123456",
            slack_thread_ts="1234567890.123456",
        )

        assert state.slack_channel == "C123456"
        assert state.slack_thread_ts == "1234567890.123456"

    def test_error_accumulation(self):
        """Test that errors can be accumulated."""
        alert = AlertContext(
            alert_name="Test",
            severity="warning",
            service_name="test",
            cluster="test",
            namespace="test",
            timestamp=datetime.utcnow(),
        )

        state = AgentState(
            alert=alert,
            errors=["Prometheus query failed", "Loki timeout"],
        )

        assert len(state.errors) == 2
        assert "Prometheus query failed" in state.errors
