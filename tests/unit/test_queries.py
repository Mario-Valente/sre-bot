"""Tests for query templates."""

import pytest

from sre_bot.queries.loki import (
    LogQueryType,
    LogQueryValidationError,
    build_loki_query,
    get_incident_log_queries,
)
from sre_bot.queries.prometheus import (
    MetricType,
    QueryValidationError,
    build_prometheus_query,
    get_all_metric_queries,
)
from sre_bot.queries.tempo import (
    TraceQueryType,
    TraceQueryValidationError,
    build_tempo_query,
    get_incident_trace_queries,
)


class TestPrometheusQueries:
    """Tests for Prometheus query templates."""

    def test_build_cpu_query(self):
        """Test building CPU usage query."""
        query = build_prometheus_query(
            MetricType.CPU_USAGE,
            service="payment-api",
            namespace="production",
        )

        assert 'namespace="production"' in query
        assert 'pod=~"payment-api.*"' in query
        assert "container_cpu_usage_seconds_total" in query

    def test_build_error_rate_query(self):
        """Test building error rate query."""
        query = build_prometheus_query(
            MetricType.ERROR_RATE,
            service="payment-api",
            namespace="production",
        )

        assert 'service="payment-api"' in query
        assert 'status=~"5.."' in query

    def test_build_latency_query(self):
        """Test building latency query."""
        query = build_prometheus_query(
            MetricType.LATENCY_P99,
            service="payment-api",
            namespace="production",
        )

        assert "histogram_quantile(0.99" in query
        assert "http_request_duration_seconds_bucket" in query

    def test_get_all_metric_queries(self):
        """Test getting all metric queries at once."""
        queries = get_all_metric_queries(
            service="payment-api",
            namespace="production",
        )

        assert MetricType.CPU_USAGE in queries
        assert MetricType.ERROR_RATE in queries
        assert MetricType.LATENCY_P99 in queries
        assert len(queries) > 0

    def test_validation_empty_service(self):
        """Test that empty service name raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            build_prometheus_query(
                MetricType.CPU_USAGE,
                service="",
                namespace="production",
            )

        assert "cannot be empty" in str(exc_info.value)

    def test_validation_forbidden_characters(self):
        """Test that forbidden characters raise error."""
        with pytest.raises(QueryValidationError) as exc_info:
            build_prometheus_query(
                MetricType.CPU_USAGE,
                service='payment"; DROP TABLE metrics;--',
                namespace="production",
            )

        assert "forbidden characters" in str(exc_info.value)

    def test_validation_too_long(self):
        """Test that too long values raise error."""
        with pytest.raises(QueryValidationError) as exc_info:
            build_prometheus_query(
                MetricType.CPU_USAGE,
                service="a" * 200,
                namespace="production",
            )

        assert "too long" in str(exc_info.value)


class TestLokiQueries:
    """Tests for Loki query templates."""

    def test_build_error_logs_query(self):
        """Test building error logs query."""
        query = build_loki_query(
            LogQueryType.ERROR_LOGS,
            service="payment-api",
            namespace="production",
        )

        assert 'namespace="production"' in query
        assert 'app="payment-api"' in query
        assert 'level="error"' in query

    def test_build_exception_logs_query(self):
        """Test building exception logs query."""
        query = build_loki_query(
            LogQueryType.EXCEPTION_LOGS,
            service="payment-api",
            namespace="production",
        )

        assert "exception" in query.lower() or "stacktrace" in query.lower()

    def test_alt_labels(self):
        """Test using alternative label schema."""
        query = build_loki_query(
            LogQueryType.ERROR_LOGS,
            service="payment-api",
            namespace="production",
            use_alt_labels=True,
        )

        assert 'service="payment-api"' in query

    def test_get_incident_log_queries(self):
        """Test getting incident-relevant log queries."""
        queries = get_incident_log_queries(
            service="payment-api",
            namespace="production",
        )

        assert LogQueryType.ALL_ERRORS in queries
        assert LogQueryType.EXCEPTION_LOGS in queries
        assert len(queries) >= 3

    def test_validation_forbidden_characters(self):
        """Test that forbidden characters raise error."""
        with pytest.raises(LogQueryValidationError) as exc_info:
            build_loki_query(
                LogQueryType.ERROR_LOGS,
                service="payment|api",
                namespace="production",
            )

        assert "forbidden characters" in str(exc_info.value)


class TestTempoQueries:
    """Tests for Tempo query templates."""

    def test_build_error_traces_query(self):
        """Test building error traces query."""
        query = build_tempo_query(
            TraceQueryType.ERROR_TRACES,
            service="payment-api",
        )

        assert 'resource.service.name="payment-api"' in query
        assert "status=error" in query

    def test_build_slow_traces_query(self):
        """Test building slow traces query with custom threshold."""
        query = build_tempo_query(
            TraceQueryType.SLOW_TRACES,
            service="payment-api",
            threshold="500ms",
        )

        assert 'resource.service.name="payment-api"' in query
        assert "duration>500ms" in query

    def test_default_threshold(self):
        """Test that default threshold is used when not specified."""
        query = build_tempo_query(
            TraceQueryType.SLOW_TRACES,
            service="payment-api",
        )

        assert "duration>1s" in query

    def test_get_incident_trace_queries(self):
        """Test getting incident-relevant trace queries."""
        queries = get_incident_trace_queries(
            service="payment-api",
            latency_threshold="2s",
        )

        assert TraceQueryType.ERROR_TRACES in queries
        assert TraceQueryType.SLOW_TRACES in queries
        assert len(queries) >= 3

    def test_validation_invalid_duration(self):
        """Test that invalid duration format raises error."""
        with pytest.raises(TraceQueryValidationError) as exc_info:
            build_tempo_query(
                TraceQueryType.SLOW_TRACES,
                service="payment-api",
                threshold="invalid",
            )

        assert "Invalid duration format" in str(exc_info.value)

    def test_validation_valid_durations(self):
        """Test various valid duration formats."""
        for duration in ["100ms", "1s", "2m", "500us", "1h"]:
            query = build_tempo_query(
                TraceQueryType.SLOW_TRACES,
                service="payment-api",
                threshold=duration,
            )
            assert f"duration>{duration}" in query
